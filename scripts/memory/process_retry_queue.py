#!/usr/bin/env python3
"""Retry queue processor for failed memory storage operations.

Processes items in the unified retry queue (pending_queue.jsonl) that failed
due to Qdrant unavailability, timeouts, or other transient errors.

Architecture:
- Reads from $AI_MEMORY_INSTALL_DIR/queue/pending_queue.jsonl
- Attempts to re-store each item using MemoryStorage
- On success: removes from queue
- On failure: increments retry_count (exponential backoff)
- Items exceeding max_retries moved to dead letter queue

Usage:
    # Process all pending items
    python3 scripts/memory/process_retry_queue.py

    # Force retry exhausted items too
    python3 scripts/memory/process_retry_queue.py --force

    # Dry run (show what would be processed)
    python3 scripts/memory/process_retry_queue.py --dry-run

    # Clear all items (dangerous)
    python3 scripts/memory/process_retry_queue.py --clear
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Setup Python path
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
)
from memory.hooks_common import setup_hook_logging
from memory.models import MemoryType
from memory.queue import MemoryQueue
from memory.storage import MemoryStorage

logger = setup_hook_logging("ai_memory.retry_processor")

# Dead letter queue for items that exceed max retries
DLQ_FILE = Path(INSTALL_DIR) / "queue" / "retry_queue_dlq.jsonl"


def get_collection_for_type(memory_type: str) -> str:
    """Determine collection based on memory type."""
    if memory_type in [
        "guideline",
        "rule",
        "naming",
        "port",
        "structure",
        "best_practice",
    ]:
        return COLLECTION_CONVENTIONS
    elif memory_type in [
        "decision",
        "session",
        "blocker",
        "preference",
        "context",
        "session_summary",
        "chat_memory",
        "agent_decision",
        "user_message",
        "agent_response",
    ]:
        return COLLECTION_DISCUSSIONS
    else:
        return COLLECTION_CODE_PATTERNS


def process_entry(
    entry: dict, storage: MemoryStorage, dry_run: bool = False
) -> tuple[bool, str]:
    """Process a single queue entry.

    Args:
        entry: Queue entry with memory_data and metadata
        storage: MemoryStorage instance
        dry_run: If True, don't actually store

    Returns:
        (success: bool, message: str)
    """
    memory_data = entry.get("memory_data", {})

    # Handle different payload formats
    # Format 1: Direct memory data (content, type, group_id at top level)
    # Format 2: Hook input format (hook_input key with nested data)
    # Format 3: Payload wrapper format (payload key with content/metadata)

    if "hook_input" in memory_data:
        # This is raw hook input - needs extraction
        hook_input = memory_data["hook_input"]
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})

        # Extract content based on tool type
        if tool_name == "Edit":
            content = tool_input.get("new_string", "")
        elif tool_name == "Write":
            content = tool_input.get("content", "")
        elif tool_name == "NotebookEdit":
            content = tool_input.get("new_source", "")
        else:
            content = json.dumps(tool_input)

        if not content or len(content) < 20:
            return False, "Content too short or empty"

        # Build memory params
        from memory.project import detect_project

        cwd = hook_input.get("cwd", "/")
        group_id = detect_project(cwd)
        memory_type = "implementation"
        session_id = hook_input.get("session_id", "retry")
        source_hook = "PostToolUse"
        file_path = tool_input.get("file_path", "")
        collection = COLLECTION_CODE_PATTERNS

    elif "payload" in memory_data:
        # Payload wrapper format
        payload = memory_data["payload"]
        content = payload.get("content", "")
        metadata = payload.get("metadata", {})
        memory_type = metadata.get("type", "implementation")
        group_id = metadata.get("group_id", "unknown")
        session_id = metadata.get("session_id", "retry")
        source_hook = metadata.get("source_hook", "retry")
        file_path = metadata.get("file_path", "")
        collection = get_collection_for_type(memory_type)

    elif "content" in memory_data:
        # Direct format
        content = memory_data.get("content", "")
        memory_type = memory_data.get("type", "implementation")
        group_id = memory_data.get("group_id", "unknown")
        session_id = memory_data.get("session_id", "retry")
        source_hook = memory_data.get("source_hook", "retry")
        file_path = memory_data.get("file_path", "")
        collection = get_collection_for_type(memory_type)

    else:
        return False, f"Unknown payload format: {list(memory_data.keys())}"

    if not content:
        return False, "No content found in entry"

    if dry_run:
        return (
            True,
            f"Would store: {len(content)} chars, type={memory_type}, group={group_id}",
        )

    try:
        # Convert string type to MemoryType enum
        try:
            mem_type_enum = MemoryType(memory_type)
        except ValueError:
            mem_type_enum = MemoryType.IMPLEMENTATION

        result = storage.store_memory(
            content=content,
            cwd=file_path or "/",
            group_id=group_id,
            memory_type=mem_type_enum,
            source_hook=source_hook,
            session_id=session_id,
            collection=collection,
        )

        if result["status"] == "stored":
            return True, f"Stored: {result.get('memory_id', 'unknown')}"
        elif result["status"] == "duplicate":
            return True, "Skipped: duplicate"
        else:
            return False, f"Unknown status: {result['status']}"

    except Exception as e:
        return False, f"Storage error: {type(e).__name__}: {str(e)[:100]}"


def move_to_dlq(entry: dict):
    """Move exhausted entry to dead letter queue."""
    DLQ_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry["moved_to_dlq_at"] = datetime.now(timezone.utc).isoformat()
    with open(DLQ_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def process_queue(force: bool = False, dry_run: bool = False, limit: int = 100) -> dict:
    """Process pending items in the retry queue.

    Args:
        force: If True, also process items that exceeded max_retries
        dry_run: If True, don't actually store or modify queue
        limit: Maximum items to process

    Returns:
        dict with processing statistics
    """
    queue = MemoryQueue()
    storage = MemoryStorage() if not dry_run else None

    stats = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "moved_to_dlq": 0,
        "errors": [],
    }

    # Get pending items
    pending = queue.get_pending(limit=limit, include_exhausted=force)

    if not pending:
        logger.info("queue_empty", extra={"details": "No items pending"})
        return stats

    logger.info(
        "processing_start",
        extra={"pending_count": len(pending), "force": force, "dry_run": dry_run},
    )

    for entry in pending:
        entry_id = entry.get("id", "unknown")
        retry_count = entry.get("retry_count", 0)
        max_retries = entry.get("max_retries", 3)
        failure_reason = entry.get("failure_reason", "unknown")

        stats["processed"] += 1

        try:
            success, message = process_entry(entry, storage, dry_run)

            if success:
                stats["success"] += 1
                logger.info(
                    "entry_processed",
                    extra={
                        "entry_id": entry_id,
                        "result": message,
                        "retry_count": retry_count,
                    },
                )
                if not dry_run:
                    queue.dequeue(entry_id)
            else:
                stats["failed"] += 1
                logger.warning(
                    "entry_failed",
                    extra={
                        "entry_id": entry_id,
                        "error_detail": message,
                        "retry_count": retry_count,
                    },
                )

                if not dry_run:
                    if retry_count >= max_retries - 1:
                        # Move to DLQ
                        move_to_dlq(entry)
                        queue.dequeue(entry_id)
                        stats["moved_to_dlq"] += 1
                        logger.info("moved_to_dlq", extra={"entry_id": entry_id})
                    else:
                        queue.mark_failed(entry_id)

        except Exception as e:
            stats["failed"] += 1
            error_msg = f"{entry_id}: {type(e).__name__}: {str(e)[:100]}"
            stats["errors"].append(error_msg)
            logger.error(
                "processing_error",
                extra={
                    "entry_id": entry_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    logger.info("processing_complete", extra=stats)
    return stats


def clear_queue() -> int:
    """Clear all items from the queue. Returns count of items cleared."""
    queue = MemoryQueue()
    pending = queue.get_pending(limit=1000, include_exhausted=True)
    count = len(pending)

    for entry in pending:
        queue.dequeue(entry.get("id"))

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Process retry queue for failed memory operations"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Also process items that exceeded max_retries",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes",
    )
    parser.add_argument(
        "--limit", type=int, default=100, help="Maximum items to process (default: 100)"
    )
    parser.add_argument(
        "--clear", action="store_true", help="Clear all items from queue (dangerous)"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show queue statistics only"
    )

    args = parser.parse_args()

    if args.stats:
        queue = MemoryQueue()
        stats = queue.get_stats()
        print(f"Queue Statistics:")
        print(f"  Total items: {stats['total_items']}")
        print(f"  Ready for retry: {stats['ready_for_retry']}")
        print(f"  Awaiting backoff: {stats['awaiting_backoff']}")
        print(f"  Exhausted (max retries): {stats['exhausted']}")
        print(f"  By failure reason:")
        for reason, count in stats["by_failure_reason"].items():
            print(f"    {reason}: {count}")
        return 0

    if args.clear:
        confirm = input("Are you sure you want to clear all queue items? (yes/no): ")
        if confirm.lower() == "yes":
            count = clear_queue()
            print(f"Cleared {count} items from queue")
            return 0
        else:
            print("Aborted")
            return 1

    stats = process_queue(force=args.force, dry_run=args.dry_run, limit=args.limit)

    print(f"\nProcessing Complete:")
    print(f"  Processed: {stats['processed']}")
    print(f"  Success: {stats['success']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Moved to DLQ: {stats['moved_to_dlq']}")

    if stats["errors"]:
        print(f"\nErrors:")
        for error in stats["errors"][:10]:
            print(f"  - {error}")
        if len(stats["errors"]) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")

    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
