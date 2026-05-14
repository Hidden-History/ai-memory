"""
Regression tests for init-sanctum.py file-level idempotency (PLAN-027 Phase D, T1-T4).

W-04 empirical verification: NEVER overwrite existing sanctum files.

Tests run init-sanctum.py via subprocess against a fresh tmp_path fixture,
asserting observable behaviour at the filesystem level.
"""

import hashlib
import subprocess
import sys
import time
from pathlib import Path

# Path to the script under test — resolved relative to this file
SCRIPT = Path(__file__).parent.parent / "scripts" / "init-sanctum.py"

# Skill path for the invocation (aim-agent-sanctum-init/ root)
SKILL_PATH = Path(__file__).parent.parent

EXPECTED_FILES = [
    "CREED.md",
    "PERSONA.md",
    "INDEX.md",
    "BOND.md",
    "LORE.md",
    "MEMORY.md",
    "CAPABILITIES.md",
    "PULSE.md",
]


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal _ai-memory/ tree with config.yaml for testing."""
    ai_mem = tmp_path / "_ai-memory"
    (ai_mem / "core").mkdir(parents=True)
    (ai_mem / "core" / "config.yaml").write_text(
        "user_name: TestUser\ncommunication_language: English\n"
    )
    return tmp_path


def _run_script(project_root: Path) -> subprocess.CompletedProcess:
    """Run init-sanctum.py and return the completed process."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(project_root), str(SKILL_PATH)],
        capture_output=True,
        text=True,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_T1_empty_sanctum_creates_eight_files(tmp_path):
    """T1: Fresh sanctum dir → init-sanctum.py creates all 8 standard files from templates."""
    import re

    project_root = _make_project(tmp_path)
    result = _run_script(project_root)

    assert (
        result.returncode == 0
    ), f"Script exited non-zero.\nstdout: {result.stdout}\nstderr: {result.stderr}"

    sanctum = project_root / "_ai-memory" / "sanctum" / "parzival"
    assert sanctum.is_dir(), f"Sanctum directory not created at {sanctum}"

    created = {f.name for f in sanctum.iterdir() if f.is_file()}
    assert set(EXPECTED_FILES).issubset(
        created
    ), f"Missing files after first run: {set(EXPECTED_FILES) - created}"

    # T1 placeholder-leakage check — grep all 8 output files for unfilled {} patterns.
    # ALL {key} patterns in output are leaks — substitute_vars should have filled the
    # 6 allowed keys; any unfilled pattern (allowed or unknown) indicates a substitution
    # failure or template typo (e.g., {USER_NAME} vs {user_name} casing).
    placeholder_re = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_-]*)\}")
    leaks = []
    for fname in EXPECTED_FILES:
        content = (sanctum / fname).read_text()
        for match in placeholder_re.finditer(content):
            key = match.group(1)
            # ALL {} patterns in output are leaks — substitute_vars should have
            # filled the 6 allowed keys; any unfilled pattern (allowed or unknown)
            # indicates a substitution failure or template typo (e.g., {USER_NAME}
            # vs {user_name} casing).
            leaks.append(f"{fname}: {{{key}}}")
    assert (
        not leaks
    ), "Unfilled placeholder leakage detected in output files:\n" + "\n".join(leaks)


def test_T2_rerun_preserves_all_files(tmp_path):
    """T2: After first run, rerun init-sanctum.py → no file modified (file-level idempotency)."""
    project_root = _make_project(tmp_path)

    # First run — full scaffold
    r1 = _run_script(project_root)
    assert (
        r1.returncode == 0
    ), f"First run failed.\nstdout: {r1.stdout}\nstderr: {r1.stderr}"

    sanctum = project_root / "_ai-memory" / "sanctum" / "parzival"

    # Capture high-resolution mtimes
    mtimes_before = {
        fname: (sanctum / fname).stat().st_mtime_ns for fname in EXPECTED_FILES
    }

    # Brief sleep so that any rewrite would produce a detectable mtime delta
    time.sleep(0.05)

    # Second run
    r2 = _run_script(project_root)
    assert (
        r2.returncode == 0
    ), f"Second run failed.\nstdout: {r2.stdout}\nstderr: {r2.stderr}"

    # Every expected file must be reported as "Preserved" in stdout
    for fname in EXPECTED_FILES:
        assert f"Preserved {fname}" in r2.stdout, (
            f"Expected 'Preserved {fname}' in second-run stdout but not found.\n"
            f"stdout: {r2.stdout}"
        )

    # Mtime must not have changed for any file
    for fname in EXPECTED_FILES:
        fpath = sanctum / fname
        assert (
            fpath.stat().st_mtime_ns == mtimes_before[fname]
        ), f"{fname} was modified on rerun — file-level idempotency violated (mtime changed)"


