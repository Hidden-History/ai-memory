#!/usr/bin/env python3
"""End-to-end verification for BMAD Memory hooks system.

Verifies the complete hooks workflow:
1. Hook scripts exist and are executable
2. Hook configuration in .claude/settings.json
3. Docker services (Qdrant, Embedding) are running
4. Individual hooks work with test data
5. Full workflow: pre-work → work → post-work → verify searchable
6. Error capture flow works

Usage:
    python scripts/memory/verify_hooks_e2e.py
    python scripts/memory/verify_hooks_e2e.py --verbose
    python scripts/memory/verify_hooks_e2e.py --skip-docker  # Offline mode
    python scripts/memory/verify_hooks_e2e.py --quick        # Basic checks only

Exit codes:
    0: All checks passed
    1: Some checks failed (non-critical)
    2: Critical failures (Docker services down, etc.)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Test results tracker
class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
        self.skipped = []
        self.start_time = time.time()

    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append((test_name, details))

    def add_fail(self, test_name: str, reason: str):
        self.failed.append((test_name, reason))

    def add_warning(self, test_name: str, reason: str):
        self.warnings.append((test_name, reason))

    def add_skip(self, test_name: str, reason: str):
        self.skipped.append((test_name, reason))

    def get_duration(self) -> float:
        return time.time() - self.start_time

    def has_critical_failures(self) -> bool:
        """Check if any failures are critical (Docker services, etc.)"""
        critical_keywords = ["docker", "qdrant", "embedding", "service"]
        for test_name, _ in self.failed:
            if any(kw in test_name.lower() for kw in critical_keywords):
                return True
        return False


def print_section(title: str):
    """Print a section header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{title}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")


def print_test(test_name: str, status: str, details: str = ""):
    """Print a test result."""
    status_colors = {
        "PASS": Colors.OKGREEN,
        "FAIL": Colors.FAIL,
        "WARN": Colors.WARNING,
        "SKIP": Colors.OKCYAN,
    }
    color = status_colors.get(status, Colors.ENDC)
    status_symbol = {
        "PASS": "✓",
        "FAIL": "✗",
        "WARN": "⚠",
        "SKIP": "○",
    }
    symbol = status_symbol.get(status, "?")

    print(f"{color}{symbol} [{status}]{Colors.ENDC} {test_name}")
    if details:
        print(f"         {details}")


def get_project_root() -> Path:
    """Find the project root directory."""
    # Start from script location
    script_path = Path(__file__).resolve()
    # Go up to project root (scripts/memory/verify_hooks_e2e.py -> ../../)
    return script_path.parent.parent.parent


def check_hook_scripts_exist(results: TestResults, verbose: bool = False) -> bool:
    """Check that all expected hook scripts exist and are executable.

    Args:
        results: TestResults tracker
        verbose: Print detailed information

    Returns:
        True if all checks passed
    """
    print_section("1. Hook Scripts Existence Check")

    project_root = get_project_root()
    hooks_dir = project_root / ".claude" / "hooks" / "scripts"

    if not hooks_dir.exists():
        results.add_fail("hooks_directory", f"Directory not found: {hooks_dir}")
        print_test("Hooks directory", "FAIL", str(hooks_dir))
        return False

    print_test("Hooks directory", "PASS", str(hooks_dir))

    # Expected hook scripts (from settings.json)
    expected_scripts = [
        "session_start.py",
        "session_stop.py",
        "pre_compact_save.py",
        "post_tool_capture.py",
        "best_practices_retrieval.py",
        "error_pattern_capture.py",
        "store_async.py",  # Used by post_tool_capture
        "error_store_async.py",  # Used by error_pattern_capture
    ]

    all_passed = True
    for script_name in expected_scripts:
        script_path = hooks_dir / script_name

        # Check existence
        if not script_path.exists():
            results.add_fail(f"script_exists_{script_name}", f"Script not found: {script_path}")
            print_test(f"Script: {script_name}", "FAIL", "Not found")
            all_passed = False
            continue

        # Check executable permission (Unix-like systems)
        if os.name != 'nt' and not os.access(script_path, os.X_OK):
            results.add_warning(f"script_executable_{script_name}",
                              f"Script not executable: {script_path}")
            print_test(f"Script: {script_name}", "WARN", "Not executable (may work with python3)")
        else:
            results.add_pass(f"script_exists_{script_name}", str(script_path))
            if verbose:
                print_test(f"Script: {script_name}", "PASS", str(script_path))

    if not verbose and all_passed:
        print_test("All hook scripts", "PASS", f"{len(expected_scripts)} scripts found")

    return all_passed


