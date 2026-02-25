"""Ollama provider for local LLM classification.

Uses Ollama API for free, local classification.

TECH-DEBT-069: LLM-based memory classification system.
"""

import json
import logging

import httpx

from ..config import MAX_OUTPUT_TOKENS, OLLAMA_BASE_URL, OLLAMA_MODEL
from ..langfuse_instrument import langfuse_generation
from .base import BaseProvider, ProviderResponse

logger = logging.getLogger("ai_memory.classifier.providers.ollama")

__all__ = ["OllamaProvider"]


class OllamaProvider(BaseProvider):
    """Ollama provider for local LLM classification."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 10,
    ):
        """Initialize Ollama provider.

        Args:
            base_url: Ollama API base URL (default: from config)
            model: Model name (default: from config)
            timeout: Request timeout in seconds
        """
        super().__init__(timeout)
        self.base_url = base_url or OLLAMA_BASE_URL
        self.model = model or OLLAMA_MODEL
        self._client = httpx.Client(timeout=timeout)

    @property
    def name(self) -> str:
        """Get provider name."""
        return "ollama"

    def is_available(self) -> bool:
        """Check if Ollama is running and accessible.

        Returns:
            True if Ollama is healthy, False otherwise
        """
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.debug("ollama_unavailable", extra={"error": str(e)})
            return False

    def classify(
        self, content: str, collection: str, current_type: str
    ) -> ProviderResponse:
        """Classify content using Ollama.

        Args:
            content: The content to classify
            collection: Target collection
            current_type: Current memory type

        Returns:
            ProviderResponse with classification results

        Raises:
            TimeoutError: If request exceeds timeout
            ConnectionError: If Ollama is unreachable
            ValueError: If response is invalid JSON
        """
        from ..prompts import build_classification_prompt

        prompt = build_classification_prompt(content, collection, current_type)

        with langfuse_generation("ollama", self.model) as gen:
            gen.update(input_text=prompt)

            try:
                response = self._client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_predict": MAX_OUTPUT_TOKENS,
                            "temperature": 0.1,
                        },
                    },
                )
                response.raise_for_status()

                result = response.json()
                response_text = result.get("response", "")

                # Parse JSON response from LLM
                classification = self._parse_response(response_text)

                input_tokens = result.get("prompt_eval_count", 0)
                output_tokens = result.get("eval_count", 0)

                gen.update(
                    output_text=response_text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    metadata={
                        "classified_type": classification["classified_type"],
                        "confidence": classification["confidence"],
                    },
                )

                logger.info(
                    "ollama_classification_success",
                    extra={
                        "type": classification["classified_type"],
                        "confidence": classification["confidence"],
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
                gen.update(level="ERROR", metadata={"error": str(e)})
                logger.error("ollama_timeout", extra={"error": str(e)})
                raise TimeoutError(f"Ollama request timed out: {e}") from e
            except httpx.HTTPError as e:
                gen.update(level="ERROR", metadata={"error": str(e)})
                logger.error("ollama_http_error", extra={"error": str(e)})
                raise ConnectionError(f"Ollama HTTP error: {e}") from e
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                gen.update(level="ERROR", metadata={"error": str(e)})
                logger.error("ollama_parse_error", extra={"error": str(e)})
                raise ValueError(f"Invalid Ollama response: {e}") from e

    def close(self):
        """Clean up HTTP client."""
        if hasattr(self, "_client"):
            self._client.close()
