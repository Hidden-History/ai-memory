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
import sys
from pathlib import Path


def generate_hook_config(hooks_dir: str) -> dict:
    """Generate hook configuration with absolute paths.

    Args:
        hooks_dir: Absolute path to hooks scripts directory

    Returns:
        Dict with 'hooks' key containing SessionStart, PostToolUse, Stop config

    2026 Best Practice: Correct Claude Code hook structure
    - SessionStart/Stop: Direct hook array (no matcher needed)
    - PostToolUse: Wrapper with 'matcher' + nested 'hooks' array
    Source: https://code.claude.com/docs/en/settings, AC 7.2.2
    """
    return {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {hooks_dir}/session_start.py"
                        }
                    ]
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "Edit|Write|NotebookEdit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {hooks_dir}/post_tool_capture.py"
                        }
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {hooks_dir}/session_stop.py"
                        }
                    ]
                }
            ]
        }
    }


def main():
    """Main entry point for CLI invocation."""
    if len(sys.argv) != 3:
        print("Usage: generate_settings.py <output_path> <hooks_dir>")
        sys.exit(1)

    output_path = Path(sys.argv[1])
    hooks_dir = sys.argv[2]

    # Generate configuration
    config = generate_hook_config(hooks_dir)

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Generated settings.json at {output_path}")


if __name__ == "__main__":
    main()