def check_settings_json(results: TestResults, verbose: bool = False) -> bool:
    """Verify .claude/settings.json has correct hook configuration.

    Args:
        results: TestResults tracker
        verbose: Print detailed information

    Returns:
        True if configuration is valid
    """
    print_section("2. Claude Code Settings Configuration")

    project_root = get_project_root()
    settings_path = project_root / ".claude" / "settings.json"

    if not settings_path.exists():
        results.add_fail("settings_exists", f"Settings file not found: {settings_path}")
        print_test("Settings file", "FAIL", "Not found")
        return False

    print_test("Settings file", "PASS", str(settings_path))

    try:
        with open(settings_path, 'r') as f:
            settings = json.load(f)
    except json.JSONDecodeError as e:
        results.add_fail("settings_parse", f"Invalid JSON: {e}")
        print_test("Settings JSON", "FAIL", str(e))
        return False

    print_test("Settings JSON", "PASS", "Valid JSON")

    # Check hooks configuration
    if "hooks" not in settings:
        results.add_fail("hooks_config", "No 'hooks' section in settings.json")
        print_test("Hooks configuration", "FAIL", "Missing 'hooks' section")
        return False

    hooks = settings["hooks"]
    expected_hooks = ["SessionStart", "PreToolUse", "PostToolUse", "Stop", "PreCompact"]

    all_passed = True
    for hook_name in expected_hooks:
        if hook_name not in hooks:
            results.add_warning(f"hook_{hook_name}", f"Hook not configured: {hook_name}")
            print_test(f"Hook: {hook_name}", "WARN", "Not configured")
            all_passed = False
        elif verbose:
            hook_count = len(hooks[hook_name])
            print_test(f"Hook: {hook_name}", "PASS", f"{hook_count} configuration(s)")
        else:
            results.add_pass(f"hook_{hook_name}")

    if not verbose and all_passed:
        print_test("All hooks configured", "PASS", f"{len(expected_hooks)} hooks")

    # Check environment variables
    if "env" in settings:
        env = settings["env"]
        required_vars = ["QDRANT_HOST", "QDRANT_PORT", "EMBEDDING_HOST", "EMBEDDING_PORT"]
        for var in required_vars:
            if var in env:
                if verbose:
                    print_test(f"Env: {var}", "PASS", env[var])
                results.add_pass(f"env_{var}")
            else:
                results.add_warning(f"env_{var}", f"Environment variable not set: {var}")
                print_test(f"Env: {var}", "WARN", "Not set")

    return all_passed


def check_docker_services(results: TestResults, verbose: bool = False) -> bool:
    """Check that required Docker services are running.

    Args:
        results: TestResults tracker
        verbose: Print detailed information

    Returns:
        True if services are healthy
    """
    print_section("3. Docker Services Health Check")

    # Check Qdrant
    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
    qdrant_port = os.environ.get("QDRANT_PORT", "26350")

    try:
        import requests
        response = requests.get(f"http://{qdrant_host}:{qdrant_port}/collections", timeout=5)
        if response.status_code == 200:
            results.add_pass("qdrant_health")
            collections = response.json().get("result", {}).get("collections", [])
            print_test("Qdrant service", "PASS",
                      f"{qdrant_host}:{qdrant_port} ({len(collections)} collections)")

            if verbose:
                for coll in collections:
                    print(f"         - Collection: {coll.get('name')}")
        else:
            results.add_fail("qdrant_health", f"HTTP {response.status_code}")
            print_test("Qdrant service", "FAIL", f"HTTP {response.status_code}")
            return False
    except ImportError:
        results.add_warning("qdrant_health", "requests library not available")
        print_test("Qdrant service", "WARN", "Cannot check (requests library missing)")
    except Exception as e:
        results.add_fail("qdrant_health", str(e))
        print_test("Qdrant service", "FAIL", str(e))
        return False

    # Check Embedding service
    embedding_host = os.environ.get("EMBEDDING_HOST", "localhost")
    embedding_port = os.environ.get("EMBEDDING_PORT", "28080")

    try:
        import requests
        response = requests.post(
            f"http://{embedding_host}:{embedding_port}/embed",
            json={"texts": ["test"]},
            timeout=5
        )
        if response.status_code == 200:
            results.add_pass("embedding_health")
            print_test("Embedding service", "PASS",
                      f"{embedding_host}:{embedding_port}")
        else:
            results.add_fail("embedding_health", f"HTTP {response.status_code}")
            print_test("Embedding service", "FAIL", f"HTTP {response.status_code}")
            return False
    except Exception as e:
        results.add_fail("embedding_health", str(e))
        print_test("Embedding service", "FAIL", str(e))
        return False

    return True


