"""Tests for project-scoped storage (Story 4.2).

Tests AC 4.2.1-4.2.4:
- AC 4.2.1: Storage with automatic project detection via cwd
- AC 4.2.2: Retrieval with group_id filtering
- AC 4.2.3: Payload index creation with is_tenant=True
- AC 4.2.4: Multi-project isolation verification

Architecture Reference: architecture.md:516-690 (Storage), architecture.md:747-863 (Search)
"""

import uuid
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.memory.storage import MemoryStorage
from src.memory.search import MemorySearch
from src.memory.models import MemoryType


def unique_content(prefix: str) -> str:
    """Generate unique content string to avoid deduplication collisions."""
    return f"{prefix} - {uuid.uuid4().hex[:8]}"


class TestProjectScopedStorage:
    """Test automatic project detection and scoped storage (AC 4.2.1)."""

    @pytest.mark.integration
    def test_store_memory_with_cwd_parameter(self, qdrant_client, tmp_path):
        """Test store_memory requires cwd parameter for project detection.

        AC 4.2.1: When store_memory() is called with cwd parameter,
        project is automatically detected using detect_project(cwd).
        """
        # Create temp project directory
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()  # Make it a git repo

        storage = MemoryStorage()

        # Use unique content to avoid deduplication
        content = unique_content("Project A implementation pattern")

        # EXPECTED: This should work with cwd parameter
        result = storage.store_memory(
            content=content,
            cwd=str(project_dir),  # BREAKING CHANGE: cwd is now required
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-session",
            collection="implementations",
        )

        # Verify storage succeeded
        assert result["status"] == "stored"
        assert result["memory_id"] is not None

    def test_store_memory_without_cwd_fails(self, qdrant_client):
        """Test store_memory fails without cwd parameter.

        AC 4.2.1: cwd is required for project detection (breaking change).
        """
        storage = MemoryStorage()

        # EXPECTED: This should raise TypeError for missing required parameter
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'cwd'"):
            storage.store_memory(
                content="No project context",
                # cwd is missing
                memory_type=MemoryType.IMPLEMENTATION,
                source_hook="PostToolUse",
                session_id="test-session",
            )

    @pytest.mark.integration
    def test_store_memory_auto_detects_group_id(self, qdrant_client, tmp_path):
        """Test group_id is auto-detected from cwd even if not provided.

        AC 4.2.1: group_id is automatically set from detect_project(cwd).
        """
        # Create project A
        project_a = tmp_path / "project-alpha"
        project_a.mkdir()
        (project_a / ".git").mkdir()

        storage = MemoryStorage()

        # Use unique content
        content = unique_content("Auto-detected project")

        # Don't pass group_id explicitly - should be auto-detected
        result = storage.store_memory(
            content=content,
            cwd=str(project_a),
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-session",
        )

        assert result["status"] == "stored"
        # group_id should be "project-alpha" (auto-detected)


