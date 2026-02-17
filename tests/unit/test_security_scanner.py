"""
Unit tests for SPEC-009: Security Scanning Pipeline

Tests the 3-layer scanner (regex, detect-secrets, SpaCy NER).
"""

import pytest
from unittest.mock import Mock, patch


class TestLayer1Regex:
    """Test Layer 1: Regex pattern matching"""

    def test_email_detection_and_masking(self):
        """Test email detection and masking"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Contact me at user@example.com for details")

        assert result.action == ScanAction.MASKED
        assert "[EMAIL_REDACTED]" in result.content
        assert "user@example.com" not in result.content
        assert len(result.findings) >= 1
        assert any(f.finding_type.value == "pii_email" for f in result.findings)

    def test_phone_detection_and_masking(self):
        """Test phone number detection and masking"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Call me at 555-123-4567")

        assert result.action == ScanAction.MASKED
        assert "[PHONE_REDACTED]" in result.content
        assert "555-123-4567" not in result.content

    def test_github_pat_detection_blocks_content(self):
        """Test GitHub PAT detection blocks storage"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("My token is ghp_" + "A" * 36)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""
        assert any(f.finding_type.value == "secret_token" for f in result.findings)

    def test_aws_key_detection_blocks_content(self):
        """Test AWS access key detection blocks storage"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("AWS key: AKIAIOSFODNN7EXAMPLE")

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""

    def test_clean_content_passes(self):
        """Test clean content passes through"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("This is clean code without any PII or secrets")

        assert result.action == ScanAction.PASSED
        assert result.content == "This is clean code without any PII or secrets"
        assert len(result.findings) == 0

    def test_ip_address_masking(self):
        """Test IP address detection (excluding private ranges)"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Server at 8.8.8.8 is online")

        assert result.action == ScanAction.MASKED
        assert "[IP_REDACTED]" in result.content

    def test_private_ip_not_masked(self):
        """Test private IP ranges are not masked"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Local server at 192.168.1.1")

        # Private IPs should not be masked
        assert result.action == ScanAction.PASSED or "192.168.1.1" in result.content


class TestScannerOrchestration:
    """Test scanner execution logic"""

    def test_blocked_returns_immediately(self):
        """Test that BLOCKED returns immediately without Layer 3"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=True)
        result = scanner.scan("Secret: ghp_" + "A" * 36)

        assert result.action == ScanAction.BLOCKED
        # Should only execute layers 1 and maybe 2, not 3
        assert 3 not in result.layers_executed

    def test_layer_selection_ner_disabled(self):
        """Test that NER layer is skipped when disabled"""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Clean content")

        # Should only execute layers 1 and 2
        assert 1 in result.layers_executed
        assert 2 in result.layers_executed
        assert 3 not in result.layers_executed

    def test_scan_duration_tracked(self):
        """Test that scan duration is tracked"""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Test content")

        assert result.scan_duration_ms > 0
        assert result.scan_duration_ms < 1000  # Should be fast without NER

    def test_multiple_findings_all_masked(self):
        """Test multiple PII items are all masked"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Email user@test.com and phone 555-1234567")

        assert result.action == ScanAction.MASKED
        assert "[EMAIL_REDACTED]" in result.content
        assert "[PHONE_REDACTED]" in result.content
        assert "user@test.com" not in result.content
        assert len(result.findings) >= 2


class TestEdgeCases:
    """Test edge cases"""

    def test_empty_content(self):
        """Test scanner handles empty content"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("")

        assert result.action == ScanAction.PASSED
        assert result.content == ""
        assert len(result.findings) == 0

    def test_very_long_content(self):
        """Test scanner handles very long content (>10K chars)"""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        long_content = "Clean text. " * 1000  # ~12K chars
        result = scanner.scan(long_content)

        assert result.action == ScanAction.PASSED
        assert len(result.content) > 10000


class TestConfigIntegration:
    """Test config-based scanner initialization"""

    def test_storage_scanner_initialization(self):
        """Test MemoryStorage initializes scanner correctly"""
        from memory.storage import MemoryStorage

        storage = MemoryStorage()

        # Scanner should be initialized
        assert hasattr(storage, "_scanner")
        # Check if scanner is enabled based on config
        # (may be None if security_scanning_enabled=False)


class TestScanResult:
    """Test ScanResult data model"""

    def test_scan_result_attributes(self):
        """Test ScanResult has all required attributes"""
        from memory.security_scanner import ScanResult, ScanAction, ScanFinding, FindingType

        finding = ScanFinding(
            finding_type=FindingType.PII_EMAIL,
            layer=1,
            original_text="test@example.com",
            replacement="[EMAIL_REDACTED]",
            confidence=0.95,
            start=0,
            end=16,
        )

        result = ScanResult(
            action=ScanAction.MASKED,
            content="masked content",
            findings=[finding],
            scan_duration_ms=5.2,
            layers_executed=[1, 2],
        )

        assert result.action == ScanAction.MASKED
        assert result.content == "masked content"
        assert len(result.findings) == 1
        assert result.scan_duration_ms == 5.2
        assert result.layers_executed == [1, 2]


