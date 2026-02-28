"""Main LLM classification orchestrator.

Coordinates rule-based and LLM-based classification with provider fallback.

TECH-DEBT-069: LLM-based memory classification system.
"""

import hashlib
import logging
import time
from dataclasses import dataclass

from .circuit_breaker import circuit_breaker  # FIX-10
from .config import (
    CLASSIFIER_ENABLED,
    CONFIDENCE_THRESHOLD,
    FALLBACK_PROVIDERS,
    PRIMARY_PROVIDER,
    SKIP_RECLASSIFICATION_TYPES,
    TIMEOUT_SECONDS,
    VALID_TYPES,
)
from .metrics import record_classification, record_fallback  # FIX-4
from .providers import (
    BaseProvider,
    ClaudeProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
)
from .rate_limiter import rate_limiter  # FIX-11
from .rules import classify_by_rules
from .significance import Significance, check_significance

# TECH-DEBT-071: Import token metrics push for Pushgateway
try:
    import os
    import sys

    # Add src to path for metrics_push import
    src_path = os.path.join(os.path.dirname(__file__), "..", "..")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    from memory.metrics_push import push_token_metrics_async
    from memory.project import detect_project  # HIGH-2: For project detection
except ImportError:
    push_token_metrics_async = None
    detect_project = None

logger = logging.getLogger("ai_memory.classifier.llm_classifier")

__all__ = ["ClassificationResult", "classify"]

# Module-level provider chain cache for performance
_provider_chain_cache: list[BaseProvider] | None = None
_provider_chain_config_hash: str | None = None

# Valid collections for validation
VALID_COLLECTIONS = set(VALID_TYPES.keys())


def _validate_collection(collection: str) -> None:
    """Validate that collection is valid.

    Args:
        collection: Collection name to validate

    Raises:
        ValueError: If collection is invalid
    """
    if collection not in VALID_COLLECTIONS:
        raise ValueError(
            f"Invalid collection: '{collection}'. "
            f"Must be one of: {', '.join(sorted(VALID_COLLECTIONS))}"
        )


def _validate_classification(
    classified_type: str, collection: str, original_type: str
) -> str:
    """Validate that classified type is valid for the collection.

    Args:
        classified_type: Type returned by LLM
        collection: Target collection
        original_type: Original type before classification

    Returns:
        Validated type (either classified_type or original_type if invalid)
    """
    valid_types_for_collection = VALID_TYPES.get(collection, [])

    if classified_type in valid_types_for_collection:
        return classified_type

    # Check if it's a valid type for ANY collection (cross-collection classification)
    all_valid_types = set()
    for types in VALID_TYPES.values():
        all_valid_types.update(types)

    if classified_type in all_valid_types:
        logger.warning(
            "type_wrong_collection",
            extra={
                "classified_type": classified_type,
                "collection": collection,
                "valid_for_collection": valid_types_for_collection,
                "keeping_original": original_type,
            },
        )
        return original_type

    logger.warning(
        "invalid_classified_type",
        extra={
            "classified_type": classified_type,
            "collection": collection,
            "keeping_original": original_type,
        },
    )
    return original_type


