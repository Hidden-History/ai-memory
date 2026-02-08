"""Unit tests for smart truncation functions.

Tests all 4 functions in memory.chunking.truncation module:
- count_tokens()
- smart_end()
- first_last()
- structured_truncate()

Target: >= 90% code coverage
"""

import pytest

from memory.chunking.truncation import (
    count_tokens,
    first_last,
    smart_end,
    structured_truncate,
)


class TestCountTokens:
    """Test count_tokens() helper function."""

    def test_count_tokens_empty_string(self):
        """Empty string should return 0 tokens."""
        assert count_tokens("") == 0
        assert count_tokens("   ") == 1  # Whitespace is 1 token

    def test_count_tokens_simple_text(self):
        """Simple text should return accurate token count."""
        # "Hello world" is typically 2 tokens
        result = count_tokens("Hello world")
        assert result == 2

    def test_count_tokens_accuracy(self):
        """Verify token counting matches tiktoken expectations."""
        # Test known token counts for cl100k_base encoding
        text = "The quick brown fox jumps over the lazy dog"
        result = count_tokens(text)
        # This sentence is 9 tokens in cl100k_base
        assert result == 9

    def test_count_tokens_with_encoding(self):
        """Test with different encoding."""
        text = "Hello world"
        result_cl100k = count_tokens(text, "cl100k_base")
        result_p50k = count_tokens(text, "p50k_base")
        # Both should return token counts (may differ slightly)
        assert result_cl100k > 0
        assert result_p50k > 0


