#!/usr/bin/env python3
"""PostToolUse Hook - Retrieve error patterns when errors detected.

Memory System V2.0 TRIGGER 1: Error Detection
Automatically retrieves similar error fixes when bash commands fail.

Signal Detection:
    - PostToolUse hook for Bash tool
    - Exit code != 0 OR error patterns in output

Action:
    - Extract error signature
    - Search code-patterns collection
    - Phase 1: Search type=error_pattern, subtype=error (similar errors)
    - Phase 2: Follow error_group_id to retrieve linked fixes (subtype=fix)
    - Inject up to 6 results (3 errors + up to 1 linked fix each)

Configuration:
    - Hook: PostToolUse with matcher "Bash"
    - Collection: code-patterns
    - Type filter: ["error_pattern"]
    - Phase 1 limit: 3 errors, Phase 2: up to 1 fix per error

Exit Codes:
    - 0: Success (or graceful degradation)
"""

# LANGFUSE: Uses trace buffer (Path A). See LANGFUSE-INTEGRATION-SPEC.md §3.1, §4, §7.7
# SDK VERSION: V3 ONLY. Do NOT use Langfuse() constructor, start_span(), or start_generation().
# CONSTANT: TRACE_CONTENT_MAX = 10000 (no other value permitted)

import json
import os
import re
import sys
import time

# Add src to path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import COLLECTION_CODE_PATTERNS, get_config
from memory.hooks_common import (
    extract_error_signature,
    get_metrics,
    log_to_activity,
    setup_hook_logging,
)
from memory.project import detect_project
from memory.search import MemorySearch

# SPEC-021: Trace buffer for retrieval instrumentation
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

# WP-6: Prometheus metrics for error-fix linkage
try:
    from memory.metrics import error_fix_effectiveness_total, error_fix_injections_total
except ImportError:
    error_fix_injections_total = None
    error_fix_effectiveness_total = None

TRACE_CONTENT_MAX = 10000  # Max chars for Langfuse input/output fields

logger = setup_hook_logging()

# CR-2 FIX: Use consolidated metrics import (TECH-DEBT-142: Remove local hook_duration_seconds)
memory_retrievals_total, retrieval_duration_seconds, _ = get_metrics()

# TECH-DEBT-142: Import push metrics for Pushgateway
try:
    from memory.metrics_push import (
        push_hook_metrics_async,
        push_retrieval_metrics_async,
    )
except ImportError:
    push_hook_metrics_async = None
    push_retrieval_metrics_async = None


def detect_error(tool_response: dict) -> bool:
    """Detect if bash output contains error indicators.

    Args:
        tool_response: Tool response dict with stdout/stderr fields

    Returns:
        True if error detected, False otherwise
    """
    exit_code = tool_response.get("exitCode")
    # Claude Code sends stdout/stderr separately, not combined "output"
    stdout = tool_response.get("stdout", "")
    stderr = tool_response.get("stderr", "")
    output = stderr if stderr else stdout  # Prefer stderr for error detection

    # Exit code check (most reliable)
    if exit_code is not None and exit_code != 0:
        return True

    # Error pattern check
    # FIX #2: Added "bug" pattern per spec (TRIGGER 1 line 1071)
    # L-2: These patterns are intentionally BROADER than error_pattern_capture.py's
    # capture regex. Detection casts a wide net to trigger retrieval; capture uses
    # stricter patterns (Traceback + exception type) to avoid false positives in
    # stored error memories. The asymmetry is by design.
    error_patterns = [
        r"(?i)\berror\b",
        r"(?i)\bexception\b",
        r"(?i)\btraceback\b",
        r"(?i)\bfailed\b",
        r"(?i)\bfatal\b",
        r"(?i)\bbug\b",  # SPEC REQUIREMENT
    ]
    for pattern in error_patterns:
        if re.search(pattern, output):
            return True

    return False


