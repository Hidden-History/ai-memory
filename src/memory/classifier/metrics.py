"""Prometheus metrics for memory classification.

TECH-DEBT-069: Classification monitoring per spec section 5.1.
"""

import logging
from prometheus_client import Counter, Histogram, Gauge

logger = logging.getLogger("bmad.memory.classifier.metrics")

__all__ = [
    "classifier_requests_total",
    "classifier_tokens_total",
    "classifier_cost_microdollars",
    "classifier_latency_seconds",
    "classifier_fallbacks_total",
    "classifier_rule_matches_total",
    "classifier_significance_skips_total",
    "classifier_queue_size",
    "classifier_confidence",
    "record_classification",
    "record_fallback",
    "record_rule_match",
    "record_significance_skip",
]

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

# Request tracking
classifier_requests_total = Counter(
    'memory_classifier_requests_total',
    'Total classification requests',
    ['provider', 'status', 'classified_type']
)

# Token usage
classifier_tokens_total = Counter(
    'memory_classifier_tokens_total',
    'Total tokens used by classifier',
    ['provider', 'direction']  # direction: input/output
)

# Cost tracking (in micro-dollars for precision)
classifier_cost_microdollars = Counter(
    'memory_classifier_cost_microdollars_total',
    'Estimated cost in micro-dollars (divide by 1e6 for USD)',
    ['provider']
)

# Latency
classifier_latency_seconds = Histogram(
    'memory_classifier_latency_seconds',
    'Classification latency',
    ['provider'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# Fallbacks
classifier_fallbacks_total = Counter(
    'memory_classifier_fallbacks_total',
    'Provider fallback events',
    ['from_provider', 'to_provider', 'reason']
)

# Rule-based classification (no LLM needed)
classifier_rule_matches_total = Counter(
    'memory_classifier_rule_matches_total',
    'Successful rule-based classifications',
    ['rule_type']
)

# Significance filtering
classifier_significance_skips_total = Counter(
    'memory_classifier_significance_skips_total',
    'Content skipped due to low significance',
    ['level']
)

# Queue status
classifier_queue_size = Gauge(
    'memory_classifier_queue_size',
    'Current size of classification retry queue'
)

# Confidence distribution
classifier_confidence = Histogram(
    'memory_classifier_confidence',
    'Classification confidence scores',
    ['classified_type'],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def record_classification(
    provider: str,
    classified_type: str,
    success: bool,
    latency_seconds: float,
    confidence: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_microdollars: float = 0.0,
):
    """Record a classification event with all metrics.

    Args:
        provider: Provider name (ollama, openrouter, claude, rule-based, etc.)
        classified_type: The type assigned to the memory
        success: True if classification succeeded, False if error
        latency_seconds: Time taken for classification
        confidence: Confidence score (0.0-1.0)
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated
        cost_microdollars: Estimated cost in micro-dollars

    Example:
        >>> record_classification(
        ...     provider="ollama",
        ...     classified_type="decision",
        ...     success=True,
        ...     latency_seconds=1.23,
        ...     confidence=0.85,
        ...     input_tokens=450,
        ...     output_tokens=75,
        ...     cost_microdollars=0  # Ollama is free
        ... )
    """
    status = "success" if success else "error"

    # Increment request counter
    classifier_requests_total.labels(
        provider=provider,
        status=status,
        classified_type=classified_type
    ).inc()

    # Record latency
    classifier_latency_seconds.labels(provider=provider).observe(latency_seconds)

    # Record token usage
    if input_tokens > 0:
        classifier_tokens_total.labels(
            provider=provider,
            direction="input"
        ).inc(input_tokens)

    if output_tokens > 0:
        classifier_tokens_total.labels(
            provider=provider,
            direction="output"
        ).inc(output_tokens)

    # Record cost
    if cost_microdollars > 0:
        classifier_cost_microdollars.labels(provider=provider).inc(cost_microdollars)

    # Record confidence distribution (only on success)
    if success and confidence > 0:
        classifier_confidence.labels(classified_type=classified_type).observe(confidence)

    logger.debug(
        "classification_recorded",
        extra={
            "provider": provider,
            "type": classified_type,
            "success": success,
            "latency_seconds": latency_seconds,
            "confidence": confidence,
        }
    )


def record_fallback(from_provider: str, to_provider: str, reason: str):
    """Record a provider fallback event.

    Args:
        from_provider: Provider that failed
        to_provider: Provider being tried next
        reason: Reason for fallback (timeout, error, unavailable, etc.)

    Example:
        >>> record_fallback("ollama", "openrouter", "timeout")
    """
    classifier_fallbacks_total.labels(
        from_provider=from_provider,
        to_provider=to_provider,
        reason=reason
    ).inc()

    logger.info(
        "provider_fallback",
        extra={
            "from": from_provider,
            "to": to_provider,
            "reason": reason,
        }
    )


def record_rule_match(rule_type: str):
    """Record a rule-based classification (no LLM needed).

    Args:
        rule_type: Type of rule that matched (error_fix, port, decision, etc.)

    Example:
        >>> record_rule_match("error_fix")
    """
    classifier_rule_matches_total.labels(rule_type=rule_type).inc()

    logger.debug("rule_match_recorded", extra={"rule_type": rule_type})


def record_significance_skip(level: str):
    """Record content skipped due to significance level.

    Args:
        level: Significance level (skip, low, medium, high)

    Example:
        >>> record_significance_skip("skip")
    """
    classifier_significance_skips_total.labels(level=level).inc()

    logger.debug("significance_skip_recorded", extra={"level": level})
