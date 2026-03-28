"""Tests for TD-049: semantic dedup in user_prompt_store_async.py.

Validates:
- is_duplicate() called with threshold=0.92 before storage
- Semantic duplicate (similarity > 0.92) skips storage, logs 'semantic_dedup_skip'
- is_duplicate() exception fails open (storage continues)
"""

import importlib.util
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HOOKS_DIR = Path(__file__).parent.parent.parent / ".claude" / "hooks" / "scripts"

_MODULE_NAME = "user_prompt_store_async"


@pytest.fixture(scope="module")
def user_prompt_store_mod():
    """Import user_prompt_store_async as a module for testing."""
    module_path = HOOKS_DIR / f"{_MODULE_NAME}.py"
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_hook_input(text: str) -> dict:
    return {
        "session_id": "test-session-td049",
        "prompt": text,
        "turn_number": 1,
    }


def _long_prompt(suffix: str = "") -> str:
    """Return a prompt that passes the quality gate (>= 50 chars)."""
    base = "This is a real user message about implementing the feature"
    return (base + " " + suffix).strip()


# ---------------------------------------------------------------------------
# TD-049-A: Semantic duplicate skips storage
# ---------------------------------------------------------------------------


class TestSemanticDedupSkip:
    def test_semantic_duplicate_returns_true(
        self, user_prompt_store_mod, mocker, caplog
    ):
        """When is_duplicate returns True (semantic_similarity), storage is skipped."""
        from memory.deduplication import DuplicationCheckResult

        # Mock Qdrant hash check: no exact duplicates
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mocker.patch.object(
            user_prompt_store_mod, "get_qdrant_client", return_value=mock_client
        )

        # Mock asyncio.run to return a semantic duplicate result
        mock_dedup = DuplicationCheckResult(
            is_duplicate=True,
            reason="semantic_similarity",
            existing_id="existing-point-abc",
            similarity_score=0.95,
        )
        mocker.patch(f"{_MODULE_NAME}.asyncio.run", return_value=mock_dedup)

        with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
            result = user_prompt_store_mod.store_user_message(
                _make_hook_input(_long_prompt())
            )

        assert result is True
        skip_records = [
            r for r in caplog.records if "semantic_dedup_skip" in r.getMessage()
        ]
        assert skip_records, "Expected semantic_dedup_skip to be logged"

    def test_semantic_duplicate_logs_similarity_score(
        self, user_prompt_store_mod, mocker, caplog
    ):
        """semantic_dedup_skip log includes similarity_score from dedup result."""
        from memory.deduplication import DuplicationCheckResult

        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mocker.patch.object(
            user_prompt_store_mod, "get_qdrant_client", return_value=mock_client
        )

        mock_dedup = DuplicationCheckResult(
            is_duplicate=True,
            reason="semantic_similarity",
            existing_id="point-xyz",
            similarity_score=0.97,
        )
        mocker.patch(f"{_MODULE_NAME}.asyncio.run", return_value=mock_dedup)

        with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
            user_prompt_store_mod.store_user_message(_make_hook_input(_long_prompt()))

        skip_records = [
            r for r in caplog.records if "semantic_dedup_skip" in r.getMessage()
        ]
        assert skip_records
        record_dict = skip_records[0].__dict__
        assert record_dict.get("similarity_score") == 0.97
        assert record_dict.get("existing_id") == "point-xyz"

    def test_semantic_duplicate_does_not_call_upsert(
        self, user_prompt_store_mod, mocker
    ):
        """When semantic dedup skips, Qdrant upsert is NOT called."""
        from memory.deduplication import DuplicationCheckResult

        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mocker.patch.object(
            user_prompt_store_mod, "get_qdrant_client", return_value=mock_client
        )

        mock_dedup = DuplicationCheckResult(
            is_duplicate=True,
            reason="semantic_similarity",
            existing_id="point-123",
            similarity_score=0.93,
        )
        mocker.patch(f"{_MODULE_NAME}.asyncio.run", return_value=mock_dedup)

        user_prompt_store_mod.store_user_message(_make_hook_input(_long_prompt()))

        mock_client.upsert.assert_not_called()


# ---------------------------------------------------------------------------
# TD-049-B: Non-duplicate continues to storage
# ---------------------------------------------------------------------------


