"""BUG-530 — index-shaped retrieval failures must surface as a degraded-mode signal.

A collection that lost its `timestamp` payload index makes `MemorySearch.get_recent()`
raise `QdrantUnavailable` instead of returning rows. Every SessionStart consumer used to
swallow that into a `logger.warning` plus an empty injection, so the operator saw a
normal-looking session with no memory and no reason why.

Coverage (one per consumer surface):
  T-P2-01 — Claude Code hook, Parzival compact path: notice on stderr + in additionalContext
  T-P2-02 — Claude Code hook, non-Parzival compact path: same
  T-P2-03 — Claude Code hook: a non-index QdrantUnavailable stays silent (no false positive)
  T-P2-04 — codex/cursor/gemini adapters: index-shaped error → DEGRADED_OUTPUT on stdout
  T-P2-05 — codex/cursor/gemini adapters: non-index error → EMPTY_OUTPUT (no false positive)
  T-P2-06 — marker matching is case-insensitive and message-based, not type-based

All tests are hermetic — no Qdrant, no network.
"""

import contextlib
import importlib.util
import io
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from memory.qdrant_client import QdrantUnavailable

_REPO_ROOT = Path(__file__).parent.parent

# Hook script is not importable as a package — same path shim the other hook tests use
sys.path.insert(0, str(_REPO_ROOT / ".claude" / "hooks" / "scripts"))

# The exact wrapping search.get_recent() applies to the Qdrant error
INDEX_ERROR = QdrantUnavailable(
    "Get recent failed: Bad request: No range index for `order_by` key: timestamp. "
    "Please create one to use `order_by`"
)
OTHER_ERROR = QdrantUnavailable("Get recent failed: Connection refused")

_ADAPTERS = {
    "codex": (
        _REPO_ROOT / "src" / "memory" / "adapters" / "codex" / "session_start.py",
        {"hookSpecificOutput": {"systemMessage": ""}},
    ),
    "cursor": (
        _REPO_ROOT / "src" / "memory" / "adapters" / "cursor" / "session_start.py",
        {"additional_context": ""},
    ),
    "gemini": (
        _REPO_ROOT / "src" / "memory" / "adapters" / "gemini" / "session_start.py",
        {"hookSpecificOutput": {"additionalContext": ""}},
    ),
}


def _load_adapter(path: Path, name: str):
    """Load an adapter via importlib (hermetic, no sys.modules pollution)."""
    spec = importlib.util.spec_from_file_location(f"{name}_session_start_p2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _json_from_stdout(captured_out: str) -> dict:
    """Return the single JSON object the surface wrote to stdout."""
    for line in captured_out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"No JSON object on stdout. Got: {captured_out!r}")


# ---------------------------------------------------------------------------
# Claude Code hook (.claude/hooks/scripts/session_start.py)
# ---------------------------------------------------------------------------


def _mock_config(parzival_enabled: bool):
    config = MagicMock()
    config.parzival_enabled = parzival_enabled
    config.project_name = "test-project"
    config.token_budget = 2000
    config.qdrant_host = "localhost"
    config.qdrant_port = 26350
    config.qdrant_api_key = SecretStr("test-key")
    config.github_repo = "test-project"
    config.embedding_host = "localhost"
    config.embedding_port = 28080
    return config


def _run_compact_main(parzival_enabled: bool, error: Exception):
    """Run session_start.main() on the compact trigger with get_recent() raising."""
    config = _mock_config(parzival_enabled)

    searcher = MagicMock()
    searcher.get_recent.side_effect = error
    searcher.close.return_value = None

    state = MagicMock()
    state.compact_count = 0

    with contextlib.ExitStack() as ctx:
        ctx.enter_context(
            patch("memory.search.MemorySearch", MagicMock(return_value=searcher))
        )
        ctx.enter_context(
            patch("memory.config.get_config", MagicMock(return_value=config))
        )
        ctx.enter_context(
            patch("memory.health.check_qdrant_health", MagicMock(return_value=True))
        )
        ctx.enter_context(patch("memory.qdrant_client.get_qdrant_client", MagicMock()))
        ctx.enter_context(
            patch(
                "memory.injection.InjectionSessionState.load",
                MagicMock(return_value=state),
            )
        )
        ctx.enter_context(
            patch(
                "session_start.parse_hook_input",
                return_value={
                    "cwd": "/test",
                    "session_id": f"sess_p2_{uuid.uuid4().hex[:8]}",
                    "source": "compact",
                },
            )
        )
        ctx.enter_context(
            patch("session_start.resolve_project_id", return_value="test-project")
        )
        ctx.enter_context(
            patch("session_start._detect_agent_id", return_value="default")
        )
        ctx.enter_context(patch("session_start.cleanup_dedup_lock"))
        ctx.enter_context(patch("session_start.check_qdrant_health", return_value=True))
        ctx.enter_context(patch("session_start.emit_trace_event", None))
        ctx.enter_context(patch("session_start.get_config", return_value=config))

        from session_start import main

        with contextlib.suppress(SystemExit):
            main()


