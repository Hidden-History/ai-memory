"""Unit tests for session_start.py hook.

Tests V2.0 context injection behavior for compact/resume events.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# Import fixtures
sys.path.insert(0, "tests")
from mocks.qdrant_mock import MockQdrantClient

# Add hook scripts to path
sys.path.insert(0, ".claude/hooks/scripts")


@pytest.fixture
def compact_event():
    """Load compact event fixture."""
    with open("tests/fixtures/hooks/session_start_compact.json") as f:
        return json.load(f)


@pytest.fixture
def resume_event():
    """Load resume event fixture."""
    with open("tests/fixtures/hooks/session_start_resume.json") as f:
        return json.load(f)


@pytest.fixture
def mock_qdrant():
    """Provide fresh mock Qdrant client for each test."""
    client = MockQdrantClient()
    client.reset()  # Ensure clean state
    return client


@pytest.fixture
def mock_config():
    """Provide mock MemoryConfig."""
    config = MagicMock()
    config.qdrant_host = "localhost"
    config.qdrant_port = 26350
    config.project_name = "ai-memory-module"
    return config


class TestSessionStartHook:
    """Test suite for session_start.py hook."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Reset module state before each test."""
        # Clear any cached imports
        if "session_start" in sys.modules:
            del sys.modules["session_start"]
        yield
        # Cleanup after test
        if "session_start" in sys.modules:
            del sys.modules["session_start"]

    def test_compact_event_retrieves_context(
        self, compact_event, mock_qdrant, mock_config
    ):
        """Test that compact event triggers context injection.

        V2.0 behavior: On compact, retrieve conversation context from discussions
        collection (session summaries) and inject into Claude's context window.
        """
        from qdrant_client.models import PointStruct

        # Setup mock data: session summary with rich context
        session_id = compact_event["session_id"]
        session_summary = [
            PointStruct(
                id="session-1",
                vector=[0.1, 0.2, 0.3],
                payload={
                    "content": "Implemented error handling and logging in storage module",
                    "type": "session",
                    "session_id": session_id,
                    "group_id": "ai-memory-module",
                    "created_at": "2026-01-21T10:00:00Z",
                    "first_user_prompt": "Add error handling to the storage module",
                    "last_user_prompts": [
                        {"content": "Add error handling to the storage module"},
                        {"content": "Great, also add logging for failed operations"},
                    ],
                    "last_agent_responses": [
                        {
                            "content": "I'll add comprehensive error handling with graceful degradation to the storage module."
                        }
                    ],
                    "session_metadata": {},
                },
            )
        ]

        # Insert into mock client
        mock_qdrant.upsert("discussions", points=session_summary)

        # Import the function to test
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            # Import after patching
            from session_start import get_conversation_context

            # Call the function
            context = get_conversation_context(
                config=mock_config,
                session_id=session_id,
                project_name="ai-memory-module",
                limit=5,
            )

            # Verify context includes summary
            assert "Implemented error handling and logging" in context
            # Verify context includes user messages from summary
            assert "Add error handling to the storage module" in context
            assert "also add logging" in context
            # Verify context includes agent responses from summary
            assert "error handling with graceful degradation" in context
            # Verify section headers exist
            assert "## Session Summaries" in context
            assert "## Recent User Messages" in context
            assert "## Agent Context Summary" in context

    def test_resume_event_loads_session(self, resume_event, mock_qdrant, mock_config):
        """Test that resume event triggers session context loading.

        V2.0 behavior: On resume, load conversation context from the
        discussions collection (session summaries) to restore session state.
        """
        from qdrant_client.models import PointStruct

        session_id = resume_event["session_id"]

        # Setup minimal session summary
        points = [
            PointStruct(
                id="session-1",
                vector=[0.1, 0.2, 0.3],
                payload={
                    "content": "Implemented search functionality",
                    "type": "session",
                    "session_id": session_id,
                    "group_id": "ai-memory-module",
                    "created_at": "2026-01-21T09:00:00Z",
                    "first_user_prompt": "Implement the search functionality",
                    "last_user_prompts": [
                        {"content": "Implement the search functionality"}
                    ],
                    "last_agent_responses": [],
                    "session_metadata": {},
                },
            )
        ]

        mock_qdrant.upsert("discussions", points=points)

        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import get_conversation_context

            context = get_conversation_context(
                config=mock_config,
                session_id=session_id,
                project_name="ai-memory-module",
                limit=5,
            )

            # Verify resume loads user message from summary
            assert "Implement the search functionality" in context

    def test_empty_transcript_handles_gracefully(self, mock_qdrant, mock_config):
        """Test that empty conversation history returns empty context.

        Graceful degradation: If no conversation data exists, return empty string
        and let Claude continue without context injection.
        """
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import get_conversation_context

            # Call with session that has no data
            context = get_conversation_context(
                config=mock_config,
                session_id="nonexistent_session",
                project_name="ai-memory-module",
                limit=5,
            )

            # Verify empty context returned
            assert context == ""

    def test_user_message_soft_cap(self, mock_qdrant, mock_config):
        """Test that user messages respect 2000 char soft cap.

        V2.0: User prompts from session summaries truncated at 2000 chars
        using smart_truncate to prevent context explosion.
        """
        from qdrant_client.models import PointStruct

        session_id = "test_session_long_message"

        # Create a session summary with long user prompt (exceeding 2000 chars)
        long_content = "This is a very long user prompt. " * 100  # ~3400 chars

        points = [
            PointStruct(
                id="session-long",
                vector=[0.1, 0.2, 0.3],
                payload={
                    "content": "Session with long user prompt",
                    "type": "session",
                    "session_id": session_id,
                    "group_id": "ai-memory-module",
                    "created_at": "2026-01-21T10:00:00Z",
                    "first_user_prompt": "Long prompt",
                    "last_user_prompts": [{"content": long_content}],
                    "last_agent_responses": [],
                    "session_metadata": {},
                },
            )
        ]

        mock_qdrant.upsert("discussions", points=points)

        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import get_conversation_context

            context = get_conversation_context(
                config=mock_config,
                session_id=session_id,
                project_name="ai-memory-module",
                limit=5,
            )

            # Verify smart_truncate marker present (adds "...")
            assert "..." in context
            # Verify content is truncated (2000 char limit + headers/formatting)
            assert len(context) < 2500  # Generous margin for headers and formatting

    def test_agent_response_condensed(self, mock_qdrant, mock_config):
        """Test that agent responses are condensed to 500 chars.

        V2.0: Agent responses from session summaries truncated at 500 chars
        using smart_truncate for brevity.
        """
        from qdrant_client.models import PointStruct

        session_id = "test_session_long_response"

        # Create session summary with long agent response (exceeding 500 chars)
        long_response = "I've implemented the feature. " * 50  # ~1500 chars

        points = [
            PointStruct(
                id="session-long-agent",
                vector=[0.1, 0.2, 0.3],
                payload={
                    "content": "Session with long agent response",
                    "type": "session",
                    "session_id": session_id,
                    "group_id": "ai-memory-module",
                    "created_at": "2026-01-21T10:02:00Z",
                    "first_user_prompt": "Implement feature",
                    "last_user_prompts": [],
                    "last_agent_responses": [{"content": long_response}],
                    "session_metadata": {},
                },
            )
        ]

        mock_qdrant.upsert("discussions", points=points)

        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import get_conversation_context

            context = get_conversation_context(
                config=mock_config,
                session_id=session_id,
                project_name="ai-memory-module",
                limit=5,
            )

            # Verify smart_truncate marker for agent response (adds "...")
            assert "..." in context
            # Verify agent content is limited
            # Extract just the agent response section (rough check)
            if "## Agent Context Summary" in context:
                agent_section = context.split("## Agent Context Summary")[1]
                # Should be condensed to ~500 chars + formatting
                assert len(agent_section) < 1000  # Generous margin

    def test_qdrant_unavailable_graceful_degradation(self, mock_config):
        """Test graceful degradation when Qdrant is unavailable.

        Should return empty context and log warning, not crash.
        """
        # Mock Qdrant client that raises exception
        failing_client = MagicMock()
        failing_client.scroll.side_effect = Exception("Connection refused")

        with (
            patch(
                "memory.qdrant_client.get_qdrant_client", return_value=failing_client
            ),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import get_conversation_context

            # Should not raise, should return empty
            context = get_conversation_context(
                config=mock_config,
                session_id="test_session",
                project_name="ai-memory-module",
                limit=5,
            )

            assert context == ""

    def test_priority_injection_session_summaries_first(self, mock_qdrant, mock_config):
        """Test TECH-DEBT-047: Session summaries get priority over other memories.

        Priority allocation:
        - 60% of token budget for session summaries (highest priority)
        - 40% of token budget for other memories (decisions, patterns, conventions)
        """

        # Setup session summaries (should get 60% of budget = 1200 tokens)
        session_summaries = [
            {
                "content": "Implemented error handling with graceful degradation in storage.py",
                "timestamp": "2026-01-21T10:00:00Z",
                "type": "session",
                "first_user_prompt": "Add error handling",
                "last_user_prompts": [],
                "last_agent_responses": [],
                "session_metadata": {},
            },
            {
                "content": "Added structured logging to all modules per Story 6.2",
                "timestamp": "2026-01-21T09:00:00Z",
                "type": "session",
                "first_user_prompt": "Add logging",
                "last_user_prompts": [],
                "last_agent_responses": [],
                "session_metadata": {},
            },
        ]

        # Setup other memories (should get 40% of budget = 800 tokens)
        other_memories = [
            {
                "content": "Decision: Use Qdrant for vector storage (DEC-001)",
                "type": "decision",
                "collection": "discussions",
                "score": 0.85,
            },
            {
                "content": "Pattern: Always apply filter_low_value_content before injection",
                "type": "implementation",
                "collection": "code-patterns",
                "score": 0.90,
            },
        ]

        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import inject_with_priority

            # Set token budget to 2000 (60% = 1200, 40% = 800)
            mock_config.token_budget = 2000

            result = inject_with_priority(
                session_summaries=session_summaries,
                other_memories=other_memories,
                token_budget=2000,
            )

            # Verify session summaries appear first
            assert (
                result.find("error handling") < result.find("Decision: Use Qdrant")
                or "Decision: Use Qdrant" not in result
            )
            assert (
                result.find("structured logging") < result.find("Pattern: Always apply")
                or "Pattern: Always apply" not in result
            )

            # Verify both session summaries included (they fit in 60% budget)
            assert "error handling" in result
            assert "structured logging" in result

            # Verify at least one other memory included (fits in 40% budget)
            assert "Decision: Use Qdrant" in result or "Pattern: Always apply" in result

    def test_priority_injection_respects_token_budget(self, mock_qdrant, mock_config):
        """Test TECH-DEBT-047: Priority injection respects total token budget."""
        # Create many large session summaries that exceed budget
        session_summaries = [
            {
                "content": "A" * 800,  # ~200 tokens
                "timestamp": f"2026-01-21T10:0{i}:00Z",
                "type": "session",
                "first_user_prompt": f"Task {i}",
                "last_user_prompts": [],
                "last_agent_responses": [],
                "session_metadata": {},
            }
            for i in range(10)  # 10 summaries * 200 tokens = 2000 tokens
        ]

        other_memories = [
            {
                "content": "B" * 400,  # ~100 tokens
                "type": "decision",
                "collection": "discussions",
                "score": 0.85,
            }
            for _ in range(5)  # 5 memories * 100 tokens = 500 tokens
        ]

        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import inject_with_priority

            from memory.chunking.truncation import count_tokens

            mock_config.token_budget = 1000  # Small budget

            result = inject_with_priority(
                session_summaries=session_summaries,
                other_memories=other_memories,
                token_budget=1000,
            )

            # Verify total tokens don't exceed budget (TD-167: estimate_tokens → count_tokens)
            actual_tokens = count_tokens(result)
            assert (
                actual_tokens <= 1000
            ), f"Token budget exceeded: {actual_tokens} > 1000"

    def test_priority_injection_filters_low_value_content(
        self, mock_qdrant, mock_config
    ):
        """Test TECH-DEBT-047: Use filters.py to remove low-value content."""
        # Session summary with menu patterns (should be filtered)
        session_summaries = [
            {
                "content": "[MH] Menu Help\n[CH] Command Hub\n─────────\nActual useful content here",
                "timestamp": "2026-01-21T10:00:00Z",
                "type": "session",
                "first_user_prompt": "Show menu",
                "last_user_prompts": [],
                "last_agent_responses": [],
                "session_metadata": {},
            }
        ]

        other_memories = []

        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import inject_with_priority

            mock_config.token_budget = 2000

            result = inject_with_priority(
                session_summaries=session_summaries,
                other_memories=other_memories,
                token_budget=2000,
            )

            # Verify menu patterns filtered out
            assert "[MH]" not in result
            assert "[CH]" not in result
            assert "─────" not in result
            # Verify useful content retained
            assert "Actual useful content" in result


class TestPriorityInjectionEdgeCases:
    """Edge case tests for inject_with_priority() - MEDIUM-7 fixes."""

    def test_both_lists_empty_returns_empty(self, mock_qdrant, mock_config):
        """Empty summaries + empty memories = empty result."""
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import inject_with_priority

            result = inject_with_priority([], [], 2000)
            assert result == "" or result.strip() == ""

    def test_single_giant_summary_leaves_room_for_phase2(
        self, mock_qdrant, mock_config
    ):
        """Single summary exceeding 60% budget still allows Phase 2."""
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import inject_with_priority

            # Create a giant summary (10000 chars = ~3333 tokens)
            giant_summary = {
                "content": "x" * 10000,
                "timestamp": "2026-01-25T10:00:00Z",
                "type": "session",
            }

            # Also add a small other memory
            small_memory = {
                "content": "Decision: Use Qdrant",
                "type": "decision",
                "score": 0.85,
            }

            result = inject_with_priority([giant_summary], [small_memory], 2000)

            # Should not crash, should produce some output
            assert len(result) > 0
            # Giant summary should be truncated
            assert "..." in result

    def test_malformed_timestamp_handled(self, mock_qdrant, mock_config):
        """Invalid timestamp doesn't crash."""
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import inject_with_priority

            # Test various malformed timestamps
            bad_summaries = [
                {"content": "test1", "timestamp": None, "type": "session"},
                {"content": "test2", "timestamp": "invalid", "type": "session"},
                {
                    "content": "test3",
                    "timestamp": 12345,
                    "type": "session",
                },  # Wrong type
            ]

            result = inject_with_priority(bad_summaries, [], 2000)

            # Should not crash, should contain content
            assert "test1" in result or "test2" in result or "test3" in result

    def test_zero_budget_no_division_error(self, mock_qdrant, mock_config):
        """token_budget=0 doesn't cause division by zero."""
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import inject_with_priority

            summaries = [
                {"content": "test", "timestamp": "2026-01-25", "type": "session"}
            ]

            # Should not crash with budget=0
            result = inject_with_priority(summaries, [], 0)

            # Should return empty string (early exit)
            assert result == ""

    def test_negative_budget_handled(self, mock_qdrant, mock_config):
        """Negative budget is handled gracefully."""
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
        ):
            from session_start import inject_with_priority

            summaries = [
                {"content": "test", "timestamp": "2026-01-25", "type": "session"}
            ]

            # Should not crash with negative budget
            result = inject_with_priority(summaries, [], -100)

            # Should return empty string (early exit)
            assert result == ""

    def test_filter_exception_graceful_fallback(self, mock_qdrant, mock_config):
        """If filter raises, fall back to unfiltered content."""
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
            patch(
                "session_start.filter_low_value_content",
                side_effect=Exception("Filter crashed"),
            ),
        ):
            from session_start import inject_with_priority

            summaries = [
                {
                    "content": "This content should still appear despite filter failure",
                    "timestamp": "2026-01-25T10:00:00Z",
                    "type": "session",
                }
            ]

            result = inject_with_priority(summaries, [], 2000)

            # Should not crash, should use unfiltered content
            assert "This content should still appear" in result

    def test_smart_truncate_exception_fallback(self, mock_qdrant, mock_config):
        """If smart_truncate raises, fall back to simple truncation."""
        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
            patch("memory.config.get_config", return_value=mock_config),
            patch(
                "session_start.smart_truncate",
                side_effect=Exception("Truncate crashed"),
            ),
        ):
            from session_start import inject_with_priority

            # Long content that triggers truncation
            long_content = "a" * 3000
            summaries = [
                {
                    "content": long_content,
                    "timestamp": "2026-01-25T10:00:00Z",
                    "type": "session",
                }
            ]

            result = inject_with_priority(summaries, [], 2000)

            # Should not crash, should use simple truncation
            assert len(result) > 0
            assert "..." in result  # Simple truncation adds ...
