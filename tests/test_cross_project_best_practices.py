"""Tests for project-scoped best practices storage and retrieval (PLAN-028 P1).

Implements AC 4.3.3 (Project-Scoped Verification) with coverage for:
- Best practices stored under a real project group_id (not "shared")
- Retrieval filtered by project group_id (like other collections)
- Collection isolation (conventions vs code-patterns)
- Backward-compatible None group_id behavior in search()

PLAN-028 P1 (W-01): FR16 amended — conventions is project-scoped.
The pre-P1 "shared" group_id marker is removed; best practices store and
retrieve under the caller's project group_id like code-patterns/discussions.
"""

import pytest
from conftest import wait_for_condition

from src.memory.models import MemoryType
from src.memory.search import MemorySearch, retrieve_best_practices
from src.memory.storage import store_best_practice

# Every test in this module takes the live `qdrant_client` fixture, which writes
# on setup. TD-881: they carried no marker at all, so neither the integration
# gate (which keys on the `integration` keyword or an /integration/ path segment)
# nor `-m "not quarantine"` ever deselected them, and a plain `pytest tests/`
# ran all 13 against the operator's real collections.
pytestmark = pytest.mark.integration


class TestBestPracticesProjectScoped:
    """Test project-scoped storage and retrieval of best practices (AC 4.3.3)."""

    def test_store_best_practice_uses_project_group_id(self, qdrant_client):
        """Test that store_best_practice stores under the caller's project group_id.

        PLAN-028 P1 — Rescope from "shared" to project-scoped (W-01).

        Given: A best practice stored with explicit group_id
        Then: group_id in result matches the provided group_id (not "shared")
        """
        result = store_best_practice(
            content="Always use type hints in Python 3.10+ for better IDE support",
            session_id="proj-a-session",
            source_hook="PostToolUse",
            group_id="project-a",
        )

        assert result["status"] in ["stored", "duplicate"]
        assert result["collection"] == "conventions"
        assert (
            result["group_id"] != "shared"
        ), "group_id must not be the old 'shared' sentinel"
        assert "memory_id" in result

    def test_store_best_practice_explicit_group_id_preserved(self, qdrant_client):
        """Test that an explicit group_id is preserved through storage.

        Given: store_best_practice called with group_id="my-project"
        Then: result["group_id"] == "my-project"
        """
        result = store_best_practice(
            content="Use explicit dependency injection to improve testability",
            session_id="test-session",
            source_hook="manual",
            group_id="my-project",
        )

        assert result["status"] in ["stored", "duplicate"]
        assert result["group_id"] == "my-project"
        assert result["collection"] == "conventions"

    def test_retrieve_best_practices_with_project_filter(self, qdrant_client):
        """Test retrieval respects the project group_id filter.

        PLAN-028 P1 — project-scoped retrieval (W-01).

        Given: A best practice stored under "proj-retrieve"
        When: retrieve_best_practices is called with group_id="proj-retrieve"
        Then: Results contain the stored best practice
        """
        store_best_practice(
            content="Document public APIs with comprehensive docstrings for maintainability",
            session_id="test-session",
            source_hook="manual",
            group_id="proj-retrieve",
        )

        def doc_bp_indexed() -> bool:
            results = retrieve_best_practices(
                query="API documentation docstrings",
                limit=5,
                group_id="proj-retrieve",
            )
            return any("docstrings" in r.get("content", "").lower() for r in results)

        wait_for_condition(doc_bp_indexed, timeout=10.0, message="Doc BP not indexed")

        results = retrieve_best_practices(
            query="API documentation best practice",
            limit=5,
            group_id="proj-retrieve",
        )

        assert len(results) > 0
        for result in results:
            assert result["collection"] == "conventions"
            assert "score" in result
            assert "content" in result
            # group_id must be a real project ID, not the old "shared" sentinel
            assert result["group_id"] != "shared"

    def test_best_practices_project_isolation(self, qdrant_client):
        """Test that best practices stored under project-a are not returned for project-b.

        PLAN-028 P1 — isolation is now enforced for conventions (W-01).

        Given: A best practice stored under "isolation-proj-a"
        When: retrieve_best_practices is called with group_id="isolation-proj-b"
        Then: The project-a best practice is NOT returned
        """
        unique_marker = "proj-a-specific-unique-marker-iso-xyz-2026"
        store_best_practice(
            content=f"Best practice for project A only: {unique_marker}",
            session_id="session-a",
            source_hook="manual",
            group_id="isolation-proj-a",
        )

        # Wait briefly for indexing
        def stored_in_a() -> bool:
            results = retrieve_best_practices(
                query=unique_marker,
                limit=5,
                group_id="isolation-proj-a",
            )
            return any(unique_marker in r.get("content", "") for r in results)

        wait_for_condition(
            stored_in_a, timeout=10.0, message="BP not indexed in proj-a"
        )

        # Retrieve from project-b — should NOT find project-a's best practice
        results_b = retrieve_best_practices(
            query=unique_marker,
            limit=5,
            group_id="isolation-proj-b",
        )
        found_in_b = any(unique_marker in r.get("content", "") for r in results_b)
        assert (
            not found_in_b
        ), "Project-a best practice must not appear in project-b results"

    def test_best_practices_not_in_code_patterns_collection(self, qdrant_client):
        """Test that best practices don't leak into the code-patterns collection.

        Implements AC 4.3.3 (Collection Isolation Verification).

        Given: A best practice stored in conventions
        When: I search the code-patterns collection
        Then: Best practice is NOT returned (collection isolation)
        """
        store_best_practice(
            content="Best practice: Mock external APIs in tests to improve reliability",
            session_id="session-1",
            source_hook="manual",
            group_id="isolation-col-test",
        )

        def mock_bp_indexed() -> bool:
            results = retrieve_best_practices(
                query="mock external APIs",
                limit=5,
                group_id="isolation-col-test",
            )
            return any("Mock" in r.get("content", "") for r in results)

        wait_for_condition(mock_bp_indexed, timeout=10.0, message="Mock BP not indexed")

        search = MemorySearch()
        impl_results = search.search(
            query="mock external APIs",
            collection="code-patterns",
            group_id="isolation-col-test",
        )

        assert not any("Best practice:" in r.get("content", "") for r in impl_results)

    def test_implementations_not_in_best_practices_collection(
        self, qdrant_client, tmp_path
    ):
        """Test that code-patterns don't leak into the conventions collection.

        Implements AC 4.3.3 (Collection Isolation Verification).

        Given: An implementation stored in code-patterns for "col-proj-a"
        When: I search conventions with group_id="col-proj-a"
        Then: Implementation is NOT returned
        """
        from src.memory.storage import MemoryStorage

        storage = MemoryStorage()
        storage.store_memory(
            content="Implemented OAuth2 login flow using FastAPI for col-proj-a",
            cwd=str(tmp_path),
            group_id="col-proj-a",
            collection="code-patterns",
            memory_type=MemoryType.IMPLEMENTATION,
            session_id="session-2",
            source_hook="PostToolUse",
        )

        def implementation_indexed() -> bool:
            search_impl = MemorySearch()
            results = search_impl.search(
                query="OAuth2 login",
                collection="code-patterns",
                group_id="col-proj-a",
                limit=1,
            )
            return len(results) > 0

        wait_for_condition(
            implementation_indexed, timeout=10.0, message="Implementation not indexed"
        )

        bp_results = retrieve_best_practices(
            query="OAuth2 login implementation",
            limit=5,
            group_id="col-proj-a",
        )

        assert not any("col-proj-a" in r.get("content", "").lower() for r in bp_results)

    def test_best_practices_query_performance(self, qdrant_client):
        """Verify project-scoped best practice queries meet performance requirements.

        Implements AC 4.3.3 (Performance Verification).

        Given: Best practices stored for "perf-test-proj"
        When: I query retrieve_best_practices with that group_id
        Then: Query completes in <500ms and returns results
        """
        for i in range(10):
            store_best_practice(
                content=f"Best practice {i}: Universal coding pattern #{i} for maintainability",
                session_id=f"session-{i}",
                source_hook="manual",
                group_id="perf-test-proj",
            )

        def entries_indexed() -> bool:
            results = retrieve_best_practices(
                query="coding pattern",
                limit=5,
                group_id="perf-test-proj",
            )
            return len(results) >= 3

        wait_for_condition(
            entries_indexed,
            timeout=15.0,
            message="Performance test entries not indexed",
        )

        import time as time_module

        start = time_module.time()
        results = retrieve_best_practices(
            query="coding pattern best practice",
            limit=5,
            group_id="perf-test-proj",
        )
        elapsed_ms = (time_module.time() - start) * 1000

        assert elapsed_ms < 500, f"Query took {elapsed_ms:.0f}ms, expected <500ms"
        assert len(results) > 0, "Should return at least some results"
        assert all(r["collection"] == "conventions" for r in results)