def format_error_pattern(fix: dict, index: int) -> str:
    """Format a single error fix for display (no truncation).

    Args:
        fix: Error fix dict with content, score, metadata
        index: 1-based index for numbering

    Returns:
        Formatted string for stdout display
    """
    content = fix.get("content", "")
    score = fix.get("score", 0)
    fix_type = fix.get("type", "error_pattern")
    subtype = fix.get("subtype", "error")
    file_path = fix.get("file_path", "")
    confidence = fix.get("resolution_confidence", 0)

    # Build header with relevance and subtype
    label = "FIX" if subtype == "fix" else "ERROR"
    header = f"{index}. **[{label}]** {fix_type} ({score:.0%}) [code-patterns]"
    if file_path:
        header += f"\n   From: {file_path}"
    if subtype == "fix" and confidence:
        header += f"\n   Confidence: {confidence:.0%}"

    # No truncation - show full content
    return f"{header}\n{content}\n"


def two_phase_retrieval(
    search: MemorySearch,
    error_signature: str,
    project_name: str,
    session_id: str,
) -> list[dict]:
    """Two-phase fix retrieval per Behavior Spec §4.3 R2.

    Phase 1: Search for similar errors (subtype="error")
    Phase 2: For each matched error, follow error_group_id to retrieve paired fix (subtype="fix")

    Priority: Fixes with resolution_confidence >= 0.7 shown first.
    Freshness: Skip fix if freshness_status is "stale" or "expired".

    Args:
        search: MemorySearch instance
        error_signature: Extracted error signature
        project_name: Project name for group_id
        session_id: Session ID

    Returns:
        List of result dicts (errors + their linked fixes), max 6 (3 errors + 3 fixes)
    """
    # Phase 1: Semantic match for similar errors (§4.3 R2)
    # M-1/L-1 FIX: Use type=error_pattern only (not dead "error_fix").
    # Post-filter by subtype="error" — Phase 2 follows links to find fixes.
    phase1_results = search.search(
        query=error_signature,
        collection=COLLECTION_CODE_PATTERNS,
        group_id=project_name,
        limit=3,
        score_threshold=0.5,
        memory_type=["error_pattern"],
    )

    # M-1 FIX: Filter Phase 1 to only error entries (subtype="error").
    # Fixes that happened to match semantically are excluded — Phase 2
    # retrieves linked fixes via error_group_id instead.
    phase1_results = [
        r for r in phase1_results
        if r.get("subtype", "error") == "error"
    ]

    if not phase1_results:
        return []

    # Phase 2: For each matched error, follow error_group_id to find paired fix
    all_results = []
    fix_results = []

    # Create QdrantClient ONCE before the loop for all Phase 2 lookups
    client = None
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "26350"))
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        qdrant_use_https = os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true"

        client = QdrantClient(
            host=qdrant_host,
            port=qdrant_port,
            api_key=qdrant_api_key,
            https=qdrant_use_https,
        )
    except Exception as e:
        logger.debug("phase2_client_init_failed", extra={"error": str(e)})

    try:
        for error_result in phase1_results:
            error_group_id = error_result.get("error_group_id", "")
            subtype = error_result.get("subtype", "")

            # Only follow link for error entries (not already a fix)
            if subtype == "fix":
                # This is already a fix - check freshness and add directly
                freshness = error_result.get("freshness_status", "unverified")
                if freshness.lower() in ("stale", "expired"):
                    continue
                fix_results.append(error_result)
                continue

            # Add the error context
            all_results.append(error_result)

            # Phase 2: Search for paired fix by error_group_id
            if error_group_id and client is not None:
                try:
                    # Scroll for fixes matching this error_group_id (limit=3, pick highest confidence)
                    fix_points, _ = client.scroll(
                        collection_name=COLLECTION_CODE_PATTERNS,
                        scroll_filter=Filter(
                            must=[
                                FieldCondition(
                                    key="error_group_id",
                                    match=MatchValue(value=error_group_id),
                                ),
                                FieldCondition(
                                    key="subtype",
                                    match=MatchValue(value="fix"),
                                ),
                                FieldCondition(
                                    key="group_id",
                                    match=MatchValue(value=project_name),
                                ),
                            ]
                        ),
                        limit=3,
                        with_payload=True,
                        with_vectors=False,
                    )

                    # Select the fix with highest resolution_confidence
                    best_fix = None
                    best_confidence = -1.0
                    for point in fix_points:
                        payload = point.payload or {}
                        freshness = payload.get("freshness_status", "unverified")
                        # §4.3 R2: Skip fix if freshness_status is STALE or EXPIRED
                        if freshness.lower() in ("stale", "expired"):
                            continue
                        confidence = payload.get("resolution_confidence", 0)
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_fix = (point, payload, freshness)

                    if best_fix is not None:
                        point, payload, freshness = best_fix
                        fix_entry = {
                            "content": payload.get("content", ""),
                            "score": error_result.get(
                                "score", 0
                            ),  # Inherit error's semantic score
                            "type": payload.get("type", "error_pattern"),
                            "subtype": "fix",
                            "file_path": payload.get("file_path", ""),
                            "error_group_id": error_group_id,
                            "resolution_confidence": payload.get(
                                "resolution_confidence", 0
                            ),
                            "freshness_status": freshness,
                            "fix_point_id": str(point.id),
                        }
                        fix_results.append(fix_entry)
                except Exception as e:
                    logger.debug("phase2_fix_retrieval_failed", extra={"error": str(e)})
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    # Priority sort: fixes with resolution_confidence >= 0.7 shown first
    high_confidence_fixes = [
        f for f in fix_results if f.get("resolution_confidence", 0) >= 0.7
    ]
    low_confidence_fixes = [
        f for f in fix_results if f.get("resolution_confidence", 0) < 0.7
    ]

    # Combine: high-confidence fixes → errors → low-confidence fixes
    combined = high_confidence_fixes + all_results + low_confidence_fixes

    return combined


