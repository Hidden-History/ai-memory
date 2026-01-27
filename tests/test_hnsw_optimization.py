"""Unit tests for HNSW multi-tenancy optimization script.

Tests optimize_hnsw_multitenancy.py functionality with mocked Qdrant client.
Implements TECH-DEBT-064.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add scripts/memory to path for import
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "memory"))

from optimize_hnsw_multitenancy import (
    get_hnsw_config,
    optimize_collection,
)
from qdrant_client.models import HnswConfigDiff
from src.memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
)


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client with HNSW config."""
    mock_client = Mock()

    # Mock collection_exists
    mock_client.collection_exists = Mock(return_value=True)

    # Mock get_collection to return HNSW config
    mock_collection = Mock()
    mock_config = Mock()
    mock_hnsw = Mock()
    mock_hnsw.m = 16  # Default value
    mock_hnsw.payload_m = None  # Not set initially
    mock_hnsw.ef_construct = 100
    mock_hnsw.full_scan_threshold = 10000
    mock_hnsw.max_indexing_threads = 0
    mock_hnsw.on_disk = False

    mock_config.hnsw_config = mock_hnsw
    mock_collection.config = mock_config
    mock_client.get_collection = Mock(return_value=mock_collection)

    # Mock update_collection
    mock_client.update_collection = Mock()

    return mock_client


def test_get_hnsw_config_success(mock_qdrant_client):
    """Test retrieving HNSW config from collection."""
    config = get_hnsw_config(mock_qdrant_client, COLLECTION_CODE_PATTERNS)

    assert config["m"] == 16
    assert config["payload_m"] is None
    assert config["ef_construct"] == 100
    mock_qdrant_client.get_collection.assert_called_once_with(COLLECTION_CODE_PATTERNS)


def test_get_hnsw_config_collection_not_found(mock_qdrant_client):
    """Test error handling when collection doesn't exist."""
    mock_qdrant_client.get_collection.side_effect = Exception("Collection not found")

    with pytest.raises(Exception, match="Collection not found"):
        get_hnsw_config(mock_qdrant_client, "nonexistent-collection")


def test_optimize_collection_success(mock_qdrant_client):
    """Test successful HNSW optimization for a collection."""
    # Initial state: m=16, payload_m=None
    # After update: m=0, payload_m=16

    # Mock the "after" state
    def get_collection_side_effect(collection_name):
        """Return different config based on call count."""
        mock_collection = Mock()
        mock_config = Mock()
        mock_hnsw = Mock()

        # First call: before optimization
        if mock_qdrant_client.get_collection.call_count == 1:
            mock_hnsw.m = 16
            mock_hnsw.payload_m = None
        # Second call: after optimization
        else:
            mock_hnsw.m = 0
            mock_hnsw.payload_m = 16

        mock_hnsw.ef_construct = 100
        mock_hnsw.full_scan_threshold = 10000
        mock_hnsw.max_indexing_threads = 0
        mock_hnsw.on_disk = False

        mock_config.hnsw_config = mock_hnsw
        mock_collection.config = mock_config
        return mock_collection

    mock_qdrant_client.get_collection.side_effect = get_collection_side_effect

    # Run optimization
    optimize_collection(mock_qdrant_client, COLLECTION_CODE_PATTERNS, dry_run=False)

    # Verify update was called with correct parameters
    mock_qdrant_client.update_collection.assert_called_once()
    call_args = mock_qdrant_client.update_collection.call_args

    assert call_args.kwargs["collection_name"] == COLLECTION_CODE_PATTERNS
    hnsw_config = call_args.kwargs["hnsw_config"]
    assert isinstance(hnsw_config, HnswConfigDiff)
    assert hnsw_config.m == 0
    assert hnsw_config.payload_m == 16


def test_optimize_collection_dry_run(mock_qdrant_client):
    """Test dry-run mode doesn't modify collection."""
    optimize_collection(mock_qdrant_client, COLLECTION_CONVENTIONS, dry_run=True)

    # Verify update_collection was NOT called
    mock_qdrant_client.update_collection.assert_not_called()

    # Verify get_collection was called (to read current state)
    mock_qdrant_client.get_collection.assert_called_once()


def test_optimize_collection_not_exists(mock_qdrant_client):
    """Test error when collection doesn't exist."""
    mock_qdrant_client.collection_exists.return_value = False

    with pytest.raises(ValueError, match="does not exist"):
        optimize_collection(mock_qdrant_client, "nonexistent-collection")

    # Verify update was not attempted
    mock_qdrant_client.update_collection.assert_not_called()


def test_optimize_all_collections(mock_qdrant_client):
    """Test optimizing all three collections."""
    # Mock to return optimized config after update
    def get_collection_side_effect(collection_name):
        mock_collection = Mock()
        mock_config = Mock()
        mock_hnsw = Mock()

        # Return optimized config
        mock_hnsw.m = 0
        mock_hnsw.payload_m = 16
        mock_hnsw.ef_construct = 100
        mock_hnsw.full_scan_threshold = 10000
        mock_hnsw.max_indexing_threads = 0
        mock_hnsw.on_disk = False

        mock_config.hnsw_config = mock_hnsw
        mock_collection.config = mock_config
        return mock_collection

    mock_qdrant_client.get_collection.side_effect = get_collection_side_effect

    # Optimize each collection
    for collection_name in [COLLECTION_CODE_PATTERNS, COLLECTION_CONVENTIONS, COLLECTION_DISCUSSIONS]:
        optimize_collection(mock_qdrant_client, collection_name, dry_run=False)

    # Verify update_collection called 3 times
    assert mock_qdrant_client.update_collection.call_count == 3


def test_optimize_collection_update_failure(mock_qdrant_client):
    """Test error handling when update fails."""
    mock_qdrant_client.update_collection.side_effect = Exception("Update failed")

    with pytest.raises(Exception, match="Update failed"):
        optimize_collection(mock_qdrant_client, COLLECTION_DISCUSSIONS, dry_run=False)


def test_hnsw_config_verification(mock_qdrant_client):
    """Test that optimization verifies config after update."""
    call_count = 0

    def get_collection_side_effect(collection_name):
        nonlocal call_count
        call_count += 1

        mock_collection = Mock()
        mock_config = Mock()
        mock_hnsw = Mock()

        # First call: before optimization
        if call_count == 1:
            mock_hnsw.m = 16
            mock_hnsw.payload_m = None
        # Second call: after optimization (verification)
        else:
            mock_hnsw.m = 0
            mock_hnsw.payload_m = 16

        mock_hnsw.ef_construct = 100
        mock_hnsw.full_scan_threshold = 10000
        mock_hnsw.max_indexing_threads = 0
        mock_hnsw.on_disk = False

        mock_config.hnsw_config = mock_hnsw
        mock_collection.config = mock_config
        return mock_collection

    mock_qdrant_client.get_collection.side_effect = get_collection_side_effect

    # Run optimization
    optimize_collection(mock_qdrant_client, COLLECTION_CODE_PATTERNS, dry_run=False)

    # Verify get_collection called twice (before + after verification)
    assert mock_qdrant_client.get_collection.call_count == 2
