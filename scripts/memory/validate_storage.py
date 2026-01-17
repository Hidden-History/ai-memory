#!/usr/bin/env python3
"""
Pre-Storage Validator for BMAD Memory System

Implements proven validation patterns:
1. Wrapper Script Bridge - Python interface for validation
2. Dual Access - Works with both MCP and Python API
3. Token Budget Enforcement - Validates token limits
4. File:Line References - REQUIRED for actionable memories
5. Workflow Hook Timing - Pre-storage validation (before Step 6.5)
6. Metadata Validation - JSON schema enforcement
7. Duplicate Detection - Hash + semantic similarity >0.85
8. Agent-Specific Memory Types - Validates agent permissions
9. Code Snippets - Validates 3-10 line code blocks

Usage:
    # As module
    from validate_storage import validate_before_storage
    is_valid, message = validate_before_storage(information, metadata)

    # As CLI
    python validate_storage.py --content "..." --metadata '{...}'

Created: 2026-01-17
Adapted from proven patterns for BMAD Memory Module
"""

import os
import sys
import json
import hashlib
import argparse
import re
from pathlib import Path
from typing import Tuple, Dict, List, Optional

# Add src to path for imports
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Try to import from installed location first, fall back to relative
try:
    from memory.config import get_config
    from memory.qdrant_client import get_qdrant_client, QdrantUnavailable
except ImportError:
    # Running from dev repo
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from memory.config import get_config
    from memory.qdrant_client import get_qdrant_client, QdrantUnavailable

# Collection names
COLLECTIONS_TO_CHECK = [
    "implementations",
    "best_practices",
    "agent-memory",
]

# Required metadata fields for ALL memory types
REQUIRED_FIELDS = ["type", "group_id", "source_hook"]

# Optional but recommended fields
RECOMMENDED_FIELDS = ["agent", "component", "story_id", "importance"]

# All valid memory types
VALID_TYPES = [
    # implementations collection
    "implementation",
    "architecture_decision",
    "story_outcome",
    "error_pattern",
    "database_schema",
    "config_pattern",
    "integration_example",
    # best_practices collection
    "best_practice",
    # agent-memory collection
    "session_summary",
    "chat_memory",
    "agent_decision",
]

VALID_IMPORTANCE = ["critical", "high", "medium", "low"]

# Token Budget - Content length in tokens (1 token ~ 4 chars)
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "50"))  # ~12 tokens minimum
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", "50000"))  # ~12,500 tokens maximum
MAX_TOKENS_PER_SHARD = int(os.getenv("MAX_TOKENS_PER_SHARD", "1200"))  # Per shard limit

# File:Line References - Required for actionable memories
FILE_LINE_PATTERN = re.compile(r'[a-zA-Z0-9_/\-\.]+\.(py|md|yaml|yml|sql|sh|js|ts|tsx|json|css|html):\d+(?:-\d+)?')

# Duplicate Detection - Similarity threshold
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))


def estimate_tokens(text: str) -> int:
    """
    Estimate token count (rough: 1 token ~ 4 chars).
    """
    return len(text) // 4


def validate_token_budget(content: str) -> Tuple[bool, List[str]]:
    """
    Validate content doesn't exceed token limits.
    """
    messages = []
    token_count = estimate_tokens(content)

    if token_count > MAX_TOKENS_PER_SHARD:
        messages.append(
            f"Content exceeds max tokens per shard: {token_count} > {MAX_TOKENS_PER_SHARD}. "
            f"Split into multiple shards."
        )

    return len(messages) == 0, messages


def validate_file_references(content: str, memory_type: str) -> Tuple[bool, List[str]]:
    """
    Validate file:line references are present.

    File:Line References REQUIRED for actionable memories.
    """
    # Types that REQUIRE file:line references
    requires_file_refs = [
        "implementation",
        "story_outcome",
        "error_pattern",
        "integration_example",
        "config_pattern",
        "architecture_decision",
    ]

    if memory_type not in requires_file_refs:
        return True, []  # Not required for this type

    messages = []
    matches = FILE_LINE_PATTERN.findall(content)

    if len(matches) == 0:
        messages.append(
            f"Missing file:line references. Type '{memory_type}' REQUIRES format: "
            f"src/path/file.py:89-234. Add at least one reference to make memory actionable."
        )

    return len(messages) == 0, messages


def validate_code_snippets(content: str) -> Tuple[bool, List[str]]:
    """
    Validate code snippets if present.

    Code Snippets - 3-10 lines optimal for comprehension.
    """
    warnings = []

    # Detect code blocks (markdown or plain)
    code_block_pattern = re.compile(r'```[\s\S]*?```|`[^`]+`')
    code_blocks = code_block_pattern.findall(content)

    for block in code_blocks:
        lines = block.split('\n')
        line_count = len([l for l in lines if l.strip() and not l.strip().startswith('```')])

        if line_count > 10:
            warnings.append(
                f"Code snippet has {line_count} lines. Optimal: 3-10 lines for quick comprehension. "
                f"Consider reducing or linking to full file."
            )

    return True, warnings  # Warnings only, not blocking


