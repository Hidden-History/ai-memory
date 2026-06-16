"""
Tests for .claude/hooks/scripts/sot_digest_session_start.py — Claude SessionStart
SOT-digest hook (BP-035 Part-2).

Coverage:
  T-DH01 — no_registry_emits_empty_output: no .sot/registry.yaml → EMPTY_OUTPUT, exit 0,
             no subprocess
  T-DH02 — valid_digest_emits_additionalContext: good engine output → correct channel
             payload with rendered digest text in hookSpecificOutput.additionalContext
  T-DH03 — no_registry_engine_error_emits_empty: engine returns {"error":"no_registry"}
             → EMPTY_OUTPUT, exit 0
  T-DH04 — malformed_engine_output_is_fail_open: engine returns non-JSON → EMPTY_OUTPUT
  T-DH05 — empty_stdin_emits_empty_output: empty stdin → EMPTY_OUTPUT, exit 0, no subprocess
  T-DH06 — invalid_stdin_emits_empty_output: bad JSON stdin → EMPTY_OUTPUT, exit 0
  T-DH07 — engine_nonzero_exit_emits_empty_output: engine rc=1 → EMPTY_OUTPUT, exit 0
  T-DH08 — subprocess_timeout_is_fail_open: TimeoutExpired → EMPTY_OUTPUT, exit 0
  T-DH09 — timeout_handler_exits_0: _timeout_handler raises SystemExit(0)
  T-DH10 — worktree_cwd_normalized: /proj/.claude/worktrees/feat → Path(/proj)
  T-DH11 — normal_cwd_unchanged: /proj/src → not mangled
  T-DH12 — propose_only_no_write_source_scan: AST walk + mutation guard
  T-DH13 — engine_invoked_with_correct_args: bash + run-with-env.sh + engine full path
             + digest + --json + --registry; mutation guards
  T-DH14 — empty_digest_lines_emits_empty_output: engine returns digest=[] → EMPTY_OUTPUT
  T-DH15 — render_digest_correct: _render_digest produces expected text shape

All tests are hermetic (no network, tmp dirs, subprocess mocked).
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

_HOOK_PATH = (
    Path(__file__).parent.parent
    / ".claude"
    / "hooks"
    / "scripts"
    / "sot_digest_session_start.py"
)

EMPTY_OUTPUT = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "",
    }
}

SAMPLE_DIGEST = {
    "digest": ["sot/api.md: REST API surface", "sot/db.md: database schema"],
    "count": 2,
    "drift": {"clean": 1, "stale": 0, "unverified": 1},
    "truncated": False,
}


def _load_hook():
    """Load sot_digest_session_start.py via importlib (hermetic, no sys.modules pollution)."""
    spec = importlib.util.spec_from_file_location(
        "sot_digest_session_start", _HOOK_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hook():
    return _load_hook()


def _make_payload(cwd, *, session_id="sess-abc"):
    return json.dumps({"session_id": session_id, "cwd": cwd})


def _engine_digest(digest=None, clean=1, stale=0, unverified=0):
    """Return a mock CompletedProcess simulating a healthy digest engine run."""
    data = {
        "digest": digest if digest is not None else ["entry: some content"],
        "count": len(digest) if digest is not None else 1,
        "drift": {"clean": clean, "stale": stale, "unverified": unverified},
        "truncated": False,
    }
    return MagicMock(returncode=0, stdout=json.dumps(data), stderr="")


# ---------------------------------------------------------------------------
# AST-based write-op scanner (used by T-DH12)
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
# T-DH01 — no registry → EMPTY_OUTPUT, exit 0, no subprocess
# ---------------------------------------------------------------------------


def test_no_registry_emits_empty_output(hook, tmp_path, capsys):
    """No .sot/registry.yaml → EMPTY_OUTPUT to stdout, exit 0, engine not called."""
    payload = _make_payload(str(tmp_path))
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(hook.subprocess, "run", mock_run),
    ):
        hook.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-DH02 — valid digest → correct Claude channel payload
# ---------------------------------------------------------------------------


def test_valid_digest_emits_additionalContext(hook, tmp_path, capsys):
    """Good engine output → hookSpecificOutput.additionalContext with rendered digest."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    mock_run = MagicMock(return_value=_engine_digest(["sot/api.md: REST API"], clean=1))

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(hook.subprocess, "run", mock_run),
    ):
        hook.main()

    assert exc_info.value.code == 0
    mock_run.assert_called_once()
    out = json.loads(capsys.readouterr().out.strip())

    # Must be Claude's exact channel shape
    assert "hookSpecificOutput" in out
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "[ai-memory] SOT digest:" in ctx
    assert "sot/api.md: REST API" in ctx
    assert "drift: 1 clean, 0 stale, 0 unverified" in ctx


# ---------------------------------------------------------------------------
# T-DH03 — engine no_registry error → EMPTY_OUTPUT
# ---------------------------------------------------------------------------


def test_no_registry_engine_error_emits_empty(hook, tmp_path, capsys):
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
        patch.object(hook.subprocess, "run", return_value=no_reg),
    ):
        hook.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-DH04 — malformed engine output → fail-open EMPTY_OUTPUT
# ---------------------------------------------------------------------------


