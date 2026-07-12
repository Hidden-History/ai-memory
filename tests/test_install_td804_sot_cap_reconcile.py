"""Install tests for TD-804: reconcile the stale AI_MEMORY_SOT_DISCOVERY_MAX_DIRS
default on existing installs.

#305 raised the code default for AI_MEMORY_SOT_DISCOVERY_MAX_DIRS from 5000 to
15000 (aim_sot_detect_propose.py) to fix a discovery-coverage regression, and
docker/.env.example was bumped to a commented `# ...=15000` so new installs pick
up the code default. But any docker/.env deployed BEFORE #305 still carries the
retired default ACTIVE (=5000), and run-with-env.sh forwards the whole
AI_MEMORY_SOT_* namespace to the engine, so the stale 5000 shadows the new code
default — #305's fix never takes effect on an existing install.

reconcile_sot_discovery_cap() is the migration function: it rewrites ONLY the
exact retired-default active line (^AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000$) to
15000, in place, with a timestamped backup of docker/.env taken first. A
deliberate operator override (any other active value), a commented-out line, or
an absent key are all left untouched.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"


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
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


def _run_reconcile(
    install_sh_copy: Path, install_dir: Path
) -> subprocess.CompletedProcess:
    """Source install.sh (no-main copy) and call reconcile_sot_discovery_cap."""
    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
reconcile_sot_discovery_cap
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


def _make_env(install_dir: Path, body: str) -> Path:
    docker_dir = install_dir / "docker"
    docker_dir.mkdir(parents=True, exist_ok=True)
    env_file = docker_dir / ".env"
    env_file.write_text(body, encoding="utf-8")
    return env_file


def _env_backups(install_dir: Path):
    return list((install_dir / "docker").glob(".env.bak.*"))


class TestReconcileSotDiscoveryCap:
    def test_stale_active_5000_is_reconciled_to_15000(
        self, install_sh_no_main, tmp_path
    ):
        """Active AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000 (the pre-#305 default) is
        rewritten in place to 15000, and a timestamped backup is taken first."""
        install_dir = tmp_path / "install_dir"
        env_file = _make_env(
            install_dir,
            "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000\n" "OTHER_KEY=unrelated\n",
        )

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr

        content = env_file.read_text(encoding="utf-8")
        assert "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=15000" in content
        assert "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000" not in content
        assert "OTHER_KEY=unrelated" in content, "unrelated keys must be preserved"

        backups = _env_backups(install_dir)
        assert (
            backups
        ), "a timestamped backup of docker/.env must be created before mutation"
        backup_content = backups[0].read_text(encoding="utf-8")
        assert (
            "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000" in backup_content
        ), "backup must capture the pre-mutation state"

    def test_custom_operator_value_is_preserved(self, install_sh_no_main, tmp_path):
        """A deliberate operator override (any value other than the retired 5000
        default) is left untouched — this is not treated as the stale default."""
        install_dir = tmp_path / "install_dir"
        env_file = _make_env(install_dir, "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=8000\n")

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr

        assert (
            env_file.read_text(encoding="utf-8")
            == "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=8000\n"
        )
        assert not _env_backups(
            install_dir
        ), "no-op path must not create a backup (nothing is mutated)"

    def test_absent_key_is_noop(self, install_sh_no_main, tmp_path):
        """Key entirely absent (new install seeded from the commented example) —
        no-op, file unchanged, no backup."""
        install_dir = tmp_path / "install_dir"
        original = "QDRANT_API_KEY=x\nOTHER_KEY=unrelated\n"
        env_file = _make_env(install_dir, original)

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr

        assert env_file.read_text(encoding="utf-8") == original
        assert not _env_backups(install_dir)

    def test_commented_line_is_untouched(self, install_sh_no_main, tmp_path):
        """A commented-out `# AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000` (the shipped
        .env.example form) is not an active value — must not be uncommented or
        rewritten."""
        install_dir = tmp_path / "install_dir"
        original = "# AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000\n"
        env_file = _make_env(install_dir, original)

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr

        assert env_file.read_text(encoding="utf-8") == original
        assert not _env_backups(install_dir)

    def test_fresh_install_no_env_file_is_noop(self, install_sh_no_main, tmp_path):
        """No docker/.env at all — pure no-op, nothing created."""
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr
        assert not (install_dir / "docker").exists()

    def test_idempotent_second_run_is_noop(self, install_sh_no_main, tmp_path):
        """Re-running after reconciliation makes no further change and no
        additional backup."""
        install_dir = tmp_path / "install_dir"
        env_file = _make_env(install_dir, "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000\n")

        first = _run_reconcile(install_sh_no_main, install_dir)
        assert first.returncode == 0, first.stderr
        after_first = env_file.read_text(encoding="utf-8")
        assert "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=15000" in after_first
        backups_after_first = _env_backups(install_dir)
        assert len(backups_after_first) == 1

        second = _run_reconcile(install_sh_no_main, install_dir)
        assert second.returncode == 0, second.stderr
        after_second = env_file.read_text(encoding="utf-8")
        assert after_second == after_first
        assert (
            len(_env_backups(install_dir)) == 1
        ), "second run must be a no-op — no additional backup taken"

    def test_function_called_from_main(self):
        """Structural regression guard: reconcile_sot_discovery_cap must actually
        be called from main()'s full-install branch — a defined-but-unreachable
        function would silently leave every existing install's stale cap in
        place."""
        text = _INSTALL_SH.read_text()
        assert (
            "reconcile_sot_discovery_cap() {" in text
        ), "reconcile_sot_discovery_cap() function definition not found"
        call_sites = [
            line
            for line in text.splitlines()
            if line.strip() == "reconcile_sot_discovery_cap"
        ]
        assert call_sites, (
            "reconcile_sot_discovery_cap is defined but never called — "
            "it must be invoked from main()'s full-install branch."
        )
