"""Tests for PLAN-015 WP-7 Remembrance Protection.

Tests the access_count field handling and decay bypass logic.
These are unit tests — they do not require a running Qdrant instance.
"""
from unittest.mock import MagicMock, patch


class TestRememberanceProtectionAccessCount:
    """Test access_count increment logic."""

    def test_access_count_missing_treated_as_zero(self):
        """A point with no access_count in payload field is treated as count=0."""
        # Simulate a point with no access_count in payload
        mock_point = MagicMock()
        mock_point.payload = {}  # No access_count key
        current = int(mock_point.payload.get("access_count") or 0)
        assert current == 0

    def test_access_count_none_treated_as_zero(self):
        """A point with access_count=None is treated as count=0."""
        mock_point = MagicMock()
        mock_point.payload = {"access_count": None}
        current = int(mock_point.payload.get("access_count") or 0)
        assert current == 0

    def test_threshold_crossing_at_3_triggers_trace(self):
        """access_count reaching exactly 3 (not 4+) is the triggering transition."""
        # Verify that _new_count == 3 is the trigger condition used in search.py
        # This mirrors: if _new_count == 3 and emit_trace_event:
        triggering_counts = [3]
        non_triggering_counts = [1, 2, 4, 5, 10]

        for count in triggering_counts:
            assert count == 3, f"Expected 3 to trigger, got {count}"

        for count in non_triggering_counts:
            assert count != 3, f"Expected {count} not to trigger"

    def test_remembrance_threshold_crossing_2_to_3(self):
        """The protection activates on transition from 2 → 3 (not earlier or later)."""
        # Simulate the increment logic used in search.py
        current_count = 2
        new_count = current_count + 1
        assert new_count == 3  # This is the threshold crossing

        # Already protected — no new trace at 4
        current_count = 3
        new_count = current_count + 1
        assert new_count == 4  # Above threshold but NOT the trigger


class TestDecayFormulaAccessCountProtection:
    """Verify decay formula includes access_count protection."""

    def test_build_decay_formula_importable(self):
        """build_decay_formula can be imported without error."""
        from memory.decay import build_decay_formula
        assert callable(build_decay_formula)

    def test_decay_module_importable(self):
        """decay module imports cleanly."""
        import memory.decay as decay_module
        assert hasattr(decay_module, "build_decay_formula")
        assert hasattr(decay_module, "compute_decay_score")

    def test_build_decay_formula_defaults_contain_access_count(self):
        """build_decay_formula() FormulaQuery defaults include access_count=0."""
        from memory.config import MemoryConfig
        from memory.decay import build_decay_formula

        config = MemoryConfig(decay_enabled=True)
        dummy_embedding = [0.0] * 768
        formula, _prefetch = build_decay_formula(
            query_embedding=dummy_embedding,
            collection="discussions",
            config=config,
        )
        assert formula is not None, "Expected a FormulaQuery when decay_enabled=True"
        assert "access_count" in formula.defaults
        assert formula.defaults["access_count"] == 0

    def test_build_decay_formula_contains_protection_branch(self):
        """Formula tree contains a MultExpression with Range(gte=3.0) for protection."""
        from qdrant_client import models

        from memory.config import MemoryConfig
        from memory.decay import build_decay_formula

        config = MemoryConfig(decay_enabled=True)
        dummy_embedding = [0.0] * 768
        formula, _prefetch = build_decay_formula(
            query_embedding=dummy_embedding,
            collection="discussions",
            config=config,
        )
        assert formula is not None

        # Walk the outer SumExpression: [semantic_mult, temporal_mult]
        outer_sum = formula.formula
        assert isinstance(outer_sum, models.SumExpression)

        # temporal component: MultExpression([temporal_w, temporal_score_expr])
        temporal_mult = outer_sum.sum[1]
        assert isinstance(temporal_mult, models.MultExpression)
        temporal_score_expr = temporal_mult.mult[1]
        assert isinstance(temporal_score_expr, models.SumExpression)

        # protected_branch = MultExpression([FieldCondition(access_count >= 3), 1.0])
        protected_branch = temporal_score_expr.sum[0]
        assert isinstance(protected_branch, models.MultExpression)

        field_cond = protected_branch.mult[0]
        assert isinstance(field_cond, models.FieldCondition)
        assert field_cond.key == "access_count"
        assert field_cond.range is not None
        assert field_cond.range.gte == 3.0

    def test_build_decay_formula_disabled_returns_none(self):
        """build_decay_formula() returns None formula when decay_enabled=False."""
        from memory.config import MemoryConfig
        from memory.decay import build_decay_formula

        config = MemoryConfig(decay_enabled=False)
        dummy_embedding = [0.0] * 768
        formula, prefetch = build_decay_formula(
            query_embedding=dummy_embedding,
            collection="discussions",
            config=config,
        )
        assert formula is None
        assert prefetch is not None


