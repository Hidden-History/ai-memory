#!/usr/bin/env python3
"""Unified UserPromptSubmit trigger - consolidates decision, session, best practices.

TECH-DEBT-062: Replaces 3 sequential triggers with 1 parallel trigger.
Performance target: <1000ms total (down from 2966ms+)

Architecture:
    1. Run all 3 keyword detectors synchronously (<0.1ms total)
    2. For each triggered type, search Qdrant in parallel (shared client)
    3. Deduplicate results by content_hash
    4. Priority order: decision > session > best_practices
    5. Output formatted context to stdout

CR Fixes Applied:
    - CRIT-1: Keyword detection now synchronous (thread overhead > work time)
    - CRIT-2: Metrics track found vs shown (deduplication doesn't hide success)
    - HIGH-1: Shared MemorySearch client (60%+ latency reduction via pooling)
    - HIGH-3: Thread-safe circuit breaker with RLock
    - MED-1: Proper hash fallback for deduplication
"""

import asyncio
import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field

# Path setup
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import COLLECTION_CONVENTIONS, COLLECTION_DISCUSSIONS, get_config
from memory.health import check_qdrant_health
from memory.hooks_common import log_to_activity, setup_hook_logging
from memory.project import detect_project
from memory.qdrant_client import get_qdrant_client
from memory.search import MemorySearch
from memory.triggers import (
    detect_best_practices_keywords,
    detect_decision_keywords,
    detect_session_history_keywords,
)

logger = setup_hook_logging()

# Configuration
MAX_RESULTS_PER_TYPE = 2  # Limit per trigger type
MAX_TOTAL_RESULTS = 5  # Total results to show
SEARCH_TIMEOUT = 3.0  # Seconds per search
CIRCUIT_BREAKER_THRESHOLD = 3  # Failures before opening
CIRCUIT_BREAKER_RESET = 60  # Seconds to reset


@dataclass
class TriggerResult:
    """Result from a single trigger type."""

    trigger_type: str  # "decision", "session", "best_practices"
    topic: str
    results: list[dict]
    search_time_ms: float


@dataclass
class CircuitBreaker:
    """Thread-safe circuit breaker for Qdrant protection.

    CR-FIX HIGH-3: Added RLock for thread safety under concurrent hook invocations.
    """

    failures: int = 0
    last_failure: float = 0.0
    is_open: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def record_failure(self):
        """Record a failure (thread-safe)."""
        with self._lock:
            self.failures += 1
            self.last_failure = time.time()
            if self.failures >= CIRCUIT_BREAKER_THRESHOLD:
                self.is_open = True
                logger.warning(
                    "circuit_breaker_opened", extra={"failures": self.failures}
                )

    def record_success(self):
        """Record a success (thread-safe)."""
        with self._lock:
            self.failures = 0
            self.is_open = False

    def should_allow(self) -> bool:
        """Check if requests should be allowed (thread-safe)."""
        with self._lock:
            if not self.is_open:
                return True
            # Check if reset period passed
            if time.time() - self.last_failure > CIRCUIT_BREAKER_RESET:
                self.is_open = False
                self.failures = 0
                logger.info("circuit_breaker_reset")
                return True
            return False


# Global circuit breaker (persists across hook calls via module state)
_circuit_breaker = CircuitBreaker()


async def detect_all_triggers(prompt: str) -> dict[str, str | None]:
    """Run all keyword detectors synchronously.

    CR-FIX CRIT-1: These are trivial string operations (<0.1ms each).
    Thread pool overhead would exceed actual work time.

    Returns:
        Dict mapping trigger_type to extracted topic (or None if not triggered)
    """
    return {
        "decision": detect_decision_keywords(prompt),
        "session": detect_session_history_keywords(prompt),
        "best_practices": detect_best_practices_keywords(prompt),
    }


