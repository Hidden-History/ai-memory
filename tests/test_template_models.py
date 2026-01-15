"""Tests for template_models.py - Pydantic validation for best practice templates.

Test Coverage:
- BestPracticeTemplate field validation (all fields)
- Content injection prevention (security)
- Tag validation and normalization
- Source URL validation
- load_templates_from_file() with valid/invalid JSON
- Pydantic ValidationError messages

2026 Best Practices:
- Pydantic v2 TypeAdapter validation
- Security-first template validation
- Comprehensive error messages
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from memory.template_models import (
    BestPracticeTemplate,
    TemplateListAdapter,
    load_templates_from_file,
)


class TestBestPracticeTemplateValidation:
    """Test BestPracticeTemplate field validation."""

    def test_valid_template_minimal(self):
        """Test minimal valid template with required fields only."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
        )

        assert template.content == "Use type hints for better IDE support"
        assert template.domain == "python"
        assert template.type == "pattern"  # default
        assert template.importance == "medium"  # default
        assert template.tags == []  # default
        assert template.source is None  # default

    def test_valid_template_full(self):
        """Test fully specified valid template."""
        template = BestPracticeTemplate(
            content="Always use type hints in function signatures",
            type="pattern",
            domain="python",
            importance="high",
            tags=["python", "type-hints", "best-practice"],
            source="https://docs.python.org/3/library/typing.html",
        )

        assert template.content == "Always use type hints in function signatures"
        assert template.type == "pattern"
        assert template.domain == "python"
        assert template.importance == "high"
        assert template.tags == ["python", "type-hints", "best-practice"]
        assert template.source == "https://docs.python.org/3/library/typing.html"

    def test_content_too_short(self):
        """Test content validation - minimum length."""
        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content="Short",  # Only 5 chars, min is 10
                domain="python",
            )

        error = exc_info.value
        assert "content" in str(error)
        assert "at least 10 characters" in str(error)

    def test_content_too_long(self):
        """Test content validation - maximum length."""
        long_content = "x" * 2001  # Max is 2000

        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content=long_content,
                domain="python",
            )

        error = exc_info.value
        assert "content" in str(error)
        assert "at most 2000 characters" in str(error)

    def test_content_whitespace_stripped(self):
        """Test content whitespace normalization."""
        template = BestPracticeTemplate(
            content="  Use type hints  \n",
            domain="python",
        )

        assert template.content == "Use type hints"

    def test_domain_too_short(self):
        """Test domain validation - minimum length."""
        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content="Use type hints for better IDE support",
                domain="x",  # Only 1 char, min is 2
            )

        error = exc_info.value
        assert "domain" in str(error)
        assert "at least 2 characters" in str(error)

    def test_domain_lowercase_normalization(self):
        """Test domain normalized to lowercase."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="PYTHON",
        )

        assert template.domain == "python"

    def test_type_literal_validation(self):
        """Test type field only accepts valid literals."""
        # Valid types
        valid_types = ["pattern", "antipattern", "tip", "security", "performance"]

        for valid_type in valid_types:
            template = BestPracticeTemplate(
                content="Use type hints for better IDE support",
                domain="python",
                type=valid_type,
            )
            assert template.type == valid_type

        # Invalid type
        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content="Use type hints for better IDE support",
                domain="python",
                type="invalid_type",
            )

        error = exc_info.value
        assert "type" in str(error)

    def test_importance_literal_validation(self):
        """Test importance field only accepts valid literals."""
        # Valid importance levels
        valid_levels = ["high", "medium", "low"]

        for level in valid_levels:
            template = BestPracticeTemplate(
                content="Use type hints for better IDE support",
                domain="python",
                importance=level,
            )
            assert template.importance == level

        # Invalid importance
        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content="Use type hints for better IDE support",
                domain="python",
                importance="critical",
            )

        error = exc_info.value
        assert "importance" in str(error)


class TestContentInjectionPrevention:
    """Test security validators prevent injection attacks."""

    def test_content_script_tag_rejected(self):
        """Test <script> tags rejected in content."""
        dangerous_content = "Use this pattern: <script>alert('XSS')</script>"

        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content=dangerous_content,
                domain="python",
            )

        error = exc_info.value
        assert "dangerous pattern" in str(error).lower()
        assert "<script" in str(error)

    def test_content_javascript_protocol_rejected(self):
        """Test javascript: protocol rejected in content."""
        dangerous_content = "Click here: javascript:alert('XSS')"

        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content=dangerous_content,
                domain="python",
            )

        error = exc_info.value
        assert "dangerous pattern" in str(error).lower()
        assert "javascript:" in str(error)

    def test_content_eval_rejected(self):
        """Test eval() rejected in content."""
        dangerous_content = "Use this: eval(user_input)"

        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content=dangerous_content,
                domain="python",
            )

        error = exc_info.value
        assert "dangerous pattern" in str(error).lower()
        assert "eval(" in str(error)

    def test_content_template_injection_rejected(self):
        """Test template injection syntax rejected."""
        # Jinja2-style template injection
        dangerous_patterns = [
            "Use this: {{ user_input }}",
            "Execute: {% if condition %}",
        ]

        for pattern in dangerous_patterns:
            with pytest.raises(ValidationError) as exc_info:
                BestPracticeTemplate(
                    content=pattern,
                    domain="python",
                )

            error = exc_info.value
            assert "dangerous pattern" in str(error).lower()

    def test_content_safe_code_examples_allowed(self):
        """Test legitimate code examples are allowed."""
        safe_examples = [
            "Use json.loads() not eval() for parsing JSON",
            "Type hints example: def func(x: int) -> str:",
            "Docker command: docker run -p 8080:8080",
        ]

        for example in safe_examples:
            template = BestPracticeTemplate(
                content=example,
                domain="python",
            )
            assert template.content == example


class TestTagValidation:
    """Test tag validation and normalization."""

    def test_tags_empty_list_default(self):
        """Test tags default to empty list."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
        )

        assert template.tags == []

    def test_tags_normalized_lowercase(self):
        """Test tags normalized to lowercase."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
            tags=["Python", "Type-Hints", "BEST-PRACTICE"],
        )

        assert template.tags == ["python", "type-hints", "best-practice"]

    def test_tags_deduplicated(self):
        """Test duplicate tags removed."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
            tags=["python", "Python", "python", "type-hints"],
        )

        assert template.tags == ["python", "type-hints"]

    def test_tags_max_count(self):
        """Test maximum 10 tags enforced."""
        many_tags = [f"tag{i}" for i in range(11)]

        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content="Use type hints for better IDE support",
                domain="python",
                tags=many_tags,
            )

        error = exc_info.value
        assert "tags" in str(error)
        assert "at most 10" in str(error)

    def test_tags_max_length_per_tag(self):
        """Test individual tag max 50 chars."""
        long_tag = "x" * 51

        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content="Use type hints for better IDE support",
                domain="python",
                tags=["valid-tag", long_tag],
            )

        error = exc_info.value
        assert "Tag too long" in str(error)

    def test_tags_invalid_characters_rejected(self):
        """Test tags with invalid characters rejected."""
        invalid_tags = ["<script>", "tag{value}", "tag;drop"]

        for invalid_tag in invalid_tags:
            with pytest.raises(ValidationError) as exc_info:
                BestPracticeTemplate(
                    content="Use type hints for better IDE support",
                    domain="python",
                    tags=[invalid_tag],
                )

            error = exc_info.value
            assert "invalid characters" in str(error).lower()

    def test_tags_non_string_rejected(self):
        """Test non-string tags rejected.

        Note: Pydantic v2 validates list item types BEFORE field_validator runs,
        so we get a Pydantic type error, not our custom validation error.
        """
        with pytest.raises(ValidationError) as exc_info:
            BestPracticeTemplate(
                content="Use type hints for better IDE support",
                domain="python",
                tags=["valid", 123, "another"],  # type: ignore
            )

        error = exc_info.value
        # Pydantic v2 error: "Input should be a valid string"
        assert "should be a valid string" in str(error).lower()


