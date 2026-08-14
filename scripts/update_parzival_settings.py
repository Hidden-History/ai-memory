#!/usr/bin/env python3
"""Patch an existing settings.json with Parzival configuration.

Called from install.sh AFTER setup_parzival() writes to docker/.env.
Reads Parzival vars from docker/.env and syncs them to the env section
of settings.json.

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

# The enablement record (AD-32): value + cause + condition. These are synced in
# BOTH directions of the flag. The not-enabled state is the only state in which a
# cause exists, so removing them when the flag is false would strip the cause
# exactly when a consumer needs it.
PARZIVAL_STATE_VARS = [
    "PARZIVAL_ENABLED",
    "PARZIVAL_ENABLED_CAUSE",
    "PARZIVAL_ENABLED_CONDITION",
]

# Preference vars — only meaningful while Parzival is enabled, so they are still
# removed from settings.json when it is not.
PARZIVAL_PREFERENCE_VARS = [
    "PARZIVAL_USER_NAME",
    "PARZIVAL_LANGUAGE",
    "PARZIVAL_DOC_LANGUAGE",
    "PARZIVAL_OVERSIGHT_FOLDER",
    "PARZIVAL_HANDOFF_RETENTION",
]

PARZIVAL_VARS = PARZIVAL_STATE_VARS + PARZIVAL_PREFERENCE_VARS


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

    else:
        # Carry the enablement record across — host-side hooks read env from
        # settings.json, not docker/.env (BUG-120). Deleting it here is what made
        # a re-install transitioning enabled->failed leave a stale `true` in
        # settings.json while docker/.env said `false`.
        for var in PARZIVAL_STATE_VARS:
            if var in docker_env:
                old_val = env_section.get(var)
                env_section[var] = docker_env[var]
                if old_val != docker_env[var]:
                    print(f"  env.{var}: {old_val!r} -> {docker_env[var]!r}")
                else:
                    print(f"  env.{var}: unchanged ({docker_env[var]!r})")
            elif var in env_section:
                del env_section[var]
                print(f"  Removed stale env.{var} (not recorded in docker/.env)")

        # Preference vars are meaningless while disabled — remove as before.
        for var in PARZIVAL_PREFERENCE_VARS:
            if var in env_section:
                del env_section[var]
                print(f"  Removed env.{var}")

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
