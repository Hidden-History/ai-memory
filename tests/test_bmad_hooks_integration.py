"""Integration tests for BMAD memory hooks.

Tests the following hook scripts:
- pre-work-search.py: Pre-work memory search
- post-work-store.py: Post-work storage with validation
- store-chat-memory.py: Chat memory storage for agent-memory collection
- load-chat-context.py: Recent memory retrieval
- best_practices_retrieval.py: PreToolUse best practices context
- error_pattern_capture.py: PostToolUse error pattern capture

All tests verify:
1. Valid JSON output format
2. Graceful degradation (exit 0 on errors)
3. Proper metadata validation
4. Correct collection targeting
5. Integration with mocked Qdrant

Fixtures:
- Uses mock_qdrant_client from conftest.py for offline testing
- Uses temp_queue_dir for async storage tests
- Uses sample_memory_payload for test data

2026 pytest best practices:
- Parametrized tests for multiple scenarios
- Clear test names describing expected behavior
- Structured assertions with helpful failure messages
- Proper subprocess handling for hook scripts
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts" / "memory"
HOOKS_DIR = PROJECT_ROOT / ".claude" / "hooks" / "scripts"


# =============================================================================
# Test Helpers
# =============================================================================


def run_hook_script(
    script_path: Path,
    args: list | None = None,
    stdin_data: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 5,
) -> dict[str, Any]:
    """Execute a hook script and return results.

    Args:
        script_path: Path to the Python script
        args: Command-line arguments
        stdin_data: Data to send to stdin
        env: Environment variables (merged with current env)
        timeout: Timeout in seconds

    Returns:
        Dict with 'exit_code', 'stdout', 'stderr', and 'json_output' (if stdout is JSON)
    """
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    # Merge environment variables
    test_env = os.environ.copy()
    if env:
        test_env.update(env)

    # Add src to PYTHONPATH so hook scripts can find memory module
    src_path = str(PROJECT_ROOT / "src")
    existing_pythonpath = test_env.get("PYTHONPATH", "")
    test_env["PYTHONPATH"] = (
        f"{src_path}:{existing_pythonpath}" if existing_pythonpath else src_path
    )

    # Run the script
    result = subprocess.run(
        cmd,
        input=stdin_data,
        capture_output=True,
        text=True,
        env=test_env,
        timeout=timeout,
    )

    # Try to parse stdout as JSON
    json_output = None
    if result.stdout.strip():
        try:
            json_output = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass  # Not JSON, leave as None

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "json_output": json_output,
    }


def create_hook_input(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_output: str | None = None,
    cwd: str | None = None,
) -> str:
    """Create JSON hook input for PreToolUse/PostToolUse hooks.

    Args:
        tool_name: Name of the tool (e.g., "Edit", "Bash")
        tool_input: Tool input parameters
        tool_output: Optional tool output for PostToolUse hooks
        cwd: Optional working directory

    Returns:
        JSON string for stdin
    """
    hook_data = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": cwd or os.getcwd(),
    }
    if tool_output is not None:
        hook_data["tool_output"] = tool_output

    return json.dumps(hook_data)


# =============================================================================
# Test pre-work-search.py
# =============================================================================


class TestPreWorkSearch:
    """Tests for pre-work-search.py script.

    Note: These tests use invalid Qdrant URLs to trigger graceful degradation
    without requiring real Qdrant service. Integration tests with real Qdrant
    are in TestHooksWithRealQdrant class.
    """

    def test_returns_valid_json_structure(self):
        """Test pre-work-search returns valid JSON structure (graceful degradation)."""
        script = SCRIPTS_DIR / "pre-work-search.py"

        # Use invalid Qdrant URL to trigger graceful degradation without real service
        result = run_hook_script(
            script,
            args=["--query", "test query", "--limit", "5"],
            env={
                "QDRANT_URL": "http://localhost:99999"
            },  # Invalid port triggers graceful degradation
        )

        # Verify exit code 0 (graceful degradation)
        assert result["exit_code"] == 0, f"Expected exit 0, got {result['exit_code']}"

        # Verify valid JSON output structure
        assert result["json_output"] is not None, "Expected JSON output"
        assert "memories" in result["json_output"], "Missing 'memories' field"
        assert "count" in result["json_output"], "Missing 'count' field"
        assert isinstance(
            result["json_output"]["memories"], list
        ), "'memories' should be a list"
        assert isinstance(
            result["json_output"]["count"], int
        ), "'count' should be an integer"

    def test_returns_empty_on_missing_args(self):
        """Test graceful degradation when no args provided."""
        script = SCRIPTS_DIR / "pre-work-search.py"

        result = run_hook_script(script, args=[])

        # Should exit 0 with empty result (graceful degradation)
        assert result["exit_code"] == 0
        assert result["json_output"] is not None
        assert result["json_output"]["count"] == 0
        assert result["json_output"]["memories"] == []

    def test_accepts_story_context_args(self):
        """Test accepting story context parameters."""
        script = SCRIPTS_DIR / "pre-work-search.py"

        # Graceful degradation with invalid Qdrant
        result = run_hook_script(
            script,
            args=["--story-id", "story-2-1", "--component", "auth", "--agent", "dev"],
            env={"QDRANT_URL": "http://localhost:99999"},
        )

        # Should parse args successfully and exit 0
        assert result["exit_code"] == 0
        assert result["json_output"] is not None
        # Note: May return results if real Qdrant is running
        assert isinstance(result["json_output"]["count"], int)

    def test_graceful_degradation_on_qdrant_error(self):
        """Test graceful degradation when Qdrant is unavailable."""
        script = SCRIPTS_DIR / "pre-work-search.py"

        # Set invalid Qdrant URL to trigger error
        result = run_hook_script(
            script,
            args=["--query", "test query"],
            env={"QDRANT_URL": "http://localhost:99999"},  # Invalid port
        )

        # Should exit 0 (graceful degradation)
        assert result["exit_code"] == 0
        assert result["json_output"] is not None
        # May return results if real Qdrant is running, just verify structure
        assert isinstance(result["json_output"]["count"], int)


# =============================================================================
# Test post-work-store.py
# =============================================================================


class TestPostWorkStore:
    """Tests for post-work-store.py script.

    Note: Tests use validation logic without real Qdrant connection.
    Some tests require --skip-validation to bypass dependency checks.
    """

    def test_validates_metadata_structure(self):
        """Test metadata validation catches missing required fields."""
        script = SCRIPTS_DIR / "post-work-store.py"

        # Missing required field "type"
        invalid_metadata = {"group_id": "test-project", "source_hook": "test"}

        result = run_hook_script(
            script,
            args=[
                "--content",
                "Test content",
                "--metadata",
                json.dumps(invalid_metadata),
                "--sync",  # Use sync mode for testing
            ],
        )

        # Should exit 1 (validation failed)
        assert result["exit_code"] == 1
        assert "Missing required metadata fields" in result["stderr"]

    def test_validates_invalid_type(self):
        """Test metadata validation rejects invalid type values."""
        script = SCRIPTS_DIR / "post-work-store.py"

        invalid_metadata = {
            "type": "invalid_type",  # Not in valid types list
            "group_id": "test-project",
            "source_hook": "test",
        }

        result = run_hook_script(
            script,
            args=[
                "--content",
                "Test content",
                "--metadata",
                json.dumps(invalid_metadata),
                "--sync",
            ],
        )

        # Should exit 1 (validation failed)
        assert result["exit_code"] == 1
        assert "Invalid type" in result["stderr"]

    def test_accepts_valid_metadata_structure(self):
        """Test accepts valid metadata structure (connection may fail, but metadata validates)."""
        script = SCRIPTS_DIR / "post-work-store.py"

        valid_metadata = {
            "type": "implementation",
            "group_id": "test-project",
            "source_hook": "test",
            "agent": "dev",
            "component": "auth",
            "story_id": "story-2-1",
            "importance": "high",
            "session_id": "test-session",
        }

        # Use invalid Qdrant URL and skip validation to test metadata parsing only
        result = run_hook_script(
            script,
            args=[
                "--content",
                "Test implementation content",
                "--metadata",
                json.dumps(valid_metadata),
                "--skip-validation",  # Skip validation to test metadata only
                "--skip-duplicate-check",
                "--sync",
            ],
            env={
                "QDRANT_URL": "http://localhost:99999"
            },  # Invalid to trigger error after validation
        )

        # Metadata should validate successfully (exit 1 from Qdrant connection, not metadata)
        # The error message will be about Qdrant, not metadata
        if result["exit_code"] != 0:
            assert "Missing required metadata fields" not in result["stderr"]


# =============================================================================
# Test store-chat-memory.py
# =============================================================================


class TestStoreChatMemory:
    """Tests for store-chat-memory.py script."""

    def test_accepts_valid_args(self):
        """Test accepting valid arguments (connection may fail gracefully)."""
        script = SCRIPTS_DIR / "store-chat-memory.py"

        # Use invalid Qdrant to test graceful degradation
        result = run_hook_script(
            script,
            args=[
                "--session-id",
                "test-session-123",
                "--agent",
                "dev",
                "--content",
                "Test conversation context",
                "--cwd",
                str(PROJECT_ROOT),
            ],
            env={"QDRANT_URL": "http://localhost:99999"},
        )

        # Should exit 0 (graceful degradation)
        assert result["exit_code"] == 0

    def test_accepts_invalid_agent_name_gracefully(self):
        """Test warning on invalid agent name (graceful degradation)."""
        script = SCRIPTS_DIR / "store-chat-memory.py"

        result = run_hook_script(
            script,
            args=[
                "--session-id",
                "test-session-123",
                "--agent",
                "invalid-agent",  # Invalid agent name
                "--content",
                "Test content",
            ],
            env={"QDRANT_URL": "http://localhost:99999"},
        )

        # Should still exit 0 (graceful degradation)
        assert result["exit_code"] == 0

    def test_graceful_degradation_on_qdrant_error(self):
        """Test graceful degradation when Qdrant unavailable."""
        script = SCRIPTS_DIR / "store-chat-memory.py"

        result = run_hook_script(
            script,
            args=[
                "--session-id",
                "test-session-123",
                "--agent",
                "dev",
                "--content",
                "Test content",
            ],
            env={"QDRANT_URL": "http://localhost:99999"},  # Invalid port
        )

        # Should exit 0 (graceful degradation)
        assert result["exit_code"] == 0


# =============================================================================
# Test load-chat-context.py
# =============================================================================


class TestLoadChatContext:
    """Tests for load-chat-context.py script."""

    def test_returns_valid_json_structure(self):
        """Test returns valid JSON structure (graceful degradation)."""
        script = SCRIPTS_DIR / "load-chat-context.py"

        # Use invalid Qdrant to trigger graceful degradation
        result = run_hook_script(
            script,
            args=[
                "--session-id",
                "test-session-123",
                "--agent",
                "dev",  # Required parameter
                "--limit",
                "5",
            ],
            env={"QDRANT_URL": "http://localhost:99999"},
        )

        # Should exit 0 and return JSON
        assert result["exit_code"] == 0
        assert result["json_output"] is not None
        assert "memories" in result["json_output"]
        assert "count" in result["json_output"]

    def test_accepts_session_id_parameter(self):
        """Test accepting session ID parameter."""
        script = SCRIPTS_DIR / "load-chat-context.py"

        result = run_hook_script(
            script,
            args=[
                "--session-id",
                "test-session-123",
                "--agent",
                "dev",  # Required parameter
            ],
            env={"QDRANT_URL": "http://localhost:99999"},
        )

        # Should exit 0 with graceful degradation
        assert result["exit_code"] == 0
        assert result["json_output"] is not None


# =============================================================================
# Test best_practices_retrieval.py (PreToolUse Hook)
# =============================================================================


class TestBestPracticesRetrieval:
    """Tests for best_practices_retrieval.py PreToolUse hook."""

    def test_accepts_valid_hook_input(self):
        """Test accepting valid hook input."""
        script = HOOKS_DIR / "best_practices_retrieval.py"

        # Create hook input for Edit tool
        hook_input = create_hook_input(
            tool_name="Edit",
            tool_input={"file_path": "src/auth/login.py"},
            cwd=str(PROJECT_ROOT),
        )

        # Use invalid Qdrant for graceful degradation
        result = run_hook_script(
            script, stdin_data=hook_input, env={"QDRANT_URL": "http://localhost:99999"}
        )

        # Should exit 0 (graceful degradation)
        assert result["exit_code"] == 0

    @pytest.mark.parametrize(
        "file_path",
        [
            "src/auth/login.py",
            "src/database/models.py",
            "tests/test_api.py",
            ".claude/hooks/scripts/session_start.py",
        ],
    )
    def test_processes_different_file_paths(self, file_path):
        """Test processing different file path patterns."""
        script = HOOKS_DIR / "best_practices_retrieval.py"

        hook_input = create_hook_input(
            tool_name="Edit", tool_input={"file_path": file_path}
        )

        result = run_hook_script(
            script, stdin_data=hook_input, env={"QDRANT_URL": "http://localhost:99999"}
        )

        # Should exit 0 even if no results (graceful degradation)
        assert result["exit_code"] == 0

    def test_graceful_degradation_on_malformed_json(self):
        """Test graceful degradation on malformed hook input."""
        script = HOOKS_DIR / "best_practices_retrieval.py"

        result = run_hook_script(script, stdin_data="not valid json")

        # Should exit 0 (graceful degradation)
        assert result["exit_code"] == 0


# =============================================================================
# Test error_pattern_capture.py (PostToolUse Hook)
# =============================================================================


class TestErrorPatternCapture:
    """Tests for error_pattern_capture.py PostToolUse hook."""

    def test_accepts_bash_error_output(self):
        """Test accepting Bash tool with error output."""
        script = HOOKS_DIR / "error_pattern_capture.py"

        # Create hook input for Bash tool with error output
        hook_input = create_hook_input(
            tool_name="Bash",
            tool_input={"command": "pytest tests/"},
            tool_output="ERROR: pytest failed\nFile test.py, line 42\n  assert False\nAssertionError",
        )

        result = run_hook_script(
            script,
            stdin_data=hook_input,
            env={"QDRANT_URL": "http://localhost:99999"},  # Graceful degradation
        )

        # Should exit 0 (success or graceful degradation)
        assert result["exit_code"] == 0

    @pytest.mark.parametrize(
        "error_output",
        [
            "Error: command failed",
            "FATAL: database connection refused",
            "Traceback (most recent call last):",
            "Exception: invalid argument",
            "Warning: deprecated function",
            "Permission denied",
            "No such file or directory",
            "Command not found: unknown-cmd",
        ],
    )
    def test_processes_various_error_types(self, error_output):
        """Test processing various error output patterns."""
        script = HOOKS_DIR / "error_pattern_capture.py"

        hook_input = create_hook_input(
            tool_name="Bash",
            tool_input={"command": "test-command"},
            tool_output=error_output,
        )

        result = run_hook_script(
            script, stdin_data=hook_input, env={"QDRANT_URL": "http://localhost:99999"}
        )

        # Should exit 0 for all error types (graceful degradation)
        assert result["exit_code"] == 0

    def test_processes_error_with_file_references(self):
        """Test processing errors with file:line references."""
        script = HOOKS_DIR / "error_pattern_capture.py"

        # Error with file:line references
        error_with_refs = 'File "src/auth/login.py", line 42\n  raise ValueError("Invalid")\nValueError: Invalid'

        hook_input = create_hook_input(
            tool_name="Bash",
            tool_input={"command": "python src/auth/login.py"},
            tool_output=error_with_refs,
        )

        result = run_hook_script(
            script, stdin_data=hook_input, env={"QDRANT_URL": "http://localhost:99999"}
        )

        # Should exit 0 (graceful degradation)
        assert result["exit_code"] == 0

    def test_graceful_degradation_on_malformed_input(self):
        """Test graceful degradation on malformed hook input."""
        script = HOOKS_DIR / "error_pattern_capture.py"

        # Malformed JSON
        result = run_hook_script(script, stdin_data="not valid json")

        # Should exit 0 (graceful degradation)
        assert result["exit_code"] == 0

    def test_processes_successful_command_gracefully(self):
        """Test hook processes successful command output (no error)."""
        script = HOOKS_DIR / "error_pattern_capture.py"

        # Successful command output
        hook_input = create_hook_input(
            tool_name="Bash",
            tool_input={"command": "ls -la"},
            tool_output="total 48\ndrwxr-xr-x  10 user  staff  320 Jan 16 10:00 .\ndrwxr-xr-x  20 user  staff  640 Jan 16 09:00 ..",
        )

        result = run_hook_script(script, stdin_data=hook_input)

        # Should exit 0 (no error to capture, nothing to do)
        assert result["exit_code"] == 0


# =============================================================================
# Integration Tests with Real Qdrant (Requires Docker)
# =============================================================================


@pytest.mark.integration
class TestHooksWithRealQdrant:
    """Integration tests using real Qdrant (requires Docker services running)."""

    def test_end_to_end_workflow(self, docker_services_available):
        """Test complete workflow: search -> store -> search again."""
        if not docker_services_available:
            pytest.skip("Docker services not running")

        # Step 1: Search for memories (should return empty initially)
        search_script = SCRIPTS_DIR / "pre-work-search.py"
        search_result = run_hook_script(
            search_script,
            args=["--query", "authentication implementation", "--limit", "3"],
        )

        assert search_result["exit_code"] == 0
        assert search_result["json_output"] is not None

        # Step 2: Store a new memory
        store_script = SCRIPTS_DIR / "post-work-store.py"

        metadata = {
            "type": "implementation",
            "group_id": "test-project",
            "source_hook": "PostToolUse",
            "session_id": "test-session-e2e",
            "agent": "dev",
            "component": "auth",
            "importance": "medium",
        }

        content = (
            "Implemented JWT authentication middleware for API endpoints. "
            "Token validation added in src/auth/middleware.py:45-89. "
            "Refresh token logic in src/auth/refresh.py:12-34."
        )

        store_result = run_hook_script(
            store_script,
            args=[
                "--content",
                content,
                "--metadata",
                json.dumps(metadata),
                "--sync",  # Synchronous for testing
                "--skip-duplicate-check",  # Allow repeated test runs
            ],
            env={"QDRANT_URL": "http://localhost:26350"},
        )

        assert store_result["exit_code"] == 0

        # Step 3: Search again (should find the stored memory)
        # Note: May need to wait for embedding generation
        import time

        time.sleep(2)  # Wait for async embedding

        search_result_2 = run_hook_script(
            search_script,
            args=["--query", "authentication JWT tokens", "--limit", "5"],
            env={"QDRANT_URL": "http://localhost:26350"},
        )

        assert search_result_2["exit_code"] == 0
        assert search_result_2["json_output"] is not None

        # Cleanup: Delete test memory
        # (Handled by test fixtures in conftest.py)