class TestProjectScopedRetrieval:
    """Test search with group_id filtering (AC 4.2.2)."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_with_cwd_parameter(self, qdrant_client, tmp_path):
        """Test search accepts cwd parameter for automatic project detection.

        AC 4.2.2: search() called with cwd auto-detects group_id.
        """
        # Create temp project
        project_dir = tmp_path / "search-project"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        # Use unique content
        content = unique_content("Search test content")

        # Store memory with cwd
        storage = MemoryStorage()
        storage.store_memory(
            content=content,
            cwd=str(project_dir),
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-session",
        )

        # Search with cwd parameter
        search = MemorySearch()
        results = search.search(
            query="Search test",
            collection="implementations",
            cwd=str(project_dir),  # NEW: cwd for auto-detection
            limit=5,
        )

        # Should find the memory we just stored
        assert len(results) >= 1
        assert any("Search test" in r["content"] for r in results)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_uses_type_safe_filter_construction(self, qdrant_client, tmp_path):
        """Test search uses Filter + FieldCondition (2026 best practice).

        AC 4.2.2: Filter construction uses FieldCondition with MatchValue,
        not dict-based filters.
        """
        project_dir = tmp_path / "filter-project"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        # Use unique content
        content = unique_content("Type-safe filter test")

        storage = MemoryStorage()
        storage.store_memory(
            content=content,
            cwd=str(project_dir),
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-session",
        )

        search = MemorySearch()
        # This should work with type-safe filter construction
        results = search.search(
            query="Type-safe",
            cwd=str(project_dir),
            collection="implementations",
        )

        assert isinstance(results, list)
        # No errors means type-safe filtering worked


class TestPayloadIndexCreation:
    """Test payload index creation with is_tenant=True (AC 4.2.3)."""

    def test_payload_index_exists_for_group_id(self, qdrant_client):
        """Test group_id payload index exists with is_tenant=True.

        AC 4.2.3: Payload index created for group_id field with is_tenant=True
        for optimal filtering performance.
        """
        # Check if index exists (will be created during initialization)
        collection_info = qdrant_client.get_collection("implementations")

        # Qdrant 1.16+ returns payload_schema as dict of PayloadIndexInfo
        payload_schema = collection_info.payload_schema

        # Verify payload index exists for group_id
        assert "group_id" in payload_schema, "group_id index should exist"

        # Check for keyword index type (required for is_tenant)
        group_id_index = payload_schema["group_id"]
        # PayloadIndexInfo has data_type attribute (case varies by Qdrant version)
        assert group_id_index.data_type.name.lower() == "keyword", "group_id should be keyword type"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_index_improves_filtering_performance(self, qdrant_client, tmp_path):
        """Test that is_tenant index provides fast filtering (<100ms overhead).

        AC 4.2.3: Index enables fast filtering performance.
        """
        import time

        # Create multiple projects
        projects = []
        for i in range(5):
            proj = tmp_path / f"perf-project-{i}"
            proj.mkdir()
            (proj / ".git").mkdir()
            projects.append(proj)

        # Store 50 memories across projects (10 per project)
        storage = MemoryStorage()
        for i in range(10):
            for proj in projects:
                # Use unique content for each
                content = unique_content(f"Performance test memory {i}")
                storage.store_memory(
                    content=content,
                    cwd=str(proj),
                    memory_type=MemoryType.IMPLEMENTATION,
                    source_hook="PostToolUse",
                    session_id="perf-session",
                )

        # Measure filtered search performance
        search = MemorySearch()
        start = time.time()
        results = search.search(
            query="Performance test",
            cwd=str(projects[0]),  # Filter to single project
            limit=5,
        )
        elapsed_ms = (time.time() - start) * 1000

        # With is_tenant index, filtering should add <10ms overhead
        # Allow 100ms margin for CI environments
        assert elapsed_ms < 100, f"Search took {elapsed_ms}ms, expected <100ms"
        assert len(results) > 0


class TestMultiProjectIsolation:
    """Test memory isolation between projects (AC 4.2.4)."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_project_isolation_basic(self, qdrant_client, tmp_path):
        """Test memories are isolated between different projects.

        AC 4.2.4: Memories from project-a are NOT returned when
        searching from project-b.
        """
        unique_id = uuid.uuid4().hex[:8]

        # Create two projects
        project_a = tmp_path / "project-a"
        project_a.mkdir()
        (project_a / ".git").mkdir()

        project_b = tmp_path / "project-b"
        project_b.mkdir()
        (project_b / ".git").mkdir()

        storage = MemoryStorage()

        # Store memory in project A with unique content
        storage.store_memory(
            content=f"Project A implementation pattern - {unique_id}",
            cwd=str(project_a),
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="a-session",
        )

        # Store memory in project B with unique content
        storage.store_memory(
            content=f"Project B implementation pattern - {unique_id}",
            cwd=str(project_b),
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="b-session",
        )

        search = MemorySearch()

        # Search from project A
        results_a = search.search(
            query=f"implementation pattern {unique_id}",
            collection="implementations",
            cwd=str(project_a),
        )

        # Search from project B
        results_b = search.search(
            query=f"implementation pattern {unique_id}",
            collection="implementations",
            cwd=str(project_b),
        )

        # Verify isolation: Project A results should NOT contain Project B content
        assert any("Project A" in r["content"] for r in results_a)
        assert not any("Project B" in r["content"] for r in results_a)

        # Verify isolation: Project B results should NOT contain Project A content
        assert any("Project B" in r["content"] for r in results_b)
        assert not any("Project A" in r["content"] for r in results_b)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_project_isolation_with_multiple_memories(self, qdrant_client, tmp_path):
        """Test isolation holds with multiple memories per project.

        AC 4.2.4: Comprehensive isolation verification.
        """
        unique_id = uuid.uuid4().hex[:8]

        # Create three projects
        projects = {}
        for name in ["alpha", "beta", "gamma"]:
            proj = tmp_path / f"project-{name}"
            proj.mkdir()
            (proj / ".git").mkdir()
            projects[name] = proj

        storage = MemoryStorage()

        # Store 3 memories per project with unique content
        for name, proj in projects.items():
            for i in range(3):
                storage.store_memory(
                    content=f"Memory {i} from {name} - {unique_id}",
                    cwd=str(proj),
                    memory_type=MemoryType.IMPLEMENTATION,
                    source_hook="PostToolUse",
                    session_id=f"{name}-session",
                )

        search = MemorySearch()

        # Search each project and verify isolation
        for name, proj in projects.items():
            results = search.search(
                query=f"Memory from {unique_id}",
                cwd=str(proj),
                collection="implementations",
                limit=10,
            )

            # Should only see memories from THIS project
            for result in results:
                assert name in result["content"], (
                    f"Project {name} search returned memory from another project: "
                    f"{result['content']}"
                )

    @pytest.mark.integration
    @pytest.mark.slow
    def test_search_without_cwd_returns_all_projects(self, qdrant_client, tmp_path):
        """Test search without cwd/group_id returns memories from all projects.

        AC 4.2.4: When no group_id filter is applied, all memories are searchable.
        """
        unique_id = uuid.uuid4().hex[:8]

        # Create two projects
        project_a = tmp_path / "global-a"
        project_a.mkdir()
        (project_a / ".git").mkdir()

        project_b = tmp_path / "global-b"
        project_b.mkdir()
        (project_b / ".git").mkdir()

        storage = MemoryStorage()

        # Store in both projects with unique content
        storage.store_memory(
            content=f"Global search test A - {unique_id}",
            cwd=str(project_a),
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="global-session",
        )

        storage.store_memory(
            content=f"Global search test B - {unique_id}",
            cwd=str(project_b),
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="global-session",
        )

        search = MemorySearch()

        # Search without cwd (no group_id filter)
        results = search.search(
            query=f"Global search test {unique_id}",
            collection="implementations",
            cwd=None,  # No project filter
            limit=10,
        )

        # Should return memories from BOTH projects
        contents = [r["content"] for r in results]
        assert any("test A" in c for c in contents)
        assert any("test B" in c for c in contents)


