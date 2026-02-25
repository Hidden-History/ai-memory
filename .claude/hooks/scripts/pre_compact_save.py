#!/usr/bin/env python3
"""PreCompact Hook - Capture session summaries BEFORE compaction.

This hook fires BEFORE Claude Code runs compaction (manual /compact or auto-compact).
It has access to the FULL transcript via transcript_path, making it the ideal place
to save session summaries for the "aha moment" in future sessions.

Hook Events:
- PreCompact (manual): Triggered by /compact command
- PreCompact (auto): Triggered when context window is full

Exit Codes:
- 0: Success (allow compaction to proceed)
- 1: Non-blocking error (allow compaction to proceed with warning)

Performance: <10s timeout (blocking before compaction is acceptable)
Pattern: Sync storage with zero vector, background embedding generation

2026 Best Practices:
- Sync QdrantClient for PreCompact (blocking allowed)
- Structured JSON logging with extra={} dict (never f-strings)
- Proper exception handling: ResponseHandlingException, UnexpectedResponse
- Graceful degradation: queue to file on any failure
- All Qdrant payload fields: snake_case
- Store to discussions collection (Memory System v2.0) for session continuity

Sources:
- Qdrant Python client: https://python-client.qdrant.tech/
- Claude Hooks reference: oversight/research/Claude_Hooks_reference.md
- Architecture: docs/memory settings/AI_MEMORY_ARCHITECTURE.md
"""

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

# Add src to path for imports (must be inline before importing from memory)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# CR-3.3: Use consolidated logging and transcript reading
from memory.hooks_common import log_to_activity, read_transcript, setup_hook_logging

logger = setup_hook_logging()

from memory.activity_log import log_precompact
from memory.config import COLLECTION_DISCUSSIONS
from memory.embeddings import EmbeddingClient, EmbeddingError
from memory.graceful import graceful_hook
from memory.project import detect_project
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client
from memory.queue import queue_operation
from memory.validation import compute_content_hash

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import memory_captures_total
except ImportError:
    logger.warning("metrics_module_unavailable")
    memory_captures_total = None

# TECH-DEBT-142: Import push metrics for Pushgateway
try:
    from memory.metrics_push import push_capture_metrics_async, push_hook_metrics_async
except ImportError:
    push_hook_metrics_async = None
    push_capture_metrics_async = None

# SPEC-021: Trace buffer for pipeline instrumentation
# NOTE: SPEC-021 §3.2 designates pre_compact_save for @observe() + flush()
# (long-lived process pattern). Phase 3 uses emit_trace_event consistently;
# migration to @observe() is deferred to Phase 4 (Langfuse SDK integration).
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

# Import Qdrant-specific exceptions for proper error handling
try:
    from qdrant_client.http.exceptions import (
        ApiException,
        ResponseHandlingException,
        UnexpectedResponse,
    )
    from qdrant_client.models import FieldCondition, Filter, MatchValue
except ImportError:
    # Graceful degradation if qdrant-client not installed
    ApiException = Exception
    ResponseHandlingException = Exception
    UnexpectedResponse = Exception
    Filter = None
    FieldCondition = None
    MatchValue = None

# Timeout configuration
PRECOMPACT_HOOK_TIMEOUT = int(os.getenv("PRECOMPACT_HOOK_TIMEOUT", "10"))  # Default 10s


def validate_hook_input(data: dict[str, Any]) -> str | None:
    """Validate PreCompact hook input against expected schema.

    Args:
        data: Parsed JSON input from Claude Code

    Returns:
        Error message if validation fails, None if valid
    """
    # Check required fields
    if "session_id" not in data:
        return "missing_session_id"
    if "cwd" not in data:
        return "missing_cwd"
    if "transcript_path" not in data:
        return "missing_transcript_path"
    if "hook_event_name" not in data:
        return "missing_hook_event_name"
    if data.get("hook_event_name") != "PreCompact":
        return f"wrong_hook_event: {data.get('hook_event_name')}"
    if "trigger" not in data:
        return "missing_trigger"
    # TECH-DEBT-097: safe .get() access for error message
    trigger = data.get("trigger", "")
    if trigger not in ["manual", "auto"]:
        return f"invalid_trigger: {trigger}"

    return None


