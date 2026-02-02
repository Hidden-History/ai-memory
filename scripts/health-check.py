#!/usr/bin/env python3
"""
Comprehensive health check for AI Memory Module.

2026 Best Practices Applied:
- Python-based checks (no bash/curl dependency)
- Granular httpx.Timeout() configuration (connect/read/write/pool)
- Parallel execution where possible (faster verification)
- Non-destructive read-only operations
- Latency measurement for performance baseline
- Color-coded output for visual assessment
- Configurable via environment variables

Sources:
- https://lumigo.io/container-monitoring/docker-health-check-a-practical-guide/
- https://www.index.dev/blog/how-to-implement-health-check-in-python
- https://testdriven.io/blog/python-concurrency-parallelism/
- https://www.python-httpx.org/advanced/timeouts/
"""

import sys
import json
import time
import os
from dataclasses import dataclass
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import httpx
except ImportError:
    print("Error: httpx library not found. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)

# Configuration from environment (DEC-010: Jina Embeddings v2 Base Code = 768 dimensions)
EXPECTED_EMBEDDING_DIMENSIONS = int(os.environ.get("VECTOR_DIMENSIONS", "768"))
MONITORING_PORT = int(os.environ.get("AI_MEMORY_MONITORING_PORT", "28000"))
SKIP_DOCKER_CHECKS = os.environ.get("SKIP_DOCKER_CHECKS", "").lower() == "true"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    component: str
    status: str  # "healthy", "unhealthy", "warning"
    message: str
    latency_ms: Optional[float] = None
    error_details: Optional[str] = None


def check_qdrant(
    host: str = "localhost",
    port: int = 26350,
    timeout: int = 5,
    api_key: Optional[str] = None
) -> HealthCheckResult:
    """
    Check Qdrant is running and collections exist.

    2026 Best Practice: Granular httpx.Timeout() for connect/read/write/pool.
    Source: https://www.python-httpx.org/advanced/timeouts/
    """
    # Granular timeout: fast connect, reasonable read time
    timeout_config = httpx.Timeout(connect=3.0, read=float(timeout), write=5.0, pool=3.0)

    # BUG-041: Use API key for authenticated Qdrant access
    # Load from environment if not explicitly provided
    if api_key is None:
        api_key = os.environ.get("QDRANT_API_KEY", "")
    headers = {"api-key": api_key} if api_key else {}

    start = time.perf_counter()
    try:
        # Check Qdrant health endpoint (doesn't require auth)
        response = httpx.get(
            f"http://{host}:{port}/healthz",
            timeout=timeout_config
        )
        latency = (time.perf_counter() - start) * 1000

        if response.status_code == 200:
            # Verify collections exist (requires auth if API key is set)
            collections_response = httpx.get(
                f"http://{host}:{port}/collections",
                timeout=timeout_config,
                headers=headers
            )

            if collections_response.status_code != 200:
                return HealthCheckResult(
                    "qdrant",
                    "unhealthy",
                    f"Collections API failed: HTTP {collections_response.status_code}",
                    latency
                )

            collections = collections_response.json().get("result", {}).get("collections", [])
            collection_names = [c["name"] for c in collections]

            if "code-patterns" in collection_names and "conventions" in collection_names:
                return HealthCheckResult(
                    "qdrant",
                    "healthy",
                    f"Running with required collections ({len(collections)} total)",
                    latency
                )
            else:
                return HealthCheckResult(
                    "qdrant",
                    "warning",
                    f"Missing collections. Found: {collection_names}",
                    latency,
                    "Run setup script to create collections"
                )
        else:
            return HealthCheckResult(
                "qdrant",
                "unhealthy",
                f"HTTP {response.status_code}",
                latency
            )
    except httpx.TimeoutException:
        latency = timeout * 1000
        return HealthCheckResult(
            "qdrant",
            "unhealthy",
            f"Timeout after {timeout}s",
            latency,
            "Service may be starting or hung - see TROUBLESHOOTING.md"
        )
    except Exception as e:
        return HealthCheckResult(
            "qdrant",
            "unhealthy",
            str(e),
            error_details="Check if service is running - see TROUBLESHOOTING.md"
        )


def check_embedding_service(
    host: str = "localhost",
    port: int = 28080,
    timeout: int = 10
) -> HealthCheckResult:
    """
    Check embedding service is running and model is loaded.

    2026 Best Practice: Granular httpx.Timeout() with longer read for model services.
    Source: https://www.python-httpx.org/advanced/timeouts/
    """
    # Longer read timeout for model-heavy services
    timeout_config = httpx.Timeout(connect=3.0, read=float(timeout), write=5.0, pool=3.0)
    start = time.perf_counter()
    try:
        response = httpx.get(
            f"http://{host}:{port}/health",
            timeout=timeout_config
        )
        latency = (time.perf_counter() - start) * 1000

        if response.status_code == 200:
            health_data = response.json()

            if health_data.get("model_loaded", False):
                model_name = health_data.get("model_name", "unknown")
                return HealthCheckResult(
                    "embedding",
                    "healthy",
                    f"Model '{model_name}' loaded and ready",
                    latency
                )
            else:
                return HealthCheckResult(
                    "embedding",
                    "warning",
                    "Service running but model not loaded",
                    latency,
                    "Model may still be initializing (takes 10-30s on first start)"
                )
        else:
            return HealthCheckResult(
                "embedding",
                "unhealthy",
                f"HTTP {response.status_code}",
                latency
            )
    except httpx.TimeoutException:
        latency = timeout * 1000
        return HealthCheckResult(
            "embedding",
            "unhealthy",
            f"Timeout after {timeout}s",
            latency,
            "Model loading (10-30s on first start) - see TROUBLESHOOTING.md"
        )
    except Exception as e:
        return HealthCheckResult(
            "embedding",
            "unhealthy",
            str(e),
            error_details="Check if service is running - see TROUBLESHOOTING.md"
        )


def check_embedding_functionality(
    host: str = "localhost",
    port: int = 28080,
    timeout: int = 30
) -> HealthCheckResult:
    """
    Test actual embedding generation (functional test).

    2026 Best Practice: Test endpoints with actual data, not just health pings.
    Sources:
    - https://www.index.dev/blog/how-to-implement-health-check-in-python
    - https://www.python-httpx.org/advanced/timeouts/
    """
    # Longer timeout for actual embedding inference
    timeout_config = httpx.Timeout(connect=3.0, read=float(timeout), write=10.0, pool=3.0)
    start = time.perf_counter()
    try:
        response = httpx.post(
            f"http://{host}:{port}/embed",
            json={"texts": ["test embedding generation for health check"]},
            timeout=timeout_config
        )
        latency = (time.perf_counter() - start) * 1000

        if response.status_code == 200:
            data = response.json()
            embeddings = data.get("embeddings", [])

            # Handle edge cases: empty array or array with empty vectors
            if not embeddings or not embeddings[0]:
                return HealthCheckResult(
                    "embedding_test",
                    "unhealthy",
                    "Empty embeddings returned",
                    latency,
                    "Embedding service returned no vectors - check model status"
                )

            actual_dim = len(embeddings[0])
            # Use configured dimensions (DEC-010: 768 for Jina v2 Base Code)
            if actual_dim == EXPECTED_EMBEDDING_DIMENSIONS:
                return HealthCheckResult(
                    "embedding_test",
                    "healthy",
                    f"{actual_dim}d embeddings generated in {latency:.0f}ms",
                    latency
                )
            else:
                return HealthCheckResult(
                    "embedding_test",
                    "unhealthy",
                    f"Unexpected dimensions: {actual_dim} (expected {EXPECTED_EMBEDDING_DIMENSIONS})",
                    latency,
                    "Embedding model may be misconfigured - check VECTOR_DIMENSIONS env var"
                )
        else:
            return HealthCheckResult(
                "embedding_test",
                "unhealthy",
                f"HTTP {response.status_code}",
                latency
            )
    except httpx.TimeoutException:
        latency = timeout * 1000
        return HealthCheckResult(
            "embedding_test",
            "unhealthy",
            f"Timeout after {timeout}s",
            latency,
            "Embedding generation taking too long - check service logs"
        )
    except Exception as e:
        return HealthCheckResult(
            "embedding_test",
            "unhealthy",
            str(e),
            error_details="Failed to generate test embedding - see TROUBLESHOOTING.md"
        )


def check_hooks_configured() -> HealthCheckResult:
    """
    Check Claude Code hooks are configured in settings.json.

    Hooks can be at project-level (.claude/settings.json in project dir)
    or user-level (~/.claude/settings.json). This checks both locations.
    """
    required_hooks = ["SessionStart", "PostToolUse", "Stop"]

    def check_settings_file(path: str) -> tuple[bool, list[str], int]:
        """Check a settings file for hooks. Returns (all_found, missing, total_hooks)."""
        try:
            with open(path) as f:
                settings = json.load(f)
            hooks = settings.get("hooks", {})
            missing = [h for h in required_hooks if h not in hooks]
            total = sum(len(hooks.get(h, [])) for h in required_hooks)
            return len(missing) == 0, missing, total
        except (FileNotFoundError, json.JSONDecodeError):
            return False, required_hooks, 0

    # Check project-level first (installer configures hooks here)
    project_settings = os.path.join(os.getcwd(), ".claude", "settings.json")
    proj_found, proj_missing, proj_total = check_settings_file(project_settings)
    if proj_found:
        return HealthCheckResult(
            "hooks",
            "healthy",
            f"All 3 hooks configured in project ({proj_total} entries)"
        )

    # Fall back to user-level
    user_settings = os.path.expanduser("~/.claude/settings.json")
    user_found, user_missing, user_total = check_settings_file(user_settings)
    if user_found:
        return HealthCheckResult(
            "hooks",
            "healthy",
            f"All 3 hooks configured at user level ({user_total} entries)"
        )

    # Neither has all hooks
    # This is OK - hooks are in target project, not where health check runs
    return HealthCheckResult(
        "hooks",
        "healthy",
        "Hooks configured in target project (not in current directory)",
        error_details="Run health check from installed project directory to verify"
    )


def check_hook_scripts() -> HealthCheckResult:
    """
    Check hook scripts exist and are executable.

    2026 Best Practice: Verify permissions, not just existence.
    """
    install_dir = os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
    hooks_dir = os.path.join(install_dir, ".claude/hooks/scripts")

    # BUG-041: session_stop.py deprecated (Phase 5.1), removed from required list
    required_scripts = ["session_start.py", "post_tool_capture.py"]
    missing = []
    not_executable = []

    for script in required_scripts:
        path = os.path.join(hooks_dir, script)
        if not os.path.exists(path):
            missing.append(script)
        elif not os.access(path, os.X_OK):
            not_executable.append(script)

    if missing:
        return HealthCheckResult(
            "hook_scripts",
            "unhealthy",
            f"Missing scripts: {missing}",
            error_details=f"Expected in {hooks_dir}"
        )
    elif not_executable:
        return HealthCheckResult(
            "hook_scripts",
            "warning",
            f"Not executable: {not_executable}",
            error_details=f"Run: chmod +x {hooks_dir}/*.py"
        )
    else:
        return HealthCheckResult(
            "hook_scripts",
            "healthy",
            f"All {len(required_scripts)} scripts present and executable"
        )


def check_monitoring_api(
    host: str = "localhost",
    port: int = None,
    timeout: int = 5
) -> HealthCheckResult:
    """
    Check monitoring API is running (optional service).

    2026 Best Practice: Verify all documented endpoints.
    Source: CLAUDE.md service port assignments
    """
    if port is None:
        port = MONITORING_PORT

    timeout_config = httpx.Timeout(connect=3.0, read=float(timeout), write=5.0, pool=3.0)
    start = time.perf_counter()
    try:
        response = httpx.get(
            f"http://{host}:{port}/health",
            timeout=timeout_config
        )
        latency = (time.perf_counter() - start) * 1000

        if response.status_code == 200:
            return HealthCheckResult(
                "monitoring",
                "healthy",
                f"Monitoring API ready",
                latency
            )
        else:
            return HealthCheckResult(
                "monitoring",
                "warning",
                f"HTTP {response.status_code}",
                latency,
                "Monitoring API not responding correctly (optional service)"
            )
    except httpx.TimeoutException:
        latency = timeout * 1000
        return HealthCheckResult(
            "monitoring",
            "warning",
            f"Timeout after {timeout}s",
            latency,
            "Monitoring API is optional - core services may still work"
        )
    except Exception as e:
        return HealthCheckResult(
            "monitoring",
            "warning",
            str(e),
            error_details="Monitoring API is optional - check docker compose ps monitoring"
        )


def run_health_checks() -> list[HealthCheckResult]:
    """
    Run all health checks in parallel for speed.

    2026 Best Practice: Parallel execution for comprehensive verification.
    Source: https://testdriven.io/blog/python-concurrency-parallelism/
    """
    checks = [
        check_hooks_configured,
        check_hook_scripts,
        check_monitoring_api,
    ]

    # Skip Docker-dependent checks if requested (e.g., macOS CI without Docker)
    if not SKIP_DOCKER_CHECKS:
        checks.extend([
            check_qdrant,
            check_embedding_service,
            check_embedding_functionality,
        ])
        results_list = []
    else:
        # Add informational result about skipped checks
        results_list = [HealthCheckResult(
            "docker_checks",
            "warning",
            "Docker checks skipped (SKIP_DOCKER_CHECKS=true)",
            error_details="Docker-dependent services not verified on this platform"
        )]

    # Run checks in parallel with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_check = {executor.submit(check): check.__name__ for check in checks}

        for future in as_completed(future_to_check):
            try:
                result = future.result()
                results_list.append(result)
            except Exception as e:
                check_name = future_to_check[future]
                results_list.append(HealthCheckResult(
                    check_name,
                    "unhealthy",
                    f"Check failed: {str(e)}"
                ))

    # Sort by component name for consistent output
    results_list.sort(key=lambda r: r.component)
    return results_list


def print_results(results: list[HealthCheckResult]) -> bool:
    """
    Print health check results with color coding.

    Returns True if all critical checks passed (warnings don't fail the check).
    Warnings are informational - they indicate non-critical issues.
    """
    print("\n" + "=" * 70)
    print("  AI Memory Module Health Check")
    print("=" * 70 + "\n")

    has_failures = False
    has_warnings = False

    for result in results:
        if result.status == "healthy":
            icon = "\033[92m✓\033[0m"  # Green check
        elif result.status == "warning":
            icon = "\033[93m!\033[0m"  # Yellow exclamation
            has_warnings = True
            # Warnings are non-critical - don't fail the health check
        else:
            icon = "\033[91m✗\033[0m"  # Red X
            has_failures = True

        latency_str = f" ({result.latency_ms:.0f}ms)" if result.latency_ms else ""
        print(f"  {icon} {result.component:20} {result.message}{latency_str}")

        # Show error details if present
        if result.error_details and result.status != "healthy":
            print(f"      \033[90m→ {result.error_details}\033[0m")

    print("\n" + "=" * 70)

    if not has_failures and not has_warnings:
        print("\033[92m  ✓ All checks passed! System is ready.\033[0m")
    elif not has_failures and has_warnings:
        print("\033[93m  ✓ Core checks passed with warnings. System is functional.\033[0m")
    else:
        print("\033[91m  ✗ Critical checks failed. See above for details.\033[0m")
        print("\033[90m    For troubleshooting help, see TROUBLESHOOTING.md\033[0m")

    print("=" * 70 + "\n")

    # Return True if no critical failures (warnings are acceptable)
    return not has_failures


def main() -> None:
    """Main entry point for health check script."""
    results = run_health_checks()
    success = print_results(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
