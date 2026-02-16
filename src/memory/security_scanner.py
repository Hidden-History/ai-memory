"""
Security scanning pipeline for AI Memory Module.

SPEC-009: 3-layer scanning for PII and secrets:
- Layer 1: Regex pattern matching (~1ms)
- Layer 2: detect-secrets entropy scanning (~10ms)
- Layer 3: SpaCy NER (~50-100ms, optional)

PII is MASKED with placeholders. Secrets are BLOCKED entirely.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ai_memory.security_scanner")

# Layer 3 (SpaCy) is lazy-loaded to avoid import overhead in hook scripts
_spacy_nlp = None
_spacy_available = None


class ScanAction(str, Enum):
    """Outcome of security scan."""

    PASSED = "passed"  # No sensitive data found
    MASKED = "masked"  # PII masked with placeholders
    BLOCKED = "blocked"  # Secrets detected, content blocked


class FindingType(str, Enum):
    """Types of sensitive data detected."""

    PII_EMAIL = "pii_email"
    PII_PHONE = "pii_phone"
    PII_NAME = "pii_name"
    PII_IP = "pii_ip"
    PII_CC = "pii_credit_card"
    PII_SSN = "pii_ssn"
    PII_HANDLE = "pii_github_handle"
    PII_INTERNAL_URL = "pii_internal_url"
    SECRET_API_KEY = "secret_api_key"
    SECRET_TOKEN = "secret_token"
    SECRET_PASSWORD = "secret_password"
    SECRET_HIGH_ENTROPY = "secret_high_entropy"


@dataclass
class ScanFinding:
    """A single detected sensitive item."""

    finding_type: FindingType
    layer: int  # 1=regex, 2=detect-secrets, 3=SpaCy
    original_text: str  # For logging only — NOT stored in Qdrant
    replacement: Optional[str]  # Masked replacement (None if BLOCK)
    confidence: float  # 0.0-1.0
    start: int  # Character offset
    end: int  # Character offset


@dataclass
class ScanResult:
    """Result of security scan."""

    action: ScanAction
    content: str  # Original or masked content (empty if blocked)
    findings: list[ScanFinding]
    scan_duration_ms: float
    layers_executed: list[int]  # Which layers ran [1], [1,2], or [1,2,3]


# =============================================================================
# LAYER 1: REGEX PATTERNS (SPEC-009 Section 3.1)
# =============================================================================

# PII patterns (MASK action)
PII_PATTERNS = {
    FindingType.PII_EMAIL: (
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "[EMAIL_REDACTED]",
        0.95,
    ),
    FindingType.PII_PHONE: (
        r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        "[PHONE_REDACTED]",
        0.85,
    ),
    FindingType.PII_IP: (
        # IPv4, excluding private ranges
        r'\b(?!127\.0\.0\.1|0\.0\.0\.0|10\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|192\.168\.)(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
        "[IP_REDACTED]",
        0.80,
    ),
    FindingType.PII_CC: (
        # 13-19 digit sequences (Luhn validation done separately)
        r'\b(?:\d{4}[-\s]?){3}\d{1,7}\b',
        "[CC_REDACTED]",
        0.90,
    ),
    FindingType.PII_SSN: (
        r'\b\d{3}-\d{2}-\d{4}\b',
        "[SSN_REDACTED]",
        0.95,
    ),
    FindingType.PII_HANDLE: (
        r'@[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}\b',
        "[HANDLE_REDACTED]",
        0.70,
    ),
    FindingType.PII_INTERNAL_URL: (
        r'https?://(?:internal|intranet|wiki|jira|confluence)\.[a-zA-Z0-9.-]+\S*',
        "[INTERNAL_URL_REDACTED]",
        0.75,
    ),
}

# Secret patterns (BLOCK action)
SECRET_PATTERNS = {
    "github_tokens": (
        r'ghp_[A-Za-z0-9_]{36}|github_pat_[A-Za-z0-9_]{82}',
        FindingType.SECRET_TOKEN,
        0.95,
    ),
    "aws_keys": (
        r'AKIA[0-9A-Z]{16}',
        FindingType.SECRET_API_KEY,
        0.93,
    ),
    "stripe_keys": (
        r'sk_live_[A-Za-z0-9]{24,}',
        FindingType.SECRET_API_KEY,
        0.93,
    ),
    "slack_tokens": (
        r'xox[bpors]-[A-Za-z0-9-]{10,}',
        FindingType.SECRET_TOKEN,
        0.90,
    ),
}


def _luhn_check(card_number: str) -> bool:
    """Validate credit card using Luhn algorithm."""
    digits = [int(d) for d in card_number if d.isdigit()]
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _scan_layer1_regex(content: str) -> tuple[list[ScanFinding], bool]:
    """Layer 1: Regex pattern matching.

    Returns:
        (findings, has_secrets) tuple
    """
    findings = []
    has_secrets = False

    # Scan for secrets first
    for name, (pattern, finding_type, confidence) in SECRET_PATTERNS.items():
        for match in re.finditer(pattern, content):
            findings.append(
                ScanFinding(
                    finding_type=finding_type,
                    layer=1,
                    original_text=match.group(0),
                    replacement=None,  # Secrets are blocked, not masked
                    confidence=confidence,
                    start=match.start(),
                    end=match.end(),
                )
            )
            has_secrets = True

    # Scan for PII
    for finding_type, (pattern, replacement, confidence) in PII_PATTERNS.items():
        for match in re.finditer(pattern, content):
            # Special validation for credit cards
            if finding_type == FindingType.PII_CC:
                if not _luhn_check(match.group(0)):
                    continue

            findings.append(
                ScanFinding(
                    finding_type=finding_type,
                    layer=1,
                    original_text=match.group(0),
                    replacement=replacement,
                    confidence=confidence,
                    start=match.start(),
                    end=match.end(),
                )
            )

    return findings, has_secrets


# =============================================================================
# LAYER 2: DETECT-SECRETS (SPEC-009 Section 3.2)
# =============================================================================


def _scan_layer2_detect_secrets(content: str) -> tuple[list[ScanFinding], bool]:
    """Layer 2: detect-secrets entropy scanning.

    Returns:
        (findings, has_secrets) tuple
    """
    findings = []
    has_secrets = False

    try:
        from detect_secrets.core.scan import scan_line
        from detect_secrets.settings import default_settings
    except ImportError:
        logger.warning("detect-secrets not installed, skipping Layer 2")
        return findings, has_secrets

    try:
        with default_settings():
            for line_number, line in enumerate(content.splitlines(), start=1):
                for secret in scan_line(line):
                    # Map detect-secrets type to our FindingType
                    if "key" in secret.type.lower() or "api" in secret.type.lower():
                        finding_type = FindingType.SECRET_API_KEY
                    elif "token" in secret.type.lower():
                        finding_type = FindingType.SECRET_TOKEN
                    elif "password" in secret.type.lower():
                        finding_type = FindingType.SECRET_PASSWORD
                    else:
                        finding_type = FindingType.SECRET_HIGH_ENTROPY

                    findings.append(
                        ScanFinding(
                            finding_type=finding_type,
                            layer=2,
                            original_text="<redacted>",  # Don't capture actual secret
                            replacement=None,
                            confidence=0.85,
                            start=0,  # detect-secrets doesn't provide offsets
                            end=0,
                        )
                    )
                    has_secrets = True
    except Exception as e:
        logger.error(f"detect-secrets scan failed: {e}")

    return findings, has_secrets


# =============================================================================
# LAYER 3: SPACY NER (SPEC-009 Section 3.3)
# =============================================================================


def _load_spacy_model():
    """Lazy load SpaCy model (called on first scan)."""
    global _spacy_nlp, _spacy_available

    if _spacy_available is False:
        return None

    if _spacy_nlp is not None:
        return _spacy_nlp

    try:
        import spacy

        _spacy_nlp = spacy.load(
            "en_core_web_sm",
            exclude=["tagger", "parser", "senter", "attribute_ruler", "lemmatizer"],
        )
        _spacy_available = True
        logger.info("SpaCy NER model loaded successfully")
        return _spacy_nlp
    except Exception as e:
        logger.warning(f"SpaCy model load failed: {e}. Falling back to L1+L2 only.")
        _spacy_available = False
        return None


def _segment_text(text: str, max_chars: int = 2000) -> list[str]:
    """Segment long texts for NER processing (BP-084)."""
    if len(text) <= max_chars:
        return [text]

    segments = []
    current = ""

    for para in text.split("\n\n"):
        if len(para) > max_chars:
            # Oversized paragraph: split on sentence boundaries
            for sentence in para.split(". "):
                piece = sentence + ". " if not sentence.endswith(".") else sentence
                if len(current) + len(piece) > max_chars:
                    if current:
                        segments.append(current)
                    current = piece
                else:
                    current = f"{current}{piece}" if current else piece
        elif len(current) + len(para) > max_chars:
            if current:
                segments.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        segments.append(current)

    return segments


def _scan_layer3_spacy(content: str) -> list[ScanFinding]:
    """Layer 3: SpaCy NER for person names."""
    findings = []

    nlp = _load_spacy_model()
    if nlp is None:
        return findings

    try:
        segments = _segment_text(content)

        # Process with memory_zone() context manager (SpaCy >=3.8.0)
        if hasattr(nlp, "memory_zone"):
            with nlp.memory_zone():
                for doc in nlp.pipe(segments, batch_size=50):
                    for ent in doc.ents:
                        if ent.label_ == "PERSON":
                            findings.append(
                                ScanFinding(
                                    finding_type=FindingType.PII_NAME,
                                    layer=3,
                                    original_text=ent.text,
                                    replacement="[NAME_REDACTED]",
                                    confidence=0.80,
                                    start=ent.start_char,
                                    end=ent.end_char,
                                )
                            )
        else:
            # Fallback for older SpaCy versions
            for doc in nlp.pipe(segments, batch_size=50):
                for ent in doc.ents:
                    if ent.label_ == "PERSON":
                        findings.append(
                            ScanFinding(
                                finding_type=FindingType.PII_NAME,
                                layer=3,
                                original_text=ent.text,
                                replacement="[NAME_REDACTED]",
                                confidence=0.80,
                                start=ent.start_char,
                                end=ent.end_char,
                            )
                        )
    except Exception as e:
        logger.error(f"SpaCy NER scan failed: {e}")

    return findings


# =============================================================================
# AUDIT LOGGING (SPEC-009 Section 6)
# =============================================================================


def _log_scan_result(result: "ScanResult", content: str, audit_dir: str | None = None) -> None:
    """Append scan result to .audit/logs/sanitization-log.jsonl.

    Per SPEC-009 Section 6: All scan results must be logged to audit trail.
    Follows same pattern as injection.py:log_injection_event and
    freshness.py:_log_freshness_results.

    Args:
        result: ScanResult from scan() call.
        content: Original content (used for content_hash correlation only).
        audit_dir: Path to .audit/ directory. If None, uses cwd/.audit/.
    """
    import os

    base = Path(audit_dir) if audit_dir else Path(os.getcwd()) / ".audit"
    log_path = base / "logs" / "sanitization-log.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "action": result.action.value,
        "findings_count": len(result.findings),
        "layers_executed": result.layers_executed,
        "scan_duration_ms": round(result.scan_duration_ms, 2),
        "content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
    }

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except (OSError, PermissionError):
        pass  # Audit logging is best-effort, never blocks


# =============================================================================
# SECURITY SCANNER CLASS (SPEC-009 Section 4.2)
# =============================================================================


class SecurityScanner:
    """Shared 3-layer security scanning pipeline."""

    def __init__(self, enable_ner: bool = False):
        """
        Args:
            enable_ner: Enable Layer 3 (SpaCy NER). False for hooks (Layers 1+2 only).
                        True for GitHub sync service and SDK batch operations.
        """
        self.enable_ner = enable_ner

    def scan(self, content: str, force_ner: bool = False) -> ScanResult:
        """Scan a single text. Returns ScanResult with action, cleaned content, and findings.

        Args:
            content: Text content to scan.
            force_ner: If True, enable Layer 3 (SpaCy NER) for this call regardless
                       of instance config. Used by batch operations per SPEC-009.
        """
        start_time = time.perf_counter()
        all_findings = []
        layers_executed = []

        # Layer 1: Regex
        layer1_findings, has_secrets_l1 = _scan_layer1_regex(content)
        all_findings.extend(layer1_findings)
        layers_executed.append(1)

        if has_secrets_l1:
            duration_ms = (time.perf_counter() - start_time) * 1000
            result = ScanResult(
                action=ScanAction.BLOCKED,
                content="",
                findings=all_findings,
                scan_duration_ms=duration_ms,
                layers_executed=layers_executed,
            )
            _log_scan_result(result, content)
            return result

        # Layer 2: detect-secrets
        layer2_findings, has_secrets_l2 = _scan_layer2_detect_secrets(content)
        all_findings.extend(layer2_findings)
        layers_executed.append(2)

        if has_secrets_l2:
            duration_ms = (time.perf_counter() - start_time) * 1000
            result = ScanResult(
                action=ScanAction.BLOCKED,
                content="",
                findings=all_findings,
                scan_duration_ms=duration_ms,
                layers_executed=layers_executed,
            )
            _log_scan_result(result, content)
            return result

        # Layer 3: SpaCy NER (if enabled or forced for batch operations)
        if self.enable_ner or force_ner:
            layer3_findings = _scan_layer3_spacy(content)
            all_findings.extend(layer3_findings)
            layers_executed.append(3)

        # Apply all PII masks
        masked_content = content
        # Sort findings by position (descending) to avoid offset shifts
        pii_findings = [f for f in all_findings if f.replacement is not None]
        pii_findings.sort(key=lambda f: f.start, reverse=True)

        for finding in pii_findings:
            masked_content = (
                masked_content[: finding.start]
                + finding.replacement
                + masked_content[finding.end :]
            )

        # Determine final action
        action = ScanAction.MASKED if pii_findings else ScanAction.PASSED

        duration_ms = (time.perf_counter() - start_time) * 1000
        result = ScanResult(
            action=action,
            content=masked_content if action != ScanAction.BLOCKED else content,
            findings=all_findings,
            scan_duration_ms=duration_ms,
            layers_executed=layers_executed,
        )
        _log_scan_result(result, content)
        return result

    def scan_batch(self, texts: list[str]) -> list[ScanResult]:
        """Scan multiple texts. Uses SpaCy batch processing if NER enabled."""
        # For now, scan individually
        # TODO: Optimize with true batch processing for SpaCy
        return [self.scan(text) for text in texts]
