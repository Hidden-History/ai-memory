"""
Unit tests for scripts/health-check.py

Tests health check functions with mocked HTTP requests.
Verifies timeout handling, parallel execution, and result formatting.

Updated per code review (2026-01-14):
- Fixed dimension mocks to use 768 (DEC-010) instead of 3584
- Added tests for monitoring API check
- Added tests for empty embeddings edge case
- Updated warning/failure logic tests
"""

import json
import os
import sys
from unittest.mock import MagicMock, Mock, patch

# Add scripts directory to path and import health-check module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# Import after path modification - use importlib for hyphenated module name
import importlib.util

spec = importlib.util.spec_from_file_location(
    "health_check",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "health-check.py"),
)
health_check = importlib.util.module_from_spec(spec)
sys.modules["health_check"] = health_check  # Add to sys.modules so @patch can find it
spec.loader.exec_module(health_check)

# Import symbols from the module
HealthCheckResult = health_check.HealthCheckResult
check_qdrant = health_check.check_qdrant
check_embedding_service = health_check.check_embedding_service
check_embedding_functionality = health_check.check_embedding_functionality
check_hooks_configured = health_check.check_hooks_configured
check_hook_scripts = health_check.check_hook_scripts
check_monitoring_api = health_check.check_monitoring_api
run_health_checks = health_check.run_health_checks
print_results = health_check.print_results
EXPECTED_EMBEDDING_DIMENSIONS = health_check.EXPECTED_EMBEDDING_DIMENSIONS


class TestHealthCheckResult:
    """Test HealthCheckResult dataclass."""

    def test_healthy_result(self):
        """Test creating a healthy result."""
        result = HealthCheckResult(
            component="test", status="healthy", message="All good", latency_ms=123.45
        )
        assert result.component == "test"
        assert result.status == "healthy"
        assert result.message == "All good"
        assert result.latency_ms == 123.45
        assert result.error_details is None

    def test_unhealthy_result_with_error_details(self):
        """Test creating an unhealthy result with error details."""
        result = HealthCheckResult(
            component="test",
            status="unhealthy",
            message="Service down",
            error_details="Check logs",
        )
        assert result.status == "unhealthy"
        assert result.error_details == "Check logs"


class TestCheckQdrant:
    """Test check_qdrant function."""

    @patch("health_check.httpx.get")
    def test_qdrant_healthy_with_collections(self, mock_get):
        """Test Qdrant is healthy and has required collections."""
        # Mock /healthz endpoint
        healthz_response = Mock()
        healthz_response.status_code = 200

        # Mock /collections endpoint
        collections_response = Mock()
        collections_response.status_code = 200
        collections_response.json.return_value = {
            "result": {
                "collections": [{"name": "code-patterns"}, {"name": "conventions"}]
            }
        }

        mock_get.side_effect = [healthz_response, collections_response]

        result = check_qdrant()

        assert result.component == "qdrant"
        assert result.status == "healthy"
        assert "2 total" in result.message
        assert result.latency_ms is not None
        assert result.latency_ms > 0

    @patch("health_check.httpx.get")
    def test_qdrant_missing_collections(self, mock_get):
        """Test Qdrant is running but missing collections."""
        # Mock /healthz endpoint
        healthz_response = Mock()
        healthz_response.status_code = 200

        # Mock /collections endpoint - missing required collections
        collections_response = Mock()
        collections_response.status_code = 200
        collections_response.json.return_value = {
            "result": {"collections": [{"name": "other_collection"}]}
        }

        mock_get.side_effect = [healthz_response, collections_response]

        result = check_qdrant()

        assert result.component == "qdrant"
        assert result.status == "warning"
        assert "Missing collections" in result.message
        assert "other_collection" in result.message
        assert result.error_details == "Run setup script to create collections"

    @patch("health_check.httpx.get")
    def test_qdrant_http_error(self, mock_get):
        """Test Qdrant returns HTTP error."""
        # Mock /healthz endpoint with error
        healthz_response = Mock()
        healthz_response.status_code = 503

        mock_get.return_value = healthz_response

        result = check_qdrant()

        assert result.component == "qdrant"
        assert result.status == "unhealthy"
        assert "503" in result.message

    @patch("health_check.httpx.get")
    def test_qdrant_timeout(self, mock_get):
        """Test Qdrant timeout handling."""
        import httpx

        mock_get.side_effect = httpx.TimeoutException("Connection timeout")

        result = check_qdrant(timeout=5)

        assert result.component == "qdrant"
        assert result.status == "unhealthy"
        assert "Timeout after 5s" in result.message
        assert result.latency_ms == 5000
        assert "starting or hung" in result.error_details

    @patch("health_check.httpx.get")
    def test_qdrant_connection_error(self, mock_get):
        """Test Qdrant connection refused."""
        mock_get.side_effect = Exception("Connection refused")

        result = check_qdrant()

        assert result.component == "qdrant"
        assert result.status == "unhealthy"
        assert "Connection refused" in result.message
        # Production returns generic troubleshooting message
        assert "Check if service is running" in result.error_details


