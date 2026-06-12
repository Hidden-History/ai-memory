"""Unit tests for the Codex AGENTS.md managed-block splice (TD-600).

merge_agents_md.py delivers AI-Memory's Codex guidance as a managed marker-block
inside the project-root AGENTS.md. Core safety properties:

  - insert-if-absent / replace-in-place (never stacks a second block);
  - everything OUTSIDE the markers stays byte-for-byte;
  - an existing AGENTS.md is backed up (copy) before writing;
  - the write is atomic (no partial/corrupt AGENTS.md on failure).
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "merge_agents_md.py"

_spec = importlib.util.spec_from_file_location("merge_agents_md", _SCRIPT)
mam = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mam)

_CONTENT = "# AI Memory — Agent Guidance\n\nUse `search-memory` and `memory-status`.\n"


@pytest.fixture
def content_file(tmp_path) -> Path:
    p = tmp_path / "content.md"
    p.write_text(_CONTENT, encoding="utf-8")
    return p


class TestSpliceBlock:
    def test_insert_into_empty(self):
        out = mam.splice_block("", _CONTENT)
        assert out.startswith(mam.BEGIN_MARKER)
        assert mam.END_MARKER in out
        assert "search-memory" in out

    def test_insert_preserves_user_content_verbatim(self):
        user = "# My project\n\nCustom instructions for my agent.\n"
        out = mam.splice_block(user, _CONTENT)
        # User content is preserved exactly as a prefix.
        assert out.startswith(user)
        assert mam.BEGIN_MARKER in out and mam.END_MARKER in out

    def test_replace_in_place_is_idempotent(self):
        user = "# My project\n\nKeep me.\n"
        once = mam.splice_block(user, _CONTENT)
        twice = mam.splice_block(once, _CONTENT)
        assert once == twice
        assert once.count(mam.BEGIN_MARKER) == 1
        assert once.count(mam.END_MARKER) == 1

    def test_replace_preserves_bytes_outside_markers(self):
        pre = "# Header\n\nuser pre text\n\n"
        post = "\n\n## Trailer\n\nuser post text\n"
        original = pre + mam.build_block("OLD AI-MEMORY CONTENT") + post
        out = mam.splice_block(original, _CONTENT)
        # Bytes before BEGIN and after END are byte-identical; only the block changed.
        assert out.startswith(pre)
        assert out.endswith(post)
        assert "OLD AI-MEMORY CONTENT" not in out
        assert "search-memory" in out

    def test_block_content_has_no_marker_leak(self):
        out = mam.splice_block("", _CONTENT)
        # Exactly one marker pair.
        assert out.count(mam.BEGIN_MARKER) == 1
        assert out.count(mam.END_MARKER) == 1


class TestMergeAgentsMd:
    def test_creates_new_agents_md(self, tmp_path, content_file):
        agents = tmp_path / "AGENTS.md"
        mam.merge_agents_md(str(agents), str(content_file))
        assert agents.exists()
        text = agents.read_text(encoding="utf-8")
        assert mam.BEGIN_MARKER in text and mam.END_MARKER in text
        assert "search-memory" in text

    def test_backup_created_for_existing_file(self, tmp_path, content_file):
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Existing user AGENTS\n", encoding="utf-8")
        mam.merge_agents_md(str(agents), str(content_file))
        backups = list(tmp_path.glob("AGENTS.md.backup.*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "# Existing user AGENTS\n"

    def test_user_content_preserved_byte_for_byte(self, tmp_path, content_file):
        agents = tmp_path / "AGENTS.md"
        user_text = "# My AGENTS\n\nDo not clobber this.\n"
        agents.write_text(user_text, encoding="utf-8")
        mam.merge_agents_md(str(agents), str(content_file))
        out = agents.read_text(encoding="utf-8")
        assert out.startswith(user_text)

    def test_rerun_replaces_not_duplicates(self, tmp_path, content_file):
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# My AGENTS\n\nKeep me.\n", encoding="utf-8")
        mam.merge_agents_md(str(agents), str(content_file))
        first = agents.read_text(encoding="utf-8")
        mam.merge_agents_md(str(agents), str(content_file))
        second = agents.read_text(encoding="utf-8")
        assert first == second
        assert second.count(mam.BEGIN_MARKER) == 1

    def test_no_temp_files_left_behind(self, tmp_path, content_file):
        agents = tmp_path / "AGENTS.md"
        mam.merge_agents_md(str(agents), str(content_file))
        leftovers = list(tmp_path.glob(".AGENTS_*"))
        assert leftovers == []
