"""Unit tests for session_start.py hook.

Tests V2.0 context injection behavior for compact/resume events.
"""

import contextlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

# Import fixtures
sys.path.insert(0, str(Path(__file__).parent.parent))
from mocks.qdrant_mock import MockQdrantClient

# Add hook scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".claude/hooks/scripts"))


@pytest.fixture
def compact_event():
    """Load compact event fixture."""
    with open(
        Path(__file__).parent.parent / "fixtures/hooks/session_start_compact.json"
    ) as f:
        return json.load(f)


@pytest.fixture
def resume_event():
    """Load resume event fixture."""
    with open(
        Path(__file__).parent.parent / "fixtures/hooks/session_start_resume.json"
    ) as f:
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


class TestParzivalCompactAgentIdFilter:
    """Tests for H-1: Parzival compact path must include agent_id='parzival' filter.

    Spec §4.1: '3 session summaries + 5 decisions (agent_id=parzival)'
    The Parzival path uses config.parzival_enabled=True and calls get_recent()
    with agent_id='parzival' to scope retrieval to Parzival's tenant.
    """

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Reset module state before each test."""
        if "session_start" in sys.modules:
            del sys.modules["session_start"]
        yield
        if "session_start" in sys.modules:
            del sys.modules["session_start"]

    @staticmethod
    def _build_mock_config(parzival_enabled=True):
        mock_config = MagicMock()
        mock_config.parzival_enabled = parzival_enabled
        mock_config.project_name = "test-project"
        mock_config.qdrant_host = "localhost"
        mock_config.qdrant_port = 26350
        mock_config.qdrant_api_key = SecretStr("test-key")
        mock_config.github_repo = "test-project"
        mock_config.embedding_host = "localhost"
        mock_config.embedding_port = 28080
        return mock_config

    def _run_compact_main(
        self, mock_config, session_id_suffix="default", extra_patches=None
    ):
        """Run session_start.main() with compact trigger and mocked dependencies.

        Returns the mock_searcher so callers can inspect get_recent calls.
        """
        import uuid

        unique_session_id = (
            f"sess_compact_parz_{session_id_suffix}_{uuid.uuid4().hex[:8]}"
        )

        mock_searcher = MagicMock()
        mock_searcher.get_recent.return_value = []
        mock_searcher.close.return_value = None

        patches = {
            "memory.search.MemorySearch": MagicMock(return_value=mock_searcher),
            "memory.config.get_config": MagicMock(return_value=mock_config),
            "memory.health.check_qdrant_health": MagicMock(return_value=True),
            "memory.qdrant_client.get_qdrant_client": MagicMock(),
            "memory.embeddings.EmbeddingClient": MagicMock(),
        }
        if extra_patches:
            patches.update(extra_patches)

        with contextlib.ExitStack() as ctx:
            for target, mock_val in patches.items():
                ctx.enter_context(patch(target, mock_val))
            # Patch session_start module-level symbols after import
            ctx.enter_context(
                patch(
                    "session_start.parse_hook_input",
                    return_value={
                        "cwd": "/test",
                        "session_id": unique_session_id,
                        "source": "compact",
                    },
                )
            )
            ctx.enter_context(
                patch("session_start.detect_project", return_value="test-project")
            )
            ctx.enter_context(patch("session_start.cleanup_dedup_lock"))
            ctx.enter_context(
                patch("session_start.check_qdrant_health", return_value=True)
            )
            ctx.enter_context(patch("session_start.emit_trace_event", None))
            ctx.enter_context(patch("session_start.log_conversation_context_injection"))
            ctx.enter_context(
                patch("session_start.inject_with_priority", return_value="test output")
            )
            ctx.enter_context(patch("builtins.print"))

            from session_start import main

            with contextlib.suppress(SystemExit):
                main()

        return mock_searcher

    def test_parzival_compact_session_summaries_include_agent_id(self):
        """Parzival compact path must call get_recent() with agent_id='parzival' for session summaries."""
        mock_config = self._build_mock_config(parzival_enabled=True)
        mock_searcher = self._run_compact_main(mock_config)

        # Find the get_recent call for session summaries (type=session)
        session_calls = [
            call
            for call in mock_searcher.get_recent.call_args_list
            if call.kwargs.get("memory_type") == ["session"]
        ]

        assert len(session_calls) >= 1, (
            f"Expected at least 1 get_recent call with memory_type=['session'], "
            f"got {len(session_calls)}. All calls: {mock_searcher.get_recent.call_args_list}"
        )

        session_call = session_calls[0]
        assert session_call.kwargs.get("agent_id") == "parzival", (
            f"Parzival compact path must pass agent_id='parzival' for session summaries. "
            f"Got kwargs: {session_call.kwargs}"
        )
        assert session_call.kwargs.get("limit") == 3, (
            f"Parzival compact path must use limit=3 for session summaries. "
            f"Got: {session_call.kwargs.get('limit')}"
        )

    def test_parzival_compact_decisions_include_agent_id(self):
        """Parzival compact path must call get_recent() with agent_id='parzival' for decisions."""
        mock_config = self._build_mock_config(parzival_enabled=True)
        mock_searcher = self._run_compact_main(mock_config)

        decision_calls = [
            call
            for call in mock_searcher.get_recent.call_args_list
            if call.kwargs.get("memory_type") == ["decision"]
        ]

        assert len(decision_calls) >= 1, (
            f"Expected at least 1 get_recent call with memory_type=['decision'], "
            f"got {len(decision_calls)}. All calls: {mock_searcher.get_recent.call_args_list}"
        )

        decision_call = decision_calls[0]
        assert decision_call.kwargs.get("agent_id") == "parzival", (
            f"Parzival compact path must pass agent_id='parzival' for decisions. "
            f"Got kwargs: {decision_call.kwargs}"
        )
        assert decision_call.kwargs.get("limit") == 5, (
            f"Parzival compact path must use limit=5 for decisions. "
            f"Got: {decision_call.kwargs.get('limit')}"
        )


class TestNonParzivalCompactSummaryLimit:
    """Tests for non-Parzival compact summary limit logic (1st vs 2nd+ compact)."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Reset module state before each test."""
        if "session_start" in sys.modules:
            del sys.modules["session_start"]
        yield
        if "session_start" in sys.modules:
            del sys.modules["session_start"]

    @staticmethod
    def _build_mock_config():
        mock_config = MagicMock()
        mock_config.parzival_enabled = False
        mock_config.project_name = "test-project"
        mock_config.qdrant_host = "localhost"
        mock_config.qdrant_port = 26350
        mock_config.qdrant_api_key = SecretStr("test-key")
        mock_config.github_repo = "test-project"
        mock_config.embedding_host = "localhost"
        mock_config.embedding_port = 28080
        return mock_config

    def _run_compact_main(self, compact_count):
        """Run non-Parzival compact path with given compact_count.

        Returns mock_searcher so callers can inspect get_recent calls.
        """
        import uuid

        unique_session_id = (
            f"sess_compact_nonparz_{compact_count}_{uuid.uuid4().hex[:8]}"
        )

        mock_config = self._build_mock_config()
        mock_searcher = MagicMock()
        mock_searcher.get_recent.return_value = []
        mock_searcher.close.return_value = None

        mock_state = MagicMock()
        mock_state.compact_count = compact_count

        with contextlib.ExitStack() as ctx:
            ctx.enter_context(
                patch(
                    "memory.search.MemorySearch", MagicMock(return_value=mock_searcher)
                )
            )
            ctx.enter_context(
                patch("memory.config.get_config", MagicMock(return_value=mock_config))
            )
            ctx.enter_context(
                patch("memory.health.check_qdrant_health", MagicMock(return_value=True))
            )
            ctx.enter_context(
                patch("memory.qdrant_client.get_qdrant_client", MagicMock())
            )
            ctx.enter_context(patch("memory.embeddings.EmbeddingClient", MagicMock()))
            ctx.enter_context(
                patch(
                    "memory.injection.InjectionSessionState.load",
                    MagicMock(return_value=mock_state),
                )
            )
            ctx.enter_context(
                patch(
                    "session_start.parse_hook_input",
                    return_value={
                        "cwd": "/test",
                        "session_id": unique_session_id,
                        "source": "compact",
                    },
                )
            )
            ctx.enter_context(
                patch("session_start.detect_project", return_value="test-project")
            )
            ctx.enter_context(
                patch("session_start._detect_agent_id", return_value="default")
            )
            ctx.enter_context(patch("session_start.cleanup_dedup_lock"))
            ctx.enter_context(
                patch("session_start.check_qdrant_health", return_value=True)
            )
            ctx.enter_context(patch("session_start.emit_trace_event", None))
            ctx.enter_context(patch("session_start.log_conversation_context_injection"))
            ctx.enter_context(
                patch("session_start.inject_with_priority", return_value="test output")
            )
            ctx.enter_context(patch("builtins.print"))

            from session_start import main

            with contextlib.suppress(SystemExit):
                main()

        return mock_searcher

    def test_first_compact_gets_1_summary(self):
        """1st compact (compact_count=0) should request limit=1 for session summaries."""
        mock_searcher = self._run_compact_main(compact_count=0)

        session_calls = [
            call
            for call in mock_searcher.get_recent.call_args_list
            if call.kwargs.get("memory_type") == ["session"]
        ]

        assert len(session_calls) >= 1, (
            f"Expected get_recent call with memory_type=['session']. "
            f"All calls: {mock_searcher.get_recent.call_args_list}"
        )

        assert session_calls[0].kwargs.get("limit") == 1, (
            f"1st compact (compact_count=0) should use limit=1 for summaries. "
            f"Got: {session_calls[0].kwargs.get('limit')}"
        )

    def test_second_compact_gets_2_summaries(self):
        """2nd+ compact (compact_count>=1) should request limit=2 for session summaries."""
        mock_searcher = self._run_compact_main(compact_count=2)

        session_calls = [
            call
            for call in mock_searcher.get_recent.call_args_list
            if call.kwargs.get("memory_type") == ["session"]
        ]

        assert len(session_calls) >= 1, (
            f"Expected get_recent call with memory_type=['session']. "
            f"All calls: {mock_searcher.get_recent.call_args_list}"
        )

        assert session_calls[0].kwargs.get("limit") == 2, (
            f"2nd+ compact (compact_count>=1) should use limit=2 for summaries. "
            f"Got: {session_calls[0].kwargs.get('limit')}"
        )


class TestMatcherConfiguration:
    """Tests for SessionStart hook matcher configuration."""

    def test_matcher_does_not_include_startup(self):
        """PLAN-011: startup trigger removed — no matcher constants in settings script."""
        import scripts.update_parzival_settings as ups

        # Matcher constants were removed (v2.2.0) — startup is no longer managed
        assert not hasattr(ups, "MATCHER_PARZIVAL")
        assert not hasattr(ups, "MATCHER_STANDARD")


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
