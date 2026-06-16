"""
Tests for src/memory/adapters/cursor/sot_digest_session_start.py — Cursor sessionStart
SOT-digest adapter (BP-035 Part-2).

Coverage:
  T-CA01 — no_registry_emits_empty_output: no .sot/registry.yaml → EMPTY_OUTPUT, exit 0,
             no subprocess
  T-CA02 — valid_digest_emits_additional_context: good engine output → top-level
             {"additional_context": "<text>"} (NOT nested in hookSpecificOutput)
  T-CA03 — no_registry_engine_error_emits_empty: engine {"error":"no_registry"} → EMPTY_OUTPUT
  T-CA04 — malformed_engine_output_is_fail_open: non-JSON engine output → EMPTY_OUTPUT
  T-CA05 — empty_stdin_emits_empty_output: empty stdin → EMPTY_OUTPUT, exit 0, no subprocess
  T-CA06 — invalid_stdin_emits_empty_output: bad JSON → EMPTY_OUTPUT, exit 0
  T-CA07 — engine_nonzero_exit_emits_empty_output: engine rc=1 → EMPTY_OUTPUT, exit 0
  T-CA08 — subprocess_timeout_is_fail_open: TimeoutExpired → EMPTY_OUTPUT, exit 0
  T-CA09 — timeout_handler_exits_0: _timeout_handler raises SystemExit(0)
  T-CA10 — propose_only_no_write_source_scan: AST walk + mutation guard
  T-CA11 — engine_invoked_with_correct_args: bash + run-with-env.sh + engine path
             + digest + --json + --registry
  T-CA12 — event_contract_sessionStart: normalize_cursor_event("sessionStart") → canonical
             "SessionStart" in VALID_HOOK_EVENTS; validate_canonical_event does not raise
  T-CA13 — cursor_output_is_top_level_key: assert "hookSpecificOutput" NOT present in output
             (cursor contract: top-level additional_context, never nested)

All tests are hermetic (no network, tmp dirs, subprocess mocked).
normalize_cursor_event + validate_canonical_event run against the real installed schema.
"""

import ast
import importlib.util
import io
import json
import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ADAPTER_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "memory"
    / "adapters"
    / "cursor"
    / "sot_digest_session_start.py"
)

EMPTY_OUTPUT = {"additional_context": ""}


def _load_adapter():
    """Load sot_digest_session_start.py via importlib (hermetic, no sys.modules pollution)."""
    spec = importlib.util.spec_from_file_location(
        "cursor_sot_digest_session_start", _ADAPTER_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def adapter():
    return _load_adapter()


def _make_payload(cwd, *, session_id="sess-abc"):
    return json.dumps({"session_id": session_id, "cwd": cwd})


def _engine_digest(digest=None, clean=1, stale=0, unverified=0):
    data = {
        "digest": digest if digest is not None else ["entry: some content"],
        "count": len(digest) if digest is not None else 1,
        "drift": {"clean": clean, "stale": stale, "unverified": unverified},
        "truncated": False,
    }
    return MagicMock(returncode=0, stdout=json.dumps(data), stderr="")


# ---------------------------------------------------------------------------
# AST-based write-op scanner (used by T-CA10)
# ---------------------------------------------------------------------------

_WRITE_CHARS: frozenset = frozenset("wax+")


def _is_write_mode(s: str) -> bool:
    return any(c in _WRITE_CHARS for c in s)


def _find_write_ops(source: str) -> list:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        is_open = (isinstance(func, ast.Name) and func.id == "open") or (
            isinstance(func, ast.Attribute) and func.attr == "open"
        )
        if is_open:
            for arg in node.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and _is_write_mode(arg.value)
                ):
                    findings.append(
                        f"open() write mode {arg.value!r} at line {node.lineno}"
                    )
            for kw in node.keywords:
                if (
                    kw.arg == "mode"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                    and _is_write_mode(kw.value.value)
                ):
                    findings.append(
                        f"open(mode={kw.value.value!r}) at line {node.lineno}"
                    )

        if isinstance(func, ast.Attribute) and func.attr in (
            "write_text",
            "write_bytes",
        ):
            findings.append(f".{func.attr}() at line {node.lineno}")

        if (
            isinstance(func, ast.Attribute)
            and func.attr == "write"
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
        ):
            findings.append(f"os.write() at line {node.lineno}")

    return findings


