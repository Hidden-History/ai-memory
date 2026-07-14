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

import re
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


# A hooks.json / settings.json counts as an ai-memory adapter only when it
# CONTAINS the AI_MEMORY_INSTALL_DIR marker (mirrors the write_<ide>_config
# force-gate grep). These helpers deploy a genuine, marked install.
_MARKED_HOOKS = '{"env": {"AI_MEMORY_INSTALL_DIR": "/home/u/.ai-memory"}}'


def _deploy_cursor(project: Path) -> None:
    (project / ".cursor").mkdir(parents=True, exist_ok=True)
    (project / ".cursor" / "hooks.json").write_text(_MARKED_HOOKS, encoding="utf-8")
    (project / ".cursor" / "skills" / "search-memory").mkdir(
        parents=True, exist_ok=True
    )


def _deploy_codex(project: Path) -> None:
    (project / ".codex").mkdir(parents=True, exist_ok=True)
    (project / ".codex" / "hooks.json").write_text(_MARKED_HOOKS, encoding="utf-8")
    (project / ".codex" / "skills" / "search-memory").mkdir(parents=True, exist_ok=True)
    (project / ".agents" / "skills" / "search-memory").mkdir(
        parents=True, exist_ok=True
    )


def _deploy_gemini(project: Path) -> None:
    (project / ".gemini").mkdir(parents=True, exist_ok=True)
    (project / ".gemini" / "settings.json").write_text(_MARKED_HOOKS, encoding="utf-8")


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


class TestOwnershipMarkerRequiredForNativeConfig:
    """BUG-529 fix-r1 (HIGH clobber defect): a generic per-IDE native config
    (.gemini/settings.json, .cursor/hooks.json, .codex/hooks.json) is
    AI-Memory-owned — and therefore selectable/refreshable — ONLY when it
    contains the AI_MEMORY_INSTALL_DIR marker. A user's unrelated hand-written
    native config lacking the marker must NOT be selected, because
    write_<ide>_config would otherwise wholesale-overwrite it (silent data loss).
    Skill presence is scoped to the ai-memory-named subskill dir, not bare skills/.
    """

    def test_unmarked_gemini_settings_not_selected(self, install_sh_no_main, tmp_path):
        # A user's own .gemini/settings.json (no AI_MEMORY_INSTALL_DIR marker),
        # no AI-MEMORY.md, no CLI → gemini must NOT be selected.
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        (project / ".gemini" / "settings.json").write_text(
            '{"contextFileName": "GEMINI.md", "theme": "dark"}', encoding="utf-8"
        )
        assert _parse_ide(install_sh_no_main, "", project) == []

    def test_unmarked_cursor_hooks_not_selected(self, install_sh_no_main, tmp_path):
        # A user's own .cursor/hooks.json (no marker), no ai-memory skill subdir,
        # no rules/ai-memory.mdc → cursor must NOT be selected.
        project = tmp_path / "proj"
        (project / ".cursor").mkdir(parents=True)
        (project / ".cursor" / "hooks.json").write_text(
            '{"hooks": {"beforeShellExecution": []}}', encoding="utf-8"
        )
        assert "cursor" not in _parse_ide(install_sh_no_main, "", project)

    def test_unmarked_codex_hooks_not_selected(self, install_sh_no_main, tmp_path):
        # A user's own .codex/hooks.json (no marker) + bare (non-ai-memory) skills
        # dirs → codex must NOT be selected.
        project = tmp_path / "proj"
        (project / ".codex").mkdir(parents=True)
        (project / ".codex" / "hooks.json").write_text(
            '{"notify": ["say", "done"]}', encoding="utf-8"
        )
        (project / ".codex" / "skills" / "my-own-skill").mkdir(parents=True)
        (project / ".agents" / "skills" / "unrelated").mkdir(parents=True)
        assert "codex" not in _parse_ide(install_sh_no_main, "", project)

    def test_marked_gemini_settings_selected(self, install_sh_no_main, tmp_path):
        # Positive: a real ai-memory install's settings.json (contains the marker)
        # IS selected even with no CLI on PATH.
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        (project / ".gemini" / "settings.json").write_text(
            '{"env": {"AI_MEMORY_INSTALL_DIR": "/home/u/.ai-memory"}}',
            encoding="utf-8",
        )
        assert _parse_ide(install_sh_no_main, "", project) == ["gemini"]

    def test_marked_hooks_select_cursor_and_codex(self, install_sh_no_main, tmp_path):
        # Positive: real ai-memory install (marked hooks.json) selects both IDEs.
        project = tmp_path / "proj"
        (project / ".cursor").mkdir(parents=True)
        (project / ".cursor" / "hooks.json").write_text(_MARKED_HOOKS, encoding="utf-8")
        (project / ".codex").mkdir(parents=True)
        (project / ".codex" / "hooks.json").write_text(_MARKED_HOOKS, encoding="utf-8")
        selected = _parse_ide(install_sh_no_main, "", project)
        assert "cursor" in selected
        assert "codex" in selected

    def test_ai_memory_skill_subdir_selects_ide(self, install_sh_no_main, tmp_path):
        # Positive: the ai-memory-named skill subdir (search-memory) selects the
        # IDE even when the hooks.json is absent/unmarked.
        project = tmp_path / "proj"
        (project / ".cursor" / "skills" / "search-memory").mkdir(parents=True)
        (project / ".agents" / "skills" / "search-memory").mkdir(parents=True)
        selected = _parse_ide(install_sh_no_main, "", project)
        assert "cursor" in selected
        assert "codex" in selected

    def test_ai_memory_guidance_files_still_select(self, install_sh_no_main, tmp_path):
        # The already-ai-memory-specific guidance markers still count: an
        # ownership-marked AI-MEMORY.md (gemini) / .cursor/rules/ai-memory.mdc.
        # fix-r2 residual #1: AI-MEMORY.md is now ownership-gated (not bare
        # existence) — the fixture must carry the real guidance header.
        project = tmp_path / "proj"
        project.mkdir()
        (project / "AI-MEMORY.md").write_text(
            "# AI Memory — Agent Guidance\n\nguidance body", encoding="utf-8"
        )
        (project / ".cursor" / "rules").mkdir(parents=True)
        (project / ".cursor" / "rules" / "ai-memory.mdc").write_text(
            "---\nalwaysApply: true\n---\n", encoding="utf-8"
        )
        selected = _parse_ide(install_sh_no_main, "", project)
        assert "gemini" in selected
        assert "cursor" in selected

    def test_unmarked_ai_memory_md_not_selected(self, install_sh_no_main, tmp_path):
        # fix-r2 residual #1: a user's own hand-written root AI-MEMORY.md (no
        # ownership header), no marked settings.json, no CLI → gemini must NOT
        # be selected (previously bare existence alone selected it, risking
        # write_gemini_config clobbering the file + settings.json).
        project = tmp_path / "proj"
        project.mkdir()
        (project / "AI-MEMORY.md").write_text(
            "My own notes about AI and memory.", encoding="utf-8"
        )
        assert "gemini" not in _parse_ide(install_sh_no_main, "", project)

    def test_agents_md_managed_block_selects_codex(self, install_sh_no_main, tmp_path):
        # fix-r2 residual #2: an AGENTS.md containing the merge_agents_md.py
        # managed-block marker selects codex, even with no codex CLI on PATH
        # and no other codex adapter artifact present.
        project = tmp_path / "proj"
        project.mkdir()
        (project / "AGENTS.md").write_text(
            "<!-- BEGIN AI-MEMORY -->\nguidance\n<!-- END AI-MEMORY -->\n",
            encoding="utf-8",
        )
        assert _parse_ide(install_sh_no_main, "", project) == ["codex"]


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


