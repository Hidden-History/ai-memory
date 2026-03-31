#!/usr/bin/env python3
"""Shared utilities for AI Memory hook configuration scripts.

TD-338: Extracted from generate_settings.py and merge_settings.py to
eliminate duplication. Both scripts define identical _hook_cmd() and
the same Langfuse env var block — centralised here.
"""

import os

# SessionStart matcher triggers that are vestigial as of v2.2.0+ and must be
# stripped on every merge. 'startup' was removed by DEC-054; 'clear' by DEC-055.
_STALE_SESSION_TRIGGERS: frozenset[str] = frozenset({"startup", "clear"})


def normalize_matcher(
    matcher: str,
    stale: frozenset[str] = _STALE_SESSION_TRIGGERS,
    fallback: str = "resume|compact",
) -> str:
    """Strip stale triggers from a SessionStart matcher string.

    Args:
        matcher: The matcher string to normalize (e.g. "startup|resume|compact|clear")
        stale: Set of trigger names to remove (defaults to _STALE_SESSION_TRIGGERS)
        fallback: Value to use when all parts are stripped (defaults to "resume|compact")

    Returns:
        Normalized matcher with stale triggers removed, or fallback if all stripped.
    """
    parts = [p.strip() for p in matcher.split("|") if p.strip() not in stale]
    return "|".join(parts) if parts else fallback


def _hook_cmd(script_name: str) -> str:
    """Generate gracefully-degrading hook command. Exits 0 if installation missing.

    Args:
        script_name: The hook script filename (e.g. 'session_start.py')

    Returns:
        Shell command string that runs the hook if the file exists, else exits 0.
    """
    script = f"$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/{script_name}"
    python = "$AI_MEMORY_INSTALL_DIR/.venv/bin/python"
    return f'[ -f "{script}" ] && "{python}" "{script}" || true'


def get_langfuse_env_section() -> dict:
    """Return Langfuse env vars dict if LANGFUSE_ENABLED=true, else empty dict.

    Both generate_settings.py and merge_settings.py need the same 6 env vars
    with the same defaults. Centralised here to stay DRY (TD-338).
    """
    if os.environ.get("LANGFUSE_ENABLED", "").lower() != "true":
        return {}
    return {
        "LANGFUSE_ENABLED": "true",
        "LANGFUSE_PUBLIC_KEY": os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        "LANGFUSE_SECRET_KEY": os.environ.get("LANGFUSE_SECRET_KEY", ""),
        "LANGFUSE_BASE_URL": os.environ.get(
            "LANGFUSE_BASE_URL", "http://localhost:23100"
        ),
        "LANGFUSE_TRACE_HOOKS": os.environ.get("LANGFUSE_TRACE_HOOKS", "true"),
        "LANGFUSE_TRACE_SESSIONS": os.environ.get("LANGFUSE_TRACE_SESSIONS", "true"),
    }