class TestCheckEmbeddingService:
    """Test check_embedding_service function."""

    @patch("health_check.httpx.get")
    def test_embedding_healthy_model_loaded(self, mock_get):
        """Test embedding service healthy with model loaded."""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "model_loaded": True,
            "model_name": "jina-embeddings-v2-base-en",
        }
        mock_get.return_value = response

        result = check_embedding_service()

        assert result.component == "embedding"
        assert result.status == "healthy"
        assert "jina-embeddings-v2-base-en" in result.message
        assert result.latency_ms is not None

    @patch("health_check.httpx.get")
    def test_embedding_warning_model_not_loaded(self, mock_get):
        """Test embedding service running but model not loaded."""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"model_loaded": False}
        mock_get.return_value = response

        result = check_embedding_service()

        assert result.component == "embedding"
        assert result.status == "warning"
        assert "model not loaded" in result.message
        assert "10-30s" in result.error_details

    @patch("health_check.httpx.get")
    def test_embedding_timeout(self, mock_get):
        """Test embedding service timeout."""
        import httpx

        mock_get.side_effect = httpx.TimeoutException("Timeout")

        result = check_embedding_service(timeout=10)

        assert result.component == "embedding"
        assert result.status == "unhealthy"
        assert "Timeout after 10s" in result.message
        assert result.latency_ms == 10000


class TestCheckEmbeddingFunctionality:
    """Test check_embedding_functionality function."""

    @patch("health_check.httpx.post")
    def test_embedding_test_successful(self, mock_post):
        """Test embedding generation successful with correct dimensions (DEC-010: 768)."""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "embeddings": [
                [0.1] * EXPECTED_EMBEDDING_DIMENSIONS
            ]  # DEC-010: 768 dimensions
        }
        mock_post.return_value = response

        result = check_embedding_functionality()

        assert result.component == "embedding_test"
        assert result.status == "healthy"
        assert (
            f"{EXPECTED_EMBEDDING_DIMENSIONS}d embeddings generated" in result.message
        )
        assert result.latency_ms is not None

    @patch("health_check.httpx.post")
    def test_embedding_test_wrong_dimensions(self, mock_post):
        """Test embedding generation returns wrong dimensions."""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "embeddings": [[0.1] * 1024]  # Wrong dimensions (not 768)
        }
        mock_post.return_value = response

        result = check_embedding_functionality()

        assert result.component == "embedding_test"
        assert result.status == "unhealthy"
        assert "Unexpected dimensions: 1024" in result.message
        assert f"expected {EXPECTED_EMBEDDING_DIMENSIONS}" in result.message

    @patch("health_check.httpx.post")
    def test_embedding_test_empty_array(self, mock_post):
        """Test embedding generation returns empty array."""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"embeddings": []}  # Empty array
        mock_post.return_value = response

        result = check_embedding_functionality()

        assert result.component == "embedding_test"
        assert result.status == "unhealthy"
        assert "Empty embeddings returned" in result.message

    @patch("health_check.httpx.post")
    def test_embedding_test_empty_vector(self, mock_post):
        """Test embedding generation returns array with empty vector."""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"embeddings": [[]]}  # Array with empty vector
        mock_post.return_value = response

        result = check_embedding_functionality()

        assert result.component == "embedding_test"
        assert result.status == "unhealthy"
        assert "Empty embeddings returned" in result.message

    @patch("health_check.httpx.post")
    def test_embedding_test_timeout(self, mock_post):
        """Test embedding generation timeout."""
        import httpx

        mock_post.side_effect = httpx.TimeoutException("Timeout")

        result = check_embedding_functionality(timeout=30)

        assert result.component == "embedding_test"
        assert result.status == "unhealthy"
        assert "Timeout after 30s" in result.message
        assert result.latency_ms == 30000

    @patch("health_check.httpx.post")
    def test_embedding_test_http_error(self, mock_post):
        """Test embedding generation HTTP error."""
        response = Mock()
        response.status_code = 500
        mock_post.return_value = response

        result = check_embedding_functionality()

        assert result.component == "embedding_test"
        assert result.status == "unhealthy"
        assert "HTTP 500" in result.message