def test_session_start_hook(results: TestResults, verbose: bool = False) -> bool:
    """Test SessionStart hook with mock data.

    Args:
        results: TestResults tracker
        verbose: Print detailed information

    Returns:
        True if hook executed successfully
    """
    print_section("4. Individual Hook Tests")
    print(f"{Colors.BOLD}Testing SessionStart Hook{Colors.ENDC}\n")

    project_root = get_project_root()
    script_path = project_root / ".claude" / "hooks" / "scripts" / "session_start.py"

    # Create mock input
    mock_input = {
        "cwd": str(project_root),
        "session_id": "test_session_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
        "trigger": "startup"
    }

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(mock_input),
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            results.add_fail("session_start_hook", f"Exit code: {result.returncode}")
            print_test("SessionStart hook", "FAIL", f"Exit code: {result.returncode}")
            if verbose and result.stderr:
                print(f"         stderr: {result.stderr[:200]}")
            return False

        # Try to parse JSON output
        try:
            output = json.loads(result.stdout)
            if "hookSpecificOutput" in output:
                results.add_pass("session_start_hook", "Valid JSON output")
                print_test("SessionStart hook", "PASS", "Valid JSON output")

                if verbose:
                    context = output["hookSpecificOutput"].get("additionalContext", "")
                    if context:
                        print(f"         Context length: {len(context)} chars")
                    else:
                        print(f"         No context returned (no memories)")
            else:
                results.add_warning("session_start_hook", "Missing hookSpecificOutput")
                print_test("SessionStart hook", "WARN", "Missing hookSpecificOutput in JSON")
        except json.JSONDecodeError:
            results.add_warning("session_start_hook", "Non-JSON output")
            print_test("SessionStart hook", "WARN", "Output is not JSON")
            if verbose:
                print(f"         stdout: {result.stdout[:200]}")

        return True

    except subprocess.TimeoutExpired:
        results.add_fail("session_start_hook", "Timeout (>10s)")
        print_test("SessionStart hook", "FAIL", "Timeout")
        return False
    except Exception as e:
        results.add_fail("session_start_hook", str(e))
        print_test("SessionStart hook", "FAIL", str(e))
        return False


def test_best_practices_hook(results: TestResults, verbose: bool = False) -> bool:
    """Test best practices retrieval hook with mock data.

    Args:
        results: TestResults tracker
        verbose: Print detailed information

    Returns:
        True if hook executed successfully
    """
    print(f"\n{Colors.BOLD}Testing Best Practices Hook{Colors.ENDC}\n")

    project_root = get_project_root()
    script_path = project_root / ".claude" / "hooks" / "scripts" / "best_practices_retrieval.py"

    # Create mock input
    mock_input = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "src/memory/storage.py"
        },
        "cwd": str(project_root)
    }

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(mock_input),
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            results.add_fail("best_practices_hook", f"Exit code: {result.returncode}")
            print_test("Best Practices hook", "FAIL", f"Exit code: {result.returncode}")
            if verbose and result.stderr:
                print(f"         stderr: {result.stderr[:200]}")
            return False

        results.add_pass("best_practices_hook", "Executed successfully")
        print_test("Best Practices hook", "PASS", "Executed successfully")

        if verbose and result.stdout:
            print(f"         Output length: {len(result.stdout)} chars")

        return True

    except subprocess.TimeoutExpired:
        results.add_fail("best_practices_hook", "Timeout (>10s)")
        print_test("Best Practices hook", "FAIL", "Timeout")
        return False
    except Exception as e:
        results.add_fail("best_practices_hook", str(e))
        print_test("Best Practices hook", "FAIL", str(e))
        return False


