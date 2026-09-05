"""Transport 2: the cause must survive the docker/.env -> settings.json hop.

Host-side hooks read env from ``settings.json``, not ``docker/.env`` — that is
BUG-120's exact class (CHANGELOG.md:3124), so this transport has already broken
once. The record has to reach it, and the ``not-enabled`` state is the *only*
state in which a cause exists: an implementation that deletes the Parzival vars
when the flag is false strips the cause precisely when a consumer needs it.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_UPDATER = _SCRIPTS_DIR / "update_parzival_settings.py"
_LANGFUSE_STOP_HOOK = _REPO / ".claude" / "hooks" / "scripts" / "langfuse_stop_hook.py"


def _reader_one_condition() -> str:
    """Return Reader 1's real condition, lifted verbatim from the hook source.

    The point is coupling: the returned string is the production expression, so a
    renamed key, a changed default or a deleted read turns its caller red instead
    of leaving a hand-typed copy passing on its own. The uniqueness assertion is
    the load-bearing half — if a second read appears, "the reader" is no longer a
    single expression and silently picking the first would resume guessing.
    """
    src = _LANGFUSE_STOP_HOOK.read_text(encoding="utf-8")
    reads = [
        line.strip()
        for line in src.splitlines()
        if "os.environ.get(" in line and "PARZIVAL_ENABLED" in line
    ]
    assert len(reads) == 1, (
        f"expected exactly one PARZIVAL_ENABLED read in {_LANGFUSE_STOP_HOOK.name}, "
        f"found {len(reads)}: {reads}"
    )
    line = reads[0]
    assert line.startswith("if ") and line.endswith(":"), (
        f"the reader is no longer a bare `if <expr>:` and this extraction can no "
        f"longer be trusted: {line!r}"
    )
    return line[len("if ") : -1]


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
        # PARZIVAL_ENABLED is deliberately ABSENT on the disabled path, not "false".
        # settings.json's env section reaches the hook process and pydantic-settings
        # ranks process env ABOVE env_file, so a persisted "false" would outrank
        # docker/.env — the file the panel tells the operator to edit. Absent reads
        # false in both consumers (langfuse_stop_hook's os.environ.get default, and
        # MemoryConfig falling through to docker/.env).
        assert "PARZIVAL_ENABLED" not in env, env
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
        # Absence, not "false": the stale true must not survive, and the replacement
        # must not itself become a process-env override of docker/.env.
        assert "PARZIVAL_ENABLED" not in env, "stale true must not survive"
        assert env.get("PARZIVAL_ENABLED_CAUSE") == "failed"
        assert "PARZIVAL_USER_NAME" not in env, "preference vars still cleared"


class TestSettingsJsonMustNotOutrankDockerEnv:
    """Why PARZIVAL_ENABLED is deleted rather than written on the disabled path.

    This is the mechanism, asserted rather than asserted-about: pydantic-settings
    ranks process env ABOVE ``env_file``. ``settings.json``'s ``env`` section is
    delivered to the hook process, so persisting ``"false"`` there pins the disabled
    state above ``docker/.env`` — and the installer panel's own remediation advice
    ("set PARZIVAL_ENABLED=true in docker/.env") becomes inert.
    """

    def test_process_env_false_outranks_a_true_docker_env(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(_REPO / "src"))
        from memory.config import MemoryConfig

        env_file = tmp_path / ".env"
        env_file.write_text("PARZIVAL_ENABLED=true\n", encoding="utf-8")

        monkeypatch.delenv("PARZIVAL_ENABLED", raising=False)
        assert MemoryConfig(_env_file=str(env_file)).parzival_enabled is True

        # The trap: what a persisted settings.json "false" would do to that install.
        monkeypatch.setenv("PARZIVAL_ENABLED", "false")
        assert MemoryConfig(_env_file=str(env_file)).parzival_enabled is False, (
            "process env must outrank env_file — this is the reason the disabled "
            "path deletes the key instead of writing false"
        )

    def test_absent_key_falls_through_to_docker_env(self, tmp_path, monkeypatch):
        """Absence must be constructed by REMOVAL, which is what the fix performs.

        This test stands behind the claim "absence is safe in both readers", so it
        has to exercise the state the disabled path actually creates: a key that was
        present in ``settings.json``'s ``env`` section and is then deleted. Asserting
        a never-set key re-runs the opening of the sibling above and proves nothing
        about the deletion — it cannot distinguish "the key was removed" from "the
        key was never written".

        ``monkeypatch.setenv``/``delenv`` is the faithful model of that transport:
        ``settings.json``'s ``env`` section reaches these readers as process
        environment, which is precisely why a persisted "false" there outranks
        ``docker/.env``.
        """
        sys.path.insert(0, str(_REPO / "src"))
        from memory.config import MemoryConfig

        env_file = tmp_path / ".env"
        env_file.write_text("PARZIVAL_ENABLED=true\n", encoding="utf-8")

        # PRESENT, and disagreeing with docker/.env — the exact state settings.json
        # held before the disabled path was changed to delete rather than write
        # "false". Establishing it first is what makes the removal below meaningful.
        monkeypatch.setenv("PARZIVAL_ENABLED", "false")
        assert MemoryConfig(_env_file=str(env_file)).parzival_enabled is False

        # ...now the deletion the disabled path performs.
        monkeypatch.delenv("PARZIVAL_ENABLED", raising=False)

        # Reader 1 — langfuse_stop_hook.py, exercised by EXTRACTING ITS ACTUAL
        # CONDITION from the file rather than by re-typing it here. Re-typing
        # `os.environ.get("PARZIVAL_ENABLED", "false") == "false"` asserts that
        # dict.get returns its own default argument: it holds unconditionally once
        # the key is deleted, names no production symbol, and stays green if the hook
        # renames the key or flips its default to "true". That is a second
        # implementation agreeing with itself, which is the same non-gate this
        # commit's sibling work removed from the static record-field guard.
        expr = _reader_one_condition()
        assert eval(expr, {"os": os}) is False, (
            "with the key absent the hook's own condition must be False, so the "
            f"stop hook does not claim agent_id=parzival: {expr!r}"
        )

        # Reader 2 — MemoryConfig falls back to the env_file, so docker/.env wins.
        assert MemoryConfig(_env_file=str(env_file)).parzival_enabled is True, (
            "with the key removed the SDK must fall through to docker/.env — this "
            "is what makes the panel's 'set PARZIVAL_ENABLED=true in docker/.env' "
            "remediation advice actually take effect"
        )


class TestEnabledPathClearsStaleState:
    """The enabled branch had no stale-key removal; the disabled branch did.

    A settings.json holding ``CAUSE=failed`` from a prior run, plus a docker/.env
    that reaches enabled WITHOUT a cause line (an operator who *deletes* rather than
    empties it, per the session guide), left ``PARZIVAL_ENABLED=true`` x
    ``cause=failed`` on transport 2 — the exact cell the single-pass writer makes
    unrepresentable in docker/.env.
    """

    def test_stale_cause_is_removed_when_docker_env_omits_it(self, settings_and_env):
        settings, env_file = settings_and_env
        settings.write_text(
            json.dumps({"env": {"PARZIVAL_ENABLED_CAUSE": "failed"}}, indent=2),
            encoding="utf-8",
        )
        env_file.write_text("PARZIVAL_ENABLED=true\n", encoding="utf-8")
        assert _run_updater(settings, env_file).returncode == 0

        env = _env_section(settings)
        assert env.get("PARZIVAL_ENABLED") == "true"
        assert "PARZIVAL_ENABLED_CAUSE" not in env, (
            "the forbidden (enabled x non-empty cause) cell must not survive on "
            f"transport 2 either: {env}"
        )

    def test_a_preference_absent_from_docker_env_is_kept_not_deleted(
        self, settings_and_env
    ):
        """The stale-state removal must be scoped to the STATE vars.

        Both halves run against one settings.json in one pass because the risk is
        precisely that they are not separable: the removal loop walks
        ``PARZIVAL_VARS`` (state + preference), so an unscoped `elif var in
        env_section` deletes an operator's ``PARZIVAL_USER_NAME`` for the same
        reason it deletes a stale cause — absence from docker/.env. Asserting only
        the survival would pass against a version that never removed anything;
        asserting only the removal is the sibling above. The pair is what pins the
        scoping, and reverting the guard to `elif var in env_section:` turns the
        first assertion red.

        A preference absent from docker/.env is not stale, it is unset there.
        """
        settings, env_file = settings_and_env
        settings.write_text(
            json.dumps(
                {
                    "env": {
                        "PARZIVAL_USER_NAME": "will",
                        "PARZIVAL_ENABLED_CAUSE": "failed",
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        # Enabled, and carrying NEITHER key — the operator who deletes rather than
        # empties, which is what makes both keys "absent from docker/.env".
        env_file.write_text("PARZIVAL_ENABLED=true\n", encoding="utf-8")
        assert _run_updater(settings, env_file).returncode == 0

        env = _env_section(settings)
        assert env.get("PARZIVAL_USER_NAME") == "will", (
            "a preference var absent from docker/.env must survive the enabled "
            f"path — the removal is scoped to the state vars: {env}"
        )
        assert "PARZIVAL_ENABLED_CAUSE" not in env, (
            "...while the stale state var in the same run is still removed, which "
            f"is what makes the scoping a scope and not a disabled removal: {env}"
        )


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
        assert "PARZIVAL_ENABLED" not in env, env
        assert env.get("PARZIVAL_ENABLED_CAUSE") == "opt-out", env
