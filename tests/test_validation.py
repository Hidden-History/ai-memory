"""Unit tests for payload validation.

Tests AC 1.3.3 from Story 1.3.
"""

import pytest
from src.memory.validation import (
    ValidationError,
    validate_payload,
    compute_content_hash,
)


class TestValidatePayload:
    """Test validate_payload function."""

    def test_validate_payload_valid(self):
        """Valid payload passes validation with no errors."""
        payload = {
            "content": "This is valid content for a memory implementation",
            "group_id": "test-project",
            "type": "implementation",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload)
        assert errors == []

    def test_validate_payload_missing_content(self):
        """Missing content field fails validation."""
        payload = {
            "group_id": "test-project",
            "type": "implementation",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload)
        assert len(errors) == 1
        assert "content" in errors[0].lower()

    def test_validate_payload_missing_group_id(self):
        """Missing group_id field fails validation."""
        payload = {
            "content": "Test content here",
            "type": "implementation",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload)
        assert len(errors) == 1
        assert "group_id" in errors[0].lower()

    def test_validate_payload_missing_type(self):
        """Missing type field fails validation."""
        payload = {
            "content": "Test content here",
            "group_id": "proj",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload)
        assert len(errors) == 1
        assert "type" in errors[0].lower()

    def test_validate_payload_missing_source_hook(self):
        """Missing source_hook field fails validation."""
        payload = {
            "content": "Test content here",
            "group_id": "proj",
            "type": "implementation",
        }
        errors = validate_payload(payload)
        assert len(errors) == 1
        assert "source_hook" in errors[0].lower()

    def test_validate_payload_missing_multiple_fields(self):
        """Multiple missing fields returns multiple errors."""
        payload = {
            "content": "Test content here",
            # Missing: group_id, type, source_hook
        }
        errors = validate_payload(payload)
        assert len(errors) == 3
        assert any("group_id" in e.lower() for e in errors)
        assert any("type" in e.lower() for e in errors)
        assert any("source_hook" in e.lower() for e in errors)

    def test_validate_payload_content_too_short(self):
        """Content shorter than 10 chars fails validation."""
        payload = {
            "content": "Short",  # Only 5 chars
            "group_id": "proj",
            "type": "implementation",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload)
        assert len(errors) == 1
        assert "too short" in errors[0].lower()
        assert "10 chars" in errors[0].lower()

    def test_validate_payload_content_too_long(self):
        """Content longer than 100,000 chars fails validation."""
        payload = {
            "content": "x" * 100001,  # 100,001 chars
            "group_id": "proj",
            "type": "implementation",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload)
        assert len(errors) == 1
        assert "exceeds maximum" in errors[0].lower()
        assert "100,000" in errors[0]

    def test_validate_payload_invalid_type(self):
        """Invalid type value fails validation."""
        payload = {
            "content": "Valid content here",
            "group_id": "proj",
            "type": "invalid_type",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload)
        assert len(errors) == 1
        assert "invalid type" in errors[0].lower()

    def test_validate_payload_valid_types(self):
        """All valid types pass validation."""
        valid_types = ["implementation", "session_summary", "decision", "pattern"]

        for valid_type in valid_types:
            payload = {
                "content": "Valid content for testing",
                "group_id": "proj",
                "type": valid_type,
                "source_hook": "PostToolUse",
            }
            errors = validate_payload(payload)
            assert errors == [], f"Type {valid_type} should be valid but got errors: {errors}"

    def test_validate_payload_invalid_source_hook(self):
        """Invalid source_hook value fails validation."""
        payload = {
            "content": "Valid content here",
            "group_id": "proj",
            "type": "implementation",
            "source_hook": "InvalidHook",
        }
        errors = validate_payload(payload)
        assert len(errors) == 1
        assert "invalid source_hook" in errors[0].lower()

    def test_validate_payload_valid_source_hooks(self):
        """All valid source_hooks pass validation."""
        valid_hooks = ["PostToolUse", "Stop", "SessionStart", "seed_script"]

        for valid_hook in valid_hooks:
            payload = {
                "content": "Valid content for testing",
                "group_id": "proj",
                "type": "implementation",
                "source_hook": valid_hook,
            }
            errors = validate_payload(payload)
            assert errors == [], f"Hook {valid_hook} should be valid but got errors: {errors}"

    def test_validate_payload_empty_string_values(self):
        """Empty string values fail validation (treated as missing)."""
        payload = {
            "content": "",  # Empty
            "group_id": "",  # Empty
            "type": "implementation",
            "source_hook": "PostToolUse",
        }
        errors = validate_payload(payload)
        # Should have errors for empty content and group_id
        # Plus content too short error
        assert len(errors) >= 2
        assert any("content" in e.lower() for e in errors)
        assert any("group_id" in e.lower() for e in errors)


class TestComputeContentHash:
    """Test compute_content_hash function."""

    def test_compute_content_hash_deterministic(self):
        """Hash is deterministic for same content."""
        content = "Test content for hashing"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        assert hash1 == hash2

    def test_compute_content_hash_sha256_length(self):
        """Hash is SHA256 (64 hex characters)."""
        content = "Test content"
        content_hash = compute_content_hash(content)
        assert len(content_hash) == 64  # SHA256 hex length
        assert all(c in "0123456789abcdef" for c in content_hash)

    def test_compute_content_hash_different_content(self):
        """Different content produces different hashes."""
        hash1 = compute_content_hash("Content A")
        hash2 = compute_content_hash("Content B")
        assert hash1 != hash2

    def test_compute_content_hash_unicode(self):
        """Hash handles unicode content correctly."""
        content = "Test with unicode: 你好世界 🌍"
        content_hash = compute_content_hash(content)
        assert len(content_hash) == 64
        # Should be reproducible
        assert content_hash == compute_content_hash(content)
