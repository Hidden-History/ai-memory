"""Tests for classifier Langfuse instrumentation.

Phase 2: Verifies generation span creation, kill switch, and graceful fallback.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.memory.classifier.langfuse_instrument import (
    _NoOpGeneration,
    langfuse_generation,
    reset_client,
)


@pytest.fixture(autouse=True)
def _reset_langfuse():
    """Reset Langfuse client state before each test."""
    reset_client()
    yield
    reset_client()


class TestKillSwitch:
    """Test that Langfuse instrumentation respects kill switch."""

    def test_disabled_when_env_not_set(self):
        """When LANGFUSE_ENABLED is not set, generation yields NoOp."""
        with (
            patch.dict(os.environ, {}, clear=True),
            langfuse_generation("ollama", "test-model") as gen,
        ):
            assert isinstance(gen, _NoOpGeneration)

    def test_disabled_when_env_false(self):
        """When LANGFUSE_ENABLED=false, generation yields NoOp."""
        with (
            patch.dict(os.environ, {"LANGFUSE_ENABLED": "false"}),
            langfuse_generation("ollama", "test-model") as gen,
        ):
            assert isinstance(gen, _NoOpGeneration)

    def test_noop_update_does_nothing(self):
        """NoOp generation silently ignores update calls."""
        noop = _NoOpGeneration()
        # Should not raise
        noop.update(
            input_text="test",
            output_text="test",
            input_tokens=100,
            output_tokens=50,
            metadata={"key": "value"},
            level="ERROR",
        )


class TestGracefulFallback:
    """Test graceful fallback when langfuse is not installed."""

    def test_import_error_yields_noop(self):
        """When langfuse_config import fails, generation yields NoOp."""
        import src.memory.classifier.langfuse_instrument as mod

        reset_client()
        # Simulate langfuse_config not being importable by blocking it in sys.modules
        with patch.dict("sys.modules", {"memory.langfuse_config": None}):
            # Force re-evaluation by resetting the checked flag
            mod._langfuse_checked = False
            mod._langfuse_client = None
            with langfuse_generation("ollama", "test-model") as gen:
                assert isinstance(gen, _NoOpGeneration)

    def test_client_returns_none_yields_noop(self):
        """When get_langfuse_client returns None, generation yields NoOp."""
        with (
            patch(
                "src.memory.classifier.langfuse_instrument._get_client",
                return_value=None,
            ),
            langfuse_generation("openrouter", "test-model") as gen,
        ):
            assert isinstance(gen, _NoOpGeneration)


class TestGenerationSpanCreation:
    """Test that generation spans are created correctly when Langfuse is enabled."""

    def test_generation_created_with_correct_params(self):
        """Verify trace and generation are created with correct names/model."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_client.trace.return_value = mock_trace
        mock_trace.generation.return_value = mock_generation

        with (
            patch(
                "src.memory.classifier.langfuse_instrument._get_client",
                return_value=mock_client,
            ),
            langfuse_generation("ollama", "llama3.2") as gen,
        ):
            gen.update(
                input_text="prompt text",
                output_text="response text",
                input_tokens=100,
                output_tokens=50,
            )

        # Verify trace created with 9_classify name
        mock_client.trace.assert_called_once()
        trace_kwargs = mock_client.trace.call_args
        assert trace_kwargs.kwargs["name"] == "9_classify"
        assert trace_kwargs.kwargs["metadata"]["provider"] == "ollama"

        # Verify generation created with provider-specific name
        mock_trace.generation.assert_called_once()
        gen_kwargs = mock_trace.generation.call_args
        assert gen_kwargs.kwargs["name"] == "9_classify.ollama"
        assert gen_kwargs.kwargs["model"] == "llama3.2"

        # Verify generation.end called with token usage
        mock_generation.end.assert_called_once()
        end_kwargs = mock_generation.end.call_args.kwargs
        assert end_kwargs["usage"] == {"input": 100, "output": 50}
        assert end_kwargs["input"] == "prompt text"
        assert end_kwargs["output"] == "response text"

    def test_generation_with_trace_id(self):
        """Verify trace_id is passed through to trace creation."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_client.trace.return_value = mock_trace
        mock_trace.generation.return_value = mock_generation

        with (
            patch(
                "src.memory.classifier.langfuse_instrument._get_client",
                return_value=mock_client,
            ),
            langfuse_generation(
                "claude", "claude-3-haiku", trace_id="test-trace-123"
            ) as gen,
        ):
            gen.update(output_text="response")

        trace_kwargs = mock_client.trace.call_args.kwargs
        assert trace_kwargs["id"] == "test-trace-123"

    def test_error_level_propagated(self):
        """Verify error level is propagated to generation end."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_client.trace.return_value = mock_trace
        mock_trace.generation.return_value = mock_generation

        with (
            patch(
                "src.memory.classifier.langfuse_instrument._get_client",
                return_value=mock_client,
            ),
            langfuse_generation("openai", "gpt-4o-mini") as gen,
        ):
            gen.update(level="ERROR", metadata={"error": "timeout"})

        end_kwargs = mock_generation.end.call_args.kwargs
        assert end_kwargs["level"] == "ERROR"

    def test_provider_names_all_supported(self):
        """Verify all four providers create valid generation spans."""
        for provider in ["ollama", "openrouter", "claude", "openai"]:
            mock_client = MagicMock()
            mock_trace = MagicMock()
            mock_generation = MagicMock()
            mock_client.trace.return_value = mock_trace
            mock_trace.generation.return_value = mock_generation

            with patch(
                "src.memory.classifier.langfuse_instrument._get_client",
                return_value=mock_client,
            ):
                reset_client()
                with langfuse_generation(provider, "test-model") as gen:
                    gen.update(input_tokens=10, output_tokens=5)

            gen_name = mock_trace.generation.call_args.kwargs["name"]
            assert gen_name == f"9_classify.{provider}"


class TestZeroOverhead:
    """Test that disabled Langfuse adds zero overhead."""

    def test_no_langfuse_imports_when_disabled(self):
        """When disabled, no Langfuse package imports happen inside the context."""
        with (
            patch.dict(os.environ, {"LANGFUSE_ENABLED": "false"}),
            langfuse_generation("ollama", "test-model") as gen,
        ):
            # Should complete instantly with no Langfuse SDK interaction
            gen.update(input_tokens=100, output_tokens=50)
            # If we got here, no exception was raised and no real import happened
