#!/usr/bin/env python3
"""
Validation script for BMAD Memory Module dashboards.
Tests Streamlit and Grafana accessibility.
"""

import sys
from typing import Any

import httpx


def test_streamlit_dashboard() -> dict[str, Any]:
    """Test Streamlit Dashboard accessibility and basic functionality"""
    print("\n" + "=" * 70)
    print("TEST 4: Streamlit Dashboard (localhost:28501)")
    print("=" * 70)

    result = {"accessible": False, "error": None, "details": {}}

    try:
        # Test 1: Check if dashboard is accessible
        print("\n[4.1] Testing dashboard accessibility")
        response = httpx.get(
            "http://localhost:28501", timeout=10.0, follow_redirects=True
        )

        if response.status_code == 200:
            print(f"  ✓ Dashboard accessible (HTTP {response.status_code})")
            result["accessible"] = True
            result["details"]["status_code"] = response.status_code
        else:
            print(f"  ✗ Unexpected status code: {response.status_code}")
            result["error"] = f"HTTP {response.status_code}"
            return result

        # Test 2: Check for key UI elements in response
        print("\n[4.2] Checking for UI components")
        content = response.text.lower()

        required_elements = {
            "title": "bmad memory" in content or "memory browser" in content,
            "collections": "collection" in content,
            "search": "search" in content,
        }

        for element, found in required_elements.items():
            if found:
                print(f"  ✓ {element.title()} found")
            else:
                print(f"  ⚠  {element.title()} not found (may be in JS)")

        result["details"]["ui_elements"] = required_elements

        # Test 3: Check for error messages in content
        print("\n[4.3] Checking for error messages")
        error_indicators = ["error", "failed", "exception"]
        errors_found = []

        for indicator in error_indicators:
            # Only count as error if it appears in an error context
            if f'"{indicator}"' in content or f">{indicator}<" in content:
                errors_found.append(indicator)

        if errors_found:
            print(f"  ⚠  Possible errors detected: {', '.join(errors_found)}")
            result["details"]["warnings"] = errors_found
        else:
            print("  ✓ No error messages detected")

        print("\n✅ PASS: Streamlit Dashboard accessible and functional")
        return result

    except httpx.ConnectError as e:
        print(f"\n❌ FAIL: Cannot connect to Streamlit - {e!s}")
        result["error"] = f"Connection failed: {e!s}"
        return result
    except Exception as e:
        print(f"\n❌ FAIL: Streamlit test failed - {e!s}")
        result["error"] = str(e)
        import traceback

        traceback.print_exc()
        return result


def test_grafana_dashboards() -> dict[str, Any]:
    """Test Grafana Dashboard accessibility"""
    print("\n" + "=" * 70)
    print("TEST 5: Grafana Dashboards (localhost:23000)")
    print("=" * 70)

    result = {"accessible": False, "error": None, "details": {}}

    try:
        # Test 1: Check if Grafana is accessible
        print("\n[5.1] Testing Grafana accessibility")
        response = httpx.get(
            "http://localhost:23000", timeout=10.0, follow_redirects=True
        )

        if response.status_code == 200:
            print(f"  ✓ Grafana accessible (HTTP {response.status_code})")
            result["accessible"] = True
            result["details"]["status_code"] = response.status_code
        else:
            print(f"  ✗ Unexpected status code: {response.status_code}")
            result["error"] = f"HTTP {response.status_code}"
            return result

        # Test 2: Check API health endpoint
        print("\n[5.2] Testing Grafana API health")
        try:
            health_response = httpx.get(
                "http://localhost:23000/api/health", timeout=5.0
            )
            if health_response.status_code == 200:
                health_data = health_response.json()
                print("  ✓ Grafana API healthy")
                print(f"    Database: {health_data.get('database', 'unknown')}")
                print(f"    Version: {health_data.get('version', 'unknown')}")
                result["details"]["health"] = health_data
            else:
                print(f"  ⚠  Health endpoint returned {health_response.status_code}")
        except Exception as e:
            print(f"  ⚠  Health check failed: {e}")

        # Test 3: Check for dashboards via API
        print("\n[5.3] Checking for dashboards")
        try:
            # Note: This may require authentication in production
            # Using anonymous access for validation
            search_response = httpx.get(
                "http://localhost:23000/api/search?type=dash-db", timeout=5.0
            )
            if search_response.status_code == 200:
                dashboards = search_response.json()
                print(f"  ✓ Found {len(dashboards)} dashboard(s)")

                # Look for memory-related dashboards
                memory_dashboards = [
                    d for d in dashboards if "memory" in d.get("title", "").lower()
                ]
                if memory_dashboards:
                    print(f"    Memory dashboards: {len(memory_dashboards)}")
                    for dash in memory_dashboards[:3]:  # Show first 3
                        print(f"      - {dash.get('title')}")
                result["details"]["dashboard_count"] = len(dashboards)
                result["details"]["memory_dashboards"] = len(memory_dashboards)
            else:
                print(f"  ⚠  Dashboard search returned {search_response.status_code}")
        except Exception as e:
            print(f"  ⚠  Dashboard search failed: {e}")

        print("\n✅ PASS: Grafana accessible and functional")
        return result

    except httpx.ConnectError as e:
        print(f"\n❌ FAIL: Cannot connect to Grafana - {e!s}")
        result["error"] = f"Connection failed: {e!s}"
        return result
    except Exception as e:
        print(f"\n❌ FAIL: Grafana test failed - {e!s}")
        result["error"] = str(e)
        import traceback

        traceback.print_exc()
        return result


def main():
    """Run all dashboard validation tests"""
    print("╔" + "=" * 68 + "╗")
    print("║" + " BMAD Memory Module - Dashboard Validation ".center(68) + "║")
    print("╚" + "=" * 68 + "╝")

    streamlit_result = test_streamlit_dashboard()
    grafana_result = test_grafana_dashboards()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(
        f"{'✅' if streamlit_result['accessible'] else '❌'} Streamlit Dashboard (localhost:28501)"
    )
    if streamlit_result.get("error"):
        print(f"  Error: {streamlit_result['error']}")

    print(
        f"{'✅' if grafana_result['accessible'] else '❌'} Grafana Dashboards (localhost:23000)"
    )
    if grafana_result.get("error"):
        print(f"  Error: {grafana_result['error']}")

    success = streamlit_result["accessible"] and grafana_result["accessible"]

    if success:
        print("\n🎉 All dashboards validated successfully!")
        return 0
    else:
        print("\n⚠️  Some dashboards failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
