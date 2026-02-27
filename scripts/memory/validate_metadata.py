#!/usr/bin/env python3
"""
Metadata Validation for AI Memory System

Implements metadata validation with JSON schema enforcement for all memory types.

Validates metadata for memory types across 3 v2.0 collections:
- code-patterns: implementation, error_fix, refactor, file_pattern
- conventions: guideline, anti_pattern, decision
- discussions: session, conversation, analysis, reflection, context, decision_record, lesson_learned

Usage:
    # As module
    from validate_metadata import validate_metadata_complete
    is_valid, errors = validate_metadata_complete(metadata)

    # As CLI
    python validate_metadata.py --metadata metadata.json
    python validate_metadata.py --metadata metadata.json --strict

Created: 2026-01-17
Updated: 2026-01-17 (v2.0 compliance)
Adapted from proven patterns for AI Memory Module
"""

import argparse
import json
import re
import sys
from typing import Any

# Required metadata fields for ALL memory types
REQUIRED_FIELDS = [
    "type",
    "group_id",
    "source_hook",
]

# Optional fields
OPTIONAL_FIELDS = [
    "unique_id",
    "agent",
    "component",
    "story_id",
    "importance",
    "created_at",
    "session_id",
]

# All valid memory types (v2.0 - all 3 collections)
VALID_TYPES = [
    # code-patterns collection (HOW)
    "implementation",
    "error_fix",
    "refactor",
    "file_pattern",
    # conventions collection (WHAT)
    "guideline",
    "anti_pattern",
    "decision",
    # discussions collection (WHY)
    "session",
    "conversation",
    "analysis",
    "reflection",
    "context",
    "decision_record",
    "lesson_learned",
]

VALID_IMPORTANCE = ["critical", "high", "medium", "low"]

# Valid agents from BMAD
VALID_AGENTS = [
    "architect",
    "analyst",
    "pm",
    "dev",
    "tea",
    "tech-writer",
    "ux-designer",
    "quick-flow-solo-dev",
    "sm",
]

# Valid source hooks
VALID_SOURCE_HOOKS = [
    "SessionStart",
    "PostToolUse",
    "PreToolUse",
    "PreCompact",
    "Stop",
    "manual",
    "pre-work-search",
    "post-work-store",
    "store-chat-memory",
    "load-chat-context",
]

# Security: Limits to prevent attacks
MAX_JSON_DEPTH = 100
MAX_JSON_SIZE = 1_000_000  # 1MB


def validate_json_safety(obj: Any, depth: int = 0) -> tuple[bool, list[str]]:
    """
    Validate JSON structure is safe (not too deep).

    Security validation

    Returns:
        (is_valid, errors)
    """
    if depth > MAX_JSON_DEPTH:
        return False, [
            f"JSON too deeply nested (max: {MAX_JSON_DEPTH} levels). "
            f"This prevents ReDoS attacks."
        ]

    if isinstance(obj, dict):
        for key, value in obj.items():
            is_valid, errors = validate_json_safety(value, depth + 1)
            if not is_valid:
                return False, errors
    elif isinstance(obj, list):
        for item in obj:
            is_valid, errors = validate_json_safety(item, depth + 1)
            if not is_valid:
                return False, errors

    return True, []


def validate_required_fields(metadata: dict) -> tuple[bool, list[str]]:
    """
    Validate all required fields are present.
    """
    errors = []
    missing = [f for f in REQUIRED_FIELDS if f not in metadata]

    if missing:
        errors.append(f"Missing required fields: {', '.join(missing)}")

    return len(errors) == 0, errors


def validate_type(metadata: dict) -> tuple[bool, list[str]]:
    """Validate memory type is valid."""
    errors = []
    memory_type = metadata.get("type", "")

    if not memory_type:
        errors.append("Missing type field")
    elif memory_type not in VALID_TYPES:
        errors.append(
            f"Invalid type '{memory_type}'. Must be one of: {', '.join(VALID_TYPES)}"
        )

    return len(errors) == 0, errors


