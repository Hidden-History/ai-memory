"""Unit tests for TECH-DEBT-157: Session state path sanitization.

Tests that InjectionSessionState._state_path() properly sanitizes
session_id to prevent path traversal attacks.
"""

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
