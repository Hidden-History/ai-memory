# LANGFUSE: V4 SDK. See LANGFUSE-INTEGRATION-SPEC.md
# This file does NOT use Langfuse directly — it calls LLM APIs for evaluation.
"""Model-agnostic evaluator provider.

Supports: Ollama, OpenRouter, Anthropic, OpenAI, and any OpenAI-compatible API.
API keys are read from environment variables ONLY — ZERO secrets in code or config.

PLAN-012 Phase 2 — Section 5.2
"""

import json
import logging
import os
import random
import time
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
    model_name: str = "gemma3:4b"
    base_url: str | None = None
    temperature: float = 0.0  # Deterministic for evaluation
    max_tokens: int = (
        4096  # Must accommodate thinking tokens + output for reasoning models
    )
    max_retries: int = 3
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
            model_name=model_cfg.get("model_name", "gemma3:4b"),
            base_url=model_cfg.get("base_url"),
            temperature=model_cfg.get("temperature", 0.0),
            max_tokens=model_cfg.get("max_tokens", 4096),
            max_retries=model_cfg.get("max_retries", 3),
        )

    def get_client(self):
        """Return a cached LLM client for the configured provider.

        Keys are read from environment variables ONLY (PM #190 security requirement).
        All cloud providers raise ValueError if the required env var is not set.

        Returns:
            openai.OpenAI for ollama/openrouter/openai/custom providers
            anthropic.Anthropic for the anthropic provider (native SDK)
        """
        if self._client is not None:
            return self._client

        if self.provider == "ollama":
            from openai import OpenAI

            api_key = os.environ.get("OLLAMA_API_KEY", "")
            # Auto-detect cloud vs local: if API key is set and no explicit
            # base_url, use Ollama cloud. Otherwise default to local.
            if self.base_url:
                base_url = self.base_url
            elif api_key:
                base_url = "https://ollama.com/v1"
            else:
                # OLLAMA_BASE_URL env var allows Docker deployments to point to
                # host.docker.internal without modifying evaluator_config.yaml.
                base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

            # Ensure /v1 suffix for OpenAI-compatible Ollama API
            if base_url and not base_url.rstrip("/").endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

            client = OpenAI(
                base_url=base_url,
                api_key=api_key or "ollama",  # Local Ollama ignores key
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

        Retries on transient HTTP errors (500, 502, 503, 429) and network
        errors up to self.max_retries times with exponential backoff + jitter.

        Args:
            prompt: The evaluation prompt (with trace input/output embedded)

        Returns:
            dict with keys: "score" (float|bool|str) and "reasoning" (str)
        """
        _RETRYABLE_STATUS_CODES = {500, 502, 503, 429}
        _BASE_DELAY = 1.0
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
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

            except (ConnectionError, TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                delay = _BASE_DELAY * (2**attempt)
                delay += random.uniform(0, 0.5 * delay)
                logger.warning(
                    "Retry %d/%d: network error (%s), waiting %.2fs",
                    attempt + 1,
                    self.max_retries,
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)

            except Exception as exc:
                last_exc = exc
                status_code = getattr(exc, "status_code", None)
                if status_code not in _RETRYABLE_STATUS_CODES:
                    raise

                if attempt >= self.max_retries:
                    break

                # For 429, honour Retry-After header if present
                delay = _BASE_DELAY * (2**attempt)
                if status_code == 429:
                    try:
                        retry_after = exc.response.headers.get("Retry-After")
                        if retry_after is not None:
                            delay = float(retry_after)
                    except AttributeError:
                        pass

                delay += random.uniform(0, 0.5 * delay)
                logger.warning(
                    "Retry %d/%d: HTTP %s, waiting %.2fs",
                    attempt + 1,
                    self.max_retries,
                    status_code,
                    delay,
                )
                time.sleep(delay)

        # All retries exhausted — reset client to force fresh connection next call
        self._client = None
        logger.error(
            "Evaluator failed after %d retries. Last error: %s",
            self.max_retries,
            last_exc,
        )
        raise last_exc


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
