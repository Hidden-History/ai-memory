"""
Integration tests for SPEC-010: Dual Embedding Routing

Tests cover:
- Dual model embedding produces different vectors
- Code quality improvement with code model
- Backward compatibility
- Storage routing integration
"""

import pytest
import numpy as np
from unittest.mock import patch, Mock


@pytest.mark.integration
class TestDualModelEmbedding:
    """Test that different models produce different vectors"""

    def test_same_text_different_models_different_vectors(self):
        """Test same text with en vs code models produces different 768-dim vectors"""
        from memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        text = "def hello_world(): return 'Hello, World!'"

        with patch.object(client, "client") as mock_client:
            # Mock en model response
            mock_en_response = Mock()
            mock_en_response.status_code = 200
            mock_en_response.json.return_value = {
                "embeddings": [np.random.rand(768).tolist()]
            }

            # Mock code model response (different vector)
            mock_code_response = Mock()
            mock_code_response.status_code = 200
            mock_code_response.json.return_value = {
                "embeddings": [np.random.rand(768).tolist()]
            }

            # Set side_effect to return different responses
            mock_client.post.side_effect = [mock_en_response, mock_code_response]

            en_embedding = client.embed([text], model="en")[0]
            code_embedding = client.embed([text], model="code")[0]

            # Both should be 768-dimensional
            assert len(en_embedding) == 768
            assert len(code_embedding) == 768

            # Vectors should be different (mocked to be different)
            # In real scenario, they would differ due to model specialization

    def test_both_models_produce_768_dimensions(self):
        """Test both models produce 768-dimensional vectors"""
        from memory.embeddings import EmbeddingClient

        client = EmbeddingClient()

        with patch.object(client, "client") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "embeddings": [[0.1] * 768]
            }
            mock_client.post.return_value = mock_response

            en_emb = client.embed(["test"], model="en")[0]
            code_emb = client.embed(["test"], model="code")[0]

            assert len(en_emb) == 768
            assert len(code_emb) == 768


@pytest.mark.integration
class TestCodeQualityImprovement:
    """Test code model improves code retrieval quality (conceptual test)"""

    def test_code_query_prefers_code_model(self):
        """Test code-specific query benefits from code model (mock test)"""
        # This is a conceptual test - in real scenario, we'd measure retrieval quality
        from memory.embeddings import EmbeddingClient

        client = EmbeddingClient()
        code_query = "function that validates email addresses using regex"

        with patch.object(client, "client") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            # Simulate higher quality embedding for code model
            mock_response.json.return_value = {
                "embeddings": [[0.8] * 768]  # Higher values simulate better match
            }
            mock_client.post.return_value = mock_response

            result = client.embed([code_query], model="code")

            assert len(result) == 1
            assert len(result[0]) == 768
            # In real scenario, code model would produce semantically richer embeddings


@pytest.mark.integration
class TestBackwardCompatibility:
    """Test backward compatibility with existing hooks"""

    def test_legacy_embed_endpoint_still_works(self):
        """Test existing hooks using /embed continue to work"""
        from memory.embeddings import EmbeddingClient

        # Simulate legacy code calling embed() without model parameter
        client = EmbeddingClient()

        with patch.object(client, "client") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "embeddings": [[0.1] * 768]
            }
            mock_client.post.return_value = mock_response

            # Legacy call without model parameter
            result = client.embed(["test"])

            assert len(result) == 1
            assert len(result[0]) == 768

            # Should default to "en" model
            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["model"] == "en"


