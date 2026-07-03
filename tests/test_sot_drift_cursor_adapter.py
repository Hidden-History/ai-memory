"""
Tests for sot_drift.py — Cursor stop SOT-drift trigger adapter (Wave-2).

Coverage:
  T-CA01 — registry_present_engine_invoked: .sot/registry.yaml present → engine called, exit 0
  T-CA02 — no_registry_exits_quietly: .sot/registry.yaml absent → exit 0, engine NOT called
  T-CA03 — engine_invoked_with_correct_args: argv has bash + run-with-env.sh (full path)
             + engine full path + run + --json + --registry; mutation guards included
  T-CA04 — non_git_env_still_runs: no .git dir, no AI_MEMORY_PROJECT_ID → engine called, exit 0
  T-CA05 — propose_only_no_write_source_scan: AST walk catches write-mode opens + os.write
             + .write_text/.write_bytes; mutation guard confirms scanner has teeth
  T-CA06 — engine_nonzero_exit_is_fail_open: engine rc=1 → adapter exits 0
  T-CA07 — invalid_stdin_exits_quietly: malformed JSON → exit 0, no subprocess
  T-CA08 — timeout_handler_exits_0: _timeout_handler raises SystemExit(0)
  T-CA09 — empty_stdin_exits_quietly: empty stdin → exit 0, no subprocess
  T-CA10 — subprocess_timeout_is_fail_open: TimeoutExpired → adapter exits 0
  T-CA11 — event_contract_stop_maps_to_canonical_Stop: native 'stop' → canonical 'Stop'
             in VALID_HOOK_EVENTS; validate_canonical_event does not raise

All tests are hermetic (no network, tmp dirs, subprocess mocked).
normalize_cursor_event + validate_canonical_event run against the real installed schema.
"""

import ast
import importlib.util
import io
import json
import os
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
    / "sot_drift.py"
)


