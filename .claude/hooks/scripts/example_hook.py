#!/usr/bin/env python3
"""Example hook demonstrating graceful degradation patterns.

This hook demonstrates all graceful degradation patterns for the BMAD
Memory Module. Use this as a template for implementing real hooks:
- SessionStart: Load relevant memories
- PostToolUse: Capture implementations
- Stop: Store session summary

Patterns Demonstrated:
    1. @graceful_hook decorator for automatic exception handling
    2. check_services() for service health checks
    3. get_fallback_mode() for degradation strategy
    4. queue_operation() for resilience when Qdrant down
    5. Structured logging with extras dict throughout
    6. Exit code policy (0=success, 1=non-blocking error)

Usage:
    # Direct execution
    python .claude/hooks/scripts/example_hook.py

    # As Claude Code hook (in .claude/settings.json)
    {
      "hooks": {
        "SessionStart": [{
          "type": "command",
          "command": ".claude/hooks/scripts/example_hook.py"
        }]
      }
    }

Exit Codes:
    0 - Success (normal operation or queued)
    1 - Non-blocking error (Claude continues)
    2 - Blocking error (never used in this example)
"""

import sys
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path for imports (portable - works from any location)
# .claude/hooks/scripts/example_hook.py -> project root is 3 levels up
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from src.memory.graceful import graceful_hook, exit_success, exit_graceful
from src.memory.health import check_services, get_fallback_mode
from src.memory.queue import queue_operation

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("bmad.memory.example_hook")


@graceful_hook
def main():
    """Example hook entry point with graceful degradation.

    Demonstrates complete graceful degradation flow:
    1. Check service health
    2. Determine fallback mode
    3. Execute appropriate strategy
    4. Log results with structured extras
    5. Exit with appropriate code
    """
    logger.info("example_hook_started", extra={
        "timestamp": datetime.now().isoformat()
    })

    # Step 1: Check service health
    # Fast check (<2s per NFR-P1) - never raises exceptions
    health = check_services()

    logger.info("service_health_checked", extra={
        "qdrant": health["qdrant"],
        "embedding": health["embedding"],
        "all_healthy": health["all_healthy"]
    })

    # Step 2: Determine fallback mode based on health
    mode = get_fallback_mode(health)

    logger.info("fallback_mode_selected", extra={
        "mode": mode
    })

    # Step 3: Execute strategy based on fallback mode
    if mode == "normal":
        # All services healthy - full operation
        logger.info("executing_normal_mode", extra={
            "operation": "full_memory_operation"
        })

        # In real hook:
        # - Generate embedding for content
        # - Store in Qdrant with embedding
        # - Exit 0

        logger.info("memory_operation_completed", extra={
            "mode": "normal",
            "result": "success"
        })
        exit_success()

    elif mode == "queue_to_file":
        # Qdrant unavailable - queue operation for later
        logger.warning("qdrant_unavailable", extra={
            "action": "queuing_to_file"
        })

        # Queue example operation
        operation = {
            "content": "Example memory content",
            "group_id": "example-project",
            "type": "implementation",
            "source_hook": "example_hook",
            "timestamp": datetime.now().isoformat()
        }

        if queue_operation(operation):
            logger.info("operation_queued_successfully", extra={
                "queue_location": "~/.bmad-memory/queue/pending.jsonl"
            })
            # Exit 0 - queued successfully (will replay later)
            exit_success()
        else:
            logger.error("queue_operation_failed", extra={
                "fallback": "passthrough"
            })
            # Exit 1 - non-blocking error
            exit_graceful("Failed to queue operation")

    elif mode == "pending_embedding":
        # Embedding service unavailable - store with pending status
        logger.warning("embedding_unavailable", extra={
            "action": "storing_with_pending_embedding"
        })

        # In real hook:
        # - Store in Qdrant with embedding_status="pending"
        # - Background process will backfill embedding later
        # - Exit 0

        logger.info("memory_stored_pending_embedding", extra={
            "embedding_status": "pending",
            "will_backfill": True
        })
        exit_success()

    elif mode == "passthrough":
        # Both services unavailable - log and exit gracefully
        logger.error("memory_system_unavailable", extra={
            "qdrant": False,
            "embedding": False,
            "action": "passthrough"
        })

        # Exit 1 - non-blocking error (Claude continues without memory)
        exit_graceful("All memory services unavailable")

    else:
        # Unknown mode (defensive)
        logger.error("unknown_fallback_mode", extra={
            "mode": mode
        })
        exit_graceful(f"Unknown fallback mode: {mode}")


if __name__ == "__main__":
    # Entry point - decorator will catch all exceptions
    # and exit with code 1 (non-blocking) on error
    main()
