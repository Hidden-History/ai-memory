"""Install tests for oversight-template content-sync + drift migration (#295 / #296 Part C).

The installer stamps each shipped oversight template with a SHA-256 content hash and
records the deployed hash per project (``.audit/state/oversight-templates.manifest``).
On re-run, ``deploy_oversight_templates`` classifies each project copy:

  * missing            -> deploy the new file
  * == shipped         -> in-sync, silent
  * == recorded hash   -> unmodified since our deploy -> auto-sync to shipped
  * == known prior     -> stale old-shipped copy      -> auto-migrate to shipped
  * anything else      -> locally modified            -> loud WARN, never clobbered

``check_oversight_templates`` (``install.sh --check-templates``) is the CI-gateable
dry-run: it mutates nothing, prints one classified line per drifted template, exits 1
if anything is pending, and stays silent + exits 0 when everything is in-sync.

These tests source install.sh (minus its final ``main "$@"``) and drive the two public
entrypoints directly against mocked INSTALL_DIR / PROJECT_PATH trees.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_HELPERS = _SCRIPTS_DIR / "_env_split_helpers.sh"

# Real historical PLAN_TEMPLATE content hashes (see
# templates/known-oversight-template-versions.txt): the 333-line blob shipped at
# commit 3a7956c, superseded by the 46-line version. The drifted testV2/dev copies
# byte-match the prior hash, which is what makes migration provable rather than a guess.
_PLAN_PRIOR_333L_HASH = (
    "236dee01b5fbdee51232ea109dcb6b415692c7e9370f5800ccf419bc08fcc8a2"
)


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """Copy install.sh minus the final 'main "$@"' line into tmp_path for safe sourcing."""
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(_HELPERS, tmp_path / "_env_split_helpers.sh")
    return copy


def _mk_shipped_template(install_dir: Path, rel_path: str, body: str) -> None:
    """Place a shipped oversight template at INSTALL_DIR/templates/oversight/<rel_path>."""
    dest = install_dir / "templates" / "oversight" / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")


def _mk_registry(install_dir: Path, rows: list[tuple[str, str]]) -> None:
    """Write the prior-shipped-hash registry with (rel_path, sha256) rows."""
    reg = install_dir / "templates" / "known-oversight-template-versions.txt"
    reg.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# test registry\n"]
    lines += [f"{rel}\t{h}\n" for rel, h in rows]
    reg.write_text("".join(lines), encoding="utf-8")


def _run_entrypoint(
    install_sh_copy: Path, install_dir: Path, project_dir: Path, func: str
) -> subprocess.CompletedProcess:
    """Source install.sh (no-main copy) and invoke a template entrypoint with mocked dirs."""
    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
{func}
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


def _deploy(install_sh_copy, install_dir, project_dir):
    return _run_entrypoint(
        install_sh_copy, install_dir, project_dir, "deploy_oversight_templates"
    )


def _check(install_sh_copy, install_dir, project_dir):
    return _run_entrypoint(
        install_sh_copy, install_dir, project_dir, "check_oversight_templates"
    )


@pytest.fixture
def dirs(tmp_path):
    install_dir = tmp_path / "install_dir"
    project_dir = tmp_path / "project_dir"
    install_dir.mkdir()
    project_dir.mkdir()
    return install_dir, project_dir


class TestNewFileDeploy:
    def test_new_template_deploys_into_existing_project(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        _mk_shipped_template(install_dir, "plans/PLAN_TEMPLATE.md", "SHIPPED v2\n")

        # Pre-existing project oversight dir with unrelated content -> the new template
        # file must still be deployed (spec pt 4: new files into existing projects).
        (project_dir / "oversight").mkdir()
        (project_dir / "oversight" / "existing.md").write_text("keep me\n")

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr

        deployed = project_dir / "oversight" / "plans" / "PLAN_TEMPLATE.md"
        assert deployed.read_text() == "SHIPPED v2\n"
        assert (project_dir / "oversight" / "existing.md").read_text() == "keep me\n"
        # Manifest records the deployed hash.
        manifest = project_dir / ".audit" / "state" / "oversight-templates.manifest"
        assert manifest.exists()
        assert "plans/PLAN_TEMPLATE.md" in manifest.read_text()


class TestUnmodifiedAutoSync:
    def test_unmodified_copy_auto_syncs_to_new_shipped(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        # First install: ship + deploy v1, recording its hash in the manifest.
        _mk_shipped_template(install_dir, "tracking/task-tracker.md", "V1\n")
        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0
        copy = project_dir / "oversight" / "tracking" / "task-tracker.md"
        assert copy.read_text() == "V1\n"

        # Upstream changes; the project copy is untouched -> should auto-sync to V2.
        _mk_shipped_template(install_dir, "tracking/task-tracker.md", "V2\n")
        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert copy.read_text() == "V2\n"


class TestLocallyModifiedWarn:
    def test_locally_modified_copy_is_warned_not_clobbered(
        self, install_sh_no_main, dirs
    ):
        install_dir, project_dir = dirs
        _mk_shipped_template(install_dir, "tracking/task-tracker.md", "V1\n")
        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0

        # User edits the deployed copy, then upstream changes.
        copy = project_dir / "oversight" / "tracking" / "task-tracker.md"
        copy.write_text("MY LOCAL EDITS\n")
        _mk_shipped_template(install_dir, "tracking/task-tracker.md", "V2\n")

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        # Never clobbered; a loud warning is emitted.
        assert copy.read_text() == "MY LOCAL EDITS\n"
        assert "review + merge" in res.stdout
        assert "tracking/task-tracker.md" in res.stdout


class TestMigration:
    def test_stale_old_shipped_copy_migrates_via_known_hash(
        self, install_sh_no_main, dirs
    ):
        """F-INSTALLER-5: no recorded baseline, but the copy byte-matches a known
        prior-shipped version -> provably stale -> auto-migrate (the real 333L->46L case).
        """
        install_dir, project_dir = dirs
        prior_body = "PRIOR SHIPPED BODY\n"

        # Compute the prior body's hash the same way the installer does.
        import hashlib

        prior_hash = hashlib.sha256(prior_body.encode()).hexdigest()

        _mk_shipped_template(install_dir, "plans/PLAN_TEMPLATE.md", "CURRENT SHIPPED\n")
        _mk_registry(install_dir, [("plans/PLAN_TEMPLATE.md", prior_hash)])

        # Project carries the stale old-shipped copy, with NO manifest (first run).
        copy = project_dir / "oversight" / "plans" / "PLAN_TEMPLATE.md"
        copy.parent.mkdir(parents=True)
        copy.write_text(prior_body)

        res = _deploy(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert copy.read_text() == "CURRENT SHIPPED\n"
        assert "migrated" in res.stdout

    def test_real_plan_template_prior_hash_is_registered(self):
        """Guard: the shipped registry actually carries the historical 333L hash, so the
        real drifted testV2/dev copies can migrate (not just a synthetic fixture)."""
        registry = (
            _SCRIPTS_DIR.parent / "templates" / "known-oversight-template-versions.txt"
        )
        text = registry.read_text(encoding="utf-8")
        assert f"plans/PLAN_TEMPLATE.md\t{_PLAN_PRIOR_333L_HASH}" in text


class TestCheckMode:
    def test_check_is_silent_and_zero_when_in_sync(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        _mk_shipped_template(install_dir, "tracking/task-tracker.md", "V1\n")
        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0

        res = _check(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 0, res.stderr
        assert res.stdout.strip() == ""  # silent-when-clean (Design Standard)

    def test_check_reports_and_exits_one_on_drift(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        _mk_shipped_template(install_dir, "tracking/task-tracker.md", "V1\n")
        assert _deploy(install_sh_no_main, install_dir, project_dir).returncode == 0

        # Introduce a new shipped file (pending deploy) -> check must flag + exit 1.
        _mk_shipped_template(install_dir, "plans/PLAN_TEMPLATE.md", "NEW\n")
        res = _check(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 1
        assert "[new]" in res.stdout
        assert "plans/PLAN_TEMPLATE.md" in res.stdout

    def test_check_does_not_mutate_project(self, install_sh_no_main, dirs):
        install_dir, project_dir = dirs
        _mk_shipped_template(install_dir, "tracking/task-tracker.md", "V1\n")
        _mk_shipped_template(install_dir, "plans/PLAN_TEMPLATE.md", "NEW\n")

        res = _check(install_sh_no_main, install_dir, project_dir)
        assert res.returncode == 1
        # Dry-run: nothing deployed, no manifest written.
        assert not (project_dir / "oversight" / "plans" / "PLAN_TEMPLATE.md").exists()
        assert not (
            project_dir / ".audit" / "state" / "oversight-templates.manifest"
        ).exists()