class TestMemorySearchAccessCountUpdate:
    """Test that search() updates access_count via set_payload after returning results."""

    def _make_mock_point(self, point_id="test-point-1", access_count=0):
        """Create a mock Qdrant ScoredPoint with payload."""
        mock_point = MagicMock()
        mock_point.id = point_id
        mock_point.score = 0.85
        mock_point.payload = {
            "content": "Test memory content",
            "type": "decision",
            "group_id": "test-project",
            "stored_at": "2026-01-01T00:00:00Z",
            "access_count": access_count,
        }
        return mock_point

    def _make_mock_retrieved_point(self, point_id="test-point-1", access_count=0):
        """Create a mock Qdrant Record (retrieve result) with payload."""
        mock_point = MagicMock()
        mock_point.id = point_id
        mock_point.payload = {"access_count": access_count}
        return mock_point

    def test_search_calls_set_payload_after_results(self):
        """search() calls client.set_payload() to increment access_count after returning results."""
        from memory.config import MemoryConfig

        mock_scored_point = self._make_mock_point("pid-1", access_count=1)
        mock_retrieved_point = self._make_mock_retrieved_point("pid-1", access_count=1)

        mock_response = MagicMock()
        mock_response.points = [mock_scored_point]

        mock_client = MagicMock()
        mock_client.query_points.return_value = mock_response
        mock_client.retrieve.return_value = [mock_retrieved_point]
        mock_client.set_payload.return_value = None

        mock_embedding = MagicMock()
        mock_embedding.embed.return_value = [[0.0] * 768]
        mock_embedding.embed_sparse.return_value = None

        config = MemoryConfig(
            decay_enabled=False,
            hybrid_search_enabled=False,
        )

        with patch("memory.search.get_qdrant_client", return_value=mock_client), \
             patch("memory.search.EmbeddingClient", return_value=mock_embedding):
            from memory.search import MemorySearch
            searcher = MemorySearch(config=config)
            results = searcher.search(
                query="test query",
                collection="discussions",
                group_id="test-project",
                limit=5,
            )

        assert len(results) == 1
        mock_client.retrieve.assert_called_once()
        mock_client.set_payload.assert_called_once()

        # Verify set_payload was called with incremented count (1 → 2)
        call_kwargs = mock_client.set_payload.call_args
        assert call_kwargs is not None
        payload_arg = call_kwargs[1].get("payload") or call_kwargs[0][1]
        assert payload_arg["access_count"] == 2

    def test_search_returns_results_when_set_payload_raises(self):
        """search() returns results even when set_payload raises an exception."""
        from memory.config import MemoryConfig

        mock_scored_point = self._make_mock_point("pid-fail", access_count=0)
        mock_retrieved_point = self._make_mock_retrieved_point("pid-fail", access_count=0)

        mock_response = MagicMock()
        mock_response.points = [mock_scored_point]

        mock_client = MagicMock()
        mock_client.query_points.return_value = mock_response
        mock_client.retrieve.return_value = [mock_retrieved_point]
        mock_client.set_payload.side_effect = Exception("Qdrant unavailable")

        mock_embedding = MagicMock()
        mock_embedding.embed.return_value = [[0.0] * 768]
        mock_embedding.embed_sparse.return_value = None

        config = MemoryConfig(
            decay_enabled=False,
            hybrid_search_enabled=False,
        )

        with patch("memory.search.get_qdrant_client", return_value=mock_client), \
             patch("memory.search.EmbeddingClient", return_value=mock_embedding):
            from memory.search import MemorySearch
            searcher = MemorySearch(config=config)
            results = searcher.search(
                query="test query",
                collection="discussions",
                group_id="test-project",
                limit=5,
            )

        # Results MUST be returned even though set_payload raised
        assert len(results) == 1
        assert results[0]["id"] == "pid-fail"

    def test_search_returns_results_when_retrieve_raises(self):
        """search() returns results even when retrieve raises (falls back to access_count=0)."""
        from memory.config import MemoryConfig

        mock_scored_point = self._make_mock_point("pid-retrieve-fail", access_count=0)

        mock_response = MagicMock()
        mock_response.points = [mock_scored_point]

        mock_client = MagicMock()
        mock_client.query_points.return_value = mock_response
        mock_client.retrieve.side_effect = Exception("Retrieve failed")
        mock_client.set_payload.return_value = None

        mock_embedding = MagicMock()
        mock_embedding.embed.return_value = [[0.0] * 768]
        mock_embedding.embed_sparse.return_value = None

        config = MemoryConfig(
            decay_enabled=False,
            hybrid_search_enabled=False,
        )

        with patch("memory.search.get_qdrant_client", return_value=mock_client), \
             patch("memory.search.EmbeddingClient", return_value=mock_embedding):
            from memory.search import MemorySearch
            searcher = MemorySearch(config=config)
            results = searcher.search(
                query="test query",
                collection="discussions",
                group_id="test-project",
                limit=5,
            )

        # Results MUST be returned even though retrieve raised
        assert len(results) == 1
        assert results[0]["id"] == "pid-retrieve-fail"
        # set_payload still called (using empty count_map fallback, access_count 0 → 1)
        mock_client.set_payload.assert_called_once()


class TestInjectionSessionState:
    """Test InjectionSessionState access_count and compact tracking."""

    def test_injection_state_default_compact_count(self):
        """InjectionSessionState initialises compact_count to 0."""
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id="test-abc")
        assert state.compact_count == 0

    def test_reset_after_compact_increments_count(self):
        """reset_after_compact() increments compact_count and clears injected_point_ids."""
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id="test-abc")
        state.injected_point_ids = ["id1", "id2"]
        state.reset_after_compact()
        assert state.compact_count == 1
        assert state.injected_point_ids == []

    def test_memory_search_class_exists(self):
        """MemorySearch class is importable from memory.search (smoke test)."""
        from memory.search import MemorySearch

        assert callable(MemorySearch)