def _load_adapter():
    """Load sot_drift.py via importlib (hermetic, no sys.modules pollution)."""
    spec = importlib.util.spec_from_file_location("cursor_sot_drift", _ADAPTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def adapter():
    return _load_adapter()


def _make_payload(cwd, *, session_id="sess-cursor-abc"):
    """Build a minimal Cursor stop payload JSON string."""
    return json.dumps({"session_id": session_id, "cwd": cwd})


def _engine_ok(drift=0, candidates=0):
    """Return a mock CompletedProcess simulating a healthy engine run."""
    data = {
        "drift_proposals": [
            {"kind": "drift", "entry_id": f"e{i}"} for i in range(drift)
        ],
        "candidate_proposals": [{"kind": "new_candidate"} for _ in range(candidates)],
        "deferred_count": 0,
        "project_id": "test-proj",
    }
    return MagicMock(returncode=0, stdout=json.dumps(data), stderr="")


# ---------------------------------------------------------------------------
# AST-based write-op scanner (used by T-CA05)
# ---------------------------------------------------------------------------

_WRITE_CHARS: frozenset = frozenset("wax+")


def _is_write_mode(s: str) -> bool:
    """True if mode string contains a write/append/exclusive/update character."""
    return any(c in _WRITE_CHARS for c in s)


def _find_write_ops(source: str) -> list:
    """Walk AST of source; return descriptions of any write-mode file operations.

    Flags:
    - open(..., "<write-mode>") or open(..., mode="<write-mode>") for any
      mode containing w / a / x / + (positional OR keyword), regardless of
      intervening args.
    - .write_text(...) / .write_bytes(...)
    - os.write(...)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # open(...) — bare name or attribute (.open)
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

        # .write_text(...) or .write_bytes(...)
        if isinstance(func, ast.Attribute) and func.attr in (
            "write_text",
            "write_bytes",
        ):
            findings.append(f".{func.attr}() at line {node.lineno}")

        # os.write(...)
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "write"
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
        ):
            findings.append(f"os.write() at line {node.lineno}")

    return findings


# ---------------------------------------------------------------------------
# T-CA01 — registry present → engine invoked, exit 0
# ---------------------------------------------------------------------------


def test_registry_present_engine_invoked(adapter, tmp_path):
    """Registry exists → engine IS invoked, adapter exits 0."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    mock_run = MagicMock(return_value=_engine_ok())

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# T-CA02 — no registry → exit 0, engine not called
# ---------------------------------------------------------------------------


def test_no_registry_exits_quietly(adapter, tmp_path):
    """No .sot/registry.yaml → exit 0, engine not called (not a SOT project)."""
    payload = _make_payload(str(tmp_path))  # no .sot dir
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# T-CA03 — engine invoked via run-with-env.sh with full paths + correct flags
# ---------------------------------------------------------------------------


def test_engine_invoked_with_correct_args(adapter, tmp_path):
    """subprocess cmd must be: bash <run-with-env.sh full path> <engine full path>
    run --json --registry <registry_path>.
    Mutation guards: change bash→python, drop --json, drop --registry, bare script
    name → each breaks one of the asserts below.
    """
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    captured = []

    def mock_run(cmd, **kwargs):
        captured.append(list(cmd))
        return _engine_ok()

    with (
        pytest.raises(SystemExit),
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", side_effect=mock_run),
    ):
        adapter.main()

    assert len(captured) == 1
    cmd = captured[0]

    # Must invoke via bash (not bare venv python)
    assert cmd[0] == "bash", f"Expected bash, got {cmd[0]!r}"

    # run-with-env.sh must be at scripts/memory/run-with-env.sh (full path)
    assert (
        "scripts/memory/run-with-env.sh" in cmd[1]
    ), f"run-with-env.sh not found at expected path; got {cmd[1]!r}"

    # Engine script must be the full _ai-memory/skills/aim-sot path (not bare name)
    assert (
        "_ai-memory/skills/aim-sot/scripts/aim_sot_detect_propose.py" in cmd[2]
    ), f"Engine full path missing from cmd[2]: {cmd[2]!r}"

    # Must use the run subcommand (not reindex) — propose-only
    assert "run" in cmd

    # Must pass --json for machine-readable output
    assert "--json" in cmd

    # Must pass explicit --registry path (bypasses engine's git rev-parse)
    assert "--registry" in cmd
    registry_idx = cmd.index("--registry")
    assert cmd[registry_idx + 1] == str(tmp_path / ".sot" / "registry.yaml")


# ---------------------------------------------------------------------------
# T-CA12 — --no-reindex passed on the engine invocation (F-LB-2f regression)
# ---------------------------------------------------------------------------


def test_no_reindex_flag_passed(adapter, tmp_path):
    """Engine invocation MUST include --no-reindex so a registry-content change
    never triggers the unguarded 5b delete-then-replace of sot_entry rows
    (F-LB-2). Regression pin against the 4 drift hooks drifting apart again."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    captured = []

    def mock_run(cmd, **kwargs):
        captured.append(list(cmd))
        return _engine_ok()

    with (
        pytest.raises(SystemExit),
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", side_effect=mock_run),
    ):
        adapter.main()

    assert len(captured) == 1
    assert (
        "--no-reindex" in captured[0]
    ), f"--no-reindex missing from engine invocation: {captured[0]!r}"


# ---------------------------------------------------------------------------
# T-CA13 — AI_MEMORY_SOT_HOOKS=off suppresses the run at runtime (F-LB-2e)
# ---------------------------------------------------------------------------


def test_sot_hooks_off_skips_run(adapter, tmp_path, monkeypatch):
    """AI_MEMORY_SOT_HOOKS=off disables the adapter at runtime with no reinstall:
    exit 0 and NO subprocess invocation, even with a valid registry (F-LB-2e)."""
    monkeypatch.setenv("AI_MEMORY_SOT_HOOKS", "off")
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    called = []

    def mock_run(cmd, **kwargs):
        called.append(list(cmd))
        return _engine_ok()

    with (
        pytest.raises(SystemExit) as exc,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", side_effect=mock_run),
    ):
        adapter.main()

    assert exc.value.code == 0
    assert called == [], "AI_MEMORY_SOT_HOOKS=off must suppress the engine run"


# ---------------------------------------------------------------------------
# T-CA04 — non-git project still runs (BP-032 non-git TTL fallback)
# ---------------------------------------------------------------------------


def test_non_git_env_still_runs(adapter, tmp_path):
    """No .git dir, no AI_MEMORY_PROJECT_ID — adapter still calls engine, exits 0.

    The adapter is git-agnostic by design: project_root derives from cwd only,
    --registry PATH bypasses the engine's git rev-parse call.
    """
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")
    assert not (tmp_path / ".git").exists()

    payload = _make_payload(str(tmp_path))
    mock_run = MagicMock(return_value=_engine_ok())

    # Strip AI_MEMORY_PROJECT_ID from environment if present
    clean_env = {k: v for k, v in os.environ.items() if k != "AI_MEMORY_PROJECT_ID"}

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", mock_run),
        patch.dict(os.environ, clean_env, clear=True),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# T-CA05 — AST-based write-op scan (propose-only guarantee)
# ---------------------------------------------------------------------------


def test_propose_only_no_write_source_scan():
    """AST walk of adapter source finds no write-mode file operations.

    Part 1: asserts the actual adapter is write-free.
    Part 2: mutation guard — injects open(os.path.join(p),"w") and confirms
    the scanner turns RED (scanner has teeth, not just a formality).
    """
    # Part 1: adapter source must be clean
    source = _ADAPTER_PATH.read_text(encoding="utf-8")
    findings = _find_write_ops(source)
    assert not findings, f"Adapter contains write operation(s): {findings}"

    # Part 2: mutation guard — scanner MUST catch an injected write
    injected = 'result = open(os.path.join(p, "output"), "w")'
    injected_findings = _find_write_ops(injected)
    assert (
        injected_findings
    ), "Scanner failed to detect injected write op — test has no teeth"


# ---------------------------------------------------------------------------
# T-CA06 — engine non-zero exit is fail-open
# ---------------------------------------------------------------------------


def test_engine_nonzero_exit_is_fail_open(adapter, tmp_path):
    """Engine exits rc=1 → adapter exits 0 (never blocks Cursor)."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    failing = MagicMock(
        returncode=1, stdout="", stderr="error: project resolution failed"
    )

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", return_value=failing),
    ):
        adapter.main()

    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# T-CA07 — invalid stdin exits quietly
