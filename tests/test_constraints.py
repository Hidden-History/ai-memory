"""Tests for aim-parzival-constraints/scripts/constraints.py.

Script invoked via stdlib subprocess (BP-016 DOMAIN 2). A hermetic fake memory
package is written to tmp_path/.ai-memory/src/ so the script's hardcoded
sys.path.insert(0, ~/.ai-memory/src) resolves to our stubs. plugin-free;
AI_MEMORY_PROJECT_ID unset.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "_ai-memory/pov/skills/aim-parzival-constraints/scripts/constraints.py"
)

_INJECTION_STUB = """\
import json
import os
import pathlib

if os.environ.get("FAKE_INJECTION_FAIL", "0") == "1":
    raise ImportError("test-induced failure")


def _record(name, args, kwargs):
    p = pathlib.Path(os.getcwd()) / "calls.json"
    try:
        data = json.loads(p.read_text())
    except Exception:
        data = {}
    data.setdefault(name, []).append({"args": list(args), "kwargs": kwargs})
    p.write_text(json.dumps(data))


def load_parzival_constraints(*args, **kwargs):
    _record("load", args, kwargs)
    return os.environ.get("FAKE_LOAD_RETURN", "")
"""

_METRICS_STUB = """\
import json
import os
import pathlib


def push_skill_metrics_async(*args, **kwargs):
    p = pathlib.Path(os.getcwd()) / "calls.json"
    try:
        data = json.loads(p.read_text())
    except Exception:
        data = {}
    data.setdefault("push", []).append({"args": list(args), "kwargs": kwargs})
    p.write_text(json.dumps(data))
"""

_TRACE_STUB = """\
import json
import os
import pathlib


def emit_trace_event(*args, **kwargs):
    p = pathlib.Path(os.getcwd()) / "calls.json"
    try:
        data = json.loads(p.read_text())
    except Exception:
        data = {}
    data.setdefault("emit", []).append({"args": list(args), "kwargs": kwargs})
    p.write_text(json.dumps(data))
"""


def _build_fake_memory(tmp_path: Path) -> None:
    mem_dir = tmp_path / ".ai-memory" / "src" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "__init__.py").write_text("")
    (mem_dir / "injection.py").write_text(_INJECTION_STUB)
    (mem_dir / "metrics_push.py").write_text(_METRICS_STUB)
    (mem_dir / "trace_buffer.py").write_text(_TRACE_STUB)


def _run_constraints(
    tmp_path: Path,
    args: list,
    load_return: str = "",
    import_fail: bool = False,
) -> tuple:
    """Run constraints.py out-of-process; return (CompletedProcess, calls dict)."""
    _build_fake_memory(tmp_path)
    env: dict = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
        "HOME": str(tmp_path),
        "FAKE_LOAD_RETURN": load_return,
    }
    if import_fail:
        env["FAKE_INJECTION_FAIL"] = "1"

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
        env=env,
    )

    calls_path = tmp_path / "calls.json"
    calls = json.loads(calls_path.read_text()) if calls_path.exists() else {}
    return result, calls


class TestKnownPhase:
    """Case 1: --phase <value> → load called with that phase, stdout shows constraints."""

    def test_known_phase_passed_to_load(self, tmp_path):
        result, calls = _run_constraints(
            tmp_path,
            args=["--phase", "init"],
            load_return="## Constraint A\n## Constraint B",
        )
        assert result.returncode == 0
        assert len(calls["load"]) == 1
        assert calls["load"][0]["kwargs"]["phase"] == "init"
        assert isinstance(calls["load"][0]["args"][0], str)

    def test_known_phase_output_printed(self, tmp_path):
        result, _ = _run_constraints(
            tmp_path,
            args=["--phase", "init"],
            load_return="## Constraint A\n## Constraint B",
        )
        assert result.returncode == 0
        assert "## Constraint A" in result.stdout
        assert "## Constraint B" in result.stdout


class TestNoPhase:
    """Case 2: no --phase → phase=None, graceful handling of empty result."""

    def test_no_phase_passes_none_to_load(self, tmp_path):
        result, calls = _run_constraints(tmp_path, args=[], load_return="")
        assert result.returncode == 0
        assert len(calls["load"]) == 1
        assert calls["load"][0]["kwargs"]["phase"] is None

    def test_empty_constraints_prints_not_found(self, tmp_path):
        result, _ = _run_constraints(tmp_path, args=[], load_return="")
        assert result.returncode == 0
        assert "No constraint files found" in result.stdout

    def test_empty_constraints_metric_label_empty(self, tmp_path):
        result, calls = _run_constraints(tmp_path, args=[], load_return="")
        assert result.returncode == 0
        assert len(calls["push"]) == 1
        assert calls["push"][0]["args"][:2] == ["aim-parzival-constraints", "empty"]
        assert len(calls["push"][0]["args"]) == 3
        assert "emit" in calls
        assert len(calls["emit"]) == 1


class TestTelemetryShim:
    """Case 3: telemetry shim integration — callables invoked with exact args."""

    def test_push_metrics_success_label(self, tmp_path):
        result, calls = _run_constraints(
            tmp_path, args=[], load_return="## Some constraint"
        )
        assert result.returncode == 0
        assert len(calls["push"]) == 1
        assert calls["push"][0]["args"][:2] == ["aim-parzival-constraints", "success"]
        assert len(calls["push"][0]["args"]) == 3

    def test_emit_trace_event_kwargs(self, tmp_path):
        result, calls = _run_constraints(
            tmp_path, args=[], load_return="## Some constraint"
        )
        assert result.returncode == 0
        assert len(calls["emit"]) == 1
        emit_kw = calls["emit"][0]["kwargs"]
        assert emit_kw["event_type"] == "skill_execution"
        assert emit_kw["data"] == {
            "input": "Skill: aim-parzival-constraints"[:10000],
            "output": "Result: completed"[:10000],
            "metadata": {"skill_name": "aim-parzival-constraints"},
        }
        assert isinstance(emit_kw["session_id"], str)
        assert emit_kw["tags"] == ["skill"]


class TestImportError:
    """Safety-critical early-exit: ImportError on memory.injection → exit 0 + Unavailable."""

    def test_import_error_exits_zero_with_unavailable_message(self, tmp_path):
        result, calls = _run_constraints(tmp_path, args=[], import_fail=True)
        assert result.returncode == 0
        assert "**Unavailable**" in result.stdout
        assert "Traceback" not in result.stderr
        assert calls == {}