@pytest.mark.parametrize("parzival_enabled", [True, False])
def test_hook_surfaces_index_failure_as_degraded_signal(capsys, parzival_enabled):
    """T-P2-01/02: hook emits valid JSON AND the degraded notice, not a bare empty result."""
    from session_start import DEGRADED_INDEX_NOTICE

    _run_compact_main(parzival_enabled, INDEX_ERROR)
    captured = capsys.readouterr()

    output = _json_from_stdout(captured.out)
    assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert DEGRADED_INDEX_NOTICE in output["hookSpecificOutput"]["additionalContext"]
    assert DEGRADED_INDEX_NOTICE in captured.err


def test_hook_stays_silent_for_non_index_failure(capsys):
    """T-P2-03: an unrelated QdrantUnavailable must not claim a missing index."""
    from session_start import DEGRADED_INDEX_NOTICE

    _run_compact_main(False, OTHER_ERROR)
    captured = capsys.readouterr()

    output = _json_from_stdout(captured.out)
    assert output["hookSpecificOutput"]["additionalContext"] == ""
    assert DEGRADED_INDEX_NOTICE not in captured.err


# ---------------------------------------------------------------------------
# Codex / Cursor / Gemini adapters
# ---------------------------------------------------------------------------


def _run_adapter(module, error: Exception):
    """Run an adapter's main() with bootstrap retrieval raising `error`."""
    payload = json.dumps({"session_id": "sess-p2", "cwd": "/test"})

    with contextlib.ExitStack() as ctx:
        ctx.enter_context(patch.object(sys, "stdin", io.StringIO(payload)))
        ctx.enter_context(patch("memory.config.MemoryConfig", MagicMock()))
        ctx.enter_context(
            patch("memory.health.check_qdrant_health", MagicMock(return_value=True))
        )
        ctx.enter_context(patch("memory.qdrant_client.get_qdrant_client", MagicMock()))
        ctx.enter_context(
            patch("memory.project.resolve_project_id", return_value="test-project")
        )
        ctx.enter_context(patch("memory.search.MemorySearch", MagicMock()))
        ctx.enter_context(
            patch("memory.injection.retrieve_bootstrap_context", side_effect=error)
        )

        assert module.main() == 0


@pytest.mark.parametrize("adapter_name", sorted(_ADAPTERS))
def test_adapter_surfaces_index_failure_as_degraded_signal(capsys, adapter_name):
    """T-P2-04: each adapter emits its own degraded payload, not a bare empty result."""
    path, empty_output = _ADAPTERS[adapter_name]
    module = _load_adapter(path, adapter_name)

    _run_adapter(module, INDEX_ERROR)
    output = _json_from_stdout(capsys.readouterr().out)

    assert output == module.DEGRADED_OUTPUT
    assert output != empty_output
    assert module.DEGRADED_INDEX_NOTICE in json.dumps(output, ensure_ascii=False)


@pytest.mark.parametrize("adapter_name", sorted(_ADAPTERS))
def test_adapter_stays_silent_for_non_index_failure(capsys, adapter_name):
    """T-P2-05: an unrelated QdrantUnavailable must not claim a missing index."""
    path, empty_output = _ADAPTERS[adapter_name]
    module = _load_adapter(path, adapter_name)

    _run_adapter(module, OTHER_ERROR)
    output = _json_from_stdout(capsys.readouterr().out)

    assert output == empty_output


# ---------------------------------------------------------------------------
# Marker matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Get recent failed: No range index for `order_by` key: timestamp", True),
        ("get recent failed: no range index for order_by key: timestamp", True),
        ('Index required but not found for "timestamp"', True),
        ("Get recent failed: Connection refused", False),
        ("Get recent failed: timed out", False),
    ],
)
def test_index_shaped_matching_is_message_based(message, expected):
    """T-P2-06: detection keys off the message, not the exception type."""
    from session_start import is_index_shaped_error

    # Same exception type both ways — only the message decides.
    assert is_index_shaped_error(QdrantUnavailable(message)) is expected
    # A non-QdrantUnavailable carrying the same message is treated identically.
    assert is_index_shaped_error(RuntimeError(message)) is expected
