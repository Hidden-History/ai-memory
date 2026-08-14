"""AC-3 fixture pairs: every message consumer branches on cause, not the value.

Each site is driven twice — once with ``cause=opt-out``, once with ``cause=failed``
— and the two runs must differ in a *named, asserted* way. "Behaves differently"
alone is unpinned: appending the cause to one log line would turn every pair green
while the site still gives identical advice. The pinned observable here is the
exact operator-facing string from the story's cause->wording mapping, plus the
exit status where the site has one.

The advice itself is what matters. Telling an operator whose install *failed* to
"set PARZIVAL_ENABLED=true" is advice that cannot work — the package is absent —
and that is the conflation this story exists to remove.

Fixtures are ``spec=MemoryConfig``-bound deliberately (TR-8): a bare ``MagicMock``
makes cause branches take the wrong path and still pass, because
``mock.parzival_enabled_cause == "failed"`` is ``False`` while
``if mock.parzival_enabled_cause:`` is ``True`` and no ``AttributeError`` is raised.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memory.config import MemoryConfig
from memory.parzival_state import CAUSE_FAILED, CAUSE_OPT_OUT, CAUSE_UNKNOWN

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts" / "memory"

_SITES = {
    "handoff": (_SCRIPTS / "parzival_save_handoff.py", 0),
    "decision": (_SCRIPTS / "parzival_save_decision.py", 0),
    # E-3: insight returns 1 where the other two return 0, on the same condition
    # with the same message. Normalising it is a behaviour change this story never
    # authorised, so each site's CURRENT exit code is preserved and asserted.
    "insight": (_SCRIPTS / "parzival_save_insight.py", 1),
}


def _load_module(monkeypatch, script_path: Path, module_name: str):
    """Load a backing script fresh via importlib, evicting any cached version.

    The eviction goes through ``monkeypatch.delitem`` rather than a bare ``del``
    so pytest restores every evicted entry at teardown. A bare ``del`` leaves the
    eviction in place after the test, which makes the rest of the suite's import
    state depend on whether this module ran first -- an order-dependent suite is
    exactly the nondeterminism that makes a failure set unpinnable.
    """
    for key in list(sys.modules.keys()):
        if module_name in key or "parzival_save_common" in key:
            monkeypatch.delitem(sys.modules, key, raising=False)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _disabled_config(cause: str) -> MagicMock:
    """A spec-bound config representing 'not enabled, for this cause'."""
    config = MagicMock(spec=MemoryConfig)
    config.parzival_enabled = False
    config.parzival_enabled_cause = cause
    config.parzival_enabled_condition = "complete"
    return config


def _patch_memory_modules(monkeypatch, config: MagicMock) -> None:
    """Inject fake ``memory.*`` modules so scripts never touch live services."""
    memory_pkg = types.ModuleType("memory")
    cfg_mod = types.ModuleType("memory.config")
    cfg_mod.get_config = MagicMock(return_value=config)
    cfg_mod.MemoryConfig = MemoryConfig
    storage_mod = types.ModuleType("memory.storage")
    storage_mod.MemoryStorage = MagicMock()
    project_mod = types.ModuleType("memory.project")
    project_mod.detect_project = lambda _cwd: "proj"
    project_mod.resolve_project_id = lambda _cwd=None, *, explicit=None: "proj"
    metrics_mod = types.ModuleType("memory.metrics_push")
    metrics_mod.push_skill_metrics_async = MagicMock()
    trace_mod = types.ModuleType("memory.trace_buffer")
    trace_mod.emit_trace_event = MagicMock()

    # The real module under test — the scripts import the mapping from it.
    import memory.parzival_state as real_state

    for name, mod in [
        ("memory", memory_pkg),
        ("memory.config", cfg_mod),
        ("memory.storage", storage_mod),
        ("memory.project", project_mod),
        ("memory.metrics_push", metrics_mod),
        ("memory.trace_buffer", trace_mod),
        ("memory.parzival_state", real_state),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def _run_site(monkeypatch, capsys, site: str, cause: str) -> tuple[int, str]:
    """Run one save script with Parzival disabled for ``cause``; return (rc, stdout)."""
    script_path, _ = _SITES[site]
    _patch_memory_modules(monkeypatch, _disabled_config(cause))
    monkeypatch.setattr(sys, "argv", [script_path.name, "body"])
    module = _load_module(monkeypatch, script_path, f"cause_{site}")
    rc = module.main()
    return rc, capsys.readouterr().out


@pytest.mark.parametrize("site", sorted(_SITES))
class TestSaveScriptsBranchOnCause:
    def test_opt_out_and_failed_produce_different_advice(
        self, monkeypatch, capsys, site
    ):
        rc_opt, out_opt = _run_site(monkeypatch, capsys, site, CAUSE_OPT_OUT)
        rc_failed, out_failed = _run_site(monkeypatch, capsys, site, CAUSE_FAILED)
        assert out_opt != out_failed, f"{site} gives identical advice for both causes"
        # Exit code is preserved per site and is cause-invariant (E-3 untouched).
        assert rc_opt == rc_failed == _SITES[site][1]

    def test_failed_does_not_advise_setting_the_flag(self, monkeypatch, capsys, site):
        """The package is absent; this advice cannot work."""
        _, out = _run_site(monkeypatch, capsys, site, CAUSE_FAILED)
        assert "PARZIVAL_ENABLED=true" not in out, out

    def test_opt_out_advises_setting_the_flag(self, monkeypatch, capsys, site):
        _, out = _run_site(monkeypatch, capsys, site, CAUSE_OPT_OUT)
        assert "PARZIVAL_ENABLED=true" in out, out

    def test_absent_cause_never_claims_the_operator_declined(
        self, monkeypatch, capsys, site
    ):
        """TR-11: the pre-existing-install state must not be reported as opt-out."""
        _, out = _run_site(monkeypatch, capsys, site, CAUSE_UNKNOWN)
        assert "declined" not in out.lower(), out