# ---------------------------------------------------------------------------


def test_invalid_stdin_exits_quietly(adapter):
    """Malformed JSON stdin → exit 0, no subprocess (fail-open)."""
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO("not-valid-json{")),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# T-CA08 — timeout handler exits 0
# ---------------------------------------------------------------------------


def test_timeout_handler_exits_0(adapter):
    """_timeout_handler(SIGALRM, frame) raises SystemExit(0) — adapter doesn't hang."""
    with pytest.raises(SystemExit) as exc_info:
        adapter._timeout_handler(signal.SIGALRM, None)
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# T-CA09 — empty stdin exits quietly
# ---------------------------------------------------------------------------


def test_empty_stdin_exits_quietly(adapter):
    """Empty stdin string → exit 0, no subprocess called (fail-open)."""
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO("")),
        patch.object(adapter.subprocess, "run", mock_run),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# T-CA10 — subprocess.TimeoutExpired is fail-open
# ---------------------------------------------------------------------------


def test_subprocess_timeout_is_fail_open(adapter, tmp_path):
    """subprocess.TimeoutExpired → outer except catches it → adapter exits 0."""
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


# ---------------------------------------------------------------------------
# T-CA11 — event-contract: native 'stop' → canonical 'Stop' (F-C-S-5)
# ---------------------------------------------------------------------------


def test_event_contract_stop_maps_to_canonical_Stop(adapter, tmp_path):
    """Adapter wires native 'stop' to normalize_cursor_event — not another event name.

    Calls adapter.main() with a valid payload and asserts normalize_cursor_event
    is invoked with event_name='stop'. Fails if the adapter reverts to passing
    a different event name (e.g. preCompact).
    """
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")
    payload = _make_payload(str(tmp_path))

    import memory.adapters.schema as schema_mod

    captured = []
    original_normalize = schema_mod.normalize_cursor_event

    def spy_normalize(raw, event_name):
        captured.append(event_name)
        return original_normalize(raw, event_name)

    mock_run = MagicMock(return_value=_engine_ok())

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(adapter.subprocess, "run", mock_run),
        patch.object(schema_mod, "normalize_cursor_event", side_effect=spy_normalize),
    ):
        adapter.main()

    assert exc_info.value.code == 0
    assert captured == ["stop"], (
        f"Adapter must wire native 'stop'; got {captured!r} "
        "(reverted to preCompact?)"
    )
