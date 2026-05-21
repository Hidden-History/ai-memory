"""Tests for PLAN-028 P1B / W-09 required-explicit project-scope enforcement.

Coverage:
- ``detect_project()`` raises ``ValueError`` on un-resolvable cwd (no env var,
  no git remote, basename fallback removed per DEC-PM302-D2 Q-5).
- Every public store API raises ``ValueError`` on missing/empty ``group_id``.
- Every public search API raises ``ValueError`` on missing/empty ``group_id``.
- Per-item ``group_id`` validation in batch methods.

Anchors: DEC-PM298-D4 (P1 template), DEC-PM302-D1 (P1B locked design),
DEC-PM302-D2 (Wb dispositions Q-1..Q-6), DEC-PM302-D4 (BL-1..BL-6 expansions).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# =============================================================================
# detect_project() — chokepoint raises on resolution failure
# =============================================================================


class TestDetectProjectFailLoud:
    """``detect_project()`` raises ValueError when no scope is resolvable."""

    def test_raises_when_no_env_no_git_no_edge_case(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Plain non-git tmp dir with no AI_MEMORY_PROJECT_ID set must raise."""
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        from memory.project import detect_project

        # tmp_path is not /, not home, not in /tmp special-case patterns
        # (it's typically /tmp/pytest-of-USER/pytest-N/test_X which the
        # edge-case logic considers nested, not a direct child of /tmp).
        non_temp_dir = tmp_path / "plain-dir-no-git"
        non_temp_dir.mkdir()

        with pytest.raises(ValueError, match="project detection failed"):
            detect_project(str(non_temp_dir))

    def test_env_var_short_circuits_detection(self, monkeypatch) -> None:
        """AI_MEMORY_PROJECT_ID env var bypasses other detection paths."""
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "explicit-project")
        from memory.project import detect_project

        assert detect_project("/nonexistent/path") == "explicit-project"


# =============================================================================
# Storage public APIs — required-explicit group_id
# =============================================================================


class TestStorageRequiredExplicit:
    """All public store_* methods require a non-empty group_id."""

    @pytest.fixture
    def storage(self):
        """MemoryStorage stub — won't be invoked for arg-validation tests."""
        from memory.storage import MemoryStorage

        # Use MagicMock to bypass __init__ side effects (qdrant connection etc.).
        instance = MagicMock(spec=MemoryStorage)
        # Bind the real method so the call goes through actual validation.
        instance.store_memory = MemoryStorage.store_memory.__get__(instance)
        instance.store_memories_batch = MemoryStorage.store_memories_batch.__get__(
            instance
        )
        instance.store_github_code_blob_chunks_batch = (
            MemoryStorage.store_github_code_blob_chunks_batch.__get__(instance)
        )
        instance.store_agent_memory = MemoryStorage.store_agent_memory.__get__(instance)
        return instance

    def test_store_memory_rejects_missing_group_id_kwarg(self, storage) -> None:
        """store_memory raises TypeError when keyword-only group_id is absent."""
        from memory.models import MemoryType

        with pytest.raises(TypeError, match="group_id"):
            storage.store_memory(
                content="x" * 50,
                cwd="/tmp",
                memory_type=MemoryType.IMPLEMENTATION,
                source_hook="test",
                session_id="sess-1",
            )

    def test_store_memory_rejects_empty_group_id(self, storage) -> None:
        from memory.models import MemoryType

        with pytest.raises(ValueError, match="explicit project scope"):
            storage.store_memory(
                content="x" * 50,
                cwd="/tmp",
                memory_type=MemoryType.IMPLEMENTATION,
                source_hook="test",
                session_id="sess-1",
                group_id="",
            )

    def test_store_memory_rejects_whitespace_group_id(self, storage) -> None:
        from memory.models import MemoryType

        with pytest.raises(ValueError, match="explicit project scope"):
            storage.store_memory(
                content="x" * 50,
                cwd="/tmp",
                memory_type=MemoryType.IMPLEMENTATION,
                source_hook="test",
                session_id="sess-1",
                group_id="   ",
            )

    def test_store_memories_batch_rejects_missing_group_id(self, storage) -> None:
        with pytest.raises(TypeError, match="group_id"):
            storage.store_memories_batch(memories=[])

    def test_store_memories_batch_rejects_empty_group_id(self, storage) -> None:
        with pytest.raises(ValueError, match="explicit project scope"):
            storage.store_memories_batch(memories=[{"content": "x"}], group_id="")

    def test_store_memories_batch_rejects_per_item_empty_group_id(
        self, storage
    ) -> None:
        """Per-item group_id override must be non-empty too."""
        with pytest.raises(ValueError, match="per-item group_id"):
            storage.store_memories_batch(
                memories=[{"content": "x" * 50, "group_id": ""}],
                group_id="batch-default",
            )

    def test_store_github_blob_chunks_rejects_empty_group_id(self, storage) -> None:
        from memory.models import MemoryType

        with pytest.raises(ValueError, match="explicit project scope"):
            storage.store_github_code_blob_chunks_batch(
                chunk_items=[{"content": "x"}],
                cwd="/tmp",
                collection="github",
                group_id="",
                memory_type=MemoryType.GITHUB_CODE_BLOB,
                source_hook="github_code_sync",
                session_id="sync-1",
            )

    def test_store_agent_memory_rejects_missing_group_id(self, storage) -> None:
        with pytest.raises(TypeError, match="group_id"):
            storage.store_agent_memory(content="x" * 50, memory_type="agent_memory")

    def test_store_agent_memory_rejects_empty_group_id(self, storage) -> None:
        with pytest.raises(ValueError, match="explicit project scope"):
            storage.store_agent_memory(
                content="x" * 50, memory_type="agent_memory", group_id=""
            )