class TestGeminiDetectionMarkerParity:
    """fix-r2 parity gate: detect_gemini_project's AI-MEMORY.md ownership grep
    (install.sh) and the shipped gemini template's H1 (both reviewers flagged)
    have nothing asserting they stay in sync. If a future edit changes one and
    not the other, gemini detection silently breaks on existing installs, with
    no failing test. install.sh is the single source of truth for the marker —
    this test extracts it from there rather than hardcoding a third copy."""

    def test_gemini_detection_marker_parity(self):
        install_sh_text = _INSTALL_SH.read_text(encoding="utf-8")
        match = re.search(
            r'grep -q "([^"]+)" "\$project_path/AI-MEMORY\.md"', install_sh_text
        )
        assert match, (
            "Could not find detect_gemini_project's AI-MEMORY.md grep pattern "
            f"in {_INSTALL_SH}. If the grep line moved or changed shape, update "
            "this test's extraction regex."
        )
        marker = match.group(1)

        template_path = (
            _REPO
            / "src"
            / "memory"
            / "adapters"
            / "templates"
            / "gemini"
            / "ai-memory.md"
        )
        template_text = template_path.read_text(encoding="utf-8")
        assert marker in template_text, (
            f"detect_gemini_project's ownership marker {marker!r} (extracted "
            f"from install.sh) is absent from {template_path}. The install.sh "
            "grep and the shipped template's H1 have drifted out of sync — "
            "gemini detection will silently stop working on existing installs "
            "whose AI-MEMORY.md was deployed from an older template."
        )
