#!/usr/bin/env python3
"""aim-verify — post-install self-diagnostic runner (PLAN-037 P1: framework only).

Architecture (BP-195, kubeadm-`Checker`-style):

    Check (protocol)  --  owns id/category and its own run() severity
        |
        v
    REGISTRY: list[Check]   -- append-only; the runner below never changes
        |
        v
    run_checks()  -- iterates ALL checks, accumulates ALL results (no
                      fail-fast); a check that raises is caught and turned
                      into its OWN fail result so one broken check cannot
                      hide the rest
        |
        v
    worst_status() / exit_code_for()  -- worst severity across all results
                                          maps to the process exit code
        |
        v
    render_human() / render_json()  -- two projections of the same result
                                        list, BOTH routed through redact()

Standing contract (PLAN-037 §4, BOND PM #389):
    REPORT-ONLY   -- no Check.run() implementation may write/mutate state.
                     This module holds no write path; enforce it in every
                     Check that gets registered.
    SECRET-REDACTED -- every output surface (human, --json, and the future
                     issue body) is routed through redact() before it is
                     ever printed or handed off. redact() here is a
                     PASS-THROUGH STUB — PLAN-037 P2 implements the real
                     scrub (safe-key allowlist + secret-pattern scrubber).
                     Do not remove or bypass the redact() call sites when P2
                     lands; extend redact() itself.
    CONSENT-GATED   -- filing a GitHub issue from a failing run is PLAN-037
                     P3's job. maybe_offer_report() below is the seam: P1
                     wires it in as a documented no-op so P3 has exactly one
                     place to implement (interactive-only, default-No,
                     CI/non-interactive never prompts/files, body = the
                     already-redacted report). Do not add reporting logic
                     anywhere else.

This script is invoked directly (see SKILL.md), typically through
run-with-env.sh so it runs under the installed ai-memory virtualenv.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

#: Ordinal severity, lowest to highest. "skip" ranks with "pass" — a check
#: that does not apply here is not evidence of a problem.
_SEVERITY_RANK = {"pass": 0, "skip": 0, "warn": 1, "fail": 2}

STATUS_GLYPH = {"pass": "✓", "skip": "-", "warn": "!", "fail": "✗"}


@dataclass
class CheckResult:
    """One check's outcome. Severity is decided by the check, never the runner."""

    check_id: str
    category: str
    status: str  # "pass" | "warn" | "fail" | "skip"
    message: str
    remediation: str | None = None
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in _SEVERITY_RANK:
            raise ValueError(f"unknown CheckResult.status: {self.status!r}")


class Check(Protocol):
    """A self-contained, read-only diagnostic. Owns its id, category, and
    its own expected-state — the runner never inspects or decides severity."""

    id: str
    category: str

    def run(self, ctx: dict) -> CheckResult: ...


# ---------------------------------------------------------------------------
# Registry — append-only; adding a check = append here, the runner below
# never changes (BP-195 Q2, Function Registry Pattern).
# ---------------------------------------------------------------------------

REGISTRY: list[Check] = []


def register(check: Check) -> Check:
    """Append a check to the module-level registry. Returns the check
    unchanged so it can be used as `_ = register(MyCheck())`."""
    REGISTRY.append(check)
    return check


# ---------------------------------------------------------------------------
# Example check (P1 proof of the run -> render -> exit path).
#
# Real domain checks (Qdrant payload-index, template-parity, env-parity) are
# PLAN-037 P4 — this one is deliberately narrow but genuinely useful: it
# catches the most common "aim-verify was worth running" case, an install
# directory that is missing or partially deployed.
# ---------------------------------------------------------------------------

INSTALL_DIR_ENV = "AI_MEMORY_INSTALL_DIR"
DEFAULT_INSTALL_DIR = "~/.ai-memory"
_CORE_SUBDIRS = ("src", "scripts", "docker")


class InstallDirCheck:
    """Confirms the AI-Memory install directory and its core subdirs exist."""

    id = "install-dir-present"
    category = "runtime"

    def run(self, ctx: dict) -> CheckResult:
        install_dir = Path(
            os.environ.get(INSTALL_DIR_ENV, DEFAULT_INSTALL_DIR)
        ).expanduser()

        if not install_dir.is_dir():
            return CheckResult(
                check_id=self.id,
                category=self.category,
                status="fail",
                message=f"install directory not found: {install_dir}",
                remediation="Run scripts/install.sh to install AI-Memory.",
                evidence={"install_dir": str(install_dir), "exists": False},
            )

        missing = [d for d in _CORE_SUBDIRS if not (install_dir / d).is_dir()]
        if missing:
            return CheckResult(
                check_id=self.id,
                category=self.category,
                status="fail",
                message=(f"install directory is missing subdirs: {', '.join(missing)}"),
                remediation="Re-run scripts/install.sh — the install looks incomplete.",
                evidence={"install_dir": str(install_dir), "missing": missing},
            )

        return CheckResult(
            check_id=self.id,
            category=self.category,
            status="pass",
            message=f"install directory OK: {install_dir}",
            evidence={"install_dir": str(install_dir)},
        )


