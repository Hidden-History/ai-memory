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


def read_qdrant_api_key(install_dir: str) -> str:
    """Read QDRANT_API_KEY from .env file.

    BUG-029 fix: API key is required for Qdrant authentication.
    BUG-033 fix: Check multiple locations for .env file.

    Args:
        install_dir: Path to BMAD installation directory

    Returns:
        API key string, or empty string if not found
    """
    # Check environment variable first (allows override)
    if os.environ.get("QDRANT_API_KEY"):
        return os.environ["QDRANT_API_KEY"]

    # BUG-033: Check multiple possible locations for .env file
    possible_locations = [
        Path(install_dir) / ".env",           # Root of install dir
        Path(install_dir) / "docker" / ".env", # Docker subdirectory
    ]

    for env_file in possible_locations:
        if env_file.exists():
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("QDRANT_API_KEY=") and not line.startswith("#"):
                        return line.split("=", 1)[1].strip()

    return ""


def generate_hook_config(hooks_dir: str, project_name: str, install_dir: str = None) -> dict:
    """Generate COMPLETE hook configuration with all BMAD memory hooks.

    BUG-030 fix: Previous version only included minimal hooks (SessionStart,
    PostToolUse for edits, PreCompact). This version includes ALL hooks needed
    for full memory system functionality.

    BUG-032 fix: Support project-local hooks (copied files, not symlinks) for
    Windows/WSL compatibility. WSL symlinks don't work from Windows.

    Args:
        hooks_dir: Absolute path to hooks scripts directory for hook commands
                   For user-level: /path/to/install/.claude/hooks/scripts
                   For project-level: /path/to/project/.claude/hooks/scripts
        project_name: Name of the project for BMAD_PROJECT_ID
        install_dir: Optional. Path to BMAD installation for env vars and API key.
                     If not provided, derived from hooks_dir (legacy behavior).

    Returns:
        Dict with complete hook configuration including:
        - SessionStart: Context injection on session start/resume/compact
        - UserPromptSubmit: Memory retrieval triggers (decision/best practices keywords)
        - PreToolUse: New file and first edit triggers
        - PostToolUse: Error detection, error capture, code pattern capture
        - PreCompact: Save conversation memory before compaction
        - Stop: Capture agent responses

    2026 Best Practice: Complete Claude Code hook structure
    - Project-level hooks use absolute paths to copied scripts
    - User-level hooks use $BMAD_INSTALL_DIR for portability
    - UserPromptSubmit is CRITICAL for memory retrieval on user queries
    Source: https://code.claude.com/docs/en/hooks
    """
    hooks_path = Path(hooks_dir)

    # BUG-032: Determine install_dir for env vars
    # If install_dir provided (project-level), use it
    # Otherwise derive from hooks_dir (user-level, legacy behavior)
    if install_dir is None:
        # Legacy: hooks_dir format is /path/to/install/.claude/hooks/scripts
        # .parent chain: scripts -> hooks -> .claude -> install_dir (3 levels up)
        install_dir = str(hooks_path.parent.parent.parent)
        # Use environment variable reference for portability (user-level)
        hooks_base = '$BMAD_INSTALL_DIR/.claude/hooks/scripts'
    else:
        # BUG-032: Project-level - use absolute path to project's hooks
        # Hooks were copied to project, so use project path directly
        hooks_base = str(hooks_path)

    # BUG-029: Read API key from shared installation
    qdrant_api_key = read_qdrant_api_key(install_dir)

    # BUG-033: Validate API key presence and warn if missing
    if not qdrant_api_key:
        import sys
        print("WARNING: QDRANT_API_KEY not found in .env files", file=sys.stderr)
        print(f"  Checked: {install_dir}/.env, {install_dir}/docker/.env", file=sys.stderr)
        print("  Memory operations will fail without API key authentication.", file=sys.stderr)

    # Build env section with all required variables
    env_config = {
        # BMAD Memory Module installation directory (dynamic)
        "BMAD_INSTALL_DIR": install_dir,
        # Project identification for multi-tenancy
        "BMAD_PROJECT_ID": project_name,
        # Service configuration - ports per CLAUDE.md
        "QDRANT_HOST": "localhost",
        "QDRANT_PORT": "26350",
        "EMBEDDING_HOST": "localhost",
        "EMBEDDING_PORT": "28080",
        # TECH-DEBT-002: Lower threshold for NL query → code content matching
        "SIMILARITY_THRESHOLD": "0.4",
        "LOG_LEVEL": "INFO",
        # Pushgateway for metrics (BUG-030)
        "PUSHGATEWAY_URL": "localhost:29091",
        "PUSHGATEWAY_ENABLED": "true",
    }

    # BUG-029: Include QDRANT_API_KEY if available
    if qdrant_api_key:
        env_config["QDRANT_API_KEY"] = qdrant_api_key

    # BUG-030: Complete hook configuration matching main project
    return {
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "env": env_config,
        "hooks": {
            # SessionStart: Context injection on session events
            "SessionStart": [
                {
                    "matcher": "startup|resume|compact|clear",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/session_start.py"',
                            "timeout": 30000
                        }
                    ]
                }
            ],
            # UserPromptSubmit: Memory retrieval triggers (CRITICAL for memory injection)
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/user_prompt_capture.py"'
                        }
                    ]
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/unified_keyword_trigger.py"',
                            "timeout": 5000
                        }
                    ]
                }
            ],
            # PreToolUse: Triggers before tool execution
            "PreToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/new_file_trigger.py"',
                            "timeout": 2000
                        }
                    ]
                },
                {
                    "matcher": "Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/first_edit_trigger.py"',
                            "timeout": 2000
                        }
                    ]
                }
            ],
            # PostToolUse: Capture after tool execution
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/error_detection.py"',
                            "timeout": 2000
                        },
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/error_pattern_capture.py"'
                        }
                    ]
                },
                {
                    "matcher": "Edit|Write|NotebookEdit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/post_tool_capture.py"'
                        }
                    ]
                }
            ],
            # PreCompact: Save conversation memory before compaction
            "PreCompact": [
                {
                    "matcher": "auto|manual",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/pre_compact_save.py"',
                            "timeout": 10000
                        }
                    ]
                }
            ],
            # Stop: Capture agent responses
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'python3 "{hooks_base}/agent_response_capture.py"'
                        }
                    ]
                }
            ]
        }
    }


def main():
    """Main entry point for CLI invocation."""
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        print("Usage: generate_settings.py <output_path> <hooks_dir> <project_name> [install_dir]")
        print("")
        print("  output_path  - Path to write settings.json")
        print("  hooks_dir    - Path to hooks scripts directory for commands")
        print("  project_name - Project identifier for BMAD_PROJECT_ID")
        print("  install_dir  - Optional. BMAD install dir for env vars (default: derived from hooks_dir)")
        sys.exit(1)

    output_path = Path(sys.argv[1])
    hooks_dir = sys.argv[2]
    project_name = sys.argv[3]
    # BUG-032: Optional install_dir for project-local hooks
    install_dir = sys.argv[4] if len(sys.argv) == 5 else None

    # Generate configuration
    config = generate_hook_config(hooks_dir, project_name, install_dir)

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Generated settings.json at {output_path}")
    print(f"Project ID: {project_name}")


if __name__ == "__main__":
    main()
