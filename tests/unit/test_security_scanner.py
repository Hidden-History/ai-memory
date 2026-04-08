"""
Unit tests for SPEC-009: Security Scanning Pipeline

Tests the 3-layer scanner (regex, detect-secrets, SpaCy NER).
"""

import pytest


class TestLayer1Regex:
    """Test Layer 1: Regex pattern matching"""

    @pytest.fixture(autouse=True)
    def _disable_detect_secrets(self, monkeypatch):
        """Isolate Layer 1 tests from Layer 2 detect-secrets interference."""
        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

    def test_email_detection_and_masking(self):
        """Test email detection and masking"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Contact me at user@example.com for details")

        assert result.action == ScanAction.MASKED
        assert "[EMAIL_REDACTED]" in result.content
        assert "user@example.com" not in result.content
        assert len(result.findings) >= 1
        assert any(f.finding_type.value == "pii_email" for f in result.findings)

    def test_phone_detection_and_masking(self):
        """Test phone number detection and masking"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Call me at 555-123-4567")

        assert result.action == ScanAction.MASKED
        assert "[PHONE_REDACTED]" in result.content
        assert "555-123-4567" not in result.content

    def test_github_pat_detection_blocks_content(self):
        """Test GitHub PAT detection blocks storage"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("My token is ghp_" + "A" * 36)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""
        assert any(f.finding_type.value == "secret_token" for f in result.findings)

    def test_aws_key_detection_blocks_content(self):
        """Test AWS access key detection blocks storage"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("AWS key: AKIAIOSFODNN7EXAMPLE")

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""

    def test_clean_content_passes(self):
        """Test clean content passes through"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("This is clean code without any PII or secrets")

        assert result.action == ScanAction.PASSED
        assert result.content == "This is clean code without any PII or secrets"
        assert len(result.findings) == 0

    def test_ip_address_masking(self):
        """Test IP address detection (excluding private ranges)"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Server at 8.8.8.8 is online")

        assert result.action == ScanAction.MASKED
        assert "[IP_REDACTED]" in result.content

    def test_private_ip_not_masked(self):
        """Test private IP ranges are not masked"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Local server at 192.168.1.1")

        # Private IPs should not be masked
        assert result.action == ScanAction.PASSED or "192.168.1.1" in result.content


class TestScannerOrchestration:
    """Test scanner execution logic"""

    @pytest.fixture(autouse=True)
    def _disable_detect_secrets(self, monkeypatch):
        """Isolate orchestration tests from Layer 2 detect-secrets interference."""
        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

    def test_blocked_returns_immediately(self):
        """Test that BLOCKED returns immediately without Layer 3"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=True)
        result = scanner.scan("Secret: ghp_" + "A" * 36)

        assert result.action == ScanAction.BLOCKED
        # Should only execute layers 1 and maybe 2, not 3
        assert 3 not in result.layers_executed

    def test_layer_selection_ner_disabled(self, monkeypatch):
        """Test that NER layer is skipped when disabled"""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # Routing test: verifies Layer 1+2 run for session content (TD-368)
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
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Email user@test.com and phone 555-1234567")

        assert result.action == ScanAction.MASKED
        assert "[EMAIL_REDACTED]" in result.content
        assert "[PHONE_REDACTED]" in result.content
        assert "user@test.com" not in result.content
        assert len(result.findings) >= 2