class TestSmartEnd:
    """Test smart_end() sentence-boundary truncation."""

    def test_smart_end_no_truncation_needed(self):
        """Content under limit should return unchanged."""
        text = "Short text."
        result = smart_end(text, max_tokens=100)
        assert result == text
        assert "[...]" not in result

    def test_smart_end_truncates_at_sentence(self):
        """Should truncate at last sentence boundary."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = smart_end(text, max_tokens=10)

        # Should truncate after a sentence
        assert result.endswith(" [...]")
        assert "First sentence." in result
        # Should not include all sentences
        assert "Fourth sentence" not in result

    def test_smart_end_truncates_at_word(self):
        """Should fall back to word boundary if no sentence found."""
        # Long text without sentence boundaries
        text = "word " * 100  # 100 words, no periods
        result = smart_end(text, max_tokens=20)

        assert "[...]" in result
        # Should truncate and have marker
        assert result.endswith(" [...]")
        # Should have some content before marker
        assert len(result.replace(" [...]", "")) > 0

    def test_smart_end_adds_marker(self):
        """Truncated content must have [...] marker."""
        text = "This is a long sentence that will definitely exceed the token limit."
        result = smart_end(text, max_tokens=5)

        assert "[...]" in result
        assert result.endswith(" [...]")

    def test_smart_end_respects_50pct_rule(self):
        """Should not truncate if last sentence < 50% of budget."""
        # Create text where first sentence is very short (< 50% of budget)
        # and second sentence would exceed budget
        text = "Hi. " + "word " * 100
        result = smart_end(text, max_tokens=20)

        # Should include more than just "Hi."
        assert len(result) > 10
        assert "[...]" in result

    def test_smart_end_empty_content(self):
        """Empty or whitespace-only content should return as-is."""
        assert smart_end("", max_tokens=100) == ""
        assert smart_end("   ", max_tokens=100) == "   "

    def test_smart_end_exactly_at_limit(self):
        """Content exactly at token limit should not truncate."""
        text = "Hello world"  # 2 tokens
        result = smart_end(text, max_tokens=2)
        assert result == text
        assert "[...]" not in result

    def test_smart_end_multiple_sentence_types(self):
        """Should handle different sentence endings (. ! ?)."""
        text = "First! Second? Third. Fourth sentence."
        result = smart_end(text, max_tokens=5)

        assert "[...]" in result
        # Should truncate at one of the sentence boundaries
        assert result.count(".") + result.count("!") + result.count("?") >= 1


class TestFirstLast:
    """Test first_last() head+tail truncation."""

    def test_first_last_no_truncation_needed(self):
        """Content under limit should return unchanged."""
        text = "Short text"
        result = first_last(text, max_tokens=100)
        assert result == text
        assert "[...]" not in result

    def test_first_last_preserves_beginning_and_end(self):
        """Should preserve beginning and end with marker in middle."""
        text = "START\n" + "\n".join([f"line {i}" for i in range(100)]) + "\nEND"
        result = first_last(text, max_tokens=20, first_ratio=0.7)

        assert "START" in result
        assert "END" in result
        assert "[... truncated middle ...]" in result

    def test_first_last_default_ratio(self):
        """Default ratio should be 70/30."""
        lines = [f"line {i}" for i in range(50)]
        text = "\n".join(lines)
        result = first_last(text, max_tokens=20)

        # Should have middle truncated marker
        assert "[... truncated middle ...]" in result
        # Should have both beginning and end
        parts = result.split("[... truncated middle ...]")
        assert len(parts) == 2
        assert len(parts[0]) > 0  # Beginning present
        assert len(parts[1]) > 0  # End present

    def test_first_last_custom_ratio(self):
        """Should respect custom first_ratio."""
        text = "A" * 1000
        result_70_30 = first_last(text, max_tokens=100, first_ratio=0.7)
        result_50_50 = first_last(text, max_tokens=100, first_ratio=0.5)

        # 70/30 should have longer beginning than 50/50
        beginning_70 = result_70_30.split("[... truncated middle ...]")[0]
        beginning_50 = result_50_50.split("[... truncated middle ...]")[0]
        assert len(beginning_70) > len(beginning_50)

    def test_first_last_empty_content(self):
        """Empty content should return as-is."""
        assert first_last("", max_tokens=100) == ""

    def test_first_last_invalid_ratio(self):
        """Invalid ratio should raise ValueError."""
        with pytest.raises(ValueError, match="first_ratio must be between"):
            first_last("text", max_tokens=100, first_ratio=0.0)

        with pytest.raises(ValueError, match="first_ratio must be between"):
            first_last("text", max_tokens=100, first_ratio=1.0)

        with pytest.raises(ValueError, match="first_ratio must be between"):
            first_last("text", max_tokens=100, first_ratio=1.5)


class TestStructuredTruncate:
    """Test structured_truncate() for error context preservation."""

    def test_structured_truncate_all_sections_preserved(self):
        """All 3 sections (command, error, output) must be present."""
        sections = {
            "command": "pytest tests/",
            "error": "AssertionError: expected 5, got 3",
            "output": "long output here " * 50,
        }
        result = structured_truncate("", max_tokens=100, sections=sections)

        assert "Command:" in result
        assert "Error:" in result
        assert "Output:" in result
        assert sections["command"] in result
        assert sections["error"] in result

    def test_structured_truncate_never_truncates_error(self):
        """Error message should NEVER be truncated."""
        error_msg = "Critical error message that must be preserved"
        sections = {
            "command": "long command " * 50,
            "error": error_msg,
            "output": "long output " * 50,
        }
        result = structured_truncate("", max_tokens=50, sections=sections)

        # Error must be complete
        assert error_msg in result

    def test_structured_truncate_within_budget(self):
        """Result should stay within token budget."""
        sections = {
            "command": "pytest tests/test_long.py --verbose",
            "error": "AssertionError: test failed",
            "output": "Output line\n" * 100,
        }
        max_tokens = 100
        result = structured_truncate("", max_tokens=max_tokens, sections=sections)

        # Verify result is within budget (allow some margin for markers)
        result_tokens = count_tokens(result)
        assert result_tokens <= max_tokens + 20  # +20 margin for truncation markers

    def test_structured_truncate_missing_sections(self):
        """Should raise ValueError if required sections missing."""
        with pytest.raises(ValueError, match="Missing required sections"):
            structured_truncate("", max_tokens=100, sections={"command": "test"})

        with pytest.raises(ValueError, match="Missing required sections"):
            structured_truncate(
                "", max_tokens=100, sections={"command": "test", "error": "error"}
            )

    def test_structured_truncate_empty_sections(self):
        """Should handle empty section values."""
        sections = {"command": "", "error": "Error occurred", "output": ""}
        result = structured_truncate("", max_tokens=50, sections=sections)

        assert "Command:" in result
        assert "Error: Error occurred" in result
        assert "Output:" in result

    def test_structured_truncate_error_exceeds_budget(self):
        """When error alone exceeds budget, keep error + minimal command/output."""
        long_error = "Error: " + "word " * 200
        sections = {
            "command": "test command",
            "error": long_error,
            "output": "test output",
        }
        result = structured_truncate("", max_tokens=50, sections=sections)

        # Error should be preserved
        assert "Error:" in result
        # Command should be truncated to minimal
        assert "Command:" in result
        assert "..." in result

    def test_structured_truncate_uses_first_last_for_output(self):
        """Output section should use first_last strategy."""
        sections = {
            "command": "test",
            "error": "error",
            "output": "START\n" + "\n".join([f"line {i}" for i in range(50)]) + "\nEND",
        }
        result = structured_truncate("", max_tokens=150, sections=sections)

        # Should preserve both start and end of output
        assert "START" in result
        assert "END" in result


class TestIntegration:
    """Integration tests for truncation functions."""

    def test_smart_end_with_real_guideline(self):
        """Test smart_end with realistic guideline content."""
        guideline = """# Best Practice: Use Type Hints

        Always use type hints in Python 3.10+ code.

        ## Benefits
        - Better IDE support
        - Catch errors early
        - Self-documenting code

        ## Examples
        ```python
        def greet(name: str) -> str:
            return f"Hello, {name}"
        ```
        """
        result = smart_end(guideline, max_tokens=50)

        assert "[...]" in result
        assert "# Best Practice" in result
        # Should truncate at sentence boundary
        assert result.count(".") >= 1

    def test_first_last_with_log_output(self):
        """Test first_last with realistic log output."""
        log = "Starting process\n"
        log += "\n".join([f"Processing item {i}" for i in range(100)])
        log += "\nProcess completed"

        result = first_last(log, max_tokens=50)

        assert "Starting process" in result
        assert "Process completed" in result
        assert "[... truncated middle ...]" in result

    def test_structured_truncate_with_pytest_error(self):
        """Test structured_truncate with realistic pytest output."""
        sections = {
            "command": "pytest tests/test_storage.py::test_store_memory -v",
            "error": "AssertionError: assert 'stored' == 'duplicate'\n  - duplicate\n  + stored",
            "output": """
======================== test session starts =========================
collected 1 item

tests/test_storage.py::test_store_memory FAILED                [100%]

============================== FAILURES ==============================
_________________________ test_store_memory __________________________

    def test_store_memory():
>       assert result["status"] == "stored"
E       AssertionError: assert 'duplicate' == 'stored'

tests/test_storage.py:42: AssertionError
======================= short test summary info ======================
FAILED tests/test_storage.py::test_store_memory - AssertionError
======================== 1 failed in 0.05s ===========================
            """,
        }

        result = structured_truncate("", max_tokens=200, sections=sections)

        # All critical parts preserved
        assert "pytest tests/test_storage.py" in result
        assert "AssertionError" in result
        assert "Output:" in result
