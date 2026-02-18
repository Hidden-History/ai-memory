#!/usr/bin/env python3
"""Generate Claude Code settings.json with BMAD hooks.

2026 Best Practice: Using Python json module + template pattern
- Python 3.10+ required (project standard)
- Absolute paths prevent PATH hijacking
- Structured logging for diagnostics
- AC 7.2.2 compliance

Exit codes:
  0 = Success
  1 = Error (missing arguments, write failure)
"""

import json
import os
import sys
from pathlib import Path


def _hook_cmd(script_name: str) -> str:
    """Generate gracefully-degrading hook command. Exits 0 if installation missing.

    NOTE: Duplicated in merge_settings.py — keep in sync.
    """
    script = f"$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/{script_name}"
    python = "$AI_MEMORY_INSTALL_DIR/.venv/bin/python"
    return f'[ -f "{script}" ] && "{python}" "{script}" || true'


def generate_hook_config(hooks_dir: str, project_name: str) -> dict:
    """Generate hook configuration with dynamic AI_MEMORY_INSTALL_DIR paths.

    Args:
        hooks_dir: Absolute path to hooks scripts directory
                   Expected format: /path/to/install/.claude/hooks/scripts
        project_name: Name of the project for AI_MEMORY_PROJECT_ID

    Returns:
        Dict with complete V2.0 hook configuration:
        - 'env' section with AI_MEMORY_INSTALL_DIR, AI_MEMORY_PROJECT_ID, service ports, API keys
        - 'hooks' section with all 6 hook types

    2026 Best Practice: Complete Claude Code V2.0 hook structure
    - SessionStart: Requires 'matcher' (resume|compact) per Core-Architecture-V2 Section 7.2
    - UserPromptSubmit: Captures user prompts and triggers context injection
    - PreToolUse: Triggers for new file creation and first edit detection
    - PostToolUse: Wrapper with 'matcher' + nested 'hooks' array (Bash errors, Edit/Write capture)
    - PreCompact: Wrapper with 'matcher' for auto|manual triggers
    - Stop: Captures agent responses
    - Uses $AI_MEMORY_INSTALL_DIR for portability across installations
    Source: https://code.claude.com/docs/en/hooks, AC 7.2.2
    """
    # Extract install directory from hooks_dir
    # hooks_dir format: /path/to/install/.claude/hooks/scripts
    # install_dir should be: /path/to/install
    # .parent chain: scripts -> hooks -> .claude -> install_dir (3 levels up)
    hooks_path = Path(hooks_dir)
    install_dir = str(hooks_path.parent.parent.parent)

    session_start_hook = {
        "type": "command",
        "command": _hook_cmd("session_start.py"),
        "timeout": 30000,
    }

    # Build env section - only include QDRANT_API_KEY if it has a value
    # (empty string vs omitted key matters for some consumers)
    env_section = {
        # AI Memory Module installation directory (dynamic)
        "AI_MEMORY_INSTALL_DIR": install_dir,
        # Project identification for multi-tenancy
        "AI_MEMORY_PROJECT_ID": project_name,
        # Service configuration - ports per CLAUDE.md
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "26350",
        "EMBEDDING_HOST": "localhost",
        "EMBEDDING_PORT": "28080",
        # TECH-DEBT-002: Lower threshold for NL query → code content matching
        "SIMILARITY_THRESHOLD": "0.4",
        "LOG_LEVEL": "INFO",
        # Pushgateway configuration for metrics
        "PUSHGATEWAY_URL": "localhost:29091",
        "PUSHGATEWAY_ENABLED": "true",
    }

    # Only include QDRANT_API_KEY if it has a non-empty value
    api_key = os.environ.get("QDRANT_API_KEY", "")
    if api_key:
        env_section["QDRANT_API_KEY"] = api_key

    return {
        # Schema reference for IDE validation (BUG-029+030 fix)
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "env": env_section,
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "resume|compact",
                    "hooks": [session_start_hook],
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_cmd("user_prompt_capture.py"),
                        }
                    ]
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_cmd("context_injection_tier2.py"),
                            "timeout": 5000,
                        }
                    ]
                },
            ],
            "PreToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_cmd("new_file_trigger.py"),
                            "timeout": 2000,
                        }
                    ],
                },
                {
                    "matcher": "Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_cmd("first_edit_trigger.py"),
                            "timeout": 2000,
                        }
                    ],
                },
            ],
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_cmd("error_detection.py"),
                            "timeout": 2000,
                        },
                        {
                            "type": "command",
                            "command": _hook_cmd("error_pattern_capture.py"),
                        },
                    ],
                },
                {
                    "matcher": "Edit|Write|NotebookEdit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_cmd("post_tool_capture.py"),
                        }
                    ],
                },
            ],
            "PreCompact": [
                {
                    "matcher": "auto|manual",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_cmd("pre_compact_save.py"),
                            "timeout": 10000,
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_cmd("agent_response_capture.py"),
                        }
                    ]
                }
            ],
        },
    }


def main():
    """Main entry point for CLI invocation."""
    if len(sys.argv) != 4:
        print("Usage: generate_settings.py <output_path> <hooks_dir> <project_name>")
        sys.exit(1)

    output_path = Path(sys.argv[1])
    hooks_dir = sys.argv[2]
    project_name = sys.argv[3]

    # Generate configuration
    config = generate_hook_config(hooks_dir, project_name)

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Generated settings.json at {output_path}")
    print(f"Project ID: {project_name}")


if __name__ == "__main__":
    main()