class TestCheckHooksConfigured:
    """Test check_hooks_configured function."""

    @patch("builtins.open")
    @patch("os.path.expanduser")
    def test_hooks_all_configured(self, mock_expanduser, mock_open):
        """Test all hooks are configured."""
        mock_expanduser.return_value = "/home/user/.claude/settings.json"

        settings_data = {
            "hooks": {
                "SessionStart": [{"type": "command", "command": "start.py"}],
                "PostToolUse": [{"type": "command", "command": "post.py"}],
                "Stop": [{"type": "command", "command": "stop.py"}],
            }
        }

        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = json.dumps(settings_data)
        mock_open.return_value = mock_file

        # Mock json.load to return our settings
        with patch("json.load", return_value=settings_data):
            result = check_hooks_configured()

        assert result.component == "hooks"
        assert result.status == "healthy"
        assert "All 3 hooks configured" in result.message

    @patch("builtins.open")
    @patch("os.path.expanduser")
    def test_hooks_missing(self, mock_expanduser, mock_open):
        """Test some hooks are missing - now returns healthy (graceful handling)."""
        mock_expanduser.return_value = "/home/user/.claude/settings.json"

        settings_data = {
            "hooks": {
                "SessionStart": [{"type": "command"}]
                # Missing PostToolUse and Stop
            }
        }

        with patch("json.load", return_value=settings_data):
            result = check_hooks_configured()

        assert result.component == "hooks"
        # Production now returns healthy with message about hooks being in target project
        assert result.status == "healthy"
        assert "Hooks configured in target project" in result.message

    @patch("os.path.expanduser")
    def test_hooks_file_not_found(self, mock_expanduser):
        """Test settings.json not found - now returns healthy (graceful handling)."""
        mock_expanduser.return_value = "/home/user/.claude/settings.json"

        with patch("builtins.open", side_effect=FileNotFoundError):
            result = check_hooks_configured()

        assert result.component == "hooks"
        # Production now returns healthy - hooks are in installed project, not health check dir
        assert result.status == "healthy"
        assert "Hooks configured in target project" in result.message

    @patch("builtins.open")
    @patch("os.path.expanduser")
    def test_hooks_invalid_json(self, mock_expanduser, mock_open):
        """Test settings.json has invalid JSON - now returns healthy (graceful handling)."""
        mock_expanduser.return_value = "/home/user/.claude/settings.json"

        with patch("json.load", side_effect=json.JSONDecodeError("", "", 0)):
            result = check_hooks_configured()

        assert result.component == "hooks"
        # Production now returns healthy - hooks are in installed project, not health check dir
        assert result.status == "healthy"
        assert "Hooks configured in target project" in result.message


class TestCheckHookScripts:
    """Test check_hook_scripts function."""

    @patch("os.path.exists")
    @patch("os.access")
    @patch.dict(os.environ, {"AI_MEMORY_INSTALL_DIR": "/test/install"})
    def test_all_scripts_present_and_executable(self, mock_access, mock_exists):
        """Test all hook scripts exist and are executable."""
        mock_exists.return_value = True
        mock_access.return_value = True

        result = check_hook_scripts()

        assert result.component == "hook_scripts"
        assert result.status == "healthy"
        # Production now only requires 2 scripts (session_stop.py deprecated per BUG-041)
        assert "All 2 scripts present and executable" in result.message

    @patch("os.path.exists")
    @patch.dict(os.environ, {"AI_MEMORY_INSTALL_DIR": "/test/install"})
    def test_scripts_missing(self, mock_exists):
        """Test some scripts are missing."""
        # First script missing, second present (only 2 required scripts now)
        mock_exists.side_effect = [False, True]

        result = check_hook_scripts()

        assert result.component == "hook_scripts"
        assert result.status == "unhealthy"
        assert "Missing scripts" in result.message
        assert "session_start.py" in result.message

    @patch("os.path.exists")
    @patch("os.access")
    @patch.dict(os.environ, {"AI_MEMORY_INSTALL_DIR": "/test/install"})
    def test_scripts_not_executable(self, mock_access, mock_exists):
        """Test scripts exist but are not executable."""
        mock_exists.return_value = True
        # First script not executable, second executable (only 2 required scripts now)
        mock_access.side_effect = [False, True]

        result = check_hook_scripts()

        assert result.component == "hook_scripts"
        assert result.status == "warning"
        assert "Not executable" in result.message
        assert "chmod +x" in result.error_details