# =============================================================================
# Search public APIs — required-explicit group_id (5 entry points)
# =============================================================================


class TestSearchRequiredExplicit:
    """All 5 public search entry points require non-empty group_id (BL-3)."""

    @pytest.fixture
    def search(self):
        from memory.search import MemorySearch

        instance = MagicMock(spec=MemorySearch)
        instance.search = MemorySearch.search.__get__(instance)
        instance.search_both_collections = MemorySearch.search_both_collections.__get__(
            instance
        )
        instance.get_recent = MemorySearch.get_recent.__get__(instance)
        instance.cascading_search = MemorySearch.cascading_search.__get__(instance)
        return instance

    def test_search_rejects_missing_group_id(self, search) -> None:
        with pytest.raises(TypeError, match="group_id"):
            search.search(query="anything")

    def test_search_rejects_empty_group_id(self, search) -> None:
        with pytest.raises(ValueError, match="explicit project scope"):
            search.search(query="anything", group_id="")

    def test_search_both_collections_rejects_missing_group_id(self, search) -> None:
        with pytest.raises(TypeError, match="group_id"):
            search.search_both_collections(query="anything")

    def test_search_both_collections_rejects_empty_group_id(self, search) -> None:
        with pytest.raises(ValueError, match="explicit project scope"):
            search.search_both_collections(query="anything", group_id="")

    def test_get_recent_rejects_missing_group_id(self, search) -> None:
        with pytest.raises(TypeError, match="group_id"):
            search.get_recent(collection="code-patterns")

    def test_get_recent_rejects_empty_group_id(self, search) -> None:
        with pytest.raises(ValueError, match="explicit project scope"):
            search.get_recent(collection="code-patterns", group_id="")

    def test_cascading_search_rejects_missing_group_id(self, search) -> None:
        with pytest.raises(TypeError, match="group_id"):
            search.cascading_search(
                query="anything",
                primary_collection="code-patterns",
                secondary_collections=["conventions"],
            )

    def test_cascading_search_rejects_empty_group_id(self, search) -> None:
        with pytest.raises(ValueError, match="explicit project scope"):
            search.cascading_search(
                query="anything",
                group_id="",
                primary_collection="code-patterns",
                secondary_collections=["conventions"],
            )

    def test_module_search_memories_rejects_missing_group_id(self) -> None:
        from memory.search import search_memories

        with pytest.raises(TypeError, match="group_id"):
            search_memories(query="anything")

    def test_module_search_memories_rejects_empty_group_id(self) -> None:
        from memory.search import search_memories

        with pytest.raises(ValueError, match="explicit project scope"):
            search_memories(query="anything", group_id="")


# =============================================================================
# Search filter is unconditional — covered structurally by the TypeError +
# ValueError tests above: if group_id cannot be missing/empty, the filter
# branch is unconditional by construction (the "no_filter" branch was removed
# in MemorySearch.search and search_both_collections per DEC-PM302-D1).
# =============================================================================
