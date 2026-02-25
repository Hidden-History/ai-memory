"""Langfuse instrumentation for classifier LLM calls.

Provides generation-span wrappers for all classifier LLM providers.
Phase 2: LLM tracing (SPEC-021, pipeline step 9_classify).

Kill switch: LANGFUSE_ENABLED=true required. Zero overhead when disabled.
Graceful fallback: If langfuse package not installed, all functions are no-ops.
"""

import contextlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger("ai_memory.classifier.langfuse_instrument")

# Lazy-loaded Langfuse client (None = not yet attempted, False = disabled/unavailable)
_langfuse_client = None
_langfuse_checked = False


def _get_client():
    """Get Langfuse client singleton, respecting kill switch.

    Returns None if disabled, unavailable, or package not installed.
    Uses langfuse_config.is_langfuse_enabled() for kill switch.
    """
    global _langfuse_client, _langfuse_checked

    if _langfuse_checked:
        return _langfuse_client

    _langfuse_checked = True

    try:
        from memory.langfuse_config import get_langfuse_client, is_langfuse_enabled

        if not is_langfuse_enabled():
            _langfuse_client = None
            return None

        _langfuse_client = get_langfuse_client()
        if _langfuse_client:
            logger.info("langfuse_classifier_instrumentation_enabled")
        return _langfuse_client
    except ImportError:
        logger.debug("langfuse_config_not_available")
        _langfuse_client = None
        return None
    except Exception as e:
        logger.debug("langfuse_client_init_failed", extra={"error": str(e)})
        _langfuse_client = None
        return None


def reset_client():
    """Reset client for testing."""
    global _langfuse_client, _langfuse_checked
    _langfuse_client = None
    _langfuse_checked = False


@contextlib.contextmanager
def langfuse_generation(
    provider_name: str,
    model: str,
    trace_id: str | None = None,
):
    """Context manager that creates a Langfuse generation span for an LLM call.

    Usage:
        with langfuse_generation("ollama", "llama3.2") as gen:
            # ... make LLM call ...
            gen.update(input_tokens=100, output_tokens=50, response_text="...")

    When Langfuse is disabled or unavailable, yields a no-op object.

    Args:
        provider_name: Provider name (ollama, openrouter, claude, openai)
        model: Model name/ID used for the call
        trace_id: Optional trace ID for linking to existing trace
    """
    client = _get_client()

    if client is None:
        # No-op path: yield a dummy that silently ignores updates
        yield _NoOpGeneration()
        return

    start_time = datetime.now(tz=timezone.utc)
    generation = None

    try:
        # Create a trace for this classification call
        trace_kwargs = {
            "name": "9_classify",
            "metadata": {"provider": provider_name},
        }
        if trace_id:
            trace_kwargs["id"] = trace_id

        trace = client.trace(**trace_kwargs)

        # Create generation span within the trace
        generation = trace.generation(
            name=f"9_classify.{provider_name}",
            model=model,
            metadata={
                "provider": provider_name,
            },
        )

        wrapper = _GenerationWrapper(generation, start_time)
        yield wrapper

        # End the generation with captured data
        end_kwargs = {
            "end_time": datetime.now(tz=timezone.utc),
        }
        if wrapper.input_text is not None:
            end_kwargs["input"] = wrapper.input_text
        if wrapper.output_text is not None:
            end_kwargs["output"] = wrapper.output_text
        if wrapper.input_tokens is not None or wrapper.output_tokens is not None:
            usage = {}
            if wrapper.input_tokens is not None:
                usage["input"] = wrapper.input_tokens
            if wrapper.output_tokens is not None:
                usage["output"] = wrapper.output_tokens
            end_kwargs["usage"] = usage
        if wrapper.metadata:
            end_kwargs["metadata"] = {
                "provider": provider_name,
                **wrapper.metadata,
            }
        if wrapper.level is not None:
            end_kwargs["level"] = wrapper.level

        generation.end(**end_kwargs)

    except Exception as e:
        # Langfuse errors must never break classification — re-raise original
        logger.debug(
            "langfuse_generation_error",
            extra={"provider": provider_name, "error": str(e)},
        )
        if generation:
            with contextlib.suppress(Exception):
                generation.end(
                    level="ERROR",
                    status_message=str(e),
                )
        raise


class _GenerationWrapper:
    """Mutable wrapper to capture generation data from provider calls."""

    __slots__ = (
        "input_text",
        "input_tokens",
        "level",
        "metadata",
        "output_text",
        "output_tokens",
        "start_time",
    )

    def __init__(self, generation, start_time: datetime):
        self.start_time = start_time
        self.input_text = None
        self.output_text = None
        self.input_tokens = None
        self.output_tokens = None
        self.metadata = {}
        self.level = None

    def update(
        self,
        input_text: str | None = None,
        output_text: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        metadata: dict | None = None,
        level: str | None = None,
    ):
        """Update generation data. Call after LLM response is received."""
        if input_text is not None:
            self.input_text = input_text
        if output_text is not None:
            self.output_text = output_text
        if input_tokens is not None:
            self.input_tokens = input_tokens
        if output_tokens is not None:
            self.output_tokens = output_tokens
        if metadata:
            self.metadata.update(metadata)
        if level is not None:
            self.level = level


class _NoOpGeneration:
    """No-op generation that silently ignores all updates."""

    __slots__ = ()

    def update(self, **kwargs):
        pass
