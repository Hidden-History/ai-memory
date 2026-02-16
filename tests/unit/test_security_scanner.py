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
