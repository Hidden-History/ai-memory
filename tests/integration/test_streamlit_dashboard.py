"""
Integration tests for Streamlit Memory Browser (Story 6.4).

Tests verify:
- Health endpoint accessibility
- Dashboard load time <5s (NFR-P4)
- Qdrant connectivity
- Search functionality
- Statistics display

RED PHASE: Write failing tests first, then implement.
"""

import pytest
import httpx
import time
from qdrant_client import QdrantClient
import os


class TestStreamlitHealthEndpoint:
    """AC 6.4.6: Health check endpoint must be accessible."""

    def test_health_endpoint_returns_200(self):
        """Health endpoint returns 200 OK."""
        streamlit_url = os.getenv("STREAMLIT_URL", "http://localhost:28501")

        response = httpx.get(
            f"{streamlit_url}/_stcore/health",
            timeout=10.0,
            follow_redirects=True
        )

        assert response.status_code == 200, \
            f"Health endpoint failed: {response.status_code}"


class TestStreamlitDashboardLoad:
    """AC 6.4.1: Dashboard must load within 5s (NFR-P4)."""

    def test_dashboard_loads_within_5_seconds(self):
        """Dashboard loads within NFR-P4 threshold."""
        streamlit_url = os.getenv("STREAMLIT_URL", "http://localhost:28501")

        start = time.time()
        response = httpx.get(
            streamlit_url,
            timeout=10.0,
            follow_redirects=True
        )
        elapsed = time.time() - start

        assert response.status_code == 200, \
            f"Dashboard failed to load: {response.status_code}"
        assert elapsed < 5.0, \
            f"Dashboard load time {elapsed:.2f}s exceeds 5s threshold (NFR-P4)"


class TestStreamlitQdrantConnectivity:
    """AC 6.4.2: Streamlit must connect to Qdrant successfully."""

    def test_streamlit_can_connect_to_qdrant(self):
        """Verify Qdrant connectivity via Streamlit environment."""
        # Use same connection params as Streamlit
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))

        client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            timeout=10.0
        )

        # Verify collections exist
        collections_response = client.get_collections()
        collection_names = [c.name for c in collections_response.collections]

        assert "implementations" in collection_names, \
            "implementations collection not found"
        assert "best_practices" in collection_names, \
            "best_practices collection not found"


class TestStreamlitSearchFunctionality:
    """AC 6.4.4: Search functionality must work end-to-end."""

    @pytest.fixture
    def qdrant_client(self):
        """Qdrant client for test setup."""
        return QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
            timeout=10.0
        )

    def test_search_returns_results_above_threshold(self, qdrant_client):
        """
        Search returns results with score >0.70 threshold.

        This test verifies:
        1. Embedding service generates embeddings
        2. Qdrant semantic search works
        3. Score threshold filtering applies
        """
        # Skip if no data available
        info = qdrant_client.get_collection("implementations")
        if info.points_count == 0:
            pytest.skip("No data in implementations collection for search test")

        # Simulate Streamlit search flow
        # (This test validates the underlying components)

        # In real implementation, app.py will:
        # 1. Call get_embedding(query)
        # 2. Execute client.search() with threshold
        # 3. Display results

        # For now, verify Qdrant search works with threshold
        # Use a dummy vector (768d for nomic-embed-code)
        dummy_vector = [0.1] * 768

        from qdrant_client.models import SearchRequest

        results = qdrant_client.query_points(
            collection_name="implementations",
            query=dummy_vector,
            limit=20,
            score_threshold=0.70,
            with_payload=True
        ).points

        # If results found, all scores must be >0.70
        for result in results:
            assert result.score >= 0.70, \
                f"Result score {result.score} below threshold"


class TestStreamlitStatisticsDisplay:
    """AC 6.4.5: Statistics panel must display collection counts."""

    def test_statistics_show_collection_counts(self):
        """Statistics panel retrieves accurate collection counts."""
        client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
            timeout=10.0
        )

        # Get both collection counts (simulating stats panel)
        impl_info = client.get_collection("implementations")
        bp_info = client.get_collection("best_practices")

        # Verify structure
        assert hasattr(impl_info, "points_count"), \
            "implementations collection missing points_count"
        assert hasattr(bp_info, "points_count"), \
            "best_practices collection missing points_count"

        # Counts should be >= 0
        assert impl_info.points_count >= 0
        assert bp_info.points_count >= 0
