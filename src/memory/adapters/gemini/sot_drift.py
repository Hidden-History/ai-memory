#!/usr/bin/env python3
"""Gemini CLI PreCompress SOT-drift trigger adapter — propose-only, opt-in-OFF by default.

Fires on Gemini CLI PreCompress event (canonical: PreCompact). Invokes the
aim-sot detect-propose engine in propose-only mode and surfaces a one-line
summary to stderr when drift or new candidates are found. Never writes any
committed file.

Input (stdin JSON): Gemini PreCompress payload (normalized via normalize_gemini_event)

Opt-in: ships unregistered. See aim-sot SKILL.md § Gemini PreCompact Hook.
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Self-termination timeout — prevents adapter from hanging Gemini CLI.
# Inner subprocess.run uses a tighter 20s timeout; this outer guard
# fires at 25s to kill the whole process if something escapes.
HOOK_TIMEOUT_SECONDS = 25


def _timeout_handler(signum, frame):
    """Self-terminate if adapter exceeds global SIGALRM timeout."""
    sys.exit(0)


def main():
    """Main entry point for Gemini PreCompress SOT-drift adapter."""
    # Install global self-termination timeout (signal.alarm best practice).
    # Skipped in test environments to prevent SIGALRM leaks across tests.
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(HOOK_TIMEOUT_SECONDS)
        except (AttributeError, OSError):
            pass  # SIGALRM not available on Windows

    try:
        # Parse stdin — fail-open on any parse error
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            sys.exit(0)

        # Normalize via gemini adapter schema — resolve_cwd handles cwd per-CLI.
        try:
            from memory.adapters.schema import (
                normalize_gemini_event,
                validate_canonical_event,
            )

            event = normalize_gemini_event(payload, "PreCompress")
            validate_canonical_event(event)
        except (ValueError, ImportError):
            sys.exit(0)

        cwd = event["cwd"]
        if not cwd:
            sys.exit(0)

        # Only run against SOT-enabled projects — no registry means not opted in.
        registry_path = Path(cwd) / ".sot" / "registry.yaml"
        if not registry_path.exists():
            sys.exit(0)

        # Locate run-with-env.sh wrapper and engine script.
        # run-with-env.sh loads QDRANT_API_KEY + secrets needed by the engine's
        # 5b derived-memory reindex (auto-triggered when registry sha changes).
        run_with_env = os.path.join(INSTALL_DIR, "scripts", "memory", "run-with-env.sh")
        engine_script = os.path.join(
            INSTALL_DIR,
            "_ai-memory",
            "skills",
            "aim-sot",
            "scripts",
            "aim_sot_detect_propose.py",
        )

        # Invoke engine — propose-only, JSON output, explicit registry path.
        # Passing --registry bypasses the engine's internal git rev-parse call
        # (BP-032 non-git TTL fallback: the 5a per-install cache handles
        # component re-check cadence without any git dependency).
        result = subprocess.run(
            [
                "bash",
                run_with_env,
                engine_script,
                "run",
                "--json",
                "--registry",
                str(registry_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                n_drift = len(data.get("drift_proposals", []))
                n_cand = len(data.get("candidate_proposals", []))
                if n_drift or n_cand:
                    parts = []
                    if n_drift:
                        parts.append(f"{n_drift} drift")
                    if n_cand:
                        noun = "candidate" if n_cand == 1 else "candidates"
                        parts.append(f"{n_cand} new {noun}")
                    print(
                        f"[ai-memory] SOT: {', '.join(parts)} detected — "
                        "run aim-sot detect-propose to review.",
                        file=sys.stderr,
                    )
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # fail-open: swallow malformed engine output

    except Exception:
        pass  # never block Gemini CLI

    sys.exit(0)


if __name__ == "__main__":
    main()
