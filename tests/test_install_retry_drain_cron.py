"""Install tests for retiring the retry-queue drain host cron (TD-710 → daemon migration).

TD-710 originally had install.sh register a flock-guarded host cron entry (marker
"# ai-memory-retry-drain") that ran process_retry_queue.py every 15 minutes. The
standing scheduler has since moved to an in-stack daemon container
(docker-compose.yml, owned separately), so install.sh must no longer install that
cron — it must instead REMOVE any prior installation's tagged entry (or a legacy
untagged process_retry_queue.py entry) so an upgrading operator doesn't end up with
BOTH the old host cron and the new daemon draining the queue concurrently.

remove_legacy_retry_drain_cron() is the migration function: idempotent, no-op on a
fresh install or a host with no crontab, and it must never touch unrelated crontab
entries — only lines matching the marker or the legacy script path.

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
    inspect state_file's contents after calling remove_legacy_retry_drain_cron.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    crontab_bin = bin_dir / "crontab"
    crontab_bin.write_text(_FAKE_CRONTAB, encoding="utf-8")
    crontab_bin.chmod(0o755)
    state_file = tmp_path / "fake_crontab_state"
    return bin_dir, state_file


def _run_remove_legacy_retry_drain_cron(
    install_sh_copy: Path,
    install_dir: Path,
    bin_dir: Path,
    state_file: Path,
) -> subprocess.CompletedProcess:
    """Source install.sh (no-main copy) and call remove_legacy_retry_drain_cron
    with a fake crontab."""
    bash_cmd = f"""
set -euo pipefail
export PATH="{bin_dir}:$PATH"
export FAKE_CRONTAB_FILE="{state_file}"
export INSTALL_DIR="{install_dir}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
remove_legacy_retry_drain_cron
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


class TestRemoveLegacyRetryDrainCron:
    def test_fresh_install_no_crontab_write(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        """No prior crontab at all (fake crontab -l exits 1, state_file absent) —
        the function must be a pure no-op: no crontab write, state_file never
        created."""
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()

        result = _run_remove_legacy_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert (
            result.returncode == 0
        ), f"remove_legacy_retry_drain_cron failed:\n{result.stderr}"
        assert (
            not state_file.exists()
        ), "Fresh install with no crontab must not create one"

    def test_removes_marked_legacy_entry(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        """A pre-existing tagged entry (marker "# ai-memory-retry-drain") is removed."""
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()
        legacy_entry = (
            "*/15 * * * * flock -n /tmp/.locks/retry_drain.lock "
            "/tmp/.venv/bin/python /tmp/scripts/memory/process_retry_queue.py "
            "--limit 500 >> /tmp/logs/retry_drain.log 2>&1 # ai-memory-retry-drain\n"
        )
        state_file.write_text(legacy_entry, encoding="utf-8")

        result = _run_remove_legacy_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert result.returncode == 0, result.stderr

        crontab_content = state_file.read_text(encoding="utf-8")
        assert "ai-memory-retry-drain" not in crontab_content
        assert "process_retry_queue.py" not in crontab_content

    def test_removes_legacy_untagged_entry(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        """A pre-TD-710 untagged entry (process_retry_queue.py, no marker) is also
        removed — the migration must not leave a pre-marker cron installation behind."""
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()
        legacy_entry = "*/30 * * * * /usr/bin/python3 /opt/legacy/process_retry_queue.py --limit 50\n"
        state_file.write_text(legacy_entry, encoding="utf-8")

        result = _run_remove_legacy_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert result.returncode == 0, result.stderr

        crontab_content = state_file.read_text(encoding="utf-8")
        assert "/opt/legacy/process_retry_queue.py" not in crontab_content

    def test_preserves_unrelated_existing_crontab_entries(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        """Unrelated crontab entries are never touched — only the marker/legacy-script
        lines are matched for removal."""
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()
        state_file.write_text(
            "0 0 * * * /usr/bin/some-other-job\n"
            "*/15 * * * * /usr/bin/python3 /opt/process_retry_queue.py # ai-memory-retry-drain\n",
            encoding="utf-8",
        )

        result = _run_remove_legacy_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert result.returncode == 0, result.stderr

        crontab_content = state_file.read_text(encoding="utf-8")
        assert "/usr/bin/some-other-job" in crontab_content
        assert "ai-memory-retry-drain" not in crontab_content
        assert "process_retry_queue.py" not in crontab_content

    def test_idempotent_second_run_is_noop(
        self, install_sh_no_main, fake_crontab_env, tmp_path
    ):
        """Re-running after the legacy entry is already removed makes no further
        crontab write and leaves the (now-clean) crontab unchanged."""
        bin_dir, state_file = fake_crontab_env
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()
        state_file.write_text(
            "*/15 * * * * /usr/bin/python3 /opt/process_retry_queue.py # ai-memory-retry-drain\n"
            "0 0 * * * /usr/bin/some-other-job\n",
            encoding="utf-8",
        )

        first = _run_remove_legacy_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert first.returncode == 0, first.stderr
        after_first = state_file.read_text(encoding="utf-8")
        assert "ai-memory-retry-drain" not in after_first
        assert "/usr/bin/some-other-job" in after_first

        second = _run_remove_legacy_retry_drain_cron(
            install_sh_no_main, install_dir, bin_dir, state_file
        )
        assert second.returncode == 0, second.stderr
        after_second = state_file.read_text(encoding="utf-8")
        assert after_second == after_first, (
            "Second run must be a no-op once the legacy entry is already gone "
            f"— before: {after_first!r} after: {after_second!r}"
        )

    def test_noop_when_crontab_binary_unavailable(self, install_sh_no_main, tmp_path):
        """On a host with no `crontab` binary at all (e.g. a minimal container),
        the function must exit 0 without attempting to invoke crontab."""
        install_dir = tmp_path / "install_dir"
        install_dir.mkdir()
        empty_path_dir = tmp_path / "empty_path_dir"
        empty_path_dir.mkdir()
        bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
source "{install_sh_no_main}"
INSTALL_DIR="{install_dir}"
export PATH="{empty_path_dir}"
remove_legacy_retry_drain_cron
echo "REACHED_END"
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "REACHED_END" in result.stdout

    def test_no_cron_installing_function_defined(self):
        """Structural regression guard: install.sh must not define a
        setup_retry_drain_cron function (the pre-migration cron-INSTALLING
        symbol) — only the removal function remove_legacy_retry_drain_cron."""
        text = _INSTALL_SH.read_text()
        assert "setup_retry_drain_cron()" not in text, (
            "install.sh must not define setup_retry_drain_cron() — the standing "
            "retry-drain scheduler moved to an in-stack daemon; install.sh should "
            "only remove a legacy host cron, not install one."
        )
        assert (
            "remove_legacy_retry_drain_cron() {" in text
        ), "remove_legacy_retry_drain_cron() function definition not found"

    def test_removal_function_called_from_main(self):
        """Structural regression guard: remove_legacy_retry_drain_cron must
        actually be called from main() — a defined-but-unreachable function
        would silently never clean up an operator's legacy cron."""
        text = _INSTALL_SH.read_text()
        call_sites = [
            line
            for line in text.splitlines()
            if line.strip() == "remove_legacy_retry_drain_cron"
        ]
        assert call_sites, (
            "remove_legacy_retry_drain_cron is defined but never called — "
            "it must be invoked from main()'s full-install branch."
        )
