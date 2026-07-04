#!/usr/bin/env python3
"""aim doctor — post-install state-assertion command (TD-578).

Verifies that installer-derived Tier-1 state and documented, forwarded
config actually match reality, instead of drifting silently until an
operator stumbles onto the symptom (BUG-311, F-D1-1).

Checks:

1. tier1-compose-profiles — re-derives the expected ``COMPOSE_PROFILES``
   from the persisted ``MONITORING_ENABLED`` / ``GITHUB_SYNC_ENABLED``
   values and compares it against the persisted ``COMPOSE_PROFILES``.
   Mirrors ``derive_and_persist_compose_profiles`` in scripts/install.sh.
   Catches the BUG-311 shape: installer wrote a blank/stale
   ``COMPOSE_PROFILES`` while monitoring was nonetheless enabled.

2. config-delivery — for a curated manifest of config keys that MUST reach
   scripts invoked via ``scripts/memory/run-with-env.sh``, actually runs
   ``run-with-env.sh`` with a probe script and compares the delivered
   ``os.environ`` values against what is configured in ``docker/.env`` /
   ``docker/.env.secrets``. This is a real subprocess execution, so it
   proves *delivery*, not merely that the key is present in ``.env`` or
   textually referenced in ``run-with-env.sh``. Catches the F-D1-1 shape:
   the ``AI_MEMORY_SOT_*`` family was documented and configurable, but
   ``run-with-env.sh`` forwarded none of it, so the whole surface was
   silently inert.

Exit codes:
    0 - no WARNING (or WARNING present but --strict not given)
    1 - a WARNING was found and --strict was given

Usage:
    python scripts/aim_doctor.py
    python scripts/aim_doctor.py --strict
    python scripts/aim_doctor.py --install-dir /path/to/.ai-memory
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Config-delivery manifest (F-D1-1 class check) — TD-578.
#
# Keys here MUST reach any script invoked via scripts/memory/run-with-env.sh.
# These are consumed via bare `os.environ.get(...)` in operator/hook scripts
# (not through MemoryConfig/pydantic-settings, which the containerized engine
# gets separately via Docker Compose env_file).
#
# Derivation (verified at TASK-096 Lane E, 2026-07-03): intersection of
# docker/.env.example-documented keys with os.environ reads in scripts
# reachable through run-with-env.sh:
#   - QDRANT_API_KEY, GITHUB_REPO, GITHUB_BRANCH, GITHUB_TOKEN,
#     GITHUB_SYNC_ENABLED: already forwarded via run-with-env.sh's own
#     load_env_var calls.
#   - AI_MEMORY_SOT_DISCOVERY_MAX_SECONDS, AI_MEMORY_SOT_DISCOVERY_MAX_DIRS,
#     AI_MEMORY_SOT_DIGEST_MAX_SECONDS, AI_MEMORY_SOT_DIGEST_MAX_FILES,
#     AI_MEMORY_SOT_DISCOVERY_TTL_SECONDS,
#     AI_MEMORY_SOT_DISCOVERY_SESSION_INTERVAL,
#     AI_MEMORY_SOT_DISCOVERY_NUDGE_SESSIONS: read via _env_float/_env_int in
#     _ai-memory/skills/aim-sot/scripts/{aim_sot_shadow,aim_sot_detect_propose}.py
#     (the F-D1-1 shape — Lane A / PR #256 proposes fixing forwarding for this
#     family; PR #256 is not yet merged as of this writing).
#
# Deliberately EXCLUDED:
#   - AI_MEMORY_PROJECT_ID: run-with-env.sh documents (BUG-314) that
#     forwarding the install-global value into operator scripts is a
#     confused-deputy bug; its absence here is correct, not drift.
#   - AI_MEMORY_SOT_HOOKS: documented in docker/.env.example alongside the
#     rest of the SOT family, but only ever read by scripts/generate_settings.py
#     at install time (it controls whether the SOT hooks get registered into
#     .claude/settings.json at all) — a different delivery mechanism than
#     run-with-env.sh, so it is not part of this manifest.
DELIVERY_MANIFEST = (
    "QDRANT_API_KEY",
    "GITHUB_REPO",
    "GITHUB_BRANCH",
    "GITHUB_TOKEN",
    "GITHUB_SYNC_ENABLED",
    "AI_MEMORY_SOT_DISCOVERY_MAX_SECONDS",
    "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS",
    "AI_MEMORY_SOT_DIGEST_MAX_SECONDS",
    "AI_MEMORY_SOT_DIGEST_MAX_FILES",
    "AI_MEMORY_SOT_DISCOVERY_TTL_SECONDS",
    "AI_MEMORY_SOT_DISCOVERY_SESSION_INTERVAL",
    "AI_MEMORY_SOT_DISCOVERY_NUDGE_SESSIONS",
)

_PROBE_SOURCE = (
    "import json, os, sys\n"
    "print(json.dumps({k: os.environ.get(k) for k in sys.argv[1:]}))\n"
)


class Status(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    SKIP = "SKIP"


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str


def _strip_quotes(value: str) -> str:
    """Strip ALL single/double quote characters (not just leading/trailing).

    Matches bash `tr -d '"'"'"'` in _env_split_helpers.sh::_read_env_key — a
    value like ``foo"bar`` loses the embedded quote too, not just wrapping ones.
    """
    return value.replace("'", "").replace('"', "")


def _read_env_key(key: str, secrets_file: Path, env_file: Path) -> str:
    """Secrets-first env read. Mirrors scripts/_env_split_helpers.sh::_read_env_key."""
    for path in (secrets_file, env_file):
        if path is None or not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(f"{key}="):
                val = _strip_quotes(line.split("=", 1)[1].strip())
                if val:
                    return val
    return ""


def check_tier1_derived_state(install_dir: Path) -> CheckResult:
    """Re-derive expected COMPOSE_PROFILES and compare against persisted state.

    Mirrors derive_and_persist_compose_profiles in scripts/install.sh.
    Reimplemented here rather than shelled out to the bash function: that
    function's own fallback reads MONITORING_ENABLED/GITHUB_SYNC_ENABLED from
    the same docker/.env this check verifies, so invoking it from a
    post-install context (no shell-scope INSTALL_MONITORING) would just
    recompute from — and always agree with — the value under test. Keep this
    derivation in sync with derive_and_persist_compose_profiles in
    scripts/install.sh by hand; the duplication is an
    accepted maintenance cost for a MED-severity diagnostic (see TASK-096
    Lane E work report).
    """
    name = "tier1-compose-profiles"
    env_file = install_dir / "docker" / ".env"
    secrets_file = install_dir / "docker" / ".env.secrets"

    if not env_file.exists():
        return CheckResult(name, Status.SKIP, f"{env_file} not found — not installed")

    monitoring_enabled = _read_env_key("MONITORING_ENABLED", secrets_file, env_file)
    github_sync_enabled = _read_env_key("GITHUB_SYNC_ENABLED", secrets_file, env_file)
    persisted_profiles = _read_env_key("COMPOSE_PROFILES", secrets_file, env_file)

    if not monitoring_enabled:
        # Mirrors derive_and_persist_compose_profiles in scripts/install.sh — no
        # prior/current monitoring choice to derive from.
        return CheckResult(
            name, Status.SKIP, "MONITORING_ENABLED not set — nothing to derive"
        )

    expected = "monitoring" if monitoring_enabled == "true" else ""
    if github_sync_enabled == "true":
        expected = f"{expected},github" if expected else "github"

    if expected == persisted_profiles:
        return CheckResult(
            name,
            Status.PASS,
            f"COMPOSE_PROFILES={persisted_profiles!r} matches derived state",
        )
    return CheckResult(
        name,
        Status.WARNING,
        f"COMPOSE_PROFILES={persisted_profiles!r} does not match expected {expected!r} "
        f"(derived from MONITORING_ENABLED={monitoring_enabled!r}, GITHUB_SYNC_ENABLED={github_sync_enabled!r})",
    )


def _probe_delivered_env(
    run_with_env: Path, install_dir: Path, keys: list[str]
) -> dict | None:
    """Actually execute run-with-env.sh and return what os.environ looks like inside it.

    Returns None if the probe could not be run/parsed (caller decides how to report).

    The DELIVERY_MANIFEST keys are scrubbed from the subprocess env before it is
    passed down: if a manifest key happens to already be exported in the
    caller's own shell (e.g. an operator's ``QDRANT_API_KEY``), inheriting it
    would make the probe see the key regardless of whether run-with-env.sh
    actually forwards it — a false PASS that defeats the whole delivery check.
    The only way a manifest key can appear in the probe's environ is via
    run-with-env.sh's own load_env_var loading it from docker/.env(.secrets).
    """
    fd, probe_path_str = tempfile.mkstemp(suffix="_aim_doctor_probe.py")
    probe_path = Path(probe_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_PROBE_SOURCE)
        env = {k: v for k, v in os.environ.items() if k not in DELIVERY_MANIFEST}
        env["AI_MEMORY_INSTALL_DIR"] = str(install_dir)
        result = subprocess.run(
            ["bash", str(run_with_env), str(probe_path), *keys],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if result.returncode != 0:
            return None
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None
    finally:
        probe_path.unlink(missing_ok=True)


def check_config_delivery(install_dir: Path) -> CheckResult:
    """Assert that DELIVERY_MANIFEST keys configured in .env actually reach a
    run-with-env.sh-invoked subprocess (the F-D1-1 class check).
    """
    name = "config-delivery"
    env_file = install_dir / "docker" / ".env"
    secrets_file = install_dir / "docker" / ".env.secrets"
    run_with_env = install_dir / "scripts" / "memory" / "run-with-env.sh"
    py_bin = install_dir / ".venv" / "bin" / "python"

    if not env_file.exists() and not secrets_file.exists():
        return CheckResult(
            name,
            Status.SKIP,
            "no docker/.env or docker/.env.secrets found — not installed",
        )
    if not run_with_env.exists():
        return CheckResult(
            name, Status.SKIP, f"{run_with_env} not found — cannot probe delivery"
        )
    if not py_bin.exists():
        return CheckResult(
            name,
            Status.SKIP,
            f"venv python not found at {py_bin} — install incomplete?",
        )

    source_values = {
        k: _read_env_key(k, secrets_file, env_file) for k in DELIVERY_MANIFEST
    }
    configured = {k: v for k, v in source_values.items() if v}
    if not configured:
        return CheckResult(
            name,
            Status.PASS,
            "no delivery-manifest keys configured — nothing to verify",
        )

    delivered = _probe_delivered_env(run_with_env, install_dir, list(configured))
    if delivered is None:
        return CheckResult(
            name,
            Status.WARNING,
            f"delivery probe via {run_with_env} failed to execute or parse",
        )

    undelivered = sorted(k for k, v in configured.items() if delivered.get(k) != v)
    if undelivered:
        return CheckResult(
            name,
            Status.WARNING,
            f"documented + configured but not delivered via run-with-env.sh: {', '.join(undelivered)}",
        )
    return CheckResult(
        name,
        Status.PASS,
        f"{len(configured)} configured key(s) verified delivered via run-with-env.sh",
    )


def run_checks(install_dir: Path) -> list[CheckResult]:
    return [
        check_tier1_derived_state(install_dir),
        check_config_delivery(install_dir),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=None,
        help="ai-memory install directory (default: $AI_MEMORY_INSTALL_DIR or ~/.ai-memory)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any check reports WARNING (default: always exit 0)",
    )
    args = parser.parse_args(argv)

    install_dir = args.install_dir or Path(
        os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
    )

    results = run_checks(install_dir)
    for r in results:
        print(f"[{r.status.value}] {r.name}: {r.detail}")

    warnings = [r for r in results if r.status == Status.WARNING]
    print()
    if warnings:
        print(f"{len(warnings)} WARNING(s) found.")
        if args.strict:
            return 1
    else:
        print("All checks PASS (or SKIP).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
