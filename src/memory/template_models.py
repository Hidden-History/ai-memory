"""Pydantic models for best practice template validation.

2026 Best Practices Applied:
- Pydantic v2 TypeAdapter for JSON validation
- Field validators for security (injection prevention)
- Type-safe template structure
- Comprehensive validation error messages

Sources:
- Pydantic TypeAdapter: https://docs.pydantic.dev/latest/concepts/type_adapter/
- JSON Security: https://www.invicti.com/learn/json-injection
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

__all__ = ["BestPracticeTemplate", "load_templates_from_file"]


class BestPracticeTemplate(BaseModel):
    """Template for best practice memory seeding.

    Attributes:
        content: The actual best practice text (max 2000 chars)
        type: Category of best practice (V2.0 spec: rule, guideline, port, naming, structure)
        domain: Technology domain (python, docker, git, etc.)
        importance: Priority level for this practice
        tags: List of searchable tags (max 10 tags, each max 50 chars)
        source: Optional reference to documentation/article
        source_date: When the source was published (ISO 8601, e.g. 2026-01-15)
        last_verified: When this practice was last verified as accurate

    Example:
        >>> template = BestPracticeTemplate(
        ...     content="Always use type hints in function signatures",
        ...     type="guideline",
        ...     domain="python",
        ...     importance="high",
        ...     tags=["python", "type-hints", "best-practice"],
        ...     source="https://peps.python.org/pep-0484/",
        ...     source_date="2014-09-29",  # TECH-DEBT-028: When published
        ...     last_verified="2026-01-15"  # TECH-DEBT-028: When verified
        ... )
    """

    content: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Best practice text content",
    )

    type: Literal["rule", "guideline", "port", "naming", "structure"] = Field(
        default="guideline",
        description="Category of best practice (V2.0 conventions types)",
    )

    domain: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Technology domain (python, docker, git, typescript, etc.)",
    )

    importance: Literal["high", "medium", "low"] = Field(
        default="medium",
        description="Priority level for this practice",
    )

    tags: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Searchable tags (max 10)",
    )

    source: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reference URL or citation",
    )

    # Timestamp fields (TECH-DEBT-028)
    source_date: datetime | None = Field(
        default=None,
        description="When the source was published (ISO 8601, e.g. 2026-01-15)",
    )

    last_verified: datetime | None = Field(
        default=None,
        description="When this practice was last verified as accurate",
    )

    @field_validator("source_date", "last_verified", mode="before")
    @classmethod
    def parse_datetime_field(cls, v):
        """Parse datetime fields from strings or datetime objects.

        2026 Pattern: Use datetime.fromisoformat() for parsing
        Supports: YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, YYYY-MM-DDTHH:MM:SSZ

        Args:
            v: datetime object, ISO string, or None

        Returns:
            datetime object or None

        Raises:
            ValueError: If date format is invalid
        """
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            # Support YYYY-MM-DD format and ISO datetime with Z suffix
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError(f"Invalid date format: {v}")

    @field_validator("content")
    @classmethod
    def validate_content_safe(cls, v: str) -> str:
        """Prevent injection attacks in content field.

        Security: 2026 best practice per OWASP JSON injection prevention
        Source: https://www.invicti.com/learn/json-injection

        Note: We allow mentioning dangerous patterns in educational context
        (e.g., "Never use eval()") but reject actual usage patterns.
        """
        # Check for suspicious patterns that could indicate injection attempts
        dangerous_patterns = [
            "<script",
            "javascript:",
            "{{",  # Template injection
            "{%",  # Template injection
        ]
        content_lower = v.lower()

        for pattern in dangerous_patterns:
            if pattern in content_lower:
                raise ValueError(
                    f"Content contains potentially dangerous pattern: {pattern}. "
                    "Templates must not contain executable code or template injection syntax."
                )

        # Special check for eval() - reject only if used without negation context
        # Allow: "Don't use eval()", "Never use eval()", "Avoid eval()"
        # Reject: "Use eval(" (suggesting actual usage)
        if "eval(" in content_lower:
            # Check if eval appears in negative context
            eval_index = content_lower.find("eval(")
            context_start = max(0, eval_index - 30)
            context = content_lower[context_start : eval_index + 10]

            negative_indicators = [
                "never",
                "don't",
                "do not",
                "avoid",
                "not",
                "instead of",
            ]

            has_negative_context = any(
                indicator in context for indicator in negative_indicators
            )

            if not has_negative_context:
                raise ValueError(
                    "Content contains potentially dangerous pattern: eval(. "
                    "Templates must not contain executable code or template injection syntax."
                )

        return v.strip()

    @field_validator("domain")
    @classmethod
    def validate_domain_lowercase(cls, v: str) -> str:
        """Normalize domain to lowercase for consistency."""
        return v.lower().strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate and normalize tags.

        Security: Prevent tag injection, ensure consistent formatting
        """
        if not v:
            return []

        # Validate each tag
        validated_tags = []
        for tag in v:
            if not isinstance(tag, str):
                raise ValueError(f"Tag must be string, got {type(tag)}")

            tag = tag.lower().strip()

            # Length check
            if len(tag) > 50:
                raise ValueError(f"Tag too long (max 50 chars): {tag[:50]}...")

            # No special characters that could cause issues
            if any(char in tag for char in ["<", ">", "{", "}", ";"]):
                raise ValueError(f"Tag contains invalid characters: {tag}")

            validated_tags.append(tag)

        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in validated_tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)

        return unique_tags

    @field_validator("source")
    @classmethod
    def validate_source_url(cls, v: str | None) -> str | None:
        """Validate source URL if provided."""
        if v is None:
            return None

        v = v.strip()

        # Basic URL validation
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"Source must be a valid HTTP(S) URL, got: {v[:50]}...")

        return v


# TypeAdapter for loading lists of templates from JSON
TemplateListAdapter = TypeAdapter(list[BestPracticeTemplate])


def load_templates_from_file(file_path: Path) -> list[BestPracticeTemplate]:
    """Load and validate templates from a JSON file.

    2026 Pattern: Use Pydantic v2 TypeAdapter for JSON validation
    Source: https://docs.pydantic.dev/latest/concepts/type_adapter/

    Args:
        file_path: Path to JSON file containing template array

    Returns:
        List of validated BestPracticeTemplate instances

    Raises:
        FileNotFoundError: If template file doesn't exist
        ValueError: If JSON is invalid or validation fails

    Example:
        >>> templates = load_templates_from_file(Path("templates/python.json"))
        >>> len(templates)
        5
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Template file not found: {file_path}")

    # Read JSON file
    json_content = file_path.read_text(encoding="utf-8")

    # Validate using TypeAdapter (2026 best practice)
    try:
        templates = TemplateListAdapter.validate_json(json_content)
    except Exception as e:
        raise ValueError(
            f"Failed to validate templates from {file_path.name}: {e}"
        ) from e

    return templates
