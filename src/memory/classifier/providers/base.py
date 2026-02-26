"""Base provider abstract class for LLM classification.

Defines the interface that all classification providers must implement.

TECH-DEBT-069: LLM-based memory classification system.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger("ai_memory.classifier.providers")

__all__ = ["BaseProvider", "ProviderResponse"]


@dataclass
class ProviderResponse:
    """Response from a classification provider.

    Attributes:
        classified_type: The classified memory type
        confidence: Confidence score (0.0-1.0)
        reasoning: Brief explanation of the classification
        tags: List of relevant tags extracted from content
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens used
        model_name: Specific model used (e.g., "llama3.2:3b", "claude-3-5-haiku-20241022")
    """

    classified_type: str
    confidence: float
    reasoning: str
    tags: list[str]
    input_tokens: int
    output_tokens: int
    model_name: str = ""


class BaseProvider(ABC):
    """Abstract base class for classification providers.

    All providers (Ollama, OpenRouter, Claude) must implement this interface.
    """

    def __init__(self, timeout: int = 10):
        """Initialize provider.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    @abstractmethod
    def classify(
        self, content: str, collection: str, current_type: str
    ) -> ProviderResponse:
        """Classify content using this provider.

        Args:
            content: The content to classify
            collection: Target collection (code-patterns, conventions, discussions)
            current_type: Current memory type

        Returns:
            ProviderResponse with classification results

        Raises:
            TimeoutError: If request exceeds timeout
            ConnectionError: If provider is unreachable
            ValueError: If response is invalid
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available and healthy.

        Returns:
            True if provider can accept requests, False otherwise
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Get provider name for logging and metrics.

        Returns:
            Provider name (e.g., "ollama", "openrouter", "claude")
        """
        pass

    def _parse_response(self, response_text: str) -> dict:
        """Parse LLM response text into classification dict.

        Handles various response formats:
        - Clean JSON
        - JSON wrapped in markdown code blocks
        - JSON with extra text before/after

        Args:
            response_text: Raw text response from LLM

        Returns:
            dict with classified_type, confidence, reasoning, tags, is_significant

        Raises:
            ValueError: If response cannot be parsed as valid JSON
        """
        text = response_text.strip()

        # Try direct JSON parse first (fastest path)
        try:
            result = json.loads(text)
            self._validate_response_fields(result)
            return result
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block_match:
            try:
                result = json.loads(code_block_match.group(1))
                self._validate_response_fields(result)
                return result
            except json.JSONDecodeError:
                pass

        # Try finding JSON object with classified_type
        json_match = re.search(r'\{[^{}]*"classified_type"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                self._validate_response_fields(result)
                return result
            except json.JSONDecodeError:
                pass

        # Last resort: try to find any JSON object
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                result = json.loads(brace_match.group(0))
                self._validate_response_fields(result)
                return result
            except json.JSONDecodeError:
                pass

        logger.warning("json_parse_failed", extra={"response_preview": text[:200]})
        raise ValueError(f"Could not parse JSON from response: {text[:100]}...")

    def _validate_response_fields(self, result: dict) -> None:
        """Validate that required fields are present in LLM response.

        Args:
            result: Parsed JSON dict

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Check required fields
        if "classified_type" not in result:
            raise ValueError("Missing 'classified_type' in response")
        if "confidence" not in result:
            raise ValueError("Missing 'confidence' in response")

        # Ensure confidence is float
        try:
            result["confidence"] = float(result["confidence"])
        except (ValueError, TypeError) as err:
            raise ValueError(
                f"Invalid confidence value: {result.get('confidence')}"
            ) from err

        # Ensure tags is list
        if "tags" not in result:
            result["tags"] = []
        elif not isinstance(result["tags"], list):
            result["tags"] = [result["tags"]]

        # Set default reasoning if missing
        if "reasoning" not in result:
            result["reasoning"] = ""

    def close(self):
        """Clean up resources. Override in subclasses if needed."""
        # Default no-op implementation - subclasses override if cleanup needed
        return None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()