class TestBestPracticesStorage:
    """Test store_best_practice() function (AC 4.3.1)."""

    def test_store_best_practice_basic(self, qdrant_client):
        """Test basic best practice storage with project-scoped group_id.

        Implements AC 4.3.1 (Best Practices Storage).

        Given: Valid best practice content with explicit group_id
        Then: Memory is stored, group_id is the project value, collection is "conventions"
        """
        result = store_best_practice(
            content="Always validate user input before processing to prevent injection attacks",
            session_id="test-session",
            source_hook="manual",
            domain="security",
            group_id="store-basic-proj",
        )

        assert result["status"] in ["stored", "duplicate"]
        assert result["group_id"] == "store-basic-proj"
        assert result["collection"] == "conventions"
        assert "memory_id" in result
        assert result["embedding_status"] in ["complete", "pending", "n/a"]

    def test_store_best_practice_with_metadata(self, qdrant_client):
        """Test best practice storage with additional metadata.

        Implements AC 4.3.1 (Best Practices Storage with Metadata).
        """
        result = store_best_practice(
            content="Use environment variables for configuration to avoid hardcoding secrets",
            session_id="test-session-2",
            source_hook="PostToolUse",
            domain="devops",
            tags=["security", "configuration"],
            group_id="metadata-test-proj",
        )

        assert result["status"] in ["stored", "duplicate"]
        assert result["group_id"] == "metadata-test-proj"
        assert result["collection"] == "conventions"

    def test_store_best_practice_group_id_not_shared(self, qdrant_client):
        """Test that store_best_practice never uses the 'shared' sentinel.

        PLAN-028 P1 regression guard: 'shared' group_id was the pre-P1 marker.
        """
        result = store_best_practice(
            content="Prefer composition over inheritance for flexible design",
            session_id="test-session-3",
            source_hook="manual",
            group_id="regression-guard-proj",
        )

        assert result["group_id"] != "shared", (
            "store_best_practice must not use the old 'shared' group_id sentinel "
            "(PLAN-028 P1 regression)"
        )


