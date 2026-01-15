"""Test helpers for SessionStart hook.

This module imports the actual functions from the hook script
so we can test them in isolation.

Once .claude/hooks/scripts/session_start.py is implemented,
these imports will work.
"""

import sys
import os

# Add hooks scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "scripts"))

# Import functions from session_start.py
try:
    from session_start import (
        parse_hook_input,
        build_session_query,
        format_context,
        format_memory_entry,
        log_session_retrieval
    )
except ImportError:
    # Hook script doesn't exist yet - tests will fail as expected (RED phase)
    def parse_hook_input():
        raise NotImplementedError("session_start.py not implemented yet")

    def build_session_query(project_name, cwd):
        raise NotImplementedError("session_start.py not implemented yet")

    def format_context(results, project_name, token_budget=2000):
        raise NotImplementedError("session_start.py not implemented yet")

    def format_memory_entry(memory, truncate=False, max_chars=500):
        raise NotImplementedError("session_start.py not implemented yet")

    def log_session_retrieval(session_id, project, query, results, duration_ms):
        raise NotImplementedError("session_start.py not implemented yet")
