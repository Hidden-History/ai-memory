#!/usr/bin/env python3
"""
Post-Work Storage Hook for BMAD Workflows

Stores implementation memories after story completion or significant work milestones.
Designed for BMAD workflow integration with non-blocking background storage.

Requirements:
1. Accept content via stdin or --content-file
2. Accept metadata via --metadata JSON (type, agent, component, story_id, importance)
3. Use MemoryStorage class from src/memory/storage.py
4. Call validate_storage.py logic before storing
5. Skip duplicates using check_duplicates.py logic
6. Add file:line references validation for implementation types
7. Fork background process for actual storage (non-blocking)
8. Exit 0 immediately after forking

Usage:
    # Via stdin
    echo "Implementation content" | python post-work-store.py --metadata '{"type":"implementation",...}'

    # Via file
    python post-work-store.py --content-file content.txt --metadata-file metadata.json

    # Background storage (non-blocking)
    python post-work-store.py --content-file content.txt --metadata '{"type":"implementation"}' &

Exit Codes:
- 0: Success (forked to background or validation passed)
- 1: Validation failed or critical error (blocking)

Created: 2026-01-17
Follows patterns from validate_storage.py and check_duplicates.py
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Add src to path for imports
# Try dev repo FIRST, then fall back to installed location
dev_src = Path(__file__).parent.parent.parent / "src"
if dev_src.exists():
    sys.path.insert(0, str(dev_src))
else:
    INSTALL_DIR = os.environ.get(
        "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
    )
    sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.logging_config import StructuredFormatter
from memory.qdrant_client import QdrantUnavailable

# Import validation and duplicate detection modules
try:
    from check_duplicates import check_for_duplicates
    from validate_storage import validate_before_storage
except ImportError:
    # Running from dev repo - use absolute path
    scripts_dir = Path(__file__).parent
    sys.path.insert(0, str(scripts_dir))
    from check_duplicates import check_for_duplicates
    from validate_storage import validate_before_storage

# Configure structured logging
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.post_work_store")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Metadata defaults
DEFAULT_SOURCE_HOOK = (
    "manual"  # "manual" is for skill-based and workflow-driven storage
)
DEFAULT_SESSION_ID = "workflow"

# Required metadata fields
REQUIRED_METADATA_FIELDS = ["type", "group_id", "source_hook"]

# Recommended metadata fields for BMAD workflows
RECOMMENDED_METADATA_FIELDS = ["agent", "component", "story_id", "importance"]


def validate_metadata(metadata: dict[str, Any]) -> tuple[bool, str]:
    """
    Validate metadata structure and required fields.

    Args:
        metadata: Metadata dictionary to validate

    Returns:
        (is_valid, error_message)
    """
    # Check required fields
    missing_required = [f for f in REQUIRED_METADATA_FIELDS if f not in metadata]
    if missing_required:
        return False, f"Missing required metadata fields: {missing_required}"

    # Check recommended fields (warning only)
    missing_recommended = [f for f in RECOMMENDED_METADATA_FIELDS if f not in metadata]
    if missing_recommended:
        logger.warning(
            "missing_recommended_fields", extra={"fields": missing_recommended}
        )

    # Validate type field
    valid_types = [
        "implementation",
        "architecture_decision",
        "story_outcome",
        "error_pattern",
        "database_schema",
        "config_pattern",
        "integration_example",
        "best_practice",
        "session_summary",
        "chat_memory",
        "agent_decision",
    ]
    if metadata.get("type") not in valid_types:
        return (
            False,
            f"Invalid type '{metadata.get('type')}'. Must be one of: {valid_types}",
        )

    # Validate importance if provided
    if "importance" in metadata:
        valid_importance = ["critical", "high", "medium", "low"]
        if metadata["importance"] not in valid_importance:
            return (
                False,
                f"Invalid importance '{metadata['importance']}'. Must be: {valid_importance}",
            )

    return True, ""


def fork_background_storage(content: str, metadata: dict[str, Any]) -> None:
    """
    Fork the actual storage operation to a background process.

    This ensures the calling workflow is not blocked by network I/O.
    Uses subprocess.Popen with start_new_session=True for full detachment.

    Args:
        content: Memory content to store
        metadata: Validated metadata dictionary
    """
    try:
        # Path to background storage script
        script_dir = Path(__file__).parent
        background_script = script_dir / "post_work_store_async.py"

        # Prepare payload for background process
        payload = {
            "content": content,
            "metadata": metadata,
        }
        payload_json = json.dumps(payload)

        # Fork to background using subprocess.Popen
        # This is Python 3.14+ compliant (avoids fork with active event loops)
        process = subprocess.Popen(
            [sys.executable, str(background_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Full detachment from parent
        )

        # Write payload and close stdin (non-blocking)
        if process.stdin:
            process.stdin.write(payload_json.encode("utf-8"))
            process.stdin.close()

        logger.info(
            "background_storage_forked",
            extra={
                "type": metadata.get("type"),
                "story_id": metadata.get("story_id"),
                "group_id": metadata.get("group_id"),
            },
        )

    except Exception as e:
        # Log error but don't raise - graceful degradation
        logger.error(
            "fork_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )


def store_synchronous(content: str, metadata: dict[str, Any]) -> int:
    """
    Store memory synchronously (for testing or when fork is disabled).

    Args:
        content: Memory content to store
        metadata: Validated metadata dictionary

    Returns:
        Exit code: 0 (success) or 1 (failure)
    """
    try:
        from memory.models import MemoryType
        from memory.storage import MemoryStorage

        # Get session_id and source_hook from metadata
        session_id = metadata.get("session_id", DEFAULT_SESSION_ID)
        source_hook = metadata.get("source_hook", DEFAULT_SOURCE_HOOK)
        memory_type_str = metadata.get("type")
        group_id = metadata.get("group_id")

        # Convert string type to MemoryType enum
        memory_type = MemoryType(memory_type_str)

        # Determine collection based on type
        if memory_type_str == "best_practice":
            collection = "conventions"
        elif memory_type_str in ["session_summary", "chat_memory", "agent_decision"]:
            collection = "discussions"
        else:
            collection = "code-patterns"

        # Store memory
        storage = MemoryStorage()
        result = storage.store_memory(
            content=content,
            cwd=metadata.get("cwd", "/"),  # Use cwd from metadata or fallback
            group_id=group_id,
            memory_type=memory_type,
            source_hook=source_hook,
            session_id=session_id,
            collection=collection,
            # Pass additional metadata fields
            agent=metadata.get("agent"),
            component=metadata.get("component"),
            story_id=metadata.get("story_id"),
            importance=metadata.get("importance"),
        )

        logger.info(
            "memory_stored_synchronously",
            extra={
                "memory_id": result.get("memory_id"),
                "status": result.get("status"),
                "embedding_status": result.get("embedding_status"),
                "type": memory_type_str,
                "group_id": group_id,
            },
        )

        print(f"\n✅ Memory stored successfully: {result['status']}")
        print(f"   Memory ID: {result.get('memory_id')}")
        print(f"   Embedding: {result.get('embedding_status')}")

        return 0

    except QdrantUnavailable as e:
        logger.error("qdrant_unavailable", extra={"error": str(e)})
        print(f"\n❌ ERROR: Qdrant unavailable - {e}", file=sys.stderr)
        return 1

    except Exception as e:
        logger.error(
            "storage_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )
        print(f"\n❌ ERROR: Storage failed - {e}", file=sys.stderr)
        # Print traceback for debugging
        import traceback

        traceback.print_exc(file=sys.stderr)
        return 1


def main() -> int:
    """
    Main entry point for post-work storage hook.

    Process:
    1. Parse arguments
    2. Load content and metadata
    3. Validate metadata structure
    4. Validate content (validate_storage.py logic)
    5. Check for duplicates (check_duplicates.py logic)
    6. Fork to background for actual storage (non-blocking)
    7. Exit 0 immediately

    Returns:
        Exit code: 0 (success) or 1 (validation failed)
    """
    start_time = time.perf_counter()

    parser = argparse.ArgumentParser(
        description="Store implementation memories after BMAD workflow completion"
    )

    # Content input options
    content_group = parser.add_mutually_exclusive_group()
    content_group.add_argument("--content", help="Memory content as string")
    content_group.add_argument("--content-file", help="File containing memory content")

    # Metadata input options
    metadata_group = parser.add_mutually_exclusive_group(required=True)
    metadata_group.add_argument("--metadata", help="Metadata as JSON string")
    metadata_group.add_argument("--metadata-file", help="File containing metadata JSON")

    # Processing options
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Store synchronously (no fork, for testing)",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip pre-storage validation (not recommended)",
    )
    parser.add_argument(
        "--skip-duplicate-check",
        action="store_true",
        help="Skip duplicate detection (faster but may create duplicates)",
    )

    args = parser.parse_args()

    # Load content
    if args.content:
        content = args.content
    elif args.content_file:
        try:
            with open(args.content_file) as f:
                content = f.read()
        except FileNotFoundError:
            print(
                f"ERROR: Content file not found: {args.content_file}", file=sys.stderr
            )
            return 1
        except Exception as e:
            print(f"ERROR: Failed to read content file: {e}", file=sys.stderr)
            return 1
    else:
        # Read from stdin
        try:
            content = sys.stdin.read()
        except Exception as e:
            print(f"ERROR: Failed to read from stdin: {e}", file=sys.stderr)
            return 1

    # Validate content is not empty
    if not content or not content.strip():
        print("ERROR: Content is empty", file=sys.stderr)
        return 1

    # Load metadata
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid metadata JSON: {e}", file=sys.stderr)
            return 1
    elif args.metadata_file:
        try:
            with open(args.metadata_file) as f:
                metadata = json.load(f)
        except FileNotFoundError:
            print(
                f"ERROR: Metadata file not found: {args.metadata_file}", file=sys.stderr
            )
            return 1
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid metadata JSON in file: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"ERROR: Failed to read metadata file: {e}", file=sys.stderr)
            return 1
    else:
        print("ERROR: Must provide --metadata or --metadata-file", file=sys.stderr)
        return 1

    # Validate metadata structure
    is_valid, error_msg = validate_metadata(metadata)
    if not is_valid:
        print(f"ERROR: Metadata validation failed: {error_msg}", file=sys.stderr)
        return 1

    # Add defaults if not provided
    if "session_id" not in metadata:
        metadata["session_id"] = DEFAULT_SESSION_ID
    if "source_hook" not in metadata:
        metadata["source_hook"] = DEFAULT_SOURCE_HOOK

    # Pre-storage validation (validate_storage.py logic)
    if not args.skip_validation:
        logger.info("running_pre_storage_validation")
        is_valid, validation_msg, validation_details = validate_before_storage(
            information=content,
            metadata=metadata,
            skip_duplicate_check=args.skip_duplicate_check,
            skip_similarity_check=args.skip_duplicate_check,
        )

        if not is_valid:
            print("\n" + "=" * 60, file=sys.stderr)
            print("PRE-STORAGE VALIDATION FAILED", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            print(validation_msg, file=sys.stderr)
            print("\nMemory will NOT be stored.", file=sys.stderr)
            return 1

        # Log validation warnings if any
        if validation_details.get("warnings"):
            for warning in validation_details["warnings"]:
                logger.warning("validation_warning", extra={"warning_text": warning})

    # Duplicate detection (check_duplicates.py logic)
    if not args.skip_duplicate_check:
        logger.info("running_duplicate_detection")
        duplicates_found, dup_details = check_for_duplicates(
            content=content,
            unique_id=metadata.get("unique_id"),
            skip_semantic=False,
        )

        if duplicates_found:
            print("\n" + "=" * 60, file=sys.stderr)
            print("DUPLICATE DETECTED", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            print(
                f"Content hash: {dup_details.get('content_hash', '')[:16]}...",
                file=sys.stderr,
            )

            if dup_details.get("duplicates"):
                print("\nExact duplicates found:", file=sys.stderr)
                for dup in dup_details["duplicates"]:
                    print(
                        f"  - {dup['unique_id']} in {dup['collection']}",
                        file=sys.stderr,
                    )

            if dup_details.get("similar"):
                print("\nSemantically similar content:", file=sys.stderr)
                for sim in dup_details["similar"]:
                    print(
                        f"  - {sim['unique_id']} in {sim['collection']} "
                        f"(similarity: {sim['similarity']:.2%})",
                        file=sys.stderr,
                    )

            print("\nMemory will NOT be stored (duplicate).", file=sys.stderr)
            return 1

    # All validation passed - proceed with storage
    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "validation_completed",
        extra={
            "duration_ms": f"{duration_ms:.2f}",
            "type": metadata.get("type"),
            "story_id": metadata.get("story_id"),
        },
    )

    # User notification
    print(f"\n✅ Validation passed ({duration_ms:.0f}ms)", file=sys.stderr)
    print(f"   Type: {metadata.get('type')}", file=sys.stderr)
    print(f"   Story: {metadata.get('story_id', 'N/A')}", file=sys.stderr)
    print(f"   Group: {metadata.get('group_id')}", file=sys.stderr)

    # Store (synchronous or background fork)
    if args.sync:
        print("\n🔄 Storing synchronously...", file=sys.stderr)
        return store_synchronous(content, metadata)
    else:
        print("\n🚀 Forking to background storage...", file=sys.stderr)
        fork_background_storage(content, metadata)
        print("✅ Background storage initiated", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