async def search_single_trigger(
    search_client: MemorySearch,
    trigger_type: str,
    topic: str,
    collection: str,
    type_filter: str | None,
    group_id: str,
    mem_config,
) -> TriggerResult:
    """Execute single trigger search with shared client and timeout.

    CR-FIX HIGH-1: Uses shared MemorySearch client for connection pooling.

    Args:
        search_client: Shared MemorySearch instance (reused across searches)
        trigger_type: Trigger type identifier
        topic: Search topic/query
        collection: Collection to search
        type_filter: Optional memory type filter
        group_id: Project group ID
        mem_config: Memory configuration

    Returns:
        TriggerResult with search results and timing
    """
    start = time.time()

    try:
        # Run sync search in executor with timeout
        loop = asyncio.get_event_loop()

        def perform_search():
            query = f"{type_filter or 'memory'} about {topic}" if topic else topic
            return search_client.search(
                query=query,
                collection=collection,
                group_id=group_id,
                limit=MAX_RESULTS_PER_TYPE,
                score_threshold=mem_config.similarity_threshold,
                memory_type=type_filter,
                fast_mode=True,  # TECH-DEBT-066: Triggers use fast mode (hnsw_ef=64)
            )

        search_task = loop.run_in_executor(None, perform_search)
        results = await asyncio.wait_for(search_task, timeout=SEARCH_TIMEOUT)
        _circuit_breaker.record_success()

        return TriggerResult(
            trigger_type=trigger_type,
            topic=topic,
            results=results,
            search_time_ms=(time.time() - start) * 1000,
        )

    except asyncio.TimeoutError:
        logger.warning(
            "search_timeout",
            extra={"trigger_type": trigger_type, "timeout_seconds": SEARCH_TIMEOUT},
        )
        _circuit_breaker.record_failure()
        return TriggerResult(trigger_type, topic, [], (time.time() - start) * 1000)

    except Exception as e:
        logger.error(
            "search_error",
            extra={
                "trigger_type": trigger_type,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        _circuit_breaker.record_failure()
        return TriggerResult(trigger_type, topic, [], (time.time() - start) * 1000)


async def search_all_triggered(
    triggers: dict[str, str | None], group_id: str, mem_config
) -> list[TriggerResult]:
    """Run all triggered searches in parallel with shared client.

    CR-FIX HIGH-1: Creates ONE MemorySearch instance for all searches,
    enabling connection pooling and reducing overhead by ~60%.

    Args:
        triggers: Dict of trigger types to topics
        group_id: Project group ID
        mem_config: Memory configuration

    Returns:
        List of TriggerResult objects
    """
    if not _circuit_breaker.should_allow():
        logger.info("circuit_breaker_blocked")
        return []

    # CR-FIX HIGH-1: Create ONE shared MemorySearch instance
    search_client = MemorySearch(mem_config)

    try:
        tasks = []

        if triggers.get("decision"):
            tasks.append(
                search_single_trigger(
                    search_client,  # Pass shared client
                    "decision",
                    triggers["decision"],
                    COLLECTION_DISCUSSIONS,
                    None,  # Search ALL discussion types (decision, session, blocker, preference, user_message, agent_response)
                    group_id,
                    mem_config,
                )
            )

        if triggers.get("session"):
            tasks.append(
                search_single_trigger(
                    search_client,  # Pass shared client
                    "session",
                    triggers["session"],
                    COLLECTION_DISCUSSIONS,
                    "session",
                    group_id,
                    mem_config,
                )
            )

        if triggers.get("best_practices"):
            tasks.append(
                search_single_trigger(
                    search_client,  # Pass shared client
                    "best_practices",
                    triggers["best_practices"],
                    COLLECTION_CONVENTIONS,
                    None,
                    group_id,
                    mem_config,
                )
            )

        if not tasks:
            return []

        return await asyncio.gather(*tasks)

    finally:
        # CR-FIX HIGH-1: Clean up shared client
        search_client.close()


def deduplicate_results(trigger_results: list[TriggerResult]) -> list[dict]:
    """Deduplicate results by content_hash, priority order."""

    # Priority: decision > session > best_practices
    priority = {"decision": 0, "session": 1, "best_practices": 2}

    # Sort by priority
    sorted_results = sorted(
        trigger_results, key=lambda r: priority.get(r.trigger_type, 99)
    )

    seen_hashes: set[str] = set()
    deduplicated: list[dict] = []

    for tr in sorted_results:
        for result in tr.results:
            # CR-FIX MED-1: Use proper hash fallback instead of first 50 chars
            content_hash = result.get("content_hash")
            if not content_hash:
                logger.warning(
                    "missing_content_hash", extra={"result_id": result.get("id")}
                )
                content_hash = hashlib.sha256(
                    result.get("content", "").encode()
                ).hexdigest()

            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                result["_trigger_type"] = tr.trigger_type
                deduplicated.append(result)

                if len(deduplicated) >= MAX_TOTAL_RESULTS:
                    return deduplicated

    return deduplicated


def format_result(result: dict, index: int) -> str:
    """Format single result for stdout (no truncation for full context)."""
    content = result.get("content", "")
    score = result.get("score", 0)
    result_type = result.get("type", "unknown")
    trigger_type = result.get("_trigger_type", "unknown")
    tags = result.get("tags", [])

    header = f"{index}. **{result_type}** ({score:.0%}) [{trigger_type}]"
    if tags:
        header += f" - {', '.join(tags)}"

    return f"{header}\n{content}\n"


async def main_async() -> int:
    """Main async entry point."""
    start_time = time.time()
    project_name = "unknown"  # Initialize for metrics (TECH-DEBT-142)

    try:
        # Read hook input
        raw_input = sys.stdin.read()
        hook_input = json.loads(raw_input)
        prompt = hook_input.get("prompt", "")
        cwd = hook_input.get("cwd", os.getcwd())

        if not prompt:
            return 0

        # Step 1: Detect all triggers in parallel
        triggers = await detect_all_triggers(prompt)

        triggered_count = sum(1 for v in triggers.values() if v)
        if triggered_count == 0:
            logger.debug("no_triggers_matched")
            return 0

        logger.info(
            "triggers_detected",
            extra={
                "decision": bool(triggers.get("decision")),
                "session": bool(triggers.get("session")),
                "best_practices": bool(triggers.get("best_practices")),
            },
        )

        # Initialize Qdrant connection
        mem_config = get_config()
        client = get_qdrant_client(mem_config)

        # Check Qdrant health
        if not check_qdrant_health(client):
            logger.warning("qdrant_unavailable")
            return 0

        # Detect project for filtering
        project_name = detect_project(cwd)

        # Step 2: Search all triggered types in parallel
        trigger_results = await search_all_triggered(triggers, project_name, mem_config)

        # CR-FIX CRIT-2: Track results BEFORE deduplication
        results_found_by_trigger = {
            "decision": 0,
            "session": 0,
            "best_practices": 0,
        }

        for tr in trigger_results:
            results_found_by_trigger[tr.trigger_type] = len(tr.results)

        # Step 3: Deduplicate and prioritize
        final_results = deduplicate_results(trigger_results)

        # CR-FIX CRIT-2: Track results AFTER deduplication
        results_shown_by_trigger = {
            "decision": 0,
            "session": 0,
            "best_practices": 0,
        }

        for result in final_results:
            trigger_type = result.get("_trigger_type")
            if trigger_type in results_shown_by_trigger:
                results_shown_by_trigger[trigger_type] += 1

        if not final_results:
            logger.info("no_results_found")
            # Activity log for visibility even when no results
            total_time = (time.time() - start_time) * 1000
            triggered_names = ", ".join(k for k, v in triggers.items() if v)
            log_to_activity(
                f"🎯 KeywordTrigger ({triggered_names}): No relevant memories found [{total_time:.0f}ms]",
                INSTALL_DIR,
            )
            # TECH-DEBT-070: Push accurate metrics (async to avoid latency)
            from memory.metrics_push import push_trigger_metrics_async

            duration_seconds = time.time() - start_time

            for trigger_type in ["decision", "session", "best_practices"]:
                if triggers.get(trigger_type):  # If this trigger fired
                    found = results_found_by_trigger[trigger_type]
                    # Status is "success" if trigger FOUND results (even if all deduplicated)
                    status = "success" if found > 0 else "empty"

                    push_trigger_metrics_async(
                        trigger_type=f"{trigger_type}_keywords",
                        status=status,
                        project=project_name,
                        results_count=0,  # Nothing shown to user
                        duration_seconds=duration_seconds,
                    )

                    logger.info(
                        "trigger_metrics",
                        extra={
                            "trigger": trigger_type,
                            "found": found,
                            "shown": 0,
                            "deduplicated": found,
                        },
                    )
            return 0

        # Step 4: Format and output
        output_lines = ["=" * 70, "🎯 RELEVANT MEMORIES", "=" * 70]
        output_lines.append(
            f"Triggers: {', '.join(k for k, v in triggers.items() if v)}\n"
        )

        for i, result in enumerate(final_results, 1):
            output_lines.append(format_result(result, i))

        output_lines.append("=" * 70)
        print("\n".join(output_lines))

        # Activity log for user visibility
        total_time = (time.time() - start_time) * 1000
        triggered_names = ", ".join(k for k, v in triggers.items() if v)
        types_found = set(r.get("type", "unknown") for r in final_results)
        log_to_activity(
            f"🎯 KeywordTrigger ({triggered_names}): {len(final_results)} memories found "
            f"[types: {', '.join(types_found)}] [{total_time:.0f}ms]",
            INSTALL_DIR,
        )

        # Metrics
        logger.info(
            "unified_trigger_complete",
            extra={
                "total_time_ms": total_time,
                "triggers_fired": triggered_count,
                "results_returned": len(final_results),
                "searches_performed": len(trigger_results),
            },
        )

        # TECH-DEBT-070: Push accurate metrics for each trigger type (async)
        from memory.metrics_push import push_trigger_metrics_async

        duration_seconds = time.time() - start_time

        for trigger_type in ["decision", "session", "best_practices"]:
            if triggers.get(trigger_type):  # If this trigger fired
                found = results_found_by_trigger[trigger_type]
                shown = results_shown_by_trigger[trigger_type]

                # Status is "success" if trigger FOUND results (even if deduplicated)
                status = "success" if found > 0 else "empty"

                push_trigger_metrics_async(
                    trigger_type=f"{trigger_type}_keywords",
                    status=status,
                    project=project_name,
                    results_count=shown,  # What user actually sees
                    duration_seconds=duration_seconds,
                )

                logger.info(
                    "trigger_metrics",
                    extra={
                        "trigger": trigger_type,
                        "found": found,
                        "shown": shown,
                        "deduplicated": found - shown,
                    },
                )

        # HIGH-3 FIX: Protect import with try/except for graceful degradation
        try:
            from memory.metrics_push import push_hook_metrics_async

            duration_seconds = time.time() - start_time
            push_hook_metrics_async(
                hook_name="UserPromptSubmit",
                duration_seconds=duration_seconds,
                success=True,
                project=project_name,
            )
        except ImportError:
            pass  # Graceful degradation if metrics unavailable

        return 0

    except Exception as e:
        logger.error(
            "unified_trigger_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )

        # HIGH-3 FIX: Protect import with try/except for graceful degradation
        try:
            from memory.metrics_push import push_hook_metrics_async

            duration_seconds = time.time() - start_time
            push_hook_metrics_async(
                hook_name="UserPromptSubmit",
                duration_seconds=duration_seconds,
                success=False,
                project=project_name,
            )
        except ImportError:
            pass  # Graceful degradation if metrics unavailable

        return 0  # Graceful degradation


def main() -> int:
    """Sync entry point."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