def test_T3_partial_sanctum_fills_only_missing(tmp_path):
    """T3: Sanctum has 3 of 8 files → init-sanctum.py creates exactly 5 new, preserves 3."""
    project_root = _make_project(tmp_path)
    sanctum = project_root / "_ai-memory" / "sanctum" / "parzival"

    # First run — full scaffold
    r1 = _run_script(project_root)
    assert r1.returncode == 0

    # Keep CREED, PERSONA, BOND — delete the other 5
    keep = {"CREED.md", "PERSONA.md", "BOND.md"}
    delete = set(EXPECTED_FILES) - keep
    for fname in delete:
        (sanctum / fname).unlink()

    # Capture mtime of the 3 preserved files before second run
    mtimes_before = {fname: (sanctum / fname).stat().st_mtime_ns for fname in keep}

    # Brief sleep
    time.sleep(0.05)

    # Second run
    r2 = _run_script(project_root)
    assert (
        r2.returncode == 0
    ), f"Second run failed.\nstdout: {r2.stdout}\nstderr: {r2.stderr}"

    # All 8 files must now exist
    for fname in EXPECTED_FILES:
        assert (
            sanctum / fname
        ).exists(), f"File {fname} still missing after partial-sanctum rerun"

    # The 5 deleted files must be reported as "Created"
    for fname in delete:
        assert f"Created {fname}" in r2.stdout, (
            f"Expected 'Created {fname}' in stdout after partial rerun.\n"
            f"stdout: {r2.stdout}"
        )

    # The 3 preserved files must report "Preserved" and have unchanged mtime
    for fname in keep:
        assert (
            f"Preserved {fname}" in r2.stdout
        ), f"Expected 'Preserved {fname}' in stdout.\nstdout: {r2.stdout}"
        assert (sanctum / fname).stat().st_mtime_ns == mtimes_before[
            fname
        ], f"{fname} was modified when it should have been preserved (partial sanctum run)"


def test_T4_customized_file_preserved(tmp_path):
    """T4: Owner edits BOND.md after first run → second run preserves customization byte-for-byte."""
    project_root = _make_project(tmp_path)
    sanctum = project_root / "_ai-memory" / "sanctum" / "parzival"

    # First run
    r1 = _run_script(project_root)
    assert r1.returncode == 0

    # Simulate owner customization of BOND.md
    bond_path = sanctum / "BOND.md"
    custom_content = (
        "# My Custom Bond\n\n"
        "Owner: Alice\n"
        "Project: Acme AI\n\n"
        "This is my owner-edited BOND content — should never be overwritten.\n"
    )
    bond_path.write_text(custom_content)
    sha_before = _sha256(bond_path)

    # Second run
    r2 = _run_script(project_root)
    assert (
        r2.returncode == 0
    ), f"Second run failed.\nstdout: {r2.stdout}\nstderr: {r2.stderr}"

    # BOND.md must be byte-for-byte identical to the custom content
    sha_after = _sha256(bond_path)
    assert sha_after == sha_before, (
        "BOND.md was overwritten — W-04 idempotency violated, owner customization lost!\n"
        f"SHA before: {sha_before}\nSHA after:  {sha_after}"
    )

    # Confirm "Preserved" reported for BOND.md
    assert (
        "Preserved BOND.md" in r2.stdout
    ), f"Expected 'Preserved BOND.md' in stdout.\nstdout: {r2.stdout}"
