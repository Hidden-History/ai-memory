#!/usr/bin/env python3
"""Langfuse Stop Hook — Session-Level Tier 1 Tracing.

Captures Claude Code conversation transcripts as Langfuse traces.
Fires when a Claude Code session ends (Stop hook).

Input (stdin JSON): {session_id, transcript_path, cwd}
Transcript (.jsonl at transcript_path): Each line is {role, content, token_count}
  - content may be a string or a list of content blocks

Fixes: BUG-151, BUG-152, BUG-154, BUG-155, BUG-156, BUG-157
PLAN-008 / SPEC-022 S2
"""

# LANGFUSE: Uses direct SDK (Path B). See LANGFUSE-INTEGRATION-SPEC.md §3.2, §7.1
# SDK VERSION: V3 ONLY. Use get_client(), start_as_current_observation(), propagate_attributes().
# Do NOT use Langfuse() constructor, start_span(), start_generation(), or langfuse_context.

import json
import logging
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Configure logging — INFO when DEBUG_HOOKS set, else WARNING
_log_level = logging.INFO if os.environ.get("DEBUG_HOOKS") else logging.WARNING
logging.basicConfig(level=_log_level, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Self-termination timeout — prevents hook from hanging Claude Code
HOOK_TIMEOUT_SECONDS = 30
# TD-241 FIX: 5s was too short for large transcripts. Configurable via env var.
# Default 15s: enough time for N child spans + network round-trip to local Langfuse.
try:
    FLUSH_TIMEOUT_SECONDS = int(os.environ.get("LANGFUSE_FLUSH_TIMEOUT_SECONDS", "15"))
except (ValueError, TypeError):
    FLUSH_TIMEOUT_SECONDS = 15
LANGFUSE_PAYLOAD_MAX_CHARS = 10000


def _timeout_handler(signum, frame):
    """Self-terminate if hook exceeds global timeout (signal.alarm)."""
    logger.warning(
        "Langfuse stop hook exceeded %ds timeout — self-terminating",
        HOOK_TIMEOUT_SECONDS,
    )
    sys.exit(0)


def _extract_text(content) -> str:
    """Extract text from a message content field.

    Content may be:
    - A plain string
    - A list of content blocks [{type, text, ...}, ...]
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f"[Tool: {block.get('name', 'unknown')}]")
                elif block.get("type") == "tool_result":
                    parts.append("[Tool Result]")
        return "\n".join(parts)
    return str(content)


def _read_transcript(transcript_path: str) -> list[dict]:
    """Read and parse a .jsonl transcript file.

    Each line: {role, content, token_count}
    Returns list of parsed message dicts.
    """
    messages = []
    path = Path(transcript_path)
    if not path.exists():
        logger.warning("Transcript file not found: %s", transcript_path)
        return messages

    try:
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    messages.append(msg)
                except json.JSONDecodeError:
                    logger.debug("Skipping malformed JSONL line %d", line_num)
    except OSError as e:
        logger.warning("Failed to read transcript file: %s", e)

    return messages


def _get_entry_role(msg: dict) -> str:
    """Get the role/type from a transcript entry.

    Claude Code V2.x transcript format: {"type": "user"|"assistant", "message": {...}}
    Older format (fallback): {"role": "user"|"assistant", "content": ...}
    """
    # New V2.x format uses "type" at the top level
    if "type" in msg and msg["type"] in ("user", "assistant"):
        return msg["type"]
    # Fallback: older format used "role" at the top level
    return msg.get("role", "unknown")


def _get_entry_content(msg: dict):
    """Get the content from a transcript entry.

    Claude Code V2.x format: msg["message"]["content"] (string or list of blocks)
    Older format (fallback): msg["content"] (string or list)
    """
    # New V2.x format: content nested under "message"
    if "message" in msg and isinstance(msg["message"], dict):
        return msg["message"].get("content", "")
    # Fallback: older format had content at top level
    return msg.get("content", "")


def _extract_model_and_usage(msg: dict) -> tuple:
    """Extract model name and usage data from a transcript entry.

    PLAN-014 G-04: Token usage enrichment for turn observations.

    Claude Code V2.x format stores these under "message":
      msg["message"]["model"] and msg["message"]["usage"]
    Older format may have them at the top level.

    Note: Claude Code transcripts may NOT include usage/model in all cases.
    If not present, returns (None, None) — callers must handle gracefully.
    """
    inner = msg.get("message", {}) if isinstance(msg.get("message"), dict) else {}
    model_name = inner.get("model") or msg.get("model")
    usage = inner.get("usage") or msg.get("usage")
    return model_name, usage


def _extract_thinking_blocks(msg: dict) -> list[dict]:
    """Extract thinking content blocks from a transcript entry.

    PLAN-014 G-02: Thinking block observation enrichment.

    Claude Code assistant turns may contain content blocks with type="thinking".
    V2.x format: msg["message"]["content"] is a list of blocks.

    Note: Thinking blocks may NOT be present in all transcript formats or may
    be redacted. Returns empty list if none found — callers must handle gracefully.
    """
    content = _get_entry_content(msg)
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "thinking"]


def _pair_turns(messages: list[dict]) -> list[dict]:
    """Pair user messages with their assistant responses.

    Handles both V2.x transcript format (type/message.content) and
    older format (role/content).

    Returns list of turn dicts with keys:
      user_input, assistant_output, user_tokens, assistant_tokens,
      model, usage, thinking_blocks
    """
    turns = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = _get_entry_role(msg)

        if role == "user":
            turn = {
                "user_input": _extract_text(_get_entry_content(msg)),
                "user_tokens": msg.get("token_count"),
            }
            # Look ahead for assistant response
            if i + 1 < len(messages) and _get_entry_role(messages[i + 1]) == "assistant":
                next_msg = messages[i + 1]
                turn["assistant_output"] = _extract_text(_get_entry_content(next_msg))
                turn["assistant_tokens"] = next_msg.get("token_count")
                # PLAN-014 G-04: Extract model and usage from assistant turn
                turn["model"], turn["usage"] = _extract_model_and_usage(next_msg)
                # PLAN-014 G-02: Extract thinking blocks from assistant turn
                turn["thinking_blocks"] = _extract_thinking_blocks(next_msg)
                i += 2
            else:
                turn["assistant_output"] = None
                turn["assistant_tokens"] = None
                turn["model"] = None
                turn["usage"] = None
                turn["thinking_blocks"] = []
                i += 1
            turns.append(turn)
        elif role == "assistant" and not turns:
            # Orphan assistant message at start — still capture it
            model, usage = _extract_model_and_usage(msg)
            thinking = _extract_thinking_blocks(msg)
            turns.append(
                {
                    "user_input": None,
                    "user_tokens": None,
                    "assistant_output": _extract_text(_get_entry_content(msg)),
                    "assistant_tokens": msg.get("token_count"),
                    "model": model,
                    "usage": usage,
                    "thinking_blocks": thinking,
                }
            )
            i += 1
        else:
            # System messages or already-paired assistant messages
            i += 1

    return turns


def _deterministic_trace_id(session_id: str) -> str | None:
    """Generate a deterministic trace ID from session_id for deduplication."""
    if not session_id:
        return None
    return uuid.uuid5(uuid.NAMESPACE_URL, f"langfuse-session:{session_id}").hex


def main():
    """Main entry point for Stop hook."""
    # Install global self-termination timeout (BUG-155 / signal.alarm best practice)
    # BUG-158: Skip signal registration in test environments to prevent SIGALRM leaks
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(HOOK_TIMEOUT_SECONDS)
        except (AttributeError, OSError):
            pass  # SIGALRM not available on Windows

    # ── Early kill-switch: only exit if EXPLICITLY disabled ──
    # Wave 1F: The LANGFUSE_ENABLED env var may not be in the subprocess environment
    # if it comes from docker/.env rather than settings.json. We therefore only do
    # a fast-exit here when LANGFUSE_ENABLED is explicitly set to a non-true value.
    # The full kill-switch check (including after env-file load) runs inside the try block.
    _early_enabled = os.environ.get("LANGFUSE_ENABLED")
    if _early_enabled is not None and _early_enabled.lower() != "true":
        sys.exit(0)
    _early_sessions = os.environ.get("LANGFUSE_TRACE_SESSIONS")
    if _early_sessions is not None and _early_sessions.lower() != "true":
        sys.exit(0)

    try:
        # ── BUG-151: Parse stdin JSON → {session_id, transcript_path, cwd} ──
        input_data = sys.stdin.read()
        if not input_data.strip():
            logger.debug("No input data — skipping trace")
            sys.exit(0)

        stdin_payload = json.loads(input_data)
    except Exception as e:
        logger.warning("Failed to parse stdin JSON: %s", e)
        sys.exit(0)  # Never block Claude Code

    try:
        # Add src to path for imports
        install_dir = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        sys.path.insert(0, os.path.join(install_dir, "src"))

        # Wave 1F: Load Langfuse env vars from docker/.env if not already set in environment.
        # Claude Code propagates env vars from settings.json, but when the Stop hook runs in
        # certain contexts (e.g., subagents, non-project-dir sessions), those vars may be absent.
        # Loading docker/.env as a fallback ensures credentials are always available.
        _env_file = os.path.join(install_dir, "docker", ".env")
        if os.path.isfile(_env_file):
            _langfuse_keys = (
                "LANGFUSE_ENABLED",
                "LANGFUSE_PUBLIC_KEY",
                "LANGFUSE_SECRET_KEY",
                "LANGFUSE_BASE_URL",
                "LANGFUSE_TRACE_SESSIONS",
            )
            _missing = [k for k in _langfuse_keys if not os.environ.get(k)]
            if _missing:
                try:
                    with open(_env_file, encoding="utf-8") as _ef:
                        for _line in _ef:
                            _line = _line.strip()
                            if not _line or _line.startswith("#") or "=" not in _line:
                                continue
                            _key, _, _val = _line.partition("=")
                            _key = _key.strip()
                            if _key in _missing and _key not in os.environ:
                                os.environ[_key] = _val.strip().strip('"').strip("'")
                    logger.info(
                        "Loaded Langfuse env vars from docker/.env: %s",
                        [k for k in _missing if os.environ.get(k)],
                    )
                except OSError as _e:
                    logger.warning("Failed to read docker/.env: %s", _e)

        # Wave 1F: Re-check kill-switch AFTER env file load (in case it was missing before)
        if os.environ.get("LANGFUSE_ENABLED", "false").lower() != "true":
            logger.info(
                "Langfuse disabled (LANGFUSE_ENABLED != true) — skipping session trace"
            )
            sys.exit(0)
        if os.environ.get("LANGFUSE_TRACE_SESSIONS", "true").lower() != "true":
            logger.info(
                "Session tracing disabled (LANGFUSE_TRACE_SESSIONS != true) — skipping"
            )
            sys.exit(0)

        # TD-241 DIAGNOSTIC: Log credential status at WARNING so it's visible without DEBUG_HOOKS.
        _pub = os.environ.get("LANGFUSE_PUBLIC_KEY")
        _sec = os.environ.get("LANGFUSE_SECRET_KEY")
        _url = os.environ.get("LANGFUSE_BASE_URL", "NOT SET")
        if not _pub or not _sec:
            logger.warning(
                "Langfuse credentials MISSING — no session trace will be created. "
                "PUBLIC_KEY=%s, SECRET_KEY=%s, BASE_URL=%s",
                "set" if _pub else "MISSING",
                "set" if _sec else "MISSING",
                _url,
            )
        else:
            logger.info(
                "Langfuse env: PUBLIC_KEY=set, SECRET_KEY=set, BASE_URL=%s, FLUSH_TIMEOUT=%ds",
                _url,
                FLUSH_TIMEOUT_SECONDS,
            )

        from memory.langfuse_config import get_langfuse_client
        # Check if Langfuse is enabled (config check only)
        if get_langfuse_client() is None:
            logger.warning(
                "Langfuse client unavailable — session trace skipped "
                "(check LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)"
            )
            sys.exit(0)

        # ── BUG-151: Extract fields from stdin, read .jsonl transcript ──
        session_id = stdin_payload.get("session_id", "")
        transcript_path = stdin_payload.get("transcript_path", "")
        cwd = stdin_payload.get("cwd", "")

        if not transcript_path:
            logger.debug("No transcript_path in stdin payload — skipping trace")
            sys.exit(0)

        messages = _read_transcript(transcript_path)
        if not messages:
            logger.warning(
                "Empty or missing transcript at %s — skipping session trace", transcript_path
            )
            sys.exit(0)

        # Pair user/assistant turns (BUG-154)
        turns = _pair_turns(messages)
        logger.info(
            "Transcript parsed: %d messages, %d turns, session=%s",
            len(messages),
            len(turns),
            session_id[:8] + "..." if len(session_id) > 8 else session_id,
        )

        # Build trace metadata
        now = datetime.now(tz=timezone.utc)  # BUG-157: timezone-aware
        project_id = os.environ.get("AI_MEMORY_PROJECT_ID", "")

        trace_metadata = {
            "project_id": project_id,
            "source": "claude_code_stop_hook",
            "cwd": cwd,
            "transcript_path": transcript_path,
        }
        if os.environ.get("PARZIVAL_ENABLED", "false").lower() == "true":
            trace_metadata["agent_id"] = "parzival"
        trace_metadata["agent_name"] = os.environ.get("CLAUDE_AGENT_NAME", "main")
        trace_metadata["agent_role"] = os.environ.get("CLAUDE_AGENT_ROLE", "user")

        # ── BUG-152: Derive root span input/output from conversation ──
        first_user_text = ""
        last_assistant_text = ""
        for msg in messages:
            if _get_entry_role(msg) == "user" and not first_user_text:
                first_user_text = _extract_text(_get_entry_content(msg))
            if _get_entry_role(msg) == "assistant":
                last_assistant_text = _extract_text(_get_entry_content(msg))

        # Deterministic trace ID for dedup (replaces Langfuse.create_trace_id)
        trace_id = _deterministic_trace_id(session_id) if session_id else None

        # ── V3 SDK: Create root observation + child spans ──
        # LANGFUSE-INTEGRATION-SPEC.md §7.1: Uses start_as_current_observation (V3)
        from langfuse import get_client as _get_v3_client, propagate_attributes

        langfuse_v3 = _get_v3_client()

        trace_kwargs = {}
        if trace_id:
            trace_kwargs["trace_context"] = {"trace_id": trace_id}

        with langfuse_v3.start_as_current_observation(
            as_type="span",
            name="claude_code_session",
            input=first_user_text[:LANGFUSE_PAYLOAD_MAX_CHARS] if first_user_text else None,
            output=last_assistant_text[:LANGFUSE_PAYLOAD_MAX_CHARS] if last_assistant_text else None,
            **trace_kwargs,
        ) as root_span:
            # Set session and trace attributes via propagate_attributes (V3 pattern)
            with propagate_attributes(
                session_id=session_id or None,
                user_id="claude_code_user",
            ):
                root_span.update_trace(
                    name="claude_code_session",
                    metadata={**trace_metadata, "turn_count": len(turns)},
                    tags=["session_trace", "tier1"],
                )

                # ── BUG-154: Child spans with BOTH input and output ──
                for i, turn in enumerate(turns, 1):
                    token_meta = {}
                    if turn.get("user_tokens") is not None:
                        token_meta["user_tokens"] = turn["user_tokens"]
                    if turn.get("assistant_tokens") is not None:
                        token_meta["assistant_tokens"] = turn["assistant_tokens"]

                    # PLAN-014 G-04: Include model and usage in turn metadata if available
                    # Note: Claude Code transcripts may not always include usage/model data.
                    # These fields are extracted best-effort; if absent, they are simply omitted.
                    turn_model = turn.get("model")
                    turn_usage = turn.get("usage")
                    if turn_model:
                        token_meta["model"] = turn_model
                    if turn_usage and isinstance(turn_usage, dict):
                        token_meta["usage"] = turn_usage

                    turn_input = turn.get("user_input") or ""
                    turn_output = turn.get("assistant_output") or ""

                    # PLAN-014 G-04: Use as_type="generation" when model/usage available,
                    # otherwise keep as "span" for backward compatibility
                    turn_type = "generation" if turn_model else "span"

                    with langfuse_v3.start_as_current_observation(
                        as_type=turn_type,
                        name=f"turn_{i}",
                        input=turn_input[:LANGFUSE_PAYLOAD_MAX_CHARS] if turn_input else None,
                    ) as turn_span:
                        update_kwargs = {
                            "output": turn_output[:LANGFUSE_PAYLOAD_MAX_CHARS] if turn_output else None,
                            "metadata": token_meta,
                        }
                        # PLAN-014 G-04: Set model and usage on generation observations
                        if turn_type == "generation":
                            update_kwargs["model"] = turn_model
                            if turn_usage and isinstance(turn_usage, dict):
                                update_kwargs["usage"] = turn_usage
                        turn_span.update(**update_kwargs)

                        # PLAN-014 G-02: Child span for thinking blocks if present
                        # Claude Code assistant turns may include content blocks with
                        # type="thinking". If found, capture as a child observation.
                        # Note: Thinking blocks may not be present in all transcript
                        # formats or may be redacted by Claude Code.
                        thinking_blocks = turn.get("thinking_blocks", [])
                        if thinking_blocks:
                            thinking_text = "\n".join(
                                b.get("thinking", b.get("text", ""))
                                for b in thinking_blocks
                            )
                            if thinking_text.strip():
                                with langfuse_v3.start_as_current_observation(
                                    as_type="span",
                                    name=f"turn_{i}_thinking",
                                    input=thinking_text[:LANGFUSE_PAYLOAD_MAX_CHARS],
                                ) as thinking_span:
                                    thinking_span.update(
                                        metadata={
                                            "block_count": len(thinking_blocks),
                                            "source": "extended_thinking",
                                        },
                                    )

        # ── BUG-155: flush() with timeout guard + logging ──
        logger.info(
            "Flushing Langfuse trace: session=%s turns=%d messages=%d",
            session_id,
            len(turns),
            len(messages),
        )
        try:
            remaining = signal.alarm(0)  # Save remaining global timeout

            def _flush_timeout_handler(signum, frame):
                raise TimeoutError(
                    f"Langfuse flush exceeded {FLUSH_TIMEOUT_SECONDS}s timeout"
                )

            old_handler = signal.signal(signal.SIGALRM, _flush_timeout_handler)
            signal.alarm(FLUSH_TIMEOUT_SECONDS)
            try:
                langfuse_v3.flush()
                logger.info("Langfuse flush completed successfully")
            except TimeoutError:
                logger.warning(
                    "Langfuse flush timed out after %ds — traces may be lost",
                    FLUSH_TIMEOUT_SECONDS,
                )
            finally:
                signal.alarm(0)  # Cancel flush timeout
                signal.signal(signal.SIGALRM, old_handler)
                signal.alarm(remaining)  # Restore global safety timeout
        except (AttributeError, OSError):
            # SIGALRM not available on Windows — flush without timeout
            langfuse_v3.flush()

        logger.info(
            "Langfuse trace created: session=%s turns=%d",
            session_id,
            len(turns),
        )

    except Exception as e:
        # CRITICAL: Never block Claude Code (SPEC-022 AC-11)
        logger.warning("Langfuse stop hook error (non-blocking): %s", e)

    sys.exit(0)


if __name__ == "__main__":
    main()
