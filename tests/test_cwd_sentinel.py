"""Companion test for scripts/lib/cwd_sentinel.sh.

Consolidates the 2+1 inline CWD-sentinel forms from aim-model-dispatch:
  Form 1: bmad-dispatch/steps/step-02-launch-and-activate.md:35-41  (strict)
  Form 2: tmux-dispatch/steps/step-02-launch-pane.md:35-41          (strict, byte-identical)
  Form 3: claude-native/workflow.md:65-67                            (loose variant)

Parity rationale
----------------
Forms 1+2 are byte-identical: ``if ! (test -d _ai-memory && test -d _bmad &&
test -d oversight); then echo "FAIL: ..."; echo "CWD: $(pwd)"; echo "Aborting
..."; exit 1; fi; echo "OK: workspace root ($(pwd))"``.

Form 3 diverges on three axes (the 1 known variant):
  - exit code on failure: strict=1 / loose=0 (``echo`` in ``||`` branch exits 0)
  - failure lines: strict=3 / loose=1 (shorter message)
  - success message: strict includes ``($(pwd))`` / loose does not

``--variant strict|loose`` captures this divergence exactly.

Output routing (TASK-071-wide rule, locked by wb):
  stdout -- inline-equivalent output (OK/FAIL messages; parity with inline forms).
  stderr -- net-new output only (arg validation errors; no inline equivalent).

Exit codes under test: 0=ok, 1=markers absent (strict), 2=bad arg.

Harness: stdlib subprocess.run only (no pytest-shell-utilities).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "_ai-memory/pov/skills/aim-model-dispatch/scripts/lib"
)

# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_env() -> dict[str, str]:
    """Minimal deterministic environment -- never inherits os.environ implicitly."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(
    helper: Path,
    *args: str,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(helper), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
        env=env,
    )


def _make_markers(
    base: Path,
    markers: tuple[str, ...] = ("_ai-memory", "_bmad", "oversight"),
) -> None:
    """Create workspace-root marker subdirs in *base*."""
    for m in markers:
        (base / m).mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Session fixture for the helper under test (path via the SCRIPTS_DIR constant)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sentinel() -> Path:
    """Resolved path to cwd_sentinel.sh; fails fast if the file is missing."""
    p = SCRIPTS_DIR / "cwd_sentinel.sh"
    assert p.exists(), f"Helper not found: {p}"
    return p


# ---------------------------------------------------------------------------
# Parametrised correctness matrix
# CWD-check results -> stdout (parity with inline forms).
# stderr must be empty for all CWD-check scenarios.
# ---------------------------------------------------------------------------

_MATRIX = [
    pytest.param(
        ("_ai-memory", "_bmad", "oversight"),
        "strict",
        0,
        "OK: workspace root (",  # path appended; substring sufficient
        id="strict-correct",
    ),
    pytest.param(
        (),
        "strict",
        1,
        "FAIL: CWD is not workspace root",
        id="strict-wrong",
    ),
    pytest.param(
        ("_ai-memory", "_bmad"),  # oversight/ absent
        "strict",
        1,
        "FAIL: CWD is not workspace root",
        id="strict-partial",
    ),
    pytest.param(
        ("_ai-memory", "_bmad", "oversight"),
        "loose",
        0,
        "OK: workspace root\n",  # no path appended; exact-match via `in`
        id="loose-correct",
    ),
    pytest.param(
        (),
        "loose",
        0,  # loose is always non-fatal
        "FAIL: not workspace root",
        id="loose-wrong",
    ),
]


@pytest.mark.parametrize("markers, variant, exp_rc, stdout_frag", _MATRIX)
def test_cwd_sentinel_matrix(
    sentinel: Path,
    tmp_path: Path,
    base_env: dict[str, str],
    markers: tuple[str, ...],
    variant: str,
    exp_rc: int,
    stdout_frag: str,
) -> None:
    """Parametrised matrix: strict/loose x correct/wrong/partial markers.

    CWD-check output is on stdout (parity); stderr must be empty.
    Assert order: returncode -> stdout -> stderr (BP-016 D2-5).
    """
    _make_markers(tmp_path, markers)
    r = _run(
        sentinel,
        "--required-root",
        str(tmp_path),
        "--variant",
        variant,
        cwd=tmp_path,
        env=base_env,
    )
    assert r.returncode == exp_rc
    assert stdout_frag in r.stdout
    assert r.stderr == ""


# ---------------------------------------------------------------------------
# Strict failure: all 3 stdout lines present (parity with inline form)
# ---------------------------------------------------------------------------


def test_strict_failure_stdout_lines(
    sentinel: Path, tmp_path: Path, base_env: dict[str, str]
) -> None:
    """Strict failure emits all 3 inline-form stdout lines; stderr stays empty."""
    r = _run(sentinel, "--required-root", str(tmp_path), cwd=tmp_path, env=base_env)
    assert r.returncode == 1
    assert (
        "FAIL: CWD is not workspace root. Expected _ai-memory/, _bmad/, oversight/ all present."
        in r.stdout
    )
    assert "CWD: " in r.stdout
    assert "Aborting dispatch. cd to workspace root and re-invoke." in r.stdout
    assert r.stderr == ""


# ---------------------------------------------------------------------------
# Arg-error edge cases: net-new output -> stderr; stdout must be empty
# ---------------------------------------------------------------------------


def test_unknown_variant_exits_two(
    sentinel: Path, tmp_path: Path, base_env: dict[str, str]
) -> None:
    """Unknown --variant -> exit 2; error + usage in stderr; stdout empty."""
    r = _run(sentinel, "--variant", "bogus", cwd=tmp_path, env=base_env)
    assert r.returncode == 2
    assert r.stdout == ""
    assert "Usage" in r.stderr


def test_unknown_flag_exits_two(
    sentinel: Path, tmp_path: Path, base_env: dict[str, str]
) -> None:
    """Unknown flag -> exit 2; error + usage in stderr; stdout empty."""
    r = _run(sentinel, "--unknown", cwd=tmp_path, env=base_env)
    assert r.returncode == 2
    assert r.stdout == ""
    assert "Usage" in r.stderr


# ---------------------------------------------------------------------------
# Defaults and CWD-relative path
# ---------------------------------------------------------------------------


def test_default_variant_is_strict(
    sentinel: Path, tmp_path: Path, base_env: dict[str, str]
) -> None:
    """No --variant flag -> defaults to strict -> exit 1; FAIL on stdout when markers absent."""
    r = _run(sentinel, "--required-root", str(tmp_path), cwd=tmp_path, env=base_env)
    assert r.returncode == 1
    assert "FAIL" in r.stdout
    assert r.stderr == ""


def test_no_required_root_uses_cwd(
    sentinel: Path, tmp_path: Path, base_env: dict[str, str]
) -> None:
    """Without --required-root, checks markers relative to CWD (subprocess cwd=).

    Exercises the relative-marker code path (else-branch of required_root check).
    """
    _make_markers(tmp_path)
    r = _run(sentinel, cwd=tmp_path, env=base_env)
    assert r.returncode == 0
    assert "OK: workspace root" in r.stdout
    assert r.stderr == ""
