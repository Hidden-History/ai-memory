"""Tests for MemorySubagent pattern.

Comprehensive test suite covering:
- QueryContext dataclass
- MemorySource dataclass
- MemoryResult dataclass
- MemorySubagent query and store operations
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, patch, MagicMock

from src.memory.subagent import (
    MemorySubagent,
    MemoryResult,
    MemorySource,
    QueryContext,
    DEFAULT_LIMIT,
)
from src.memory.intent import IntentType


class TestQueryContext:
    """Tests for QueryContext dataclass."""

    def test_dataclass_fields(self):
        """QueryContext should have all expected fields."""
        context = QueryContext(
            current_file="/path/to/file.py",
            current_task="implement auth",
            session_id="sess-123",
            project_id="my-project"
        )
        assert context.current_file == "/path/to/file.py"
        assert context.current_task == "implement auth"
        assert context.session_id == "sess-123"
        assert context.project_id == "my-project"

    def test_all_fields_optional(self):
        """All QueryContext fields should be optional with None defaults."""
        context = QueryContext()
        assert context.current_file is None
        assert context.current_task is None
        assert context.session_id is None
        assert context.project_id is None


class TestMemorySource:
    """Tests for MemorySource dataclass."""

    def test_required_fields(self):
        """MemorySource should require collection and memory_type."""
        source = MemorySource(
            collection="code-patterns",
            memory_type="implementation"
        )
        assert source.collection == "code-patterns"
        assert source.memory_type == "implementation"

    def test_optional_fields_default(self):
        """Optional fields should have sensible defaults."""
        source = MemorySource(
            collection="code-patterns",
            memory_type="implementation"
        )
        assert source.file_path is None
        assert source.line_number is None
        assert source.score == 0.0


class TestMemoryResult:
    """Tests for MemoryResult dataclass."""

    def test_required_fields(self):
        """MemoryResult should require answer field."""
        result = MemoryResult(answer="Test answer")
        assert result.answer == "Test answer"

    def test_sources_default_empty_list(self):
        """Sources should default to empty list."""
        result = MemoryResult(answer="Test")
        assert result.sources == []
        assert isinstance(result.sources, list)

    def test_confidence_default_zero(self):
        """Confidence should default to 0.0."""
        result = MemoryResult(answer="Test")
        assert result.confidence == 0.0


class TestMemorySubagent:
    """Tests for MemorySubagent class."""

    def test_init_creates_search_client(self):
        """Subagent should create MemorySearch if not provided."""
        with patch("src.memory.subagent.MemorySearch") as MockSearch:
            subagent = MemorySubagent()
            MockSearch.assert_called_once()
            assert subagent.search is not None

    def test_init_accepts_custom_search_client(self):
        """Subagent should accept custom MemorySearch instance."""
        mock_search = Mock()
        subagent = MemorySubagent(search_client=mock_search)
        assert subagent.search is mock_search

    @pytest.mark.asyncio
    async def test_query_returns_memory_result(self):
        """Query should return MemoryResult instance."""
        mock_search = Mock()
        mock_search.search.return_value = []

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test question")

        assert isinstance(result, MemoryResult)
        assert result.answer is not None

    @pytest.mark.asyncio
    async def test_query_detects_how_intent(self):
        """Query should detect HOW intent and route to code-patterns."""
        mock_search = Mock()
        mock_search.search.return_value = []

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("how do I implement authentication?")

        assert result.intent_detected == "how"
        assert result.collection_searched == "code-patterns"
        mock_search.search.assert_called_once()
        call_args = mock_search.search.call_args
        assert call_args.kwargs["collection"] == "code-patterns"

    @pytest.mark.asyncio
    async def test_query_detects_what_intent(self):
        """Query should detect WHAT intent and route to conventions."""
        mock_search = Mock()
        mock_search.search.return_value = []

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("what port does Qdrant use?")

        assert result.intent_detected == "what"
        assert result.collection_searched == "conventions"
        call_args = mock_search.search.call_args
        assert call_args.kwargs["collection"] == "conventions"

    @pytest.mark.asyncio
    async def test_query_detects_why_intent(self):
        """Query should detect WHY intent and route to discussions."""
        mock_search = Mock()
        mock_search.search.return_value = []

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("why did we choose Qdrant?")

        assert result.intent_detected == "why"
        assert result.collection_searched == "discussions"
        call_args = mock_search.search.call_args
        assert call_args.kwargs["collection"] == "discussions"

    @pytest.mark.asyncio
    async def test_query_respects_collection_override(self):
        """Query should use explicit collection when provided."""
        mock_search = Mock()
        mock_search.search.return_value = []

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query(
            "how do I implement auth?",
            collection="conventions"  # Override detected intent
        )

        assert result.collection_searched == "conventions"
        call_args = mock_search.search.call_args
        assert call_args.kwargs["collection"] == "conventions"

    @pytest.mark.asyncio
    async def test_query_respects_limit(self):
        """Query should pass limit to search."""
        mock_search = Mock()
        mock_search.search.return_value = []

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test", limit=10)

        call_args = mock_search.search.call_args
        assert call_args.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_confidence_high_for_good_results(self):
        """Confidence should be high for multiple high-scoring results."""
        mock_search = Mock()
        mock_search.search.return_value = [
            {"score": 0.95, "content": "Result 1", "type": "implementation"},
            {"score": 0.92, "content": "Result 2", "type": "implementation"},
            {"score": 0.90, "content": "Result 3", "type": "implementation"},
        ]

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test")

        # Should be high confidence: avg_score * 0.7 + result_factor * 0.3
        # avg = 0.92, result_factor = 1.0 (3 results)
        # confidence = 0.92 * 0.7 + 1.0 * 0.3 = 0.644 + 0.3 = 0.944
        assert result.confidence > 0.9

    @pytest.mark.asyncio
    async def test_confidence_low_for_poor_results(self):
        """Confidence should be low for few low-scoring results."""
        mock_search = Mock()
        mock_search.search.return_value = [
            {"score": 0.3, "content": "Low relevance", "type": "implementation"},
        ]

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test")

        # avg = 0.3, result_factor = 0.33 (1 result)
        # confidence = 0.3 * 0.7 + 0.33 * 0.3 = 0.21 + 0.1 = 0.31
        assert result.confidence < 0.5

    @pytest.mark.asyncio
    async def test_format_answer_includes_content(self):
        """Formatted answer should include result content."""
        mock_search = Mock()
        mock_search.search.return_value = [
            {"score": 0.95, "content": "Implementation details here", "type": "implementation"},
        ]

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test")

        assert "Implementation details here" in result.answer
        assert "implementation" in result.answer
        assert "95%" in result.answer

    @pytest.mark.asyncio
    async def test_build_sources_extracts_metadata(self):
        """Sources should extract metadata from results."""
        mock_search = Mock()
        mock_search.search.return_value = [
            {
                "score": 0.95,
                "content": "Test",
                "type": "implementation",
                "file_path": "/src/auth.py"
            },
            {
                "score": 0.85,
                "content": "Test 2",
                "type": "error_fix",
                "file_path": None
            }
        ]

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test")

        assert len(result.sources) == 2
        assert result.sources[0].memory_type == "implementation"
        assert result.sources[0].file_path == "/src/auth.py"
        assert result.sources[0].score == 0.95
        assert result.sources[1].memory_type == "error_fix"
        assert result.sources[1].file_path is None

    @pytest.mark.asyncio
    @patch("src.memory.subagent.MemoryStorage")
    async def test_store_returns_memory_id(self, MockStorage):
        """Store should return memory ID on success."""
        mock_storage_instance = Mock()
        mock_storage_instance.store_memory.return_value = {
            "memory_id": "mem-123",
            "status": "stored",
            "embedding_status": "complete"
        }
        MockStorage.return_value = mock_storage_instance

        subagent = MemorySubagent()
        memory_id = await subagent.store(
            content="Test implementation",
            memory_type="implementation",
            tags=["auth", "security"],
            source="agent:dev"
        )

        assert memory_id == "mem-123"
        mock_storage_instance.store_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_context(self):
        """Query should use context for project scoping."""
        mock_search = Mock()
        mock_search.search.return_value = []

        context = QueryContext(
            current_file="/src/auth.py",
            project_id="my-project"
        )

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test", context=context)

        call_args = mock_search.search.call_args
        assert call_args.kwargs["group_id"] == "my-project"

    @pytest.mark.asyncio
    async def test_query_graceful_degradation_on_error(self):
        """Query should return empty result on search failure."""
        mock_search = Mock()
        mock_search.search.side_effect = Exception("Search failed")

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test")

        # Should not raise, should return graceful result
        assert isinstance(result, MemoryResult)
        assert result.confidence == 0.0
        assert result.sources == []
        assert "No relevant memories found" in result.answer

    @pytest.mark.asyncio
    async def test_query_empty_results(self):
        """Query should handle empty search results gracefully."""
        mock_search = Mock()
        mock_search.search.return_value = []

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test")

        assert result.confidence == 0.0
        assert result.sources == []
        assert "No relevant memories found" in result.answer

    @pytest.mark.asyncio
    @patch("src.memory.subagent.MemoryStorage")
    async def test_store_graceful_degradation_on_error(self, MockStorage):
        """Store should return empty string on failure."""
        mock_storage_instance = Mock()
        mock_storage_instance.store_memory.side_effect = Exception("Storage failed")
        MockStorage.return_value = mock_storage_instance

        subagent = MemorySubagent()
        memory_id = await subagent.store(
            content="Test",
            memory_type="implementation"
        )

        # Should not raise, should return empty string
        assert memory_id == ""

    @pytest.mark.asyncio
    async def test_query_populates_raw_results(self):
        """raw_results contains the full search results."""
        mock_search = Mock()
        mock_results = [
            {"content": "test1", "score": 0.9, "type": "implementation"},
            {"content": "test2", "score": 0.8, "type": "error_fix"},
        ]
        mock_search.search.return_value = mock_results

        subagent = MemorySubagent(search_client=mock_search)
        result = await subagent.query("test query")

        assert result.raw_results == mock_results
        assert len(result.raw_results) == 2
