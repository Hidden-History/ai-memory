"""Tests for scripts/memory/store_best_practice.py (RISK-021 fix).

Verifies the externalized CLI script:
- routes project-scope through resolve_project_id (NOT env-only),
- passes the resolved group_id to store_best_practice,
- honours the stdout contract (Stored: <id> / Duplicate skipped),
- fails loudly (exit 2) when scope cannot be resolved.

Mock strategy (DEC-109 / CI convention 1):
  resolve_project_id is patched at the call boundary inside memory.project —
  NOT detect_project (patching detect_project is a dead mock; the resolver
  calls it internally and goes green-local / red-CI).

Environment convention (DEC-109 / CI convention 2):
  All tests run with AI_MEMORY_PROJECT_ID unset so resolution is exercised
  through the full-precedence chain (or mocked at the boundary above).

"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "memory" / "store_best_practice.py"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_ARGV = [
    "store_best_practice.py",
    "--content",
    "Always use type hints in Python 3.10+",
    "--session-id",
    "sess-test-001",
]


def _make_resolve_mock(
    return_value: str = "test-project",
    side_effect: Exception | None = None,
) -> MagicMock:
    m = MagicMock()
    if side_effect is not None:
        m.side_effect = side_effect
    else:
        m.return_value = return_value
    return m


def _make_store_mock(
    status: str = "stored",
    memory_id: str | None = "mem-abc-001",
) -> MagicMock:
    m = MagicMock()
    m.return_value = {"status": status, "memory_id": memory_id}
    return m


def _inject_fakes(
    monkeypatch,
    resolve_mock: MagicMock,
    store_mock: MagicMock,
) -> None:
    """Patch memory.project and memory.storage into sys.modules.

    Must be called BEFORE _load_module() so that the ``from memory.*``
    top-level imports in the script bind to the mocks.
    """
    project_mod = types.ModuleType("memory.project")
    project_mod.resolve_project_id = resolve_mock

    storage_mod = types.ModuleType("memory.storage")
    storage_mod.store_best_practice = store_mock

    monkeypatch.setitem(sys.modules, "memory.project", project_mod)
    monkeypatch.setitem(sys.modules, "memory.storage", storage_mod)


def _load_module():
    """Load the script module fresh for each test.

    Evicts any previously cached version so module-level imports rebind to
    the sys.modules patches installed by _inject_fakes().
    """
    for key in list(sys.modules.keys()):
        if "store_best_practice_under_test" in key:
            del sys.modules[key]
    spec = importlib.util.spec_from_file_location(
        "store_best_practice_under_test", _SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_script_exists():
    """Sanity: the script file was created at the expected path."""
    assert _SCRIPT.exists(), f"script not found: {_SCRIPT}"


def test_explicit_group_id_forwarded_to_resolver(monkeypatch):
    """--group-id CLI flag is forwarded to resolve_project_id as explicit=."""
    resolve_mock = _make_resolve_mock("my-explicit-project")
    store_mock = _make_store_mock()
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(sys, "argv", [*_BASE_ARGV, "--group-id", "my-explicit-project"])
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 0
    resolve_mock.assert_called_once()
    assert resolve_mock.call_args.kwargs.get("explicit") == "my-explicit-project"
    assert isinstance(
        resolve_mock.call_args.kwargs.get("cwd"), str
    )  # N-2: cwd always passed


def test_store_receives_resolved_group_id(monkeypatch):
    """store_best_practice is called with the id returned by resolve_project_id."""
    resolve_mock = _make_resolve_mock("resolved-project-id")
    store_mock = _make_store_mock()
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(sys, "argv", _BASE_ARGV)
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 0
    store_mock.assert_called_once()
    assert store_mock.call_args.kwargs["group_id"] == "resolved-project-id"


def test_fail_loud_when_resolver_raises_value_error(monkeypatch, capsys):
    """main() returns 2 and writes to stderr when resolve_project_id raises ValueError.

    store_best_practice must NOT be called — the script halts before storage.
    """
    resolve_mock = _make_resolve_mock(
        side_effect=ValueError(
            "no project scope found — explicit, env, marker, git all absent"
        )
    )
    store_mock = _make_store_mock()
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(sys, "argv", _BASE_ARGV)
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 2
    store_mock.assert_not_called()
    _, err = capsys.readouterr()
    assert "ERROR" in err


def test_stdout_stored_contract(monkeypatch, capsys):
    """Prints 'Stored: <memory_id>' when storage returns status=stored."""
    resolve_mock = _make_resolve_mock("any-project")
    store_mock = _make_store_mock(status="stored", memory_id="mem-xyz-999")
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(sys, "argv", _BASE_ARGV)
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 0
    out, _ = capsys.readouterr()
    assert "Stored: mem-xyz-999" in out


def test_stdout_duplicate_skipped_contract(monkeypatch, capsys):
    """Prints 'Duplicate skipped' when storage returns status=duplicate."""
    resolve_mock = _make_resolve_mock("any-project")
    store_mock = _make_store_mock(status="duplicate", memory_id=None)
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(sys, "argv", _BASE_ARGV)
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 0
    out, _ = capsys.readouterr()
    assert "Duplicate skipped" in out


def test_store_called_with_full_kwargs(monkeypatch):
    """All store_best_practice kwargs are passed correctly from their CLI args."""
    resolve_mock = _make_resolve_mock("proj-full")
    store_mock = _make_store_mock()
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "store_best_practice.py",
            "--content",
            "Use httpx with explicit timeouts",
            "--session-id",
            "sess-999",
            "--source-hook",
            "PostToolUse",
            "--domain",
            "python",
            "--tags",
            "httpx",
            "timeout",
            "--source",
            "https://example.com/httpx-timeouts",
            "--source-date",
            "2026-05-30",
        ],
    )
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 0
    kw = store_mock.call_args.kwargs
    assert kw["content"] == "Use httpx with explicit timeouts"
    assert kw["session_id"] == "sess-999"
    assert kw["source_hook"] == "PostToolUse"
    assert kw["group_id"] == "proj-full"
    assert kw["domain"] == "python"
    assert kw["tags"] == ["httpx", "timeout"]
    assert kw["source"] == "https://example.com/httpx-timeouts"
    assert kw["source_date"] == "2026-05-30"
    assert kw["auto_seeded"] is True


def test_no_env_explicit_no_group_id_calls_resolver_without_explicit(monkeypatch):
    """When --group-id is omitted, resolver is called with explicit=None (env-tier path)."""
    resolve_mock = _make_resolve_mock("env-resolved-project")
    store_mock = _make_store_mock()
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(sys, "argv", _BASE_ARGV)  # no --group-id
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 0
    resolve_mock.assert_called_once()
    # explicit= must be None — resolver handles env/marker/git tiers internally
    assert resolve_mock.call_args.kwargs.get("explicit") is None


def test_no_sys_path_insert_in_script():
    """Script must not use the sys.path.insert anti-pattern (BP-013 Pattern B)."""
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "sys.path.insert" not in src, (
        "store_best_practice.py must not use sys.path.insert — "
        "run-with-env.sh supplies the venv (BP-013 Pattern B)"
    )


def test_script_uses_resolve_project_id():
    """Script must call resolve_project_id (not inline env-only resolution)."""
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "resolve_project_id" in src
    assert 'os.environ.get("AI_MEMORY_PROJECT_ID")' not in src, (
        "store_best_practice.py must not contain env-only resolution — "
        "that is the RISK-021 defect being fixed"
    )


def test_storage_value_error_returns_exit_2(monkeypatch, capsys):
    """main() returns 2 and writes to stderr when store_best_practice raises ValueError.

    Distinct from the resolver-ValueError path: this exercises the storage
    validation guard (e.g. empty group_id, content too short) → exit 2.
    """
    resolve_mock = _make_resolve_mock("any-project")
    store_mock = _make_store_mock()
    store_mock.side_effect = ValueError("group_id is required and must be non-empty")
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(sys, "argv", _BASE_ARGV)
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 2
    _, err = capsys.readouterr()
    assert "ERROR" in err


def test_unknown_status_warns_to_stderr(monkeypatch, capsys):
    """Unknown status from storage prints WARNING to stderr; stdout stays empty; exit 1.

    Covers the else branch added by M-1. Non-zero exit signals false-success
    avoidance: storage may return "blocked" or "failed" — those are real failure
    conditions, not silent successes.
    """
    resolve_mock = _make_resolve_mock("any-project")
    store_mock = _make_store_mock(status="unexpected-status", memory_id=None)
    _inject_fakes(monkeypatch, resolve_mock, store_mock)
    monkeypatch.setattr(sys, "argv", _BASE_ARGV)
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mod = _load_module()
    rc = mod.main()

    assert rc == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "WARNING" in err
