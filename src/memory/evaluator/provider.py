# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
# This file does NOT use Langfuse directly — it calls LLM APIs for evaluation.
"""Model-agnostic evaluator provider.

Supports: Ollama, OpenRouter, Anthropic, OpenAI, and any OpenAI-compatible API.
API keys are read from environment variables ONLY — ZERO secrets in code or config.

PLAN-012 Phase 2 — Section 5.2
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from . import TRACE_CONTENT_MAX

logger = logging.getLogger(__name__)


@dataclass
class EvaluatorConfig:
    """Configuration for the LLM evaluator provider.

    API keys are NEVER stored here — they are read from os.environ at runtime.
    """

    provider: Literal["ollama", "openrouter", "anthropic", "openai", "custom"] = (
        "ollama"
    )
    model_name: str = "llama3.2:8b"
    base_url: str | None = None
    temperature: float = 0.0  # Deterministic for evaluation
    max_tokens: int = (
        4096  # Must accommodate thinking tokens + output for reasoning models
    )
    _client: Any = field(default=None, init=False, repr=False)

    @classmethod
    def from_yaml(cls, path: str) -> "EvaluatorConfig":
        """Load EvaluatorConfig from the evaluator_model section of a YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        model_cfg = data.get("evaluator_model", {})
        return cls(
            provider=model_cfg.get("provider", "ollama"),
            model_name=model_cfg.get("model_name", "llama3.2:8b"),
            base_url=model_cfg.get("base_url"),
            temperature=model_cfg.get("temperature", 0.0),
            max_tokens=model_cfg.get("max_tokens", 4096),
        )

    def get_client(self):
        """Return a cached LLM client for the configured provider.

        Keys are read from environment variables ONLY (PM #190 security requirement).
        All cloud providers raise ValueError if the required env var is not set.

        Returns:
            openai.OpenAI for ollama/openrouter/openai/custom providers
            anthropic.Anthropic for the anthropic provider (native SDK)
        """
        if self._client:
            return self._client

        if self.provider == "ollama":
            from openai import OpenAI

            client = OpenAI(
                base_url=self.base_url or "http://localhost:11434/v1",
                api_key=os.environ.get(
                    "OLLAMA_API_KEY", "ollama"
                ),  # Cloud: set OLLAMA_API_KEY; local: ignored
            )

        elif self.provider == "openrouter":
            from openai import OpenAI

            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY environment variable not set. "
                    "Set it before using the openrouter provider."
                )
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )

        elif self.provider == "anthropic":
            # PM #190 FIX: Use native Anthropic SDK — OpenAI compat layer loses features
            from anthropic import Anthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Set it before using the anthropic provider."
                )
            client = Anthropic(api_key=api_key)

        elif self.provider == "openai":
            from openai import OpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY environment variable not set. "
                    "Set it before using the openai provider."
                )
            client = OpenAI(api_key=api_key)

        else:  # custom — any OpenAI-compatible endpoint
            from openai import OpenAI

            base_url = self.base_url or os.environ.get("EVALUATOR_BASE_URL")
            api_key = os.environ.get("EVALUATOR_API_KEY", "custom")
            client = OpenAI(
                base_url=base_url,
                api_key=api_key,
            )

        self._client = client
        return self._client

    def evaluate(self, prompt: str) -> dict:
        """Send prompt to LLM and return parsed evaluation result.

        Args:
            prompt: The evaluation prompt (with trace input/output embedded)

        Returns:
            dict with keys: "score" (float|bool|str) and "reasoning" (str)
        """
        client = self.get_client()

        if self.provider == "anthropic":
            # Native Anthropic SDK uses client.messages.create()
            response = client.messages.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text
        else:
            # All other providers use OpenAI-compatible chat.completions.create()
            response = client.chat.completions.create(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            msg = response.choices[0].message
            content = msg.content
            # Thinking models (e.g., Qwen3) may put output in reasoning field
            if not content and hasattr(msg, "reasoning") and msg.reasoning:
                content = msg.reasoning

        return _parse_evaluation_response(content)


def _parse_evaluation_response(content: str) -> dict:
    """Parse LLM response JSON, returning score and reasoning.

    Handles both clean JSON and JSON embedded in markdown code blocks.
    Falls back to {"score": None, "reasoning": content} on parse failure.
    """
    if not content:
        return {"score": None, "reasoning": "Empty response from evaluator"}

    # Strip markdown code fences if present
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        inner = "\n".join(lines[1:])
        inner = inner.rsplit("```", 1)[0].strip()
        text = inner

    try:
        result = json.loads(text)
        return {
            "score": result.get("score"),
            "reasoning": str(result.get("reasoning", ""))[:TRACE_CONTENT_MAX],
        }
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse evaluation response as JSON: %s", exc)
        return {"score": None, "reasoning": content[:TRACE_CONTENT_MAX]}