def validate_importance(metadata: dict) -> tuple[bool, list[str]]:
    """Validate importance level (if provided)."""
    errors = []
    importance = metadata.get("importance", "")

    if importance and importance not in VALID_IMPORTANCE:
        errors.append(
            f"Invalid importance '{importance}'. Must be: {', '.join(VALID_IMPORTANCE)}"
        )

    return len(errors) == 0, errors


def validate_agent(metadata: dict) -> tuple[bool, list[str]]:
    """Validate agent field (if provided)."""
    errors = []
    warnings = []
    agent = metadata.get("agent", "")

    if agent and agent not in VALID_AGENTS:
        warnings.append(
            f"Agent '{agent}' not in standard list: {', '.join(VALID_AGENTS)}"
        )

    return True, warnings  # Just warnings, not blocking


def validate_source_hook(metadata: dict) -> tuple[bool, list[str]]:
    """Validate source_hook field."""
    errors = []
    source_hook = metadata.get("source_hook", "")

    if not source_hook:
        errors.append("Missing source_hook field")
    elif source_hook not in VALID_SOURCE_HOOKS:
        # Warning only - allow custom hooks
        pass

    return len(errors) == 0, errors


def validate_group_id(metadata: dict) -> tuple[bool, list[str]]:
    """Validate group_id for multitenancy."""
    errors = []
    group_id = metadata.get("group_id", "")

    if not group_id:
        errors.append("Missing group_id field - required for multitenancy")
    elif len(group_id) < 3:
        errors.append(f"group_id '{group_id}' too short (min 3 characters)")

    return len(errors) == 0, errors


def validate_unique_id(metadata: dict) -> tuple[bool, list[str]]:
    """Validate unique_id format (if provided)."""
    errors = []
    warnings = []
    unique_id = metadata.get("unique_id", "")
    memory_type = metadata.get("type", "")

    if not unique_id:
        return True, []  # unique_id is optional

    if len(unique_id) < 5:
        errors.append(f"unique_id '{unique_id}' too short (min 5 characters)")

    # Expected prefixes for each type
    expected_prefixes = {
        "implementation": ["impl-"],
        "architecture_decision": ["arch-", "arch-decision-"],
        "story_outcome": ["story-"],
        "error_pattern": ["error-"],
        "database_schema": ["schema-"],
        "config_pattern": ["config-"],
        "integration_example": ["integration-"],
        "best_practice": ["bp-"],
        "session_summary": ["session-"],
        "chat_memory": ["chat-"],
        "agent_decision": ["decision-"],
    }

    prefixes = expected_prefixes.get(memory_type, [])
    if prefixes:
        matches_prefix = any(unique_id.startswith(p) for p in prefixes)
        if not matches_prefix:
            warnings.append(
                f"unique_id '{unique_id}' doesn't follow expected format for "
                f"'{memory_type}'. Expected prefix: {' or '.join(prefixes)}"
            )

    return len(errors) == 0, errors + warnings


def validate_created_at(metadata: dict) -> tuple[bool, list[str]]:
    """Validate created_at format (ISO 8601) if provided."""
    errors = []
    created_at = metadata.get("created_at", "")

    if not created_at:
        return True, []  # Optional

    # Check ISO 8601 format (basic check)
    if not re.match(r"^\d{4}-\d{2}-\d{2}", created_at):
        errors.append(f"created_at '{created_at}' must be ISO 8601 format (YYYY-MM-DD)")

    return len(errors) == 0, errors


def validate_component(metadata: dict) -> tuple[bool, list[str]]:
    """Validate component field (if provided)."""
    errors = []
    component = metadata.get("component", "")

    if component and len(component) < 2:
        errors.append(f"component '{component}' too short (min 2 characters)")

    return len(errors) == 0, errors


