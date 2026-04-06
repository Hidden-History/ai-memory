"""Unit tests for classifier provider classes.

Covers ClaudeProvider, OllamaProvider, OpenAIProvider, OpenRouterProvider.
Each provider is tested for: is_available() True/False, classify() success,
classify() HTTP/SDK error handling, and provider name property.
"""

import json
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from src.memory.classifier.providers.base import ProviderResponse
from src.memory.classifier.providers.claude import ClaudeProvider
from src.memory.classifier.providers.ollama import OllamaProvider
from src.memory.classifier.providers.openai import OpenAIProvider
from src.memory.classifier.providers.openrouter import OpenRouterProvider

# Valid classification JSON reused across all provider success tests
_VALID_JSON = json.dumps(
    {
        "classified_type": "decision",
        "confidence": 0.9,
        "reasoning": "DEC prefix marks a decision",
        "tags": ["decision", "architecture"],
    }
)


class TestClaudeProvider:
    """Tests for ClaudeProvider (Anthropic SDK)."""

    def test_claude_is_available_without_key(self, monkeypatch):
        """is_available() returns False when no API key is configured."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = ClaudeProvider(api_key=None)
        assert provider.is_available() is False

    def test_claude_is_available_with_key(self):
        """is_available() returns True when API key and SDK are present."""
        anthropic_mock = MagicMock()
        with patch.dict("sys.modules", {"anthropic": anthropic_mock}):
            provider = ClaudeProvider(api_key="sk-ant-test")
        assert provider.is_available() is True

    def test_claude_classify_success(self, monkeypatch):
        """classify() returns correct ProviderResponse fields on success."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = ClaudeProvider(api_key=None)

        # Inject mock client directly — bypasses SDK installation requirement
        mock_client = Mock()
        provider._client = mock_client

        mock_msg = Mock()
        mock_msg.content = [Mock(text=_VALID_JSON)]
        mock_msg.usage = Mock(input_tokens=120, output_tokens=45)
        mock_client.messages.create.return_value = mock_msg

        result = provider.classify("DEC-031 use PostgreSQL", "discussions", "guideline")

        assert isinstance(result, ProviderResponse)
        assert result.classified_type == "decision"
        assert result.confidence == 0.9
        assert result.reasoning == "DEC prefix marks a decision"
        assert result.tags == ["decision", "architecture"]
        assert result.input_tokens == 120
        assert result.output_tokens == 45
        assert result.model_name == provider.model

    def test_claude_classify_no_client_raises_connection_error(self, monkeypatch):
        """classify() raises ConnectionError when _client is None."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = ClaudeProvider(api_key=None)
        assert provider._client is None

        with pytest.raises(ConnectionError, match="not initialized"):
            provider.classify("content", "discussions", "user_message")

    def test_claude_classify_timeout_raises_timeout_error(self, monkeypatch):
        """classify() re-raises as TimeoutError when SDK exception contains 'timeout'."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = ClaudeProvider(api_key=None)
        provider._client = Mock()
        provider._client.messages.create.side_effect = Exception(
            "request timeout occurred"
        )

        with pytest.raises(TimeoutError):
            provider.classify("content", "discussions", "user_message")

    def test_claude_classify_api_error_raises_connection_error(self, monkeypatch):
        """classify() re-raises as ConnectionError when SDK exception contains 'api'."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = ClaudeProvider(api_key=None)
        provider._client = Mock()
        provider._client.messages.create.side_effect = Exception(
            "api authentication failed 401"
        )

        with pytest.raises(ConnectionError):
            provider.classify("content", "discussions", "user_message")

    def test_claude_classify_malformed_response(self, monkeypatch):
        """classify() raises ValueError when LLM returns unparseable non-JSON text.

        ClaudeProvider has a broad except-Exception block that re-raises as ValueError
        for anything that isn't a timeout or API/auth error.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = ClaudeProvider(api_key=None)
        provider._client = Mock()

        mock_msg = Mock()
        mock_msg.content = [Mock(text="I cannot classify this content")]
        mock_msg.usage = Mock(input_tokens=50, output_tokens=5)
        provider._client.messages.create.return_value = mock_msg

        with pytest.raises(ValueError):
            provider.classify("test content", "discussions", "user_message")

    def test_claude_name(self, monkeypatch):
        """Provider name property returns 'claude'."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert ClaudeProvider(api_key=None).name == "claude"


class TestOllamaProvider:
    """Tests for OllamaProvider (httpx, local LLM — no API key required)."""

    def test_ollama_is_available_with_server(self):
        """is_available() returns True when Ollama /api/tags responds 200."""
        provider = OllamaProvider()
        mock_client = Mock()
        provider._client = mock_client
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_client.get.return_value = mock_resp

        assert provider.is_available() is True
        mock_client.get.assert_called_once_with(f"{provider.base_url}/api/tags")

    def test_ollama_is_available_without_server(self):
        """is_available() returns False when Ollama connection raises an exception."""
        provider = OllamaProvider()
        provider._client = Mock()
        provider._client.get.side_effect = Exception("connection refused")

        assert provider.is_available() is False

    def test_ollama_is_available_non_200_status(self):
        """is_available() returns False when Ollama returns non-200 status."""
        provider = OllamaProvider()
        mock_client = Mock()
        provider._client = mock_client
        mock_resp = Mock()
        mock_resp.status_code = 503
        mock_client.get.return_value = mock_resp

        assert provider.is_available() is False

    def test_ollama_classify_success(self):
        """classify() returns correct ProviderResponse fields on success."""
        provider = OllamaProvider()
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.json.return_value = {
            "response": _VALID_JSON,
            "prompt_eval_count": 80,
            "eval_count": 32,
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        result = provider.classify("DEC-031 use PostgreSQL", "discussions", "guideline")

        assert isinstance(result, ProviderResponse)
        assert result.classified_type == "decision"
        assert result.confidence == 0.9
        assert result.tags == ["decision", "architecture"]
        assert result.input_tokens == 80
        assert result.output_tokens == 32
        assert result.model_name == provider.model

    def test_ollama_classify_http_error_raises_connection_error(self):
        """classify() raises ConnectionError on httpx.HTTPStatusError from raise_for_status."""
        provider = OllamaProvider()
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=Mock(),
            response=Mock(),
        )
        mock_client.post.return_value = mock_resp

        with pytest.raises(ConnectionError):
            provider.classify("content", "discussions", "user_message")

    def test_ollama_classify_timeout_raises_timeout_error(self):
        """classify() raises TimeoutError on httpx.TimeoutException."""
        provider = OllamaProvider()
        mock_client = Mock()
        provider._client = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("timed out")

        with pytest.raises(TimeoutError):
            provider.classify("content", "discussions", "user_message")

    def test_ollama_classify_malformed_response(self):
        """classify() raises ValueError when Ollama returns unparseable non-JSON text.

        OllamaProvider catches ValueError from _parse_response via its explicit
        except-(json.JSONDecodeError, KeyError, ValueError) block and re-raises as ValueError.
        """
        provider = OllamaProvider()
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.json.return_value = {
            "response": "I cannot classify this content",
            "prompt_eval_count": 50,
            "eval_count": 20,
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        with pytest.raises(ValueError):
            provider.classify("test content", "discussions", "user_message")

    def test_ollama_name(self):
        """Provider name property returns 'ollama'."""
        assert OllamaProvider().name == "ollama"


class TestOpenAIProvider:
    """Tests for OpenAIProvider (httpx, OpenAI Chat Completions API)."""

    def test_openai_is_available_with_key(self, monkeypatch):
        """is_available() returns True when OPENAI_API_KEY is set."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        provider = OpenAIProvider()
        assert provider.is_available() is True

    def test_openai_is_available_without_key(self, monkeypatch):
        """is_available() returns False when no API key is configured."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = OpenAIProvider(api_key=None)
        assert provider.is_available() is False

    def test_openai_classify_success(self, monkeypatch):
        """classify() returns correct ProviderResponse fields on success."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        provider = OpenAIProvider(api_key="sk-test")
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": _VALID_JSON}}],
            "usage": {"prompt_tokens": 110, "completion_tokens": 40},
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        result = provider.classify("DEC-031 use PostgreSQL", "discussions", "guideline")

        assert isinstance(result, ProviderResponse)
        assert result.classified_type == "decision"
        assert result.confidence == 0.9
        assert result.tags == ["decision", "architecture"]
        assert result.input_tokens == 110
        assert result.output_tokens == 40
        assert result.model_name == provider.model

    def test_openai_classify_no_key_raises_connection_error(self, monkeypatch):
        """classify() raises ConnectionError when no API key configured."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = OpenAIProvider(api_key=None)

        with pytest.raises(ConnectionError, match="API key not configured"):
            provider.classify("content", "discussions", "user_message")

    def test_openai_classify_http_error_raises_connection_error(self, monkeypatch):
        """classify() raises ConnectionError on httpx.HTTPStatusError from raise_for_status."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        provider = OpenAIProvider(api_key="sk-test")
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=Mock(),
            response=Mock(),
        )
        mock_client.post.return_value = mock_resp

        with pytest.raises(ConnectionError):
            provider.classify("content", "discussions", "user_message")

    def test_openai_classify_timeout_raises_timeout_error(self, monkeypatch):
        """classify() raises TimeoutError on httpx.TimeoutException."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        provider = OpenAIProvider(api_key="sk-test")
        mock_client = Mock()
        provider._client = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("timed out")

        with pytest.raises(TimeoutError):
            provider.classify("content", "discussions", "user_message")

    def test_openai_classify_malformed_response(self, monkeypatch):
        """classify() raises ValueError when OpenAI returns unparseable non-JSON text.

        OpenAIProvider catches ValueError from _parse_response via its explicit
        except-(json.JSONDecodeError, KeyError, ValueError) block and re-raises as ValueError.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        provider = OpenAIProvider(api_key="sk-test")
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "I cannot classify this content"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        with pytest.raises(ValueError):
            provider.classify("test content", "discussions", "user_message")

    def test_openai_name(self, monkeypatch):
        """Provider name property returns 'openai'."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert OpenAIProvider(api_key=None).name == "openai"


class TestOpenRouterProvider:
    """Tests for OpenRouterProvider (httpx, OpenRouter Chat Completions API)."""

    def test_openrouter_is_available_with_key(self, monkeypatch):
        """is_available() returns True when OPENROUTER_API_KEY is set."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        provider = OpenRouterProvider()
        assert provider.is_available() is True

    def test_openrouter_is_available_without_key(self, monkeypatch):
        """is_available() returns False when no API key is configured."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        provider = OpenRouterProvider(api_key=None)
        assert provider.is_available() is False

    def test_openrouter_classify_success(self, monkeypatch):
        """classify() returns correct ProviderResponse fields on success."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        provider = OpenRouterProvider(api_key="or-test")
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": _VALID_JSON}}],
            "usage": {"prompt_tokens": 95, "completion_tokens": 38},
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        result = provider.classify("DEC-031 use PostgreSQL", "discussions", "guideline")

        assert isinstance(result, ProviderResponse)
        assert result.classified_type == "decision"
        assert result.confidence == 0.9
        assert result.tags == ["decision", "architecture"]
        assert result.input_tokens == 95
        assert result.output_tokens == 38
        assert result.model_name == provider.model

    def test_openrouter_classify_no_key_raises_connection_error(self, monkeypatch):
        """classify() raises ConnectionError when no API key configured."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        provider = OpenRouterProvider(api_key=None)

        with pytest.raises(ConnectionError, match="API key not configured"):
            provider.classify("content", "discussions", "user_message")

    def test_openrouter_classify_http_error_raises_connection_error(self, monkeypatch):
        """classify() raises ConnectionError on httpx.HTTPStatusError from raise_for_status."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        provider = OpenRouterProvider(api_key="or-test")
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=Mock(),
            response=Mock(),
        )
        mock_client.post.return_value = mock_resp

        with pytest.raises(ConnectionError):
            provider.classify("content", "discussions", "user_message")

    def test_openrouter_classify_timeout_raises_timeout_error(self, monkeypatch):
        """classify() raises TimeoutError on httpx.TimeoutException."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        provider = OpenRouterProvider(api_key="or-test")
        mock_client = Mock()
        provider._client = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("timed out")

        with pytest.raises(TimeoutError):
            provider.classify("content", "discussions", "user_message")

    def test_openrouter_classify_malformed_response(self, monkeypatch):
        """classify() raises ValueError when OpenRouter returns unparseable non-JSON text.

        OpenRouterProvider catches ValueError from _parse_response via its explicit
        except-(json.JSONDecodeError, KeyError, ValueError) block and re-raises as ValueError.
        """
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        provider = OpenRouterProvider(api_key="or-test")
        mock_client = Mock()
        provider._client = mock_client

        mock_resp = Mock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "I cannot classify this content"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.post.return_value = mock_resp

        with pytest.raises(ValueError):
            provider.classify("test content", "discussions", "user_message")

    def test_openrouter_name(self, monkeypatch):
        """Provider name property returns 'openrouter'."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert OpenRouterProvider(api_key=None).name == "openrouter"