class TestCheckMonitoringApi:
    """Test check_monitoring_api function."""

    @patch("health_check.httpx.get")
    def test_monitoring_healthy(self, mock_get):
        """Test monitoring API is healthy."""
        response = Mock()
        response.status_code = 200
        mock_get.return_value = response

        result = check_monitoring_api()

        assert result.component == "monitoring"
        assert result.status == "healthy"
        assert "Monitoring API ready" in result.message
        assert result.latency_ms is not None

    @patch("health_check.httpx.get")
    def test_monitoring_http_error(self, mock_get):
        """Test monitoring API returns HTTP error."""
        response = Mock()
        response.status_code = 503
        mock_get.return_value = response

        result = check_monitoring_api()

        assert result.component == "monitoring"
        assert result.status == "warning"  # Optional service - warning not failure
        assert "503" in result.message

    @patch("health_check.httpx.get")
    def test_monitoring_timeout(self, mock_get):
        """Test monitoring API timeout (warning, not failure)."""
        import httpx

        mock_get.side_effect = httpx.TimeoutException("Timeout")

        result = check_monitoring_api(timeout=5)

        assert result.component == "monitoring"
        assert result.status == "warning"  # Optional - warning not unhealthy
        assert "Timeout after 5s" in result.message
        assert "optional" in result.error_details.lower()

    @patch("health_check.httpx.get")
    def test_monitoring_connection_refused(self, mock_get):
        """Test monitoring API connection refused (warning)."""
        mock_get.side_effect = Exception("Connection refused")

        result = check_monitoring_api()

        assert result.component == "monitoring"
        assert result.status == "warning"
        assert "Connection refused" in result.message


class TestRunHealthChecks:
    """Test run_health_checks parallel execution."""

    @patch("health_check.check_venv_health")
    @patch("health_check.check_monitoring_api")
    @patch("health_check.check_hook_scripts")
    @patch("health_check.check_hooks_configured")
    @patch("health_check.check_embedding_functionality")
    @patch("health_check.check_embedding_service")
    @patch("health_check.check_qdrant")
    def test_parallel_execution(
        self,
        mock_qdrant,
        mock_embedding,
        mock_embed_test,
        mock_hooks,
        mock_scripts,
        mock_monitoring,
        mock_venv,
    ):
        """Test all checks run in parallel."""
        # Mock each check to return unique results and add __name__ attribute
        mock_qdrant.return_value = HealthCheckResult("qdrant", "healthy", "OK")
        mock_qdrant.__name__ = "check_qdrant"

        mock_embedding.return_value = HealthCheckResult("embedding", "healthy", "OK")
        mock_embedding.__name__ = "check_embedding_service"

        mock_embed_test.return_value = HealthCheckResult(
            "embedding_test", "healthy", "OK"
        )
        mock_embed_test.__name__ = "check_embedding_functionality"

        mock_hooks.return_value = HealthCheckResult("hooks", "healthy", "OK")
        mock_hooks.__name__ = "check_hooks_configured"

        mock_scripts.return_value = HealthCheckResult("hook_scripts", "healthy", "OK")
        mock_scripts.__name__ = "check_hook_scripts"

        mock_monitoring.return_value = HealthCheckResult("monitoring", "healthy", "OK")
        mock_monitoring.__name__ = "check_monitoring_api"

        mock_venv.return_value = HealthCheckResult("venv", "healthy", "OK")
        mock_venv.__name__ = "check_venv_health"

        results = run_health_checks()

        # All checks should be called
        assert mock_qdrant.called
        assert mock_embedding.called
        assert mock_embed_test.called
        assert mock_hooks.called
        assert mock_scripts.called
        assert mock_monitoring.called
        assert mock_venv.called

        # Should return 7 results (including monitoring and venv)
        assert len(results) == 7

        # Results should be sorted by component name
        components = [r.component for r in results]
        assert components == sorted(components)

    @patch("health_check.check_qdrant")
    def test_exception_handling(self, mock_qdrant):
        """Test exception handling in parallel execution."""
        # Make one check raise an exception and add __name__
        mock_qdrant.side_effect = Exception("Unexpected error")
        mock_qdrant.__name__ = "check_qdrant"

        with (
            patch("health_check.check_embedding_service") as mock_embed,
            patch("health_check.check_embedding_functionality") as mock_test,
            patch("health_check.check_hooks_configured") as mock_hooks,
            patch("health_check.check_hook_scripts") as mock_scripts,
            patch("health_check.check_monitoring_api") as mock_monitoring,
            patch("health_check.check_venv_health") as mock_venv,
        ):

            mock_embed.return_value = HealthCheckResult("embedding", "healthy", "OK")
            mock_embed.__name__ = "check_embedding_service"

            mock_test.return_value = HealthCheckResult(
                "embedding_test", "healthy", "OK"
            )
            mock_test.__name__ = "check_embedding_functionality"

            mock_hooks.return_value = HealthCheckResult("hooks", "healthy", "OK")
            mock_hooks.__name__ = "check_hooks_configured"

            mock_scripts.return_value = HealthCheckResult(
                "hook_scripts", "healthy", "OK"
            )
            mock_scripts.__name__ = "check_hook_scripts"

            mock_monitoring.return_value = HealthCheckResult(
                "monitoring", "healthy", "OK"
            )
            mock_monitoring.__name__ = "check_monitoring_api"

            mock_venv.return_value = HealthCheckResult("venv", "healthy", "OK")
            mock_venv.__name__ = "check_venv_health"

            results = run_health_checks()

            # Should still get results for all checks (7 including monitoring and venv)
            assert len(results) == 7

            # The failed check should have status unhealthy
            qdrant_result = next(r for r in results if r.component == "check_qdrant")
            assert qdrant_result.status == "unhealthy"


