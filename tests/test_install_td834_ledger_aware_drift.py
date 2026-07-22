"""TD-834: the installer oversight-drift warning is ledger-aware.

Before this fix, ``_sync_oversight_templates`` emitted the imperative
``[WARNING] template drifted + upstream changed; review + merge: oversight/<file>``
for EVERY both-changed managed file on EVERY install, even files the operator already
reconciled last session (disposition ``applied``/``dismissed``/``resolved`` at the same
shipped template hash). ``reconcile_helper.py pending`` already suppressed those, so the two
surfaces disagreed. The fix routes the warn-site through ``reconcile_helper.py
is-disposed`` — the SAME terminal-at-hash predicate the session-start consumer uses —
so an already-disposed-at-current-hash file downgrades to a non-imperative info line.

Two layers:
  * ``TestIsDisposedSubcommand`` — the helper query itself (loaded by path, like the
    sibling tests/test_plan033_p2_reconcile_helper.py).
  * ``TestLedgerAwareInstallerWarning`` — the installer end-to-end: source install.sh
    (minus ``main "$@"``), stage the real helper into the mock INSTALL_DIR, drive
    ``deploy_oversight_templates`` and assert on stdout (log_warning/log_info → stdout).

Revert-and-confirm-fail: reverting the install.sh warn-site edit makes
``test_applied_at_current_hash_suppresses_warning`` fail (the imperative warning
re-appears). Verified manually during development; see the PR description.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_HELPERS = _SCRIPTS_DIR / "_env_split_helpers.sh"
_HELPER_SCRIPTS = (
    _REPO / "_ai-memory" / "pov" / "skills" / "aim-content-drift" / "scripts"
)
_HELPER_PATH = _HELPER_SCRIPTS / "reconcile_helper.py"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Layer 1: the `is-disposed` subcommand.
# --------------------------------------------------------------------------- #
_spec = importlib.util.spec_from_file_location("reconcile_helper_td834", _HELPER_PATH)
helper = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = helper
_spec.loader.exec_module(helper)


def _write_ledger(project_root: Path, entries: dict) -> None:
    """entries: {rel_path: {"disposition": ..., "new_template_hash": ...}}."""
    state = project_root / ".audit" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "reconcile-dispositions.json").write_text(
        json.dumps({"schema_version": "1.0", "dispositions": entries}),
        encoding="utf-8",
    )


class TestIsDisposedSubcommand:
    def _run(self, project_root: Path, rel_path: str, h: str) -> int:
        return helper.main(
            [
                "is-disposed",
                "--project-root",
                str(project_root),
                "--id",
                rel_path,
                "--hash",
                h,
            ]
        )

    def test_terminal_at_matching_hash_exits_zero(self, tmp_path, capsys):
        _write_ledger(
            tmp_path, {"t/f.md": {"disposition": "applied", "new_template_hash": "H1"}}
        )
        assert self._run(tmp_path, "t/f.md", "H1") == 0
        assert capsys.readouterr().out.strip() == "applied"

    def test_dismissed_at_matching_hash_exits_zero(self, tmp_path, capsys):
        _write_ledger(
            tmp_path,
            {"t/f.md": {"disposition": "dismissed", "new_template_hash": "H1"}},
        )
        assert self._run(tmp_path, "t/f.md", "H1") == 0
        assert capsys.readouterr().out.strip() == "dismissed"

    def test_moved_hash_exits_one(self, tmp_path):
        _write_ledger(
            tmp_path, {"t/f.md": {"disposition": "applied", "new_template_hash": "OLD"}}
        )
        assert self._run(tmp_path, "t/f.md", "NEW") == 1

    def test_deferred_exits_one(self, tmp_path):
        _write_ledger(
            tmp_path, {"t/f.md": {"disposition": "deferred", "new_template_hash": "H1"}}
        )
        assert self._run(tmp_path, "t/f.md", "H1") == 1

    def test_no_entry_exits_one(self, tmp_path):
        _write_ledger(
            tmp_path,
            {"other.md": {"disposition": "applied", "new_template_hash": "H1"}},
        )
        assert self._run(tmp_path, "t/f.md", "H1") == 1

    def test_absent_ledger_exits_one(self, tmp_path):
        assert self._run(tmp_path, "t/f.md", "H1") == 1  # no crash under a bare root


# --------------------------------------------------------------------------- #
# Layer 2: the installer end-to-end.
# --------------------------------------------------------------------------- #
_REL = "tracking/task-tracker.md"


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert (
        lines[-1].strip() == 'main "$@"'
    ), f"Expected last line 'main \"$@\"', got: {lines[-1]!r}."
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(_HELPERS, tmp_path / "_env_split_helpers.sh")
    return copy


@pytest.fixture
def dirs(tmp_path):
    install_dir = tmp_path / "install_dir"
    project_dir = tmp_path / "project_dir"
    install_dir.mkdir()
    project_dir.mkdir()
    return install_dir, project_dir


def _mk_shipped_template(install_dir: Path, rel_path: str, body: str) -> None:
    dest = install_dir / "templates" / "oversight" / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")


def _stage_helper(install_dir: Path) -> None:
    """Copy the real shipped reconcile scripts to where the installer shells out."""
    dst = (
        install_dir / "_ai-memory" / "pov" / "skills" / "aim-content-drift" / "scripts"
    )
    shutil.copytree(_HELPER_SCRIPTS, dst)


def _deploy(install_sh_copy: Path, install_dir: Path, project_dir: Path):
    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
deploy_oversight_templates
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


def _drive_to_both_changed(install_sh, install_dir, project_dir):
    """Deploy V1, locally edit the copy, ship V2 → next deploy hits the warn branch.

    Returns the current shipped hash ($h_shipped) = sha256 of the V2 template body.
    """
    _mk_shipped_template(install_dir, _REL, "V1\n")
    assert _deploy(install_sh, install_dir, project_dir).returncode == 0
    copy = project_dir / "oversight" / _REL
    copy.write_text("MY LOCAL EDITS\n")
    _mk_shipped_template(install_dir, _REL, "V2\n")
    return _sha("V2\n")


class TestLedgerAwareInstallerWarning:
    def test_applied_at_current_hash_suppresses_warning(self, install_sh_no_main, dirs):
        """The fix: applied @ unmoved hash → no imperative 'review + merge'."""
        install_dir, project_dir = dirs
        _stage_helper(install_dir)
        h_shipped = _drive_to_both_changed(install_sh_no_main, install_dir, project_dir)
        _write_ledger(
            project_dir,
            {_REL: {"disposition": "applied", "new_template_hash": h_shipped}},
        )

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert "review + merge" not in res.stdout, res.stdout
        assert "already reconciled" in res.stdout, res.stdout
        # Never clobbered regardless of disposition.
        assert (project_dir / "oversight" / _REL).read_text() == "MY LOCAL EDITS\n"

    def test_dismissed_at_current_hash_suppresses_warning(
        self, install_sh_no_main, dirs
    ):
        install_dir, project_dir = dirs
        _stage_helper(install_dir)
        h_shipped = _drive_to_both_changed(install_sh_no_main, install_dir, project_dir)
        _write_ledger(
            project_dir,
            {_REL: {"disposition": "dismissed", "new_template_hash": h_shipped}},
        )

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert "review + merge" not in res.stdout, res.stdout

    def test_disposed_but_hash_moved_still_warns(self, install_sh_no_main, dirs):
        """Negative (a): applied but at a STALE hash → genuinely new upstream → warn."""
        install_dir, project_dir = dirs
        _stage_helper(install_dir)
        _drive_to_both_changed(install_sh_no_main, install_dir, project_dir)
        _write_ledger(
            project_dir,
            {_REL: {"disposition": "applied", "new_template_hash": _sha("OLD\n")}},
        )

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert "review + merge" in res.stdout, res.stdout

    def test_no_ledger_entry_still_warns(self, install_sh_no_main, dirs):
        """Negative (b): no disposition recorded → warn as today."""
        install_dir, project_dir = dirs
        _stage_helper(install_dir)
        _drive_to_both_changed(install_sh_no_main, install_dir, project_dir)
        _write_ledger(
            project_dir,
            {"unrelated.md": {"disposition": "applied", "new_template_hash": "x"}},
        )

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert "review + merge" in res.stdout, res.stdout

    def test_deferred_disposition_still_warns(self, install_sh_no_main, dirs):
        """Negative (c): only applied/dismissed/resolved suppress; deferred re-surfaces."""
        install_dir, project_dir = dirs
        _stage_helper(install_dir)
        h_shipped = _drive_to_both_changed(install_sh_no_main, install_dir, project_dir)
        _write_ledger(
            project_dir,
            {_REL: {"disposition": "deferred", "new_template_hash": h_shipped}},
        )

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert "review + merge" in res.stdout, res.stdout

    def test_absent_helper_degrades_to_warn(self, install_sh_no_main, dirs):
        """Fail-safe: helper not present at INSTALL_DIR → non-zero → warn, never abort."""
        install_dir, project_dir = dirs
        # deliberately DO NOT stage the helper
        h_shipped = _drive_to_both_changed(install_sh_no_main, install_dir, project_dir)
        _write_ledger(
            project_dir,
            {_REL: {"disposition": "applied", "new_template_hash": h_shipped}},
        )

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert "review + merge" in res.stdout, res.stdout
