"""Tests for memory event dataclasses (TECH-DEBT-111).

Provides coverage for src/memory/events.py CaptureEvent and RetrievalEvent
dataclasses which define type-safe event structures for memory operations.
"""

import pytest

from memory.events import CaptureEvent, RetrievalEvent


class TestCaptureEvent:
    """Tests for CaptureEvent dataclass."""

    def test_create_capture_event_minimal(self):
        """Test creating CaptureEvent with minimal required fields."""
        event = CaptureEvent(
            collection="code-patterns",
            type="implementation",
            content="test content",
            group_id="test-project",
        )
        assert event.collection == "code-patterns"
        assert event.type == "implementation"
        assert event.content == "test content"
        assert event.group_id == "test-project"

    def test_create_capture_event_full(self):
        """Test creating CaptureEvent with all fields."""
        event = CaptureEvent(
            collection="discussions",
            type="agent_response",
            content="def hello(): pass",
            group_id="my-project",
            session_id="session-123",
            tags=["python", "function"],
            metadata={"line": 42, "source_hook": "PostToolUse"},
        )
        assert event.session_id == "session-123"
        assert event.tags == ["python", "function"]
        assert event.metadata == {"line": 42, "source_hook": "PostToolUse"}

    def test_capture_event_defaults(self):
        """Test CaptureEvent default values."""
        event = CaptureEvent(
            collection="discussions",
            type="user_message",
            content="test",
            group_id="proj",
        )
        assert event.session_id is None
        assert event.tags is None
        # metadata defaults to empty dict via field(default_factory=dict)
        assert event.metadata == {}

    def test_capture_event_to_payload(self):
        """Test CaptureEvent.to_payload() method."""
        event = CaptureEvent(
            collection="code-patterns",
            type="implementation",
            content="test content",
            group_id="test-project",
            session_id="sess-456",
            tags=["tag1", "tag2"],
            metadata={"source_hook": "PostToolUse"},
        )
        payload = event.to_payload()

        assert payload["content"] == "test content"
        assert payload["type"] == "implementation"
        assert payload["group_id"] == "test-project"
        assert payload["session_id"] == "sess-456"
        assert payload["tags"] == ["tag1", "tag2"]
        assert payload["source_hook"] == "PostToolUse"

    def test_capture_event_to_payload_minimal(self):
        """Test to_payload() with minimal fields."""
        event = CaptureEvent(
            collection="discussions",
            type="agent_response",
            content="minimal",
            group_id="proj",
        )
        payload = event.to_payload()

        assert payload == {
            "content": "minimal",
            "type": "agent_response",
            "group_id": "proj",
        }

    def test_capture_event_validation_missing_collection(self):
        """Test validation rejects empty collection."""
        with pytest.raises(ValueError, match="collection is required"):
            CaptureEvent(
                collection="",
                type="implementation",
                content="test",
                group_id="proj",
            )

    def test_capture_event_validation_missing_type(self):
        """Test validation rejects empty type."""
        with pytest.raises(ValueError, match="type is required"):
            CaptureEvent(
                collection="discussions",
                type="",
                content="test",
                group_id="proj",
            )

    def test_capture_event_validation_missing_content(self):
        """Test validation rejects empty content."""
        with pytest.raises(ValueError, match="content is required"):
            CaptureEvent(
                collection="discussions",
                type="implementation",
                content="",
                group_id="proj",
            )

    def test_capture_event_validation_missing_group_id(self):
        """Test validation rejects empty group_id."""
        with pytest.raises(
            ValueError, match=r"group_id is required per architecture Section 7\.3"
        ):
            CaptureEvent(
                collection="discussions",
                type="implementation",
                content="test",
                group_id="",
            )


class TestRetrievalEvent:
    """Tests for RetrievalEvent dataclass."""

    def test_create_retrieval_event_minimal(self):
        """Test creating RetrievalEvent with minimal fields."""
        event = RetrievalEvent(
            query="fix error",
            collection="code-patterns",
        )
        assert event.query == "fix error"
        assert event.collection == "code-patterns"
        assert event.type_filter is None
        assert event.group_id == ""
        assert event.limit == 10

    def test_create_retrieval_event_full(self):
        """Test creating RetrievalEvent with all fields."""
        event = RetrievalEvent(
            query="previous session",
            collection="discussions",
            type_filter="session",
            group_id="my-project",
            limit=5,
        )
        assert event.type_filter == "session"
        assert event.group_id == "my-project"
        assert event.limit == 5

    def test_retrieval_event_to_filter_dict_with_group_id(self):
        """Test to_filter_dict() with group_id."""
        event = RetrievalEvent(
            query="test",
            collection="discussions",
            group_id="my-project",
        )
        filters = event.to_filter_dict()
        assert filters == {"group_id": "my-project"}

    def test_retrieval_event_to_filter_dict_with_type_filter(self):
        """Test to_filter_dict() with type_filter."""
        event = RetrievalEvent(
            query="test",
            collection="discussions",
            type_filter="implementation",
            group_id="proj",
        )
        filters = event.to_filter_dict()
        assert filters == {"group_id": "proj", "type": "implementation"}

    def test_retrieval_event_to_filter_dict_empty(self):
        """Test to_filter_dict() with no filters."""
        event = RetrievalEvent(
            query="test",
            collection="conventions",
        )
        filters = event.to_filter_dict()
        assert filters == {}

    def test_retrieval_event_validation_missing_query(self):
        """Test validation rejects empty query."""
        with pytest.raises(ValueError, match="query is required"):
            RetrievalEvent(
                query="",
                collection="discussions",
            )

    def test_retrieval_event_validation_missing_collection(self):
        """Test validation rejects empty collection."""
        with pytest.raises(ValueError, match="collection is required"):
            RetrievalEvent(
                query="test",
                collection="",
            )

    def test_retrieval_event_allows_empty_group_id(self):
        """Test that empty group_id is allowed (for shared collections)."""
        # Should not raise - empty group_id is valid for shared collections
        event = RetrievalEvent(
            query="test",
            collection="conventions",
            group_id="",
        )
        assert event.group_id == ""


class TestEventTypeCompliance:
    """Tests for type hint compliance."""

    def test_capture_event_tags_is_list(self):
        """Verify CaptureEvent tags is a list of strings."""
        event = CaptureEvent(
            collection="code-patterns",
            type="implementation",
            content="x",
            group_id="g",
            tags=["a", "b", "c"],
        )
        assert isinstance(event.tags, list)
        assert all(isinstance(t, str) for t in event.tags)

    def test_capture_event_metadata_is_dict(self):
        """Verify CaptureEvent metadata is a dict."""
        event = CaptureEvent(
            collection="discussions",
            type="agent_response",
            content="x",
            group_id="g",
            metadata={"key": "value", "count": 42},
        )
        assert isinstance(event.metadata, dict)

    def test_retrieval_event_limit_is_int(self):
        """Verify RetrievalEvent limit is an int."""
        event = RetrievalEvent(
            query="test",
            collection="discussions",
            limit=20,
        )
        assert isinstance(event.limit, int)
        assert event.limit == 20
