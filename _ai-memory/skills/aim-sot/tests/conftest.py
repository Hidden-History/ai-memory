"""Autouse test isolation for the aim-sot suite.

Redirects every machine-local ``~/.ai-memory`` state root to a throwaway tmp
dir so a full ``pytest`` run writes ZERO files into the user's real
``~/.ai-memory`` — the BP-048 per-file hash cache (``sot_file_hash_*``), the 5a
drift cache + reindex locks, the discovery-state file, the shadow git repo, and
the setup sentinel.

The aim-sot tests load each script via :func:`importlib.util.spec_from_file_location`
into their own module globals, so there is no single shared module object to
patch centrally.  This autouse fixture instead discovers the loaded
script-modules referenced by the running test (``request.module``) and patches
the state-root constants on those exact instances — AND one level of nesting
beneath them: ``aim_sot_detect_propose`` does its own internal importlib load of
``aim_sot_shadow``, so ``dp.shadow`` is a SEPARATE module object whose per-entry
/ Layer-1 cache writes (``dp.shadow._DRIFT_STATE_DIR``) the top-level scan alone
would miss.

It is a SAFETY NET *beneath* each test's own patching: a test that already
redirects one of these roots simply overrides this fixture (both use
``monkeypatch``, both are undone at teardown), so no existing per-test isolation
is weakened.
"""

import types

import pytest

# Module-level constant name → subpath under the throwaway home.
# ``_DRIFT_CACHE_DIR`` maps to ``<home>/drift-state`` (not ``<home>``) on
# purpose: the discovery-state file derives from ``_DRIFT_CACHE_DIR.parent``, so
# this keeps that parent inside the throwaway home too.
_STATE_ROOTS: dict[str, tuple[str, ...]] = {
    "_INSTALL_DIR": (),
    "_SHADOW_GIT_ROOT": ("sot-git",),
    "_SETUP_DIR": ("sot-setup",),
    "_DRIFT_STATE_DIR": ("drift-state",),
    "_DRIFT_CACHE_DIR": ("drift-state",),
}


def _redirect_roots(module, home, monkeypatch):
    """Point every known state-root constant on ``module`` at ``home``."""
    for attr, sub in _STATE_ROOTS.items():
        if not hasattr(module, attr):
            continue
        target = home
        for part in sub:
            target = target / part
        monkeypatch.setattr(module, attr, target, raising=False)


@pytest.fixture(autouse=True)
def _isolate_ai_memory_state(request, monkeypatch, tmp_path_factory):
    """Point every ``~/.ai-memory`` state root at a per-test throwaway dir."""
    home = tmp_path_factory.mktemp("ai_memory_home")
    seen: set[int] = set()
    for value in list(vars(request.module).values()):
        if not isinstance(value, types.ModuleType) or id(value) in seen:
            continue
        seen.add(id(value))
        _redirect_roots(value, home, monkeypatch)
        # One level of nesting: a script module that internally importlib-loads
        # another script (e.g. detect_propose's own ``shadow``) holds a SEPARATE
        # module object whose state roots the top-level scan never reaches.
        for nested in list(vars(value).values()):
            if isinstance(nested, types.ModuleType) and id(nested) not in seen:
                seen.add(id(nested))
                _redirect_roots(nested, home, monkeypatch)


# ---------------------------------------------------------------------------
# MUTATION PROOF ONLY -- Shape A (skip-driven), reproducing BUG-536.
# Every test collects and then skips; pytest still exits 0. This must turn the
# job RED via the executed-test floor. REVERTED immediately after the run.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _mutation_proof_force_mass_skip():
    pytest.skip("mutation proof: forced mass-skip (BUG-536 shape)")