class TestSourceURLValidation:
    """Test source URL validation."""

    def test_source_none_allowed(self):
        """Test source can be None."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
            source=None,
        )

        assert template.source is None

    def test_source_https_valid(self):
        """Test HTTPS URL accepted."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
            source="https://docs.python.org/3/library/typing.html",
        )

        assert template.source == "https://docs.python.org/3/library/typing.html"

    def test_source_http_valid(self):
        """Test HTTP URL accepted."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
            source="http://example.com/docs",
        )

        assert template.source == "http://example.com/docs"

    def test_source_invalid_protocol_rejected(self):
        """Test non-HTTP(S) protocols rejected."""
        invalid_sources = [
            "ftp://example.com/file",
            "file:///local/path",
            "javascript:alert('XSS')",
            "www.example.com",  # Missing protocol
        ]

        for invalid_source in invalid_sources:
            with pytest.raises(ValidationError) as exc_info:
                BestPracticeTemplate(
                    content="Use type hints for better IDE support",
                    domain="python",
                    source=invalid_source,
                )

            error = exc_info.value
            assert "valid HTTP(S) URL" in str(error)

    def test_source_whitespace_stripped(self):
        """Test source URL whitespace stripped."""
        template = BestPracticeTemplate(
            content="Use type hints for better IDE support",
            domain="python",
            source="  https://docs.python.org  \n",
        )

        assert template.source == "https://docs.python.org"


class TestLoadTemplatesFromFile:
    """Test load_templates_from_file() function."""

    def test_load_valid_json_file(self, tmp_path: Path):
        """Test loading valid JSON file with templates."""
        json_file = tmp_path / "test_templates.json"

        templates_data = [
            {
                "content": "Use type hints for better IDE support",
                "domain": "python",
                "type": "pattern",
                "importance": "high",
                "tags": ["python", "type-hints"],
                "source": "https://docs.python.org",
            },
            {
                "content": "Never use eval() for JSON parsing",
                "domain": "python",
                "type": "security",
                "importance": "high",
                "tags": ["python", "security"],
            },
        ]

        json_file.write_text(json.dumps(templates_data))

        templates = load_templates_from_file(json_file)

        assert len(templates) == 2
        assert all(isinstance(t, BestPracticeTemplate) for t in templates)
        assert templates[0].content == "Use type hints for better IDE support"
        assert templates[1].type == "security"

    def test_load_file_not_found(self, tmp_path: Path):
        """Test FileNotFoundError when file doesn't exist."""
        missing_file = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError) as exc_info:
            load_templates_from_file(missing_file)

        error = str(exc_info.value)
        assert "not found" in error.lower()
        assert str(missing_file) in error

    def test_load_invalid_json(self, tmp_path: Path):
        """Test ValueError when JSON is malformed."""
        json_file = tmp_path / "invalid.json"
        json_file.write_text("{ this is not valid JSON }")

        with pytest.raises(ValueError) as exc_info:
            load_templates_from_file(json_file)

        error = str(exc_info.value)
        assert "Failed to validate" in error
        assert json_file.name in error

    def test_load_invalid_template_data(self, tmp_path: Path):
        """Test ValueError when template validation fails."""
        json_file = tmp_path / "invalid_template.json"

        # Missing required 'domain' field
        invalid_data = [
            {
                "content": "Use type hints",
                # Missing 'domain' (required field)
            }
        ]

        json_file.write_text(json.dumps(invalid_data))

        with pytest.raises(ValueError) as exc_info:
            load_templates_from_file(json_file)

        error = str(exc_info.value)
        assert "Failed to validate" in error
        assert json_file.name in error

    def test_load_injection_attack_rejected(self, tmp_path: Path):
        """Test injection attacks in JSON rejected."""
        json_file = tmp_path / "dangerous.json"

        dangerous_data = [
            {
                "content": "Click here: <script>alert('XSS')</script>",
                "domain": "python",
            }
        ]

        json_file.write_text(json.dumps(dangerous_data))

        with pytest.raises(ValueError) as exc_info:
            load_templates_from_file(json_file)

        error = str(exc_info.value)
        assert "Failed to validate" in error
        assert "dangerous pattern" in str(error).lower()

    def test_load_empty_json_array(self, tmp_path: Path):
        """Test loading empty JSON array returns empty list."""
        json_file = tmp_path / "empty.json"
        json_file.write_text("[]")

        templates = load_templates_from_file(json_file)

        assert templates == []


class TestTypeAdapter:
    """Test Pydantic v2 TypeAdapter usage."""

    def test_type_adapter_validate_json(self):
        """Test TypeAdapter.validate_json() works correctly."""
        json_data = """
        [
            {
                "content": "Use type hints for better IDE support",
                "domain": "python",
                "type": "pattern",
                "importance": "high"
            }
        ]
        """

        templates = TemplateListAdapter.validate_json(json_data)

        assert len(templates) == 1
        assert isinstance(templates[0], BestPracticeTemplate)
        assert templates[0].content == "Use type hints for better IDE support"

    def test_type_adapter_invalid_json(self):
        """Test TypeAdapter raises error on invalid JSON."""
        invalid_json = "{ not valid JSON }"

        with pytest.raises(Exception):
            TemplateListAdapter.validate_json(invalid_json)
