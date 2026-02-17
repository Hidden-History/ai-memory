"""
Integration tests for SPEC-009: Security Scanning Pipeline

Tests end-to-end scanner integration with:
- MemoryStorage.store_memory()
- MemoryStorage.store_memories_batch()
- Hook scripts (via subprocess)
- Performance benchmarks
"""

import json
import subprocess
import uuid
from pathlib import Path

import pytest

from memory.config import get_config
from memory.security_scanner import SecurityScanner, ScanAction
from memory.storage import MemoryStorage


@pytest.mark.integration
class TestStorageIntegration:
    """Test scanner integration with MemoryStorage."""

    def test_store_memory_with_secrets_blocks_storage(self):
        """Test that secrets detected in store_memory() block storage."""
        config = get_config()
        if not config.security_scanning_enabled:
            pytest.skip("Security scanning disabled in config")

        storage = MemoryStorage()

        # Attempt to store memory with GitHub PAT
        result = storage.store_memory(
            content="My token is ghp_" + "A" * 36,
            content_type="implementation",
            source_hook="test",
            session_id="test-session",
            cwd="/tmp",
        )

        assert result["status"] == "blocked"
        assert result["reason"] == "secrets_detected"
        assert result["memory_id"] is None

    def test_store_memory_with_pii_masks_content(self):
        """Test that PII detected in store_memory() is masked."""
        config = get_config()
        if not config.security_scanning_enabled:
            pytest.skip("Security scanning disabled in config")

        storage = MemoryStorage()

        # Store memory with email
        result = storage.store_memory(
            content="Contact me at user@example.com for details",
            content_type="implementation",
            source_hook="test",
            session_id="test-session",
            cwd="/tmp",
        )

        assert result["status"] == "stored"
        assert result["memory_id"] is not None

        # Verify stored content is masked
        from memory.qdrant_client import get_qdrant_client
        client = get_qdrant_client()
        point = client.retrieve(
            collection_name="code-patterns",
            ids=[result["memory_id"]],
            with_payload=True,
        )[0]

        assert "[EMAIL_REDACTED]" in point.payload["content"]
        assert "user@example.com" not in point.payload["content"]

    def test_store_memory_clean_content_passes(self):
        """Test that clean content passes through store_memory() unchanged."""
        config = get_config()
        if not config.security_scanning_enabled:
            pytest.skip("Security scanning disabled in config")

        storage = MemoryStorage()

        clean_content = "This is clean code without any PII or secrets"
        result = storage.store_memory(
            content=clean_content,
            content_type="implementation",
            source_hook="test",
            session_id="test-session",
            cwd="/tmp",
        )

        assert result["status"] == "stored"
        assert result["memory_id"] is not None

        # Verify stored content is unchanged
        from memory.qdrant_client import get_qdrant_client
        client = get_qdrant_client()
        point = client.retrieve(
            collection_name="code-patterns",
            ids=[result["memory_id"]],
            with_payload=True,
        )[0]

        assert point.payload["content"] == clean_content


@pytest.mark.integration
class TestBatchStorageIntegration:
    """Test scanner integration with batch storage."""

    def test_batch_storage_filters_out_blocked_memories(self):
        """Test that batch storage filters out memories with secrets."""
        config = get_config()
        if not config.security_scanning_enabled:
            pytest.skip("Security scanning disabled in config")

        storage = MemoryStorage()

        memories = [
            {
                "content": "Clean content 1",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "test-session",
            },
            {
                "content": "Secret: ghp_" + "A" * 36,
                "type": "implementation",
                "source_hook": "test",
                "session_id": "test-session",
            },
            {
                "content": "Clean content 2",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "test-session",
            },
        ]

        results = storage.store_memories_batch(memories, cwd="/tmp")

        # Should have 3 results: 2 stored, 1 blocked
        assert len(results) == 3

        # First result: stored
        assert results[0]["status"] == "stored"
        assert results[0]["memory_id"] is not None

        # Second result: blocked
        assert results[1]["status"] == "blocked"
        assert results[1]["reason"] == "secrets_detected"
        assert results[1]["memory_id"] is None

        # Third result: stored
        assert results[2]["status"] == "stored"
        assert results[2]["memory_id"] is not None

    def test_batch_storage_masks_pii_in_all_memories(self):
        """Test that batch storage masks PII in all memories."""
        config = get_config()
        if not config.security_scanning_enabled:
            pytest.skip("Security scanning disabled in config")

        storage = MemoryStorage()

        memories = [
            {
                "content": "Email: user1@example.com",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "test-session",
            },
            {
                "content": "Phone: 555-123-4567",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "test-session",
            },
        ]

        results = storage.store_memories_batch(memories, cwd="/tmp")

        assert len(results) == 2
        assert all(r["status"] == "stored" for r in results)

        # Verify masking in stored content
        from memory.qdrant_client import get_qdrant_client
        client = get_qdrant_client()

        point1 = client.retrieve(
            collection_name="code-patterns",
            ids=[results[0]["memory_id"]],
            with_payload=True,
        )[0]
        assert "[EMAIL_REDACTED]" in point1.payload["content"]
        assert "user1@example.com" not in point1.payload["content"]

        point2 = client.retrieve(
            collection_name="code-patterns",
            ids=[results[1]["memory_id"]],
            with_payload=True,
        )[0]
        assert "[PHONE_REDACTED]" in point2.payload["content"]
        assert "555-123-4567" not in point2.payload["content"]


