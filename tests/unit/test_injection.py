"""Unit tests for progressive context injection (SPEC-012).

Tests cover:
- Collection routing (keyword, intent, file-path detection)
- Adaptive budget computation (quality, density, drift signals)
- Topic drift calculation (cosine distance)
- Greedy fill selection (budget enforcement, deduplication)
- Injection formatting (<retrieved_context> tags)
- Session state management (load/save, reset_after_compact)
- Audit logging (JSONL format)
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    MemoryConfig,
)
from memory.injection import (
    InjectionSessionState,
    RouteTarget,
    compute_adaptive_budget,
    compute_topic_drift,
    format_injection_output,
    init_session_state,
    log_injection_event,
    route_collections,
    select_results_greedy,
)


class TestRouteCollections:
    """Test collection routing logic."""

    def test_decision_keywords_route_to_discussions(self):
        """Decision keywords should route to discussions collection."""
        prompt = "why did we decide to use Qdrant for vector storage?"
        routes = route_collections(prompt)
        assert len(routes) == 1
        assert routes[0].collection == COLLECTION_DISCUSSIONS
        assert routes[0].shared is False

    def test_best_practices_keywords_route_to_conventions(self):
        """Best practices keywords should route to conventions collection."""
        prompt = "what are the best practices for error handling?"
        routes = route_collections(prompt)
        assert len(routes) == 1
        assert routes[0].collection == COLLECTION_CONVENTIONS
        assert routes[0].shared is True

    def test_file_paths_route_to_code_patterns(self):
        """File paths in prompt should route to code-patterns collection."""
        prompt = "how does src/memory/search.py implement vector search?"
        routes = route_collections(prompt)
        assert len(routes) == 1
        assert routes[0].collection == COLLECTION_CODE_PATTERNS
        assert routes[0].shared is False

    @patch("memory.injection.detect_intent")
    @patch("memory.injection.get_target_collection")
    def test_intent_detection_routing(self, mock_get_target, mock_detect):
        """Intent detection should route to target collection."""
        from memory.intent import IntentType

        mock_detect.return_value = IntentType.HOW
        mock_get_target.return_value = COLLECTION_CODE_PATTERNS

        prompt = "how to implement caching"
        routes = route_collections(prompt)
        assert len(routes) == 1
        assert routes[0].collection == COLLECTION_CODE_PATTERNS

    @patch("memory.injection.detect_intent")
    def test_unknown_intent_cascades_all_collections(self, mock_detect):
        """Unknown intent should cascade to all collections."""
        from memory.intent import IntentType

        mock_detect.return_value = IntentType.UNKNOWN

        prompt = "random vague question"
        routes = route_collections(prompt)
        assert len(routes) == 3
        assert routes[0].collection == COLLECTION_DISCUSSIONS
        assert routes[1].collection == COLLECTION_CODE_PATTERNS
        assert routes[2].collection == COLLECTION_CONVENTIONS

    def test_multiple_keywords_deduplicate_same_collection(self):
        """Multiple triggers to same collection should deduplicate."""
        prompt = "why did we decide on best practices for sessions?"
        routes = route_collections(prompt)
        # Both decision and session keywords → discussions, should deduplicate
        collections = [r.collection for r in routes]
        assert collections.count(COLLECTION_DISCUSSIONS) == 1


class TestComputeAdaptiveBudget:
    """Test adaptive budget computation."""

    def setup_method(self):
        """Create test config."""
        self.config = MagicMock(spec=MemoryConfig)
        self.config.injection_budget_floor = 500
        self.config.injection_budget_ceiling = 1500
        self.config.injection_confidence_threshold = 0.6
        self.config.injection_quality_weight = 0.5
        self.config.injection_density_weight = 0.3
        self.config.injection_drift_weight = 0.2

    def test_floor_budget_when_signals_low(self):
        """Budget should be at floor when all signals are low."""
        best_score = 0.0
        results = [{"score": 0.3}, {"score": 0.2}]  # Below threshold
        session_state = {"topic_drift": 0.0}

        budget = compute_adaptive_budget(
            best_score, results, session_state, self.config
        )
        # Low quality, low density, low drift → minimum budget
        assert budget == self.config.injection_budget_floor

    def test_ceiling_budget_when_signals_high(self):
        """Budget should be at ceiling when all signals are high."""
        best_score = 1.0
        results = [{"score": 0.9}, {"score": 0.8}, {"score": 0.7}]
        session_state = {"topic_drift": 1.0}

        budget = compute_adaptive_budget(
            best_score, results, session_state, self.config
        )
        # High quality, high density, high drift → maximum budget
        assert budget == self.config.injection_budget_ceiling

    def test_weighted_combination_mid_range(self):
        """Budget should be in mid-range with mixed signals."""
        best_score = 0.7
        results = [{"score": 0.8}, {"score": 0.5}]
        session_state = {"topic_drift": 0.5}

        budget = compute_adaptive_budget(
            best_score, results, session_state, self.config
        )
        # Mixed signals → mid-range budget
        assert self.config.injection_budget_floor < budget < self.config.injection_budget_ceiling

    def test_neutral_drift_default(self):
        """Neutral drift (0.5) should be used when no previous embedding."""
        best_score = 0.8
        results = [{"score": 0.8}]
        session_state = {}  # No topic_drift key

        budget = compute_adaptive_budget(
            best_score, results, session_state, self.config
        )
        # Should use default drift 0.5
        assert budget > 0

    def test_empty_results_zero_density(self):
        """Empty results should give zero density signal."""
        best_score = 0.0
        results = []
        session_state = {"topic_drift": 0.5}

        budget = compute_adaptive_budget(
            best_score, results, session_state, self.config
        )
        # Should still compute budget with zero density
        assert budget >= self.config.injection_budget_floor


class TestComputeTopicDrift:
    """Test topic drift computation."""

    def test_same_embedding_zero_drift(self):
        """Identical embeddings should have zero drift."""
        embedding = [1.0, 0.0, 0.0]
        drift = compute_topic_drift(embedding, embedding)
        assert drift < 0.01  # Nearly zero

    def test_orthogonal_embeddings_high_drift(self):
        """Orthogonal embeddings should have high drift."""
        current = [1.0, 0.0, 0.0]
        previous = [0.0, 1.0, 0.0]
        drift = compute_topic_drift(current, previous)
        assert drift > 0.9  # Nearly 1.0

    def test_no_previous_embedding_neutral_drift(self):
        """First turn (no previous) should return neutral 0.5."""
        current = [1.0, 0.0, 0.0]
        drift = compute_topic_drift(current, None)
        assert drift == 0.5


class TestSelectResultsGreedy:
    """Test greedy fill selection."""

    def test_budget_enforcement(self):
        """Should stop selecting when budget exhausted."""
        # Use simple content strings with known token counts
        results = [
            {"id": "1", "content": "First result " * 5, "score": 0.9},  # ~10 tokens
            {"id": "2", "content": "Second result " * 5, "score": 0.8},  # ~10 tokens
            {"id": "3", "content": "Third result " * 5, "score": 0.7},  # ~10 tokens
            {"id": "4", "content": "Fourth result " * 5, "score": 0.6},  # ~10 tokens
        ]
        budget = 25  # Should fit 2-3 results

        selected, tokens_used = select_results_greedy(results, budget)
        # Should respect budget constraint
        assert tokens_used <= budget
        # Should select at least 1 but not all 4 results
        assert 1 <= len(selected) < 4

    def test_skip_and_continue_oversized(self):
        """Should skip oversized results and continue with smaller ones."""
        results = [
            {"id": "1", "content": "a" * 1000, "score": 0.9},  # Very large
            {"id": "2", "content": "b" * 30, "score": 0.8},  # Small
            {"id": "3", "content": "c" * 30, "score": 0.7},  # Small
        ]
        budget = 50

        selected, tokens_used = select_results_greedy(results, budget)
        # Should skip result 1 and select 2 and 3
        assert "1" not in [s["id"] for s in selected]
        assert len(selected) >= 2

    def test_deduplication_by_excluded_ids(self):
        """Should skip results in excluded_ids list."""
        results = [
            {"id": "1", "content": "test", "score": 0.9},
            {"id": "2", "content": "test", "score": 0.8},
            {"id": "3", "content": "test", "score": 0.7},
        ]
        excluded = ["2"]
        budget = 1000

        selected, tokens_used = select_results_greedy(results, budget, excluded)
        assert "2" not in [s["id"] for s in selected]
        assert len(selected) == 2

    def test_empty_results_returns_empty(self):
        """Empty results should return empty selection."""
        results = []
        budget = 1000

        selected, tokens_used = select_results_greedy(results, budget)
        assert selected == []
        assert tokens_used == 0

    def test_skip_empty_content(self):
        """Should skip results with empty content."""
        results = [
            {"id": "1", "content": "", "score": 0.9},
            {"id": "2", "content": "valid", "score": 0.8},
        ]
        budget = 1000

        selected, tokens_used = select_results_greedy(results, budget)
        assert len(selected) == 1
        assert selected[0]["id"] == "2"


class TestFormatInjectionOutput:
    """Test injection output formatting."""

    def test_format_with_attribution(self):
        """Should format results with type, collection, and score."""
        results = [
            {
                "content": "Test memory",
                "type": "decision",
                "score": 0.85,
                "collection": "discussions",
            }
        ]

        formatted = format_injection_output(results, tier=1)
        assert "<retrieved_context>" in formatted
        assert "</retrieved_context>" in formatted
        assert "decision" in formatted
        assert "discussions" in formatted
        assert "85%" in formatted
        assert "Test memory" in formatted

    def test_empty_results_returns_empty(self):
        """Empty results should return empty string."""
        results = []
        formatted = format_injection_output(results, tier=1)
        assert formatted == ""


class TestInjectionSessionState:
    """Test session state management."""

    def test_load_save_roundtrip(self):
        """Should persist and reload state correctly."""
        session_id = "test-session-123"
        state = InjectionSessionState(
            session_id=session_id,
            injected_point_ids=["id1", "id2"],
            last_query_embedding=[1.0, 0.0, 0.0],
            topic_drift=0.3,
            turn_count=5,
            total_tokens_injected=1200,
        )

        # Save and reload
        state.save()
        loaded = InjectionSessionState.load(session_id)

        assert loaded.session_id == session_id
        assert loaded.injected_point_ids == ["id1", "id2"]
        assert loaded.last_query_embedding == [1.0, 0.0, 0.0]
        assert loaded.topic_drift == 0.3
        assert loaded.turn_count == 5
        assert loaded.total_tokens_injected == 1200

        # Cleanup
        Path(f"/tmp/ai-memory-{session_id}-injection-state.json").unlink(
            missing_ok=True
        )

    def test_reset_after_compact(self):
        """Should reset injected IDs but keep drift state."""
        state = InjectionSessionState(
            session_id="test",
            injected_point_ids=["id1", "id2"],
            last_query_embedding=[1.0, 0.0],
            topic_drift=0.4,
        )

        state.reset_after_compact()

        assert state.injected_point_ids == []
        assert state.last_query_embedding == [1.0, 0.0]  # Preserved
        assert state.topic_drift == 0.4  # Preserved

    def test_corrupted_file_returns_fresh_state(self):
        """Corrupted state file should return fresh state."""
        session_id = "test-corrupted"
        path = Path(f"/tmp/ai-memory-{session_id}-injection-state.json")

        # Write corrupted JSON
        path.write_text("{ invalid json")

        # Should return fresh state
        state = InjectionSessionState.load(session_id)
        assert state.session_id == session_id
        assert state.injected_point_ids == []

        # Cleanup
        path.unlink(missing_ok=True)


class TestLogInjectionEvent:
    """Test audit logging."""

    def test_creates_jsonl_log_entry(self):
        """Should create valid JSONL log entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_dir = Path(tmpdir)

            log_injection_event(
                tier=1,
                trigger="startup",
                project="test-project",
                session_id="test-session",
                results_considered=10,
                results_selected=5,
                tokens_used=1200,
                budget=2500,
                audit_dir=audit_dir,
                best_score=0.85,
                skipped_confidence=False,
                topic_drift=0.3,
                collections_searched=["discussions"],
            )

            log_path = audit_dir / "logs" / "injection-log.jsonl"
            assert log_path.exists()

            # Read and parse log entry
            line = log_path.read_text().strip()
            entry = json.loads(line)

            assert entry["tier"] == 1
            assert entry["trigger"] == "startup"
            assert entry["project"] == "test-project"
            assert entry["results_selected"] == 5
            assert entry["tokens_used"] == 1200
            assert entry["best_score"] == 0.85

    def test_graceful_failure_on_missing_dir(self):
        """Should not raise exception if audit dir missing."""
        # Should not raise
        log_injection_event(
            tier=1,
            trigger="startup",
            project="test",
            session_id="test",
            results_considered=0,
            results_selected=0,
            tokens_used=0,
            budget=1000,
            audit_dir=Path("/nonexistent/path"),
        )


class TestInitSessionState:
    """Test session state initialization."""

    def test_creates_state_file(self):
        """Should create state file with injected IDs."""
        session_id = "test-init-session"
        injected_ids = ["id1", "id2", "id3"]

        init_session_state(session_id, injected_ids)

        # Verify state file created
        state = InjectionSessionState.load(session_id)
        assert state.session_id == session_id
        assert state.injected_point_ids == injected_ids
        assert state.turn_count == 0

        # Cleanup
        Path(f"/tmp/ai-memory-{session_id}-injection-state.json").unlink(
            missing_ok=True
        )
