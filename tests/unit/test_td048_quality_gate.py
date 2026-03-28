"""Tests for TD-048: quality gate upgrade in agent_response_store_async.py.

Validates:
- 50-char minimum replaces 4-word minimum
- Acknowledgment pattern filter (case-insensitive)
- Filtered items logged with specific reason: "too_short" or "acknowledgment_pattern"
"""

import importlib.util
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HOOKS_DIR = Path(__file__).parent.parent.parent / ".claude" / "hooks" / "scripts"

_MODULE_NAME = "agent_response_store_async"


@pytest.fixture(scope="module")
def agent_store_mod():
    """Import agent_response_store_async as a module for testing."""
    module_path = HOOKS_DIR / f"{_MODULE_NAME}.py"
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_store_data(text: str) -> dict:
    return {"session_id": "test-session-td048", "response_text": text, "turn_number": 1}


# ---------------------------------------------------------------------------
# TD-048-A: 50-char minimum replaces 4-word minimum
# ---------------------------------------------------------------------------


class TestCharMinimum:
    def test_49_chars_filtered_as_too_short(self, agent_store_mod, caplog):
        """Content with 49 chars (no ack pattern) → filtered, reason 'too_short'."""
        text = "x" * 49
        with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
            result = agent_store_mod.store_agent_response(_make_store_data(text))
        assert result is True
        gate_records = [
            r for r in caplog.records if "quality_gate_skip" in r.getMessage()
        ]
        assert gate_records, "Expected quality_gate_skip to be logged"
        assert gate_records[0].__dict__.get("reason") == "too_short"

    def test_50_chars_passes_char_gate(self, agent_store_mod, mocker):
        """Content with exactly 50 chars (not an ack) is NOT caught by char minimum."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_client.upsert.return_value = MagicMock(status="completed")
        mocker.patch.object(
            agent_store_mod, "get_qdrant_client", return_value=mock_client
        )

        # Also mock embedding so the function doesn't fail trying to reach embedding service
        mock_embed = MagicMock()
        mock_embed.__enter__ = MagicMock(return_value=mock_embed)
        mock_embed.__exit__ = MagicMock(return_value=False)
        mock_embed.embed.return_value = [[0.0] * 768]
        mock_embed.embed_sparse.return_value = None
        mocker.patch("memory.embeddings.EmbeddingClient", return_value=mock_embed)

        text = "A" * 50  # Exactly 50 non-ack chars
        agent_store_mod.store_agent_response(_make_store_data(text))
        # Function should NOT return early from quality gate; Qdrant was called
        mock_client.scroll.assert_called_once()

    def test_4_words_under_50_chars_filtered(self, agent_store_mod, caplog):
        """Content with 4+ words but < 50 chars is now filtered (old 4-word rule removed)."""
        text = "one two three four"  # 4 words, 18 chars — passed old check, fails new
        with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
            result = agent_store_mod.store_agent_response(_make_store_data(text))
        assert result is True
        gate_records = [
            r for r in caplog.records if "quality_gate_skip" in r.getMessage()
        ]
        assert gate_records, "Expected quality_gate_skip for short 4-word response"
        assert gate_records[0].__dict__.get("reason") == "too_short"

    def test_empty_response_filtered_as_too_short(self, agent_store_mod, caplog):
        """Empty response → filtered, reason 'too_short'."""
        with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
            result = agent_store_mod.store_agent_response(_make_store_data(""))
        assert result is True
        gate_records = [
            r for r in caplog.records if "quality_gate_skip" in r.getMessage()
        ]
        assert gate_records
        assert gate_records[0].__dict__.get("reason") == "too_short"

    def test_whitespace_only_filtered_as_too_short(self, agent_store_mod, caplog):
        """Whitespace-only response → filtered, reason 'too_short'."""
        with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
            result = agent_store_mod.store_agent_response(_make_store_data("   \n\t  "))
        assert result is True
        gate_records = [
            r for r in caplog.records if "quality_gate_skip" in r.getMessage()
        ]
        assert gate_records
        assert gate_records[0].__dict__.get("reason") == "too_short"


# ---------------------------------------------------------------------------
# TD-048-B: Acknowledgment pattern filter
# ---------------------------------------------------------------------------


class TestAckPatternFilter:
    """Verify every listed ack phrase is caught and logged as 'acknowledgment_pattern'."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "I understand",
            "Got it",
            "Sure",
            "OK",
            "Understood",
            "Will do",
            "Noted",
            "Acknowledged",
            "Thanks",
            "Thank you",
            "Yes",
            "No",
            "Agreed",
            "Right",
            "Correct",
            "Done",
            "Nothing to add",
        ],
    )
    def test_ack_phrase_filtered(self, agent_store_mod, caplog, phrase):
        """Each ack phrase → filtered with reason 'acknowledgment_pattern'."""
        with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
            result = agent_store_mod.store_agent_response(_make_store_data(phrase))
        assert result is True
        gate_records = [
            r for r in caplog.records if "quality_gate_skip" in r.getMessage()
        ]
        assert gate_records, f"Expected quality_gate_skip for phrase: {phrase!r}"
        assert gate_records[0].__dict__.get("reason") == "acknowledgment_pattern"

    def test_ack_case_insensitive(self, agent_store_mod, caplog):
        """Ack filter is case-insensitive: 'ok', 'OK', 'Ok' all filtered."""
        for variant in ("ok", "OK", "Ok", "oK"):
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
                agent_store_mod.store_agent_response(_make_store_data(variant))
            gate_records = [
                r for r in caplog.records if "quality_gate_skip" in r.getMessage()
            ]
            assert gate_records, f"Expected filter for variant {variant!r}"
            assert gate_records[0].__dict__.get("reason") == "acknowledgment_pattern"

    def test_ack_with_trailing_punctuation_filtered(self, agent_store_mod, caplog):
        """'Noted.' (with period) → filtered as acknowledgment_pattern."""
        with caplog.at_level(logging.INFO, logger="ai_memory.hooks"):
            result = agent_store_mod.store_agent_response(_make_store_data("Noted."))
        assert result is True
        # May be too_short (6 chars) — both are valid; verify it IS filtered
        gate_records = [
            r for r in caplog.records if "quality_gate_skip" in r.getMessage()
        ]
        assert gate_records

    def test_substantive_content_passes_ack_gate(self, agent_store_mod, mocker):
        """Long non-ack response is NOT caught by ack filter."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_client.upsert.return_value = MagicMock(status="completed")
        mocker.patch.object(
            agent_store_mod, "get_qdrant_client", return_value=mock_client
        )

        mock_embed = MagicMock()
        mock_embed.__enter__ = MagicMock(return_value=mock_embed)
        mock_embed.__exit__ = MagicMock(return_value=False)
        mock_embed.embed.return_value = [[0.0] * 768]
        mock_embed.embed_sparse.return_value = None
        mocker.patch("memory.embeddings.EmbeddingClient", return_value=mock_embed)

        text = "The implementation uses a retry decorator with exponential backoff for resilience"
        agent_store_mod.store_agent_response(_make_store_data(text))
        # Qdrant was consulted — quality gate passed
        mock_client.scroll.assert_called_once()

    def test_ack_prefix_in_longer_response_passes(self, agent_store_mod, mocker):
        """'I understand your requirement...' is NOT an ack — too long and substantive."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_client.upsert.return_value = MagicMock(status="completed")
        mocker.patch.object(
            agent_store_mod, "get_qdrant_client", return_value=mock_client
        )

        mock_embed = MagicMock()
        mock_embed.__enter__ = MagicMock(return_value=mock_embed)
        mock_embed.__exit__ = MagicMock(return_value=False)
        mock_embed.embed.return_value = [[0.0] * 768]
        mock_embed.embed_sparse.return_value = None
        mocker.patch("memory.embeddings.EmbeddingClient", return_value=mock_embed)

        text = (
            "I understand your requirements and will implement the feature accordingly"
        )
        agent_store_mod.store_agent_response(_make_store_data(text))
        mock_client.scroll.assert_called_once()
