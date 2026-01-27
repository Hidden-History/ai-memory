"""Tests for LLM classifier orchestration.

TECH-DEBT-069: LLM-based memory classification system tests.
"""

import pytest
from unittest.mock import Mock, patch
from src.memory.classifier.llm_classifier import classify, ClassificationResult
from src.memory.classifier.providers.base import ProviderResponse


class TestLLMClassifier:
    """Test LLM classifier orchestration and provider chain."""

    def test_classifier_disabled(self):
        """Test that classification is skipped when disabled."""
        with patch("src.memory.classifier.llm_classifier.CLASSIFIER_ENABLED", False):
            result = classify(
                "Some content",
                "discussions",
                "user_message",
            )

            assert result.original_type == "user_message"
            assert result.classified_type == "user_message"
            assert result.was_reclassified is False
            assert result.provider_used == "disabled"

    def test_rules_bypass_llm(self):
        """Test that rule-based classification bypasses LLM."""
        content = "DEC-031 decided to use PostgreSQL"

        result = classify(content, "discussions", "user_message")

        assert result.classified_type == "decision"
        assert result.was_reclassified is True
        assert result.provider_used == "rule-based"
        assert result.confidence >= 0.85

    def test_skip_significance_filtering(self):
        """Test that low significance content skips classification."""
        result = classify("ok", "discussions", "user_message")

        assert result.original_type == "user_message"
        assert result.classified_type == "user_message"
        assert result.was_reclassified is False
        assert result.provider_used == "significance-filter"

    def test_protected_type_no_reclassification(self):
        """Test that protected types are not reclassified."""
        with patch(
            "src.memory.classifier.llm_classifier.SKIP_RECLASSIFICATION_TYPES",
            ["session"],
        ):
            result = classify(
                "This is a session summary",
                "discussions",
                "session",
            )

            assert result.classified_type == "session"
            assert result.was_reclassified is False
            assert result.provider_used == "protected-type"

    @patch("src.memory.classifier.llm_classifier._get_provider_chain")
    def test_llm_fallback_success(self, mock_get_chain):
        """Test successful LLM classification when rules don't match."""
        # Mock a provider
        mock_provider = Mock()
        mock_provider.name = "test-provider"
        mock_provider.is_available.return_value = True
        mock_provider.classify.return_value = ProviderResponse(
            classified_type="decision",
            confidence=0.85,
            reasoning="Contains decision keywords",
            tags=["database", "architecture"],
            input_tokens=100,
            output_tokens=50,
        )

        mock_get_chain.return_value = [mock_provider]

        # Content that doesn't match rules
        content = "After discussion, we selected PostgreSQL for the database"

        result = classify(content, "discussions", "user_message")

        assert result.classified_type == "decision"
        assert result.confidence == 0.85
        assert result.was_reclassified is True
        assert result.provider_used == "test-provider"
        assert "database" in result.tags

    @patch("src.memory.classifier.llm_classifier._get_provider_chain")
    def test_provider_chain_fallback(self, mock_get_chain):
        """Test that provider chain falls back on failure."""
        # Mock first provider (fails)
        mock_provider1 = Mock()
        mock_provider1.name = "provider1"
        mock_provider1.is_available.return_value = True
        mock_provider1.classify.side_effect = TimeoutError("Timeout")

        # Mock second provider (succeeds)
        mock_provider2 = Mock()
        mock_provider2.name = "provider2"
        mock_provider2.is_available.return_value = True
        mock_provider2.classify.return_value = ProviderResponse(
            classified_type="decision",
            confidence=0.90,
            reasoning="Contains decision-making discussion",
            tags=["architecture", "database"],
            input_tokens=100,
            output_tokens=50,
        )

        mock_get_chain.return_value = [mock_provider1, mock_provider2]

        # Content that doesn't match any rule patterns
        content = "After evaluating the options, we chose to use PostgreSQL instead of MongoDB"

        result = classify(content, "discussions", "user_message")

        assert result.classified_type == "decision"
        assert result.provider_used == "provider2"
        assert result.was_reclassified is True

    @patch("src.memory.classifier.llm_classifier._get_provider_chain")
    def test_confidence_below_threshold(self, mock_get_chain):
        """Test that low confidence results keep original type."""
        mock_provider = Mock()
        mock_provider.name = "test-provider"
        mock_provider.is_available.return_value = True
        mock_provider.classify.return_value = ProviderResponse(
            classified_type="decision",
            confidence=0.5,  # Below default threshold of 0.7
            reasoning="Uncertain classification",
            tags=[],
            input_tokens=100,
            output_tokens=50,
        )

        mock_get_chain.return_value = [mock_provider]

        content = "Maybe we should consider using Redis"

        result = classify(content, "discussions", "user_message")

        # Should keep original type due to low confidence
        assert result.classified_type == "user_message"
        assert result.was_reclassified is False

    @patch("src.memory.classifier.llm_classifier._get_provider_chain")
    def test_all_providers_unavailable(self, mock_get_chain):
        """Test fallback when all providers are unavailable."""
        mock_provider = Mock()
        mock_provider.name = "test-provider"
        mock_provider.is_available.return_value = False

        mock_get_chain.return_value = [mock_provider]

        content = "This content won't be classified"

        result = classify(content, "discussions", "user_message")

        assert result.classified_type == "user_message"
        assert result.was_reclassified is False
        assert result.provider_used == "fallback"

    @patch("src.memory.classifier.llm_classifier._get_provider_chain")
    def test_all_providers_fail(self, mock_get_chain):
        """Test fallback when all providers fail."""
        mock_provider = Mock()
        mock_provider.name = "test-provider"
        mock_provider.is_available.return_value = True
        mock_provider.classify.side_effect = ConnectionError("Failed to connect")

        mock_get_chain.return_value = [mock_provider]

        content = "This content classification will fail"

        result = classify(content, "discussions", "user_message")

        assert result.classified_type == "user_message"
        assert result.was_reclassified is False
        assert result.provider_used == "fallback"

    @patch("src.memory.classifier.llm_classifier._get_provider_chain")
    def test_no_providers_configured(self, mock_get_chain):
        """Test handling when no providers are configured."""
        mock_get_chain.return_value = []

        content = "No providers available"

        result = classify(content, "discussions", "user_message")

        assert result.classified_type == "user_message"
        assert result.was_reclassified is False
        assert result.provider_used == "none"

    def test_classification_result_structure(self):
        """Test that ClassificationResult has required fields."""
        content = "MUST use snake_case naming"

        result = classify(content, "conventions", "guideline")

        # Verify all fields exist
        assert hasattr(result, "original_type")
        assert hasattr(result, "classified_type")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reasoning")
        assert hasattr(result, "tags")
        assert hasattr(result, "provider_used")
        assert hasattr(result, "was_reclassified")

        # Verify types
        assert isinstance(result.original_type, str)
        assert isinstance(result.classified_type, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.reasoning, str)
        assert isinstance(result.tags, list)
        assert isinstance(result.provider_used, str)
        assert isinstance(result.was_reclassified, bool)

    def test_rule_match_with_high_confidence(self):
        """Test that high confidence rule matches bypass LLM."""
        # Port pattern has 0.95 confidence
        content = "Qdrant runs on port 26350"

        result = classify(content, "conventions", "guideline")

        assert result.classified_type == "port"
        assert result.confidence >= 0.85
        assert result.provider_used == "rule-based"
        assert result.was_reclassified is True
