"""Intent Detection for BMAD Memory System V2.0.

Routes searches based on user intent:
- HOW queries → code-patterns collection (implementation, error_fix, refactor)
- WHAT queries → conventions collection (rule, guideline, port, naming)
- WHY queries → discussions collection (decision, session, blocker)
"""

from enum import Enum


class IntentType(str, Enum):
    """User query intent types."""
    HOW = "how"      # How to implement, how did we build
    WHAT = "what"    # What port, what rule, what convention
    WHY = "why"      # Why did we decide, why this approach
    UNKNOWN = "unknown"


def detect_intent(query: str) -> IntentType:
    """Detect user intent from query text.

    Args:
        query: User's search query

    Returns:
        IntentType based on keyword matching

    Rules:
        - Case-insensitive matching
        - Check in order: WHY first (most specific), then WHAT, then HOW, then UNKNOWN
        - Return first match found
        - Returns UNKNOWN for None or empty/whitespace-only queries
    """
    # Handle None, empty string, or whitespace-only queries
    if not query or not query.strip():
        return IntentType.UNKNOWN

    query_lower = query.lower()

    # WHY: Most specific, check first
    why_keywords = ["why did", "why do", "reason", "decision", "decided", "rationale"]
    if any(keyword in query_lower for keyword in why_keywords):
        return IntentType.WHY

    # WHAT: Second priority
    what_keywords = ["what port", "what is", "which", "should i", "convention", "rule", "standard"]
    if any(keyword in query_lower for keyword in what_keywords):
        return IntentType.WHAT

    # HOW: Third priority
    how_keywords = ["how do", "how did", "how to", "implement", "build", "create", "fix", "error", "bug"]
    if any(keyword in query_lower for keyword in how_keywords):
        return IntentType.HOW

    # UNKNOWN: No clear match
    return IntentType.UNKNOWN


def get_target_collection(intent: IntentType) -> str:
    """Map intent to primary collection.

    Args:
        intent: Detected intent type

    Returns:
        Collection name to search
    """
    from .config import COLLECTION_CODE_PATTERNS, COLLECTION_CONVENTIONS, COLLECTION_DISCUSSIONS

    mapping = {
        IntentType.HOW: COLLECTION_CODE_PATTERNS,
        IntentType.WHAT: COLLECTION_CONVENTIONS,
        IntentType.WHY: COLLECTION_DISCUSSIONS,
        IntentType.UNKNOWN: COLLECTION_DISCUSSIONS,  # Default fallback
    }
    return mapping[intent]


def get_target_types(intent: IntentType) -> list[str]:
    """Map intent to memory types to search.

    Args:
        intent: Detected intent type

    Returns:
        List of memory types for payload filtering
    """
    mapping = {
        IntentType.HOW: ["implementation", "error_fix", "refactor", "file_pattern"],
        IntentType.WHAT: ["rule", "guideline", "port", "naming", "structure"],
        IntentType.WHY: ["decision", "session", "blocker", "preference", "context"],
        IntentType.UNKNOWN: [],  # No type filter for unknown
    }
    return mapping[intent]
