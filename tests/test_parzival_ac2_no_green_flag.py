"""AC-2: no code path sets the enabled-state flag true over an undeployed component.

The "exactly one true-write" claim covers ``set_env_value`` calls only, and
``docker/.env.example`` reaches the flag by ``cp``, not ``set_env_value``. That is
the same non-set_env_value blind spot the story caught for ``false``-writes, never
re-run for ``true``-writes — which is where AC-2 lives.

The abort window is real: ``copy_files`` does ``cp .env.example .env`` when no .env
exists, and ``setup_parzival`` is not reached until much later in ``main()``.
Between them run ~20 steps including venv creation, Docker startup and health
verification, plus an ``exit 1``. Any abort in that window persists whatever
``.env.example`` shipped — so a shipped ``true`` is a green flag over a component
that was never deployed.

Line numbers are deliberately not pinned in this docstring. An earlier revision
cited install.sh:1405/2461/1482/1409 as evidence, and this same commit reflows all
four — an anchor a commit falsifies is worse than no anchor (A-13 already ruled
that line numbers are hints and anchors must be quoted lines).

**On what this module does NOT do.** Two earlier tests here asserted byte offsets
and called it reachability: one compared ``body.index(...)`` positions of two
strings in install.sh, with a needle hard-coding eight leading spaces so a reindent
raised ValueError rather than failing usefully; the other ``shutil.copy``-ed the
template and re-asserted it, never invoking ``copy_files``, so the abort window was
never entered. Text offsets are not control flow, and no amount of care makes them
so. Both are replaced below by tests that drive the real functions through the
established no-main harness.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
_ENV_EXAMPLE = _REPO / "docker" / ".env.example"
_INSTALL_SH = _SCRIPTS / "install.sh"


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """The real install.sh minus its final `main "$@"`, so it can be sourced."""
    lines = _INSTALL_SH.read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(_SCRIPTS / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh")
    return copy


def _env_example_values() -> dict[str, str]:
    out = {}
    for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


class TestShippedTemplateCarriesNoGreenFlag:
    def test_env_example_does_not_ship_an_enabled_flag(self):
        assert _env_example_values().get("PARZIVAL_ENABLED") == "false"

    def test_env_example_documents_the_cause_and_condition_keys(self):
        """Also the CI gate: check_env_completeness exits 1 on an undocumented field."""
        values = _env_example_values()
        assert "PARZIVAL_ENABLED_CAUSE" in values, values.keys()
        assert "PARZIVAL_ENABLED_CONDITION" in values, values.keys()

    def test_shipped_default_matches_the_documented_default(self):
        """INSTALL.md and docs/CONFIGURATION.md both document the default as false."""
        install_md = (_REPO / "INSTALL.md").read_text(encoding="utf-8")
        assert "| `PARZIVAL_ENABLED` | Enable Parzival integration | `false` |" in (
            install_md
        )
        assert _env_example_values().get("PARZIVAL_ENABLED") == "false"


class TestAbortWindowLeavesNoGreenFlag:
    """Enter the abort window for real: run copy_files, then stop.

    This invokes the shipped ``copy_files`` rather than re-performing what it is
    believed to do. That distinction is the whole finding — a test that copies the
    template itself proves the template is fine and says nothing about the
    installer, which is what TR-5 requires and what AC-2 is about.
    """

    def test_copy_files_does_not_persist_a_true_flag(
        self, install_sh_no_main, tmp_path
    ):
        install_dir = tmp_path / "install_dir"
        (install_dir / "docker").mkdir(parents=True)

        res = subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                # Stubs for the collaborators copy_files calls that are not part of
                # the .env decision. copy_files itself is real.
                "configure_project_hooks() { :; }\n" "copy_files\n",
            ],
            capture_output=True,
            text=True,
            cwd=str(_REPO),
        )
        env_file = install_dir / "docker" / ".env"
        assert env_file.exists(), (
            "copy_files did not produce docker/.env — the abort window was never "
            f"entered, so this test proves nothing.\n{res.stdout}\n{res.stderr}"
        )
        body = env_file.read_text(encoding="utf-8")
        assert re.search(
            r"^PARZIVAL_ENABLED=", body, re.M
        ), f"docker/.env carries no PARZIVAL_ENABLED at all:\n{body}"
        assert not re.search(r"^PARZIVAL_ENABLED=true\s*$", body, re.M), (
            "an install aborting between copy_files and setup_parzival would leave "
            f"a green flag over a component that was never deployed:\n{body}"
        )

    def test_the_flag_is_false_before_setup_parzival_ever_runs(
        self, install_sh_no_main, tmp_path
    ):
        """The positive half: not merely 'not true' but explicitly recorded false."""
        install_dir = tmp_path / "install_dir"
        (install_dir / "docker").mkdir(parents=True)
        subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                "configure_project_hooks() { :; }\n"
                "copy_files\n",
            ],
            capture_output=True,
            text=True,
            cwd=str(_REPO),
        )
        body = (install_dir / "docker" / ".env").read_text(encoding="utf-8")
        assert re.search(r"^PARZIVAL_ENABLED=false\s*$", body, re.M), body


class TestExactlyOneTrueWriteReachesTheFlag:
    """Re-derive the true-write set with the non-set_env_value matcher."""

    def test_installer_has_exactly_one_enabling_write(self):
        body = _INSTALL_SH.read_text(encoding="utf-8")
        # The single enabling write now goes through the record helper.
        enabling = re.findall(r'set_parzival_enablement "true"', body)
        assert len(enabling) == 1, f"expected exactly one true-write, got {enabling}"

    def test_no_call_site_writes_the_flag_without_a_cause(self):
        """Every enablement write goes through the record helper, never raw.

        Zero raw ``set_env_value "PARZIVAL_ENABLED"`` calls now survive: the helper
        builds the whole record in one atomic pass and does not call set_env_value
        at all. Any occurrence means some site writes a value with no cause beside
        it, which is the shape AC-2 forbids.
        """
        body = _INSTALL_SH.read_text(encoding="utf-8")
        raw = re.findall(r'set_env_value "PARZIVAL_ENABLED"', body)
        assert raw == [], f"raw flag writes bypass the cause record: {raw}"

    def test_a_failed_deploy_never_produces_a_true_flag(
        self, install_sh_no_main, tmp_path
    ):
        """AC-2 as CONTROL FLOW, driven, not as two string positions compared.

        This replaces a test that compared ``body.index()`` byte offsets of
        "deploy_parzival_v2 || {" and "        configure_parzival_env" and called the
        comparison reachability. It could not fail usefully — the needle hard-coded
        eight leading spaces, so a reindent raised ValueError — and two strings
        being in a particular order in a file is not evidence about which one runs.

        Here the real ``setup_parzival`` runs with ``deploy_parzival_v2`` returning
        non-zero, and the assertion is on the record the real code actually wrote.
        """
        install_dir = tmp_path / "install_dir"
        project_dir = tmp_path / "project_dir"
        (install_dir / "docker").mkdir(parents=True)
        (install_dir / "_ai-memory").mkdir(parents=True)
        project_dir.mkdir()

        stubs = "\n".join(
            f"{fn}() {{ :; }}"
            for fn in (
                "deploy_ai_memory_skills",
                "deploy_ai_memory_agents",
                "cleanup_parzival_v1",
                "cleanup_stale_tilde_dir",
                "deploy_parzival_shims",
                "generate_parzival_skill_shims",
                "deploy_oversight_templates",
                "sync_parzival_config_yaml",
                "create_agent_id_index",
                "setup_model_dispatch",
                "sync_parzival_settings",
            )
        )
        res = subprocess.run(
            [
                "bash",
                "-c",
                "set -uo pipefail\n"
                f'export INSTALL_DIR="{install_dir}"\n'
                f'export PROJECT_PATH="{project_dir}"\n'
                'export NON_INTERACTIVE="true"\n'
                f'source "{install_sh_no_main}"\n'
                f'INSTALL_DIR="{install_dir}"\n'
                f'PROJECT_PATH="{project_dir}"\n'
                'NON_INTERACTIVE="true"\n'
                'INSTALL_PARZIVAL="true"\n'
                f"{stubs}\n"
                'detect_parzival_version() { echo "none"; }\n'
                "deploy_parzival_v2() { return 1; }\n"
                "setup_parzival\n",
            ],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        body = (install_dir / "docker" / ".env").read_text(encoding="utf-8")
        assert not re.search(
            r"^PARZIVAL_ENABLED=true\s*$", body, re.M
        ), f"a failed deploy set the enabled flag true:\n{body}"
        assert re.search(r"^PARZIVAL_ENABLED=false\s*$", body, re.M), body
        assert re.search(r"^PARZIVAL_ENABLED_CAUSE=failed\s*$", body, re.M), body
        # TR-6: "every one of tests 1-5 asserts all three keys". Tests 1-4 go through
        # _assert_record(), which checks the condition; this one asserted value and
        # cause only, so AC-1 could not fail on its third field at the site AC-2 owns.
        assert re.search(
            r"^PARZIVAL_ENABLED_CONDITION=complete\s*$", body, re.M
        ), f"TR-6: the condition key is part of the record at every site:\n{body}"