def track_fix_effectiveness(session_id: str, hook_input: dict) -> None:
    """Track error_fix_effectiveness: flag session state when fix injected; on next Bash, record exit code.

    §8.3: error_fix_effectiveness trace.

    Args:
        session_id: Session ID
        hook_input: Hook input dict
    """
    try:
        from memory.injection import InjectionSessionState

        state = InjectionSessionState.load(session_id)
        if not state.error_state:
            return

        # Check if we previously injected a fix (marked by _fix_injected flag)
        fix_injected_data = state.error_state.get("_last_fix_injected")
        if not fix_injected_data:
            return

        tool_response = hook_input.get("tool_response", {})
        exit_code = tool_response.get("exitCode")

        if exit_code is None:
            return

        resolved = exit_code == 0
        outcome = "resolved" if resolved else "unresolved"
        egid = fix_injected_data.get("error_group_id", "unknown")

        # Emit effectiveness trace
        if emit_trace_event:
            try:
                from uuid import uuid4

                emit_trace_event(
                    event_type="error_fix_effectiveness",
                    data={
                        "input": f"Checking fix effectiveness for {egid}",
                        "output": f"Outcome: {outcome}, exit_code={exit_code}",
                        "metadata": {
                            "error_group_id": egid,
                            "resolved_without_retry": resolved,
                            "next_bash_exit_code": exit_code,
                        },
                    },
                    trace_id=uuid4().hex,
                    session_id=session_id,
                    tags=["capture", "error_detection"],
                )
            except Exception:
                pass

        # Prometheus metric
        if error_fix_effectiveness_total:
            try:
                project_name = detect_project(hook_input.get("cwd", os.getcwd()))
                error_fix_effectiveness_total.labels(
                    outcome=outcome,
                    project=project_name,
                ).inc()
            except Exception:
                pass

        # Clear the tracking flag
        state.error_state.pop("_last_fix_injected", None)
        state.save()

    except Exception:
        pass  # Never block for effectiveness tracking


