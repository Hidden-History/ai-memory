"""Unit tests for OllamaProvider — /api/ps hybrid probe and keep_alive defense.

Covers T1-T3 per Wave 2 dispatch brief §4 (BP-156 §7 test design):
  T1: is_available() model-loaded check via /api/ps (3 scenarios)
  T2: is_available() daemon-down detection
  T3: classify() keep_alive parameter at top-level JSON body

BUG-290 Factor #3 (is_available probe) and Factor #2 (cold-start defense).
"""

import json
import logging
from unittest.mock import Mock

import httpx

from src.memory.classifier.providers.ollama import OllamaProvider

# Valid classification JSON for classify() success path
_VALID_JSON = json.dumps(
    {
        "classified_type": "decision",
        "confidence": 0.9,
        "reasoning": "DEC prefix marks a decision",
        "tags": ["decision", "architecture"],
    }
)


class TestOllamaIsAvailablePsProbe:
    """T1 — is_available() hybrid /api/ps probe: 3 scenarios (BP-156 §7 T1)."""

    def test_ollama_is_available_checks_model_presence_via_ps_model_loaded(
        self, caplog
    ):
        """Scenario 1: /api/ps 200 with model in loaded list → True, no cold log."""
        provider = OllamaProvider(model="llama3.2:3b")
        provider._client = Mock()

        mock_ps_resp = Mock()
        mock_ps_resp.status_code = 200
        mock_ps_resp.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
        provider._client.get.return_value = mock_ps_resp

        with caplog.at_level(
            logging.WARNING, logger="ai_memory.classifier.providers.ollama"
        ):
            result = provider.is_available()

        assert result is True
        provider._client.get.assert_called_once_with(f"{provider.base_url}/api/ps")
        # Model loaded → no ollama_model_cold WARNING should be emitted
        cold_warnings = [
            r for r in caplog.records if r.getMessage() == "ollama_model_cold"
        ]
        assert len(cold_warnings) == 0

    def test_ollama_is_available_checks_model_presence_via_ps_model_cold(self, caplog):
        """Scenario 2: /api/ps 200 with empty models list → True + ollama_model_cold WARNING."""
        provider = OllamaProvider(model="llama3.2:3b")
        provider._client = Mock()

        mock_ps_resp = Mock()
        mock_ps_resp.status_code = 200
        mock_ps_resp.json.return_value = {"models": []}
        provider._client.get.return_value = mock_ps_resp

        with caplog.at_level(
            logging.WARNING, logger="ai_memory.classifier.providers.ollama"
        ):
            result = provider.is_available()

        assert result is True
        # Daemon up but model cold → WARNING with model + action fields
        cold_warnings = [
            r for r in caplog.records if r.getMessage() == "ollama_model_cold"
        ]
        assert len(cold_warnings) == 1
        assert cold_warnings[0].model == "llama3.2:3b"
        assert cold_warnings[0].action == "cold_start_expected_on_classify"

    def test_ollama_is_available_checks_model_presence_via_ps_fallback_to_tags(self):
        """Scenario 3: /api/ps 404 (older Ollama) → fallback to /api/tags → True."""
        provider = OllamaProvider(model="llama3.2:3b")
        provider._client = Mock()

        # /api/ps returns 404 (older Ollama daemon without /api/ps support)
        mock_ps_resp = Mock()
        mock_ps_resp.status_code = 404

        # /api/tags returns 200 (daemon is alive)
        mock_tags_resp = Mock()
        mock_tags_resp.status_code = 200

        # First get call → /api/ps, second → /api/tags
        provider._client.get.side_effect = [mock_ps_resp, mock_tags_resp]

        result = provider.is_available()

        assert result is True
        assert provider._client.get.call_count == 2
        provider._client.get.assert_any_call(f"{provider.base_url}/api/ps")
        provider._client.get.assert_any_call(f"{provider.base_url}/api/tags")


class TestOllamaIsAvailableDaemonDown:
    """T2 — is_available() daemon-down detection (BP-156 §7 T2)."""

    def test_ollama_is_available_returns_false_on_connection_error(self):
        """Both /api/ps and /api/tags raise ConnectError → is_available() returns False."""
        provider = OllamaProvider(model="llama3.2:3b")
        provider._client = Mock()

        # All get calls raise ConnectError (daemon completely unreachable)
        provider._client.get.side_effect = httpx.ConnectError("Connection refused")

        result = provider.is_available()

        assert result is False


class TestOllamaClassifyKeepAlive:
    """T3 — classify() keep_alive=-1 at top-level JSON body (BP-156 §7 T3)."""

    def test_ollama_classify_sends_keep_alive_negative_one(self):
        """classify() POSTs keep_alive=-1 as a top-level key in the JSON body."""
        provider = OllamaProvider(model="llama3.2:3b")
        provider._client = Mock()

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": _VALID_JSON,
            "prompt_eval_count": 80,
            "eval_count": 32,
        }
        mock_resp.raise_for_status.return_value = None
        provider._client.post.return_value = mock_resp

        provider.classify("DEC-031 use PostgreSQL", "discussions", "guideline")

        # Capture the actual call arguments
        assert provider._client.post.call_count == 1
        _, call_kwargs = provider._client.post.call_args
        body = call_kwargs.get("json", {})

        # keep_alive must be at top-level (NOT inside body["options"])
        assert "keep_alive" in body, "keep_alive missing from top-level JSON body"
        assert (
            body["keep_alive"] == -1
        ), f"Expected keep_alive=-1, got {body['keep_alive']}"

        # Confirm options dict is still intact (keep_alive must not replace options)
        assert "options" in body, "options dict missing from JSON body"
        assert (
            "keep_alive" not in body["options"]
        ), "keep_alive must be top-level, not inside options"
