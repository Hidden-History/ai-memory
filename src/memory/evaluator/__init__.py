# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
"""Evaluator package — LLM-as-Judge evaluation engine for Langfuse traces.

Provides multi-provider LLM evaluation with Ollama, OpenRouter, Anthropic,
OpenAI, and custom OpenAI-compatible endpoints.

PLAN-012 Phase 2: Evaluation Pipeline
"""

TRACE_CONTENT_MAX = 10000  # Max chars for Langfuse input/output fields

from .provider import EvaluatorConfig
from .runner import EvaluatorRunner

__all__ = ["TRACE_CONTENT_MAX", "EvaluatorConfig", "EvaluatorRunner"]