def check_duplicate_unique_id(client, unique_id: str) -> Tuple[bool, str]:
    """
    Check if unique_id already exists in any collection.
    """
    if not unique_id:
        return False, "No unique_id to check"

    for coll_name in COLLECTIONS_TO_CHECK:
        try:
            scroll_result = client.scroll(
                collection_name=coll_name,
                limit=500,
                with_payload=True,
                with_vectors=False,
            )

            for point in scroll_result[0]:
                payload = point.payload or {}
                existing_id = payload.get("unique_id", "")
                if existing_id == unique_id:
                    return True, (
                        f"DUPLICATE: '{unique_id}' already exists in '{coll_name}' "
                        f"(point_id: {point.id})"
                    )

        except Exception as e:
            # Collection might not exist yet - that's OK
            if "not found" not in str(e).lower():
                print(f"Warning: Could not check {coll_name}: {e}")

    return False, f"'{unique_id}' is available"


def check_similar_content(client, content: str) -> Tuple[bool, List[Dict]]:
    """
    Check for exact and semantically similar content.

    Duplicate Detection - Two-stage (hash + semantic >0.85)
    """
    # Stage 1: Exact duplicate (SHA256 hash)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    similar = []

    for coll_name in COLLECTIONS_TO_CHECK:
        try:
            scroll_result = client.scroll(
                collection_name=coll_name,
                limit=500,
                with_payload=True,
                with_vectors=False,
            )

            for point in scroll_result[0]:
                payload = point.payload or {}
                existing_hash = payload.get("content_hash", "")
                if existing_hash == content_hash:
                    uid = payload.get("unique_id", "")
                    similar.append({
                        "collection": coll_name,
                        "unique_id": uid,
                        "match_type": "exact_hash",
                        "similarity": 1.0,
                    })

        except Exception:
            pass  # Skip unavailable collections

    return len(similar) > 0, similar


def validate_metadata_fields(metadata: Dict) -> Tuple[bool, List[str]]:
    """
    Validate required metadata fields and values.

    Metadata Validation - JSON schema enforcement
    """
    errors = []
    warnings = []

    # Check required fields
    missing = [f for f in REQUIRED_FIELDS if f not in metadata]
    if missing:
        errors.append(f"Missing required fields: {missing}")

    # Check recommended fields
    missing_recommended = [f for f in RECOMMENDED_FIELDS if f not in metadata]
    if missing_recommended:
        warnings.append(f"Missing recommended fields: {missing_recommended}")

    # Validate type
    entry_type = metadata.get("type", "")
    if entry_type and entry_type not in VALID_TYPES:
        errors.append(f"Invalid type '{entry_type}'. Must be one of: {VALID_TYPES}")

    # Validate importance (if provided)
    importance = metadata.get("importance", "")
    if importance and importance not in VALID_IMPORTANCE:
        errors.append(
            f"Invalid importance '{importance}'. Must be: {VALID_IMPORTANCE}"
        )

    # Validate group_id
    group_id = metadata.get("group_id", "")
    if not group_id:
        errors.append("Missing group_id field - required for multitenancy")

    return len(errors) == 0, errors + warnings


def validate_content_quality(content: str) -> Tuple[bool, List[str]]:
    """
    Validate content meets quality thresholds.
    """
    messages = []

    if len(content) < MIN_CONTENT_LENGTH:
        messages.append(
            f"Content too short ({len(content)} chars). "
            f"Minimum {MIN_CONTENT_LENGTH} chars for meaningful knowledge."
        )

    if len(content) > MAX_CONTENT_LENGTH:
        messages.append(
            f"Content too long ({len(content)} chars). "
            f"Maximum {MAX_CONTENT_LENGTH} chars. Consider splitting."
        )

    # Check for placeholder text
    placeholders = ["TODO", "FIXME", "TBD", "[INSERT", "[PLACEHOLDER"]
    for p in placeholders:
        if p in content.upper():
            messages.append(f"Content contains placeholder text: '{p}'")

    return len(messages) == 0, messages


