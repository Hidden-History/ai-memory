# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
"""Tests for memory.evaluator.provider — EvaluatorConfig and provider client creation.

Tests each provider's client creation using mocked env vars.
Verifies that cloud providers raise ValueError when env vars are not set.

PLAN-012 Phase 2 — AC-8
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from memory.evaluator.provider import EvaluatorConfig, _parse_evaluation_response


class TestEvaluatorConfigDefaults:
    """Test EvaluatorConfig dataclass defaults."""

    def test_default_provider_is_ollama(self):
        config = EvaluatorConfig()
        assert config.provider == "ollama"

    def test_default_model_is_llama(self):
        config = EvaluatorConfig()
        assert config.model_name == "llama3.2:8b"

    def test_default_temperature_zero(self):
        config = EvaluatorConfig()
        assert config.temperature == 0.0

    def test_default_max_tokens(self):
        config = EvaluatorConfig()
        assert config.max_tokens == 4096

    def test_default_base_url_none(self):
        config = EvaluatorConfig()
        assert config.base_url is None


class TestFromYaml:
    """Test EvaluatorConfig.from_yaml() classmethod."""

    def test_loads_provider_and_model(self, tmp_path):
        yaml_content = """
evaluator_model:
  provider: openai
  model_name: gpt-4o
  temperature: 0.1
  max_tokens: 256
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml_content)

        config = EvaluatorConfig.from_yaml(str(config_file))
        assert config.provider == "openai"
        assert config.model_name == "gpt-4o"
        assert config.temperature == 0.1
        assert config.max_tokens == 256

    def test_defaults_when_fields_missing(self, tmp_path):
        yaml_content = """
evaluator_model:
  provider: ollama
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)

        config = EvaluatorConfig.from_yaml(str(config_file))
        assert config.provider == "ollama"
        assert config.model_name == "llama3.2:8b"
        assert config.temperature == 0.0

    def test_empty_evaluator_model_uses_defaults(self, tmp_path):
        yaml_content = """
evaluator_model: {}
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)

        config = EvaluatorConfig.from_yaml(str(config_file))
        assert config.provider == "ollama"


class TestOllamaProvider:
    """Test Ollama provider client creation."""

    def test_ollama_creates_openai_client(self):
        config = EvaluatorConfig(provider="ollama", model_name="llama3.2:8b")
        mock_openai_cls = MagicMock()

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            config.get_client()

        mock_openai_cls.assert_called_once()
        call_kwargs = mock_openai_cls.call_args.kwargs
        assert "localhost:11434" in call_kwargs["base_url"]
        assert call_kwargs["api_key"] == "ollama"

    def test_ollama_custom_base_url(self):
        config = EvaluatorConfig(
            provider="ollama",
            base_url="http://custom-ollama:11434/v1",
        )
        mock_openai_cls = MagicMock()

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            config.get_client()

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert call_kwargs["base_url"] == "http://custom-ollama:11434/v1"

    def test_ollama_does_not_require_env_var(self, monkeypatch):
        """Ollama should never raise ValueError — it uses a dummy 'ollama' key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        config = EvaluatorConfig(provider="ollama")
        mock_openai_cls = MagicMock()

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            # Should not raise
            config.get_client()


class TestOpenRouterProvider:
    """Test OpenRouter provider client creation."""

    def test_openrouter_uses_correct_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
        config = EvaluatorConfig(provider="openrouter", model_name="openai/gpt-4o")
        mock_openai_cls = MagicMock()

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            config.get_client()

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert "openrouter.ai" in call_kwargs["base_url"]
        assert call_kwargs["api_key"] == "test-or-key"

    def test_openrouter_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        config = EvaluatorConfig(provider="openrouter")

        with (
            patch.dict("sys.modules", {"openai": MagicMock()}),
            pytest.raises(ValueError, match="OPENROUTER_API_KEY"),
        ):
            config.get_client()


class TestAnthropicProvider:
    """Test Anthropic provider uses native SDK (NOT OpenAI compat)."""

    def test_anthropic_uses_native_sdk(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        config = EvaluatorConfig(
            provider="anthropic", model_name="claude-3-5-sonnet-20241022"
        )
        mock_anthropic_cls = MagicMock()

        with patch.dict(
            "sys.modules", {"anthropic": MagicMock(Anthropic=mock_anthropic_cls)}
        ):
            config.get_client()

        # Must use Anthropic() — NOT OpenAI()
        mock_anthropic_cls.assert_called_once_with(api_key="test-anthropic-key")

    def test_anthropic_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = EvaluatorConfig(provider="anthropic")

        with (
            patch.dict("sys.modules", {"anthropic": MagicMock()}),
            pytest.raises(ValueError, match="ANTHROPIC_API_KEY"),
        ):
            config.get_client()

    def test_anthropic_does_not_use_openai(self, monkeypatch):
        """Verify Anthropic provider never uses OpenAI client."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        config = EvaluatorConfig(provider="anthropic")
        mock_openai_cls = MagicMock()
        mock_anthropic_cls = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "openai": MagicMock(OpenAI=mock_openai_cls),
                "anthropic": MagicMock(Anthropic=mock_anthropic_cls),
            },
        ):
            config.get_client()

        # Anthropic SDK called, OpenAI SDK NOT called
        mock_anthropic_cls.assert_called_once()
        mock_openai_cls.assert_not_called()


