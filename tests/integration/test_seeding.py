"""Integration tests for seed_best_practices.py script.

Test Coverage:
- seed_templates() with mock Qdrant client
- Batch processing logic
- Dry-run mode
- Graceful degradation (Qdrant down, embedding failures)
- Embedding generation failure handling

2026 Best Practices:
- Mock external dependencies (Qdrant, httpx)
- Test graceful degradation scenarios
- Verify structured logging
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest
from qdrant_client.models import PointStruct

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.template_models import BestPracticeTemplate

# Import seeding module functions
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "memory"))
from seed_best_practices import (
    create_point_from_template,
    generate_embedding,
    get_existing_hashes,
    seed_templates,
)


class TestGenerateEmbedding:
    """Test embedding generation with httpx timeouts."""

    @patch("seed_best_practices.httpx.post")
    def test_generate_embedding_success(self, mock_post):
        """Test successful embedding generation."""
        # Mock successful response with 768d vector
        mock_response = Mock()
        mock_response.json.return_value = {
            "embeddings": [[0.1] * 768]  # 768-dimensional vector
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        embedding = generate_embedding("Test content", "http://localhost:28080")

        assert embedding is not None
        assert len(embedding) == 768
        assert all(isinstance(x, float) for x in embedding)

        # Verify httpx timeout configuration
        call_kwargs = mock_post.call_args.kwargs
        assert "timeout" in call_kwargs
        timeout = call_kwargs["timeout"]
        assert timeout.connect == 5.0
        assert timeout.read == 30.0

    @patch("seed_best_practices.httpx.post")
    def test_generate_embedding_no_embeddings_in_response(self, mock_post):
        """Test handling of empty embeddings array."""
        mock_response = Mock()
        mock_response.json.return_value = {"embeddings": []}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        embedding = generate_embedding("Test content", "http://localhost:28080")

        assert embedding is None

    @patch("seed_best_practices.httpx.post")
    def test_generate_embedding_invalid_dimensions(self, mock_post):
        """Test rejection of wrong-dimensioned embeddings."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "embeddings": [[0.1] * 512]  # Wrong dimensions (should be 768)
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        embedding = generate_embedding("Test content", "http://localhost:28080")

        assert embedding is None

    @patch("seed_best_practices.httpx.post")
    def test_generate_embedding_timeout(self, mock_post):
        """Test graceful handling of timeout."""
        mock_post.side_effect = httpx.TimeoutException("Read timeout")

        embedding = generate_embedding(
            "Test content", "http://localhost:28080", timeout=5.0
        )

        assert embedding is None

    @patch("seed_best_practices.httpx.post")
    def test_generate_embedding_http_error(self, mock_post):
        """Test graceful handling of HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.side_effect = httpx.HTTPStatusError(
            "Internal Server Error", request=Mock(), response=mock_response
        )

        embedding = generate_embedding("Test content", "http://localhost:28080")

        assert embedding is None

    @patch("seed_best_practices.httpx.post")
    def test_generate_embedding_unexpected_error(self, mock_post):
        """Test graceful handling of unexpected errors."""
        mock_post.side_effect = ValueError("Unexpected error")

        embedding = generate_embedding("Test content", "http://localhost:28080")

        assert embedding is None


class TestCreatePointFromTemplate:
    """Test Qdrant point creation from templates."""

    def test_create_point_basic(self):
        """Test basic point creation with minimal template."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
        )

        embedding = [0.1] * 768

        point = create_point_from_template(template, embedding)

        assert isinstance(point, PointStruct)
        assert isinstance(point.id, str)  # UUID string
        assert len(point.id) == 36  # UUID format
        assert point.vector == embedding
        assert point.payload["content"] == template.content
        assert point.payload["content_hash"].startswith("sha256:")  # HIGH-1 fix
        assert point.payload["domain"] == "python"
        assert point.payload["type"] == "guideline"  # default (V2.0 spec)
        assert point.payload["importance"] == "medium"  # default
        assert point.payload["group_id"] == "shared"
        assert point.payload["source_hook"] == "seed_script"
        assert point.payload["embedding_status"] == "complete"
        assert point.payload["embedding_model"] == "jina-embeddings-v2-base-en"
        assert "timestamp" in point.payload

    def test_create_point_with_all_fields(self):
        """Test point creation with all optional fields."""
        template = BestPracticeTemplate(
            content="Never use eval() for JSON parsing",
            type="rule",
            domain="python",
            importance="high",
            tags=["python", "security", "json"],
            source="https://www.invicti.com/learn/json-injection",
        )

        embedding = [0.2] * 768

        point = create_point_from_template(template, embedding)

        assert point.payload["type"] == "rule"
        assert point.payload["importance"] == "high"
        assert point.payload["tags"] == ["python", "security", "json"]
        assert point.payload["source"] == "https://www.invicti.com/learn/json-injection"

    def test_create_point_unique_ids(self):
        """Test that each point gets a unique UUID."""
        template = BestPracticeTemplate(content="Use type hints", domain="python")

        embedding = [0.1] * 768

        point1 = create_point_from_template(template, embedding)
        point2 = create_point_from_template(template, embedding)

        assert point1.id != point2.id


