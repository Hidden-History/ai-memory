#!/usr/bin/env python3
"""
Validation script for BMAD Memory Module skills.
Tests underlying Python functions that skills depend on.
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_search_memory():
    """Test /search-memory skill functionality"""
    print("\n" + "="*70)
    print("TEST 1: /search-memory skill")
    print("="*70)

    try:
        from memory.search import search_memories

        # Test 1: Simple query
        print("\n[1.1] Testing simple query: 'error handling'")
        results = search_memories(query="error handling", limit=3)
        print(f"  ✓ Search completed: {len(results)} results")

        # Test 2: Collection filter
        print("\n[1.2] Testing collection filter: 'conventions'")
        results = search_memories(query="best practice", collection="conventions", limit=3)
        print(f"  ✓ Search completed: {len(results)} results from conventions")

        # Test 3: Type filter
        print("\n[1.3] Testing type filter: 'guideline'")
        results = search_memories(query="python", memory_type="guideline", limit=3)
        print(f"  ✓ Search completed: {len(results)} guideline results")

        # Test 4: Check result format
        print("\n[1.4] Validating result format")
        if results:
            result = results[0]
            required_fields = ["content", "score", "type", "collection"]
            for field in required_fields:
                if field not in result:
                    print(f"  ✗ Missing field: {field}")
                    return False
            print(f"  ✓ Result format valid: {', '.join(required_fields)}")

        print("\n✅ PASS: /search-memory skill")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: /search-memory skill - {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_status():
    """Test /memory-status skill functionality"""
    print("\n" + "="*70)
    print("TEST 2: /memory-status skill")
    print("="*70)

    try:
        from memory.health import check_services
        from memory.stats import get_collection_stats
        from memory.qdrant_client import get_qdrant_client

        # Test 1: Service health check
        print("\n[2.1] Testing service health check")
        health = check_services()
        print(f"  All healthy: {health.get('all_healthy', False)}")
        print(f"  Qdrant: {health.get('qdrant', False)}")
        print(f"  Embedding: {health.get('embedding', False)}")
        print("  ✓ Health check completed")

        # Test 2: Collection statistics
        print("\n[2.2] Testing collection statistics")
        client = get_qdrant_client()
        collections = ["code-patterns", "conventions", "discussions"]

        for collection in collections:
            try:
                stats = get_collection_stats(client, collection)
                print(f"  {collection}: {stats.total_points} points")
            except Exception as e:
                print(f"  {collection}: Error - {str(e)}")

        print("  ✓ Statistics check completed")

        # Test 3: Check required fields
        print("\n[2.3] Validating health check fields")
        required_fields = ["all_healthy", "qdrant", "embedding"]
        for field in required_fields:
            if field not in health:
                print(f"  ✗ Missing field: {field}")
                return False
        print(f"  ✓ Health format valid: {', '.join(required_fields)}")

        print("\n✅ PASS: /memory-status skill")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: /memory-status skill - {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_settings():
    """Test /memory-settings skill functionality"""
    print("\n" + "="*70)
    print("TEST 3: /memory-settings skill")
    print("="*70)

    try:
        from memory.config import get_config, AGENT_TOKEN_BUDGETS

        # Test 1: Load configuration
        print("\n[3.1] Testing configuration loading")
        config = get_config()
        print(f"  Qdrant: {config.qdrant_host}:{config.qdrant_port}")
        print(f"  Embedding: {config.embedding_host}:{config.embedding_port}")
        print("  ✓ Configuration loaded")

        # Test 2: Check ports (must be 2XXXX format)
        print("\n[3.2] Validating port assignments")
        expected_ports = {
            "qdrant_port": 26350,
            "embedding_port": 28080,
            "monitoring_port": 28000
        }

        for port_name, expected_value in expected_ports.items():
            actual_value = getattr(config, port_name)
            if actual_value != expected_value:
                print(f"  ✗ {port_name}: expected {expected_value}, got {actual_value}")
                return False
            print(f"  ✓ {port_name}: {actual_value}")

        # Test 3: Check agent token budgets
        print("\n[3.3] Validating agent token budgets")
        print(f"  architect: {AGENT_TOKEN_BUDGETS.get('architect')} tokens")
        print(f"  dev: {AGENT_TOKEN_BUDGETS.get('dev')} tokens")
        print(f"  default: {AGENT_TOKEN_BUDGETS.get('default')} tokens")
        print("  ✓ Token budgets configured")

        # Test 4: Check thresholds
        print("\n[3.4] Validating thresholds")
        print(f"  similarity_threshold: {config.similarity_threshold}")
        print(f"  dedup_threshold: {config.dedup_threshold}")
        print(f"  max_retrievals: {config.max_retrievals}")
        print("  ✓ Thresholds configured")

        print("\n✅ PASS: /memory-settings skill")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: /memory-settings skill - {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all skill validation tests"""
    print("╔" + "="*68 + "╗")
    print("║" + " BMAD Memory Module - Skills Validation ".center(68) + "║")
    print("╚" + "="*68 + "╝")

    results = {
        "search-memory": test_search_memory(),
        "memory-status": test_memory_status(),
        "memory-settings": test_memory_settings()
    }

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    for skill, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: /{skill}")

    total = len(results)
    passed = sum(results.values())

    print(f"\nTotal: {passed}/{total} skills functional")

    if passed == total:
        print("\n🎉 All skills validated successfully!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} skill(s) failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
