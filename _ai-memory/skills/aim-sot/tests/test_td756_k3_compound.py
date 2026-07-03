"""TD-756: K3 must not false-flag a valid compound drift_check.

`_check_K3` took ``tokens[0]`` and PATH-resolved it, so a compound command
leading with a shell builtin (``cd site && npm run build``) resolved ``cd`` →
not on PATH → a false CONDITIONAL. K3 now splits on shell operators, strips
leading ``VAR=val`` assignments, skips builtins, and PATH-checks the first real
executable of each sub-command — so a valid compound no longer false-flags while
a genuinely-missing binary still warns.

Run targeted only:
    pytest tests/test_td756_k3_compound.py
"""

import importlib.util
import shutil
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


verify = _load("aim_sot_verify")

# A binary that is reliably present on PATH in CI (sh is POSIX-guaranteed).
_REAL = "sh" if shutil.which("sh") else "python3"


def _entry(drift_check):
    return {"id": "e", "drift_check": drift_check}


def test_compound_leading_builtin_not_false_flagged():
    """`cd x && <real>` resolves the real binary, not `cd` → no warning."""
    failures, warnings = verify._check_K3(
        [_entry(f"cd website && {_REAL} -c 'true'")], exec_drift_checks=False
    )
    assert failures == []
    assert warnings == [], f"valid compound must not warn, got {warnings}"


def test_env_assignment_prefix_skipped():
    """A leading `VAR=val` env-assignment is not treated as the binary."""
    _, warnings = verify._check_K3(
        [_entry(f"FOO=bar {_REAL} -c 'true'")], exec_drift_checks=False
    )
    assert warnings == []


def test_missing_binary_in_compound_still_warns():
    """`cd x && <missing>` still warns on the genuinely-missing binary."""
    _, warnings = verify._check_K3(
        [_entry("cd website && definitely-not-a-real-binary-xyz build")],
        exec_drift_checks=False,
    )
    assert len(warnings) == 1
    assert "definitely-not-a-real-binary-xyz" in warnings[0]["detail"]


def test_plain_missing_binary_still_warns():
    """A simple missing command is unchanged — still warns."""
    _, warnings = verify._check_K3(
        [_entry("definitely-not-a-real-binary-xyz --check")], exec_drift_checks=False
    )
    assert len(warnings) == 1
    assert "not found on PATH" in warnings[0]["detail"]


def test_bare_builtin_command_no_warning():
    """A command that is ONLY a builtin (bare `cd x`) has nothing to resolve and
    must not false-flag."""
    _, warnings = verify._check_K3([_entry("cd website")], exec_drift_checks=False)
    assert warnings == []


def test_helper_resolves_real_executable():
    """Unit: the resolver skips builtins/operators and returns real binaries."""
    import shlex

    toks = shlex.split("cd site && FOO=1 npm run build")
    assert verify._drift_check_binaries(toks) == ["npm"]
    assert verify._drift_check_binaries(shlex.split("a | b ; c")) == ["a", "b", "c"]
    assert verify._drift_check_binaries(shlex.split("cd only")) == []
