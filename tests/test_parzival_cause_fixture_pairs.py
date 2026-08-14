"""TR-7 fixture pairs for the five converted sites that had none.

AD-32 / AC-3: every consumer branches on the **cause**, never on the bare value.
A conversion is only demonstrated by a *pair* — the same site driven once with
``cause=opt-out`` and once with ``cause=failed`` — showing it behaves differently.
A single-cause test cannot distinguish "branches on cause" from "prints a constant".

Pairs already existed for ``parzival_save_{handoff,decision,insight}`` in
``tests/test_parzival_consumers_branch_on_cause.py``. They did not exist for the
other five converted sites, verified by the absence of any reference to
``show_success_message`` or ``read_parzival_cause`` across the story's five new test
modules. Two of those five are the surfaces an operator actually looks at:
``show_success_message`` is the last thing the installer prints, and ``aim_status``
is where ``docs/PARZIVAL-SESSION-GUIDE.md`` now sends operators to check the cause.

This module also closes the "two no-else shell sites" obligation. Those two were
exempt from TR-7 only *while branch-less*; the implementation gave both an ``else``,
which retires the exemption and replaces it with this requirement.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS / "install.sh"
_UPGRADE_SH = _SCRIPTS / "upgrade.sh"

sys.path.insert(0, str(_REPO / "src"))

from memory.config import MemoryConfig  # noqa: E402

#: The pair. Every test below runs its site once per cause and asserts the two
#: outputs differ AND that each names its own cause's remedy.
CAUSES = ("opt-out", "failed")


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    lines = _INSTALL_SH.read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', lines[-1]
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(_SCRIPTS / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh")
    return copy


def _env_dir(tmp_path: Path, cause: str) -> Path:
    """An INSTALL_DIR whose docker/.env carries a disabled record with `cause`."""
    install_dir = tmp_path / f"install_{cause}"
    (install_dir / "docker").mkdir(parents=True)
    (install_dir / "docker" / ".env").write_text(
        "PARZIVAL_ENABLED=false\n"
        f"PARZIVAL_ENABLED_CAUSE={cause}\n"
        "PARZIVAL_ENABLED_CONDITION=complete\n",
        encoding="utf-8",
    )
    return install_dir


def _disabled_config(cause: str) -> MemoryConfig:
    """A REAL MemoryConfig, not a mock.

    A6/TR-8: a MagicMock makes cause branches take the wrong path and still pass,
    because `mock.parzival_cause == "failed"` is False while `if mock.parzival_cause:`
    is True and neither raises. Constructing the real object removes the question.
    """
    return MemoryConfig(
        parzival_enabled=False,
        parzival_enabled_cause=cause,
        parzival_enabled_condition="complete",
    )


class TestInstallSummaryPanelPair:
    """`show_success_message` — the last thing the installer prints."""

    def _panel(self, install_sh_copy: Path, install_dir: Path) -> str:
        res = subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'source "{install_sh_copy}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                'PROJECT_PATH="/tmp"\n'
                "show_success_message\n",
            ],
            capture_output=True,
            text=True,
        )
        return res.stdout + res.stderr

    def test_the_two_causes_render_differently(self, install_sh_no_main, tmp_path):
        outputs = {
            cause: self._panel(install_sh_no_main, _env_dir(tmp_path, cause))
            for cause in CAUSES
        }
        assert outputs["opt-out"] != outputs["failed"], (
            "the summary panel shows the same thing whether the operator declined "
            "Parzival or the installer could not deploy it — AC-3 unmet"
        )

    def test_failed_does_not_advise_setting_the_flag(
        self, install_sh_no_main, tmp_path
    ):
        out = self._panel(install_sh_no_main, _env_dir(tmp_path, "failed"))
        assert "deployment failed" in out, out
        assert "PARZIVAL_ENABLED=true" not in out, (
            "the package is absent; telling the operator to set the flag is advice "
            f"that cannot work:\n{out}"
        )

    def test_opt_out_does_advise_setting_the_flag(self, install_sh_no_main, tmp_path):
        out = self._panel(install_sh_no_main, _env_dir(tmp_path, "opt-out"))
        assert "declined at install" in out, out
        assert "PARZIVAL_ENABLED=true" in out, out

    def test_unrecorded_cause_claims_neither(self, install_sh_no_main, tmp_path):
        install_dir = tmp_path / "install_none"
        (install_dir / "docker").mkdir(parents=True)
        (install_dir / "docker" / ".env").write_text(
            "PARZIVAL_ENABLED=false\n", encoding="utf-8"
        )
        out = self._panel(install_sh_no_main, install_dir)
        assert "cause not recorded" in out, out
        assert "declined" not in out, f"an absent cause must not claim a choice:\n{out}"
        assert "deployment failed" not in out, out


class TestUpgradeShHandoffGatePair:
    """`upgrade.sh` Step 3.6 — the gate on historical-handoff ingestion."""

    def _branch(self, install_dir: Path) -> str:
        """Run the real else-branch from upgrade.sh against a prepared .env.

        The block is extracted from the shipped file rather than re-typed, so an
        edit to upgrade.sh changes what this executes.
        """
        text = _UPGRADE_SH.read_text(encoding="utf-8")
        start = text.index('    PARZIVAL_CAUSE=$(grep "^PARZIVAL_ENABLED_CAUSE="')
        end = text.index("    esac", start) + len("    esac")
        block = text[start:end]
        script = (
            "set -uo pipefail\n"
            f'INSTALL_DIR="{install_dir}"\n'
            'YELLOW=""; GREEN=""; NC=""\n'
            f"{block}\n"
        )
        res = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        return res.stdout + res.stderr

    def test_the_two_causes_render_differently(self, tmp_path):
        outs = {c: self._branch(_env_dir(tmp_path, c)) for c in CAUSES}
        assert outs["opt-out"] != outs["failed"], outs

    def test_failed_points_at_the_installer_not_the_flag(self, tmp_path):
        out = self._branch(_env_dir(tmp_path, "failed"))
        assert "could not be installed" in out, out
        assert "PARZIVAL_ENABLED=true" not in out, out

    def test_opt_out_reports_a_choice(self, tmp_path):
        out = self._branch(_env_dir(tmp_path, "opt-out"))
        assert "declined at install" in out, out


class TestAimStatusPair:
    """`aim_status.py` — the surface the session guide sends operators to."""

    @staticmethod
    def _section_flags():
        """aim_status.py lives under scripts/memory/, not src/memory/ — load by path."""
        import importlib.util

        script = _SCRIPTS / "memory" / "aim_status.py"
        spec = importlib.util.spec_from_file_location("pairs_aim_status", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.section_flags

    def _flags(self, cause: str) -> str:
        return "\n".join(self._section_flags()(_disabled_config(cause)))

    def test_the_two_causes_render_differently(self):
        assert self._flags("opt-out") != self._flags("failed")

    @pytest.mark.parametrize("cause", CAUSES)
    def test_each_cause_is_named_in_the_status_line(self, cause):
        assert f"cause: {cause}" in self._flags(cause)

    def test_enabled_shows_no_cause(self):
        section_flags = self._section_flags()
        config = MemoryConfig(parzival_enabled=True, parzival_enabled_cause="")
        rendered = "\n".join(section_flags(config))
        assert "Parzival: enabled" in rendered, rendered
        assert "cause:" not in rendered, rendered


class TestManualSaveMemoryPair:
    """`manual_save_memory.py` — the agent-memory gate.

    The gate lives inside `main()`, so `main()` is what runs. Driving the real
    entrypoint is the point: a helper extracted for testability would not prove the
    shipped path branches on cause.
    """

    def _stderr(self, cause: str, monkeypatch, capsys) -> str:
        import importlib.util

        # The script exits at import time unless AI_MEMORY_INSTALL_DIR points at a
        # tree containing src/ — same convention as
        # tests/unit/test_save_memory_agent_types.py.
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(_REPO))
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "test-project")
        script = _REPO / ".claude" / "hooks" / "scripts" / "manual_save_memory.py"
        spec = importlib.util.spec_from_file_location("pairs_manual_save", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        import memory.config as memory_config

        monkeypatch.setattr(
            memory_config, "get_config", lambda: _disabled_config(cause)
        )
        monkeypatch.setattr(
            module.sys, "argv", ["manual_save_memory.py", "--type", "agent_memory", "x"]
        )
        rc = module.main()
        assert rc == 1, f"the agent-memory gate must refuse when disabled (got {rc})"
        return capsys.readouterr().err

    def test_the_two_causes_render_differently(self, monkeypatch, capsys):
        a = self._stderr("opt-out", monkeypatch, capsys)
        b = self._stderr("failed", monkeypatch, capsys)
        assert a != b, (a, b)

    def test_failed_does_not_advise_setting_the_flag(self, monkeypatch, capsys):
        err = self._stderr("failed", monkeypatch, capsys)
        assert "could not be installed" in err, err
        assert "Set PARZIVAL_ENABLED=true" not in err, err

    def test_opt_out_does_advise_setting_the_flag(self, monkeypatch, capsys):
        err = self._stderr("opt-out", monkeypatch, capsys)
        assert "declined at install" in err, err


class TestLangfuseStopHookPair:
    """`langfuse_stop_hook.py` — transport 2, reading raw process env."""

    def _cause(self, cause: str, monkeypatch) -> str:
        from memory.parzival_state import resolve_cause_from_env

        monkeypatch.setenv("PARZIVAL_ENABLED", "false")
        monkeypatch.setenv("PARZIVAL_ENABLED_CAUSE", cause)
        return resolve_cause_from_env()

    @pytest.mark.parametrize("cause", CAUSES)
    def test_the_cause_survives_transport_two(self, cause, monkeypatch):
        assert self._cause(cause, monkeypatch) == cause

    def test_the_two_causes_differ_through_transport_two(self, monkeypatch):
        assert self._cause("opt-out", monkeypatch) != self._cause("failed", monkeypatch)

    def test_absent_cause_in_process_env_is_unknown_not_opt_out(self, monkeypatch):
        from memory.parzival_state import resolve_cause_from_env

        monkeypatch.delenv("PARZIVAL_ENABLED_CAUSE", raising=False)
        assert resolve_cause_from_env() == "unknown"