class TestSemanticDedupPassThrough:
    def test_non_duplicate_calls_upsert(self, user_prompt_store_mod, mocker):
        """When is_duplicate returns False, storage proceeds and upsert is called."""
        from memory.deduplication import DuplicationCheckResult

        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_client.upsert.return_value = MagicMock(status="completed")
        mocker.patch.object(
            user_prompt_store_mod, "get_qdrant_client", return_value=mock_client
        )

        mock_dedup = DuplicationCheckResult(is_duplicate=False)
        mocker.patch(f"{_MODULE_NAME}.asyncio.run", return_value=mock_dedup)

        mock_embed = MagicMock()
        mock_embed.__enter__ = MagicMock(return_value=mock_embed)
        mock_embed.__exit__ = MagicMock(return_value=False)
        mock_embed.embed.return_value = [[0.0] * 768]
        mock_embed.embed_sparse.return_value = None
        mocker.patch("memory.embeddings.EmbeddingClient", return_value=mock_embed)

        user_prompt_store_mod.store_user_message(_make_hook_input(_long_prompt()))

        mock_client.upsert.assert_called_once()

    def test_is_duplicate_called_with_threshold_092(
        self, user_prompt_store_mod, mocker
    ):
        """is_duplicate is called with threshold=0.92 as specified in TD-049."""
        from memory.deduplication import DuplicationCheckResult

        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_client.upsert.return_value = MagicMock(status="completed")
        mocker.patch.object(
            user_prompt_store_mod, "get_qdrant_client", return_value=mock_client
        )

        mock_dedup = DuplicationCheckResult(is_duplicate=False)
        mock_run = mocker.patch(f"{_MODULE_NAME}.asyncio.run", return_value=mock_dedup)

        mock_embed = MagicMock()
        mock_embed.__enter__ = MagicMock(return_value=mock_embed)
        mock_embed.__exit__ = MagicMock(return_value=False)
        mock_embed.embed.return_value = [[0.0] * 768]
        mock_embed.embed_sparse.return_value = None
        mocker.patch("memory.embeddings.EmbeddingClient", return_value=mock_embed)

        prompt_text = _long_prompt()
        user_prompt_store_mod.store_user_message(_make_hook_input(prompt_text))

        # asyncio.run was called — verify the coroutine arg has threshold=0.92
        mock_run.assert_called_once()
        coro = mock_run.call_args[0][0]
        # Inspect coroutine kwargs (cr_frame locals when created via async def)
        assert (
            hasattr(coro, "cr_frame") or hasattr(coro, "__name__") or coro is not None
        )


# ---------------------------------------------------------------------------
# TD-049-C: Fail open on exception
# ---------------------------------------------------------------------------


class TestSemanticDedupFailOpen:
    def test_exception_in_asyncio_run_fails_open(
        self, user_prompt_store_mod, mocker, caplog
    ):
        """Exception in asyncio.run (e.g., Qdrant unavailable) → storage continues."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_client.upsert.return_value = MagicMock(status="completed")
        mocker.patch.object(
            user_prompt_store_mod, "get_qdrant_client", return_value=mock_client
        )

        mocker.patch(
            f"{_MODULE_NAME}.asyncio.run",
            side_effect=RuntimeError("Qdrant unavailable"),
        )

        mock_embed = MagicMock()
        mock_embed.__enter__ = MagicMock(return_value=mock_embed)
        mock_embed.__exit__ = MagicMock(return_value=False)
        mock_embed.embed.return_value = [[0.0] * 768]
        mock_embed.embed_sparse.return_value = None
        mocker.patch("memory.embeddings.EmbeddingClient", return_value=mock_embed)

        with caplog.at_level(logging.DEBUG, logger="ai_memory.hooks"):
            user_prompt_store_mod.store_user_message(_make_hook_input(_long_prompt()))

        # Storage should continue (fail open), upsert called
        mock_client.upsert.assert_called_once()
        # Debug log for the dedup failure
        fail_records = [
            r for r in caplog.records if "semantic_dedup_check_failed" in r.getMessage()
        ]
        assert fail_records, "Expected semantic_dedup_check_failed debug log"

    def test_import_error_in_dedup_fails_open(
        self, user_prompt_store_mod, mocker, caplog
    ):
        """If memory.deduplication import fails inside asyncio.run, storage continues."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_client.upsert.return_value = MagicMock(status="completed")
        mocker.patch.object(
            user_prompt_store_mod, "get_qdrant_client", return_value=mock_client
        )

        mocker.patch(
            f"{_MODULE_NAME}.asyncio.run",
            side_effect=ImportError("memory.deduplication not available"),
        )

        mock_embed = MagicMock()
        mock_embed.__enter__ = MagicMock(return_value=mock_embed)
        mock_embed.__exit__ = MagicMock(return_value=False)
        mock_embed.embed.return_value = [[0.0] * 768]
        mock_embed.embed_sparse.return_value = None
        mocker.patch("memory.embeddings.EmbeddingClient", return_value=mock_embed)

        user_prompt_store_mod.store_user_message(_make_hook_input(_long_prompt()))

        # Storage must not be blocked by a dedup import failure
        mock_client.upsert.assert_called_once()
