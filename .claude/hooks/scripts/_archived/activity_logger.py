#!/usr/bin/env python3
"""Universal Activity Logger - Captures ALL Claude Code hook events.

This provides comprehensive visibility into everything Claude is doing.
Captures: PreToolUse, PostToolUse, SessionEnd, Stop, SubagentStop,
          UserPromptSubmit, Notification, PermissionRequest

For performance, this hook is designed to be fast and never block.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

# CR-4.3: Use Path operations instead of string concatenation
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
sys.path.insert(0, str(Path(INSTALL_DIR) / "src"))

from memory.activity_log import (
    log_pre_tool_use, log_post_tool_use, log_session_end,
    log_stop, log_subagent_stop, log_user_prompt, log_notification,
    log_permission_request
)
from memory.project import detect_project


def main():
    """Route hook events to appropriate activity loggers."""
    logger = logging.getLogger("bmad.memory.activity")
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        # CR-4.1: Log malformed input before graceful degradation
        logger.warning("malformed_hook_input", extra={"error": str(e)})
        return 0

    hook_event = hook_input.get("hook_event_name", "")
    cwd = hook_input.get("cwd", os.getcwd())
    project = detect_project(cwd)

    # Route to appropriate logger based on hook event
    if hook_event == "PreToolUse":
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})
        log_pre_tool_use(tool_name, tool_input, project)

    elif hook_event == "PostToolUse":
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})
        tool_response = hook_input.get("tool_response", {})
        log_post_tool_use(tool_name, tool_input, tool_response, project)

    elif hook_event == "SessionEnd":
        reason = hook_input.get("reason", "unknown")
        log_session_end(project, reason, 0)

    elif hook_event == "Stop":
        stop_hook_active = hook_input.get("stop_hook_active", False)
        log_stop(project, stop_hook_active)

    elif hook_event == "SubagentStop":
        agent_id = hook_input.get("agent_id", "unknown")
        log_subagent_stop(agent_id, project)

    elif hook_event == "UserPromptSubmit":
        prompt = hook_input.get("prompt", "")
        log_user_prompt(prompt, project)  # CR-4.2: Pass project for consistency

    elif hook_event == "Notification":
        notif_type = hook_input.get("notification_type", "")
        message = hook_input.get("message", "")
        log_notification(notif_type, message)

    elif hook_event == "PermissionRequest":
        tool_name = hook_input.get("tool_name", "")
        log_permission_request(tool_name, "requested")

    return 0


if __name__ == "__main__":
    sys.exit(main())
