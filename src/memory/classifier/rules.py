"""Rule-based memory classification.

Uses regex patterns for high-confidence classification without LLM calls.

TECH-DEBT-069: LLM-based memory classification system.
"""

import re
import logging
from typing import Optional, Tuple

from .config import RULE_PATTERNS, RULE_CONFIDENCE_THRESHOLD

logger = logging.getLogger("bmad.memory.classifier.rules")

__all__ = ["classify_by_rules"]


def classify_by_rules(
    content: str, collection: str
) -> Optional[Tuple[str, float]]:
    """Classify content using rule-based patterns.

    Args:
        content: The content to classify
        collection: Target collection (code-patterns, conventions, discussions)

    Returns:
        Tuple of (classified_type, confidence) if pattern matches with high confidence,
        None otherwise.

    Examples:
        >>> classify_by_rules("Fixed TypeError by adding null check", "code-patterns")
        ('error_fix', 0.90)
        >>> classify_by_rules("Port 26350 for Qdrant", "conventions")
        ('port', 0.95)
        >>> classify_by_rules("MUST use snake_case", "conventions")
        ('rule', 0.90)
        >>> classify_by_rules("DEC-031 decided to use PostgreSQL", "discussions")
        ('decision', 0.95)
    """
    if not content or not isinstance(content, str):
        return None

    # Try each rule pattern
    for memory_type, rule_config in RULE_PATTERNS.items():
        patterns = rule_config["patterns"]
        confidence = rule_config["confidence"]

        # Check if any pattern matches
        for pattern in patterns:
            try:
                if re.search(pattern, content):
                    # Only return if confidence meets threshold
                    if confidence >= RULE_CONFIDENCE_THRESHOLD:
                        logger.info(
                            "rule_match",
                            extra={
                                "type": memory_type,
                                "confidence": confidence,
                                "pattern": pattern[:50],  # Log first 50 chars
                            },
                        )
                        return (memory_type, confidence)
                    else:
                        logger.debug(
                            "rule_match_below_threshold",
                            extra={
                                "type": memory_type,
                                "confidence": confidence,
                            },
                        )
            except re.error as e:
                logger.warning(
                    "regex_pattern_error",
                    extra={"pattern": pattern, "error": str(e)},
                )
                continue

    # No rule matched
    logger.debug("no_rule_match")
    return None
