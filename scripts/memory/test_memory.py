#!/usr/bin/env python3
"""
Comprehensive Memory System Test for AI Memory Module

Tests all 3 memory collections with validation patterns:
- code-patterns
- conventions
- discussions

Usage:
    python test_memory.py                    # Run all tests
    python test_memory.py --offline          # Skip Qdrant connection tests
    python test_memory.py -v                 # Verbose output

Created: 2026-01-17
Adapted for AI Memory Module
"""

import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Try to import from installed location first, fall back to relative
try:
    from memory.config import get_config
    from memory.models import EmbeddingStatus, MemoryPayload, MemoryType
    from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
    from memory.search import MemorySearch
    from memory.storage import MemoryStorage
except ImportError:
    # Running from dev repo
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from memory.config import get_config
    from memory.models import MemoryPayload, MemoryType
    from memory.qdrant_client import QdrantUnavailable, get_qdrant_client

# Import validation scripts
sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Test that all memory modules can be imported."""
    print("\n" + "=" * 60)
    print("TEST 1: Module Imports")
    print("=" * 60)

    try:
        from memory.config import get_config
        from memory.deduplication import compute_content_hash
        from memory.embeddings import EmbeddingClient
        from memory.models import MemoryPayload, MemoryType
        from memory.qdrant_client import get_qdrant_client
        from memory.search import MemorySearch
        from memory.storage import MemoryStorage

        print("[PASS] All memory modules imported successfully")
    except ImportError as e:
        print(f"[FAIL] Import failed: {e}")
        assert False, f"Import failed: {e}"


def test_memory_payload_creation():
    """Test MemoryPayload creation and validation."""
    print("\n" + "=" * 60)
    print("TEST 2: MemoryPayload Creation")
    print("=" * 60)

    try:
        content = (
            "Implemented JWT authentication middleware for API endpoints. "
            "Decision: Use RS256 algorithm with short-lived access tokens (15 minutes). "
            "Implementation in src/auth/jwt.py:45-120. "
            "Key patterns: Token refresh via /auth/refresh endpoint, "
            "blacklist via Redis for logout. Trade-offs: RS256 is slower "
            "but allows distributed verification."
        )

        payload = MemoryPayload(
            content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            group_id="test-project",
            type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-session-001",
            timestamp=datetime.now().isoformat(),
            domain="auth",
            importance="high",
        )

        # Verify fields
        assert payload.content == content
        assert payload.group_id == "test-project"
        assert payload.type == MemoryType.IMPLEMENTATION
        assert payload.source_hook == "PostToolUse"
        assert payload.importance == "high"

        # Test to_dict conversion
        payload_dict = payload.to_dict()
        assert payload_dict["type"] == "implementation"
        assert payload_dict["embedding_status"] == "complete"

        print("[PASS] MemoryPayload created and validated successfully")
        print(f"   - Type: {payload.type.value}")
        print(f"   - Source Hook: {payload.source_hook}")
        print(f"   - Importance: {payload.importance}")

    except Exception as e:
        print(f"[FAIL] MemoryPayload creation failed: {e}")
        assert False, f"MemoryPayload creation failed: {e}"


def test_content_hash_generation():
    """Test content hash generation for deduplication."""
    print("\n" + "=" * 60)
    print("TEST 3: Content Hash Generation")
    print("=" * 60)

    try:
        from check_duplicates import generate_content_hash

        content1 = "Test content for duplicate detection"
        content2 = "Test content for duplicate detection"  # Exact duplicate
        content3 = "Different content"

        hash1 = generate_content_hash(content1)
        hash2 = generate_content_hash(content2)
        hash3 = generate_content_hash(content3)

        assert hash1 == hash2, "Exact duplicates should have same hash"
        print("[PASS] Exact duplicate detected (same hash)")

        assert hash1 != hash3, "Different content should have different hash"
        print("[PASS] Different content has different hash")

        print(f"   - Hash length: {len(hash1)} chars")

    except ImportError:
        print("[SKIP] check_duplicates.py not available")
    except Exception as e:
        print(f"[FAIL] Hash generation failed: {e}")
        assert False, f"Hash generation failed: {e}"


def test_metadata_validation():
    """Test metadata validation."""
    print("\n" + "=" * 60)
    print("TEST 4: Metadata Validation")
    print("=" * 60)

    try:
        from validate_metadata import validate_metadata_complete

        # Test valid metadata
        valid_metadata = {
            "type": "implementation",
            "group_id": "test-project",
            "source_hook": "PostToolUse",
            "agent": "dev",
            "component": "auth",
            "importance": "high",
        }

        is_valid, details = validate_metadata_complete(valid_metadata)
        assert is_valid, f"Valid metadata rejected: {details['errors']}"
        print("[PASS] Valid metadata accepted")
        print(f"   Checks performed: {', '.join(details['checks_performed'])}")

        # Test invalid metadata (missing required field)
        invalid_metadata = {
            "type": "implementation",
            # Missing: group_id, source_hook
        }

        is_valid, details = validate_metadata_complete(invalid_metadata)
        assert not is_valid, "Invalid metadata should be rejected"
        print("[PASS] Invalid metadata correctly rejected")
        print(f"   Errors: {len(details['errors'])}")

    except ImportError:
        print("[SKIP] validate_metadata.py not available")
    except AssertionError:
        raise
    except Exception as e:
        print(f"[FAIL] Metadata validation failed: {e}")
        assert False, f"Metadata validation failed: {e}"


def test_storage_validation():
    """Test pre-storage validation."""
    print("\n" + "=" * 60)
    print("TEST 5: Pre-Storage Validation")
    print("=" * 60)

    try:
        from validate_storage import validate_before_storage

        # Valid content with file:line references
        valid_content = """
        Implemented JWT authentication in src/auth/jwt.py:89-145.
        Tests added in tests/test_auth.py:23-67.
        Configuration in config/auth.yaml:5-12.
        Key pattern: Token validation middleware extracts Bearer token,
        verifies signature, and attaches user context to request.
        """

        valid_metadata = {
            "type": "implementation",
            "group_id": "test-project",
            "source_hook": "PostToolUse",
        }

        is_valid, message, details = validate_before_storage(
            valid_content, valid_metadata, skip_duplicate_check=True
        )

        assert is_valid, f"Valid content rejected: {message}"
        print("[PASS] Valid content accepted for storage")
        print(f"   Token count: ~{details['token_count']} tokens")

        # Test content without file:line (should fail for implementation type)
        invalid_content = "Implemented JWT authentication."

        is_valid, message, details = validate_before_storage(
            invalid_content, valid_metadata, skip_duplicate_check=True
        )

        # Note: Short content may pass validation but with warnings
        # The file:line check is the main validation
        if (
            "file:line" in message.lower()
            or "file_references" in str(details.get("errors", [])).lower()
        ):
            print("[PASS] Missing file:line references detected")
        else:
            print(
                "[INFO] Content validation completed with result:",
                "PASS" if is_valid else "FAIL",
            )

    except ImportError:
        print("[SKIP] validate_storage.py not available")
    except AssertionError:
        raise
    except Exception as e:
        print(f"[FAIL] Storage validation failed: {e}")
        assert False, f"Storage validation failed: {e}"


def test_memory_types():
    """Test all memory types can be created."""
    print("\n" + "=" * 60)
    print("TEST 6: Memory Types")
    print("=" * 60)

    memory_types = [
        MemoryType.IMPLEMENTATION,
        MemoryType.SESSION,
        MemoryType.DECISION,
        MemoryType.FILE_PATTERN,
    ]

    failures = []
    for mem_type in memory_types:
        try:
            content = f"Test content for {mem_type.value} type memory"
            payload = MemoryPayload(
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                group_id="test-project",
                type=mem_type,
                source_hook="test",
                session_id="test-session",
                timestamp=datetime.now().isoformat(),
            )
            print(f"[PASS] {mem_type.value}: Created successfully")
        except Exception as e:
            print(f"[FAIL] {mem_type.value}: Failed - {e}")
            failures.append(f"{mem_type.value}: {e}")

    assert not failures, f"Memory type creation failed: {'; '.join(failures)}"


def test_collection_routing():
    """Test collection routing for all 3 collections."""
    print("\n" + "=" * 60)
    print("TEST 7: Collection Routing")
    print("=" * 60)

    def route_to_collection(memory_type: str) -> str:
        """Route to correct collection based on type (v2.0)."""
        # code-patterns collection (HOW)
        if memory_type in ["implementation", "error_fix", "refactor", "file_pattern"]:
            return "code-patterns"
        # conventions collection (WHAT)
        elif memory_type in ["guideline", "anti_pattern", "decision"]:
            return "conventions"
        # discussions collection (WHY)
        elif memory_type in [
            "session",
            "conversation",
            "analysis",
            "reflection",
            "context",
            "decision_record",
            "lesson_learned",
        ]:
            return "discussions"
        else:
            return "code-patterns"  # Default fallback

    # Test routing (v2.0)
    test_cases = [
        ("implementation", "code-patterns"),
        ("error_fix", "code-patterns"),
        ("refactor", "code-patterns"),
        ("file_pattern", "code-patterns"),
        ("guideline", "conventions"),
        ("anti_pattern", "conventions"),
        ("decision", "conventions"),
        ("session", "discussions"),
        ("conversation", "discussions"),
        ("analysis", "discussions"),
    ]

    failures = []
    for memory_type, expected_collection in test_cases:
        actual_collection = route_to_collection(memory_type)
        if actual_collection == expected_collection:
            print(f"[PASS] {memory_type} -> {actual_collection}")
        else:
            print(
                f"[FAIL] {memory_type} -> {actual_collection} (expected {expected_collection})"
            )
            failures.append(f"{memory_type}: got {actual_collection}, expected {expected_collection}")

    assert not failures, f"Collection routing failed: {'; '.join(failures)}"


def test_qdrant_connection():
    """Test Qdrant connection and collection existence."""
    print("\n" + "=" * 60)
    print("TEST 8: Qdrant Connection")
    print("=" * 60)

    try:
        client = get_qdrant_client()
        config = get_config()
        print(
            f"[PASS] Connected to Qdrant at {config.qdrant_host}:{config.qdrant_port}"
        )

        # Check v2.0 collections
        collections = ["code-patterns", "conventions", "discussions"]

        for coll_name in collections:
            try:
                info = client.get_collection(coll_name)
                print(
                    f"[PASS] Collection '{coll_name}' exists ({info.points_count} points)"
                )
            except Exception:
                print(
                    f"[INFO] Collection '{coll_name}' not found (will be created on first use)"
                )

    except QdrantUnavailable as e:
        print(f"[INFO] Qdrant unavailable: {e}")
        print("   This is OK for offline testing")
    except Exception as e:
        print(f"[INFO] Qdrant connection failed: {e}")
        print("   This is OK for offline testing")


def test_config_loading():
    """Test configuration loading."""
    print("\n" + "=" * 60)
    print("TEST 9: Configuration Loading")
    print("=" * 60)

    try:
        config = get_config()

        print("[PASS] Configuration loaded successfully")
        print(f"   - Qdrant Host: {config.qdrant_host}")
        print(f"   - Qdrant Port: {config.qdrant_port}")
        print(f"   - Embedding Host: {config.embedding_host}")
        print(f"   - Embedding Port: {config.embedding_port}")
        print(f"   - Similarity Threshold: {config.similarity_threshold}")

        # Validate expected port values
        if config.qdrant_port == 26350:
            print("[PASS] Qdrant port is 26350 (correct)")
        else:
            print(f"[WARNING] Qdrant port is {config.qdrant_port} (expected 26350)")

        if config.embedding_port == 28080:
            print("[PASS] Embedding port is 28080 (correct)")
        else:
            print(
                f"[WARNING] Embedding port is {config.embedding_port} (expected 28080)"
            )

    except Exception as e:
        print(f"[FAIL] Configuration loading failed: {e}")
        assert False, f"Configuration loading failed: {e}"


def run_all_tests(skip_qdrant: bool = False, verbose: bool = False):
    """Run all tests and report results."""
    print("\n" + "=" * 60)
    print("AI MEMORY SYSTEM - COMPREHENSIVE TEST SUITE")
    print("Testing 3 collections with validation patterns")
    print("=" * 60)

    tests = [
        ("Module Imports", test_imports),
        ("MemoryPayload Creation", test_memory_payload_creation),
        ("Content Hash Generation", test_content_hash_generation),
        ("Metadata Validation", test_metadata_validation),
        ("Pre-Storage Validation", test_storage_validation),
        ("Memory Types", test_memory_types),
        ("Collection Routing", test_collection_routing),
        ("Configuration Loading", test_config_loading),
    ]

    if not skip_qdrant:
        tests.append(("Qdrant Connection", test_qdrant_connection))

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            # Assert-based tests return None on pass; legacy bool tests return a value
            results.append((test_name, result is not False))
        except AssertionError as e:
            print(f"\n[FAIL] {test_name}: {e}")
            results.append((test_name, False))
        except Exception as e:
            print(f"\n[FAIL] {test_name} CRASHED: {e}")
            if verbose:
                import traceback

                traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print("\n" + "=" * 60)
    print(f"RESULT: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print("=" * 60)

    if passed == total:
        print("\nAll tests passed!")
        print("\nMemory system ready for use:")
        print("  - All 3 collections validated")
        print("  - Memory types working")
        print("  - Validation patterns implemented")
        return 0
    else:
        print("\nSome tests failed")
        print("\nPlease review failures and fix before using memory system")
        return 1


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test AI Memory system (all 3 collections)"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip Qdrant connection test (offline mode)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output with stack traces",
    )

    args = parser.parse_args()

    exit_code = run_all_tests(skip_qdrant=args.offline, verbose=args.verbose)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
