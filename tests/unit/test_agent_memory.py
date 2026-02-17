"""Tests for SPEC-015: Parzival agent memory integration.

Tests cover:
- store_agent_memory() validation and routing
- agent_id search filter
- parzival_* config fields
- MemoryType enum additions
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestMemoryTypeEnum:
    """Test that 4 new agent MemoryType enum values exist."""

    def test_agent_handoff_exists(self):
        from memory.models import MemoryType

        assert MemoryType.AGENT_HANDOFF.value == "agent_handoff"

    def test_agent_memory_exists(self):
        from memory.models import MemoryType

        assert MemoryType.AGENT_MEMORY.value == "agent_memory"

    def test_agent_task_exists(self):
        from memory.models import MemoryType

        assert MemoryType.AGENT_TASK.value == "agent_task"

    def test_agent_insight_exists(self):
        from memory.models import MemoryType

        assert MemoryType.AGENT_INSIGHT.value == "agent_insight"

    def test_existing_types_unchanged(self):
        """Existing enum values are not broken by additions."""
        from memory.models import MemoryType

        assert MemoryType.IMPLEMENTATION.value == "implementation"
        assert MemoryType.DECISION.value == "decision"
        assert MemoryType.GITHUB_PR.value == "github_pr"

    def test_total_enum_count(self):
        """30 total types (26 original + 4 agent)."""
        from memory.models import MemoryType

        assert len(MemoryType) == 30


class TestParzivalConfig:
    """Test 6 parzival_* config fields."""

    def test_parzival_config_defaults(self):
        """All parzival fields have correct defaults."""
        from memory.config import MemoryConfig, reset_config

        reset_config()
        config = MemoryConfig()
        assert config.parzival_enabled is False
        assert config.parzival_user_name == "Developer"
        assert config.parzival_language == "English"
        assert config.parzival_doc_language == "English"
        assert config.parzival_oversight_folder == "oversight"
        assert config.parzival_handoff_retention == 10

    def test_parzival_config_from_env(self, monkeypatch):
        """Config reads from environment variables."""
        from memory.config import MemoryConfig, reset_config

        reset_config()
        monkeypatch.setenv("PARZIVAL_ENABLED", "true")
        monkeypatch.setenv("PARZIVAL_USER_NAME", "Alice")
        monkeypatch.setenv("PARZIVAL_LANGUAGE", "Spanish")
        monkeypatch.setenv("PARZIVAL_DOC_LANGUAGE", "French")
        monkeypatch.setenv("PARZIVAL_OVERSIGHT_FOLDER", "my-oversight")
        monkeypatch.setenv("PARZIVAL_HANDOFF_RETENTION", "5")
        config = MemoryConfig()
        assert config.parzival_enabled is True
        assert config.parzival_user_name == "Alice"
        assert config.parzival_language == "Spanish"
        assert config.parzival_doc_language == "French"
        assert config.parzival_oversight_folder == "my-oversight"
        assert config.parzival_handoff_retention == 5
        reset_config()

    def test_parzival_handoff_retention_minimum(self):
        """Handoff retention must be >= 1."""
        from memory.config import MemoryConfig, reset_config

        reset_config()
        with pytest.raises(ValueError):
            MemoryConfig(parzival_handoff_retention=0)
        reset_config()


class TestStoreAgentMemory:
    """Test store_agent_memory() method."""

    def test_invalid_type_raises_value_error(self):
        """Invalid memory type raises ValueError."""
        from memory.storage import MemoryStorage

        storage = MagicMock(spec=MemoryStorage)
        storage.store_agent_memory = MemoryStorage.store_agent_memory.__get__(storage)

        with pytest.raises(ValueError, match="Invalid agent memory type"):
            storage.store_agent_memory(
                content="test content for agent",
                memory_type="invalid_type",
                cwd="/tmp/test",
            )

    def test_no_group_or_cwd_raises_value_error(self):
        """Neither group_id nor cwd raises ValueError."""
        from memory.storage import MemoryStorage

        storage = MagicMock(spec=MemoryStorage)
        storage.store_agent_memory = MemoryStorage.store_agent_memory.__get__(storage)

        with pytest.raises(ValueError, match="Either group_id or cwd"):
            storage.store_agent_memory(
                content="test content for agent",
                memory_type="agent_memory",
            )

    def test_valid_types_accepted(self):
        """All 4 agent types are accepted (no ValueError)."""
        from memory.storage import MemoryStorage

        storage = MagicMock(spec=MemoryStorage)
        storage.store_agent_memory = MemoryStorage.store_agent_memory.__get__(storage)
        storage.store_memory = MagicMock(
            return_value={
                "status": "stored",
                "memory_id": "test-id",
                "embedding_status": "complete",
            }
        )

        for mtype in ["agent_handoff", "agent_memory", "agent_task", "agent_insight"]:
            result = storage.store_agent_memory(
                content=f"Test {mtype} content that is long enough",
                memory_type=mtype,
                agent_id="parzival",
                cwd="/tmp/test-project",
            )
            assert result["status"] == "stored"

    def test_delegates_to_store_memory(self):
        """store_agent_memory delegates to store_memory."""
        from memory.config import COLLECTION_DISCUSSIONS
        from memory.storage import MemoryStorage

        storage = MagicMock(spec=MemoryStorage)
        storage.store_agent_memory = MemoryStorage.store_agent_memory.__get__(storage)
        storage.store_memory = MagicMock(
            return_value={
                "status": "stored",
                "memory_id": "abc",
                "embedding_status": "complete",
            }
        )

        storage.store_agent_memory(
            content="Test handoff content for delegation check",
            memory_type="agent_handoff",
            agent_id="parzival",
            cwd="/tmp/test",
        )

        storage.store_memory.assert_called_once()
        call_kwargs = storage.store_memory.call_args
        assert (
            call_kwargs.kwargs.get("collection") == COLLECTION_DISCUSSIONS
            or call_kwargs[1].get("collection") == COLLECTION_DISCUSSIONS
        )
        # Check source_hook is parzival_agent
        assert "parzival_agent" in str(call_kwargs)

    def test_agent_id_in_extra_fields(self):
        """agent_id is passed to store_memory via extra fields."""
        from memory.storage import MemoryStorage

        storage = MagicMock(spec=MemoryStorage)
        storage.store_agent_memory = MemoryStorage.store_agent_memory.__get__(storage)
        storage.store_memory = MagicMock(
            return_value={
                "status": "stored",
                "memory_id": "abc",
                "embedding_status": "complete",
            }
        )

        storage.store_agent_memory(
            content="Test content with agent_id field",
            memory_type="agent_insight",
            agent_id="parzival",
            cwd="/tmp/test",
        )

        call_kwargs = storage.store_memory.call_args
        # agent_id should be in the keyword args (passed via **extra_fields)
        assert call_kwargs[1].get("agent_id") == "parzival"

    def test_default_session_id(self):
        """Default session_id is f'agent_{agent_id}'."""
        from memory.storage import MemoryStorage

        storage = MagicMock(spec=MemoryStorage)
        storage.store_agent_memory = MemoryStorage.store_agent_memory.__get__(storage)
        storage.store_memory = MagicMock(
            return_value={
                "status": "stored",
                "memory_id": "abc",
                "embedding_status": "complete",
            }
        )

        storage.store_agent_memory(
            content="Test content for session id check",
            memory_type="agent_memory",
            cwd="/tmp/test",
        )

        call_kwargs = storage.store_memory.call_args
        assert call_kwargs[1].get("session_id") == "agent_parzival"

    def test_custom_session_id(self):
        """Custom session_id overrides default."""
        from memory.storage import MemoryStorage

        storage = MagicMock(spec=MemoryStorage)
        storage.store_agent_memory = MemoryStorage.store_agent_memory.__get__(storage)
        storage.store_memory = MagicMock(
            return_value={
                "status": "stored",
                "memory_id": "abc",
                "embedding_status": "complete",
            }
        )

        storage.store_agent_memory(
            content="Test content with custom session id",
            memory_type="agent_memory",
            session_id="custom-session",
            cwd="/tmp/test",
        )

        call_kwargs = storage.store_memory.call_args
        assert call_kwargs[1].get("session_id") == "custom-session"

    def test_metadata_merged_into_extra_fields(self):
        """Metadata dict is merged into extra_fields."""
        from memory.storage import MemoryStorage

        storage = MagicMock(spec=MemoryStorage)
        storage.store_agent_memory = MemoryStorage.store_agent_memory.__get__(storage)
        storage.store_memory = MagicMock(
            return_value={
                "status": "stored",
                "memory_id": "abc",
                "embedding_status": "complete",
            }
        )

        storage.store_agent_memory(
            content="Test with metadata for extra fields",
            memory_type="agent_task",
            cwd="/tmp/test",
            metadata={"task_id": "TASK-001", "priority": "high"},
        )

        call_kwargs = storage.store_memory.call_args
        assert call_kwargs[1].get("task_id") == "TASK-001"
        assert call_kwargs[1].get("priority") == "high"


class TestSearchAgentIdFilter:
    """Test agent_id filter in search."""

    def test_search_accepts_agent_id_parameter(self):
        """MemorySearch.search() accepts agent_id parameter without error."""
        # Just verify the method signature accepts agent_id
        import inspect

        from memory.search import MemorySearch

        sig = inspect.signature(MemorySearch.search)
        assert "agent_id" in sig.parameters

    def test_agent_id_default_is_none(self):
        """agent_id defaults to None (backwards compatible)."""
        import inspect

        from memory.search import MemorySearch

        sig = inspect.signature(MemorySearch.search)
        assert sig.parameters["agent_id"].default is None


class TestValidationHook:
    """Test parzival_agent in validation whitelist."""

    def test_parzival_agent_is_valid_hook(self):
        """parzival_agent is accepted as a valid source_hook."""
        from memory.validation import validate_payload

        payload = {
            "content": "Test content for parzival agent hook validation",
            "group_id": "test-project",
            "type": "agent_memory",
            "source_hook": "parzival_agent",
            "session_id": "test-session",
            "content_hash": "abc123",
            "timestamp": "2026-02-16T00:00:00Z",
        }
        errors = validate_payload(payload)
        assert not any("source_hook" in e for e in errors)

    def test_existing_hooks_still_valid(self):
        """Existing hooks are not broken."""
        from memory.validation import validate_payload

        for hook in ["PostToolUse", "Stop", "manual", "jira_sync"]:
            payload = {
                "content": "Test content for existing hook validation",
                "group_id": "test-project",
                "type": "implementation",
                "source_hook": hook,
            }
            errors = validate_payload(payload)
            assert not any(
                "source_hook" in e for e in errors
            ), f"Hook {hook} should be valid"


class TestContentTypeMap:
    """Test that agent types are in content_type_map."""

    def test_agent_types_have_content_type_mapping(self):
        """All 4 agent types must be in content_type_map for chunking to work."""
        import inspect

        from memory import storage

        # Verify content_type_map in storage.py actually maps all 4 agent types
        # to the correct ContentType values — fails if any entry is removed
        source = inspect.getsource(storage)
        expected_entries = [
            ("MemoryType.AGENT_HANDOFF", "ContentType.AGENT_RESPONSE"),
            ("MemoryType.AGENT_MEMORY", "ContentType.PROSE"),
            ("MemoryType.AGENT_TASK", "ContentType.PROSE"),
            ("MemoryType.AGENT_INSIGHT", "ContentType.PROSE"),
        ]
        for mem_type_str, content_type_str in expected_entries:
            assert (
                mem_type_str in source
            ), f"{mem_type_str} missing from content_type_map in storage.py"
            # Also confirm the paired ContentType value appears adjacent in source
            idx = source.find(mem_type_str)
            nearby = source[idx : idx + 60]
            assert (
                content_type_str in nearby
            ), f"{mem_type_str} is not mapped to {content_type_str} in storage.py"