class TestOpenAIProvider:
    """Test OpenAI provider client creation."""

    def test_openai_uses_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-oai-key")
        config = EvaluatorConfig(provider="openai", model_name="gpt-4o")
        mock_openai_cls = MagicMock()

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            config.get_client()

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert call_kwargs["api_key"] == "test-oai-key"

    def test_openai_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        config = EvaluatorConfig(provider="openai")

        with (
            patch.dict("sys.modules", {"openai": MagicMock()}),
            pytest.raises(ValueError, match="OPENAI_API_KEY"),
        ):
            config.get_client()


class TestCustomProvider:
    """Test custom OpenAI-compatible provider."""

    def test_custom_uses_evaluator_base_url(self, monkeypatch):
        monkeypatch.setenv("EVALUATOR_BASE_URL", "http://custom-llm/v1")
        monkeypatch.setenv("EVALUATOR_API_KEY", "custom-key")
        config = EvaluatorConfig(provider="custom")
        mock_openai_cls = MagicMock()

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            config.get_client()

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert call_kwargs["base_url"] == "http://custom-llm/v1"
        assert call_kwargs["api_key"] == "custom-key"

    def test_custom_defaults_api_key_to_custom_string(self, monkeypatch):
        monkeypatch.delenv("EVALUATOR_API_KEY", raising=False)
        monkeypatch.setenv("EVALUATOR_BASE_URL", "http://local/v1")
        config = EvaluatorConfig(provider="custom")
        mock_openai_cls = MagicMock()

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            config.get_client()

        call_kwargs = mock_openai_cls.call_args.kwargs
        assert call_kwargs["api_key"] == "custom"


class TestParseEvaluationResponse:
    """Test JSON parsing of LLM evaluation responses."""

    def test_parses_clean_json(self):
        content = '{"score": 0.85, "reasoning": "Relevant memory retrieved"}'
        result = _parse_evaluation_response(content)
        assert result["score"] == 0.85
        assert result["reasoning"] == "Relevant memory retrieved"

    def test_parses_json_in_code_block(self):
        content = '```json\n{"score": true, "reasoning": "Good injection"}\n```'
        result = _parse_evaluation_response(content)
        assert result["score"] is True

    def test_parses_json_in_plain_code_block(self):
        content = '```\n{"score": "correct", "reasoning": "Accurate"}\n```'
        result = _parse_evaluation_response(content)
        assert result["score"] == "correct"

    def test_returns_none_score_on_invalid_json(self):
        result = _parse_evaluation_response("This is not JSON at all")
        assert result["score"] is None
        assert "This is not JSON at all" in result["reasoning"]

    def test_empty_response_returns_none_score(self):
        result = _parse_evaluation_response("")
        assert result["score"] is None

    def test_reasoning_truncated_to_trace_content_max(self):
        long_reasoning = "x" * 20000
        content = json.dumps({"score": 0.5, "reasoning": long_reasoning})
        result = _parse_evaluation_response(content)
        assert len(result["reasoning"]) <= 10000


class TestNoHardcodedSecrets:
    """Verify zero hardcoded API keys in provider module."""

    def test_no_sk_prefix_keys(self):
        import inspect

        import memory.evaluator.provider as provider_module

        source = inspect.getsource(provider_module)
        # Should not contain patterns like api_key = "sk-..." or api_key='sk-...'
        assert "sk-" not in source

    def test_ollama_key_is_literal_ollama(self):
        """The ONLY hardcoded key is 'ollama' for the local Ollama provider."""
        config = EvaluatorConfig(provider="ollama")
        mock_openai_cls = MagicMock()

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            config.get_client()

        call_kwargs = mock_openai_cls.call_args.kwargs
        # The ONLY acceptable hardcoded key
        assert call_kwargs["api_key"] == "ollama"
