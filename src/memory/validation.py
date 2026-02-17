"""Payload validation for memory storage.

Validates memory payloads before storage in Qdrant.
Implements Story 1.3 AC 1.3.3.
"""

import hashlib

from .models import MemoryType

__all__ = ["ValidationError", "compute_content_hash", "validate_payload"]


class ValidationError(Exception):
    """Raised when payload validation fails.

    Design Note: This exception is provided for callers who prefer exception-based
    flow control. The validate_payload() function returns a list of errors instead
    of raising, allowing callers to collect all validation errors at once. Callers
    can raise ValidationError manually if desired:

        errors = validate_payload(payload)
        if errors:
            raise ValidationError(f"Validation failed: {errors}")
    """

    pass


def validate_payload(payload: dict) -> list[str]:
    """Validate memory payload, return list of errors.

    Args:
        payload: Dictionary containing memory payload fields

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Required fields
    required = ["content", "group_id", "type", "source_hook"]
    for field_name in required:
        if field_name not in payload or not payload[field_name]:
            errors.append(f"Missing required field: {field_name}")

    # Content constraints
    if "content" in payload:
        content_len = len(payload["content"])
        if content_len > 100000:
            errors.append("Content exceeds maximum length (100,000 chars)")
        if content_len < 10:
            errors.append("Content too short (minimum 10 chars)")

    # Type validation (only if field is present and non-empty)
    # v2.0 spec types (14 total - MEMORY-SYSTEM-REDESIGN-v2.md Section 5)
    # Extract valid types from MemoryType enum (single source of truth)
    valid_types = [t.value for t in MemoryType]
    if "type" in payload and payload["type"] and payload.get("type") not in valid_types:
        errors.append(f"Invalid type. Must be one of: {valid_types}")

    # Hook validation (only if field is present and non-empty)
    # V2.0 hooks per Core-Architecture-Principle-V2.md:
    # - PostToolUse: post_tool_capture.py (code patterns)
    # - Stop: stop_capture.py (agent responses)
    # - SessionStart: session_start.py (context injection - read-only, but valid source)
    # - UserPromptSubmit: user_prompt_capture.py (user messages, decision/best-practice triggers)
    # - PreCompact: pre_compact_save.py (session summaries)
    # - PreToolUse: new_file_trigger.py, first_edit_trigger.py (convention triggers)
    # - seed_script: seed_best_practices.py (convention seeding)
    # - manual: skill-based or API-driven storage (Story 4.3)
    valid_hooks = [
        "PostToolUse",
        "Stop",
        "SessionStart",
        "UserPromptSubmit",
        "PreCompact",
        "PreToolUse",
        "seed_script",
        "manual",
        "jira_sync",  # Jira connector sync (v2.0.5)
        "github_sync",  # GitHub connector sync (v2.0.6)
        "github_code_sync",  # GitHub code blob sync (v2.0.6)
        "SDKWrapper",  # SDK-based conversation capture
        "agent:subagent",  # Agent-triggered storage
        "parzival_agent",  # Parzival session agent (SPEC-015)
    ]
    if (
        "source_hook" in payload
        and payload["source_hook"]
        and payload.get("source_hook") not in valid_hooks
    ):
        errors.append(f"Invalid source_hook. Must be one of: {valid_hooks}")

    return errors


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content for deduplication.

    Args:
        content: The content string to hash

    Returns:
        SHA256 hash as 64-character hex string
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
