"""Install test: the advisory `aim doctor` hook never fails the install (TD-578, FF-2).

Root cause context: #260 shipped `scripts/aim_doctor.py` as a standalone post-install
drift checker with no install wiring. `run_aim_doctor_advisory` (scripts/install.sh)
now calls it at the end of the full-install success path, but it MUST be report-only:
no `--strict` is passed (so aim_doctor.py's own contract makes a WARNING non-fatal),
and the call is wrapped in `if/then/else` so that even an unexpected nonzero exit
(e.g. a crash in aim_doctor.py) cannot abort the install under install.sh's own
`set -e` — the else branch, not the interpreter, is what catches that case.

These tests exercise the real `run_aim_doctor_advisory` (install.sh sourced minus the
final `main "$@"` line) against a mocked INSTALL_DIR, and assert:

  - a real WARNING-producing config (mismatched COMPOSE_PROFILES) still exits 0.
  - a hard crash in aim_doctor.py (nonzero, non-WARNING exit) still exits 0 — the
    actual behavior `set -euo pipefail` would otherwise abort on.
  - a missing scripts/aim_doctor.py is skipped silently (no invocation attempted).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_AIM_DOCTOR = _SCRIPTS_DIR / "aim_doctor.py"


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """Copy install.sh minus final 'main "$@"' line into tmp_path for safe sourcing."""
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    # install.sh sources _env_split_helpers.sh from its own dir at load time.
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


def _run_advisory(install_sh: Path, install: Path) -> subprocess.CompletedProcess:
    """Run run_aim_doctor_advisory under install.sh's own `set -euo pipefail`."""
    bash_cmd = f"""
set -euo pipefail
source "{install_sh}"
INSTALL_DIR="{install}"
run_aim_doctor_advisory
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


class TestAimDoctorAdvisoryHook:
    def test_missing_aim_doctor_skipped_silently(self, install_sh_no_main, tmp_path):
        install = tmp_path / "install_dir"
        install.mkdir()
        # No scripts/aim_doctor.py at all.

        res = _run_advisory(install_sh_no_main, install)
        assert res.returncode == 0, f"stderr: {res.stderr}"
        assert "aim doctor" not in res.stdout.lower()

    def test_warning_from_aim_doctor_does_not_fail_install(
        self, install_sh_no_main, tmp_path
    ):
        install = tmp_path / "install_dir"
        scripts = install / "scripts"
        scripts.mkdir(parents=True)
        # Real aim_doctor.py, unmodified — exercises its actual WARNING contract.
        (scripts / "aim_doctor.py").write_text(
            _AIM_DOCTOR.read_text(encoding="utf-8"), encoding="utf-8"
        )

        venv_bin = install / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").symlink_to(sys.executable)

        docker = install / "docker"
        docker.mkdir()
        # MONITORING_ENABLED=true derives expected COMPOSE_PROFILES="monitoring";
        # persisting a stale/mismatched value forces check_tier1_derived_state -> WARNING.
        (docker / ".env").write_text(
            "MONITORING_ENABLED=true\n"
            "GITHUB_SYNC_ENABLED=false\n"
            "COMPOSE_PROFILES=\n",
            encoding="utf-8",
        )

        res = _run_advisory(install_sh_no_main, install)
        assert res.returncode == 0, f"stderr: {res.stderr}"
        assert "[WARNING] tier1-compose-profiles" in res.stdout
        assert "1 WARNING(s) found." in res.stdout
        assert "aim doctor: advisory check complete" in res.stdout

    def test_aim_doctor_crash_does_not_fail_install(self, install_sh_no_main, tmp_path):
        install = tmp_path / "install_dir"
        scripts = install / "scripts"
        scripts.mkdir(parents=True)
        # Stub that always crashes — simulates the failure mode the if/then/else
        # wrapping exists to protect against (not the normal WARNING path).
        (scripts / "aim_doctor.py").write_text(
            "import sys\nsys.exit(1)\n", encoding="utf-8"
        )

        venv_bin = install / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").symlink_to(sys.executable)

        res = _run_advisory(install_sh_no_main, install)
        assert res.returncode == 0, (
            f"advisory hook must not abort the install on a nonzero aim_doctor.py "
            f"exit (set -e would otherwise kill it): stderr: {res.stderr}"
        )
        assert "aim doctor: advisory check did not complete cleanly" in res.stdout
