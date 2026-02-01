"""Claude (Anthropic) provider for LLM classification.

Uses Anthropic SDK for reliable classification fallback.

TECH-DEBT-069: LLM-based memory classification system.
"""

import logging
import os

from ..config import ANTHROPIC_MODEL, MAX_OUTPUT_TOKENS
from .base import BaseProvider, ProviderResponse

logger = logging.getLogger("ai_memory.classifier.providers.claude")

__all__ = ["ClaudeProvider"]


class ClaudeProvider(BaseProvider):
    """Claude/Anthropic provider for LLM classification."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 10,
    ):
        """Initialize Claude provider.

        Args:
            api_key: Anthropic API key (default: from ANTHROPIC_API_KEY env)
            model: Model name (default: from config)
            timeout: Request timeout in seconds
        """
        super().__init__(timeout)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or ANTHROPIC_MODEL

        if not self.api_key:
            logger.warning("claude_no_api_key")
            self._client = None
        else:
            try:
                from anthropic import Anthropic

                self._client = Anthropic(
                    api_key=self.api_key,
                    timeout=timeout,
                )
            except ImportError:
                logger.error("anthropic_sdk_not_installed")
                self._client = None

    @property
    def name(self) -> str:
        """Get provider name."""
        return "claude"

    def is_available(self) -> bool:
        """Check if Claude is accessible.

        Returns:
            True if API key is configured and SDK is available, False otherwise
        """
        return self._client is not None

    def classify(
        self, content: str, collection: str, current_type: str
    ) -> ProviderResponse:
        """Classify content using Claude.

        Args:
            content: The content to classify
            collection: Target collection
            current_type: Current memory type

        Returns:
            ProviderResponse with classification results

        Raises:
            TimeoutError: If request exceeds timeout
            ConnectionError: If Claude is unreachable
            ValueError: If response is invalid JSON
        """
        from ..prompts import build_classification_prompt

        if not self._client:
            raise ConnectionError(
                "Claude client not initialized (missing API key or SDK)"
            )

        prompt = build_classification_prompt(content, collection, current_type)

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            # Extract response text
            response_text = response.content[0].text

            # Parse JSON response from LLM
            classification = self._parse_response(response_text)

            # Extract token usage
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            logger.info(
                "claude_classification_success",
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

        except Exception as e:
            # Handle various Anthropic SDK exceptions
            error_type = type(e).__name__
            if "timeout" in str(e).lower():
                logger.error("claude_timeout", extra={"error": str(e)})
                raise TimeoutError(f"Claude request timed out: {e}") from e
            elif "api" in str(e).lower() or "auth" in str(e).lower():
                logger.error("claude_api_error", extra={"error": str(e)})
                raise ConnectionError(f"Claude API error: {e}") from e
            else:
                logger.error(
                    "claude_error", extra={"error": str(e), "type": error_type}
                )
                raise ValueError(f"Claude error: {e}") from e
