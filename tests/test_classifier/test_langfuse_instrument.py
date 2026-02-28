"""Tests for classifier Langfuse instrumentation.

BUG-170 / TD-190: Verifies langfuse_instrument is a pure data-capture wrapper
with no direct Langfuse SDK interaction. All tracing goes through the
classification_worker's emit_trace_event (trace buffer path).
"""

from src.memory.classifier.langfuse_instrument import (
    _GenerationWrapper,
    _NoOpGeneration,
    langfuse_generation,
    reset_client,
)


class TestDataCaptureWrapper:
    """Test that langfuse_generation yields a data-capture wrapper."""

    def test_yields_generation_wrapper(self):
        """langfuse_generation always yields a _GenerationWrapper."""
        with langfuse_generation("ollama", "llama3.2") as gen:
            assert isinstance(gen, _GenerationWrapper)

    def test_captures_all_fields(self):
        """Wrapper captures input/output text, tokens, metadata, and level."""
        with langfuse_generation("ollama", "llama3.2") as gen:
            gen.update(
                input_text="prompt text",
                output_text="response text",
                input_tokens=100,
                output_tokens=50,
                metadata={"key": "value"},
                level="DEFAULT",
            )

        assert gen.input_text == "prompt text"
        assert gen.output_text == "response text"
        assert gen.input_tokens == 100
        assert gen.output_tokens == 50
        assert gen.metadata == {"key": "value"}
        assert gen.level == "DEFAULT"

    def test_captures_partial_updates(self):
        """Wrapper handles partial updates (only some fields set)."""
        with langfuse_generation("claude", "claude-3-haiku") as gen:
            gen.update(output_text="response only")

        assert gen.output_text == "response only"
        assert gen.input_text is None
        assert gen.input_tokens is None

    def test_metadata_merges(self):
        """Multiple update() calls merge metadata dicts."""
        with langfuse_generation("openai", "gpt-4o-mini") as gen:
            gen.update(metadata={"a": 1})
            gen.update(metadata={"b": 2})

        assert gen.metadata == {"a": 1, "b": 2}

    def test_has_start_time(self):
        """Wrapper records a start_time."""
        with langfuse_generation("openrouter", "test-model") as gen:
            assert gen.start_time is not None

    def test_all_providers_supported(self):
        """All four providers create valid wrappers."""
        for provider in ["ollama", "openrouter", "claude", "openai"]:
            with langfuse_generation(provider, "test-model") as gen:
                gen.update(input_tokens=10, output_tokens=5)
            assert gen.input_tokens == 10

    def test_trace_id_accepted(self):
        """trace_id parameter is accepted without error (interface compat)."""
        with langfuse_generation(
            "claude", "claude-3-haiku", trace_id="test-trace-123"
        ) as gen:
            gen.update(output_text="response")
        assert gen.output_text == "response"


class TestNoLangfuseSDKInteraction:
    """Test that no Langfuse SDK is called from langfuse_instrument."""

    def test_no_langfuse_import(self):
        """langfuse_generation does not import or call langfuse SDK."""
        import sys

        # Remove any cached langfuse modules
        langfuse_modules = [k for k in sys.modules if k.startswith("langfuse")]

        with langfuse_generation("ollama", "test-model") as gen:
            gen.update(input_tokens=100)

        # No new langfuse modules should have been imported
        new_langfuse = [
            k
            for k in sys.modules
            if k.startswith("langfuse") and k not in langfuse_modules
        ]
        assert new_langfuse == [], f"Unexpected langfuse imports: {new_langfuse}"


class TestNoOpGeneration:
    """Test _NoOpGeneration for backwards compatibility."""

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


class TestResetClient:
    """Test reset_client is callable (test compatibility)."""

    def test_reset_client_is_noop(self):
        """reset_client is a no-op that doesn't raise."""
        reset_client()  # Should not raise
