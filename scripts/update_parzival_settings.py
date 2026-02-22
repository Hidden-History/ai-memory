#!/usr/bin/env python3
"""Patch an existing settings.json with Parzival configuration.

Called from install.sh AFTER setup_parzival() writes to docker/.env.
Reads Parzival vars from docker/.env and syncs them to the env section
of settings.json, and adjusts the SessionStart hook matcher accordingly.

Usage:
    update_parzival_settings.py <settings_json_path> <docker_env_path>

Exit codes:
  0 = Success
  1 = Error (missing arguments, file not found, write failure)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

PARZIVAL_VARS = [
    "PARZIVAL_ENABLED",
    "PARZIVAL_USER_NAME",
    "PARZIVAL_LANGUAGE",
    "PARZIVAL_DOC_LANGUAGE",
    "PARZIVAL_OVERSIGHT_FOLDER",
    "PARZIVAL_HANDOFF_RETENTION",
]

MATCHER_PARZIVAL = "startup|resume|compact|clear"
MATCHER_STANDARD = "resume|compact"


def read_env_file(env_path):
    """Read key=value pairs from .env file."""
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: update_parzival_settings.py <settings_json_path> <docker_env_path>"
        )
        sys.exit(1)

    settings_path = Path(sys.argv[1])
    env_path = Path(sys.argv[2])

    # Validate inputs
    if not settings_path.exists():
        print(f"ERROR: settings.json not found: {settings_path}")
        sys.exit(1)

    if not env_path.exists():
        print(f"ERROR: docker/.env not found: {env_path}")
        sys.exit(1)

    # Read docker/.env
    docker_env = read_env_file(env_path)
    parzival_enabled = docker_env.get("PARZIVAL_ENABLED", "").lower() == "true"

    # Read existing settings.json
    with open(settings_path) as f:
        settings = json.load(f)

    env_section = settings.setdefault("env", {})
    hooks = settings.get("hooks", {})

    if parzival_enabled:
        # Add/update Parzival vars in env section
        for var in PARZIVAL_VARS:
            if var in docker_env:
                old_val = env_section.get(var)
                env_section[var] = docker_env[var]
                if old_val != docker_env[var]:
                    print(f"  env.{var}: {old_val!r} -> {docker_env[var]!r}")
                else:
                    print(f"  env.{var}: unchanged ({docker_env[var]!r})")

        # Expand SessionStart matcher
        for wrapper in hooks.get("SessionStart", []):
            if isinstance(wrapper, dict) and wrapper.get("matcher") == MATCHER_STANDARD:
                wrapper["matcher"] = MATCHER_PARZIVAL
                print(
                    f"  SessionStart matcher: {MATCHER_STANDARD!r} -> {MATCHER_PARZIVAL!r}"
                )
    else:
        # Remove Parzival vars from env section
        for var in PARZIVAL_VARS:
            if var in env_section:
                del env_section[var]
                print(f"  Removed env.{var}")

        # Narrow SessionStart matcher back to standard
        for wrapper in hooks.get("SessionStart", []):
            if isinstance(wrapper, dict) and wrapper.get("matcher") == MATCHER_PARZIVAL:
                wrapper["matcher"] = MATCHER_STANDARD
                print(
                    f"  SessionStart matcher: {MATCHER_PARZIVAL!r} -> {MATCHER_STANDARD!r}"
                )

    # Write updated settings.json atomically (preserve indent=2)
    fd, temp_path = tempfile.mkstemp(
        dir=str(settings_path.parent), prefix=".settings_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        os.replace(temp_path, str(settings_path))
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise

    status = "enabled" if parzival_enabled else "disabled"
    print(f"Updated {settings_path} (Parzival {status})")


if __name__ == "__main__":
    main()
