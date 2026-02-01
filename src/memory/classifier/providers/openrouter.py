"""OpenRouter provider for cloud LLM classification.

Uses OpenRouter API for cost-effective cloud classification.

TECH-DEBT-069: LLM-based memory classification system.
"""

import json
import logging
import os

import httpx

from ..config import MAX_OUTPUT_TOKENS, OPENROUTER_BASE_URL, OPENROUTER_MODEL
from .base import BaseProvider, ProviderResponse

logger = logging.getLogger("ai_memory.classifier.providers.openrouter")

__all__ = ["OpenRouterProvider"]


class OpenRouterProvider(BaseProvider):
    """OpenRouter provider for cloud LLM classification."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 10,
    ):
        """Initialize OpenRouter provider.

        Args:
            api_key: OpenRouter API key (default: from OPENROUTER_API_KEY env)
            base_url: OpenRouter API base URL (default: from config)
            model: Model name (default: from config)
            timeout: Request timeout in seconds
        """
        super().__init__(timeout)
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url or OPENROUTER_BASE_URL
        self.model = model or OPENROUTER_MODEL

        if not self.api_key:
            logger.warning("openrouter_no_api_key")

        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Required OpenRouter headers for proper routing
                "HTTP-Referer": "https://github.com/Hidden-History/ai-memory",
                "X-Title": "AI Memory Module",
            },
        )

    @property
    def name(self) -> str:
        """Get provider name."""
        return "openrouter"

    def is_available(self) -> bool:
        """Check if OpenRouter is accessible.

        Returns:
            True if API key is configured, False otherwise
        """
        return self.api_key is not None

    def classify(
        self, content: str, collection: str, current_type: str
    ) -> ProviderResponse:
        """Classify content using OpenRouter.

        Args:
            content: The content to classify
            collection: Target collection
            current_type: Current memory type

        Returns:
            ProviderResponse with classification results

        Raises:
            TimeoutError: If request exceeds timeout
            ConnectionError: If OpenRouter is unreachable
            ValueError: If response is invalid JSON
        """
        from ..prompts import build_classification_prompt

        if not self.api_key:
            raise ConnectionError("OpenRouter API key not configured")

        prompt = build_classification_prompt(content, collection, current_type)

        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()

            result = response.json()

            # Extract response text
            response_text = result["choices"][0]["message"]["content"]

            # Parse JSON response from LLM
            classification = self._parse_response(response_text)

            # Extract token usage
            usage = result.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)

            logger.info(
                "openrouter_classification_success",
                extra={
                    "type": classification["classified_type"],
                    "confidence": classification["confidence"],
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )

            return ProviderResponse(
                classified_type=classification["classified_type"],
                confidence=classification["confidence"],
                reasoning=classification.get("reasoning", ""),
                tags=classification.get("tags", []),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except httpx.TimeoutException as e:
            logger.error("openrouter_timeout", extra={"error": str(e)})
            raise TimeoutError(f"OpenRouter request timed out: {e}") from e
        except httpx.HTTPError as e:
            logger.error("openrouter_http_error", extra={"error": str(e)})
            raise ConnectionError(f"OpenRouter HTTP error: {e}") from e
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("openrouter_parse_error", extra={"error": str(e)})
            raise ValueError(f"Invalid OpenRouter response: {e}") from e

    def close(self):
        """Clean up HTTP client."""
        if hasattr(self, "_client"):
            self._client.close()