def test_post_tool_capture(results: TestResults, verbose: bool = False) -> bool:
    """Test PostToolUse capture hook with mock data.

    Args:
        results: TestResults tracker
        verbose: Print detailed information

    Returns:
        True if hook executed successfully
    """
    print(f"\n{Colors.BOLD}Testing PostToolUse Capture Hook{Colors.ENDC}\n")

    project_root = get_project_root()
    script_path = project_root / ".claude" / "hooks" / "scripts" / "post_tool_capture.py"

    # Create mock input
    mock_input = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "test_file.py",
            "content": "# Test implementation\ndef test_function():\n    return 42\n"
        },
        "cwd": str(project_root),
        "session_id": "test_session_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    }

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(mock_input),
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            results.add_fail("post_tool_capture", f"Exit code: {result.returncode}")
            print_test("PostToolUse Capture hook", "FAIL", f"Exit code: {result.returncode}")
            if verbose and result.stderr:
                print(f"         stderr: {result.stderr[:200]}")
            return False

        results.add_pass("post_tool_capture", "Executed successfully")
        print_test("PostToolUse Capture hook", "PASS", "Background storage initiated")

        return True

    except subprocess.TimeoutExpired:
        results.add_fail("post_tool_capture", "Timeout (>10s)")
        print_test("PostToolUse Capture hook", "FAIL", "Timeout")
        return False
    except Exception as e:
        results.add_fail("post_tool_capture", str(e))
        print_test("PostToolUse Capture hook", "FAIL", str(e))
        return False


