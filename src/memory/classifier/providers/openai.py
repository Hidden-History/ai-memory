"""OpenAI provider for LLM classification.

Uses OpenAI API for GPT-based classification.

TECH-DEBT-069: LLM-based memory classification system.
"""

import json
import logging
import os

import httpx

from ..config import MAX_OUTPUT_TOKENS
from .base import BaseProvider, ProviderResponse

logger = logging.getLogger("ai_memory.classifier.providers.openai")

__all__ = ["OpenAIProvider"]

# Default model
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class OpenAIProvider(BaseProvider):
    """OpenAI provider for GPT-based classification."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 30,
    ):
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (default: from OPENAI_API_KEY env)
            model: Model name (default: gpt-4o-mini)
            timeout: Request timeout in seconds
        """
        super().__init__(timeout)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or OPENAI_MODEL
        self.base_url = "https://api.openai.com/v1"

        if not self.api_key:
            logger.warning("openai_no_api_key")

        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def name(self) -> str:
        """Get provider name."""
        return "openai"

    def is_available(self) -> bool:
        """Check if OpenAI is accessible.

        Returns:
            True if API key is configured, False otherwise
        """
        return self.api_key is not None

    def classify(
        self, content: str, collection: str, current_type: str
    ) -> ProviderResponse:
        """Classify content using OpenAI GPT.

        Args:
            content: The content to classify
            collection: Target collection
            current_type: Current memory type

        Returns:
            ProviderResponse with classification results

        Raises:
            TimeoutError: If request exceeds timeout
            ConnectionError: If OpenAI is unreachable
            ValueError: If response is invalid JSON
        """
        from ..prompts import build_classification_prompt

        if not self.api_key:
            raise ConnectionError("OpenAI API key not configured")

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
                "openai_classification_success",
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
            logger.error("openai_timeout", extra={"error": str(e)})
            raise TimeoutError(f"OpenAI request timed out: {e}") from e
        except httpx.HTTPError as e:
            logger.error("openai_http_error", extra={"error": str(e)})
            raise ConnectionError(f"OpenAI HTTP error: {e}") from e
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("openai_parse_error", extra={"error": str(e)})
            raise ValueError(f"Invalid OpenAI response: {e}") from e

    def close(self):
        """Clean up HTTP client."""
        if hasattr(self, "_client"):
            self._client.close()
