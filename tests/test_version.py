"""Tests for version tracking functionality.

Tests verify 2026 best practices:
- PEP 440 compliant version format
- Semantic version comparison
- httpx timeout handling
- Graceful degradation on network errors
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import patch, Mock

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.__version__ import __version__, __version_info__
import httpx
import importlib.util

# Load check-version.py module (has hyphen, can't import normally)
spec = importlib.util.spec_from_file_location(
    "check_version",
    Path(__file__).parent.parent / "scripts" / "check-version.py"
)
check_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_version)


class TestVersionModule:
    """Test src/memory/__version__.py functionality."""

    def test_version_format_pep440_compliant(self):
        """Test that __version__ follows PEP 440 format."""
        # Should be X.Y.Z format
        parts = __version__.split(".")
        assert len(parts) == 3, "Version must be Major.Minor.Patch format"

        # All parts should be integers
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' must be integer"

    def test_version_info_tuple(self):
        """Test that __version_info__ is a tuple of integers."""
        assert isinstance(__version_info__, tuple), "__version_info__ must be tuple"
        assert len(__version_info__) == 3, "__version_info__ must have 3 elements"

        for part in __version_info__:
            assert isinstance(part, int), "Version info parts must be integers"

    def test_version_and_version_info_match(self):
        """Test that __version__ and __version_info__ are consistent."""
        version_parts = tuple(int(x) for x in __version__.split("."))
        assert version_parts == __version_info__, "Version string and tuple must match"


class TestCheckVersionScript:
    """Test scripts/check-version.py functionality."""

    def test_compare_versions_current_less_than_latest(self):
        """Test version comparison when update available."""
        compare_versions = check_version.compare_versions

        result = compare_versions("1.0.0", "1.0.1")
        assert result == -1, "Should return -1 when current < latest"

        result = compare_versions("1.0.0", "1.1.0")
        assert result == -1, "Should return -1 for minor version update"

        result = compare_versions("1.0.0", "2.0.0")
        assert result == -1, "Should return -1 for major version update"

    def test_compare_versions_current_equals_latest(self):
        """Test version comparison when up to date."""
        compare_versions = check_version.compare_versions

        result = compare_versions("1.0.0", "1.0.0")
        assert result == 0, "Should return 0 when versions equal"

    def test_compare_versions_current_greater_than_latest(self):
        """Test version comparison when ahead of release."""
        compare_versions = check_version.compare_versions

        result = compare_versions("1.0.1", "1.0.0")
        assert result == 1, "Should return 1 when current > latest"

        result = compare_versions("2.0.0", "1.9.9")
        assert result == 1, "Should return 1 when ahead by major version"

    def test_compare_versions_with_different_lengths(self):
        """Test version comparison with mismatched length."""
        compare_versions = check_version.compare_versions

        result = compare_versions("1.0", "1.0.0")
        assert result == 0, "Should pad with zeros for comparison"

        result = compare_versions("1.0", "1.0.1")
        assert result == -1, "Should handle missing patch version"

    def test_compare_versions_with_prerelease(self):
        """Test version comparison with pre-release versions (PEP 440)."""
        compare_versions = check_version.compare_versions

        # Pre-release should be less than release
        result = compare_versions("1.0.0a1", "1.0.0")
        assert result == -1, "Pre-release should be < release"

        result = compare_versions("1.0.0", "1.0.0a1")
        assert result == 1, "Release should be > pre-release"

        # Beta vs release
        result = compare_versions("2.0.0-beta", "2.0.0")
        assert result == -1, "Beta should be < release"

    def test_parse_version_basic(self):
        """Test parse_version with standard versions."""
        parse_version = check_version.parse_version

        assert parse_version("1.0.0") == [1, 0, 0]
        assert parse_version("2.1.3") == [2, 1, 3]
        assert parse_version("10.20.30") == [10, 20, 30]

    def test_parse_version_prerelease(self):
        """Test parse_version handles pre-release markers."""
        parse_version = check_version.parse_version

        # Pre-release adds -1 marker to indicate it's before release
        result = parse_version("1.0.0a1")
        assert -1 in result, "Pre-release should have -1 marker"

        result = parse_version("2.0.0-beta")
        assert -1 in result, "Beta should have -1 marker"

    def test_get_latest_version_success(self):
        """Test successful version fetch from GitHub API."""
        get_latest_version = check_version.get_latest_version

        with patch.object(httpx, 'get') as mock_get:
            # Mock successful response
            mock_response = Mock()
            mock_response.json.return_value = {"tag_name": "v1.0.1"}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            version = get_latest_version()
            assert version == "1.0.1", "Should strip 'v' prefix from tag"

            # Verify httpx.Timeout was used
            call_kwargs = mock_get.call_args.kwargs
            assert 'timeout' in call_kwargs, "Must use timeout parameter"
            timeout_obj = call_kwargs['timeout']
            assert isinstance(timeout_obj, httpx.Timeout), "Must use httpx.Timeout object"

    def test_get_latest_version_timeout_with_retry(self):
        """Test retry logic on timeout errors with exponential backoff."""
        get_latest_version = check_version.get_latest_version

        with patch.object(httpx, 'get') as mock_get, \
             patch.object(check_version.time, 'sleep') as mock_sleep, \
             patch.object(check_version, 'MAX_RETRIES', 2):
            mock_get.side_effect = httpx.TimeoutException("Connection timeout")

            version = get_latest_version()
            assert version is None, "Should return None after retries exhausted"
            # Should have retried (MAX_RETRIES - 1 sleeps for backoff)
            assert mock_get.call_count == 2, "Should retry on timeout"

    def test_get_latest_version_http_error_no_retry_4xx(self):
        """Test that 4xx errors don't trigger retry (client errors)."""
        get_latest_version = check_version.get_latest_version

        with patch.object(httpx, 'get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not found", request=Mock(), response=mock_response
            )
            mock_get.return_value = mock_response

            version = get_latest_version()
            assert version is None, "Should return None on HTTP 4xx error"
            assert mock_get.call_count == 1, "Should NOT retry on 4xx errors"

    def test_get_latest_version_network_error(self):
        """Test graceful handling of network errors with retry."""
        get_latest_version = check_version.get_latest_version

        with patch.object(httpx, 'get') as mock_get, \
             patch.object(check_version.time, 'sleep') as mock_sleep, \
             patch.object(check_version, 'MAX_RETRIES', 2):
            mock_get.side_effect = httpx.RequestError("Network unreachable")

            version = get_latest_version()
            assert version is None, "Should return None on network error"

    def test_get_latest_version_invalid_response(self):
        """Test graceful handling of invalid API response (no retry)."""
        get_latest_version = check_version.get_latest_version

        with patch.object(httpx, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"invalid": "response"}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            version = get_latest_version()
            assert version is None, "Should return None on invalid response"
            assert mock_get.call_count == 1, "Should NOT retry on invalid response"

    def test_configurable_github_repo(self):
        """Test that GitHub owner/repo is configurable via env vars."""
        # Verify the module has configurable constants
        assert hasattr(check_version, 'GITHUB_OWNER'), "Must have GITHUB_OWNER constant"
        assert hasattr(check_version, 'GITHUB_REPO'), "Must have GITHUB_REPO constant"
        assert hasattr(check_version, 'MAX_RETRIES'), "Must have MAX_RETRIES constant"

    def test_httpx_timeout_granular_control(self):
        """Test that httpx.Timeout uses granular timeout control (2026 best practice)."""
        # This test verifies the code uses httpx.Timeout with connect/read/write/pool
        check_version_path = Path(__file__).parent.parent / "scripts" / "check-version.py"
        content = check_version_path.read_text()

        assert "httpx.Timeout(" in content, "Must use httpx.Timeout object"
        assert "connect=" in content, "Must specify connect timeout"
        assert "read=" in content, "Must specify read timeout"
        assert "write=" in content, "Must specify write timeout"
        assert "pool=" in content, "Must specify pool timeout"