class TestBestPracticesRetrieval:
    """Test retrieve_best_practices() function (AC 4.3.2)."""

    def test_retrieve_best_practices_basic(self, qdrant_client):
        """Test basic best practice retrieval with project filter.

        Implements AC 4.3.2 (Best Practices Retrieval).

        Given: Best practices stored under "retrieval-basic-proj"
        When: retrieve_best_practices called with that group_id
        Then: Results are project-scoped and properly structured
        """
        store_best_practice(
            content="Document public APIs with comprehensive docstrings",
            session_id="test-session",
            source_hook="manual",
            group_id="retrieval-basic-proj",
        )

        def doc_bp_indexed() -> bool:
            results = retrieve_best_practices(
                query="API documentation",
                limit=3,
                group_id="retrieval-basic-proj",
            )
            return any("docstrings" in r.get("content", "").lower() for r in results)

        wait_for_condition(doc_bp_indexed, timeout=10.0, message="Doc BP not indexed")

        results = retrieve_best_practices(
            query="API documentation best practice",
            limit=3,
            group_id="retrieval-basic-proj",
        )

        assert len(results) <= 3
        for result in results:
            assert result["collection"] == "conventions"
            assert "score" in result
            assert "content" in result
            assert result["group_id"] != "shared"

    def test_retrieve_best_practices_default_limit(self, qdrant_client):
        """Test that retrieve_best_practices() respects default limit=3.

        Implements AC 4.3.2 (Context Efficiency).
        """
        for i in range(10):
            store_best_practice(
                content=f"Best practice {i}: Python pattern for efficiency",
                session_id=f"session-{i}",
                source_hook="manual",
                group_id="default-limit-proj",
            )

        def python_bp_indexed() -> bool:
            results = retrieve_best_practices(
                query="Python pattern",
                limit=3,
                group_id="default-limit-proj",
            )
            return len(results) >= 1

        wait_for_condition(
            python_bp_indexed, timeout=10.0, message="Python pattern BPs not indexed"
        )

        results = retrieve_best_practices(
            query="Python pattern efficiency",
            group_id="default-limit-proj",
        )

        assert len(results) <= 3

    def test_retrieve_best_practices_empty_result(self, qdrant_client):
        """Test retrieval returns empty list when no match for project.

        Implements AC 4.3.2 (Edge Case Handling).
        """
        results = retrieve_best_practices(
            query="nonexistent best practice query that won't match anything",
            limit=5,
            group_id="nonexistent-project-xyz",
        )

        assert isinstance(results, list)
        assert len(results) == 0
