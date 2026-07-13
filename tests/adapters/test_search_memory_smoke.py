"""Smoke test for BUG-525: adapter search-memory templates must cite a
runnable CLI with an argv shape that actually parses.

Verifies gemini/search-memory.toml, codex/search-memory/SKILL.md, and
cursor/search-memory/SKILL.md all reference the real
`scripts/memory/search_cli.py` CLI (positional query, routed through
`run-with-env.sh`, with NO `--group-id`/basename argument — the shared
resolver in `memory.project` handles project-id resolution) rather than the
non-existent `src/memory/search_cli.py` / `src/memory/search.py` paths, the
argparse-rejected `--query`/`--project` flags, or the removed
directory-basename fallback.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "src" / "memory" / "adapters" / "templates"
SEARCH_CLI_PATH = REPO_ROOT / "scripts" / "memory" / "search_cli.py"
RUN_WITH_ENV_PATH = REPO_ROOT / "scripts" / "memory" / "run-with-env.sh"

# Mirrors tests/test_search_cli.py's import convention.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "memory"))
import search_cli  # noqa: E402

TEMPLATE_FILES = {
    "gemini": TEMPLATES_DIR / "gemini" / "search-memory.toml",
    "codex": TEMPLATES_DIR / "codex" / "search-memory" / "SKILL.md",
    "cursor": TEMPLATES_DIR / "cursor" / "search-memory" / "SKILL.md",
}


class TestSearchCliPathExists:
    """(a) The path every template cites must exist on disk."""

    def test_search_cli_py_exists(self):
        assert SEARCH_CLI_PATH.exists(), f"Missing: {SEARCH_CLI_PATH}"

    def test_run_with_env_wrapper_exists(self):
        assert RUN_WITH_ENV_PATH.exists(), f"Missing: {RUN_WITH_ENV_PATH}"


class TestTemplatesCiteCorrectInterface:
    """Each template must cite the real path/flags, not the broken ones."""

    @pytest.mark.parametrize("adapter", TEMPLATE_FILES)
    def test_cites_real_search_cli_path(self, adapter):
        content = TEMPLATE_FILES[adapter].read_text()
        assert "scripts/memory/search_cli.py" in content
        assert "src/memory/search_cli.py" not in content
        assert "src/memory/search.py" not in content

    @pytest.mark.parametrize("adapter", TEMPLATE_FILES)
    def test_no_group_id_or_basename_fallback(self, adapter):
        content = TEMPLATE_FILES[adapter].read_text()
        assert "--group-id" not in content
        assert "basename" not in content
        assert "--query" not in content
        assert "--project" not in content

    @pytest.mark.parametrize("adapter", TEMPLATE_FILES)
    def test_routes_through_run_with_env_wrapper(self, adapter):
        content = TEMPLATE_FILES[adapter].read_text()
        assert "run-with-env.sh" in content

    @pytest.mark.parametrize("adapter", TEMPLATE_FILES)
    def test_run_with_env_precedes_search_cli(self, adapter):
        """run-with-env.sh must invoke search_cli.py, not the reverse."""
        content = TEMPLATE_FILES[adapter].read_text()
        assert content.index("run-with-env.sh") < content.index(
            "scripts/memory/search_cli.py"
        )


class TestArgvShapeParsesAgainstRealCli:
    """(b) The new argv shape must parse; the old broken shape must not."""

    def test_positional_query_only_parses(self):
        with patch(
            "sys.argv",
            [
                "search_cli.py",
                "authentication implementation",
            ],
        ):
            args = search_cli.parse_args()
        assert args.query == "authentication implementation"
        assert args.group_id is None

    def test_old_query_and_project_flags_rejected(self):
        with patch(
            "sys.argv",
            [
                "search_cli.py",
                "--query",
                "authentication implementation",
                "--project",
                "my-project",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                search_cli.parse_args()
            assert exc_info.value.code == 2  # argparse rejects unrecognized flags
