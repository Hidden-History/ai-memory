"""Transport 2: the cause must survive the docker/.env -> settings.json hop.

Host-side hooks read env from ``settings.json``, not ``docker/.env`` — that is
BUG-120's exact class (CHANGELOG.md:3124), so this transport has already broken
once. The record has to reach it, and the ``not-enabled`` state is the *only*
state in which a cause exists: an implementation that deletes the Parzival vars
when the flag is false strips the cause precisely when a consumer needs it.
"""

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
_UPDATER = _SCRIPTS_DIR / "update_parzival_settings.py"


def _load_updater():
    spec = importlib.util.spec_from_file_location("upd_transport", _UPDATER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_updater(settings_path: Path, env_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_UPDATER), str(settings_path), str(env_path)],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def settings_and_env(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"env": {}}, indent=2), encoding="utf-8")
    env_file = tmp_path / ".env"
    return settings, env_file


def _env_section(settings_path: Path) -> dict:
    return json.loads(settings_path.read_text(encoding="utf-8")).get("env", {})


class TestDisabledStateCarriesTheCause:
    def test_failed_cause_reaches_settings_json(self, settings_and_env):
        settings, env_file = settings_and_env
        env_file.write_text(
            "PARZIVAL_ENABLED=false\n"
            "PARZIVAL_ENABLED_CAUSE=failed\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n",
            encoding="utf-8",
        )
        res = _run_updater(settings, env_file)
        assert res.returncode == 0, res.stdout + res.stderr

        env = _env_section(settings)
        assert env.get("PARZIVAL_ENABLED") == "false"
        assert env.get("PARZIVAL_ENABLED_CAUSE") == "failed", env
        assert env.get("PARZIVAL_ENABLED_CONDITION") == "complete", env

    def test_opt_out_cause_reaches_settings_json(self, settings_and_env):
        settings, env_file = settings_and_env
        env_file.write_text(
            "PARZIVAL_ENABLED=false\nPARZIVAL_ENABLED_CAUSE=opt-out\n", encoding="utf-8"
        )
        assert _run_updater(settings, env_file).returncode == 0
        assert _env_section(settings).get("PARZIVAL_ENABLED_CAUSE") == "opt-out"

    def test_stale_enabled_true_is_overwritten_not_left_behind(self, settings_and_env):
        """BUG-120's class: enabled->failed must not leave a stale true in settings."""
        settings, env_file = settings_and_env
        settings.write_text(
            json.dumps(
                {"env": {"PARZIVAL_ENABLED": "true", "PARZIVAL_USER_NAME": "dev"}},
                indent=2,
            ),
            encoding="utf-8",
        )
        env_file.write_text(
            "PARZIVAL_ENABLED=false\nPARZIVAL_ENABLED_CAUSE=failed\n", encoding="utf-8"
        )
        assert _run_updater(settings, env_file).returncode == 0

        env = _env_section(settings)
        assert env.get("PARZIVAL_ENABLED") == "false", "stale true must not survive"
        assert env.get("PARZIVAL_ENABLED_CAUSE") == "failed"
        assert "PARZIVAL_USER_NAME" not in env, "preference vars still cleared"


class TestEnabledStateStillSyncs:
    def test_enabled_run_syncs_all_vars(self, settings_and_env):
        settings, env_file = settings_and_env
        env_file.write_text(
            "PARZIVAL_ENABLED=true\n"
            "PARZIVAL_ENABLED_CAUSE=\n"
            "PARZIVAL_ENABLED_CONDITION=complete\n"
            "PARZIVAL_USER_NAME=dev\n",
            encoding="utf-8",
        )
        assert _run_updater(settings, env_file).returncode == 0

        env = _env_section(settings)
        assert env.get("PARZIVAL_ENABLED") == "true"
        assert env.get("PARZIVAL_USER_NAME") == "dev"


class TestInstallerInvokesTheSyncOnFalsePaths:
    """The script was only ever called from inside the enabled branch."""

    @pytest.fixture
    def install_sh_no_main(self, tmp_path) -> Path:
        content = _INSTALL_SH.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        assert lines[-1].strip() == 'main "$@"', lines[-1]
        copy = tmp_path / "install.sh"
        copy.write_text("".join(lines[:-1]), encoding="utf-8")
        copy.chmod(0o755)
        shutil.copy(
            _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
        )
        return copy

    def test_non_interactive_skip_syncs_settings_json(
        self, install_sh_no_main, tmp_path
    ):
        """An opt-out run must still push its cause into settings.json."""
        install_dir = tmp_path / "install_dir"
        project_dir = tmp_path / "project_dir"
        (install_dir / "docker").mkdir(parents=True)
        (install_dir / "_ai-memory").mkdir(parents=True)
        (install_dir / "scripts").mkdir(parents=True)
        shutil.copy(_UPDATER, install_dir / "scripts" / "update_parzival_settings.py")
        settings = project_dir / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"env": {}}, indent=2), encoding="utf-8")

        bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
export NON_INTERACTIVE="true"
source "{install_sh_no_main}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
NON_INTERACTIVE="true"
deploy_ai_memory_skills() {{ :; }}
deploy_ai_memory_agents() {{ :; }}
setup_parzival
"""
        res = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True, input=""
        )
        assert res.returncode == 0, res.stdout + res.stderr

        env = json.loads(settings.read_text(encoding="utf-8")).get("env", {})
        assert env.get("PARZIVAL_ENABLED") == "false", env
        assert env.get("PARZIVAL_ENABLED_CAUSE") == "opt-out", env