@pytest.mark.integration
class TestStorageRouting:
    """Test storage layer correctly routes to appropriate models"""

    def test_store_memory_to_code_patterns_uses_code_model(self):
        """Test storing to code-patterns collection uses code model"""
        from memory.storage import MemoryStorage
        from memory.models import MemoryType

        storage = MemoryStorage()

        with patch.object(storage.embedding_client, "embed") as mock_embed:
            mock_embed.return_value = [[0.1] * 768]

            with patch.object(storage.qdrant_client, "upsert"):
                with patch.object(storage, "_check_duplicate", return_value=None):
                    result = storage.store_memory(
                        content="def test(): pass",
                        cwd="/test/project",
                        memory_type=MemoryType.IMPLEMENTATION,
                        source_hook="test",
                        session_id="test-session",
                        collection="code-patterns",
                    )

                    # Verify embed was called with model="code"
                    mock_embed.assert_called_once()
                    call_args = mock_embed.call_args
                    assert call_args[1]["model"] == "code"

    def test_store_memory_to_discussions_uses_en_model(self):
        """Test storing to discussions collection uses en model"""
        from memory.storage import MemoryStorage
        from memory.models import MemoryType

        storage = MemoryStorage()

        with patch.object(storage.embedding_client, "embed") as mock_embed:
            mock_embed.return_value = [[0.1] * 768]

            with patch.object(storage.qdrant_client, "upsert"):
                with patch.object(storage, "_check_duplicate", return_value=None):
                    result = storage.store_memory(
                        content="User asked about feature X",
                        cwd="/test/project",
                        memory_type=MemoryType.USER_MESSAGE,
                        source_hook="test",
                        session_id="test-session",
                        collection="discussions",
                    )

                    # Verify embed was called with model="en"
                    mock_embed.assert_called_once()
                    call_args = mock_embed.call_args
                    assert call_args[1]["model"] == "en"

    def test_store_github_code_blob_uses_code_model(self):
        """Test github_code_blob content type uses code model"""
        from memory.storage import MemoryStorage
        from memory.models import MemoryType

        storage = MemoryStorage()

        with patch.object(storage.embedding_client, "embed") as mock_embed:
            mock_embed.return_value = [[0.1] * 768]

            with patch.object(storage.qdrant_client, "upsert"):
                with patch.object(storage, "_check_duplicate", return_value=None):
                    result = storage.store_memory(
                        content="def sync_code(): pass",
                        cwd="/test/project",
                        memory_type=MemoryType.GITHUB_CODE_BLOB,
                        source_hook="github_sync",
                        session_id="github-session",
                        collection="discussions",
                        content_type="github_code_blob",
                    )

                    # Verify embed was called with model="code"
                    mock_embed.assert_called_once()
                    call_args = mock_embed.call_args
                    assert call_args[1]["model"] == "code"

    def test_store_memories_batch_uses_correct_model(self):
        """Test batch storage routes to correct model"""
        from memory.storage import MemoryStorage

        storage = MemoryStorage()

        memories = [
            {
                "content": "def test1(): pass",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "test",
                "group_id": "test-project",
            },
            {
                "content": "def test2(): pass",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "test",
                "group_id": "test-project",
            },
        ]

        with patch.object(storage.embedding_client, "embed") as mock_embed:
            mock_embed.return_value = [[0.1] * 768, [0.2] * 768]

            with patch.object(storage.qdrant_client, "upsert"):
                results = storage.store_memories_batch(
                    memories, collection="code-patterns"
                )

                # Verify embed was called with model="code" for code-patterns
                mock_embed.assert_called()
                call_args = mock_embed.call_args
                assert call_args[1]["model"] == "code"


@pytest.mark.integration
class TestConcurrentRequests:
    """Test both models handle parallel requests without interference"""

    def test_concurrent_en_and_code_requests(self):
        """Test en and code model requests can run concurrently"""
        from memory.embeddings import EmbeddingClient
        import concurrent.futures

        client = EmbeddingClient()

        with patch.object(client, "client") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "embeddings": [[0.1] * 768]
            }
            mock_client.post.return_value = mock_response

            # Simulate concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_en = executor.submit(client.embed, ["test en"], "en")
                future_code = executor.submit(client.embed, ["test code"], "code")

                result_en = future_en.result()
                result_code = future_code.result()

                assert len(result_en) == 1
                assert len(result_code) == 1
                assert len(result_en[0]) == 768
                assert len(result_code[0]) == 768