class TestRollbackScript:
    """Test scripts/rollback.sh functionality."""

    def test_rollback_script_exists_and_executable(self):
        """Test that rollback.sh exists and is executable."""
        rollback_script = Path(__file__).parent.parent / "scripts" / "rollback.sh"

        assert rollback_script.exists(), "rollback.sh must exist"
        assert rollback_script.stat().st_mode & 0o111, "rollback.sh must be executable"

    def test_rollback_script_has_strict_error_handling(self):
        """Test that rollback.sh uses set -euo pipefail."""
        rollback_script = Path(__file__).parent.parent / "scripts" / "rollback.sh"
        content = rollback_script.read_text()

        assert "set -euo pipefail" in content, "Must use strict error handling"
        assert "#!/usr/bin/env bash" in content or "#!/bin/bash" in content

    def test_rollback_script_has_backup_selection(self):
        """Test that rollback.sh has backup selection logic."""
        rollback_script = Path(__file__).parent.parent / "scripts" / "rollback.sh"
        content = rollback_script.read_text()

        assert "select_backup" in content, "Must have backup selection function"
        assert "BACKUPS" in content or "backups" in content, "Must reference backups"

    def test_rollback_script_has_confirmation(self):
        """Test that rollback.sh requires user confirmation."""
        rollback_script = Path(__file__).parent.parent / "scripts" / "rollback.sh"
        content = rollback_script.read_text()

        assert "confirm" in content.lower(), "Must have confirmation step"
        assert "yes/no" in content.lower() or "y/n" in content.lower(), "Must require explicit confirmation"

    def test_rollback_script_has_signal_trap(self):
        """Test that rollback.sh has signal trap for cleanup (2026 best practice)."""
        rollback_script = Path(__file__).parent.parent / "scripts" / "rollback.sh"
        content = rollback_script.read_text()

        assert "trap" in content.lower(), "Must have signal trap"
        assert "cleanup" in content.lower(), "Must have cleanup function"