register(InstallDirCheck())


# ---------------------------------------------------------------------------
# Runner — thin, closed to modification. Accumulates ALL results (no
# fail-fast); a check that raises is isolated into its own fail result.
# ---------------------------------------------------------------------------


def run_checks(
    ctx: dict | None = None, registry: list[Check] | None = None
) -> list[CheckResult]:
    ctx = ctx or {}
    results: list[CheckResult] = []
    for check in registry if registry is not None else REGISTRY:
        try:
            results.append(check.run(ctx))
        except Exception as exc:  # isolate one bad check from the rest
            results.append(
                CheckResult(
                    check_id=getattr(check, "id", check.__class__.__name__),
                    category=getattr(check, "category", "unknown"),
                    status="fail",
                    message=f"check crashed: {exc}",
                    remediation="Report this to the AI-Memory project (see aim-verify SKILL.md).",
                )
            )
    return results


def worst_status(results: list[CheckResult]) -> str:
    """The single worst status across all results; "pass" if the list is empty."""
    if not results:
        return "pass"
    return max(results, key=lambda r: _SEVERITY_RANK[r.status]).status


def exit_code_for(results: list[CheckResult]) -> int:
    """0 = all pass/warn/skip (warnings never fail the run); 1 = >=1 fail.

    Exit code 2 is reserved for "the verifier itself could not run" (e.g. an
    unhandled error outside any single check) and is set by main(), not here.
    """
    return 1 if worst_status(results) == "fail" else 0


# ---------------------------------------------------------------------------
# Redaction seam — PLAN-037 P2 implements the real scrub (safe-key allowlist
# + secret-pattern scrubber). Every renderer below routes through this
# function so P2 is a one-function change, not a renderer rewrite.
# ---------------------------------------------------------------------------


def redact(results: list[CheckResult]) -> list[CheckResult]:
    """PASS-THROUGH STUB (P1). P2 replaces the body with the real scrub pass
    over every result's message/remediation/evidence. Callers must not skip
    this call even though it is currently a no-op."""
    return results


# ---------------------------------------------------------------------------
# Renderers — two projections of the same (redacted) result list.
# ---------------------------------------------------------------------------


def render_human(results: list[CheckResult]) -> str:
    lines = []
    for r in redact(results):
        glyph = STATUS_GLYPH[r.status]
        lines.append(f"{glyph} [{r.category}] {r.check_id}: {r.message}")
        if r.status in ("warn", "fail") and r.remediation:
            lines.append(f"    -> {r.remediation}")
    return "\n".join(lines)


def render_json(results: list[CheckResult]) -> list[dict]:
    return [
        {
            "check": r.check_id,
            "status": r.status,
            "severity": _SEVERITY_RANK[r.status],
            "message": r.message,
            "remediation": r.remediation,
        }
        for r in redact(results)
    ]


# ---------------------------------------------------------------------------
# Consent-gated reporter seam — PLAN-037 P3. Documented no-op in P1: do not
# implement issue-filing logic anywhere else in this module.
# ---------------------------------------------------------------------------


def maybe_offer_report(results: list[CheckResult], *, interactive: bool) -> None:
    """Seam for the P3 consent-gated GitHub-issue reporter.

    P1 stub: always a no-op. P3 replaces this body with: interactive-only,
    default-No `Report this to the AI-Memory project? [y/N]` prompt; CI /
    non-interactive (`interactive=False`) never prompts and never files; the
    body sent is the already-redacted report (`redact(results)`), never a
    fresh unscrubbed dump.
    """
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aim-verify", description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="machine-readable JSON output"
    )
    args = parser.parse_args(argv)

    try:
        results = run_checks()
    except Exception as exc:  # the verifier itself could not run
        print(f"aim-verify: could not run: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(render_json(results), indent=2))
    else:
        print(render_human(results))

    maybe_offer_report(results, interactive=sys.stdin.isatty())

    return exit_code_for(results)


if __name__ == "__main__":
    sys.exit(main())
