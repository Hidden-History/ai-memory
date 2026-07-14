"""BUG-529: installer must refresh already-deployed IDE adapters on a normal update.

Root cause: `parse_ide_flag` auto-detected IDEs ONLY by machine-CLI presence
(`command -v gemini|agent|cursor-agent|codex`). On a machine without the cursor /
codex CLIs, a normal update (no `--ide`) selected gemini only, so the already-
deployed cursor / codex project adapters never re-processed → permanent drift.

Fix (Option 1, DEC-PM401-D2): auto-detect now UNIONs machine-CLI presence with
project-adapter-presence — an IDE is selected when its adapters already exist in
the target project, even when its CLI is absent from PATH. Explicit `--ide <list>`
and `--ide none` semantics are unchanged.

These tests exercise the real `parse_ide_flag` by sourcing install.sh (minus
`main "$@"`). The machine-CLI detectors are shadowed to return false so the tests
deterministically prove selection driven by project-adapter-presence alone,
independent of whatever CLIs happen to be on the test runner's PATH.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"

# Shadow the machine-CLI detectors to "absent" — simulates a machine without
# gemini / cursor / codex CLIs on PATH (the BUG-529 P3 machine minus gemini).
_NO_CLI = (
    "detect_gemini_cli() { return 1; }\n"
    "detect_cursor_ide() { return 1; }\n"
    "detect_codex_cli() { return 1; }\n"
)


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """install.sh minus final 'main \"$@\"' so it can be sourced for its funcs."""
    lines = _INSTALL_SH.read_text(encoding="utf-8").splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    # install.sh sources this helper at load time (before main).
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


def _parse_ide(install_sh: Path, flag: str, project: Path, no_cli: bool = True) -> list:
    """Call parse_ide_flag and return the selected IDE tokens as a list."""
    shadow = _NO_CLI if no_cli else ""
    bash_cmd = f"""
set -euo pipefail
source "{install_sh}"
{shadow}
parse_ide_flag "{flag}" "{project}"
"""
    result = subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def _deploy_cursor(project: Path) -> None:
    (project / ".cursor").mkdir(parents=True, exist_ok=True)
    (project / ".cursor" / "hooks.json").write_text("{}", encoding="utf-8")


def _deploy_codex(project: Path) -> None:
    (project / ".codex").mkdir(parents=True, exist_ok=True)
    (project / ".codex" / "hooks.json").write_text("{}", encoding="utf-8")
    (project / ".agents" / "skills").mkdir(parents=True, exist_ok=True)


def _deploy_gemini(project: Path) -> None:
    (project / ".gemini").mkdir(parents=True, exist_ok=True)
    (project / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")


class TestProjectAdapterPresenceSelectsIDE:
    """Core BUG-529 regression: adapters present → IDE selected, CLI absent."""

    def test_cursor_and_codex_selected_without_their_cli(
        self, install_sh_no_main, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        _deploy_cursor(project)
        _deploy_codex(project)
        selected = _parse_ide(install_sh_no_main, "", project)
        # Both refreshed on a normal update even though neither CLI is on PATH.
        assert "cursor" in selected
        assert "codex" in selected
        # gemini has neither a CLI nor a deployed adapter → not selected.
        assert "gemini" not in selected

    def test_gemini_adapter_presence_selected_without_cli(
        self, install_sh_no_main, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        _deploy_gemini(project)
        selected = _parse_ide(install_sh_no_main, "", project)
        assert selected == ["gemini"]

    def test_cursor_rules_mdc_alone_selects_cursor(self, install_sh_no_main, tmp_path):
        # A guidance-only cursor deploy (rules/ai-memory.mdc) still counts.
        project = tmp_path / "proj"
        (project / ".cursor" / "rules").mkdir(parents=True)
        (project / ".cursor" / "rules" / "ai-memory.mdc").write_text(
            "---\nalwaysApply: true\n---\n", encoding="utf-8"
        )
        selected = _parse_ide(install_sh_no_main, "", project)
        assert "cursor" in selected

    def test_no_adapters_no_cli_selects_nothing(self, install_sh_no_main, tmp_path):
        # No false positives: empty project + no CLIs → no IDEs.
        project = tmp_path / "proj"
        project.mkdir()
        assert _parse_ide(install_sh_no_main, "", project) == []

    def test_cli_and_adapter_both_present_no_duplicate(
        self, install_sh_no_main, tmp_path
    ):
        # gemini CLI present AND adapter deployed → selected exactly once.
        project = tmp_path / "proj"
        project.mkdir()
        _deploy_gemini(project)
        bash_cmd = f"""
set -euo pipefail
source "{install_sh_no_main}"
detect_gemini_cli() {{ return 0; }}
detect_cursor_ide() {{ return 1; }}
detect_codex_cli() {{ return 1; }}
parse_ide_flag "" "{project}"
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.split() == ["gemini"]


class TestExplicitFlagSemanticsPreserved:
    """Explicit --ide wins; adapter-presence must not leak into it."""

    def test_explicit_flag_wins_over_adapter_presence(
        self, install_sh_no_main, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        # codex adapter deployed, but the user explicitly asked for cursor only.
        _deploy_codex(project)
        selected = _parse_ide(install_sh_no_main, "cursor", project)
        assert selected == ["cursor"]

    def test_explicit_comma_list_split(self, install_sh_no_main, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        selected = _parse_ide(install_sh_no_main, "cursor,codex", project)
        assert selected == ["cursor", "codex"]

    def test_none_selects_nothing_even_with_adapters(
        self, install_sh_no_main, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        _deploy_cursor(project)
        _deploy_codex(project)
        _deploy_gemini(project)
        assert _parse_ide(install_sh_no_main, "none", project) == []


class TestSelectionIsReadOnly:
    """The selection path must never mutate user-owned project files (the
    write_<ide>_config force-gate that protects hooks.json/settings.json/GEMINI.md
    is unchanged and out of scope). This asserts selection itself is read-only."""

    def test_parse_ide_flag_does_not_modify_project(self, install_sh_no_main, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        _deploy_cursor(project)
        _deploy_codex(project)
        user_hooks = project / ".cursor" / "hooks.json"
        user_hooks.write_text('{"user": "owned"}', encoding="utf-8")
        before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
        before_tree = sorted(p.relative_to(project) for p in project.rglob("*"))

        _parse_ide(install_sh_no_main, "", project)

        after = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
        after_tree = sorted(p.relative_to(project) for p in project.rglob("*"))
        assert before == after, "selection mutated a project file"
        assert before_tree == after_tree, "selection created/removed a path"
        assert user_hooks.read_text(encoding="utf-8") == '{"user": "owned"}'
