#!/usr/bin/env python3
"""SOT Drift Stop Hook — propose-only, default-on.

Fires on Claude Code session end (Stop hook). Invokes the aim-sot detect-propose
engine in propose-only mode and surfaces a one-line summary to stderr when drift
or new candidates are found. Never writes any committed file.

Input (stdin JSON): {session_id, transcript_path, cwd, stop_hook_active}

Default-on: registered on install alongside the core ai-memory hooks.
Disable with AI_MEMORY_SOT_HOOKS=off before install. See aim-sot SKILL.md § Stop Hook.
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

# Self-termination timeout — prevents hook from hanging Claude Code.
# Inner subprocess.run uses a tighter 20s timeout; this outer guard
# fires at 25s to kill the whole process if something escapes.
HOOK_TIMEOUT_SECONDS = 25


def _timeout_handler(signum, frame):
    """Self-terminate if hook exceeds global SIGALRM timeout."""
    sys.exit(0)


def _normalize_cwd(cwd: str) -> Path:
    """Strip .claude/worktrees/<name> suffix if present (BP-032 worktree correction).

    Claude Code worktree sessions report cwd as <project>/.claude/worktrees/<name>.
    Normalize back to the project root before resolving the registry path.
    """
    p = Path(cwd)
    parts = p.parts
    for i, part in enumerate(parts):
        if part == ".claude" and i + 1 < len(parts) and parts[i + 1] == "worktrees":
            return Path(*parts[:i])
    return p


def main():
    """Main entry point for Stop hook."""
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

        # Loop guard — exit immediately if Claude is replaying this hook (BP-032).
        # Propose-only is structurally loop-free; this is belt-and-suspenders.
        if payload.get("stop_hook_active"):
            sys.exit(0)

        cwd = payload.get("cwd", "")
        if not cwd:
            sys.exit(0)

        # Worktree cwd normalization (BP-032)
        project_root = _normalize_cwd(cwd)

        # Only run against SOT-enabled projects — no registry means not opted in.
        registry_path = project_root / ".sot" / "registry.yaml"
        if not registry_path.exists():
            sys.exit(0)

        # Locate install dir, run-with-env.sh wrapper, and engine script.
        # run-with-env.sh loads QDRANT_API_KEY + secrets needed by the engine's
        # 5b derived-memory reindex (auto-triggered when registry sha changes).
        install_dir = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        run_with_env = os.path.join(install_dir, "scripts", "memory", "run-with-env.sh")
        engine_script = os.path.join(
            install_dir,
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
        pass  # never block Claude Code

    sys.exit(0)


if __name__ == "__main__":
    main()