def main() -> int:
    """PostToolUse hook entry point.

    Detects errors in Bash tool output and retrieves similar fixes from memory.
    Uses two-phase retrieval: semantic match error → follow error_group_id → inject paired fix.

    Returns:
        Exit code: Always 0 (graceful degradation)
    """
    start_time = time.perf_counter()
    project_name = "unknown"

    try:
        # Parse hook input from stdin
        try:
            hook_input = json.load(sys.stdin)
        except json.JSONDecodeError:
            logger.warning("malformed_hook_input")
            return 0

        # Validate Bash tool
        if hook_input.get("tool_name") != "Bash":
            logger.debug(
                "not_bash_tool", extra={"tool_name": hook_input.get("tool_name")}
            )
            return 0

        tool_response = hook_input.get("tool_response", {})

        _err_session_id = hook_input.get("session_id", "")
        if _err_session_id:
            os.environ["CLAUDE_SESSION_ID"] = _err_session_id

        # WP-6 §8.3: Track fix effectiveness from previous injection
        track_fix_effectiveness(_err_session_id, hook_input)

        # Check for error
        if not detect_error(tool_response):
            # No error detected - normal completion
            return 0

        # Extract error signature for search
        # Claude Code sends stdout/stderr separately
        stdout = tool_response.get("stdout", "")
        stderr = tool_response.get("stderr", "")
        output = stderr if stderr else stdout
        error_signature = extract_error_signature(output)

        # Search for similar error fixes
        config = get_config()
        search = MemorySearch(config)
        cwd = hook_input.get("cwd", os.getcwd())
        project_name = detect_project(cwd)

        try:
            # WP-6: Two-phase retrieval (§4.3 R2)
            results = two_phase_retrieval(
                search=search,
                error_signature=error_signature,
                project_name=project_name,
                session_id=_err_session_id,
            )

            if not results:
                # No similar fixes found - log for visibility
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_to_activity(
                    f"🔧 ErrorDetection: Error detected but no similar fixes found [{duration_ms:.0f}ms]",
                    INSTALL_DIR,
                )
                logger.debug(
                    "no_error_patterns_found", extra={"error": error_signature[:50]}
                )

                # Push trigger metrics even when no results
                try:
                    from memory.metrics_push import push_trigger_metrics_async

                    push_trigger_metrics_async(
                        trigger_type="error_detection",
                        status="empty",
                        project=project_name,
                        results_count=0,
                        duration_seconds=duration_ms / 1000.0,
                    )
                except ImportError:
                    pass
                return 0

            # Format and output
            # FIX #9: Add truncation indicator consistently
            error_display = error_signature[:100]
            if len(error_signature) > 100:
                error_display += "..."

            # Count fixes vs errors in results
            fix_count = sum(1 for r in results if r.get("subtype") == "fix")
            error_count = len(results) - fix_count

            output_parts = ["\n" + "=" * 70]
            output_parts.append("🔧 SIMILAR ERROR FIXES FOUND")
            if fix_count > 0:
                output_parts.append(
                    f"   ({error_count} similar errors, {fix_count} proven fixes)"
                )
            output_parts.append("=" * 70)
            output_parts.append(f"Current error: {error_display}")
            output_parts.append("")

            for i, fix in enumerate(results, 1):
                output_parts.append(format_error_pattern(fix, i))

            output_parts.append("=" * 70 + "\n")

            print("\n".join(output_parts))

            # WP-6 §8.3: Emit error_fix_injection Langfuse trace for each fix injected
            if emit_trace_event and fix_count > 0:
                try:
                    from uuid import uuid4

                    for fix_result in results:
                        if fix_result.get("subtype") != "fix":
                            continue
                        emit_trace_event(
                            event_type="error_fix_injection",
                            data={
                                "input": error_signature[:TRACE_CONTENT_MAX],
                                "output": fix_result.get("content", "")[
                                    :TRACE_CONTENT_MAX
                                ],
                                "metadata": {
                                    "error_group_id": fix_result.get(
                                        "error_group_id", ""
                                    ),
                                    "fix_point_id": fix_result.get("fix_point_id", ""),
                                    "resolution_confidence": fix_result.get(
                                        "resolution_confidence", 0
                                    ),
                                    "freshness_status": fix_result.get(
                                        "freshness_status", "unverified"
                                    ),
                                },
                            },
                            trace_id=uuid4().hex,
                            session_id=_err_session_id,
                            project_id=project_name,
                            tags=["capture", "error_detection"],
                        )
                except Exception:
                    logger.debug("trace_event_failed_error_fix_injection")

            # WP-6: Prometheus injection metric
            if error_fix_injections_total and fix_count > 0:
                error_fix_injections_total.labels(project=project_name).inc(fix_count)

            # WP-6 §8.3: Flag session state for effectiveness tracking
            if fix_count > 0 and _err_session_id:
                try:
                    from memory.injection import InjectionSessionState

                    state = InjectionSessionState.load(_err_session_id)
                    if state.error_state is None:
                        state.error_state = {}
                    # Store the last injected fix info for effectiveness tracking
                    first_fix = next(
                        (r for r in results if r.get("subtype") == "fix"), None
                    )
                    if first_fix:
                        state.error_state["_last_fix_injected"] = {
                            "error_group_id": first_fix.get("error_group_id", ""),
                            "fix_point_id": first_fix.get("fix_point_id", ""),
                            "injected_at": time.time(),
                        }
                        state.save()
                except Exception:
                    pass

            # SPEC-021: Langfuse trace for error retrieval
            if emit_trace_event:
                try:
                    from uuid import uuid4

                    best_score = max((r.get("score", 0) for r in results), default=0)
                    emit_trace_event(
                        event_type="error_retrieval",
                        data={
                            "input": error_signature[:TRACE_CONTENT_MAX],
                            "output": (
                                results[0].get("content", "")[:TRACE_CONTENT_MAX]
                                if results
                                else "No similar fixes found"
                            ),
                            "metadata": {
                                "collection": COLLECTION_CODE_PATTERNS,
                                "result_count": len(results),
                                "fix_count": fix_count,
                                "error_count": error_count,
                                "best_score": best_score,
                                "summary": f"Retrieved {error_count} errors + {fix_count} fixes (two-phase)",
                                "agent_name": os.environ.get(
                                    "CLAUDE_AGENT_NAME", "main"
                                ),
                                "agent_role": os.environ.get(
                                    "CLAUDE_AGENT_ROLE", "user"
                                ),
                            },
                        },
                        trace_id=uuid4().hex,
                        session_id=hook_input.get("session_id"),
                        project_id=project_name,
                        tags=["capture", "error_detection"],
                    )
                except Exception:
                    logger.debug("trace_event_failed_error_retrieval")

            duration_ms = (time.perf_counter() - start_time) * 1000
            log_to_activity(
                f"🔧 ErrorFixes retrieved {len(results)} results ({fix_count} fixes) [{duration_ms:.0f}ms]",
                INSTALL_DIR,
            )
            logger.info(
                "error_patterns_retrieved",
                extra={
                    "results_count": len(results),
                    "fix_count": fix_count,
                    "duration_ms": round(duration_ms, 2),
                    "error_signature": error_signature[:50],
                },
            )

            # Metrics (local)
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=COLLECTION_CODE_PATTERNS,
                    status="success",
                    project=project_name,
                ).inc()
            if retrieval_duration_seconds:
                retrieval_duration_seconds.observe(duration_ms / 1000.0)

            # TECH-DEBT-075: Push retrieval metrics to Pushgateway
            if push_retrieval_metrics_async:
                push_retrieval_metrics_async(
                    collection="code-patterns",
                    status="success" if results else "empty",
                    duration_seconds=duration_ms / 1000.0,
                    project=project_name,
                )

            # TECH-DEBT-142: Push hook duration to Pushgateway
            if push_hook_metrics_async:
                push_hook_metrics_async(
                    hook_name="PostToolUse_ErrorDetection",
                    duration_seconds=duration_ms / 1000.0,
                    success=True,
                    project=project_name,
                )

            # Push trigger metrics to Pushgateway
            try:
                from memory.metrics_push import push_trigger_metrics_async

                push_trigger_metrics_async(
                    trigger_type="error_detection",
                    status="success",
                    project=project_name,
                    results_count=len(results),
                    duration_seconds=duration_ms / 1000.0,
                )
            except ImportError:
                pass

        finally:
            search.close()

        return 0

    except Exception as e:
        logger.error(
            "hook_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )

        # Metrics (local)
        if memory_retrievals_total:
            memory_retrievals_total.labels(
                collection=COLLECTION_CODE_PATTERNS,
                status="failed",
                project=project_name,
            ).inc()

        # TECH-DEBT-142: Push hook duration to Pushgateway (error case)
        duration_seconds = time.perf_counter() - start_time
        if push_hook_metrics_async:
            push_hook_metrics_async(
                hook_name="PostToolUse_ErrorDetection",
                duration_seconds=duration_seconds,
                success=False,
                project=project_name,
            )

        # Push failure metrics
        try:
            from memory.metrics_push import push_trigger_metrics_async

            push_trigger_metrics_async(
                trigger_type="error_detection",
                status="failed",
                project=project_name,
                results_count=0,
                duration_seconds=duration_seconds,
            )
        except ImportError:
            pass

        return 0  # Graceful degradation


if __name__ == "__main__":
    sys.exit(main())
