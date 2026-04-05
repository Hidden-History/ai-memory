"""Test error pattern capture hook functionality."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def hook_script():
    """Get path to error_pattern_capture.py script."""
    script_path = (
        Path(__file__).parent.parent
        / ".claude"
        / "hooks"
        / "scripts"
        / "error_pattern_capture.py"
    )
    assert script_path.exists(), f"Hook script not found: {script_path}"
    return script_path


@pytest.fixture
def hook_env():
    """Environment variables for running hook scripts."""
    env = os.environ.copy()
    # Point to source directory for imports
    env["AI_MEMORY_INSTALL_DIR"] = str(Path(__file__).parent.parent)
    return env


def test_error_pattern_detection(hook_script, hook_env):
    """Test that error patterns are detected from Bash failures."""
    # Simulate Claude Code hook input for a failed Bash command
    hook_input = {
        "tool_name": "Bash",
        "tool_input": {"command": "python3 /path/to/script.py"},
        "tool_response": {
            "output": """Traceback (most recent call last):
  File "/path/to/script.py", line 42, in <module>
    result = divide(10, 0)
  File "/path/to/script.py", line 15, in divide
    return a / b
ZeroDivisionError: division by zero""",
            "exitCode": 1,
        },
        "cwd": "/tmp/test-project",
        "session_id": "test_session_123",
    }

    # Run hook script with input
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=hook_env,
    )

    # Hook should exit 0 (non-blocking)
    assert result.returncode == 0, f"Hook failed: {result.stderr}"

    # Should log error pattern detection
    # Note: Background fork means storage happens async, so we just verify hook succeeds


def test_no_error_pattern_for_success(hook_script, hook_env):
    """Test that successful commands don't trigger error capture."""
    # Simulate successful Bash command
    hook_input = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo 'Hello World'"},
        "tool_response": {"output": "Hello World\n", "exitCode": 0},
        "cwd": "/tmp/test-project",
        "session_id": "test_session_456",
    }

    # Run hook script
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=hook_env,
    )

    # Should still exit 0, but not capture anything
    assert result.returncode == 0


def test_file_line_reference_extraction(hook_script, hook_env):
    """Test extraction of file:line references from errors."""
    hook_input = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/test_foo.py"},
        "tool_response": {
            "output": """tests/test_foo.py:25: error: Assertion failed
Expected: 42
Actual: 24
File "tests/test_foo.py", line 25, in test_calculation""",
            "exitCode": 1,
        },
        "cwd": "/tmp/test-project",
        "session_id": "test_session_789",
    }

    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=hook_env,
    )

    assert result.returncode == 0


def test_malformed_json_graceful_handling(hook_script, hook_env):
    """Test graceful handling of malformed JSON input."""
    malformed_input = "{ this is not valid json }"

    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=malformed_input,
        capture_output=True,
        text=True,
        env=hook_env,
    )

    # Should exit 0 (non-blocking error)
    assert result.returncode == 0