def test_malformed_engine_output_is_fail_open(hook, tmp_path, capsys):
    """Engine returns non-JSON stdout → fail-open EMPTY_OUTPUT, exit 0."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    bad = MagicMock(returncode=0, stdout="not-json{{{", stderr="")

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(hook.subprocess, "run", return_value=bad),
    ):
        hook.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-DH05 — empty stdin → EMPTY_OUTPUT, exit 0
# ---------------------------------------------------------------------------


def test_empty_stdin_emits_empty_output(hook, capsys):
    """Empty stdin → EMPTY_OUTPUT, exit 0, no subprocess."""
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO("")),
        patch.object(hook.subprocess, "run", mock_run),
    ):
        hook.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-DH06 — invalid JSON stdin → EMPTY_OUTPUT, exit 0
# ---------------------------------------------------------------------------


def test_invalid_stdin_emits_empty_output(hook, capsys):
    """Malformed JSON stdin → EMPTY_OUTPUT, exit 0, no subprocess."""
    mock_run = MagicMock()

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO("not-valid-json{")),
        patch.object(hook.subprocess, "run", mock_run),
    ):
        hook.main()

    assert exc_info.value.code == 0
    mock_run.assert_not_called()
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-DH07 — engine non-zero exit → EMPTY_OUTPUT, exit 0
# ---------------------------------------------------------------------------


def test_engine_nonzero_exit_emits_empty_output(hook, tmp_path, capsys):
    """Engine exits rc=1 → EMPTY_OUTPUT, exit 0 (never blocks Claude Code)."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    failing = MagicMock(returncode=1, stdout="", stderr="error: engine failed")

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(hook.subprocess, "run", return_value=failing),
    ):
        hook.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-DH08 — subprocess.TimeoutExpired → fail-open EMPTY_OUTPUT
# ---------------------------------------------------------------------------


def test_subprocess_timeout_is_fail_open(hook, tmp_path, capsys):
    """subprocess.TimeoutExpired → EMPTY_OUTPUT, exit 0."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(
            hook.subprocess,
            "run",
            side_effect=hook.subprocess.TimeoutExpired(["bash"], 20),
        ),
    ):
        hook.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-DH09 — timeout handler exits 0
# ---------------------------------------------------------------------------


def test_timeout_handler_exits_0(hook):
    """_timeout_handler(SIGALRM, frame) raises SystemExit(0)."""
    with pytest.raises(SystemExit) as exc_info:
        hook._timeout_handler(signal.SIGALRM, None)
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# T-DH10 — worktree cwd normalized (unit)
# ---------------------------------------------------------------------------


def test_worktree_cwd_normalized(hook):
    """_normalize_cwd strips .claude/worktrees/<name> suffix."""
    result = hook._normalize_cwd("/project/.claude/worktrees/feat-branch")
    assert result == Path("/project")


# ---------------------------------------------------------------------------
# T-DH11 — normal cwd unchanged (unit)
# ---------------------------------------------------------------------------


def test_normal_cwd_unchanged(hook):
    """_normalize_cwd leaves ordinary paths untouched."""
    result = hook._normalize_cwd("/project/src")
    assert result == Path("/project/src")


# ---------------------------------------------------------------------------
# T-DH12 — AST propose-only write scan + mutation guard
# ---------------------------------------------------------------------------


def test_propose_only_no_write_source_scan():
    """AST walk finds no write-mode ops; mutation guard confirms scanner has teeth."""
    source = _HOOK_PATH.read_text(encoding="utf-8")
    findings = _find_write_ops(source)
    assert not findings, f"Hook contains write operation(s): {findings}"

    injected = 'result = open(os.path.join(p, "output"), "w")'
    assert _find_write_ops(injected), "Scanner failed to detect injected write op"


# ---------------------------------------------------------------------------
# T-DH13 — engine invoked with correct args + mutation guards
# ---------------------------------------------------------------------------


def test_engine_invoked_with_correct_args(hook, tmp_path):
    """subprocess cmd: bash <run-with-env.sh> <engine> digest --json --registry <path>."""
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
        patch.object(hook.subprocess, "run", side_effect=mock_run),
    ):
        hook.main()

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
# T-DH14 — empty digest lines → EMPTY_OUTPUT
# ---------------------------------------------------------------------------


def test_empty_digest_lines_emits_empty_output(hook, tmp_path, capsys):
    """Engine returns digest=[] (empty registry) → EMPTY_OUTPUT, exit 0."""
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text("entries: []\n")

    payload = _make_payload(str(tmp_path))
    empty_digest = MagicMock(
        returncode=0,
        stdout=json.dumps(
            {
                "digest": [],
                "count": 0,
                "drift": {"clean": 0, "stale": 0, "unverified": 0},
                "truncated": False,
            }
        ),
        stderr="",
    )

    with (
        pytest.raises(SystemExit) as exc_info,
        patch.object(sys, "stdin", io.StringIO(payload)),
        patch.object(hook.subprocess, "run", return_value=empty_digest),
    ):
        hook.main()

    assert exc_info.value.code == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out == EMPTY_OUTPUT


# ---------------------------------------------------------------------------
# T-DH15 — _render_digest unit: correct text shape
# ---------------------------------------------------------------------------


def test_render_digest_correct(hook):
    """_render_digest joins lines + drift summary with expected format."""
    data = {
        "digest": ["sot/api.md: REST API", "sot/db.md: database schema"],
        "count": 2,
        "drift": {"clean": 1, "stale": 1, "unverified": 0},
        "truncated": False,
    }
    result = hook._render_digest(data)
    assert result.startswith("[ai-memory] SOT digest:\n")
    assert "sot/api.md: REST API" in result
    assert "sot/db.md: database schema" in result
    assert "drift: 1 clean, 1 stale, 0 unverified" in result


def test_render_digest_empty_returns_empty_string(hook):
    """_render_digest with digest=[] returns empty string."""
    data = {
        "digest": [],
        "count": 0,
        "drift": {"clean": 0, "stale": 0, "unverified": 0},
    }
    assert hook._render_digest(data) == ""
