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


class TestSpliceBlockMalformedMarkers:
    """splice_block raises MalformedMarkersError on every malformed marker state."""

    def test_stray_begin_only_raises(self):
        stray = "user content\n" + mam.BEGIN_MARKER + "\nmore user content\n"
        with pytest.raises(mam.MalformedMarkersError):
            mam.splice_block(stray, _CONTENT)

    def test_stray_end_only_raises(self):
        stray = "user content\n" + mam.END_MARKER + "\nmore user content\n"
        with pytest.raises(mam.MalformedMarkersError):
            mam.splice_block(stray, _CONTENT)

    def test_end_before_begin_raises(self):
        swapped = "pre\n" + mam.END_MARKER + "\nmid\n" + mam.BEGIN_MARKER + "\npost\n"
        with pytest.raises(mam.MalformedMarkersError):
            mam.splice_block(swapped, _CONTENT)

    def test_duplicate_blocks_raises(self):
        block = mam.build_block(_CONTENT)
        two_blocks = "user\n" + block + "\n\n" + block + "\n"
        with pytest.raises(mam.MalformedMarkersError):
            mam.splice_block(two_blocks, _CONTENT)


class TestMergeAgentsMdMalformed:
    """merge_agents_md leaves the file byte-unchanged and warns on malformed markers."""

    def _assert_refused_twice(
        self, tmp_path, content_file, original_text: str, capsys
    ) -> None:
        """Two calls both refuse: file byte-identical to original, no backup, WARNING in stderr."""
        agents = tmp_path / "AGENTS.md"
        agents.write_text(original_text, encoding="utf-8")

        # Run 1: must refuse without writing.
        with pytest.raises(mam.MalformedMarkersError):
            mam.merge_agents_md(str(agents), str(content_file))
        assert agents.read_text(encoding="utf-8") == original_text
        assert list(tmp_path.glob("AGENTS.md.backup.*")) == []
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

        # Run 2: same input (unchanged file) → same refusal; no stacking or deletion.
        with pytest.raises(mam.MalformedMarkersError):
            mam.merge_agents_md(str(agents), str(content_file))
        assert agents.read_text(encoding="utf-8") == original_text

    def test_stray_begin_user_content_not_deleted(self, tmp_path, content_file, capsys):
        original = (
            "important user content\n" + mam.BEGIN_MARKER + "\nmore user content\n"
        )
        self._assert_refused_twice(tmp_path, content_file, original, capsys)

    def test_stray_end_does_not_stack(self, tmp_path, content_file, capsys):
        original = "user content\n" + mam.END_MARKER + "\nmore user\n"
        self._assert_refused_twice(tmp_path, content_file, original, capsys)

    def test_end_before_begin_does_not_stack(self, tmp_path, content_file, capsys):
        original = "pre\n" + mam.END_MARKER + "\nmid\n" + mam.BEGIN_MARKER + "\npost\n"
        self._assert_refused_twice(tmp_path, content_file, original, capsys)

    def test_duplicate_blocks_refused(self, tmp_path, content_file, capsys):
        block = mam.build_block(_CONTENT)
        original = "user\n" + block + "\n\n" + block + "\n"
        self._assert_refused_twice(tmp_path, content_file, original, capsys)
