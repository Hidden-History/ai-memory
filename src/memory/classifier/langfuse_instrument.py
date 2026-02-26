"""Langfuse instrumentation for classifier LLM calls.

Pure data-capture wrapper for classifier providers. Does NOT send data to
Langfuse directly. The classification_worker emits 9_classify via the
standard trace buffer path (emit_trace_event), which links to the pipeline
trace and carries session_id.

History: Phase 2 introduced direct SDK calls here, but Phase 3/Wave 1
consolidated all tracing through the trace buffer. Direct SDK calls caused
duplicate observations (TD-190) and missing session_id (BUG-170).

Kill switch: No longer relevant here (tracing controlled by trace buffer).
Graceful fallback: Always yields a data-capture wrapper.
"""

import contextlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger("ai_memory.classifier.langfuse_instrument")


def reset_client():
    """No-op. Retained for test compatibility."""
    pass


@contextlib.contextmanager
def langfuse_generation(
    provider_name: str,
    model: str,
    trace_id: str | None = None,
):
    """Context manager that captures LLM call data from classifier providers.

    Providers call gen.update() to record input/output/tokens. The captured
    data is NOT sent to Langfuse from here — classification_worker.py emits
    the 9_classify event through the standard trace buffer instead.

    Usage:
        with langfuse_generation("ollama", "llama3.2") as gen:
            # ... make LLM call ...
            gen.update(input_tokens=100, output_tokens=50, response_text="...")

    Args:
        provider_name: Provider name (ollama, openrouter, claude, openai)
        model: Model name/ID used for the call
        trace_id: Unused (retained for interface compatibility)
    """
    yield _GenerationWrapper(None, datetime.now(tz=timezone.utc))


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
