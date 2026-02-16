"""
Unit tests for SPEC-010: Dual Embedding Routing

Tests cover:
- Client routing logic
- Storage model selection
- Config changes
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestConfig:
    """Tests for config changes (SPEC-010 Section 7)"""

    def test_config_has_dual_embedding_fields(self):
        """Test MemoryConfig has dual embedding model fields"""
        from memory.config import get_config, reset_config

        reset_config()
        config = get_config()

        assert hasattr(config, "embedding_model_dense_en")
        assert hasattr(config, "embedding_model_dense_code")
        assert "jina-embeddings-v2-base-en" in config.embedding_model_dense_en
        assert "jina-embeddings-v2-base-code" in config.embedding_model_dense_code

    def test_config_module_constants(self):
        """Test module constants for dual embedding"""
        from memory.config import EMBEDDING_MODEL_EN, EMBEDDING_MODEL_CODE

        assert EMBEDDING_MODEL_EN == "jina-embeddings-v2-base-en"
        assert EMBEDDING_MODEL_CODE == "jina-embeddings-v2-base-code"


class TestClientRouting:
    """Tests for EmbeddingClient model routing (SPEC-010 Section 4.1)"""

    def test_embed_client_default_model_is_en(self):
        """Test embed() defaults to model=en"""
        from memory.embeddings import EmbeddingClient

        client = EmbeddingClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embeddings": [[0.1] * 768]}

        with patch.object(client.client, "post", return_value=mock_response) as mock_post:
            client.embed(["test"])

            # Check that /embed/dense was called with model=en
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/embed/dense" in call_args[0][0]
            assert call_args[1]["json"]["model"] == "en"

    def test_embed_client_explicit_model_en(self):
        """Test embed() with explicit model=en"""
        from memory.embeddings import EmbeddingClient

        client = EmbeddingClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embeddings": [[0.1] * 768]}

        with patch.object(client.client, "post", return_value=mock_response) as mock_post:
            client.embed(["test"], model="en")

            call_args = mock_post.call_args
            assert call_args[1]["json"]["model"] == "en"

    def test_embed_client_explicit_model_code(self):
        """Test embed() with explicit model=code"""
        from memory.embeddings import EmbeddingClient

        client = EmbeddingClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embeddings": [[0.1] * 768]}

        with patch.object(client.client, "post", return_value=mock_response) as mock_post:
            client.embed(["test"], model="code")

            call_args = mock_post.call_args
            assert call_args[1]["json"]["model"] == "code"

    def test_storage_routing_code_patterns_uses_code_model(self):
        """Test _get_embedding_model routes code-patterns to code model"""
        from memory.storage import MemoryStorage

        storage = MemoryStorage()
        model = storage._get_embedding_model("code-patterns")

        assert model == "code"

    def test_storage_routing_github_code_blob_uses_code_model(self):
        """Test _get_embedding_model routes github_code_blob to code model"""
        from memory.storage import MemoryStorage

        storage = MemoryStorage()
        model = storage._get_embedding_model("discussions", content_type="github_code_blob")

        assert model == "code"

    def test_storage_routing_discussions_uses_en_model(self):
        """Test _get_embedding_model routes discussions to en model"""
        from memory.storage import MemoryStorage

        storage = MemoryStorage()
        model = storage._get_embedding_model("discussions")

        assert model == "en"

    def test_storage_routing_conventions_uses_en_model(self):
        """Test _get_embedding_model routes conventions to en model"""
        from memory.storage import MemoryStorage

        storage = MemoryStorage()
        model = storage._get_embedding_model("conventions")

        assert model == "en"