# ---------------------------------------------------------------------------
# T-CA01 — no registry → EMPTY_OUTPUT, exit 0
# ---------------------------------------------------------------------------


def test_no_registry_emits_empty_output(adapter, tmp_path, capsys):
    """No .sot/registry.yaml → EMPTY_OUTPUT to stdout, exit 0, engine not called."""
    payload = _make_payload(str(tmp_path))
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-CA02 — valid digest → top-level additional_context (Cursor-specific shape)
# ---------------------------------------------------------------------------


def test_valid_digest_emits_additional_context(adapter, tmp_path, capsys):
    """Good engine output → top-level {"additional_context": "<text>"} (NOT nested)."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    mock_run = MagicMock(
        return_value=_engine_digest(["sot/api.md: REST API"], clean=1, stale=1)
    )

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_called_once()
    out = json.loads(capsys.readouterr().out.strip())

    # Cursor MUST use top-level additional_context — NOT hookSpecificOutput
    assert "additional_context" in out
    assert "hookSpecificOutput" not in out  # T-CA13 coverage: never nested
    ctx = out["additional_context"]
    assert "[ai-memory] SOT digest:" in ctx
    assert "sot/api.md: REST API" in ctx
    assert "drift: 1 clean, 1 stale, 0 unverified" in ctx


# ---------------------------------------------------------------------------
# T-CA03 — engine no_registry error → EMPTY_OUTPUT
# ---------------------------------------------------------------------------


def test_no_registry_engine_error_emits_empty(adapter, tmp_path, capsys):
    """Engine returns {"error": "no_registry"} → EMPTY_OUTPUT, exit 0."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    no_reg = MagicMock(
        returncode=0,
        stdout=json.dumps({"error": "no_registry", "message": "no registry found"}),
        stderr="",
    )

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", return_value=no_reg),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-CA04 — malformed engine output → fail-open EMPTY_OUTPUT
# ---------------------------------------------------------------------------


def test_malformed_engine_output_is_fail_open(adapter, tmp_path, capsys):
    """Non-JSON engine stdout → fail-open EMPTY_OUTPUT, exit 0."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    bad = MagicMock(returncode=0, stdout="not-json{{{", stderr="")

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", return_value=bad),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-CA05 — empty stdin → EMPTY_OUTPUT, exit 0
# ---------------------------------------------------------------------------


def test_empty_stdin_emits_empty_output(adapter, capsys):
    """Empty stdin → EMPTY_OUTPUT, exit 0, no subprocess."""
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO("")),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-CA06 — invalid JSON stdin → EMPTY_OUTPUT, exit 0
# ---------------------------------------------------------------------------


def test_invalid_stdin_emits_empty_output(adapter, capsys):
    """Malformed JSON stdin → EMPTY_OUTPUT, exit 0, no subprocess."""
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO("not-valid-json{")),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-CA07 — engine non-zero exit → EMPTY_OUTPUT
# ---------------------------------------------------------------------------


def test_engine_nonzero_exit_emits_empty_output(adapter, tmp_path, capsys):
    """Engine exits rc=1 → EMPTY_OUTPUT, exit 0."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    failing = MagicMock(returncode=1, stdout="", stderr="error")

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", return_value=failing),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-CA08 — subprocess.TimeoutExpired → fail-open EMPTY_OUTPUT
# ---------------------------------------------------------------------------


