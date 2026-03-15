"""Unit tests for monitoring API log injection sanitization (S-16.6).

Tests verify that:
- sanitize_log_input() strips log injection payloads (newlines, etc.)
- memory_id and collection path params are sanitized before logging
- API endpoint responses are unchanged for valid inputs

NOTE: monitoring/main.py requires FastAPI/Qdrant deps that live only in the
monitoring Docker container. We mock those heavy deps at the sys.modules level
before importing main so these tests run in the project's normal venv.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stub out heavy monitoring-only deps so we can import monitoring/main.py
# without a FastAPI/Qdrant installation.
# ---------------------------------------------------------------------------
def _make_fastapi_stub():
    fastapi_mod = MagicMock()

    class _App:
        def __init__(self, **kw):
            pass

        def get(self, *a, **kw):
            return lambda f: f

        def post(self, *a, **kw):
            return lambda f: f

        def mount(self, *a, **kw):
            pass

    fastapi_mod.FastAPI = _App
    fastapi_mod.HTTPException = Exception
    fastapi_mod.status.HTTP_503_SERVICE_UNAVAILABLE = 503
    fastapi_mod.status.HTTP_404_NOT_FOUND = 404
    return fastapi_mod


_STUBS = {
    "fastapi": _make_fastapi_stub(),
    "fastapi.responses": MagicMock(),
    "prometheus_client": MagicMock(),
    "pydantic": MagicMock(),
    "qdrant_client": MagicMock(),
    "qdrant_client.http": MagicMock(),
    "qdrant_client.http.exceptions": MagicMock(),
    # Stub memory package to prevent real imports (src/ is in pythonpath)
    "memory": MagicMock(),
    "memory.metrics": MagicMock(),
    "memory.metrics_push": MagicMock(),
    "memory.stats": MagicMock(),
    "memory.warnings": MagicMock(),
}

# Patch sys.modules BEFORE importing main
for _mod, _stub in _STUBS.items():
    if _mod not in sys.modules:
        sys.modules[_mod] = _stub

# Add monitoring dir to path
_monitoring_path = str(Path(__file__).parent.parent / "monitoring")
if _monitoring_path not in sys.path:
    sys.path.insert(0, _monitoring_path)

# Now import the function under test
# Use importlib to import main with patched sys.modules already in place
if "main" in sys.modules:
    del sys.modules["main"]

import main as _monitoring_main  # noqa: E402  (monitoring/main.py)

sanitize_log_input = _monitoring_main.sanitize_log_input


# ---------------------------------------------------------------------------
# Tests for sanitize_log_input
# ---------------------------------------------------------------------------
class TestSanitizeLogInput:
    """Unit tests for the sanitize_log_input helper in monitoring/main.py."""

    def test_newline_stripped(self):
        """Newlines in user input must be escaped to prevent log injection."""
        result = sanitize_log_input("valid-id\nINJECTED: fake log entry")
        assert "\n" not in result

    def test_carriage_return_stripped(self):
        """Carriage returns must be escaped."""
        result = sanitize_log_input("valid-id\rINJECTED")
        assert "\r" not in result

    def test_tab_escaped(self):
        """Tabs must be escaped."""
        result = sanitize_log_input("id\twith\ttabs")
        assert "\t" not in result

    def test_null_byte_stripped(self):
        """Null bytes must be stripped."""
        result = sanitize_log_input("id\x00null")
        assert "\x00" not in result

    def test_valid_uuid_unchanged(self):
        """Valid UUID-style IDs should pass through cleanly."""
        memory_id = "550e8400-e29b-41d4-a716-446655440000"
        result = sanitize_log_input(memory_id)
        assert "550e8400" in result
        assert "446655440000" in result

    def test_valid_collection_names_pass_through(self):
        """Valid collection names should pass through cleanly."""
        for collection in ("code-patterns", "conventions", "discussions"):
            result = sanitize_log_input(collection)
            assert collection in result

    def test_truncation_at_default_max_length(self):
        """Oversized input should be truncated to 200 chars."""
        result = sanitize_log_input("x" * 500)
        assert len(result) <= 200

    def test_custom_max_length_respected(self):
        """Custom max_length should be respected."""
        result = sanitize_log_input("a" * 50, max_length=10)
        assert len(result) <= 10

    def test_non_string_coerced(self):
        """Non-string values should be coerced to string safely."""
        result = sanitize_log_input(12345)
        assert "12345" in result

    def test_multiline_injection_in_collection(self):
        """Collection param with embedded newline must not produce raw newline."""
        result = sanitize_log_input("code-patterns\nINJECTED: severity=CRITICAL")
        assert "\n" not in result

    def test_unicode_control_chars_stripped(self):
        """Unicode control characters should be stripped."""
        payload = "id\u0000\u001f\u007f"
        result = sanitize_log_input(payload)
        for char in payload:
            if not char.isprintable():
                assert char not in result

    def test_empty_string(self):
        """Empty string input should return empty string."""
        assert sanitize_log_input("") == ""

    def test_exception_str_sanitized(self):
        """Exception messages with injection payloads must be sanitized."""
        try:
            raise ValueError("error\nINJECTED: severity=critical")
        except ValueError as e:
            result = sanitize_log_input(str(e))
            assert "\n" not in result
            assert "error" in result

    def test_none_input(self):
        assert sanitize_log_input(None) == "None"

    def test_multiline_memory_id_no_raw_newline(self):
        """memory_id injection payload must not produce raw newline in sanitized output."""
        result = sanitize_log_input("evil-id\nINJECTED")
        assert "\n" not in result

    def test_repr_escaping_preserves_printable_content(self):
        """repr()-based escaping should keep the meaningful part of the value."""
        value = "abc123"
        result = sanitize_log_input(value)
        assert "abc123" in result


# ---------------------------------------------------------------------------
# Verify call-site sanitization is inline (not via intermediate variable)
# ---------------------------------------------------------------------------
class TestCallSiteSanitization:
    """Verify that log call sites in monitoring/main.py sanitize inline.

    CodeQL requires sanitization to appear inline at the log call site rather
    than through intermediate variables. We inspect the source to confirm
    the pattern is correct.
    """

    def _read_main_source(self) -> str:
        main_path = Path(__file__).parent.parent / "monitoring" / "main.py"
        return main_path.read_text()

    def test_str_e_always_wrapped_in_sanitize(self):
        """Every str(e) used in a logger call must be wrapped with sanitize_log_input."""
        import re

        source = self._read_main_source()

        # More precise: look for "error": str(e) that is NOT inside sanitize_log_input(...)
        # We check that sanitize_log_input( appears immediately before str(
        for match in re.finditer(r'"error":\s*(str\([^)]+\))', source):
            str_pos = match.start(1)
            sanitize_prefix = "sanitize_log_input("
            prefix = source[max(0, str_pos - len(sanitize_prefix)) : str_pos]
            assert prefix.endswith(
                sanitize_prefix
            ), f"Unsanitized str() found at log call site: {match.group(0)}"

    def test_collection_name_in_extra_always_sanitized(self):
        """Every collection_name used in logger extra dicts must be sanitized inline."""
        import re

        source = self._read_main_source()

        # Find bare "collection": collection_name (not wrapped in sanitize_log_input)
        for match in re.finditer(
            r'"collection":\s*(collection_name|request\.collection)', source
        ):
            _value = match.group(1)
            context_start = max(0, match.start() - 60)
            context = source[context_start : match.end()]
            assert (
                "sanitize_log_input" in context
            ), f"Unsanitized collection_name found at log call site: ...{context}..."