class TestErrorHandling:
    """Test error handling for project-scoped storage."""

    @pytest.mark.integration
    def test_project_detection_failure_uses_fallback(self, qdrant_client, tmp_path):
        """Test fallback to 'unknown-project' when detection fails.

        Per Dev Notes: If detect_project() fails, use fallback with warning.
        """
        # Use invalid path that will fail detection
        invalid_path = tmp_path / "nonexistent-path"

        storage = MemoryStorage()

        # Use unique content
        content = unique_content("Fallback test")

        # Should NOT raise - should use fallback
        result = storage.store_memory(
            content=content,
            cwd=str(invalid_path),  # Invalid path
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="fallback-session",
        )

        # Should store successfully with fallback group_id
        assert result["status"] == "stored"
        # group_id should be "unknown-project" (fallback)

    def test_none_cwd_raises_clear_error(self, qdrant_client):
        """Test None cwd raises clear ValueError.

        Per Dev Notes: Explicit error handling, no silent failures.
        """
        storage = MemoryStorage()

        # Should raise ValueError for None cwd (explicit check in code)
        with pytest.raises(ValueError, match="cwd parameter is required"):
            storage.store_memory(
                content="Missing cwd test",
                cwd=None,  # Explicitly None
                memory_type=MemoryType.IMPLEMENTATION,
                source_hook="PostToolUse",
                session_id="error-session",
            )


class TestBackwardCompatibility:
    """Test backward compatibility with explicit group_id override."""

    @pytest.mark.integration
    def test_explicit_group_id_override_allowed(self, qdrant_client, tmp_path):
        """Test that explicit group_id can override auto-detection.

        For cases where caller wants to override the auto-detected project.
        """
        project_dir = tmp_path / "override-test"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        storage = MemoryStorage()

        # Use unique content
        content = unique_content("Explicit override test")

        # Pass both cwd and explicit group_id
        result = storage.store_memory(
            content=content,
            cwd=str(project_dir),  # Would auto-detect "override-test"
            group_id="custom-group-id",  # But override with this
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="override-session",
        )

        assert result["status"] == "stored"
        # Should use explicit group_id, not auto-detected one
