"""Integration tests for session memory round-trip (SPEC-016).

Tests the full lifecycle: closeout stores → next session loads → content matches.
Requires Qdrant and embedding services running.
"""

from unittest.mock import patch

import pytest

from memory.config import MemoryConfig
from memory.injection import retrieve_bootstrap_context

pytestmark = pytest.mark.integration


class TestSessionRoundTrip:
    """Test closeout-to-bootstrap round-trip."""

    @pytest.mark.requires_docker_stack
    def test_session_round_trip(self):
        """Full round-trip: store handoff → bootstrap loads it."""
        from memory.search import MemorySearch
        from memory.storage import MemoryStorage

        storage = MemoryStorage()
        result = storage.store_agent_memory(
            content="PM #59: Wave 2 implementation complete. Next: review cycle.",
            memory_type="agent_handoff",
            agent_id="parzival",
            cwd="/tmp/test-round-trip",
        )
        assert result["status"] == "stored"

        search = MemorySearch()
        results = search.search(
            query="session handoff current work",
            collection="discussions",
            group_id="test-round-trip",
            agent_id="parzival",
            memory_type=["agent_handoff"],
            limit=1,
        )

        assert len(results) >= 1
        assert "Wave 2 implementation complete" in results[0]["content"]

    def test_graceful_degradation_qdrant_down(self):
        """Bootstrap returns empty results when Qdrant is unavailable."""

        from memory.qdrant_client import QdrantUnavailable
        from memory.search import MemorySearch

        with patch(
            "memory.search.get_qdrant_client",
            side_effect=QdrantUnavailable("Connection refused"),
        ):
            search = MemorySearch()
            config = MemoryConfig(_env_file=None, parzival_enabled=True)

            results = retrieve_bootstrap_context(search, "test-project", config)
            assert isinstance(results, list)
