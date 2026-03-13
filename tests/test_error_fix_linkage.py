"""Test WP-6: Error-to-Fix Linkage.

Covers:
- error_group_id computation (SHA-256 of command_prefix + exception_type + session_id)
- Exception type extraction
- Command prefix extraction
- Fix detection (Edit, Write, Bash)
- Resolution confidence scoring
- Two-phase retrieval
- Freshness blocking
- Priority sorting (confidence >= 0.7 first)
- Session state error tracking
"""

import hashlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load error_pattern_capture module
_SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "hooks" / "scripts"


def _load_module(name, path):
    """Load a module from file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def capture_module():
    """Load error_pattern_capture module."""
    return _load_module(
        "error_pattern_capture",
        _SCRIPTS_DIR / "error_pattern_capture.py",
    )


@pytest.fixture
def detection_module():
    """Load error_detection module."""
    return _load_module(
        "error_detection",
        _SCRIPTS_DIR / "error_detection.py",
    )


# ==============================================================================
# error_group_id Computation
# ==============================================================================


class TestErrorGroupId:
    """Test error_group_id computation."""

    def test_basic_computation(self, capture_module):
        """error_group_id = SHA-256(command_prefix + exception_type + session_id)[:16]."""
        result = capture_module.compute_error_group_id(
            "pip", "ModuleNotFoundError", "sess_123"
        )
        expected = hashlib.sha256(
            b"pip:ModuleNotFoundError:sess_123"
        ).hexdigest()[:16]
        assert result == expected

    def test_length_is_16_hex(self, capture_module):
        """Result must be exactly 16 hex chars."""
        result = capture_module.compute_error_group_id("python3", "TypeError", "abc")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self, capture_module):
        """Same inputs always produce same output."""
        a = capture_module.compute_error_group_id("npm", "Error", "s1")
        b = capture_module.compute_error_group_id("npm", "Error", "s1")
        assert a == b

    def test_different_inputs_different_ids(self, capture_module):
        """Different inputs produce different IDs."""
        a = capture_module.compute_error_group_id("pip", "ModuleNotFoundError", "s1")
        b = capture_module.compute_error_group_id("npm", "ModuleNotFoundError", "s1")
        c = capture_module.compute_error_group_id("pip", "TypeError", "s1")
        assert a != b
        assert a != c
        assert b != c

    def test_empty_inputs(self, capture_module):
        """Empty strings produce a valid hash."""
        result = capture_module.compute_error_group_id("", "", "")
        assert len(result) == 16


# ==============================================================================
# Command Prefix Extraction
# ==============================================================================


class TestCommandPrefix:
    """Test extract_command_prefix."""

    def test_simple_command(self, capture_module):
        assert capture_module.extract_command_prefix("pip install foo") == "pip"

    def test_single_word(self, capture_module):
        assert capture_module.extract_command_prefix("pytest") == "pytest"

    def test_with_path(self, capture_module):
        assert (
            capture_module.extract_command_prefix("/usr/bin/python3 script.py")
            == "/usr/bin/python3"
        )

    def test_empty_command(self, capture_module):
        assert capture_module.extract_command_prefix("") == "unknown"

    def test_whitespace_only(self, capture_module):
        assert capture_module.extract_command_prefix("   ") == "unknown"


# ==============================================================================
# Exception Type Extraction
# ==============================================================================


class TestExceptionType:
    """Test extract_exception_type."""

    def test_module_not_found(self, capture_module):
        assert (
            capture_module.extract_exception_type(
                "ModuleNotFoundError: No module named 'foo'"
            )
            == "ModuleNotFoundError"
        )

    def test_type_error(self, capture_module):
        assert (
            capture_module.extract_exception_type("TypeError: expected str, got int")
            == "TypeError"
        )

    def test_file_not_found(self, capture_module):
        assert (
            capture_module.extract_exception_type(
                "FileNotFoundError: [Errno 2] No such file"
            )
            == "FileNotFoundError"
        )

    def test_value_error(self, capture_module):
        assert (
            capture_module.extract_exception_type(
                "ValueError: invalid literal for int()"
            )
            == "ValueError"
        )

    def test_command_not_found(self, capture_module):
        assert (
            capture_module.extract_exception_type("bash: foobar: command not found")
            == "CommandNotFound"
        )

    def test_permission_denied(self, capture_module):
        assert (
            capture_module.extract_exception_type("Permission denied: /etc/shadow")
            == "PermissionDenied"
        )

    def test_no_such_file(self, capture_module):
        assert (
            capture_module.extract_exception_type(
                "cat: foo.txt: No such file or directory"
            )
            == "FileNotFoundError"
        )

    def test_syntax_error(self, capture_module):
        assert (
            capture_module.extract_exception_type(
                "  File 'x.py', line 1\n    syntax error"
            )
            == "SyntaxError"
        )

    def test_unknown_error(self, capture_module):
        assert (
            capture_module.extract_exception_type("Something went wrong")
            == "UnknownError"
        )


# ==============================================================================
# Resolution Confidence Scoring
# ==============================================================================


def _make_mock_state(turn_count, error_state):
    """Create a mock InjectionSessionState."""
    state = MagicMock()
    state.turn_count = turn_count
    state.error_state = error_state
    state.save = MagicMock()
    return state


def _run_detect_edit_fix(post_tool_module, hook_input, mock_state):
    """Run detect_edit_write_fix with mocked session state, return captured confidence values."""
    captured = []

    def mock_fork(**kwargs):
        captured.append(kwargs.get("resolution_confidence"))

    mock_injection = MagicMock()
    mock_injection.InjectionSessionState.load.return_value = mock_state

    with (
        patch.dict(sys.modules, {"memory.injection": mock_injection}),
        patch.object(
            post_tool_module,
            "_fork_fix_to_background_from_post_tool",
            side_effect=mock_fork,
        ),
    ):
        post_tool_module.detect_edit_write_fix(hook_input)

    return captured


def _run_detect_bash_fix(capture_module, hook_input, mock_state):
    """Run detect_bash_fix with mocked session state, return captured confidence values."""
    captured = []

    def mock_fork(**kwargs):
        captured.append(kwargs.get("resolution_confidence"))

    mock_injection = MagicMock()
    mock_injection.InjectionSessionState.load.return_value = mock_state

    with (
        patch.dict(sys.modules, {"memory.injection": mock_injection}),
        patch.object(
            capture_module, "_fork_fix_to_background", side_effect=mock_fork
        ),
    ):
        capture_module.detect_bash_fix(hook_input)

    return captured


class TestResolutionConfidence:
    """Test resolution confidence scoring via production detect_edit_write_fix."""

    @pytest.fixture
    def post_tool_module(self):
        return _load_module("post_tool_capture", _SCRIPTS_DIR / "post_tool_capture.py")

    def test_same_file_within_3_turns(self, post_tool_module):
        """Same file + within 3 turns = 0.9."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "/tmp/foo.py",
                    "turn_number": 3,
                    "exception_type": "TypeError",
                }
            },
        )
        hook_input = {
            "tool_name": "Edit",
            "session_id": "sess123",
            "tool_input": {"file_path": "/tmp/foo.py", "new_string": "fix"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        result = _run_detect_edit_fix(post_tool_module, hook_input, state)
        assert result == [0.9]

    def test_same_file_within_10_turns(self, post_tool_module):
        """Same file + within 10 turns (4-10) = 0.7."""
        state = _make_mock_state(
            turn_count=10,
            error_state={
                "eid1": {
                    "file_path": "/tmp/foo.py",
                    "turn_number": 3,
                    "exception_type": "TypeError",
                }
            },
        )
        hook_input = {
            "tool_name": "Edit",
            "session_id": "sess123",
            "tool_input": {"file_path": "/tmp/foo.py", "new_string": "fix"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        result = _run_detect_edit_fix(post_tool_module, hook_input, state)
        assert result == [0.7]

    def test_different_file_within_3_turns(self, capture_module):
        """Bash fix + within 3 turns = 0.5 (not-same-file scenario via Bash path)."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "/tmp/err.py",
                    "turn_number": 3,
                    "exception_type": "ModuleNotFoundError",
                    "command_prefix": "pip",
                }
            },
        )
        hook_input = {
            "tool_name": "Bash",
            "session_id": "sess123",
            "tool_input": {"command": "pip install missing_module"},
            "tool_response": {"exitCode": 0},
            "cwd": "/tmp",
        }
        result = _run_detect_bash_fix(capture_module, hook_input, state)
        assert result == [0.5]

    def test_beyond_10_turns(self, post_tool_module):
        """Same file + beyond 10 turns = 0.3."""
        state = _make_mock_state(
            turn_count=20,
            error_state={
                "eid1": {
                    "file_path": "/tmp/foo.py",
                    "turn_number": 3,
                    "exception_type": "TypeError",
                }
            },
        )
        hook_input = {
            "tool_name": "Edit",
            "session_id": "sess123",
            "tool_input": {"file_path": "/tmp/foo.py", "new_string": "fix"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        result = _run_detect_edit_fix(post_tool_module, hook_input, state)
        assert result == [0.3]


# ==============================================================================
# Freshness Blocking
# ==============================================================================


class TestFreshnessBlocking:
    """Test that stale/expired fixes are blocked by two_phase_retrieval."""

    def _make_error_result(self, error_group_id, score=0.8):
        return {
            "score": score,
            "content": "Error content",
            "type": "error_pattern",
            "subtype": "error",
            "file_path": "/tmp/test.py",
            "error_group_id": error_group_id,
        }

    def _make_fix_point(self, freshness_status, confidence=0.9, point_id="fix-id-1"):
        point = MagicMock()
        point.id = point_id
        point.payload = {
            "content": "Fix content",
            "type": "error_pattern",
            "subtype": "fix",
            "file_path": "/tmp/test.py",
            "freshness_status": freshness_status,
            "resolution_confidence": confidence,
        }
        return point

    def _run_two_phase(self, detection_module, phase1_results, scroll_results):
        mock_search = MagicMock()
        mock_search.search.return_value = phase1_results

        mock_client = MagicMock()
        mock_client.scroll.return_value = (scroll_results, None)

        mock_qdrant = MagicMock()
        mock_qdrant.QdrantClient.return_value = mock_client
        mock_qdrant_models = MagicMock()
        mock_qdrant_models.FieldCondition = MagicMock()
        mock_qdrant_models.Filter = MagicMock()
        mock_qdrant_models.MatchValue = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "qdrant_client": mock_qdrant,
                "qdrant_client.models": mock_qdrant_models,
            },
        ):
            return detection_module.two_phase_retrieval(
                search=mock_search,
                error_signature="ModuleNotFoundError",
                project_name="test_project",
                session_id="sess123",
            )

    def test_stale_fix_blocked(self, detection_module):
        """Fixes with freshness_status='stale' are excluded from results."""
        phase1 = [self._make_error_result("egid1")]
        scroll = [self._make_fix_point("stale")]
        results = self._run_two_phase(detection_module, phase1, scroll)
        fixes = [r for r in results if r.get("subtype") == "fix"]
        assert len(fixes) == 0

    def test_expired_fix_blocked(self, detection_module):
        """Fixes with freshness_status='expired' are excluded from results."""
        phase1 = [self._make_error_result("egid1")]
        scroll = [self._make_fix_point("expired")]
        results = self._run_two_phase(detection_module, phase1, scroll)
        fixes = [r for r in results if r.get("subtype") == "fix"]
        assert len(fixes) == 0

    def test_unverified_fix_not_blocked(self, detection_module):
        """Fixes with freshness_status='unverified' are included."""
        phase1 = [self._make_error_result("egid1")]
        scroll = [self._make_fix_point("unverified")]
        results = self._run_two_phase(detection_module, phase1, scroll)
        fixes = [r for r in results if r.get("subtype") == "fix"]
        assert len(fixes) == 1

    def test_fresh_fix_not_blocked(self, detection_module):
        """Fixes with freshness_status='fresh' are included."""
        phase1 = [self._make_error_result("egid1")]
        scroll = [self._make_fix_point("fresh")]
        results = self._run_two_phase(detection_module, phase1, scroll)
        fixes = [r for r in results if r.get("subtype") == "fix"]
        assert len(fixes) == 1

    def test_case_insensitive_stale(self, detection_module):
        """Stale check is case-insensitive."""
        phase1 = [self._make_error_result("egid1")]
        scroll = [self._make_fix_point("STALE")]
        results = self._run_two_phase(detection_module, phase1, scroll)
        fixes = [r for r in results if r.get("subtype") == "fix"]
        assert len(fixes) == 0


# ==============================================================================
# Priority Sorting
# ==============================================================================


class TestPrioritySorting:
    """Test that fixes with resolution_confidence >= 0.7 appear first via two_phase_retrieval."""

    def _make_error_result(self, error_group_id, score=0.8):
        return {
            "score": score,
            "content": "Error content",
            "type": "error_pattern",
            "subtype": "error",
            "file_path": "/tmp/test.py",
            "error_group_id": error_group_id,
        }

    def _make_fix_point(self, confidence, point_id="fix-id-1"):
        point = MagicMock()
        point.id = point_id
        point.payload = {
            "content": "Fix content",
            "type": "error_pattern",
            "subtype": "fix",
            "file_path": "/tmp/test.py",
            "freshness_status": "unverified",
            "resolution_confidence": confidence,
        }
        return point

    def test_high_confidence_fix_first(self, detection_module):
        """Fixes with confidence >= 0.7 appear before errors in output."""
        # Two errors from phase1, each with a fix
        phase1 = [
            self._make_error_result("egid1", score=0.9),
            self._make_error_result("egid2", score=0.85),
        ]
        high_fix = self._make_fix_point(0.9, "fix-high")
        low_fix = self._make_fix_point(0.4, "fix-low")

        mock_search = MagicMock()
        mock_search.search.return_value = phase1

        call_count = [0]

        def scroll_side_effect(**kwargs):
            # First call returns high-confidence fix, second returns low-confidence
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return ([high_fix], None)
            return ([low_fix], None)

        mock_client = MagicMock()
        mock_client.scroll.side_effect = scroll_side_effect

        mock_qdrant = MagicMock()
        mock_qdrant.QdrantClient.return_value = mock_client
        mock_qdrant_models = MagicMock()
        mock_qdrant_models.FieldCondition = MagicMock()
        mock_qdrant_models.Filter = MagicMock()
        mock_qdrant_models.MatchValue = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "qdrant_client": mock_qdrant,
                "qdrant_client.models": mock_qdrant_models,
            },
        ):
            results = detection_module.two_phase_retrieval(
                search=mock_search,
                error_signature="test error",
                project_name="test_project",
                session_id="sess123",
            )

        # First item should be the high-confidence fix
        assert results[0]["subtype"] == "fix"
        assert results[0]["resolution_confidence"] == 0.9
        # Low-confidence fix should be at the end
        assert results[-1]["subtype"] == "fix"
        assert results[-1]["resolution_confidence"] == 0.4


# ==============================================================================
# Error Context Extraction with New Fields
# ==============================================================================


class TestErrorContextExtraction:
    """Test that extract_error_context includes new WP-6 fields."""

    def test_error_context_has_error_group_id(self, capture_module):
        """extract_error_context must include error_group_id."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pip install nonexistent"},
            "tool_response": {
                "stderr": "ModuleNotFoundError: No module named 'nonexistent'",
                "exitCode": 1,
            },
            "cwd": "/tmp/test",
            "session_id": "test_sess",
        }
        ctx = capture_module.extract_error_context(hook_input)
        assert ctx is not None
        assert "error_group_id" in ctx
        assert len(ctx["error_group_id"]) == 16

    def test_error_context_has_command_prefix(self, capture_module):
        """extract_error_context must include command_prefix."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pip install foo"},
            "tool_response": {
                "stderr": "ModuleNotFoundError: foo",
                "exitCode": 1,
            },
            "cwd": "/tmp",
            "session_id": "s1",
        }
        ctx = capture_module.extract_error_context(hook_input)
        assert ctx is not None
        assert ctx["command_prefix"] == "pip"

    def test_error_context_has_exception_type(self, capture_module):
        """extract_error_context must include exception_type."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 script.py"},
            "tool_response": {
                "stderr": "TypeError: expected str, got int",
                "exitCode": 1,
            },
            "cwd": "/tmp",
            "session_id": "s1",
        }
        ctx = capture_module.extract_error_context(hook_input)
        assert ctx is not None
        assert ctx["exception_type"] == "TypeError"


