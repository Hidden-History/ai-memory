---
name: aim-verify
description: Run AI-Memory's post-install self-diagnostic — a registry of read-only checks rendered as pass/warn/fail (human or --json), with a worst-severity exit code. Use when checking whether an AI-Memory install is healthy, diagnosing "something looks broken" after an install/update, or before filing an issue. Do NOT use for AI Memory search or save operations (use aim-search, aim-save), or for the sync/collection stats dashboard (use aim-status).
allowed-tools: Bash, Read
---

# aim-verify — Post-Install Self-Diagnostic

Runs a registry of independent, read-only checks against an AI-Memory install and
reports pass/warn/fail per check, human or `--json`. **Report-only**: no check
mutates state.

> **Status (PLAN-037 P1)**: framework only. One example check
> (`install-dir-present`) is registered to prove the path end-to-end. The real
> domain checks (Qdrant payload-index, template-parity, env-parity),
> secret-redaction, and consent-gated issue reporting are later phases — see
> `scripts/aim_verify.py`'s module docstring for the documented seams.

## Invocation

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-verify/scripts/aim_verify.py" \
  [--json]
```

When working from an `ai-memory` repo checkout, running the script directly with
`python3 _ai-memory/skills/aim-verify/scripts/aim_verify.py [--json]` is an
equivalent contributor shortcut (the framework has no dependency beyond the
standard library).

## Architecture (BP-195)

- **`Check` protocol** — each check owns its `id`, `category`, and `run()`,
  which returns a `CheckResult` with its OWN severity (`pass` / `warn` / `fail`
  / `skip`). The runner never decides severity.
- **`REGISTRY`** — an append-only list of checks. Adding a check means
  registering one more `Check` object; the runner never changes.
- **Runner** — iterates every check, accumulates ALL results (no fail-fast), and
  maps the worst severity to the process exit code: `0` = all pass/warn/skip
  (warnings never fail the run), `1` = at least one fail, `2` = the verifier
  itself could not run.
- **Renderers** — `render_human()` (glyph per tier: `✓` pass, `!` warn, `✗` fail,
  `-` skip) and `render_json()` (typed
  `{check, status, severity, message, remediation}`). Both route through
  `redact()`.
- **`redact()`** — currently a documented pass-through stub; a later phase
  implements the real secret-scrub. Every renderer calls it so that phase is a
  one-function change.
- **`maybe_offer_report()`** — a documented no-op seam where a later
  consent-gated GitHub-issue reporter plugs in (interactive-only, default-No,
  never in CI). Not implemented yet.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Every check passed, warned, or was skipped. |
| `1` | At least one check failed. |
| `2` | The verifier itself could not run (not a check failure). |

## Registered checks

| id | category | What it checks |
|----|----------|-----------------|
| `install-dir-present` | `runtime` | `$AI_MEMORY_INSTALL_DIR` (default `~/.ai-memory`) exists and has its `src`, `scripts`, and `docker` subdirs. |

## Implementation

- Script: `scripts/aim_verify.py`
- Tests: `tests/test_aim_verify.py`
- Behavior: read-only; never writes/mutates anything the checks inspect.