class TestEdgeCases:
    """Test edge cases"""

    @pytest.fixture(autouse=True)
    def _disable_detect_secrets(self, monkeypatch):
        """Isolate edge case tests from Layer 2 detect-secrets interference."""
        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

    def test_empty_content(self):
        """Test scanner handles empty content"""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("")

        assert result.action == ScanAction.PASSED
        assert result.content == ""
        assert len(result.findings) == 0

    def test_very_long_content(self):
        """Test scanner handles very long content (>10K chars)"""
        from memory.security_scanner import ScanAction, SecurityScanner

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
        from memory.security_scanner import (
            FindingType,
            ScanAction,
            ScanFinding,
            ScanResult,
        )

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

    @pytest.fixture(autouse=True)
    def _disable_detect_secrets(self, monkeypatch):
        """Isolate Layer 1 PII tests from Layer 2 detect-secrets interference."""
        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

    def test_ssn_detection_and_masking(self):
        """Test Social Security Number detection."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("My SSN is 123-45-6789")

        assert result.action == ScanAction.MASKED
        assert "[SSN_REDACTED]" in result.content
        assert "123-45-6789" not in result.content

    def test_credit_card_with_valid_luhn(self):
        """Test credit card detection with Luhn-valid number."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # 4532015112830366 is Luhn-valid
        result = scanner.scan("Card: 4532 0151 1283 0366")

        assert result.action == ScanAction.MASKED
        assert "[CC_REDACTED]" in result.content
        assert "4532" not in result.content

    def test_credit_card_invalid_luhn_not_masked(self):
        """Test credit card-like number with invalid Luhn passes through."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # 1234-5678-9012-3456 fails Luhn check
        result = scanner.scan("Not a card: 1234 5678 9012 3456")

        # Should NOT be masked (Luhn check fails)
        assert "1234" in result.content or result.action == ScanAction.PASSED

    def test_github_handle_detection(self):
        """Test GitHub handle detection."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("See PR by @octocat for details")

        assert result.action == ScanAction.MASKED
        assert "[HANDLE_REDACTED]" in result.content
        assert "@octocat" not in result.content

    def test_internal_url_detection(self):
        """Test internal URL detection."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Check https://internal.company.com/wiki/page")

        assert result.action == ScanAction.MASKED
        assert "[INTERNAL_URL_REDACTED]" in result.content
        assert "internal.company.com" not in result.content

    def test_jira_url_detection(self):
        """Test Jira internal URL detection."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("See https://jira.company.com/browse/PROJ-123")

        assert result.action == ScanAction.MASKED
        assert "[INTERNAL_URL_REDACTED]" in result.content


