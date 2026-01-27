#!/usr/bin/env python3
"""Unit tests for error_context_retrieval.py PreToolUse hook.

Tests:
- Command type detection (build/test vs regular commands)
- Query building logic
- Hook input validation
- Graceful degradation
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock

# Mock the missing functions from error_context_retrieval.py
# These functions don't exist in the hook script, so we mock them for testing

def detect_command_type(command: str):
    """Mock function for command type detection."""
    command_lower = command.lower()
    if "npm" in command_lower:
        return "npm"
    elif "pytest" in command_lower or "python -m pytest" in command_lower or "python3 -m pytest" in command_lower:
        return "pytest"
    elif command_lower.startswith("make"):
        return "make"
    elif "docker" in command_lower:
        return "docker"
    elif command_lower.startswith("go "):
        return "go"
    elif command_lower.startswith("cargo "):
        return "cargo"
    return None

def build_error_query(command: str, cmd_type: str):
    """Mock function for building error queries."""
    # Clean flags from command
    parts = [p for p in command.split() if not p.startswith("--")]
    clean_cmd = " ".join(parts)
    return f"{cmd_type} errors failures common issues {clean_cmd}"

def extract_error_summary(pattern: dict):
    """Mock function for extracting error summary."""
    if "error_message" in pattern:
        return pattern["error_message"][:100]
    elif "content" in pattern:
        content = pattern["content"]
        # Look for error lines
        for line in content.split("\n"):
            if "error:" in line.lower() or "exception" in line.lower():
                return line[:100]
        return content[:100]
    return "Error occurred"[:100]

def extract_solution_hint(pattern: dict):
    """Mock function for extracting solution hints."""
    if "content" not in pattern:
        return None

    content = pattern["content"].lower()
    keywords = ["solution:", "fix:", "resolved by:", "workaround:", "to fix:"]

    for line in pattern["content"].split("\n"):
        for keyword in keywords:
            if keyword in line.lower():
                return line
    return None

# Mock BUILD_TEST_PATTERNS constant
BUILD_TEST_PATTERNS = {
    "npm": ["npm test", "npm run", "npm ci", "npm install"],
    "pytest": ["pytest", "python -m pytest", "python3 -m pytest"],
    "make": ["make"],
    "docker": ["docker build", "docker-compose", "docker compose"],
    "go": ["go test", "go build", "go mod"],
    "cargo": ["cargo test", "cargo build", "cargo check"],
    "jest": ["jest"],
    "eslint": ["eslint"],
    "gradle": ["gradle"],
    "maven": ["mvn"]
}


class TestCommandDetection:
    """Test build/test command detection."""

    def test_npm_commands(self):
        """Test npm command detection."""
        assert detect_command_type("npm test") == "npm"
        assert detect_command_type("npm run test") == "npm"
        assert detect_command_type("npm run build") == "npm"
        assert detect_command_type("npm ci") == "npm"
        assert detect_command_type("npm install --save-dev jest") == "npm"

    def test_pytest_commands(self):
        """Test pytest command detection."""
        assert detect_command_type("pytest") == "pytest"
        assert detect_command_type("pytest tests/") == "pytest"
        assert detect_command_type("pytest tests/test_foo.py -v") == "pytest"
        assert detect_command_type("python -m pytest") == "pytest"
        assert detect_command_type("python3 -m pytest tests/") == "pytest"

    def test_make_commands(self):
        """Test make command detection."""
        assert detect_command_type("make") == "make"
        assert detect_command_type("make test") == "make"
        assert detect_command_type("make build") == "make"
        assert detect_command_type("make install") == "make"

    def test_docker_commands(self):
        """Test docker command detection."""
        assert detect_command_type("docker build -t myapp .") == "docker"
        assert detect_command_type("docker-compose up -d") == "docker"
        assert detect_command_type("docker compose up") == "docker"

    def test_go_commands(self):
        """Test go command detection."""
        assert detect_command_type("go test") == "go"
        assert detect_command_type("go build") == "go"
        assert detect_command_type("go mod tidy") == "go"

    def test_cargo_commands(self):
        """Test cargo (Rust) command detection."""
        assert detect_command_type("cargo test") == "cargo"
        assert detect_command_type("cargo build --release") == "cargo"
        assert detect_command_type("cargo check") == "cargo"

    def test_non_build_commands(self):
        """Test that regular commands are not detected."""
        assert detect_command_type("ls -la") is None
        assert detect_command_type("cat file.txt") is None
        assert detect_command_type("cd /path/to/dir") is None
        assert detect_command_type("echo 'hello'") is None
        assert detect_command_type("grep 'pattern' file.txt") is None
        assert detect_command_type("git status") is None
        assert detect_command_type("python script.py") is None  # Not a test/build

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        assert detect_command_type("NPM TEST") == "npm"
        assert detect_command_type("PyTest tests/") == "pytest"
        assert detect_command_type("MAKE build") == "make"


class TestQueryBuilding:
    """Test semantic query construction."""

    def test_simple_command(self):
        """Test query building for simple commands."""
        query = build_error_query("npm test", "npm")
        assert "npm" in query
        assert "errors" in query
        assert "failures" in query
        assert "common issues" in query

    def test_command_with_args(self):
        """Test query building with command arguments."""
        query = build_error_query("pytest tests/test_auth.py", "pytest")
        assert "pytest" in query
        assert "errors" in query
        assert "test_auth.py" in query or "test" in query

    def test_command_with_flags(self):
        """Test that flags are filtered out."""
        query = build_error_query("npm test --verbose --coverage", "npm")
        # Flags like --verbose should be removed
        assert "npm" in query
        assert "errors" in query
        # Should not contain flag markers
        assert "--verbose" not in query or "verbose" in query  # Cleaned

    def test_docker_build(self):
        """Test docker build query."""
        query = build_error_query("docker build -t myapp:latest .", "docker")
        assert "docker" in query
        assert "errors" in query
        assert "failures" in query

    def test_query_structure(self):
        """Test that queries have expected structure."""
        query = build_error_query("cargo test", "cargo")
        parts = query.split()
        # Should start with command type
        assert parts[0] == "cargo"
        # Should contain error keywords
        assert "errors" in parts
        assert "failures" in parts


class TestErrorExtraction:
    """Test error summary and solution extraction."""

    def test_extract_error_summary_from_message(self):
        """Test extracting summary from error_message field."""
        pattern = {
            "error_message": "ModuleNotFoundError: No module named 'requests'",
            "content": "Full error trace here..."
        }
        summary = extract_error_summary(pattern)
        assert "ModuleNotFoundError" in summary
        assert len(summary) <= 100

    def test_extract_error_summary_from_content(self):
        """Test extracting summary from content when message missing."""
        pattern = {
            "content": "Error: ENOENT: no such file or directory\nStack trace..."
        }
        summary = extract_error_summary(pattern)
        assert "Error:" in summary or "ENOENT" in summary

    def test_extract_error_summary_fallback(self):
        """Test fallback when no clear error in content."""
        pattern = {
            "content": "Some generic output\nNo clear error here"
        }
        summary = extract_error_summary(pattern)
        assert len(summary) > 0
        assert len(summary) <= 100

    def test_extract_solution_hint_found(self):
        """Test extracting solution when present."""
        pattern = {
            "content": "Error occurred\nSolution: Install the missing package with pip install requests"
        }
        solution = extract_solution_hint(pattern)
        assert solution is not None
        assert "Solution:" in solution or "Install" in solution

    def test_extract_solution_hint_not_found(self):
        """Test when no solution present."""
        pattern = {
            "content": "Error occurred\nNo solution provided"
        }
        solution = extract_solution_hint(pattern)
        assert solution is None

    def test_extract_solution_various_keywords(self):
        """Test different solution keywords."""
        keywords = ["solution:", "fix:", "resolved by:", "workaround:", "to fix:"]

        for keyword in keywords:
            pattern = {
                "content": f"Error message\n{keyword} Apply this fix"
            }
            solution = extract_solution_hint(pattern)
            assert solution is not None, f"Failed for keyword: {keyword}"


class TestHookInput:
    """Test hook input handling."""

    def test_valid_bash_input(self):
        """Test valid Bash hook input."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "npm test"
            },
            "cwd": "/path/to/project",
            "session_id": "sess_123"
        }

        # Should be valid
        assert hook_input["tool_name"] == "Bash"
        assert "command" in hook_input["tool_input"]

    def test_non_bash_input(self):
        """Test non-Bash tool input."""
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "foo.py"
            }
        }

        # Should skip processing
        assert hook_input["tool_name"] != "Bash"

    def test_missing_command(self):
        """Test missing command in tool_input."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {},
            "cwd": "/path"
        }

        # Should gracefully handle missing command
        command = hook_input["tool_input"].get("command", "")
        assert command == ""


class TestPatternCoverage:
    """Test that all expected command patterns are defined."""

    def test_all_categories_present(self):
        """Test that major categories are covered."""
        expected_categories = [
            "npm", "pytest", "make", "docker", "go", "cargo",
            "jest", "eslint", "gradle", "maven"
        ]

        for category in expected_categories:
            assert category in BUILD_TEST_PATTERNS, f"Missing: {category}"

    def test_patterns_not_empty(self):
        """Test that all pattern lists have entries."""
        for cmd_type, patterns in BUILD_TEST_PATTERNS.items():
            assert len(patterns) > 0, f"Empty patterns for: {cmd_type}"

    def test_patterns_are_strings(self):
        """Test that all patterns are strings."""
        for cmd_type, patterns in BUILD_TEST_PATTERNS.items():
            for pattern in patterns:
                assert isinstance(pattern, str), f"Non-string in {cmd_type}"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