# CR-3.3: read_transcript() moved to hooks_common.py


def analyze_transcript(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze transcript to extract key activities and conversation context.

    V2.1 Enhancement: Rich summary for post-compact injection.
    Extracts first prompt (task requirements), last 3-5 user prompts,
    and last 2 agent responses for conversation continuity.

    Args:
        entries: List of transcript entries

    Returns:
        Dict with analysis results including:
        - tools_used: List of tool names used
        - files_modified: List of file paths modified
        - user_prompts_count: Total user prompt count
        - first_user_prompt: First user prompt (task requirements)
        - last_user_prompts: Last 3-5 user prompts (recent context)
        - last_agent_responses: Last 2 agent responses (recent work)
        - total_entries: Total transcript entries
    """
    tools_used = set()
    files_modified = set()
    user_prompts = []  # Will store (turn_index, content) tuples
    assistant_responses = []  # Will store (turn_index, content) tuples

    for turn_index, entry in enumerate(entries):
        # Extract entry type and message content
        # Transcript format: entry.type = "user"/"assistant", content in entry.message.content
        entry_type = entry.get("type", "")
        message = entry.get("message", {})
        content = message.get("content", []) if isinstance(message, dict) else []

        if entry_type == "user":
            # User message content can be string or list
            prompt_text = ""
            if isinstance(content, str):
                prompt_text = content
            elif isinstance(content, list):
                # List of content items - concatenate text items
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        if text:
                            text_parts.append(text)
                prompt_text = "\n".join(text_parts)

            # Store non-trivial prompts (>20 chars, not just commands)
            if prompt_text and len(prompt_text.strip()) > 20:
                # Truncate very long prompts but keep more context than before
                truncated = (
                    prompt_text[:3000] if len(prompt_text) > 3000 else prompt_text
                )
                user_prompts.append((turn_index, truncated))

        elif entry_type == "assistant":
            # Assistant content is always a list
            response_text_parts = []
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")

                        if item_type == "tool_use":
                            tool_name = item.get("name", "")
                            if tool_name:
                                tools_used.add(tool_name)

                            # Extract file paths from Write/Edit tools
                            tool_input = item.get("input", {})
                            if tool_name in ["Write", "Edit", "NotebookEdit"]:
                                file_path = tool_input.get("file_path", "")
                                if file_path:
                                    files_modified.add(file_path)

                        elif item_type == "text":
                            text = item.get("text", "")
                            if text:
                                response_text_parts.append(text)

            # Store non-trivial responses
            response_text = "\n".join(response_text_parts)
            if response_text and len(response_text.strip()) > 50:
                # Truncate very long responses but keep meaningful context
                truncated = (
                    response_text[:2000] if len(response_text) > 2000 else response_text
                )
                assistant_responses.append((turn_index, truncated))

    # Extract key prompts for rich summary
    # First prompt: Task requirements (often sets the goal)
    first_user_prompt = user_prompts[0][1] if user_prompts else ""

    # Last 3-5 user prompts: Recent context before compaction
    # Take last 5, but if first prompt is in there, we already have it separately
    last_user_prompts = []
    if len(user_prompts) > 1:
        # Get last 5, excluding first if it would be duplicated
        recent_prompts = (
            user_prompts[-5:] if len(user_prompts) >= 5 else user_prompts[1:]
        )
        last_user_prompts = [
            {"turn": idx, "content": content} for idx, content in recent_prompts
        ]
    elif len(user_prompts) == 1:
        # Only one prompt - it's both first and last
        last_user_prompts = []

    # Last 2 agent responses: Recent work/explanations
    last_agent_responses = []
    if assistant_responses:
        recent_responses = assistant_responses[-2:]
        last_agent_responses = [
            {"turn": idx, "content": content} for idx, content in recent_responses
        ]

    return {
        "tools_used": sorted(tools_used),
        "files_modified": sorted(files_modified),
        "user_prompts_count": len(user_prompts),
        "first_user_prompt": first_user_prompt,
        "last_user_prompts": last_user_prompts,
        "last_agent_responses": last_agent_responses,
        "total_entries": len(entries),
    }


def build_session_summary(
    hook_input: dict[str, Any], transcript_analysis: dict[str, Any]
) -> dict[str, Any]:
    """Build rich session summary from transcript analysis.

    V2.1 Enhancement: Rich summary includes conversation context for post-compact injection.
    This eliminates the need for session_start.py to query individual messages.

    Args:
        hook_input: Validated hook input with metadata
        transcript_analysis: Analysis results from analyze_transcript()

    Returns:
        Dictionary with formatted session summary including:
        - First user prompt (task requirements)
        - Last 3-5 user prompts (recent context)
        - Last 2 agent responses (recent work)
        - Structured metadata
    """
    session_id = hook_input["session_id"]
    cwd = hook_input["cwd"]
    trigger = hook_input["trigger"]
    custom_instructions = hook_input.get("custom_instructions", "")

    # Extract project name from cwd path
    project_name = detect_project(cwd)

    # Build rich summary content optimized for post-compact context injection
    summary_parts = [
        f"Session Summary: {project_name}",
        f"Session ID: {session_id}",
        f"Compaction Trigger: {trigger}",
        "",
        f"Tools Used: {', '.join(transcript_analysis['tools_used']) if transcript_analysis['tools_used'] else 'None'}",
        f"Files Modified ({len(transcript_analysis['files_modified'])}): {', '.join(transcript_analysis['files_modified'][:10])}",
        f"User Interactions: {transcript_analysis['user_prompts_count']} prompts",
    ]

    if custom_instructions:
        summary_parts.append(f"\nUser Instructions: {custom_instructions}")

    # V2.1: Include first user prompt (task requirements)
    first_prompt = transcript_analysis.get("first_user_prompt", "")
    if first_prompt:
        summary_parts.extend(["", "Key Activities:", f"- User goals: {first_prompt}"])

    # V2.1: Include last user prompts for follow-up context
    last_prompts = transcript_analysis.get("last_user_prompts", [])
    if last_prompts:
        # Add last prompt as "follow-up work" in key activities
        last_prompt_content = (
            last_prompts[-1].get("content", "") if last_prompts else ""
        )
        if last_prompt_content and last_prompt_content != first_prompt:
            summary_parts.append(f"- Follow-up work: {last_prompt_content}")

    summary_content = "\n".join(summary_parts)

    # Return structured data for storage with rich context
    return {
        "content": summary_content,
        "group_id": project_name,
        "memory_type": "session",
        "source_hook": "PreCompact",
        "session_id": session_id,
        "importance": (
            "high" if trigger == "auto" else "normal"
        ),  # Auto-compact = long session = high importance
        # V2.1: Rich conversation context for post-compact injection
        "first_user_prompt": first_prompt,
        "last_user_prompts": transcript_analysis.get("last_user_prompts", []),
        "last_agent_responses": transcript_analysis.get("last_agent_responses", []),
        "session_metadata": {
            "trigger": trigger,
            "tools_used": transcript_analysis["tools_used"],
            "files_modified": len(transcript_analysis["files_modified"]),
            "files_list": transcript_analysis["files_modified"][
                :20
            ],  # Store first 20 file paths
            "user_interactions": transcript_analysis["user_prompts_count"],
            "transcript_entries": transcript_analysis["total_entries"],
        },
    }


def store_session_summary(summary_data: dict[str, Any]) -> bool:
    """Store session summary to discussions collection.

    Args:
        summary_data: Session summary data to store

    Returns:
        bool: True if stored successfully, False if queued (still success)

    Raises:
        No exceptions - all errors handled gracefully
    """
    try:
        # Store WITHOUT embedding generation for <10s completion
        # Pattern: Store with pending status, background process generates embeddings
        import uuid

        from qdrant_client.models import PointStruct

        from memory.models import EmbeddingStatus
        from memory.validation import compute_content_hash

        # Build payload
        content_hash = compute_content_hash(summary_data["content"])
        memory_id = str(uuid.uuid4())

        # SPEC-021: Pipeline trace context for pre_compact
        trace_id = None  # PreCompact doesn't receive trace_id from capture hook
        pc_session_id = summary_data.get("session_id", "")
        pc_project_id = summary_data.get("group_id", "")

        # SPEC-021: 2_log span — content captured for processing
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="2_log",
                    data={
                        "input": {"content_length": len(summary_data["content"])},
                        "output": {"log_path": str(os.path.join(INSTALL_DIR, "logs", "activity.log"))},
                        "metadata": {"log_path": str(os.path.join(INSTALL_DIR, "logs", "activity.log"))},
                    },
                    trace_id=trace_id, session_id=pc_session_id, project_id=pc_project_id,
                )
            except Exception:
                pass

        # SPEC-021: 3_detect span — content type is predetermined (session summary)
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="3_detect",
                    data={
                        "input": {"content_length": len(summary_data["content"])},
                        "output": {"detected_type": "session"},
                        "metadata": {"detected_type": "session", "confidence": 1.0},
                    },
                    trace_id=trace_id,
                    session_id=pc_session_id,
                    project_id=pc_project_id,
                )
            except Exception:
                pass

        # SPEC-021: Default scan tracking vars
        scan_action = "skipped"
        scan_findings = []
        scan_actually_ran = False
        scan_input_length = len(summary_data["content"])

        # SPEC-009: Security scanning before storage
        try:
            from memory.config import get_config as _get_sec_config

            sec_config = _get_sec_config()
            if sec_config.security_scanning_enabled:
                try:
                    from memory.security_scanner import ScanAction, SecurityScanner

                    scanner = SecurityScanner(enable_ner=False)
                    scan_result = scanner.scan(summary_data["content"], source_type="user_session")
                    scan_actually_ran = True
                    scan_action = scan_result.action.value if hasattr(scan_result.action, 'value') else str(scan_result.action)
                    scan_findings = scan_result.findings

                    if scan_result.action == ScanAction.BLOCKED:
                        logger.warning(
                            "session_summary_blocked_secrets",
                            extra={
                                "session_id": summary_data["session_id"],
                                "group_id": summary_data["group_id"],
                                "findings_count": len(scan_result.findings),
                            },
                        )
                        # SPEC-021: 4_scan (BLOCKED) + pipeline_terminated
                        if emit_trace_event:
                            try:
                                emit_trace_event(
                                    event_type="4_scan",
                                    data={
                                        "input": {"content_length": scan_input_length},
                                        "output": {"scan_result": "blocked"},
                                        "metadata": {"scan_result": "blocked", "pii_found": False, "secrets_found": True},
                                    },
                                    trace_id=trace_id, session_id=pc_session_id, project_id=pc_project_id,
                                )
                            except Exception:
                                pass
                            try:
                                emit_trace_event(
                                    event_type="pipeline_terminated",
                                    data={"metadata": {"reason": "scan_blocked", "scan_blocked": True}},
                                    trace_id=trace_id, session_id=pc_session_id, project_id=pc_project_id,
                                )
                            except Exception:
                                pass
                        return False
                    elif scan_result.action == ScanAction.MASKED:
                        summary_data["content"] = scan_result.content
                except ImportError:
                    logger.warning(
                        "security_scanner_unavailable", extra={"hook": "PreCompact"}
                    )
        except Exception as e:
            logger.error(
                "security_scan_failed", extra={"hook": "PreCompact", "error": str(e)}
            )

        # SPEC-021: 4_scan span (non-blocked paths) — only emit if scan actually ran
        if emit_trace_event and scan_actually_ran:
            try:
                pii_found = any(
                    hasattr(f, 'finding_type') and f.finding_type.name.startswith("PII_")
                    for f in scan_findings
                )
                secrets_found = any(
                    hasattr(f, 'finding_type') and f.finding_type.name.startswith("SECRET_")
                    for f in scan_findings
                )
                emit_trace_event(
                    event_type="4_scan",
                    data={
                        "input": {"content_length": scan_input_length},
                        "output": {"scan_result": scan_action},
                        "metadata": {"scan_result": scan_action, "pii_found": pii_found, "secrets_found": secrets_found},
                    },
                    trace_id=trace_id, session_id=pc_session_id, project_id=pc_project_id,
                )
            except Exception:
                pass

        # SPEC-021: 5_chunk span — session summaries stored as single whole chunk
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="5_chunk",
                    data={
                        "input": {"content_length": len(summary_data["content"])},
                        "output": {"num_chunks": 1, "chunk_type": "whole"},
                        "metadata": {"num_chunks": 1, "chunk_type": "whole"},
                    },
                    trace_id=trace_id, session_id=pc_session_id, project_id=pc_project_id,
                )
            except Exception:
                pass

        # Generate embedding
        embedding_status = EmbeddingStatus.PENDING.value
        vector = [0.0] * 768  # Default placeholder

        try:
            embed_client = EmbeddingClient()
            embeddings = embed_client.embed([summary_data["content"]])
            vector = embeddings[0]
            embedding_status = EmbeddingStatus.COMPLETE.value
            logger.info(
                "embedding_generated",
                extra={"memory_id": memory_id, "dimensions": len(vector)},
            )
        except EmbeddingError as e:
            logger.warning(
                "embedding_failed_using_placeholder",
                extra={"error": str(e), "memory_id": memory_id},
            )
            # Continue with zero vector - will be backfilled later

        # SPEC-021: 6_embed span — embedding generation
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="6_embed",
                    data={
                        "input": {"num_chunks": 1},
                        "output": {"embedding_status": embedding_status, "dimensions": len(vector)},
                        "metadata": {"embedding_status": embedding_status, "num_vectors": 1},
                    },
                    trace_id=trace_id, session_id=pc_session_id, project_id=pc_project_id,
                )
            except Exception:
                pass

        payload = {
            "content": summary_data["content"],
            "content_hash": content_hash,
            "group_id": summary_data["group_id"],
            "type": summary_data["memory_type"],
            "source_hook": summary_data["source_hook"],
            "session_id": summary_data["session_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),  # V2.1: Explicit created_at
            "embedding_status": embedding_status,
            "embedding_model": "jina-embeddings-v2-base-en",
            "importance": summary_data.get("importance", "normal"),
            # V2.1: Rich conversation context for post-compact injection
            "first_user_prompt": summary_data.get("first_user_prompt", ""),
            "last_user_prompts": summary_data.get("last_user_prompts", []),
            "last_agent_responses": summary_data.get("last_agent_responses", []),
            "session_metadata": summary_data.get("session_metadata", {}),
        }

        # Store to discussions collection (v2.0)
        client = get_qdrant_client()
        client.upsert(
            collection_name=COLLECTION_DISCUSSIONS,
            points=[PointStruct(id=memory_id, vector=vector, payload=payload)],
        )

        # SPEC-021: 7_store span — data persisted to Qdrant
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="7_store",
                    data={
                        "input": {"num_points": 1},
                        "output": {"collection": COLLECTION_DISCUSSIONS, "points_stored": 1},
                        "metadata": {"collection": COLLECTION_DISCUSSIONS, "points_stored": 1},
                    },
                    trace_id=trace_id, session_id=pc_session_id, project_id=pc_project_id,
                )
            except Exception:
                pass

        # SPEC-021: 8_enqueue span — PreCompact does not use classifier
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="8_enqueue",
                    data={
                        "input": {"point_id": memory_id},
                        "output": {"enqueued": False, "collection": COLLECTION_DISCUSSIONS},
                        "metadata": {"collection": COLLECTION_DISCUSSIONS, "current_type": "session", "reason": "classifier_not_integrated"},
                    },
                    trace_id=trace_id, session_id=pc_session_id, project_id=pc_project_id,
                )
            except Exception:
                pass

        # Structured logging
        logger.info(
            "session_summary_stored",
            extra={
                "memory_id": memory_id,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"],
                "source_hook": "PreCompact",
                "embedding_status": "pending",
            },
        )

        # Metrics: Increment capture counter on success (local)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="success",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
            ).inc()

        # TECH-DEBT-075: Push capture metrics to Pushgateway
        if push_capture_metrics_async:
            push_capture_metrics_async(
                hook_type="PreCompact",
                status="success",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
                count=1,
            )

        return True

    except ResponseHandlingException as e:
        # Handle request/response errors (includes 429 rate limiting)
        logger.warning(
            "qdrant_response_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"],
            },
        )
        queue_operation(summary_data)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
            ).inc()

        # TECH-DEBT-075: Push capture metrics to Pushgateway
        if push_capture_metrics_async:
            push_capture_metrics_async(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
                count=1,
            )
        return False

    except UnexpectedResponse as e:
        # Handle HTTP errors from Qdrant
        logger.warning(
            "qdrant_unexpected_response",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"],
            },
        )
        queue_operation(summary_data)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
            ).inc()

        # TECH-DEBT-075: Push capture metrics to Pushgateway
        if push_capture_metrics_async:
            push_capture_metrics_async(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
                count=1,
            )
        return False

    except QdrantUnavailable as e:
        # Queue to file on Qdrant failure (graceful degradation)
        logger.warning(
            "qdrant_unavailable_queuing",
            extra={
                "error": str(e),
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"],
            },
        )

        queue_success = queue_operation(summary_data)
        if queue_success:
            logger.info(
                "session_summary_queued",
                extra={
                    "session_id": summary_data["session_id"],
                    "group_id": summary_data["group_id"],
                },
            )
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="PreCompact",
                    status="queued",
                    project=summary_data["group_id"] or "unknown",
                    collection="discussions",
                ).inc()
        else:
            logger.error(
                "queue_failed",
                extra={
                    "session_id": summary_data["session_id"],
                    "group_id": summary_data["group_id"],
                },
            )
            if memory_captures_total:
                memory_captures_total.labels(
                    hook_type="PreCompact",
                    status="failed",
                    project=summary_data["group_id"] or "unknown",
                    collection="discussions",
                ).inc()

            # TECH-DEBT-075: Push capture metrics to Pushgateway
            if push_capture_metrics_async:
                push_capture_metrics_async(
                    hook_type="PreCompact",
                    status="failed",
                    project=summary_data["group_id"] or "unknown",
                    collection="discussions",
                    count=1,
                )

        return False

    except ApiException as e:
        # Handle general Qdrant API errors
        logger.warning(
            "qdrant_api_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"],
            },
        )
        queue_operation(summary_data)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
            ).inc()

        # TECH-DEBT-075: Push capture metrics to Pushgateway
        if push_capture_metrics_async:
            push_capture_metrics_async(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
                count=1,
            )
        return False

    except Exception as e:
        # Handle all other exceptions gracefully
        logger.error(
            "storage_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_id": summary_data["session_id"],
                "group_id": summary_data["group_id"],
            },
        )

        queue_operation(summary_data)
        if memory_captures_total:
            memory_captures_total.labels(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
            ).inc()

        # TECH-DEBT-075: Push capture metrics to Pushgateway
        if push_capture_metrics_async:
            push_capture_metrics_async(
                hook_type="PreCompact",
                status="queued",
                project=summary_data["group_id"] or "unknown",
                collection="discussions",
                count=1,
            )
        return False


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutError("Storage timeout exceeded")


def should_store_summary(summary_data: dict[str, Any]) -> bool:
    """Validate if summary has meaningful content worth storing.

    Args:
        summary_data: Session summary data with session_metadata field

    Returns:
        False if summary has no meaningful content, True otherwise
    """
    metadata = summary_data.get("session_metadata", {})

    # Extract structured data from session_metadata
    tools_used = metadata.get("tools_used", [])
    files_modified = metadata.get("files_modified", 0)
    user_interactions = metadata.get("user_interactions", 0)

    # Skip if no tools used AND no files modified AND 0 user prompts
    has_no_activity = (
        len(tools_used) == 0 and files_modified == 0 and user_interactions == 0
    )

    if has_no_activity:
        return False

    return True


def check_duplicate_hash(content_hash: str, group_id: str, client) -> str | None:
    """Check if content hash already exists in recent memories.

    Args:
        content_hash: SHA256 hash of content
        group_id: Project identifier
        client: QdrantClient instance

    Returns:
        Existing memory ID if duplicate found, None otherwise
    """
    # Check if Qdrant models are available
    if Filter is None or FieldCondition is None or MatchValue is None:
        logger.warning("qdrant_models_unavailable", extra={"group_id": group_id})
        return None  # Fail open - allow storage

    try:
        # Only check recent memories (limit 100) to avoid slow queries
        results, _ = client.scroll(
            collection_name=COLLECTION_DISCUSSIONS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="group_id", match=MatchValue(value=group_id)),
                    FieldCondition(
                        key="content_hash", match=MatchValue(value=content_hash)
                    ),
                ]
            ),
            limit=100,
        )

        if results:
            return str(results[0].id)

        return None

    except Exception as e:
        # Fail open on error - allow storage
        logger.warning(
            "duplicate_check_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "group_id": group_id,
            },
        )
        return None


@graceful_hook
def main() -> int:
    """PreCompact hook entry point.

    Reads hook input from stdin, validates it, reads transcript,
    analyzes transcript, builds session summary, and stores it.

    Returns:
        Exit code: 0 (success - allow compaction) or 1 (non-blocking error)
    """
    start_time = time.perf_counter()
    summary_data = None

    try:
        # Read hook input from stdin (Claude Code convention)
        raw_input = sys.stdin.read()

        # Handle malformed JSON
        try:
            hook_input = json.loads(raw_input)
        except json.JSONDecodeError as e:
            logger.error(
                "malformed_json",
                extra={"error": str(e), "input_preview": raw_input[:100]},
            )
            return 0  # Allow compaction to proceed

        # Validate schema
        validation_error = validate_hook_input(hook_input)
        if validation_error:
            logger.info(
                "validation_failed",
                extra={
                    "reason": validation_error,
                    "session_id": hook_input.get("session_id"),
                },
            )
            return 0  # Allow compaction to proceed

        # Read transcript from file
        transcript_path = hook_input["transcript_path"]
        transcript_entries = read_transcript(transcript_path)

        if not transcript_entries:
            logger.info(
                "no_transcript_skipping",
                extra={
                    "session_id": hook_input.get("session_id"),
                    "transcript_path": transcript_path,
                },
            )
            # User notification - no transcript to save
            print(
                "📤 AI Memory: No session transcript to save (empty transcript)",
                file=sys.stderr,
            )
            return 0  # Allow compaction to proceed

        # Analyze transcript
        transcript_analysis = analyze_transcript(transcript_entries)

        # Build session summary
        summary_data = build_session_summary(hook_input, transcript_analysis)

        # Extract project name once for validation checks
        project = summary_data.get("group_id", "unknown")

        # Validation 1: Check if summary has meaningful content
        if not should_store_summary(summary_data):
            log_to_activity("⏭️  PreCompact skipped: Empty session (no activity)")
            logger.info(
                "summary_skipped_empty",
                extra={
                    "session_id": summary_data["session_id"],
                    "group_id": project,
                    "reason": "no_activity",
                },
            )
            print(
                f"📤 AI Memory: Skipping empty session summary for {project}",
                file=sys.stderr,
            )
            return 0  # Allow compaction to proceed

        # Validation 2: Check for duplicate content hash
        content_hash = compute_content_hash(summary_data["content"])

        try:
            client = get_qdrant_client()
            duplicate_id = check_duplicate_hash(content_hash, project, client)

            if duplicate_id:
                log_to_activity(
                    f"⏭️  PreCompact skipped: Duplicate content (hash: {content_hash[:16]})"
                )
                logger.info(
                    "summary_skipped_duplicate",
                    extra={
                        "session_id": summary_data["session_id"],
                        "group_id": project,
                        "content_hash": content_hash,
                        "duplicate_id": duplicate_id,
                        "reason": "duplicate_hash",
                    },
                )
                print(
                    f"📤 AI Memory: Skipping duplicate session summary for {project}",
                    file=sys.stderr,
                )
                return 0  # Allow compaction to proceed
        except Exception as e:
            # Fail open on duplicate check error - allow storage
            logger.warning(
                "duplicate_check_error",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "group_id": project,
                },
            )

        # Set up timeout using signal (Unix only)
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(PRECOMPACT_HOOK_TIMEOUT)
        except (AttributeError, ValueError):
            # SIGALRM not available (Windows) - proceed without timeout
            pass

        stored = None
        try:
            # Store session summary synchronously
            stored = store_session_summary(summary_data)
        except TimeoutError:
            # Queue to file on timeout
            logger.warning(
                "storage_timeout",
                extra={
                    "session_id": summary_data["session_id"],
                    "timeout": PRECOMPACT_HOOK_TIMEOUT,
                },
            )
            queue_operation(summary_data)
        finally:
            # Cancel alarm
            try:
                signal.alarm(0)
            except (AttributeError, ValueError):
                pass

        # User notification via stderr (visible to user, not Claude)
        project = summary_data.get("group_id", "unknown")

        # TECH-DEBT-142: Push hook duration to Pushgateway
        duration_ms = (time.perf_counter() - start_time) * 1000
        trigger = hook_input["trigger"]
        if stored is False:
            # Content was blocked by SecurityScanner — do not claim success
            logger.warning(
                "session_summary_skipped",
                extra={"session_id": summary_data["session_id"], "reason": "blocked"},
            )
            if push_hook_metrics_async:
                push_hook_metrics_async(
                    hook_name="PreCompact",
                    duration_seconds=duration_ms / 1000,
                    success=False,
                    project=project,
                )
            print(
                f"⚠️  AI Memory: Session summary blocked/skipped for {project} (trigger: {trigger}) [{duration_ms:.0f}ms]",
                file=sys.stderr,
            )
        else:
            if push_hook_metrics_async:
                push_hook_metrics_async(
                    hook_name="PreCompact",
                    duration_seconds=duration_ms / 1000,
                    success=True,
                    project=project,
                )
            print(
                f"📤 AI Memory: Session summary saved for {project} (trigger: {trigger}) [{duration_ms:.0f}ms]",
                file=sys.stderr,
            )

        # Activity log with full content
        tools_list = (
            ", ".join(transcript_analysis["tools_used"])
            if transcript_analysis["tools_used"]
            else "None"
        )
        files_count = len(transcript_analysis["files_modified"])
        prompts_count = transcript_analysis["user_prompts_count"]

        # Log summary header
        session_id = summary_data.get("session_id", "unknown")
        session_short = session_id[:8] if len(session_id) >= 8 else session_id

        # TECH-DEBT-014: Comprehensive logging with full session content
        metadata = {
            "tools_used": transcript_analysis["tools_used"],
            "files_modified": len(transcript_analysis["files_modified"]),
            "prompts_count": transcript_analysis["user_prompts_count"],
            "content_hash": content_hash,
        }
        log_precompact(
            project, session_short, summary_data["content"], metadata, duration_ms
        )

        # ALWAYS exit 0 to allow compaction to proceed
        return 0

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "hook_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )

        # TECH-DEBT-142: Push hook duration to Pushgateway (error case)
        if push_hook_metrics_async:
            duration_seconds = time.perf_counter() - start_time
            # Try to get project from summary_data if available
            project = "unknown"
            if "summary_data" in dir() and summary_data:
                project = summary_data.get("group_id", "unknown")
            push_hook_metrics_async(
                hook_name="PreCompact",
                duration_seconds=duration_seconds,
                success=False,
                project=project,
            )

        # Non-blocking error - allow compaction to proceed
        return 0


if __name__ == "__main__":
    sys.exit(main())