class TestLayer1SecretPatterns:
    """Test ALL secret patterns from security_scanner.py SECRET_PATTERNS (TD-159)."""

    def test_stripe_live_key_blocks(self):
        """Test Stripe live key detection blocks content."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Stripe key: sk_live_" + "a" * 24)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""

    def test_slack_token_blocks(self):
        """Test Slack token detection blocks content."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Slack: xoxb-" + "1234567890-" * 3)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""

    def test_github_fine_grained_pat_blocks(self):
        """Test GitHub fine-grained PAT detection blocks content."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Token: github_pat_" + "A" * 82)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""


class TestAIEcosystemSecretPatterns:
    """Test TD-367: AI-ecosystem secret patterns (OpenAI, Anthropic, HuggingFace)."""

    @pytest.fixture(autouse=True)
    def _disable_detect_secrets(self, monkeypatch):
        """Isolate AI pattern tests from Layer 2 detect-secrets interference."""
        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

    def test_openai_key_blocks(self):
        """Test OpenAI API key detection blocks content."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # OpenAI keys start with sk- and are 20+ chars
        result = scanner.scan("API key: sk-" + "A" * 48)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""
        assert any(f.finding_type.value == "secret_api_key" for f in result.findings)

    def test_anthropic_key_blocks(self):
        """Test Anthropic API key detection blocks content."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # Anthropic keys: sk-ant-...
        result = scanner.scan("Key: sk-ant-api03-" + "A" * 80)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""
        assert any(f.finding_type.value == "secret_api_key" for f in result.findings)

    def test_huggingface_key_blocks(self):
        """Test HuggingFace API key detection blocks content."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # HuggingFace keys: hf_...
        result = scanner.scan("HF token: hf_" + "A" * 34)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""
        assert any(f.finding_type.value == "secret_api_key" for f in result.findings)

    # Fix-r2: Boundary and negative tests for AI-ecosystem patterns
    def test_openai_key_boundary_19_chars_not_blocked(self):
        """Boundary: sk- + 19 alphanumeric chars should NOT match (threshold is 20)."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # sk- + 19 chars = 22 total, but only 19 alphanumeric after sk-
        result = scanner.scan("Key: sk-" + "A" * 19)

        # Should NOT be blocked (under 20 char threshold)
        assert result.action == ScanAction.PASSED
        assert result.content == "Key: sk-" + "A" * 19

    # Fix-r3: At-threshold boundary test (exactly 20 chars SHOULD be blocked)
    def test_openai_key_boundary_20_chars_blocked(self):
        """Boundary: sk- + exactly 20 alphanumeric chars SHOULD match (at threshold)."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # sk- + 20 chars = exactly at threshold
        result = scanner.scan("Key: sk-" + "A" * 20)

        # SHOULD be blocked (meets 20 char threshold)
        assert result.action == ScanAction.BLOCKED
        assert result.content == ""
        assert any(f.finding_type.value == "secret_api_key" for f in result.findings)

    def test_huggingface_key_boundary_29_chars_not_blocked(self):
        """Boundary: hf_ + 29 alphanumeric chars should NOT match (threshold is 30)."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # hf_ + 29 chars = 32 total, but only 29 alphanumeric after hf_
        result = scanner.scan("Token: hf_" + "A" * 29)

        # Should NOT be blocked (under 30 char threshold)
        assert result.action == ScanAction.PASSED
        assert result.content == "Token: hf_" + "A" * 29

    def test_short_sk_token_not_blocked(self):
        """Negative: short sk-token should NOT match."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Short key: sk-token")

        # Should NOT be blocked (too short)
        assert result.action == ScanAction.PASSED
        assert "sk-token" in result.content

    def test_huggingface_dataset_name_not_blocked(self):
        """Negative: hf_dataset_name in non-key context should NOT match."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Use dataset hf_dataset_name for training")

        # Should NOT be blocked - "hf_dataset_name" is not a key format
        assert result.action == ScanAction.PASSED
        assert "hf_dataset_name" in result.content

    def test_openai_proj_key_blocks(self):
        """Positive: sk-proj-XXX format (20+ chars) SHOULD match."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("API key: sk-proj-" + "A" * 24)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""
        assert any(f.finding_type.value == "secret_api_key" for f in result.findings)

    def test_openai_svcacct_key_blocks(self):
        """Positive: sk-svcacct-XXX format (20+ chars) SHOULD match."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Service key: sk-svcacct-" + "A" * 25)

        assert result.action == ScanAction.BLOCKED
        assert result.content == ""
        assert any(f.finding_type.value == "secret_api_key" for f in result.findings)


class TestGitHubHandleFalsePositives:
    """Test TD-161: GitHub handle regex false positive fixes."""

    @pytest.fixture(autouse=True)
    def _disable_detect_secrets(self, monkeypatch):
        """Isolate false-positive tests from Layer 2 detect-secrets interference."""
        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

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
            assert (
                "[HANDLE_REDACTED]" not in result.content
            ), f"False positive: {text} was flagged as GitHub handle"

    def test_real_github_handles_still_detected(self):
        """Test that real GitHub handles ARE still detected."""
        from memory.security_scanner import ScanAction, SecurityScanner

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

    @pytest.fixture(autouse=True)
    def _disable_detect_secrets(self, monkeypatch):
        """Isolate batch tests from Layer 2 detect-secrets interference."""
        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

    def test_batch_without_ner_scans_individually(self):
        """Test batch scanning without NER is sequential L1+L2."""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        results = scanner.scan_batch(["clean text 1", "clean text 2"])

        assert len(results) == 2
        assert all(3 not in r.layers_executed for r in results)

    def test_batch_force_ner_enables_layer3(self):
        """Test force_ner=True enables Layer 3 in batch."""
        from memory.security_scanner import SecurityScanner, _load_spacy_model

        if _load_spacy_model() is None:
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
        from memory.security_scanner import (
            ScanAction,
            SecurityScanner,
            _load_spacy_model,
        )

        if _load_spacy_model() is None:
            pytest.skip("SpaCy not available")

        scanner = SecurityScanner(enable_ner=True)
        results = scanner.scan_batch(
            [
                "Clean text about John Smith",
                "Secret: ghp_" + "A" * 36,
                "More text about Jane Doe",
            ],
            force_ner=True,
        )

        assert len(results) == 3
        assert results[1].action == ScanAction.BLOCKED
        assert 3 not in results[1].layers_executed  # Blocked BEFORE NER
        assert 3 in results[0].layers_executed  # Non-blocked DID run NER

    def test_batch_empty_list(self):
        """Test scan_batch() with empty list returns empty list."""
        from memory.security_scanner import SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        results = scanner.scan_batch([])

        assert results == []

    def test_batch_preserves_order(self):
        """Test that scan_batch() results order matches input order."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        results = scanner.scan_batch(
            [
                "Email: user@test.com",
                "Clean text here",
                "Phone: 555-123-4567",
            ]
        )

        assert len(results) == 3
        assert results[0].action == ScanAction.MASKED
        assert "[EMAIL_REDACTED]" in results[0].content
        assert results[1].action == ScanAction.PASSED
        assert results[2].action == ScanAction.MASKED
        assert "[PHONE_REDACTED]" in results[2].content