def validate_metadata_complete(metadata: dict) -> tuple[bool, dict]:
    """
    Complete metadata validation with all proven patterns.

    Metadata Validation - JSON schema enforcement

    Returns:
        (is_valid, details)
    """
    details = {
        "errors": [],
        "warnings": [],
        "checks_performed": [],
    }

    # Security: Check JSON size
    try:
        json_str = json.dumps(metadata)
        if len(json_str) > MAX_JSON_SIZE:
            details["errors"].append(
                f"Metadata too large ({len(json_str):,} bytes). "
                f"Maximum: {MAX_JSON_SIZE:,} bytes."
            )
            return False, details
    except (TypeError, ValueError) as e:
        details["errors"].append(f"Metadata not JSON serializable: {e}")
        return False, details

    # Security: Check JSON depth
    details["checks_performed"].append("json_safety")
    is_valid, errors = validate_json_safety(metadata)
    if not is_valid:
        details["errors"].extend(errors)
        return False, details

    # Required fields
    details["checks_performed"].append("required_fields")
    is_valid, errors = validate_required_fields(metadata)
    if not is_valid:
        details["errors"].extend(errors)

    # Type validation
    details["checks_performed"].append("type")
    is_valid, errors = validate_type(metadata)
    if not is_valid:
        details["errors"].extend(errors)

    # Importance validation
    details["checks_performed"].append("importance")
    is_valid, errors = validate_importance(metadata)
    if not is_valid:
        details["errors"].extend(errors)

    # Agent validation
    details["checks_performed"].append("agent")
    _, warnings = validate_agent(metadata)
    details["warnings"].extend(warnings)

    # source_hook validation
    details["checks_performed"].append("source_hook")
    is_valid, errors = validate_source_hook(metadata)
    if not is_valid:
        details["errors"].extend(errors)

    # group_id validation
    details["checks_performed"].append("group_id")
    is_valid, errors = validate_group_id(metadata)
    if not is_valid:
        details["errors"].extend(errors)

    # unique_id validation (optional)
    details["checks_performed"].append("unique_id")
    is_valid, messages = validate_unique_id(metadata)
    for msg in messages:
        if "too short" in msg.lower():
            details["errors"].append(msg)
        else:
            details["warnings"].append(msg)

    # created_at validation (optional)
    details["checks_performed"].append("created_at")
    is_valid, errors = validate_created_at(metadata)
    if not is_valid:
        details["errors"].extend(errors)

    # component validation (optional)
    details["checks_performed"].append("component")
    is_valid, errors = validate_component(metadata)
    if not is_valid:
        details["errors"].extend(errors)

    # Final result
    is_valid = len(details["errors"]) == 0
    return is_valid, details


def format_validation_results(is_valid: bool, details: dict) -> str:
    """Format validation results for display."""
    lines = [
        "\n" + "=" * 60,
        "METADATA VALIDATION RESULTS",
        "=" * 60,
        f"\nChecks performed: {', '.join(details['checks_performed'])}",
    ]

    if details["errors"]:
        lines.append("\n[FAIL] VALIDATION ERRORS:")
        for error in details["errors"]:
            lines.append(f"  - {error}")

    if details["warnings"]:
        lines.append("\n[WARNING] WARNINGS:")
        for warning in details["warnings"]:
            lines.append(f"  - {warning}")

    lines.append("\n" + "=" * 60)

    if is_valid:
        if details["warnings"]:
            lines.append("RESULT: [PASS] VALIDATION PASSED (with warnings)")
        else:
            lines.append("RESULT: [PASS] VALIDATION PASSED")
    else:
        lines.append("RESULT: [FAIL] VALIDATION FAILED")

    return "\n".join(lines)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate metadata for AI Memory system"
    )
    parser.add_argument(
        "--metadata", required=True, help="Path to metadata JSON file or JSON string"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on warnings (not just errors)",
    )

    args = parser.parse_args()

    # Load metadata (file path or JSON string)
    metadata_input = args.metadata

    if metadata_input.startswith("{"):
        # JSON string
        try:
            metadata = json.loads(metadata_input)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON string: {e}")
            sys.exit(1)
    else:
        # File path
        try:
            with open(metadata_input) as f:
                metadata = json.load(f)
        except FileNotFoundError:
            print(f"ERROR: Metadata file not found: {metadata_input}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in metadata file: {e}")
            sys.exit(1)

    # Run validation
    is_valid, details = validate_metadata_complete(metadata)

    # Print results
    print(format_validation_results(is_valid, details))

    # Exit code
    if not is_valid:
        sys.exit(1)
    elif args.strict and details["warnings"]:
        print("\n[WARNING] Strict mode: Failing due to warnings")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
