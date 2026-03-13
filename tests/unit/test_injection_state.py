"""Unit tests for TECH-DEBT-157: Session state path sanitization.

Tests that InjectionSessionState._state_path() properly sanitizes
session_id to prevent path traversal attacks.

Also includes backward-compatibility tests for loading old JSON state
files that pre-date the error_state and compact_count fields (PLAN-015).
"""

import json
from pathlib import Path

from memory.injection import InjectionSessionState


class TestSessionStatePathSanitization:
    def test_normal_session_id(self):
        path = InjectionSessionState._state_path("abc-123-def")
        assert str(path) == "/tmp/ai-memory-abc-123-def-injection-state.json"

    def test_path_traversal_stripped(self):
        path = InjectionSessionState._state_path("../../etc/passwd")
        assert ".." not in str(path)
        assert "etc" in str(path)  # "etc" and "passwd" are valid chars
        assert str(path) == "/tmp/ai-memory-etcpasswd-injection-state.json"

    def test_null_bytes_stripped(self):
        path = InjectionSessionState._state_path("session\x00evil")
        assert "\x00" not in str(path)
        assert str(path) == "/tmp/ai-memory-sessionevil-injection-state.json"

    def test_max_length_enforced(self):
        long_id = "a" * 200
        path = InjectionSessionState._state_path(long_id)
        # session_id portion max 64 chars
        assert str(path) == f"/tmp/ai-memory-{'a' * 64}-injection-state.json"

    def test_empty_after_sanitize_uses_unknown(self):
        path = InjectionSessionState._state_path("../../../")
        assert str(path) == "/tmp/ai-memory-unknown-injection-state.json"


class TestResetAfterCompact:
    def test_reset_after_compact_clears_injected_ids(self):
        state = InjectionSessionState(session_id="test-compact-1")
        state.injected_point_ids = ["id1", "id2", "id3"]
        state.reset_after_compact()
        assert state.injected_point_ids == []

    def test_reset_after_compact_increments_compact_count(self):
        state = InjectionSessionState(session_id="test-compact-2")
        assert state.compact_count == 0
        state.reset_after_compact()
        assert state.compact_count == 1
        state.reset_after_compact()
        assert state.compact_count == 2

    def test_reset_after_compact_preserves_topic_drift(self):
        state = InjectionSessionState(session_id="test-compact-3")
        state.topic_drift = 0.75
        state.reset_after_compact()
        assert state.topic_drift == 0.75

    def test_reset_after_compact_preserves_error_state(self):
        state = InjectionSessionState(session_id="test-compact-4")
        state.error_state = {"file": "test.py", "error_group_id": "abc123"}
        state.reset_after_compact()
        assert state.error_state == {"file": "test.py", "error_group_id": "abc123"}

    def test_reset_after_compact_preserves_embedding(self):
        state = InjectionSessionState(session_id="test-compact-5")
        state.last_query_embedding = [0.1, 0.2, 0.3]
        state.reset_after_compact()
        assert state.last_query_embedding == [0.1, 0.2, 0.3]

    def test_error_state_default_is_none(self):
        state = InjectionSessionState(session_id="test-error-state")
        assert state.error_state is None

    def test_compact_count_default_is_zero(self):
        state = InjectionSessionState(session_id="test-compact-count")
        assert state.compact_count == 0


class TestBackwardCompat:
    """Verify InjectionSessionState.load() handles old JSON files lacking new fields.

    Old state files (pre-PLAN-015) do not have error_state or compact_count.
    load() must return valid state with defaults rather than raising TypeError.
    """

    # Use a unique session_id that won't collide with other tests
    SESSION_ID = "backward-compat-test-v1"

    def _state_path(self) -> Path:
        return InjectionSessionState._state_path(self.SESSION_ID)

    def _cleanup(self):
        path = self._state_path()
        import contextlib

        with contextlib.suppress(Exception):
            path.unlink(missing_ok=True)

    def test_load_old_json_without_new_fields(self):
        """load() with old JSON missing error_state and compact_count uses defaults."""
        path = self._state_path()
        old_format_data = {
            "session_id": self.SESSION_ID,
            "injected_point_ids": ["abc-001", "abc-002"],
            "last_query_embedding": None,
            "topic_drift": 0.3,
            "turn_count": 4,
            "total_tokens_injected": 512,
            # Deliberately omitting error_state and compact_count
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(old_format_data))

            state = InjectionSessionState.load(self.SESSION_ID)

            # Fields present in old JSON are preserved
            assert state.session_id == self.SESSION_ID
            assert state.injected_point_ids == ["abc-001", "abc-002"]
            assert state.topic_drift == 0.3
            assert state.turn_count == 4
            assert state.total_tokens_injected == 512

            # New fields absent in old JSON must fall back to their defaults
            assert state.error_state is None
            assert state.compact_count == 0
        finally:
            self._cleanup()