class TestPrintResults:
    """Test print_results function."""

    def test_all_healthy(self, capsys):
        """Test printing all healthy results."""
        results = [
            HealthCheckResult("qdrant", "healthy", "OK", 45.0),
            HealthCheckResult("embedding", "healthy", "OK", 12.0),
        ]

        success = print_results(results)

        assert success is True

        captured = capsys.readouterr()
        assert "All checks passed" in captured.out
        assert "qdrant" in captured.out
        assert "embedding" in captured.out

    def test_with_warnings_only(self, capsys):
        """Test printing results with warnings only - warnings don't fail health check."""
        results = [
            HealthCheckResult("qdrant", "healthy", "OK"),
            HealthCheckResult(
                "monitoring", "warning", "Timeout", error_details="Optional service"
            ),
        ]

        success = print_results(results)

        # Warnings don't fail the health check - only unhealthy status does
        assert success is True

        captured = capsys.readouterr()
        assert "Core checks passed with warnings" in captured.out
        assert "Optional service" in captured.out

    def test_with_warnings_and_failures(self, capsys):
        """Test printing results with both warnings and failures."""
        results = [
            HealthCheckResult("qdrant", "unhealthy", "Connection refused"),
            HealthCheckResult("monitoring", "warning", "Timeout"),
        ]

        success = print_results(results)

        assert success is False

        captured = capsys.readouterr()
        assert "Critical checks failed" in captured.out

    def test_with_failures(self, capsys):
        """Test printing results with failures."""
        results = [
            HealthCheckResult(
                "qdrant",
                "unhealthy",
                "Connection refused",
                error_details="Check if service is running",
            )
        ]

        success = print_results(results)

        assert success is False

        captured = capsys.readouterr()
        assert "Critical checks failed" in captured.out
        assert "Connection refused" in captured.out
        assert "Check if service is running" in captured.out


class TestMain:
    """Test main function."""

    @patch("health_check.run_health_checks")
    @patch("health_check.print_results")
    @patch("sys.exit")
    def test_main_success(self, mock_exit, mock_print, mock_run):
        """Test main function with successful health checks."""
        mock_run.return_value = [HealthCheckResult("test", "healthy", "OK")]
        mock_print.return_value = True

        health_check.main()

        mock_exit.assert_called_once_with(0)

    @patch("health_check.run_health_checks")
    @patch("health_check.print_results")
    @patch("sys.exit")
    def test_main_failure(self, mock_exit, mock_print, mock_run):
        """Test main function with failed health checks."""
        mock_run.return_value = [HealthCheckResult("test", "unhealthy", "Failed")]
        mock_print.return_value = False

        health_check.main()

        mock_exit.assert_called_once_with(1)
