"""Unit tests for error_store_async.py hook.

Tests async storage of error patterns to the code-patterns collection.
Covers: format_error_content utility, async storage routing, Qdrant unavailable
handling, and main() entry point robustness.
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add tests dir for mock imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add hook scripts dir so module can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".claude/hooks/scripts"))

import error_store_async as esav


@pytest.fixture
def mock_config():
    """Minimal MemoryConfig mock — disables security scan and hybrid search."""
    config = MagicMock()
    config.embedding_dimension = 768
    config.security_scanning_enabled = False
    config.hybrid_search_enabled = False
    return config


@pytest.fixture
def mock_async_qdrant():
    """AsyncQdrantClient mock with async upsert and close methods."""
    client = MagicMock()
    client.upsert = AsyncMock(return_value={"status": "completed"})
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_embedding():
    """EmbeddingClient mock returning a fixed 768-dim vector."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.embed = MagicMock(return_value=[[0.1] * 768])
    return mock


@pytest.fixture
def error_context():
    """A realistic error context dict as produced by the capture hook."""
    return {
        "session_id": "test-session-esav-001",
        "cwd": "/mnt/e/projects/dev-ai-memory/ai-memory",
        "command": "pytest tests/unit/test_hooks_common.py -v",
        "error_message": "ModuleNotFoundError: No module named 'memory.hooks_common'",
        "exit_code": 1,
        "output": "FAILED tests/unit/test_hooks_common.py::TestHooksCommon::test_setup",
        "file_references": [{"file": "tests/unit/test_hooks_common.py", "line": 42}],
    }


class TestFormatErrorContent:
    """Tests for the format_error_content pure utility function."""

    def test_formats_basic_error_fields(self, error_context):
        """format_error_content includes command, error message, and exit code."""
        result = esav.format_error_content(error_context)
        assert "[error_pattern]" in result
        assert error_context["command"] in result
        assert error_context["error_message"] in result
        assert str(error_context["exit_code"]) in result

    def test_formats_file_references(self, error_context):
        """format_error_content includes file references with line numbers."""
        result = esav.format_error_content(error_context)
        assert "tests/unit/test_hooks_common.py" in result
        assert "42" in result

    def test_handles_empty_error_context(self):
        """format_error_content returns at least the header for a minimal dict."""
        result = esav.format_error_content({})
        assert "[error_pattern]" in result


class TestErrorStoreAsync:
    """Tests for error_store_async.store_error_pattern_async."""

    @pytest.mark.asyncio
    async def test_stores_to_code_patterns_collection(
        self, mock_async_qdrant, mock_config, mock_embedding, error_context
    ):
        """Error pattern is stored to the code-patterns collection.

        Verifies collection routing and that upsert is called once.
        """
        mock_qdrant_cls = MagicMock(return_value=mock_async_qdrant)
        with (
            patch.object(esav, "AsyncQdrantClient", mock_qdrant_cls),
            patch.object(esav, "get_config", return_value=mock_config),
            patch("memory.embeddings.EmbeddingClient", return_value=mock_embedding),
            patch.object(esav, "log_to_activity"),
            patch.object(esav, "queue_operation"),
            patch.object(esav, "detect_project", return_value="test-project"),
        ):
            await esav.store_error_pattern_async(error_context)

        mock_async_qdrant.upsert.assert_called_once()
        call_kwargs = mock_async_qdrant.upsert.call_args
        # collection_name may be positional or keyword
        args, kwargs = call_kwargs
        collection = kwargs.get("collection_name") or (args[0] if args else None)
        assert collection == "code-patterns"

    @pytest.mark.asyncio
    async def test_qdrant_unavailable_queues_without_crash(
        self, mock_config, error_context
    ):
        """ConnectionRefusedError is caught; operation is queued; no exception propagates.

        The hook must always exit cleanly — Qdrant downtime degrades to queuing.
        """
        failing_qdrant = MagicMock()
        failing_qdrant.upsert = AsyncMock(side_effect=ConnectionRefusedError("refused"))
        failing_qdrant.close = AsyncMock()
        mock_qdrant_cls = MagicMock(return_value=failing_qdrant)

        queue_mock = MagicMock()
        with (
            patch.object(esav, "AsyncQdrantClient", mock_qdrant_cls),
            patch.object(esav, "get_config", return_value=mock_config),
            patch("memory.embeddings.EmbeddingClient") as embed_cls,
            patch.object(esav, "log_to_activity"),
            patch.object(esav, "queue_operation", queue_mock),
            patch.object(esav, "detect_project", return_value="test-project"),
        ):
            # Embedding mock: context manager returning embed client
            embed_mock = MagicMock()
            embed_mock.__enter__ = MagicMock(return_value=embed_mock)
            embed_mock.__exit__ = MagicMock(return_value=False)
            embed_mock.embed = MagicMock(return_value=[[0.1] * 768])
            embed_cls.return_value = embed_mock

            # store_error_pattern_async must not raise
            await esav.store_error_pattern_async(error_context)

        queue_mock.assert_called_once()

    def test_main_returns_0_on_malformed_stdin(self):
        """main() returns 0 (never crashes Claude) even on invalid JSON stdin.

        Hooks must always exit 0 per §1.2 Principle 4.
        """
        with patch.object(sys, "stdin", io.StringIO("{{bad json")):
            result = esav.main()
        assert result == 0

    def test_main_returns_0_on_valid_input(
        self, mock_async_qdrant, mock_config, mock_embedding, error_context
    ):
        """main() processes valid error context from stdin and returns 0."""
        mock_qdrant_cls = MagicMock(return_value=mock_async_qdrant)
        with (
            patch.object(sys, "stdin", io.StringIO(json.dumps(error_context))),
            patch.object(esav, "AsyncQdrantClient", mock_qdrant_cls),
            patch.object(esav, "get_config", return_value=mock_config),
            patch("memory.embeddings.EmbeddingClient", return_value=mock_embedding),
            patch.object(esav, "log_to_activity"),
            patch.object(esav, "queue_operation"),
            patch.object(esav, "detect_project", return_value="test-project"),
            patch.object(esav, "get_hook_timeout", return_value=60),
        ):
            result = esav.main()
        assert result == 0