class TestSourceTypeAwareness:
    """Test source_type parameter and GitHub scan profiles (BP-090, RISK-001)."""

    def _make_relaxed_config(self):
        return type("MockConfig", (), {"security_scan_github_mode": "relaxed"})()

    def _make_strict_config(self):
        return type("MockConfig", (), {"security_scan_github_mode": "strict"})()

    def test_github_source_skips_layer2_in_relaxed_mode(self, monkeypatch):
        """GitHub content should skip Layer 2 detect-secrets in relaxed mode."""
        from memory.security_scanner import ScanAction, SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", True)
        monkeypatch.setattr(
            "memory.security_scanner.SecurityScanner._is_strict_github_mode",
            lambda self: False,
        )

        scanner = SecurityScanner(enable_ner=False)
        # High-entropy variable name that would trigger detect-secrets but not Layer 1 regex
        content = "config = {'TIMEOUT_SECONDS': 30, 'MAX_RETRIES': 3, 'POOL_SIZE': 10}"
        result = scanner.scan(content, source_type="github_issue")

        # Layer 2 is skipped, so no block from entropy detection
        assert result.action != ScanAction.BLOCKED
        # Layer 2 should not appear in executed layers
        assert 2 not in result.layers_executed

    def test_github_source_runs_layer2_in_strict_mode(self, monkeypatch):
        """GitHub content should use full scanning when strict mode is active."""
        from memory.security_scanner import SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)
        monkeypatch.setattr(
            "memory.security_scanner.SecurityScanner._is_strict_github_mode",
            lambda self: True,
        )

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Safe content here", source_type="github_issue")

        # In strict mode, Layer 2 must run (detect-secrets disabled via monkeypatch
        # so it won't actually block, but it will be in layers_executed)
        assert 2 in result.layers_executed

    def test_user_session_runs_layer2_in_relaxed_mode(self, monkeypatch):
        """TD-368: User session content runs Layer 2 in relaxed mode (default)."""
        from memory.security_scanner import SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Safe content here", source_type="user_session")

        # TD-368: Session content ALWAYS runs Layer 2 regardless of mode
        assert 2 in result.layers_executed

    def test_default_source_type_runs_layer2(self, monkeypatch):
        """TD-368: Default source_type (user_session) runs Layer 2."""
        from memory.security_scanner import SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Safe content")

        # TD-368: user_session ALWAYS runs Layer 2
        assert 2 in result.layers_executed

    def test_github_code_blob_skips_layer2_in_relaxed_mode(self, monkeypatch):
        """github_code_blob source should also skip Layer 2 in relaxed mode."""
        from memory.security_scanner import ScanAction, SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", True)
        monkeypatch.setattr(
            "memory.security_scanner.SecurityScanner._is_strict_github_mode",
            lambda self: False,
        )

        scanner = SecurityScanner(enable_ner=False)
        content = "API_KEY = 'placeholder' and TOKEN = 'not_real_value_just_a_name'"
        result = scanner.scan(content, source_type="github_code_blob")

        assert result.action != ScanAction.BLOCKED
        assert 2 not in result.layers_executed

    def test_non_github_non_session_source_always_runs_layer2(self, monkeypatch):
        """Non-github, non-session source types must always run Layer 2 regardless of mode."""
        from memory.security_scanner import SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

        scanner = SecurityScanner(enable_ner=False)
        # BUG-110: user_session now respects session mode (relaxed default skips L2)
        # Only test non-session, non-github sources here
        for src in ("jira_issue", "agent_memory"):
            result = scanner.scan("Safe text", source_type=src)
            assert (
                2 in result.layers_executed
            ), f"Layer 2 missing for source_type={src!r}"

    def test_github_source_skips_all_scanning_in_off_mode(self, monkeypatch):
        """GitHub content should skip ALL scanning when mode is 'off'."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        monkeypatch.setattr(scanner, "_is_github_scanning_off", lambda: True)

        # Content with patterns that would normally trigger L1 regex
        content = "Contact user@example.com about the configuration API_KEY variable"
        result = scanner.scan(content, source_type="github_issue")
        assert result.action == ScanAction.PASSED
        assert result.content == content  # No masking applied
        assert result.layers_executed == []  # No layers ran

    def test_off_mode_does_not_affect_user_sessions(self, monkeypatch):
        """Off mode for GitHub should NOT affect user_session scanning."""
        from memory.security_scanner import SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)
        scanner = SecurityScanner(enable_ner=False)
        monkeypatch.setattr(scanner, "_is_github_scanning_off", lambda: True)

        result = scanner.scan("Safe content", source_type="user_session")
        # user_session should still run all layers regardless of github off mode
        assert 1 in result.layers_executed


class TestGitHubIdContext:
    """Test TD-415: _is_github_id_context() whitelisting for GitHub platform IDs."""

    @pytest.fixture(autouse=True)
    def _disable_detect_secrets(self, monkeypatch):
        """Isolate tests from Layer 2 detect-secrets interference."""
        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)

    def test_run_prefix_whitelists(self):
        """Test that 'run' prefix whitelists GitHub run IDs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # True positive: should be whitelisted
        result = scanner.scan("See gh run 23997575319 for details")
        assert result.action == ScanAction.PASSED
        assert len(result.findings) == 0

    def test_run_id_prefix_whitelists(self):
        """Test that 'run_id:' prefix whitelists GitHub run IDs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("run_id: 23997575319")
        assert result.action == ScanAction.PASSED

    def test_runs_slash_whitelists(self):
        """Test that 'runs/' prefix whitelists GitHub run IDs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Check runs/23997575319 status")
        assert result.action == ScanAction.PASSED

    def test_job_prefix_whitelists(self):
        """Test that 'job' prefix whitelists GitHub job IDs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("job: 23997575319")
        assert result.action == ScanAction.PASSED

    def test_jobs_slash_whitelists(self):
        """Test that 'jobs/' prefix whitelists GitHub job IDs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("jobs/23997575319 failed")
        assert result.action == ScanAction.PASSED

    def test_workflow_prefix_whitelists(self):
        """Test that 'workflow' prefix whitelists GitHub workflow IDs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("workflow: 23997575319")
        assert result.action == ScanAction.PASSED

    def test_workflow_id_prefix_whitelists(self):
        """Test that 'workflow_id:' prefix whitelists GitHub workflow IDs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("workflow_id: 23997575319")
        assert result.action == ScanAction.PASSED

    def test_actions_slash_whitelists(self):
        """Test that 'actions/' prefix whitelists GitHub Actions IDs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("See actions/runs/23997575319")
        assert result.action == ScanAction.PASSED

    def test_issue_pr_fixes_hash_whitelists(self):
        """Test that 'issue #', 'PR #', 'fixes #' whitelists numeric refs."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # These should be whitelisted (not phone numbers)
        for text in ["issue #12345", "PR #45678", "fixes #78901"]:
            result = scanner.scan(text)
            assert result.action == ScanAction.PASSED, f"'{text}' should be whitelisted"

    def test_phone_numbers_still_flagged(self):
        """Test that regular phone numbers are NOT whitelisted."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        # True negatives: must NOT whitelist
        for text in ["Call me at 5551234567", "phone: 5551234567", "5551234567"]:
            result = scanner.scan(text)
            assert (
                result.action == ScanAction.MASKED
            ), f"'{text}' should be flagged as PII"
            assert "[PHONE_REDACTED]" in result.content

    def test_phone_hash_prefix_not_whitelisted(self):
        """Test F4: 'Phone #5551234567' is NOT whitelisted (bare # removed)."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("Phone #5551234567")
        # This MUST be flagged as PII - bare # is no longer a safe prefix
        assert (
            result.action == ScanAction.MASKED
        ), "Phone #5551234567 should be flagged as PII"
        assert "[PHONE_REDACTED]" in result.content

    def test_plain_number_still_flagged(self):
        """Test that plain 10-digit numbers are still flagged."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        result = scanner.scan("The ID is 5551234567")
        assert result.action == ScanAction.MASKED
        assert "[PHONE_REDACTED]" in result.content


class TestSessionModeAwareness:
    """Test BUG-110: security_scan_session_mode config for session content."""

    def test_session_scanning_relaxed_runs_layer2(self, monkeypatch):
        """TD-368: Session content runs Layer 2 in relaxed mode.

        Only GitHub content (trusted source) skips Layer 2 in relaxed mode.
        """
        from memory.security_scanner import SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)
        scanner = SecurityScanner(enable_ner=False)
        # Ensure session scanning is not disabled
        monkeypatch.setattr(scanner, "_is_session_scanning_off", lambda: False)

        result = scanner.scan("Safe content here", source_type="user_session")

        # TD-368: Session content MUST run Layer 2 even in relaxed mode
        assert 2 in result.layers_executed

    def test_session_scanning_off_skips_all(self, monkeypatch):
        """Session content should skip ALL scanning when mode is 'off'."""
        from memory.security_scanner import ScanAction, SecurityScanner

        scanner = SecurityScanner(enable_ner=False)
        monkeypatch.setattr(scanner, "_is_session_scanning_off", lambda: True)

        # Content with patterns that would normally trigger L1 regex
        content = "Contact user@example.com about the QDRANT_API_KEY configuration"
        result = scanner.scan(content, source_type="user_session")

        assert result.action == ScanAction.PASSED
        assert result.content == content  # No masking applied
        assert result.layers_executed == []  # No layers ran

    def test_session_mode_does_not_affect_github(self, monkeypatch):
        """Session mode config should NOT affect GitHub content scanning."""
        from memory.security_scanner import SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)
        scanner = SecurityScanner(enable_ner=False)
        # Session scanning off, but GitHub should still run normally
        monkeypatch.setattr(scanner, "_is_session_scanning_off", lambda: True)
        monkeypatch.setattr(scanner, "_is_github_scanning_off", lambda: False)
        monkeypatch.setattr(scanner, "_is_strict_github_mode", lambda: True)

        result = scanner.scan("Safe content", source_type="github_issue")

        # GitHub content should still be scanned (strict mode = all layers)
        assert 1 in result.layers_executed
        assert 2 in result.layers_executed

    def test_config_validation_session_mode(self, monkeypatch):
        """Reject invalid security_scan_session_mode values."""
        from pydantic import ValidationError

        from memory.config import MemoryConfig, reset_config

        reset_config()
        monkeypatch.setenv("SECURITY_SCAN_SESSION_MODE", "invalid_mode")

        with pytest.raises(ValidationError):
            MemoryConfig()

        # Clean up
        reset_config()

    def test_scan_batch_session_runs_layer2(self, monkeypatch):
        """TD-368: Batch scanning runs Layer 2 for session content."""
        from memory.security_scanner import SecurityScanner

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)
        scanner = SecurityScanner(enable_ner=False)
        # Ensure session scanning is not disabled
        monkeypatch.setattr(scanner, "_is_session_scanning_off", lambda: False)

        results = scanner.scan_batch(
            ["Clean text about config", "Another safe text"],
            source_type="user_session",
        )

        assert len(results) == 2
        # TD-368: Layer 2 MUST run for session content even in relaxed mode
        for r in results:
            assert 2 in r.layers_executed

    def test_scan_batch_session_runs_layer2_ner_enabled(self, monkeypatch):
        """Fix-r2: Batch scanning with NER enabled routes session content through NER code path."""
        from memory.security_scanner import SecurityScanner, _load_spacy_model

        if _load_spacy_model() is None:
            pytest.skip("SpaCy not available")

        monkeypatch.setattr("memory.security_scanner._detect_secrets_available", False)
        scanner = SecurityScanner(enable_ner=True)
        # Ensure session scanning is not disabled
        monkeypatch.setattr(scanner, "_is_session_scanning_off", lambda: False)

        results = scanner.scan_batch(
            ["Text about John Smith", "Text about Jane Doe"],
            source_type="user_session",
        )

        assert len(results) == 2
        # Session content MUST run all layers: L1, L2, L3 (NER)
        for r in results:
            assert 1 in r.layers_executed
            assert 2 in r.layers_executed
            assert 3 in r.layers_executed
            # NER should have detected names
            assert any(f.finding_type.value == "pii_name" for f in r.findings)
