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

# The enablement record (AD-32): value + cause + condition.
#
# CAUSE and CONDITION are synced in BOTH directions of the flag: the not-enabled
# state is the only state in which a cause exists, so removing them when the flag
# is false would strip the cause exactly when a consumer needs it.
#
# PARZIVAL_ENABLED itself is written ONLY on the enabled path and DELETED on the
# disabled one. settings.json's env section outranks docker/.env in
# pydantic-settings, so persisting "false" here would override the file the
# operator is told to edit. See the disabled branch in main() for the measurement.
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

#: The state vars carried across on the DISABLED path — everything except the value
#: itself. Derived rather than re-listed so a fourth state var cannot be added above
#: and silently missed by the disabled branch.
PARZIVAL_DISABLED_CARRY_VARS = [
    var for var in PARZIVAL_STATE_VARS if var != "PARZIVAL_ENABLED"
]


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
            elif var in env_section:
                # Without this, a settings.json holding CAUSE=failed from a prior
                # run plus a docker/.env that reaches enabled WITHOUT a cause line
                # (an operator who *deletes* rather than empties it, per the session
                # guide) leaves PARZIVAL_ENABLED=true x cause=failed on transport 2
                # -- the exact cell the single-pass writer makes unrepresentable in
                # docker/.env. The disabled branch already had this removal; the
                # enabled branch did not.
                del env_section[var]
                print(f"  Removed stale env.{var} (not recorded in docker/.env)")

    else:
        # Carry the CAUSE and CONDITION across — host-side hooks read env from
        # settings.json, not docker/.env (BUG-120), and the not-enabled state is the
        # only state in which a cause exists.
        #
        # PARZIVAL_ENABLED ITSELF IS DELETED, NOT WRITTEN. settings.json's env
        # section reaches the hook process, and pydantic-settings ranks process env
        # ABOVE env_file: writing "false" here pins the disabled state above
        # docker/.env, so the panel's own remediation advice (edit docker/.env)
        # becomes inert -- measured, docker/.env=true + process env=false yields
        # MemoryConfig(enabled=False). Absence is safe in both readers:
        # langfuse_stop_hook.py does os.environ.get("PARZIVAL_ENABLED", "false") so
        # absent reads false, and MemoryConfig falls through to docker/.env.
        if "PARZIVAL_ENABLED" in env_section:
            del env_section["PARZIVAL_ENABLED"]
            print("  Removed env.PARZIVAL_ENABLED (docker/.env is authoritative)")

        for var in PARZIVAL_DISABLED_CARRY_VARS:
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