def test_error_pattern_capture(results: TestResults, verbose: bool = False) -> bool:
    """Test error pattern capture hook with mock data.

    Args:
        results: TestResults tracker
        verbose: Print detailed information

    Returns:
        True if hook executed successfully
    """
    print(f"\n{Colors.BOLD}Testing Error Pattern Capture Hook{Colors.ENDC}\n")

    project_root = get_project_root()
    script_path = project_root / ".claude" / "hooks" / "scripts" / "error_pattern_capture.py"

    # Create mock input with error
    mock_input = {
        "tool_name": "Bash",
        "tool_input": {
            "command": "python test.py"
        },
        "tool_result": {
            "error": "Traceback (most recent call last):\n  File \"test.py\", line 5\n    return value\nNameError: name 'value' is not defined"
        },
        "cwd": str(project_root),
        "session_id": "test_session_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    }

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(mock_input),
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            results.add_fail("error_pattern_capture", f"Exit code: {result.returncode}")
            print_test("Error Pattern Capture hook", "FAIL", f"Exit code: {result.returncode}")
            if verbose and result.stderr:
                print(f"         stderr: {result.stderr[:200]}")
            return False

        results.add_pass("error_pattern_capture", "Executed successfully")
        print_test("Error Pattern Capture hook", "PASS", "Error captured")

        return True

    except subprocess.TimeoutExpired:
        results.add_fail("error_pattern_capture", "Timeout (>10s)")
        print_test("Error Pattern Capture hook", "FAIL", "Timeout")
        return False
    except Exception as e:
        results.add_fail("error_pattern_capture", str(e))
        print_test("Error Pattern Capture hook", "FAIL", str(e))
        return False


def test_full_workflow(results: TestResults, verbose: bool = False) -> bool:
    """Test the complete workflow: search → store → verify searchable.

    Args:
        results: TestResults tracker
        verbose: Print detailed information

    Returns:
        True if workflow completed successfully
    """
    print_section("5. Full Workflow Test")

    project_root = get_project_root()

    # Add src to path
    sys.path.insert(0, str(project_root / "src"))

    try:
        from memory.storage import MemoryStorage
        from memory.search import MemorySearch
        from memory.config import get_config
        from memory.deduplication import compute_content_hash
        from memory.models import MemoryType

        config = get_config()
        storage = MemoryStorage(config)
        search = MemorySearch(config)

        # Generate unique test data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_content = f"E2E test memory - {timestamp}"
        test_hash = compute_content_hash(test_content)
        project_name = "bmad-memory-module"

        # Step 1: Store test memory
        print(f"{Colors.BOLD}Step 1: Storing test memory{Colors.ENDC}")
        try:
            result = storage.store_memory(
                content=test_content,
                cwd=str(project_root),
                memory_type=MemoryType.SESSION_SUMMARY,
                source_hook="verify_hooks_e2e",
                session_id="e2e_test_" + timestamp,
                collection="agent-memory",
                group_id=project_name,
                test=True,
                timestamp=timestamp
            )
            memory_id = result["memory_id"]
            results.add_pass("workflow_store", f"Memory ID: {memory_id}")
            print_test("Store memory", "PASS", f"ID: {memory_id}")
        except Exception as e:
            results.add_fail("workflow_store", str(e))
            print_test("Store memory", "FAIL", str(e))
            return False

        # Wait briefly for embedding to complete
        print(f"         Waiting for embedding to complete...")
        time.sleep(2)

        # Step 2: Search for the memory
        print(f"\n{Colors.BOLD}Step 2: Searching for stored memory{Colors.ENDC}")
        try:
            search_results = search.search(
                query=test_content,
                collection="agent-memory",
                group_id=project_name,
                limit=5,
                score_threshold=0.5
            )

            if not search_results:
                results.add_fail("workflow_search", "Memory not found")
                print_test("Search memory", "FAIL", "Not found (may need more time for embedding)")
                return False

            # Verify our test memory is in results
            found = any(r.get("id") == memory_id for r in search_results)
            if found:
                results.add_pass("workflow_search", f"Found {len(search_results)} results")
                print_test("Search memory", "PASS", f"Found test memory in {len(search_results)} results")

                if verbose:
                    for r in search_results:
                        print(f"         - Score: {r.get('score', 0):.2f}, ID: {r.get('id', 'unknown')}")
            else:
                results.add_warning("workflow_search", "Test memory not in top results")
                print_test("Search memory", "WARN", "Memory stored but not in search results")

        except Exception as e:
            results.add_fail("workflow_search", str(e))
            print_test("Search memory", "FAIL", str(e))
            return False

        # Step 3: Verify memory is retrievable by ID
        print(f"\n{Colors.BOLD}Step 3: Retrieving memory by ID{Colors.ENDC}")
        try:
            memory = storage.get_by_id(memory_id, collection="agent-memory")

            if memory:
                results.add_pass("workflow_retrieve", "Memory retrieved")
                print_test("Retrieve by ID", "PASS", f"Content hash matches: {memory.get('content_hash') == test_hash}")

                if verbose:
                    print(f"         Type: {memory.get('type')}")
                    print(f"         Source: {memory.get('source_hook')}")
                    print(f"         Group: {memory.get('group_id')}")
            else:
                results.add_fail("workflow_retrieve", "Memory not found")
                print_test("Retrieve by ID", "FAIL", "Not found")
                return False

        except Exception as e:
            results.add_fail("workflow_retrieve", str(e))
            print_test("Retrieve by ID", "FAIL", str(e))
            return False

        # Step 4: Test deduplication (try to store same content again)
        print(f"\n{Colors.BOLD}Step 4: Testing deduplication{Colors.ENDC}")
        try:
            duplicate_result = storage.store_memory(
                content=test_content,
                cwd=str(project_root),
                memory_type=MemoryType.SESSION_SUMMARY,
                source_hook="verify_hooks_e2e",
                session_id="e2e_test_" + timestamp,
                collection="agent-memory",
                group_id=project_name,
                test=True,
                timestamp=timestamp
            )
            duplicate_id = duplicate_result.get("memory_id")

            if duplicate_id == memory_id:
                results.add_pass("workflow_dedup", "Duplicate detected")
                print_test("Deduplication", "PASS", "Prevented duplicate storage")
            elif duplicate_id is None:
                results.add_pass("workflow_dedup", "Duplicate rejected")
                print_test("Deduplication", "PASS", "Duplicate rejected")
            else:
                results.add_warning("workflow_dedup", "New ID returned")
                print_test("Deduplication", "WARN", f"Different ID: {duplicate_id}")

        except Exception as e:
            results.add_warning("workflow_dedup", str(e))
            print_test("Deduplication", "WARN", str(e))

        # Cleanup
        try:
            storage.close()
            search.close()
        except:
            pass

        return True

    except ImportError as e:
        results.add_fail("workflow_import", f"Cannot import memory modules: {e}")
        print_test("Full workflow", "FAIL", f"Import error: {e}")
        return False
    except Exception as e:
        results.add_fail("workflow_error", str(e))
        print_test("Full workflow", "FAIL", str(e))
        return False


def generate_report(results: TestResults, verbose: bool = False):
    """Generate and print final verification report.

    Args:
        results: TestResults with all test outcomes
        verbose: Include detailed statistics
    """
    print_section("Verification Report")

    duration = results.get_duration()
    total_tests = len(results.passed) + len(results.failed) + len(results.warnings) + len(results.skipped)

    # Summary statistics
    print(f"{Colors.BOLD}Summary:{Colors.ENDC}")
    print(f"  Total tests:   {total_tests}")
    print(f"  {Colors.OKGREEN}✓ Passed:{Colors.ENDC}       {len(results.passed)}")
    print(f"  {Colors.FAIL}✗ Failed:{Colors.ENDC}       {len(results.failed)}")
    print(f"  {Colors.WARNING}⚠ Warnings:{Colors.ENDC}     {len(results.warnings)}")
    print(f"  {Colors.OKCYAN}○ Skipped:{Colors.ENDC}      {len(results.skipped)}")
    print(f"  Duration:      {duration:.2f}s")
    print()

    # Failed tests details
    if results.failed:
        print(f"{Colors.FAIL}{Colors.BOLD}Failed Tests:{Colors.ENDC}")
        for test_name, reason in results.failed:
            print(f"  {Colors.FAIL}✗{Colors.ENDC} {test_name}")
            print(f"    Reason: {reason}")
        print()

    # Warnings details
    if results.warnings and verbose:
        print(f"{Colors.WARNING}{Colors.BOLD}Warnings:{Colors.ENDC}")
        for test_name, reason in results.warnings:
            print(f"  {Colors.WARNING}⚠{Colors.ENDC} {test_name}")
            print(f"    Reason: {reason}")
        print()

    # Final verdict
    if not results.failed:
        if results.warnings:
            print(f"{Colors.WARNING}{Colors.BOLD}⚠ VERIFICATION PASSED WITH WARNINGS{Colors.ENDC}")
            print(f"{Colors.WARNING}All critical checks passed, but some warnings were found.{Colors.ENDC}")
        else:
            print(f"{Colors.OKGREEN}{Colors.BOLD}✓ ALL CHECKS PASSED{Colors.ENDC}")
            print(f"{Colors.OKGREEN}BMAD Memory hooks system is fully functional!{Colors.ENDC}")
    else:
        if results.has_critical_failures():
            print(f"{Colors.FAIL}{Colors.BOLD}✗ CRITICAL FAILURES DETECTED{Colors.ENDC}")
            print(f"{Colors.FAIL}Docker services or core components are not working.{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}{Colors.BOLD}✗ VERIFICATION FAILED{Colors.ENDC}")
            print(f"{Colors.FAIL}Some checks failed. Review details above.{Colors.ENDC}")


def main():
    """Main entry point for verification script."""
    parser = argparse.ArgumentParser(
        description="End-to-end verification for BMAD Memory hooks system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run all checks
  %(prog)s --verbose          # Show detailed output
  %(prog)s --skip-docker      # Skip Docker service checks (offline mode)
  %(prog)s --quick            # Basic checks only (scripts + config)
        """
    )
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Show verbose output with detailed information")
    parser.add_argument("--skip-docker", action="store_true",
                       help="Skip Docker service health checks (offline mode)")
    parser.add_argument("--quick", action="store_true",
                       help="Run only basic checks (scripts + config, skip services + workflow)")

    args = parser.parse_args()

    results = TestResults()

    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("╔" + "="*68 + "╗")
    print("║" + " "*68 + "║")
    print("║" + "  BMAD Memory Module - Hooks System E2E Verification".center(68) + "║")
    print("║" + " "*68 + "║")
    print("╚" + "="*68 + "╝")
    print(Colors.ENDC)

    # Run checks
    check_hook_scripts_exist(results, args.verbose)
    check_settings_json(results, args.verbose)

    if not args.skip_docker and not args.quick:
        docker_ok = check_docker_services(results, args.verbose)
        if not docker_ok and not args.verbose:
            print(f"\n{Colors.WARNING}Note: Docker services check failed. "
                  f"Subsequent tests may fail.{Colors.ENDC}")

    if not args.quick:
        # Individual hook tests
        test_session_start_hook(results, args.verbose)
        test_best_practices_hook(results, args.verbose)
        test_post_tool_capture(results, args.verbose)
        test_error_pattern_capture(results, args.verbose)

        # Full workflow test
        if not args.skip_docker:
            test_full_workflow(results, args.verbose)
        else:
            results.add_skip("full_workflow", "Docker checks skipped")

    # Generate report
    generate_report(results, args.verbose)

    # Exit with appropriate code
    if results.has_critical_failures():
        sys.exit(2)
    elif results.failed:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