# ==============================================================================
# Fix Detection (Edit)
# ==============================================================================


class TestFixDetectionEdit:
    """Test fix detection for Edit tool by calling detect_edit_write_fix."""

    @pytest.fixture
    def post_tool_module(self):
        return _load_module("post_tool_capture", _SCRIPTS_DIR / "post_tool_capture.py")

    def test_edit_fix_same_file_detected(self, post_tool_module):
        """Edit to file matching active error → fix detected."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "/tmp/app.py",
                    "turn_number": 4,
                    "exception_type": "TypeError",
                }
            },
        )
        hook_input = {
            "tool_name": "Edit",
            "session_id": "sess123",
            "tool_input": {"file_path": "/tmp/app.py", "new_string": "fixed code"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        result = _run_detect_edit_fix(post_tool_module, hook_input, state)
        # Fix should be detected: same file, turn_diff=1 → confidence=0.9
        assert len(result) == 1
        assert result[0] == 0.9

    def test_edit_no_fix_different_file(self, post_tool_module):
        """Edit to unrelated file → no fix detected (else branch removed)."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "/tmp/other.py",
                    "turn_number": 4,
                    "exception_type": "TypeError",
                }
            },
        )
        hook_input = {
            "tool_name": "Edit",
            "session_id": "sess123",
            "tool_input": {"file_path": "/tmp/app.py", "new_string": "fixed code"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        result = _run_detect_edit_fix(post_tool_module, hook_input, state)
        # No fix detected: files don't match
        assert len(result) == 0

    def test_metadata_keys_skipped(self, post_tool_module):
        """Session state keys starting with _ are skipped."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "_last_fix_injected": {
                    "error_group_id": "egid1",
                    "fix_point_id": "fp1",
                },
                "eid1": {
                    "file_path": "/tmp/app.py",
                    "turn_number": 4,
                    "exception_type": "TypeError",
                },
            },
        )
        hook_input = {
            "tool_name": "Edit",
            "session_id": "sess123",
            "tool_input": {"file_path": "/tmp/app.py", "new_string": "fix"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        result = _run_detect_edit_fix(post_tool_module, hook_input, state)
        # Only eid1 should be matched (not _last_fix_injected)
        assert len(result) == 1


# ==============================================================================
# Fix Detection (Write - FileNotFoundError)
# ==============================================================================


class TestFixDetectionWrite:
    """Test fix detection for Write tool via detect_edit_write_fix."""

    @pytest.fixture
    def post_tool_module(self):
        return _load_module("post_tool_capture", _SCRIPTS_DIR / "post_tool_capture.py")

    def test_write_creates_missing_file(self, post_tool_module):
        """Write creating file referenced in FileNotFoundError → fix detected."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "config.py",
                    "turn_number": 4,
                    "exception_type": "FileNotFoundError",
                }
            },
        )
        hook_input = {
            "tool_name": "Write",
            "session_id": "sess123",
            "tool_input": {"file_path": "config.py", "content": "# config file"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        result = _run_detect_edit_fix(post_tool_module, hook_input, state)
        assert len(result) == 1

    def test_write_creates_unrelated_file(self, post_tool_module):
        """Write creating unrelated file → NOT a fix."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "config.py",
                    "turn_number": 4,
                    "exception_type": "FileNotFoundError",
                }
            },
        )
        hook_input = {
            "tool_name": "Write",
            "session_id": "sess123",
            "tool_input": {"file_path": "utils.py", "content": "# utils file"},
            "tool_response": {},
            "cwd": "/tmp",
        }
        result = _run_detect_edit_fix(post_tool_module, hook_input, state)
        assert len(result) == 0


# ==============================================================================
# Fix Detection (Bash)
# ==============================================================================


class TestFixDetectionBash:
    """Test Bash fix detection by calling detect_bash_fix."""

    def test_bash_fix_matching_prefix(self, capture_module):
        """Successful Bash with same command_prefix as error → fix detected."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "script.py",
                    "turn_number": 4,
                    "exception_type": "ModuleNotFoundError",
                    "command_prefix": "pip",
                }
            },
        )
        hook_input = {
            "tool_name": "Bash",
            "session_id": "sess123",
            "tool_input": {"command": "pip install missing_module"},
            "tool_response": {"exitCode": 0},
            "cwd": "/tmp",
        }
        result = _run_detect_bash_fix(capture_module, hook_input, state)
        assert len(result) == 1

    def test_bash_fix_different_prefix(self, capture_module):
        """Successful Bash with different command_prefix → NOT a fix."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "script.py",
                    "turn_number": 4,
                    "exception_type": "ModuleNotFoundError",
                    "command_prefix": "pip",
                }
            },
        )
        hook_input = {
            "tool_name": "Bash",
            "session_id": "sess123",
            "tool_input": {"command": "npm install something"},
            "tool_response": {"exitCode": 0},
            "cwd": "/tmp",
        }
        result = _run_detect_bash_fix(capture_module, hook_input, state)
        assert len(result) == 0

    def test_bash_failure_not_fix(self, capture_module):
        """Failed Bash command → NOT a fix."""
        state = _make_mock_state(
            turn_count=5,
            error_state={
                "eid1": {
                    "file_path": "script.py",
                    "turn_number": 4,
                    "exception_type": "ModuleNotFoundError",
                    "command_prefix": "pip",
                }
            },
        )
        hook_input = {
            "tool_name": "Bash",
            "session_id": "sess123",
            "tool_input": {"command": "pip install missing_module"},
            "tool_response": {"exitCode": 1},
            "cwd": "/tmp",
        }
        result = _run_detect_bash_fix(capture_module, hook_input, state)
        assert len(result) == 0


# ==============================================================================
# Two-Phase Retrieval
# ==============================================================================


class TestTwoPhaseRetrieval:
    """Test two-phase retrieval in error_detection."""

    def test_format_error_pattern_with_fix_subtype(self, detection_module):
        """format_error_pattern should show [FIX] label for fix subtype."""
        fix = {
            "content": "Fix: install missing module",
            "score": 0.8,
            "type": "error_pattern",
            "subtype": "fix",
            "file_path": "requirements.txt",
            "resolution_confidence": 0.9,
        }
        result = detection_module.format_error_pattern(fix, 1)
        assert "[FIX]" in result
        assert "Confidence: 90%" in result

    def test_format_error_pattern_with_error_subtype(self, detection_module):
        """format_error_pattern should show [ERROR] label for error subtype."""
        error = {
            "content": "ModuleNotFoundError: No module named 'foo'",
            "score": 0.85,
            "type": "error_pattern",
            "subtype": "error",
            "file_path": "script.py",
        }
        result = detection_module.format_error_pattern(error, 1)
        assert "[ERROR]" in result

    def test_format_no_subtype_defaults_to_error(self, detection_module):
        """Legacy results without subtype should show [ERROR]."""
        legacy = {
            "content": "Some error content",
            "score": 0.7,
            "type": "error_pattern",
        }
        result = detection_module.format_error_pattern(legacy, 1)
        assert "[ERROR]" in result


# ==============================================================================
# Store Async with New Fields
# ==============================================================================


class TestErrorStoreAsyncFields:
    """Test that error_store_async.py handles new WP-6 fields."""

    @pytest.fixture
    def store_module(self):
        return _load_module(
            "error_store_async",
            _SCRIPTS_DIR / "error_store_async.py",
        )

    def test_format_error_content_still_works(self, store_module):
        """format_error_content should still work with existing fields."""
        ctx = {
            "command": "pip install foo",
            "error_message": "ModuleNotFoundError: foo",
            "exit_code": 1,
            "output": "Error output here",
            "file_references": [],
            "stack_trace": None,
        }
        content = store_module.format_error_content(ctx)
        assert "[error_pattern]" in content
        assert "pip install foo" in content

    def test_fix_context_format(self, store_module):
        """Fix contexts should format with fix-specific content."""
        ctx = {
            "command": "fix:edit",
            "error_message": "Fix for TypeError",
            "exit_code": 0,
            "output": "Edit fix content",
            "file_references": [],
            "stack_trace": None,
            "_is_fix": True,
            "_error_group_id": "abc123def456abcd",
        }
        content = store_module.format_error_content(ctx)
        assert "[error_pattern]" in content


# ==============================================================================
# Metrics Integration
# ==============================================================================


class TestMetricsExist:
    """Test that new Prometheus metrics are defined."""

    def test_error_fix_captures_total_exists(self):
        """aimemory_error_fix_captures_total Counter must exist."""
        from memory.metrics import error_fix_captures_total

        assert error_fix_captures_total is not None

    def test_error_fix_injections_total_exists(self):
        """aimemory_error_fix_injections_total Counter must exist."""
        from memory.metrics import error_fix_injections_total

        assert error_fix_injections_total is not None

    def test_error_fix_effectiveness_total_exists(self):
        """aimemory_error_fix_effectiveness_total Counter must exist."""
        from memory.metrics import error_fix_effectiveness_total

        assert error_fix_effectiveness_total is not None

    def test_effectiveness_has_outcome_label(self):
        """Effectiveness counter must have 'outcome' label."""
        from memory.metrics import error_fix_effectiveness_total

        # Counter._labelnames contains the label names
        assert "outcome" in error_fix_effectiveness_total._labelnames

    def test_effectiveness_has_project_label(self):
        """Effectiveness counter must have 'project' label."""
        from memory.metrics import error_fix_effectiveness_total

        assert "project" in error_fix_effectiveness_total._labelnames


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