@dataclass
class ClassificationResult:
    """Result of memory classification.

    Attributes:
        original_type: Original memory type before classification
        classified_type: Classified memory type (may be same as original)
        confidence: Confidence score (0.0-1.0)
        reasoning: Explanation of classification decision
        tags: List of relevant tags extracted
        provider_used: Provider name that performed classification (or "rule-based")
        was_reclassified: True if type changed, False if kept original
        model_name: Specific model used (e.g., "llama3.2:3b", "claude-3-5-haiku-20241022")
        input_tokens: Number of input tokens used by the LLM call
        output_tokens: Number of output tokens used by the LLM call
    """

    original_type: str
    classified_type: str
    confidence: float
    reasoning: str
    tags: list[str]
    provider_used: str
    was_reclassified: bool
    model_name: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def classify(
    content: str,
    collection: str,
    current_type: str,
    file_path: str | None = None,
) -> ClassificationResult:
    """Classify content using rules first, then LLM if needed.

    Classification flow:
    1. Check if classification is enabled
    2. Check content significance (skip if SKIP or LOW)
    3. Check if type should be skipped (session, error_fix)
    4. Try rule-based classification first
    5. If no rule match, try LLM provider chain

    Args:
        content: The content to classify
        collection: Target collection (code-patterns, conventions, discussions)
        current_type: Current memory type
        file_path: Optional file path for context

    Returns:
        ClassificationResult with classification details

    Examples:
        >>> result = classify("Fixed TypeError by adding null check", "code-patterns", "implementation")
        >>> result.classified_type
        'error_fix'
        >>> result.was_reclassified
        True
        >>> result.provider_used
        'rule-based'
    """
    # Validate collection parameter
    _validate_collection(collection)

    # Check if classification is enabled
    if not CLASSIFIER_ENABLED:
        logger.debug("classifier_disabled")
        return ClassificationResult(
            original_type=current_type,
            classified_type=current_type,
            confidence=1.0,
            reasoning="Classification disabled",
            tags=[],
            provider_used="disabled",
            was_reclassified=False,
        )

    # Check significance
    significance = check_significance(content, current_type)
    if significance in [Significance.SKIP, Significance.LOW]:
        logger.debug(
            "classification_skipped_low_significance",
            extra={"significance": significance.value},
        )
        return ClassificationResult(
            original_type=current_type,
            classified_type=current_type,
            confidence=1.0,
            reasoning=f"Skipped due to {significance.value} significance",
            tags=[],
            provider_used="significance-filter",
            was_reclassified=False,
        )

    # Check if type should never be reclassified
    if current_type in SKIP_RECLASSIFICATION_TYPES:
        logger.debug(
            "classification_skipped_protected_type",
            extra={"type": current_type},
        )
        return ClassificationResult(
            original_type=current_type,
            classified_type=current_type,
            confidence=1.0,
            reasoning=f"Type '{current_type}' is protected from reclassification",
            tags=[],
            provider_used="protected-type",
            was_reclassified=False,
        )

    # Try rule-based classification first
    rule_result = classify_by_rules(content, collection)
    if rule_result:
        classified_type, confidence = rule_result
        was_reclassified = classified_type != current_type

        logger.info(
            "rule_based_classification",
            extra={
                "original_type": current_type,
                "classified_type": classified_type,
                "confidence": confidence,
                "was_reclassified": was_reclassified,
            },
        )

        return ClassificationResult(
            original_type=current_type,
            classified_type=classified_type,
            confidence=confidence,
            reasoning="Matched rule-based pattern",
            tags=[],
            provider_used="rule-based",
            was_reclassified=was_reclassified,
        )

    # No rule match - try LLM provider chain
    return _classify_with_llm(content, collection, current_type, file_path)


