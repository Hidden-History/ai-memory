# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
"""Evaluator package — LLM-as-Judge evaluation engine for Langfuse traces.

Provides multi-provider LLM evaluation with Ollama, OpenRouter, Anthropic,
OpenAI, and custom OpenAI-compatible endpoints.

PLAN-012 Phase 2: Evaluation Pipeline
"""

from .provider import EvaluatorConfig
from .runner import EvaluatorRunner

__all__ = ["EvaluatorConfig", "EvaluatorRunner"]
