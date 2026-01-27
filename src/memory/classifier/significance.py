"""Content significance checker.

Filters out low-value content before classification to reduce token usage.

TECH-DEBT-069: LLM-based memory classification system.
"""

import re
import logging
from typing import Optional

from .config import (
    Significance,
    MIN_CONTENT_LENGTH,
    SKIP_PATTERNS,
    LOW_PATTERNS,
)

logger = logging.getLogger("bmad.memory.classifier.significance")

__all__ = ["check_significance"]


def check_significance(content: str, current_type: Optional[str] = None) -> Significance:
    """Check content significance level.

    Args:
        content: The content to evaluate
        current_type: Current memory type (optional)

    Returns:
        Significance level: SKIP, LOW, MEDIUM, or HIGH

    Examples:
        >>> check_significance("ok")
        <Significance.SKIP: 'skip'>
        >>> check_significance("sounds good")
        <Significance.LOW: 'low'>
        >>> check_significance("After discussing options, we decided to use PostgreSQL")
        <Significance.MEDIUM: 'medium'>
    """
    if not content or not isinstance(content, str):
        logger.debug("empty_or_invalid_content")
        return Significance.SKIP

    # Strip whitespace for checking
    stripped = content.strip()

    # Check length first (fastest check)
    if len(stripped) < MIN_CONTENT_LENGTH:
        logger.debug("content_too_short", extra={"length": len(stripped)})
        return Significance.SKIP

    # Check SKIP patterns (acknowledgments, emoji-only)
    for pattern in SKIP_PATTERNS:
        if re.match(pattern, stripped, re.IGNORECASE):
            logger.debug("skip_pattern_matched", extra={"pattern": pattern})
            return Significance.SKIP

    # Check LOW patterns (simple responses)
    for pattern in LOW_PATTERNS:
        if re.match(pattern, stripped, re.IGNORECASE):
            logger.debug("low_pattern_matched", extra={"pattern": pattern})
            return Significance.LOW

    # Check for high-value indicators
    high_value_indicators = [
        r"(?i)DEC-\d+",  # Decision reference
        r"(?i)BLK-\d+",  # Blocker reference
        r"(?i)(decided|chose|selected|opted for)",
        r"(?i)(error|exception|traceback)",
        r"(?i)(MUST|NEVER|ALWAYS|REQUIRED|SHALL NOT)",
    ]

    for pattern in high_value_indicators:
        if re.search(pattern, content):
            logger.debug("high_value_indicator", extra={"pattern": pattern})
            return Significance.HIGH

    # Default to MEDIUM for everything else
    return Significance.MEDIUM
