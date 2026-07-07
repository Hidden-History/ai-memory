"""Install tests for the retry-queue drain cron job (TD-710).

Before this fix, scripts/memory/process_retry_queue.py was invoked ONLY once, at
install time (drain_pending_queue). There was no standing scheduler, so the
failed-store queue accumulated append-only between installs (7-week, 203-item
backlog observed in production).

setup_retry_drain_cron() registers a flock-guarded cron entry (marker
"# ai-memory-retry-drain") that runs process_retry_queue.py every 15 minutes,
mirroring the existing setup_jira_cron() pattern. Core safety property: re-running
install must not duplicate the cron entry (idempotent by marker).

A fake `crontab` binary is placed on PATH so these tests never touch the real
crontab of the machine running them.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"

_FAKE_CRONTAB = """#!/usr/bin/env bash
# Fake crontab(1) for tests: reads/writes FAKE_CRONTAB_FILE instead of the
# real system crontab.
set -euo pipefail
: "${FAKE_CRONTAB_FILE:?FAKE_CRONTAB_FILE not set}"
if [[ "${1:-}" == "-l" ]]; then
    if [[ -f "$FAKE_CRONTAB_FILE" ]]; then
        cat "$FAKE_CRONTAB_FILE"
        exit 0
    else
        exit 1
    fi
elif [[ "${1:-}" == "-" ]]; then
    cat > "$FAKE_CRONTAB_FILE"
    exit 0
else
    echo "fake crontab: unsupported args: $*" >&2
    exit 1
fi
"""


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


@pytest.fixture
def fake_crontab_env(tmp_path):
    """Fake `crontab` binary on PATH + the state file it reads/writes.

    Returns (bin_dir, state_file) so tests can prepend bin_dir to PATH and
    inspect state_file's contents after calling setup_retry_drain_cron.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    crontab_bin = bin_dir / "crontab"
    crontab_bin.write_text(_FAKE_CRONTAB, encoding="utf-8")
    crontab_bin.chmod(0o755)
    state_file = tmp_path / "fake_crontab_state"
    return bin_dir, state_file


def _run_setup_retry_drain_cron(
    install_sh_copy: Path,
    install_dir: Path,
    bin_dir: Path,
    state_file: Path,
    platform: str = "linux",
) -> subprocess.CompletedProcess:
    """Source install.sh (no-main copy) and call setup_retry_drain_cron with a fake crontab."""
    bash_cmd = f"""
set -euo pipefail
export PATH="{bin_dir}:$PATH"
export FAKE_CRONTAB_FILE="{state_file}"
export INSTALL_DIR="{install_dir}"
export PLATFORM="{platform}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PLATFORM="{platform}"
setup_retry_drain_cron
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


class TestSetupRetryDrainCron:
    def test_registers_entry_with_marker_and_schedule(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()

        result = _run_setup_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert result.returncode == 0, f"setup_retry_drain_cron failed:\n{result.stderr}"

        crontab_content = state_file.read_text(encoding="utf-8")
        matching = [
            line for line in crontab_content.splitlines() if "ai-memory-retry-drain" in line
        ]
        assert len(matching) == 1, f"expected exactly one entry, got: {matching}"
        entry = matching[0]
        assert entry.startswith("*/15 * * * *"), entry
        assert "process_retry_queue.py" in entry
        assert "--limit 500" in entry  # raised above the 100 default so backlog clears
        assert f"{install_dir}/.locks/retry_drain.lock" in entry
        assert "flock -n" in entry
        assert f">> {install_dir}/logs/retry_drain.log 2>&1" in entry

    def test_locks_dir_created(self, install_sh_no_main, fake_crontab_env, tmp_path):
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()

        _run_setup_retry_drain_cron(install_sh_no_main, install_dir, bin_dir, state_file)
        assert (install_dir / ".locks").is_dir()

    def test_idempotent_no_duplicate_on_second_run(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()

        first = _run_setup_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert first.returncode == 0, first.stderr

        second = _run_setup_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert second.returncode == 0, second.stderr

        crontab_content = state_file.read_text(encoding="utf-8")
        matching = [
            line for line in crontab_content.splitlines() if "ai-memory-retry-drain" in line
        ]
        assert len(matching) == 1, (
            f"re-running install must not duplicate the cron entry, got: {matching}"
        )

    def test_preserves_unrelated_existing_crontab_entries(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()
        state_file.write_text("0 0 * * * /usr/bin/some-other-job\n", encoding="utf-8")

        result = _run_setup_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert result.returncode == 0, result.stderr

        crontab_content = state_file.read_text(encoding="utf-8")
        assert "/usr/bin/some-other-job" in crontab_content
        matching = [
            line for line in crontab_content.splitlines() if "ai-memory-retry-drain" in line
        ]
        assert len(matching) == 1

    def test_legacy_untagged_entry_is_replaced_not_duplicated(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        """A pre-TD-710 crontab entry that calls process_retry_queue.py but lacks the
        "# ai-memory-retry-drain" marker must be replaced by the new tagged entry, not
        left in place alongside it (the filter greps both the marker and the script name)."""
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()
        legacy_entry = "*/30 * * * * /usr/bin/python3 /opt/legacy/process_retry_queue.py --limit 50\n"
        state_file.write_text(legacy_entry, encoding="utf-8")

        result = _run_setup_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert result.returncode == 0, result.stderr

        crontab_content = state_file.read_text(encoding="utf-8")
        assert "/opt/legacy/process_retry_queue.py" not in crontab_content
        matching = [
            line for line in crontab_content.splitlines() if "process_retry_queue.py" in line
        ]
        assert len(matching) == 1, (
            f"legacy untagged entry must be replaced not duplicated, got: {matching}"
        )
        assert "ai-memory-retry-drain" in matching[0]

    def test_macos_platform_omits_flock(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()

        result = _run_setup_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file, platform="macos"
        )
        assert result.returncode == 0, result.stderr

        crontab_content = state_file.read_text(encoding="utf-8")
        matching = [
            line for line in crontab_content.splitlines() if "ai-memory-retry-drain" in line
        ]
        assert len(matching) == 1
        assert "flock" not in matching[0]
        assert "process_retry_queue.py" in matching[0]