def test_subprocess_timeout_is_fail_open(adapter, tmp_path, capsys):
    """subprocess.TimeoutExpired → EMPTY_OUTPUT, exit 0."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(
            adapter.subprocess,
            "run",
            side_effect=adapter.subprocess.TimeoutExpired(["bash"], 20),
        ),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-CA09 — timeout handler exits 0
# ---------------------------------------------------------------------------


def test_timeout_handler_exits_0(adapter):
    """_timeout_handler(SIGALRM, frame) raises SystemExit(0)."""
    with pytest.raises(SystemExit) as exc_info:
        adapter._timeout_handler(signal.SIGALRM, None)
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# T-CA10 — AST propose-only write scan + mutation guard
# ---------------------------------------------------------------------------


def test_propose_only_no_write_source_scan():
    """AST walk finds no write-mode ops; mutation guard confirms scanner has teeth."""
    source = _ADAPTER_PATH.read_text(encoding="utf-8")
    findings = _find_write_ops(source)
    assert not findings, f"Adapter contains write operation(s): {findings}"

    injected = 'result = open(os.path.join(p, "output"), "w")'
    assert _find_write_ops(injected), "Scanner failed to detect injected write op"


# ---------------------------------------------------------------------------
# T-CA11 — engine invoked with correct args
# ---------------------------------------------------------------------------


def test_engine_invoked_with_correct_args(adapter, tmp_path):
    """subprocess cmd: bash run-with-env.sh engine digest --json --registry <path>."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    captured = []

    def mock_run(cmd, **kwargs):
        captured.append(list(cmd))
        return _engine_digest()

    with (
        pytest.raises(SystemExit),
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", side_effect=mock_run),
    ):
        adapter.main()

    assert len(captured) == 1
    cmd = captured[0]

    assert cmd[0] == "bash", f"Expected bash, got {cmd[0]!r}"
    assert (
        "scripts/memory/run-with-env.sh" in cmd[1]
    ), f"run-with-env.sh missing: {cmd[1]!r}"
    assert (
        "_ai-memory/skills/aim-sot/scripts/aim_sot_consult.py" in cmd[2]
    ), f"Engine path missing: {cmd[2]!r}"
    assert "digest" in cmd
    assert "--json" in cmd
    assert "--registry" in cmd
    registry_idx = cmd.index("--registry")
    assert cmd[registry_idx + 1] == str(tmp_path / ".sot" / "registry.yaml")


# ---------------------------------------------------------------------------
# T-CA12 — event contract: sessionStart (camelCase) normalizes to canonical SessionStart
# ---------------------------------------------------------------------------


def test_event_contract_sessionStart_maps_to_canonical():
    """normalize_cursor_event("sessionStart") → hook_event_name=="SessionStart"
    in VALID_HOOK_EVENTS; validate_canonical_event does not raise.
    """
    from memory.adapters.schema import (
        VALID_HOOK_EVENTS,
        normalize_cursor_event,
        validate_canonical_event,
    )

    payload = {"session_id": "test-sess", "cwd": "/tmp/proj"}
    event = normalize_cursor_event(payload, "sessionStart")

    assert (
        event["hook_event_name"] == "SessionStart"
    ), f"Expected canonical 'SessionStart', got {event['hook_event_name']!r}"
    assert "SessionStart" in VALID_HOOK_EVENTS
    validate_canonical_event(event)  # must not raise


# ---------------------------------------------------------------------------
# T-CA13 — cursor output shape: top-level key, never hookSpecificOutput
# ---------------------------------------------------------------------------


def test_cursor_output_is_top_level_key(adapter, tmp_path, capsys):
    """Cursor digest output must be {"additional_context": ...} NOT {"hookSpecificOutput": ...}."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    mock_run = MagicMock(return_value=_engine_digest(["entry: content"]))

    with (
        pytest.raises(SystemExit),
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    out = json.loads(capsys.readouterr().out.strip())
    assert "additional_context" in out
    assert "hookSpecificOutput" not in out