def _classify_with_llm(
    content: str,
    collection: str,
    current_type: str,
    file_path: str | None = None,
) -> ClassificationResult:
    """Classify using LLM provider chain with fallback.

    Args:
        content: The content to classify
        collection: Target collection
        current_type: Current memory type
        file_path: Optional file path for context

    Returns:
        ClassificationResult from successful provider or fallback to current_type
    """
    # Defensive: Initialize project_name with safe default before any operations
    project_name = "unknown"

    # BP-045: Detect project for multi-tenancy metric labels
    project_name = detect_project(os.getcwd()) if detect_project else "unknown"

    # Get cached provider chain (builds if needed)
    providers = _get_provider_chain()

    if not providers:
        logger.warning("no_providers_available")
        return ClassificationResult(
            original_type=current_type,
            classified_type=current_type,
            confidence=1.0,
            reasoning="No LLM providers available",
            tags=[],
            provider_used="none",
            was_reclassified=False,
        )

    # Try each provider in order with circuit breaker and rate limiting
    last_error = None
    for idx, provider in enumerate(providers):
        provider_name = provider.name

        try:
            # FIX-10: Check circuit breaker
            if not circuit_breaker.is_available(provider_name):
                logger.debug(
                    "provider_circuit_open",
                    extra={"provider": provider_name},
                )
                # Record fallback if there's a next provider
                if idx < len(providers) - 1:
                    record_fallback(
                        provider_name,
                        providers[idx + 1].name,
                        "circuit_open",
                        project=project_name,
                    )
                continue

            # FIX-11: Check rate limit
            if not rate_limiter.allow_request(provider_name):
                logger.debug(
                    "provider_rate_limited",
                    extra={"provider": provider_name},
                )
                # Record fallback if there's a next provider
                if idx < len(providers) - 1:
                    record_fallback(
                        provider_name,
                        providers[idx + 1].name,
                        "rate_limited",
                        project=project_name,
                    )
                continue

            # Check provider availability
            if not provider.is_available():
                logger.debug(
                    "provider_unavailable",
                    extra={"provider": provider_name},
                )
                circuit_breaker.record_failure(provider_name, "unavailable")
                if idx < len(providers) - 1:
                    record_fallback(
                        provider_name,
                        providers[idx + 1].name,
                        "unavailable",
                        project=project_name,
                    )
                continue

            logger.info(
                "attempting_classification",
                extra={"provider": provider_name},
            )

            # Track latency
            start_time = time.time()
            response = provider.classify(content, collection, current_type)
            latency_seconds = time.time() - start_time

            # Validate classified type against collection
            validated_type = _validate_classification(
                response.classified_type, collection, current_type
            )

            # Check if confidence meets threshold
            if response.confidence >= CONFIDENCE_THRESHOLD:
                was_reclassified = validated_type != current_type

                # Record success in circuit breaker
                circuit_breaker.record_success(provider_name)

                # Record metrics
                record_classification(
                    provider=provider_name,
                    classified_type=validated_type,
                    success=True,
                    latency_seconds=latency_seconds,
                    project=project_name,
                    confidence=response.confidence,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )

                # TECH-DEBT-071: Push token metrics to Pushgateway
                # CRITICAL-3: Type validation to prevent metric corruption
                # HIGH-2: Use detected project name instead of hardcoded "classifier"
                if (
                    push_token_metrics_async
                    and isinstance(response.input_tokens, int)
                    and response.input_tokens > 0
                ):
                    push_token_metrics_async(
                        operation="classification",
                        direction="input",
                        project=project_name,
                        token_count=response.input_tokens,
                    )

                if (
                    push_token_metrics_async
                    and isinstance(response.output_tokens, int)
                    and response.output_tokens > 0
                ):
                    push_token_metrics_async(
                        operation="classification",
                        direction="output",
                        project=project_name,
                        token_count=response.output_tokens,
                    )

                logger.info(
                    "llm_classification_success",
                    extra={
                        "provider": provider_name,
                        "original_type": current_type,
                        "classified_type": validated_type,
                        "confidence": response.confidence,
                        "was_reclassified": was_reclassified,
                        "latency_seconds": latency_seconds,
                    },
                )

                return ClassificationResult(
                    original_type=current_type,
                    classified_type=validated_type,
                    confidence=response.confidence,
                    reasoning=response.reasoning,
                    tags=response.tags,
                    provider_used=provider_name,
                    was_reclassified=was_reclassified,
                    model_name=response.model_name,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
            else:
                logger.debug(
                    "confidence_below_threshold",
                    extra={
                        "provider": provider.name,
                        "confidence": response.confidence,
                        "threshold": CONFIDENCE_THRESHOLD,
                    },
                )

        except (TimeoutError, ConnectionError, ValueError) as e:
            error_type = type(e).__name__.lower()

            # Record failure in circuit breaker
            circuit_breaker.record_failure(provider_name, error_type)

            # Record metrics
            record_classification(
                provider=provider_name,
                classified_type=current_type,  # Kept original type
                success=False,
                latency_seconds=(
                    time.time() - start_time if "start_time" in locals() else 0
                ),
                project=project_name,
            )

            # Record fallback if there's a next provider
            if idx < len(providers) - 1:
                record_fallback(
                    provider_name,
                    providers[idx + 1].name,
                    error_type,
                    project=project_name,
                )

            logger.warning(
                "provider_failed",
                extra={
                    "provider": provider_name,
                    "error": str(e),
                    "error_type": error_type,
                },
            )
            last_error = e
            continue

    # All providers failed
    logger.error(
        "all_providers_failed",
        extra={"last_error": str(last_error) if last_error else "Unknown"},
    )

    return ClassificationResult(
        original_type=current_type,
        classified_type=current_type,
        confidence=1.0,
        reasoning="All providers failed, kept original type",
        tags=[],
        provider_used="fallback",
        was_reclassified=False,
    )


def _get_config_hash() -> str:
    """Get hash of current config to detect changes.

    Returns:
        MD5 hash of provider configuration
    """
    config_str = f"{PRIMARY_PROVIDER}:{','.join(FALLBACK_PROVIDERS)}"
    return hashlib.md5(config_str.encode()).hexdigest()


def _get_provider_chain() -> list[BaseProvider]:
    """Get cached provider chain, rebuilding if config changed.

    Returns:
        List of provider instances (cached if possible)
    """
    global _provider_chain_cache, _provider_chain_config_hash

    current_hash = _get_config_hash()

    if _provider_chain_cache is None or _provider_chain_config_hash != current_hash:
        logger.info(
            "building_provider_chain",
            extra={"primary": PRIMARY_PROVIDER, "fallbacks": FALLBACK_PROVIDERS},
        )
        _provider_chain_cache = _build_provider_chain()
        _provider_chain_config_hash = current_hash
    else:
        logger.debug("using_cached_provider_chain")

    return _provider_chain_cache


def _build_provider_chain() -> list[BaseProvider]:
    """Build provider chain from configuration.

    Returns:
        List of provider instances in priority order
    """
    providers = []

    # Add primary provider first
    provider_map = {
        "ollama": OllamaProvider,
        "openrouter": OpenRouterProvider,
        "claude": ClaudeProvider,
        "openai": OpenAIProvider,
    }

    if PRIMARY_PROVIDER in provider_map:
        try:
            providers.append(provider_map[PRIMARY_PROVIDER](timeout=TIMEOUT_SECONDS))
        except Exception as e:
            logger.warning(
                "primary_provider_init_failed",
                extra={"provider": PRIMARY_PROVIDER, "error": str(e)},
            )

    # Add fallback providers
    for provider_name in FALLBACK_PROVIDERS:
        provider_name = provider_name.strip()
        if provider_name in provider_map and provider_name != PRIMARY_PROVIDER:
            try:
                providers.append(provider_map[provider_name](timeout=TIMEOUT_SECONDS))
            except Exception as e:
                logger.warning(
                    "fallback_provider_init_failed",
                    extra={"provider": provider_name, "error": str(e)},
                )

    return providers