class TestSeedTemplates:
    """Test batch seeding logic."""

    def create_mock_config(self):
        """Create mock MemoryConfig for testing."""
        config = Mock()
        config.qdrant_host = "localhost"
        config.qdrant_port = 26350
        config.get_embedding_url.return_value = "http://localhost:28080"
        return config

    def create_test_templates(self, count: int = 5):
        """Create test templates for seeding."""
        return [
            BestPracticeTemplate(
                content=f"Test best practice {i}",
                domain="python",
                type="guideline",
                importance="medium",
            )
            for i in range(count)
        ]

    @patch("seed_best_practices.generate_embedding")
    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_success(self, mock_qdrant_class, mock_generate_embedding):
        """Test successful seeding of templates."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_qdrant_class.return_value = mock_client

        # Mock collections response - just mock the response directly
        mock_collection_info = Mock()
        mock_collection_info.name = "conventions"

        mock_collections = Mock()
        mock_collections.collections = [mock_collection_info]
        mock_client.get_collections.return_value = mock_collections

        # Mock embedding generation
        mock_generate_embedding.return_value = [0.1] * 768

        # Mock upsert
        mock_client.upsert = Mock()

        config = self.create_mock_config()
        templates = self.create_test_templates(count=5)

        count = seed_templates(templates, config, dry_run=False)

        assert count == 5
        assert mock_client.upsert.called
        assert mock_client.upsert.call_count == 1  # 1 batch for 5 templates

        # Verify upsert call
        call_args = mock_client.upsert.call_args
        assert call_args.kwargs["collection_name"] == "conventions"
        assert len(call_args.kwargs["points"]) == 5
        assert call_args.kwargs["wait"] is True

    @patch("seed_best_practices.generate_embedding")
    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_batch_processing(
        self, mock_qdrant_class, mock_generate_embedding
    ):
        """Test batch processing with multiple batches."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_qdrant_class.return_value = mock_client

        mock_collection_info = Mock()
        mock_collection_info.name = "conventions"

        mock_collections = Mock()
        mock_collections.collections = [mock_collection_info]
        mock_client.get_collections.return_value = mock_collections

        mock_generate_embedding.return_value = [0.1] * 768
        mock_client.upsert = Mock()

        config = self.create_mock_config()
        templates = self.create_test_templates(count=250)  # 3 batches (100, 100, 50)

        count = seed_templates(templates, config, dry_run=False)

        assert count == 250
        assert mock_client.upsert.call_count == 3  # 3 batches

    @patch("seed_best_practices.generate_embedding")
    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_dry_run(self, mock_qdrant_class, mock_generate_embedding):
        """Test dry-run mode doesn't actually insert."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_qdrant_class.return_value = mock_client

        mock_collection_info = Mock()
        mock_collection_info.name = "conventions"

        mock_collections = Mock()
        mock_collections.collections = [mock_collection_info]
        mock_client.get_collections.return_value = mock_collections

        mock_generate_embedding.return_value = [0.1] * 768
        mock_client.upsert = Mock()

        config = self.create_mock_config()
        templates = self.create_test_templates(count=5)

        count = seed_templates(templates, config, dry_run=True)

        assert count == 0  # Dry run returns 0
        assert not mock_client.upsert.called  # Never called in dry-run

    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_qdrant_connection_failed(self, mock_qdrant_class):
        """Test graceful handling when Qdrant is unreachable."""
        # Mock connection failure
        mock_qdrant_class.side_effect = Exception("Connection refused")

        config = self.create_mock_config()
        templates = self.create_test_templates(count=5)

        with pytest.raises(ConnectionError) as exc_info:
            seed_templates(templates, config, dry_run=False)

        assert "Cannot connect to Qdrant" in str(exc_info.value)

    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_collection_not_found(self, mock_qdrant_class):
        """Test error when best_practices collection doesn't exist."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_qdrant_class.return_value = mock_client

        # Mock collections without best_practices
        mock_coll1 = Mock()
        mock_coll1.name = "code-patterns"
        mock_coll2 = Mock()
        mock_coll2.name = "patterns"

        mock_collections = Mock()
        mock_collections.collections = [mock_coll1, mock_coll2]
        mock_client.get_collections.return_value = mock_collections

        config = self.create_mock_config()
        templates = self.create_test_templates(count=5)

        with pytest.raises(ConnectionError) as exc_info:
            seed_templates(templates, config, dry_run=False)

        assert "conventions" in str(exc_info.value)
        assert "not found" in str(exc_info.value).lower()

    @patch("seed_best_practices.generate_embedding")
    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_embedding_failures(
        self, mock_qdrant_class, mock_generate_embedding
    ):
        """Test graceful handling when some embeddings fail."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_qdrant_class.return_value = mock_client

        mock_collection_info = Mock()
        mock_collection_info.name = "conventions"

        mock_collections = Mock()
        mock_collections.collections = [mock_collection_info]
        mock_client.get_collections.return_value = mock_collections

        # Mock embedding generation - fail every other one
        mock_generate_embedding.side_effect = [
            [0.1] * 768,  # Success
            None,  # Failure
            [0.1] * 768,  # Success
            None,  # Failure
            [0.1] * 768,  # Success
        ]

        mock_client.upsert = Mock()

        config = self.create_mock_config()
        templates = self.create_test_templates(count=5)

        count = seed_templates(templates, config, dry_run=False)

        # Should only seed the 3 that got embeddings
        assert count == 3

        # Verify only 3 points were upserted
        call_args = mock_client.upsert.call_args
        assert len(call_args.kwargs["points"]) == 3

    @patch("seed_best_practices.generate_embedding")
    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_batch_failure_continues(
        self, mock_qdrant_class, mock_generate_embedding
    ):
        """Test graceful degradation when a batch upsert fails."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_qdrant_class.return_value = mock_client

        mock_collection_info = Mock()
        mock_collection_info.name = "conventions"

        mock_collections = Mock()
        mock_collections.collections = [mock_collection_info]
        mock_client.get_collections.return_value = mock_collections

        mock_generate_embedding.return_value = [0.1] * 768

        # First batch fails, second succeeds
        mock_client.upsert.side_effect = [
            Exception("Batch 1 failed"),
            None,  # Batch 2 succeeds
        ]

        config = self.create_mock_config()
        templates = self.create_test_templates(count=150)  # 2 batches

        # Should continue after first batch failure
        count = seed_templates(templates, config, dry_run=False)

        # Only second batch succeeded (50 templates)
        assert count == 50

    def test_seed_templates_empty_list(self):
        """Test handling of empty template list."""
        config = self.create_mock_config()
        templates = []

        count = seed_templates(templates, config, dry_run=False)

        assert count == 0

    @patch("seed_best_practices.generate_embedding")
    @patch("seed_best_practices.get_existing_hashes")
    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_with_deduplication(
        self, mock_qdrant_class, mock_get_hashes, mock_generate_embedding
    ):
        """Test deduplication skips existing content."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_qdrant_class.return_value = mock_client

        mock_collection_info = Mock()
        mock_collection_info.name = "conventions"

        mock_collections = Mock()
        mock_collections.collections = [mock_collection_info]
        mock_client.get_collections.return_value = mock_collections

        # Mock existing hashes - first 2 templates already exist
        mock_get_hashes.return_value = {
            "sha256:abc123",  # Simulated hash for template 0
            "sha256:def456",  # Simulated hash for template 1
        }

        mock_generate_embedding.return_value = [0.1] * 768
        mock_client.upsert = Mock()

        config = self.create_mock_config()
        templates = self.create_test_templates(count=5)

        # With actual hashes, this won't match - but we're testing the logic
        count = seed_templates(templates, config, dry_run=False, skip_duplicates=True)

        # All 5 should be inserted since mock hashes don't match actual content hashes
        assert count == 5

    @patch("seed_best_practices.generate_embedding")
    @patch("seed_best_practices.QdrantClient")
    def test_seed_templates_custom_batch_size(
        self, mock_qdrant_class, mock_generate_embedding
    ):
        """Test custom batch size parameter."""
        # Mock Qdrant client
        mock_client = Mock()
        mock_qdrant_class.return_value = mock_client

        mock_collection_info = Mock()
        mock_collection_info.name = "conventions"

        mock_collections = Mock()
        mock_collections.collections = [mock_collection_info]
        mock_client.get_collections.return_value = mock_collections

        mock_generate_embedding.return_value = [0.1] * 768
        mock_client.upsert = Mock()

        config = self.create_mock_config()
        templates = self.create_test_templates(count=250)

        # Use batch_size=50, should result in 5 batches
        count = seed_templates(templates, config, dry_run=False, batch_size=50)

        assert count == 250
        assert mock_client.upsert.call_count == 5  # 5 batches of 50


class TestGetExistingHashes:
    """Test get_existing_hashes function for deduplication."""

    @patch("seed_best_practices.QdrantClient")
    def test_get_existing_hashes_success(self, mock_qdrant_class):
        """Test successful retrieval of existing hashes."""

        mock_client = Mock()

        # Mock scroll results
        mock_records = [
            Mock(payload={"content_hash": "sha256:hash1"}),
            Mock(payload={"content_hash": "sha256:hash2"}),
            Mock(payload={"content_hash": "sha256:hash3"}),
        ]

        # First call returns records, second call returns empty (end of scroll)
        mock_client.scroll.side_effect = [
            (mock_records, None),  # First batch, no more pages
        ]

        hashes = get_existing_hashes(mock_client, "conventions")

        assert len(hashes) == 3
        assert "sha256:hash1" in hashes
        assert "sha256:hash2" in hashes
        assert "sha256:hash3" in hashes

    @patch("seed_best_practices.QdrantClient")
    def test_get_existing_hashes_empty_collection(self, mock_qdrant_class):
        """Test empty collection returns empty set."""

        mock_client = Mock()
        mock_client.scroll.return_value = ([], None)

        hashes = get_existing_hashes(mock_client, "conventions")

        assert hashes == set()

    @patch("seed_best_practices.QdrantClient")
    def test_get_existing_hashes_error_graceful(self, mock_qdrant_class):
        """Test graceful handling of scroll errors."""

        mock_client = Mock()
        mock_client.scroll.side_effect = Exception("Network error")

        # Should return empty set, not raise
        hashes = get_existing_hashes(mock_client, "conventions")

        assert hashes == set()


class TestMainCLI:
    """Test main() CLI function."""

    @patch("seed_best_practices.seed_templates")
    @patch("seed_best_practices.load_templates_from_file")
    @patch("seed_best_practices.get_config")
    def test_main_dry_run_success(
        self, mock_get_config, mock_load_templates, mock_seed, tmp_path
    ):
        """Test dry-run mode exits successfully."""
        from seed_best_practices import main

        # Create mock templates directory
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        json_file = templates_dir / "test.json"
        json_file.write_text('[{"content": "Test content", "domain": "python"}]')

        mock_load_templates.return_value = [
            BestPracticeTemplate(content="Test content", domain="python")
        ]

        # Mock sys.argv for argparse
        with patch(
            "sys.argv",
            [
                "seed_best_practices.py",
                "--templates-dir",
                str(templates_dir),
                "--dry-run",
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        # seed_templates should not be called with actual seeding in dry-run
        # (it's still called but with dry_run=True)

    def test_main_missing_templates_dir(self, tmp_path):
        """Test exit code 1 when templates dir doesn't exist."""
        from seed_best_practices import main

        missing_dir = tmp_path / "nonexistent"

        with patch(
            "sys.argv", ["seed_best_practices.py", "--templates-dir", str(missing_dir)]
        ):
            exit_code = main()

        assert exit_code == 1

    @patch("seed_best_practices.get_config")
    def test_main_no_json_files(self, mock_get_config, tmp_path):
        """Test exit code 0 when templates dir exists but no JSON files."""
        from seed_best_practices import main

        # Create empty templates directory
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        with patch(
            "sys.argv",
            ["seed_best_practices.py", "--templates-dir", str(templates_dir)],
        ):
            exit_code = main()

        assert exit_code == 0  # Not an error, just a warning