class TestLayer1PiiPatterns:
    """Test ALL PII patterns from security_scanner.py PII_PATTERNS (TD-159)."""

    def test_ssn_detection_and_masking(self):
        """Test Social Security Number detection."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("My SSN is 123-45-6789")

        assert result.action == ScanAction.MASKED
        assert "[SSN_REDACTED]" in result.content
        assert "123-45-6789" not in result.content

    def test_credit_card_with_valid_luhn(self):
        """Test credit card detection with Luhn-valid number."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        # 4532015112830366 is Luhn-valid
        result = scanner.scan("Card: 4532 0151 1283 0366")

        assert result.action == ScanAction.MASKED
        assert "[CC_REDACTED]" in result.content
        assert "4532" not in result.content

    def test_credit_card_invalid_luhn_not_masked(self):
        """Test credit card-like number with invalid Luhn passes through."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        # 1234-5678-9012-3456 fails Luhn check
        result = scanner.scan("Not a card: 1234 5678 9012 3456")

        # Should NOT be masked (Luhn check fails)
        assert "1234" in result.content or result.action == ScanAction.PASSED

    def test_github_handle_detection(self):
        """Test GitHub handle detection."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("See PR by @octocat for details")

        assert result.action == ScanAction.MASKED
        assert "[HANDLE_REDACTED]" in result.content
        assert "@octocat" not in result.content

    def test_internal_url_detection(self):
        """Test internal URL detection."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Check https://internal.company.com/wiki/page")

        assert result.action == ScanAction.MASKED
        assert "[INTERNAL_URL_REDACTED]" in result.content
        assert "internal.company.com" not in result.content

    def test_jira_url_detection(self):
        """Test Jira internal URL detection."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("See https://jira.company.com/browse/PROJ-123")

        assert result.action == ScanAction.MASKED
        assert "[INTERNAL_URL_REDACTED]" in result.content


class TestLayer1SecretPatterns:
    """Test ALL secret patterns from security_scanner.py SECRET_PATTERNS (TD-159)."""

    def test_stripe_live_key_blocks(self):
        """Test Stripe live key detection blocks content."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Stripe key: sk_live_" + "a" * 24)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""

    def test_slack_token_blocks(self):
        """Test Slack token detection blocks content."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Slack: xoxb-" + "1234567890-" * 3)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""

    def test_github_fine_grained_pat_blocks(self):
        """Test GitHub fine-grained PAT detection blocks content."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Token: github_pat_" + "A" * 82)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""


class TestGitHubHandleFalsePositives:
    """Test TD-161: GitHub handle regex false positive fixes."""

    def test_python_decorators_not_flagged(self):
        """Test that Python decorators are NOT detected as GitHub handles."""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)

        decorator_texts = [
            "@pytest.mark.integration",
            "@dataclass",
            "@property",
            "@staticmethod",
            "@classmethod",
            "@abstractmethod",
            "@cached_property",
            "@patch('module.Class')",
        ]

        for text in decorator_texts:
            result = scanner.scan(f"Code: {text}\ndef func(): pass")
            # Decorators should NOT be flagged as handles
            assert "[HANDLE_REDACTED]" not in result.content, (
                f"False positive: {text} was flagged as GitHub handle"
            )

    def test_real_github_handles_still_detected(self):
        """Test that real GitHub handles ARE still detected."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Thanks to @octocat and @torvalds for the review")

        assert result.action == ScanAction.MASKED
        assert "[HANDLE_REDACTED]" in result.content
        assert "@octocat" not in result.content

    def test_single_char_handle_not_flagged(self):
        """Test that single-char @x is NOT flagged as a handle (TD-161)."""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Value @x is not a handle")

        assert "[HANDLE_REDACTED]" not in result.content


class TestScanBatchNER:
    """Test TD-163/TD-165: scan_batch() with NER batching and force_ner."""

    def test_batch_without_ner_scans_individually(self):
        """Test batch scanning without NER is sequential L1+L2."""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        results = scanner.scan_batch(["clean text 1", "clean text 2"])

        assert len(results) == 2
        assert all(3 not in r.layers_executed for r in results)

    def test_batch_force_ner_enables_layer3(self):
        """Test force_ner=True enables Layer 3 in batch."""
        from memory.security_scanner import SecurityScanner, _spacy_available

        if _spacy_available is False:
            pytest.skip("SpaCy not available")

        scanner = SecurityScanner(enable_ner=False)
        results = scanner.scan_batch(
            ["John Smith wrote code", "Jane Doe reviewed it"],
            force_ner=True,
        )

        assert len(results) == 2
        # Layer 3 should have been executed
        assert all(3 in r.layers_executed for r in results)

    def test_batch_blocked_texts_excluded_from_ner(self):
        """Test that BLOCKED texts skip NER processing."""
        from memory.security_scanner import SecurityScanner, ScanAction, _spacy_available

        if _spacy_available is False:
            pytest.skip("SpaCy not available")

        scanner = SecurityScanner(enable_ner=True)
        results = scanner.scan_batch([
            "Clean text about John Smith",
            "Secret: ghp_" + "A" * 36,
            "More text about Jane Doe",
        ], force_ner=True)

        assert len(results) == 3
        assert results[1].action == ScanAction.BLOCKED
        assert 3 not in results[1].layers_executed  # Blocked BEFORE NER
        assert 3 in results[0].layers_executed      # Non-blocked DID run NER

    def test_batch_empty_list(self):
        """Test scan_batch() with empty list returns empty list."""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        results = scanner.scan_batch([])

        assert results == []

    def test_batch_preserves_order(self):
        """Test that scan_batch() results order matches input order."""
        from memory.security_scanner import SecurityScanner, ScanAction

        scanner = SecurityScanner(enable_ner=False)
        results = scanner.scan_batch([
            "Email: user@test.com",
            "Clean text here",
            "Phone: 555-123-4567",
        ])

        assert len(results) == 3
        assert results[0].action == ScanAction.MASKED
        assert "[EMAIL_REDACTED]" in results[0].content
        assert results[1].action == ScanAction.PASSED
        assert results[2].action == ScanAction.MASKED
        assert "[PHONE_REDACTED]" in results[2].content
