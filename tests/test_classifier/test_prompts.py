"""Tests for prompt formatting.

TECH-DEBT-069: Ensure file_path is correctly included in prompts.
"""

from src.memory.classifier.prompts import build_classification_prompt


class TestPromptFormatting:
    """Test classification prompt formatting."""

    def test_file_path_included_when_provided(self):
        """File path should appear in formatted prompt."""
        prompt = build_classification_prompt(
            content="Some code here",
            collection="code-patterns",
            current_type="implementation",
            file_path="/src/memory/storage.py",
        )

        assert "File Path: /src/memory/storage.py" in prompt
        assert "Collection: code-patterns" in prompt
        assert "Current Type: implementation" in prompt
        assert "Some code here" in prompt

    def test_file_path_omitted_when_none(self):
        """No file path line when not provided."""
        prompt = build_classification_prompt(
            content="Some code here",
            collection="code-patterns",
            current_type="implementation",
            file_path=None,
        )

        assert "File Path:" not in prompt
        assert "Collection: code-patterns" in prompt
        assert "Current Type: implementation" in prompt

    def test_file_path_omitted_when_empty_string(self):
        """Empty string file_path should not add line."""
        prompt = build_classification_prompt(
            content="Some code here",
            collection="discussions",
            current_type="user_message",
            file_path="",
        )

        # Empty string is falsy, so no File Path line
        assert "File Path:" not in prompt

    def test_content_truncated_to_max(self):
        """Long content should be truncated."""
        long_content = "x" * 10000
        prompt = build_classification_prompt(
            content=long_content,
            collection="discussions",
            current_type="user_message",
        )

        # Content should be truncated to MAX_INPUT_CHARS (4000)
        assert "xxx" in prompt  # Some x's should be there
        assert "[...truncated]" in prompt  # Truncation marker
        assert len(prompt) < len(long_content)  # Definitely shorter

    def test_all_placeholders_replaced(self):
        """No placeholder braces should remain in formatted prompt."""
        prompt = build_classification_prompt(
            content="Test content",
            collection="conventions",
            current_type="rule",
            file_path="/test/file.py",
        )

        # No unfilled placeholders should remain
        assert "{collection}" not in prompt
        assert "{current_type}" not in prompt
        assert "{content}" not in prompt
        assert "{file_path_line}" not in prompt

    def test_response_format_section_present(self):
        """Prompt should include JSON response format instructions."""
        prompt = build_classification_prompt(
            content="Test content",
            collection="discussions",
            current_type="decision",
        )

        assert "RESPONSE FORMAT" in prompt
        assert "classified_type" in prompt
        assert "confidence" in prompt
        assert "reasoning" in prompt

    def test_classification_rules_present(self):
        """Prompt should include classification rules."""
        prompt = build_classification_prompt(
            content="Test content",
            collection="code-patterns",
            current_type="implementation",
        )

        assert "CLASSIFICATION RULES" in prompt
        assert "MOST SPECIFIC" in prompt

    def test_memory_types_documented(self):
        """Prompt should document all memory types."""
        prompt = build_classification_prompt(
            content="Test content",
            collection="discussions",
            current_type="user_message",
        )

        # Check for collection headers
        assert "code-patterns collection" in prompt
        assert "conventions collection" in prompt
        assert "discussions collection" in prompt

        # Check for some specific types
        assert "implementation" in prompt
        assert "error_fix" in prompt
        assert "decision" in prompt
        assert "rule" in prompt
