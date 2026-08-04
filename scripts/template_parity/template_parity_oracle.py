#!/usr/bin/env python3
"""template-parity-oracle — PLAN-035 P2 keystone: report-only template-parity
conformance for shipped singletons and template-instantiated record families.

**Phase A (this file, as of this commit): SCRIPT SKELETON ONLY.** Structure and
control flow — argparse CLI, target/glob resolution, check dispatch, report
rendering — are real and wired end-to-end against the hand fixture under
fixtures/. The check functions (C1/C3/C6) and the UNMANAGED scan are STUBS:
each returns a clearly-labeled placeholder Finding so the dispatch/report path
can be proven, but none of them implement the real comparison semantics.
Phase B wires the real registry and implements the comparison logic.

Checks (PLAN-035 §3a), all runtime + report-only + per-user-project:
  C1  required_skeleton ⊆ actual — singletons AND every glob (family) match.
      BP-189 open-world subset semantic: missing required elements are
      flagged; extras and all values are out of scope.
  C3  every declared target/glob resolves to an actual on-disk file.
  C6  conventions (entry_pattern/order, cap_lines/cap_kb) — asserted, not
      trusted from the declaration.
  --  AI-Memory-owned paths matching no registry entry -> UNMANAGED
      (informational; a user's own files/dirs are silent, never flagged).

C2/C4/C5 (CI-blocking, source-repo-only wiring checks) are OUT OF SCOPE for
this script — see PLAN-035 §3a.

Never prints file contents or values — only template ids, relative paths, and
missing-element/convention NAMES (CLAUDE.md §7).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

# ── Finding model ────────────────────────────────────────────────────────────

STRUCT_NONCONFORMANT = "STRUCT_NONCONFORMANT"
CONVENTION_VIOLATION = "CONVENTION_VIOLATION"
OVER_CAP = "OVER_CAP"
UNMANAGED = "UNMANAGED"
UNBACKED = "UNBACKED"

FINDING_TYPES = {
    STRUCT_NONCONFORMANT,
    CONVENTION_VIOLATION,
    OVER_CAP,
    UNMANAGED,
    UNBACKED,
}


@dataclass(frozen=True)
class Finding:
    verdict: str  # one of FINDING_TYPES
    template: str | None  # registry `template` id; None for UNMANAGED (no owning entry)
    path: str  # path relative to --project-root, or the declared pattern for UNBACKED
    message: str  # names only, never file contents/values (CLAUDE.md §7)

    def render(self) -> str:
        tmpl = self.template or "-"
        return f"  [{self.verdict:21}] {tmpl}: {self.path} — {self.message}"


# ── Registry loading ─────────────────────────────────────────────────────────


def load_registry(registry_path: Path) -> list[dict]:
    with registry_path.open() as fh:
        data = yaml.safe_load(fh)
    entries = data.get("templates", []) if isinstance(data, dict) else []
    if not entries:
        raise SystemExit(f"template-parity-oracle: no templates in registry {registry_path}")
    return entries


# ── target/glob resolution ───────────────────────────────────────────────────


def _strip_project_token(pattern: str) -> str:
    """Strip the `{PROJECT}` placeholder token a registry pattern may carry."""
    return pattern.replace("{PROJECT}/", "").replace("{PROJECT}", "")


def resolve_entry(entry: dict, project_root: Path) -> list[Path]:
    """Resolve a registry entry's `target` (singleton) or `glob` (family) to
    actual files under project_root. Returns [] if nothing matches — that is
    a valid, expected outcome (e.g. an optional target never seeded), not an
    error at the resolution layer; C3 interprets emptiness.
    """
    if "target" in entry:
        rel = _strip_project_token(entry["target"])
        candidate = project_root / rel
        return [candidate] if candidate.is_file() else []
    if "glob" in entry:
        rel = _strip_project_token(entry["glob"])
        return sorted(p for p in project_root.glob(rel) if p.is_file())
    raise ValueError(
        f"registry entry {entry.get('template', '?')} declares neither target nor glob"
    )


def declared_pattern(entry: dict) -> str:
    """The human-readable declared target/glob pattern for an entry (for
    messages — never a resolved file path)."""
    raw = entry.get("target") or entry.get("glob") or "?"
    return _strip_project_token(raw)


# ── Stub checks (Phase B implements the real comparison logic) ──────────────


def check_c1_required_skeleton(
    entry: dict, resolved: list[Path], project_root: Path
) -> list[Finding]:
    """C1 — required_skeleton ⊆ actual, singleton + every glob member (PLAN-035
    §3a; BP-189 §2.2 open-world subset semantic).

    TODO(Phase B): parse each resolved file's structure (headings and/or
    frontmatter keys per entry["required_skeleton"]'s `required_sections` /
    `required_frontmatter_keys`) and diff against the declared skeleton; emit
    STRUCT_NONCONFORMANT naming only the missing element NAMES (never values).

    STUB: unconditionally flags every resolved file when the entry declares a
    required_skeleton, so the dispatch path is proven. Does not parse or
    compare structure.
    """
    skeleton = entry.get("required_skeleton")
    if not skeleton:
        return []
    return [
        Finding(
            verdict=STRUCT_NONCONFORMANT,
            template=entry.get("template"),
            path=str(path.relative_to(project_root)),
            message="STUB — Phase B: diff required_skeleton against actual structure",
        )
        for path in resolved
    ]


def check_c3_declared_target_present(
    entry: dict, resolved: list[Path], project_root: Path
) -> list[Finding]:
    """C3 — every declared target/glob resolves to an actual on-disk file
    (PLAN-035 §3a).

    NAMING JUDGMENT CALL (surfaced, not silently decided): PLAN-035 §3a/§5
    name `UNBACKED` only for the C4 wiring direction (a POV-workflow
    reference to a target with no shipped template). C3's "declared target,
    zero files" is the mirror direction (registry -> disk) and has no verdict
    name of its own anywhere in the plan. This stub reuses UNBACKED as the
    generalization "a declaration exists but nothing backs it" so the report
    format can represent it. Phase B/team-lead should confirm this mapping or
    assign C3 its own verdict before real logic lands.

    TODO(Phase B): for `glob` (family) entries, reconcile resolved members
    against any expected-membership source rather than treating "zero
    matches" as the only failure signal.

    STUB: only checks resolved-emptiness — no membership reconciliation.
    """
    if not (entry.get("target") or entry.get("glob")):
        return []
    if resolved:
        return []
    return [
        Finding(
            verdict=UNBACKED,
            template=entry.get("template"),
            path=declared_pattern(entry),
            message="STUB — Phase B: declared target/glob resolved to zero files",
        )
    ]


def check_c6_conventions(
    entry: dict, resolved: list[Path], project_root: Path
) -> list[Finding]:
    """C6 — convention conformance: entry_pattern/order (CONVENTION_VIOLATION)
    and cap_lines/cap_kb (OVER_CAP), asserted rather than trusted from the
    declaration (PLAN-035 §3a).

    TODO(Phase B): parse each resolved file's `entry_pattern` occurrences and
    assert `order` (e.g. newest_first — walking entries top-to-bottom and
    diffing against a recency signal); assert `cap_lines`/`cap_kb` against
    the file's actual line count / byte size. Emit CONVENTION_VIOLATION
    naming the offending entry; emit OVER_CAP with actual vs. cap.

    STUB: emits one placeholder per declared convention dimension, per
    resolved file, so both verdict types are wired. Does not parse content
    or measure size.
    """
    conventions = entry.get("conventions")
    if not conventions:
        return []
    findings: list[Finding] = []
    for path in resolved:
        rel = str(path.relative_to(project_root))
        if "entry_pattern" in conventions or "order" in conventions:
            findings.append(
                Finding(
                    verdict=CONVENTION_VIOLATION,
                    template=entry.get("template"),
                    path=rel,
                    message="STUB — Phase B: assert entry_pattern/order convention",
                )
            )
        if "cap_lines" in conventions or "cap_kb" in conventions:
            findings.append(
                Finding(
                    verdict=OVER_CAP,
                    template=entry.get("template"),
                    path=rel,
                    message="STUB — Phase B: assert cap_lines/cap_kb against actual size",
                )
            )
    return findings


def find_unmanaged(
    entries: list[dict], resolved_by_entry: dict[int, list[Path]], project_root: Path
) -> list[Finding]:
    """AI-Memory-owned paths under project_root matching no registry entry
    (PLAN-035 §3a; informational). "A user's own files/dirs are not our
    business — silent."

    FRICTION (surfaced, not silently decided): the registry shape in scope
    here (target/glob/class/required_skeleton/conventions/consumed_by) carries
    no ownership signal beyond the entries themselves. A naive full-tree scan
    (this stub) cannot distinguish "ours, unregistered" from "the user's own
    directory" — PLAN-035 §5's product/user boundary Done-When test requires
    zero findings on arbitrary user dirs, which this stub cannot satisfy as
    written. Phase B needs an explicit ownership-root list or path-prefix
    convention from the registry (or a separate ownership manifest) before
    this scan can be scoped correctly.

    STUB: scans the entire project_root tree and flags every file not
    resolved by any registry entry.
    """
    covered = {p.resolve() for paths in resolved_by_entry.values() for p in paths}
    if not project_root.is_dir():
        return []
    findings: list[Finding] = []
    for path in sorted(project_root.rglob("*")):
        if path.is_dir():
            continue
        if path.resolve() in covered:
            continue
        findings.append(
            Finding(
                verdict=UNMANAGED,
                template=None,
                path=str(path.relative_to(project_root)),
                message="STUB — Phase B: scope scan to AI-Memory-owned roots only",
            )
        )
    return findings


# ── Dispatch ──────────────────────────────────────────────────────────────────


def run_checks(entries: list[dict], project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    resolved_by_entry: dict[int, list[Path]] = {}
    for i, entry in enumerate(entries):
        resolved = resolve_entry(entry, project_root)
        resolved_by_entry[i] = resolved
        findings.extend(check_c1_required_skeleton(entry, resolved, project_root))
        findings.extend(check_c3_declared_target_present(entry, resolved, project_root))
        findings.extend(check_c6_conventions(entry, resolved, project_root))
    findings.extend(find_unmanaged(entries, resolved_by_entry, project_root))
    return findings


# ── Report ────────────────────────────────────────────────────────────────────


def render_text(findings: list[Finding], project_root: Path) -> str:
    if not findings:
        return f"template-parity-oracle (report-only): PARITY_OK — no findings — {project_root}"
    lines = [f"template-parity-oracle (report-only): {len(findings)} finding(s) — {project_root}"]
    lines.extend(f.render() for f in findings)
    return "\n".join(lines)


def render_json(findings: list[Finding]) -> str:
    return json.dumps([asdict(f) for f in findings], indent=2)


# ── CLI ───────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="template-parity-oracle",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--registry", type=Path, required=True, help="path to the template-parity registry YAML"
    )
    parser.add_argument(
        "--project-root", type=Path, required=True, help="project root to check for conformance"
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="report output format"
    )
    args = parser.parse_args(argv)

    entries = load_registry(args.registry)
    findings = run_checks(entries, args.project_root)

    if args.format == "json":
        print(render_json(findings))
    else:
        print(render_text(findings, args.project_root))

    # Report-only, always (PLAN-035 §3a runtime posture / BP-185 Gate 3
    # doctrine) — this script never blocks. CI-blocking checks (C2/C4/C5)
    # are a separate, out-of-scope surface.
    return 0


if __name__ == "__main__":
    sys.exit(main())
