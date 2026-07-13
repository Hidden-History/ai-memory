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

import re
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

    def test_50000_value_is_preserved(self, install_sh_no_main, tmp_path):
        """AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=50000 must NOT be matched by the
        =5000 substring — a whitespace-tolerant match must still be exact on
        the numeric value, not merely a prefix match."""
        install_dir = tmp_path / "install_dir"
        env_file = _make_env(install_dir, "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=50000\n")

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr

        assert (
            env_file.read_text(encoding="utf-8")
            == "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=50000\n"
        )
        assert not _env_backups(
            install_dir
        ), "no-op path must not create a backup (nothing is mutated)"

    def test_trailing_whitespace_5000_is_reconciled(self, install_sh_no_main, tmp_path):
        """A stale 5000 with trailing whitespace before the newline (e.g. from a
        hand-edited .env) still shadows the code default and must be
        reconciled to a clean 15000 line."""
        install_dir = tmp_path / "install_dir"
        env_file = _make_env(install_dir, "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000   \n")

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr

        content = env_file.read_text(encoding="utf-8")
        assert "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=15000\n" in content
        assert "5000   " not in content
        assert _env_backups(install_dir)

    def test_space_after_equals_5000_is_reconciled(self, install_sh_no_main, tmp_path):
        """A stale 5000 with a space after `=` still shadows the code default
        and must be reconciled to a clean 15000 line."""
        install_dir = tmp_path / "install_dir"
        env_file = _make_env(install_dir, "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS= 5000\n")

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr

        content = env_file.read_text(encoding="utf-8")
        assert "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=15000\n" in content
        assert "= 5000" not in content
        assert _env_backups(install_dir)

    def test_crlf_5000_is_reconciled(self, install_sh_no_main, tmp_path):
        """A stale 5000 saved with CRLF line endings (real on WSL2 when a .env
        is edited from Windows) still shadows the code default and must be
        reconciled to a clean 15000 line with no stray CR left behind."""
        install_dir = tmp_path / "install_dir"
        env_file = _make_env(install_dir, "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=5000\r\n")

        result = _run_reconcile(install_sh_no_main, install_dir)
        assert result.returncode == 0, result.stderr

        content = env_file.read_text(encoding="utf-8")
        assert "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=15000" in content
        assert "5000" not in content.replace("15000", "")
        assert "\r" not in content, "rewritten line must not retain a stray CR"
        assert _env_backups(install_dir)

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
        be called from WITHIN main()'s INSTALL_MODE == "full" if-block — a
        defined-but-unreachable function, or one whose call was refactored
        into the add-project branch (or anywhere outside the full-install
        block), would silently leave every existing install's stale cap in
        place. This tracks if/elif/fi nesting (tolerating trailing `#`
        comments on `if ...; then` / `fi` lines) so a call merely appearing
        somewhere in the file isn't mistaken for a call actually reachable
        from the full-install branch."""
        text = _INSTALL_SH.read_text()
        lines = text.splitlines()
        assert (
            "reconcile_sot_discovery_cap() {" in text
        ), "reconcile_sot_discovery_cap() function definition not found"

        call_indices = [
            i
            for i, line in enumerate(lines)
            if line.strip() == "reconcile_sot_discovery_cap"
        ]
        assert call_indices, (
            "reconcile_sot_discovery_cap is defined but never called — "
            "it must be invoked from main()'s full-install branch."
        )

        if_re = re.compile(r"^\s*if\s+(.*?)\s*;\s*then\s*(#.*)?$")
        fi_re = re.compile(r"^\s*fi\s*(#.*)?$")

        stack = []
        call_enclosing_conditions = {}
        for i, line in enumerate(lines):
            m = if_re.match(line)
            if m:
                stack.append(m.group(1))
            elif fi_re.match(line) and stack:
                stack.pop()
            if i in call_indices:
                call_enclosing_conditions[i] = list(stack)

        full_mode_check = '"$INSTALL_MODE" == "full"'
        add_project_check = '"$INSTALL_MODE" == "add-project"'
        for i in call_indices:
            enclosing = call_enclosing_conditions[i]
            assert any(full_mode_check in cond for cond in enclosing), (
                f"reconcile_sot_discovery_cap call at install.sh:{i + 1} does not "
                f'fall inside an INSTALL_MODE == "full" if-block (enclosing '
                f"conditions: {enclosing!r}) — a refactor may have moved it "
                "outside the full-install branch, which would silently leave "
                "every existing install's stale "
                "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS cap in place."
            )
            assert not any(add_project_check in cond for cond in enclosing), (
                f"reconcile_sot_discovery_cap call at install.sh:{i + 1} falls "
                'inside an INSTALL_MODE == "add-project" if-block — TD-804\'s '
                "reconciliation must only run in the full-install branch."
            )
