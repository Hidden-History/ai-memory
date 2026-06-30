#!/usr/bin/env python3
"""SOT Digest Session-Start Hook — propose-only, default-on.

Fires on Claude Code session start (SessionStart hook). Invokes the aim-sot
consult engine in digest mode and injects a compact SOT summary as ambient
session-start context. Never writes any committed file.

Input (stdin JSON): {session_id, cwd, source, ...}

Default-on: registered on install alongside the core ai-memory hooks.
Disable with AI_MEMORY_SOT_HOOKS=off before install. See aim-sot SKILL.md § Digest Session-Start Hook.
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

EMPTY_OUTPUT = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "",
    }
}


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


def _render_digest(data: dict) -> str:
    """Render digest JSON into compact context text.

    Returns empty string if digest is empty or data is malformed.
    """
    lines = data.get("digest", [])
    if not lines:
        return ""
    drift = data.get("drift", {})
    clean = drift.get("clean", 0)
    stale = drift.get("stale", 0)
    unverified = drift.get("unverified", 0)
    drift_line = f"drift: {clean} clean, {stale} stale, {unverified} unverified"
    # Live rollup from the [CL] detect pass (BP-040/042): N changed / M docs-stale.
    rollup = data.get("drift_rollup")
    if isinstance(rollup, dict):
        drift_line += (
            f", {rollup.get('changed', 0)} changed, "
            f"{rollup.get('docs_stale', 0)} docs-stale"
        )
    return "[ai-memory] SOT digest:\n" + "\n".join(lines) + "\n" + drift_line


def main():
    """Main entry point for SessionStart digest hook."""
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
            print(json.dumps(EMPTY_OUTPUT))
            sys.exit(0)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            print(json.dumps(EMPTY_OUTPUT))
            sys.exit(0)

        cwd = payload.get("cwd", "")
        if not cwd:
            print(json.dumps(EMPTY_OUTPUT))
            sys.exit(0)

        # Worktree cwd normalization (BP-032)
        project_root = _normalize_cwd(cwd)

        # No registry → not yet opted in. Surface a one-line [ST] bootstrap
        # nudge (G3) instead of staying silent, so the project can be onboarded.
        registry_path = project_root / ".sot" / "registry.yaml"
        if not registry_path.exists():
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "SessionStart",
                            "additionalContext": (
                                "[ai-memory] SOT: no .sot/registry.yaml in this "
                                "project — run `aim-sot detect-propose run "
                                "--write-proposal` to scaffold a ready-to-edit "
                                ".sot/registry.proposed.yaml draft (you fill the "
                                "TODO(human) fields, then promote it to "
                                ".sot/registry.yaml and run aim-sot verify), or "
                                "`aim-sot detect-propose run` to just list "
                                "candidates."
                            ),
                        }
                    }
                )
            )
            sys.exit(0)

        # Locate install dir, run-with-env.sh wrapper, and engine script.
        # run-with-env.sh loads QDRANT_API_KEY + secrets needed by the engine.
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
            "aim_sot_consult.py",
        )

        # Invoke engine — digest mode, JSON output, explicit registry path.
        result = subprocess.run(
            [
                "bash",
                run_with_env,
                engine_script,
                "digest",
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
                # Handle no_registry error shape (Opus MINOR-1: handle both shapes)
                if data.get("error") != "no_registry":
                    rendered = _render_digest(data)
                    if rendered:
                        output = {
                            "hookSpecificOutput": {
                                "hookEventName": "SessionStart",
                                "additionalContext": rendered,
                            }
                        }
                        print(json.dumps(output))
                        sys.exit(0)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # fail-open: swallow malformed engine output

        print(json.dumps(EMPTY_OUTPUT))

    except Exception:
        print(json.dumps(EMPTY_OUTPUT))  # never block Claude Code

    sys.exit(0)


if __name__ == "__main__":
    main()