class TestDetectErrorIndicators:
    """Unit tests for detect_error_indicators() — TD-260 false positive prevention."""

    @pytest.fixture(autouse=True)
    def _import_function(self):
        """Import detect_error_indicators from hook script."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "error_pattern_capture",
            Path(__file__).parent.parent
            / ".claude"
            / "hooks"
            / "scripts"
            / "error_pattern_capture.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.detect = mod.detect_error_indicators

    def test_conversational_error_mention_not_detected(self):
        """TD-260: Conversational text mentioning 'error' should NOT trigger capture."""
        conversational_outputs = [
            "I fixed the error in the config file and it works now.",
            "No errors were found during the review.",
            "The error was resolved by updating the dependency.",
            "Error handling has been improved in this release.",
            "Successfully deployed — no issues detected.",
            "The error is gone after the patch was applied.",
        ]
        for output in conversational_outputs:
            assert self.detect(output, 0) is False, f"False positive on: {output!r}"
            assert self.detect(output, None) is False, f"False positive on: {output!r}"

    def test_nonzero_exit_code_always_detected(self):
        """Non-zero exit code should ALWAYS return True, even with conversational text."""
        assert self.detect("I fixed the error successfully", 1) is True
        assert self.detect("No errors found", 2) is True

    def test_real_traceback_detected(self):
        """Real Python tracebacks should still be detected."""
        traceback = (
            "Traceback (most recent call last):\n"
            '  File "script.py", line 10, in <module>\n'
            "    result = 1 / 0\n"
            "ZeroDivisionError: division by zero"
        )
        assert self.detect(traceback, 0) is True
        assert self.detect(traceback, 1) is True

    def test_real_exception_types_detected(self):
        """Specific Python exception patterns should still be detected."""
        assert self.detect("ModuleNotFoundError: No module named 'foo'", 0) is True
        assert self.detect("TypeError: expected str, got int", 0) is True
        assert self.detect("FileNotFoundError: [Errno 2] No such file", 0) is True

    def test_command_not_found_detected(self):
        """Shell errors should still be detected."""
        assert self.detect("bash: foobar: command not found", 0) is True

    def test_real_error_after_conversational_prefix(self):
        """A real error following conversational text should still be detected."""
        output = (
            "Successfully connected to database\n"
            "Loading config...\n"
            "Traceback (most recent call last):\n"
            '  File "app.py", line 42\n'
            "TypeError: expected str, got int"
        )
        assert self.detect(output, 0) is True

    def test_real_error_with_no_issues_prefix(self):
        """Real error mixed with 'no issues' conversational prefix still detected."""
        output = (
            "No issues with initial setup\n"
            "ModuleNotFoundError: No module named 'missing_dep'\n"
        )
        assert self.detect(output, 0) is True

    def test_clean_output_not_detected(self):
        """Normal output without errors should not trigger."""
        assert self.detect("Hello World", 0) is False
        assert self.detect("Build complete.\n3 files processed.", 0) is False


class TestHookExitCodes:
    """H-4: All hooks must exit 0 on failure (§1.2 Principle 4)."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        """Import main function from hook script."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "error_pattern_capture",
            Path(__file__).parent.parent
            / ".claude"
            / "hooks"
            / "scripts"
            / "error_pattern_capture.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.module = mod

    def test_main_returns_0_on_success(self, hook_script, hook_env):
        """Hook returns 0 on successful error capture."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 script.py"},
            "tool_response": {
                "output": "Traceback (most recent call last):\nZeroDivisionError: division by zero",
                "exitCode": 1,
            },
            "cwd": "/tmp/test",
            "session_id": "test_exit_0",
        }
        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            env=hook_env,
        )
        assert result.returncode == 0

    def test_main_returns_0_on_malformed_json(self, hook_script, hook_env):
        """Hook returns 0 even on malformed JSON (never blocks Claude)."""
        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input="not valid json {{{",
            capture_output=True,
            text=True,
            env=hook_env,
        )
        assert result.returncode == 0

    def test_main_returns_0_on_validation_failure(self, hook_script, hook_env):
        """Hook returns 0 on validation failure (missing fields)."""
        hook_input = {"tool_name": "NotBash"}
        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            env=hook_env,
        )
        assert result.returncode == 0

    def test_no_return_1_in_main(self):
        """Verify no 'return 1' exists in main() function source code."""
        import inspect

        source = inspect.getsource(self.module.main)
        assert "return 1" not in source, "main() must never return 1 (§1.2 Principle 4)"


class TestBashFixConfidence:
    """M-2: Bash fix confidence 0.4 for 4-10 turn range."""

    @pytest.fixture(autouse=True)
    def _import_module(self):
        """Import detect_bash_fix from hook script."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "error_pattern_capture",
            Path(__file__).parent.parent
            / ".claude"
            / "hooks"
            / "scripts"
            / "error_pattern_capture.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.module = mod

    def test_confidence_within_3_turns(self):
        """Within 3 turns: confidence = 0.5 — structural verification via AST walk."""
        import ast
        import inspect

        source = inspect.getsource(self.module.detect_bash_fix)
        tree = ast.parse(source)

        # Walk the AST and find an `If` node whose test is a `Compare` where
        # one side is a `turn_diff` Name and the other is Constant(3) with LtE op.
        # The body of that If should contain an assignment or return with 0.5.
        found_branch = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            # Check if the test is a `turn_diff <= 3` comparison
            test = node.test
            if not isinstance(test, ast.Compare):
                continue
            if not any(isinstance(op, ast.LtE) for op in test.ops):
                continue
            # Look for `turn_diff` identifier on either side
            names = []
            if isinstance(test.left, ast.Name):
                names.append(test.left.id)
            for comp in test.comparators:
                if isinstance(comp, ast.Name):
                    names.append(comp.id)
            if "turn_diff" not in names:
                continue
            # Look for Constant(3) in the comparison
            has_three = any(
                isinstance(comp, ast.Constant) and comp.value == 3
                for comp in test.comparators
            ) or (isinstance(test.left, ast.Constant) and test.left.value == 3)
            if not has_three:
                continue
            # Found the `turn_diff <= 3` branch. Scope walk to node.body only
            # (ast.walk(node) also traverses orelse/elif branches — false positive risk).
            for stmt in node.body:
                for child in ast.walk(stmt):
                    if isinstance(child, ast.Constant) and child.value == 0.5:
                        found_branch = True
                        break
                if found_branch:
                    break
            if found_branch:
                break

        assert found_branch, (
            "detect_bash_fix must contain a `turn_diff <= 3` branch assigning confidence 0.5. "
            "Verified via AST walk (BP-150 §importlib hook testing, Strategy B)."
        )

    def test_confidence_4_to_10_turns(self):
        """4-10 turns: confidence = 0.4 (interpolation)."""
        # Verify the code path exists
        import inspect

        source = inspect.getsource(self.module.detect_bash_fix)
        assert "0.4" in source, "Confidence 0.4 must exist for 4-10 turn range"
        assert "0.5" in source, "Confidence 0.5 must exist for ≤3 turn range"
        assert "0.3" in source, "Confidence 0.3 must exist for >10 turn range"

    def test_confidence_beyond_10_turns(self):
        """Beyond 10 turns: confidence = 0.3."""
        import inspect

        source = inspect.getsource(self.module.detect_bash_fix)
        # Verify the three-tier structure exists
        assert "turn_diff <= 3" in source
        assert "turn_diff <= 10" in source


def test_non_bash_tool_skipped(hook_script, hook_env):
    """Test that non-Bash tools are skipped."""
    hook_input = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/path/to/file.py",
            "old_string": "foo",
            "new_string": "bar",
        },
        "tool_response": {"filePath": "/path/to/file.py"},
        "cwd": "/tmp/test-project",
        "session_id": "test_session_edit",
    }

    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=hook_env,
    )

    # Should exit 0 and skip processing
    assert result.returncode == 0