@pytest.mark.integration
class TestHookScriptIntegration:
    """Test scanner integration with hook scripts via subprocess."""

    def test_user_prompt_hook_blocks_secrets(self):
        """Test that user_prompt_store_async blocks secrets."""
        hook_script = Path(__file__).parent.parent.parent / ".claude" / "hooks" / "scripts" / "user_prompt_store_async.py"

        if not hook_script.exists():
            pytest.skip("Hook script not found")

        config = get_config()
        if not config.security_scanning_enabled:
            pytest.skip("Security scanning disabled in config")

        # Prepare hook input with secret
        hook_input = {
            "session_id": str(uuid.uuid4()),
            "prompt": "My GitHub token is ghp_" + "A" * 36,
            "turn_number": 1,
        }

        # Run hook script
        result = subprocess.run(
            ["python3", str(hook_script)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Hook should succeed (exit 0) but not store the memory
        assert result.returncode == 0

    def test_agent_response_hook_masks_pii(self):
        """Test that agent_response_store_async masks PII."""
        hook_script = Path(__file__).parent.parent.parent / ".claude" / "hooks" / "scripts" / "agent_response_store_async.py"

        if not hook_script.exists():
            pytest.skip("Hook script not found")

        config = get_config()
        if not config.security_scanning_enabled:
            pytest.skip("Security scanning disabled in config")

        # Prepare hook input with PII
        hook_input = {
            "session_id": str(uuid.uuid4()),
            "response_text": "You can reach me at contact@example.com",
            "turn_number": 1,
        }

        # Run hook script
        result = subprocess.run(
            ["python3", str(hook_script)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Hook should succeed
        assert result.returncode == 0


@pytest.mark.integration
class TestPerformance:
    """Test scanner performance benchmarks."""

    def test_layer1_and_2_performance_under_10ms(self):
        """Test that L1+L2 scanning completes in <10ms (hook requirement)."""
        scanner = SecurityScanner(enable_ner=False)

        test_content = "Email: user@example.com, Phone: 555-123-4567, IP: 8.8.8.8"

        # Warmup
        scanner.scan(test_content)

        # Measure
        result = scanner.scan(test_content)

        # L1+L2 should be <10ms
        assert result.scan_duration_ms < 10.0

    def test_all_layers_performance_under_100ms(self):
        """Test that L1+L2+L3 scanning completes in <100ms (GitHub sync requirement)."""
        config = get_config()
        if not config.security_scanning_ner_enabled:
            pytest.skip("NER layer disabled in config")

        scanner = SecurityScanner(enable_ner=True)

        test_content = "John Doe sent an email to user@example.com about the project."

        # Warmup (SpaCy model load)
        scanner.scan(test_content)

        # Measure
        result = scanner.scan(test_content)

        # L1+L2+L3 should be <100ms for short texts
        assert result.scan_duration_ms < 100.0


@pytest.mark.integration
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_scanner_unavailable_degrades_gracefully(self):
        """Test that storage works when scanner is unavailable."""
        config = get_config()

        # Create storage with scanner disabled
        config.security_scanning_enabled = False
        storage = MemoryStorage(config)

        # Should store successfully without scanning
        result = storage.store_memory(
            content="Email: user@example.com",
            content_type="implementation",
            source_hook="test",
            session_id="test-session",
            cwd="/tmp",
        )

        assert result["status"] == "stored"
        assert result["memory_id"] is not None

    def test_scanner_error_continues_with_original_content(self):
        """Test that scanner errors don't block storage."""
        config = get_config()
        if not config.security_scanning_enabled:
            pytest.skip("Security scanning disabled in config")

        storage = MemoryStorage()

        # Extremely long content that might cause scanner issues
        long_content = "Clean text. " * 10000

        result = storage.store_memory(
            content=long_content,
            content_type="implementation",
            source_hook="test",
            session_id="test-session",
            cwd="/tmp",
        )

        # Should still store successfully
        assert result["status"] == "stored"
        assert result["memory_id"] is not None


@pytest.mark.integration
class TestScannerLayers:
    """Test individual scanner layers."""

    def test_layer1_detects_common_secrets(self):
        """Test that Layer 1 detects common secret patterns."""
        scanner = SecurityScanner(enable_ner=False)

        # Test GitHub PAT
        result = scanner.scan("ghp_" + "A" * 36)
        assert result.action == ScanAction.BLOCKED
        assert 1 in result.layers_executed

        # Test AWS key
        result = scanner.scan("AKIAIOSFODNN7EXAMPLE")
        assert result.action == ScanAction.BLOCKED

    def test_layer1_detects_common_pii(self):
        """Test that Layer 1 detects common PII patterns."""
        scanner = SecurityScanner(enable_ner=False)

        # Test email
        result = scanner.scan("user@example.com")
        assert result.action == ScanAction.MASKED
        assert "[EMAIL_REDACTED]" in result.content

        # Test phone
        result = scanner.scan("555-123-4567")
        assert result.action == ScanAction.MASKED
        assert "[PHONE_REDACTED]" in result.content

    def test_layer3_detects_person_names(self):
        """Test that Layer 3 (SpaCy NER) detects person names."""
        config = get_config()
        if not config.security_scanning_ner_enabled:
            pytest.skip("NER layer disabled in config")

        scanner = SecurityScanner(enable_ner=True)

        result = scanner.scan("John Smith wrote this code.")

        assert result.action == ScanAction.MASKED
        assert 3 in result.layers_executed
        # SpaCy should detect "John Smith" as PERSON
        assert any(f.finding_type.value == "pii_name" for f in result.findings)
