"""LLM-based memory classification system.

TECH-DEBT-069: Automatic memory type classification using LLM providers.

Public API:
    - classify(): Main classification function
    - ClassificationResult: Classification result dataclass
    - Significance: Content significance levels
    - check_significance(): Check content significance
    - classify_by_rules(): Rule-based classification
    - record_classification(): Record classification metrics
    - record_fallback(): Record provider fallback metrics
    - record_rule_match(): Record rule-based match metrics
"""

from .config import CLASSIFIER_ENABLED, CONFIDENCE_THRESHOLD
from .llm_classifier import ClassificationResult, classify
from .metrics import (
    record_classification,
    record_fallback,
    record_rule_match,
    record_significance_skip,
)
from .rules import classify_by_rules
from .significance import Significance, check_significance

__all__ = [
    "CLASSIFIER_ENABLED",
    "CONFIDENCE_THRESHOLD",
    "ClassificationResult",
    "Significance",
    "check_significance",
    "classify",
    "classify_by_rules",
    # Metrics
    "record_classification",
    "record_fallback",
    "record_rule_match",
    "record_significance_skip",
]