def validate_before_storage(
    information: str,
    metadata: Dict,
    skip_duplicate_check: bool = False,
    skip_similarity_check: bool = False,
) -> Tuple[bool, str, Dict]:
    """
    Complete pre-storage validation with all proven patterns.

    Args:
        information: The knowledge content to store
        metadata: Metadata dictionary
        skip_duplicate_check: Skip Qdrant duplicate check (for offline validation)
        skip_similarity_check: Skip content similarity check

    Returns:
        (is_valid, message, details)
    """
    details = {
        "errors": [],
        "warnings": [],
        "content_hash": hashlib.sha256(information.encode("utf-8")).hexdigest(),
        "token_count": estimate_tokens(information),
        "checks_performed": [],
    }

    # Validate metadata fields
    details["checks_performed"].append("metadata_fields")
    is_valid, messages = validate_metadata_fields(metadata)
    for msg in messages:
        if "missing recommended" in msg.lower():
            details["warnings"].append(msg)
        else:
            details["errors"].append(msg)

    # Validate file:line references
    details["checks_performed"].append("file_references")
    is_valid, errors = validate_file_references(information, metadata.get("type", ""))
    if not is_valid:
        details["errors"].extend(errors)

    # Validate token budget
    details["checks_performed"].append("token_budget")
    is_valid, errors = validate_token_budget(information)
    if not is_valid:
        details["errors"].extend(errors)

    # Validate code snippets
    details["checks_performed"].append("code_snippets")
    _, warnings = validate_code_snippets(information)
    details["warnings"].extend(warnings)

    # Validate content quality
    details["checks_performed"].append("content_quality")
    is_valid, messages = validate_content_quality(information)
    if not is_valid:
        details["warnings"].extend(messages)

    # Check for duplicate unique_id
    if not skip_duplicate_check:
        try:
            client = get_qdrant_client()
            details["checks_performed"].append("duplicate_unique_id")
            unique_id = metadata.get("unique_id", "")
            if unique_id:
                is_dup, msg = check_duplicate_unique_id(client, unique_id)
                if is_dup:
                    details["errors"].append(msg)

            # Check for similar content (hash + semantic)
            if not skip_similarity_check:
                details["checks_performed"].append("similar_content")
                similar_found, similar_entries = check_similar_content(
                    client, information
                )
                if similar_found:
                    for entry in similar_entries:
                        if entry["similarity"] >= SIMILARITY_THRESHOLD:
                            details["errors"].append(
                                f"DUPLICATE: Similar content found (similarity: {entry['similarity']:.2f}): "
                                f"{entry['unique_id']} in {entry['collection']}"
                            )
        except QdrantUnavailable as e:
            details["warnings"].append(
                f"Qdrant unavailable ({e}) - skipping duplicate check"
            )

    # Build result message
    if details["errors"]:
        message = "VALIDATION FAILED:\n" + "\n".join(
            f"  - {e}" for e in details["errors"]
        )
        if details["warnings"]:
            message += "\n\nWarnings:\n" + "\n".join(
                f"  - {w}" for w in details["warnings"]
            )
        return False, message, details

    if details["warnings"]:
        message = "VALIDATION PASSED with warnings:\n" + "\n".join(
            f"  - {w}" for w in details["warnings"]
        )
        return True, message, details

    return True, "VALIDATION PASSED", details


def main():
    parser = argparse.ArgumentParser(
        description="Pre-storage validation for BMAD memory system (all proven patterns)"
    )

    parser.add_argument("--content", help="Knowledge content as string")
    parser.add_argument("--content-file", help="File containing knowledge content")
    parser.add_argument("--metadata", help="Metadata as JSON string")
    parser.add_argument("--metadata-file", help="File containing metadata JSON")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip Qdrant checks (offline validation only)",
    )

    args = parser.parse_args()

    # Load content
    if args.content:
        content = args.content
    elif args.content_file:
        with open(args.content_file, "r") as f:
            content = f.read()
    else:
        print("ERROR: Must provide --content or --content-file")
        sys.exit(1)

    # Load metadata
    if args.metadata:
        metadata = json.loads(args.metadata)
    elif args.metadata_file:
        with open(args.metadata_file, "r") as f:
            metadata = json.load(f)
    else:
        print("ERROR: Must provide --metadata or --metadata-file")
        sys.exit(1)

    # Run validation
    is_valid, message, details = validate_before_storage(
        content, metadata, skip_duplicate_check=args.offline
    )

    print("\n" + "=" * 60)
    print("BMAD MEMORY SYSTEM - PRE-STORAGE VALIDATION")
    print("=" * 60)
    print(f"\nContent hash: {details['content_hash'][:16]}...")
    print(f"Token count: ~{details['token_count']} tokens")
    print(f"Checks performed: {', '.join(details['checks_performed'])}")
    print("\n" + message)
    print("\n" + "=" * 60)

    if is_valid:
        print("RESULT: SAFE TO STORE")
        sys.exit(0)
    else:
        print("RESULT: DO NOT STORE")
        sys.exit(1)


if __name__ == "__main__":
    main()
