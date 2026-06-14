#!/usr/bin/env python3
"""Content-drift detection for per-operator scaffolded sanctum files (BP-173).

When an operator's already-scaffolded sanctum files (BOND/CAPABILITIES/CREED/
INDEX/LORE/MEMORY/PERSONA/PULSE) drift from the *evolving* reference templates,
the operator must see a recommended add/remove WITH rationale — never a silent
overwrite, never a hard-default to stale content. This generalizes the
``langfuse-guard`` version-drift pattern (a recorded reference, offline
deterministic detection, surface→human-decides, never auto-apply) from *version*
drift to *content* drift.

Design (W-07 skills-with-scripts): this is the deterministic, fragile core invoked
BY PATH from SKILL.md. The model orchestrates (which sanctum, how to read the
recommendations); this script does the exact unit parsing, fingerprint comparison,
classification, and ack-file bookkeeping.

The decision rule that makes "stale vs customized" decidable is the anchored
fingerprint (BP-173 §3): the reference owns a set of fingerprintable units (template
``##`` sections). Drift = a reference unit is absent (MISSING), matches a prior
fingerprint (SUPERSEDED), or was removed from the reference (ORPHAN). Operator
content that is additive or has replaced the reference framing is CUSTOMIZED and is
NEVER recommended for removal — the anti-clobber guarantee. "Bytes differ = drift"
is the explicit anti-pattern (BP-173 §3) and is not what this script does.

Safety (v1 — detect + ack, READ-ONLY for sanctum content):
- ``detect`` is the DEFAULT and NEVER writes a sanctum file or a template. There is
  no ``--apply`` / content write path in v1 (deferred).
- ``--ack`` / ``--prune-ack`` write ONLY the skill's own per-project ack sidecar
  (ESLint-bulk-suppressions model, BP-173 §4) — bookkeeping that suppresses
  intentional divergence; it never touches operator content.
- The anti-clobber guarantee is structural: classification iterates reference-owned
  unit ids only, so operator-authored content is invisible to the remove path; an
  ORPHAN is recommended-for-removal only when the operator's section is a pristine,
  uncustomized scaffold remnant.

Usage:
    # Detect drift in a sanctum dir (DEFAULT — read-only, never writes content):
    python3 content_drift.py <sanctum-path>

    # Show the full previewable diff for each recommendation (else index-not-log):
    python3 content_drift.py <sanctum-path> --show-diff

    # Acknowledge an intentional divergence so it stops nagging (writes ack sidecar):
    python3 content_drift.py <sanctum-path> --ack LORE.md::system-architecture

    # Drop ack entries whose unit no longer drifts (writes ack sidecar):
    python3 content_drift.py <sanctum-path> --prune-ack

    # Maintenance: (re)generate the reference fingerprint sidecars from the templates
    # (reads the *-template.md files; writes the *.fingerprints.json sidecars beside
    # them — the templates themselves are NEVER modified):
    python3 content_drift.py <templates/assets-path> --emit-fingerprints
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# --- Constants (every value carries its BP-173 rationale) ---------------------

# DEC-PM333-D7 #2: v1 covers the sanctum family (8 files) ONLY. Each operator file
# maps to its reference template (and thus to a ``<template>.fingerprints.json``
# sidecar). Per-CLI guidance family is deferred to v1.1.
SANCTUM_FILES = {
    "BOND.md": "BOND-template.md",
    "CAPABILITIES.md": "CAPABILITIES-template.md",
    "CREED.md": "CREED-template.md",
    "INDEX.md": "INDEX-template.md",
    "LORE.md": "LORE-template.md",
    "MEMORY.md": "MEMORY-template.md",
    "PERSONA.md": "PERSONA-template.md",
    "PULSE.md": "PULSE-template.md",
}

# BP-173 §5: rank by severity, HIGH first. SUPERSEDED-and-misleading framing is the
# most dangerous (the operator is acting on stale guidance) → HIGH; a MISSING section
# is a gap → MEDIUM; an ORPHAN is cosmetic → LOW. A sidecar unit may override its own
# severity; otherwise the per-class default applies.
SEVERITY_BY_CLASS = {"SUPERSEDED": "HIGH", "MISSING": "MEDIUM", "ORPHAN": "LOW"}
SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# Only these classes are actionable recommendations. MATCH and CUSTOMIZED produce no
# finding: MATCH is current; CUSTOMIZED is operator-owned content the contract
# protects (never recommend its removal).
ACTIONABLE = ("MISSING", "SUPERSEDED", "ORPHAN")

# DEC-PM333-D3: fingerprints are a sidecar shipped beside each template.
FINGERPRINT_SUFFIX = ".fingerprints.json"

# DEC-PM333-D7 #4: the ack-file is per-project and committed in the user's repo
# (diff-reviewable). It lives beside the operator's sanctum, under the project's
# ``_ai-memory/`` dir. Override with --ack-file.
ACK_FILENAME = "content-drift-ack.json"

# Default reference location: the runtime install ships the templates + sidecars
# under the sanctum-init skill assets. Home-relative (no hardcoded maintainer path —
# feedback_production_multi_operator_portability_gate). Override with
# --fingerprints-dir (tests pass a tmp dir).
DEFAULT_FINGERPRINTS_DIR = (
    Path.home()
    / ".ai-memory"
    / "_ai-memory"
    / "pov"
    / "skills"
    / "aim-agent-sanctum-init"
    / "assets"
)

# A markdown placeholder such as {user_name} / {birth_date} that the template ships
# and the scaffold resolves to a real value. For presence matching the reference
# framing AROUND a placeholder is what is owned, so a placeholder matches any value.
_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")

# In the STRICT ORPHAN/remove test a placeholder may resolve ONLY to a short,
# value-shaped fill — never to a clause of operator prose (the anti-clobber boundary).
# A value sub-token is one alphanumeric run (Unicode); underscores and prose
# punctuation are excluded so a fill cannot absorb the emphasis/clause framing around
# it.
_VALUE_SUBTOKEN = r"[^\W_]+"
# A resolved value is a SHORT run of sub-tokens joined by spaces, apostrophes, or
# hyphens — a name, a date, a language ("Alice Chen", "Mary-Jane", "O'Brien",
# "2026-05-30", "English"). The cap bounds the TOTAL sub-token count, so apostrophe-
# and hyphen-joined runs are bounded too: an unbounded "a-b-c-…" chain or "a'b'c'…"
# run exceeds the cap and is rejected, instead of collapsing to a single token as a
# space-only word count would. The cap direction is always safe: exceeding it
# classifies the section CUSTOMIZED (keep), never ORPHAN (remove).
_MAX_PLACEHOLDER_VALUE_TOKENS = 5
_VALUE_RUN = rf"{_VALUE_SUBTOKEN}(?:[ '\-]{_VALUE_SUBTOKEN}){{0,{_MAX_PLACEHOLDER_VALUE_TOKENS - 1}}}"

# Thematic breaks (---/***/___) are structural section delimiters, never part of a
# unit's reference content.
_THEMATIC_BREAK_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")


@dataclass
class Finding:
    """One classified drift recommendation for a single reference-owned unit."""

    op_filename: str  # the operator sanctum file, e.g. "LORE.md"
    unit_id: str  # stable heading slug, e.g. "system-architecture"
    heading: str  # the reference heading line, e.g. "## System Architecture"
    drift_class: str  # MISSING | SUPERSEDED | ORPHAN
    severity: str  # HIGH | MEDIUM | LOW
    rationale: str  # why this is recommended (human-decides input)
    reference_fingerprint: str  # current ref fingerprint (ack re-surface key)
    diff_preview: str  # previewable detail, shown on --show-diff
    suppressed: bool = False  # acked at the current reference fingerprint

    @property
    def ack_key(self) -> str:
        return f"{self.op_filename}::{self.unit_id}"


# --- Canonicalization + fingerprinting ----------------------------------------


def split_frontmatter(text: str) -> list[str]:
    """Return the body lines (frontmatter stripped). Frontmatter is reference
    metadata, not a drift unit."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return lines
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[idx + 1 :]
    return lines  # unterminated — treat the whole file as body


def canonical_text(lines: list[str]) -> str:
    """Whitespace-normalized, structure-stripped representation of a unit's content.

    Drops blank lines and thematic breaks (structural, not content), strips each
    line, and collapses internal whitespace so that cosmetic reflow does not register
    as drift. Case is preserved for readable diffs; the fingerprint is computed over
    this string.
    """
    kept = []
    for line in lines:
        if not line.strip():
            continue
        if _THEMATIC_BREAK_RE.match(line):
            continue
        kept.append(line.strip())
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def fingerprint(canonical: str) -> str:
    """Stable content fingerprint of a unit's canonical text (BP-173 §3)."""
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def slug(heading_text: str) -> str:
    """Stable unit id from a heading's text: lowercase, non-alnum runs → '-'."""
    return re.sub(r"[^a-z0-9]+", "-", heading_text.strip().lower()).strip("-")


def parse_units(body_lines: list[str]) -> dict[str, tuple[str, str]]:
    """Group body lines into reference-owned units keyed by heading slug.

    A unit is a ``##`` section: its id is the slug of the heading text, its value is
    ``(heading_line, canonical_content)`` where the content spans every line after the
    ``## heading`` up to the next ``##``/``#`` heading (``###`` subsections and their
    prose are part of the parent unit). The lone ``#`` title and any pre-section
    preamble are not units.
    """
    units: dict[str, tuple[str, str]] = {}
    heading: str | None = None
    uid: str | None = None
    buf: list[str] = []
    in_fence = False

    def flush() -> None:
        if uid is not None and heading is not None:
            units[uid] = (heading, canonical_text(buf))

    for line in body_lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            # A ``## `` inside a fenced code block is literal content, not a unit
            # boundary; track the fence so it is not mis-parsed as a heading.
            in_fence = not in_fence
            if uid is not None:
                buf.append(line)
            continue
        if in_fence:
            if uid is not None:
                buf.append(line)
            continue
        if stripped.startswith("## "):
            flush()
            heading = stripped
            uid = slug(stripped[3:])
            buf = []
            continue
        if stripped.startswith("# ") or stripped == "#":
            # h1 title (or a bare top-level heading) ends the current unit.
            flush()
            heading = None
            uid = None
            buf = []
            continue
        if uid is not None:
            buf.append(line)
    flush()
    return units


def _presence_pattern(guidance_canonical: str) -> re.Pattern:
    """Compile a placeholder-aware pattern for one unit's reference guidance.

    The reference owns the framing AROUND any ``{placeholder}``; the scaffold resolves
    the placeholder to a real value. So a placeholder matches any non-empty run while
    every other character is matched literally.
    """
    parts = _PLACEHOLDER_RE.split(guidance_canonical)
    return re.compile(".+?".join(re.escape(p) for p in parts))


def guidance_present(guidance_canonical: str, body_canonical: str) -> bool:
    """True if the operator's section still contains this reference framing anywhere
    (it may also carry operator-added content — that is fine, the framing is current).
    """
    if not guidance_canonical:
        return False
    return _presence_pattern(guidance_canonical).search(body_canonical) is not None


def _pristine_pattern(guidance_canonical: str) -> re.Pattern:
    """Compile the STRICT pattern for the ORPHAN/remove test: every literal framing
    segment matched exactly, each ``{placeholder}`` matched only by a bounded
    value-like run (``_VALUE_RUN``). Unlike ``_presence_pattern`` (placeholder → any
    ``.+?`` run), a placeholder here cannot span operator-authored prose, so a section
    that filled the placeholder AND added its own content does not ``fullmatch``.
    """
    parts = _PLACEHOLDER_RE.split(guidance_canonical)
    return re.compile(_VALUE_RUN.join(re.escape(p) for p in parts))


def is_pristine_remnant(guidance_canonical: str, body_canonical: str) -> bool:
    """True if the operator's section is ONLY the reference guidance with each
    placeholder resolved to a simple value — no operator content added. This is the
    strict, safe boundary for an ORPHAN remove recommendation: any added prose (a
    placeholder filled with more than a bare value, or any extra text around the
    framing) makes the section CUSTOMIZED (keep). Bias is to CUSTOMIZED when
    ambiguous — a false keep is acceptable, a false remove is the cardinal failure."""
    if not guidance_canonical:
        return body_canonical == ""
    return _pristine_pattern(guidance_canonical).fullmatch(body_canonical) is not None


# --- Fingerprint sidecar generation (maintenance mode) ------------------------


def build_sidecar(template_path: Path) -> dict:
    """Build the reference fingerprint sidecar for one template (reads only).

    On first generation every unit is ``current`` with no prior fingerprints and no
    orphans — drift appears only as the template evolves. Re-running this after a
    template changes is how priors/orphans are introduced (a maintenance step that
    versions the sidecar with the template).
    """
    text = template_path.read_text(encoding="utf-8")
    units = parse_units(split_frontmatter(text))
    return {
        "template": template_path.name,
        "reference_version": fingerprint(canonical_text(text.splitlines())),
        "units": [
            {
                "id": uid,
                "heading": heading,
                "guidance": guidance,
                "fingerprint": fingerprint(guidance),
                "prior": {},  # {prior_fingerprint: prior_guidance_text}
                "status": "current",  # or "orphan" once removed from the template
                "severity": None,  # None → per-class default
            }
            for uid, (heading, guidance) in units.items()
        ],
    }


def emit_fingerprints(assets_dir: Path) -> int:
    """Write a ``<template>.fingerprints.json`` beside each ``*-template.md``."""
    templates = sorted(assets_dir.glob("*-template.md"))
    if not templates:
        print(f"No *-template.md files found in {assets_dir}.")
        return 1
    for template in templates:
        sidecar = build_sidecar(template)
        out = assets_dir / (template.stem + FINGERPRINT_SUFFIX)
        out.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {out.name} ({len(sidecar['units'])} units)")
    return 0


# --- Classification -----------------------------------------------------------


def classify_file(
    op_filename: str, op_text: str, sidecar: dict, acks: dict
) -> list[Finding]:
    """Classify one operator file against its reference sidecar (pure, read-only).

    Iterates REFERENCE-OWNED units only — so operator-authored content is structurally
    invisible to the remove path (the anti-clobber guarantee). Per unit:
      - current unit, heading absent in operator file        → MISSING (recommend ADD)
      - current unit, operator retains current framing        → MATCH (no finding)
      - current unit, operator retains a *prior* framing      → SUPERSEDED (recommend UPDATE)
      - current unit, operator replaced the framing entirely  → CUSTOMIZED (no finding)
      - orphan unit, operator section is a pristine remnant   → ORPHAN (recommend REMOVE)
      - orphan unit, operator added any content               → CUSTOMIZED (no finding)
    """
    op_units = parse_units(split_frontmatter(op_text))
    findings: list[Finding] = []

    for unit in sidecar.get("units", []):
        uid = unit["id"]
        heading = unit["heading"]
        guidance = unit.get("guidance", "")
        cur_fp = unit["fingerprint"]
        priors = unit.get("prior", {})
        status = unit.get("status", "current")

        drift_class: str | None = None
        diff_preview = ""

        if status == "orphan":
            if uid not in op_units:
                continue  # already gone — nothing to recommend
            _, body = op_units[uid]
            if is_pristine_remnant(guidance, body):
                drift_class = "ORPHAN"
                diff_preview = (
                    f"- REMOVE? (reference-owned, looks like the original scaffold):\n"
                    f"{heading}\n{guidance}"
                )
            else:
                continue  # operator customized it → CUSTOMIZED, never recommend removal
        else:
            if uid not in op_units:
                drift_class = "MISSING"
                diff_preview = f"+ ADD this reference section:\n{heading}\n{guidance}"
            else:
                _, body = op_units[uid]
                if guidance_present(guidance, body):
                    continue  # MATCH — current framing present
                elif any(guidance_present(pt, body) for pt in priors.values()):
                    drift_class = "SUPERSEDED"
                    diff_preview = (
                        f"  your framing (older):\n  {body}\n"
                        f"  current reference framing:\n  {guidance}"
                    )
                else:
                    continue  # operator replaced the framing → CUSTOMIZED, respected

        severity = unit.get("severity") or SEVERITY_BY_CLASS.get(drift_class, "LOW")
        rationale = _rationale(drift_class, op_filename, heading)
        key = f"{op_filename}::{uid}"
        suppressed = key in acks and acks[key].get("reference_fingerprint") == cur_fp

        findings.append(
            Finding(
                op_filename=op_filename,
                unit_id=uid,
                heading=heading,
                drift_class=drift_class,
                severity=severity,
                rationale=rationale,
                reference_fingerprint=cur_fp,
                diff_preview=diff_preview,
                suppressed=suppressed,
            )
        )
    return findings


def _rationale(drift_class: str, op_filename: str, heading: str) -> str:
    name = heading.lstrip("# ").strip()
    if drift_class == "MISSING":
        return (
            f"The reference template added the '{name}' section; your {op_filename} "
            f"does not have it. Consider adding it."
        )
    if drift_class == "SUPERSEDED":
        return (
            f"Your '{name}' section matches an earlier version of the reference "
            f"framing; the template has since updated it. Review the change."
        )
    return (
        f"The reference no longer includes '{name}'. Your {op_filename} still has it "
        f"and it looks like the original scaffold text — if that is right, you may "
        f"remove it; if you have come to rely on it, keep it."
    )


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Severity-ranked, HIGH first (BP-173 §5)."""
    return sorted(
        findings,
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.op_filename, f.unit_id),
    )


# --- Project scope + ack file -------------------------------------------------


def resolve_scope(explicit: str | None, cwd: str | None) -> str:
    """Resolve the project ``group_id`` via the canonical resolver
    (feedback_project_scope_resolution_canonical). Adds the repo / runtime ``src`` to
    the import path so ``memory.project`` is importable, then delegates — no cwd-only
    inference, no hardcoded paths."""
    here = Path(__file__).resolve()
    candidates = []
    # Walk up to find the repo root that owns ``src/memory`` (where the resolver lives)
    # instead of hard-coding the skill's nesting depth — robust to layout changes.
    for parent in here.parents:
        if (parent / "src" / "memory").is_dir():
            candidates.append(parent / "src")
            break
    candidates.append(Path.home() / ".ai-memory" / "src")  # runtime install fallback
    for cand in candidates:
        if cand.is_dir() and str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
    from memory.project import resolve_project_id

    return resolve_project_id(cwd, explicit=explicit, warn=False)


def default_ack_path(sanctum_dir: Path) -> Path:
    """The committed, per-project ack sidecar location (DEC-PM333-D7 #4).

    sanctum layout is ``<project-root>/_ai-memory/sanctum/<agent_id>/``; the ack file
    sits under the project's ``_ai-memory/`` so it is committed and diff-reviewable.
    """
    parents = sanctum_dir.resolve().parents
    project_root = parents[1] if len(parents) >= 2 else sanctum_dir
    return project_root / ACK_FILENAME


def load_acks(ack_path: Path, group_id: str | None) -> dict:
    """Load ack entries, refusing a file scoped to a different project (no
    cross-project leak — T7). Returns the ``acks`` map only.

    When the project scope could not be resolved (``group_id is None``, e.g. offline)
    a project-stamped ack file is also refused: without a resolved scope its ownership
    cannot be verified, so applying it could let another project's acks suppress
    findings. The safe direction is to ignore it and show the findings.
    """
    if not ack_path.is_file():
        return {}
    try:
        data = json.loads(ack_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"  warning: could not read ack file {ack_path} — ignoring it")
        return {}
    file_pid = data.get("project_id")
    if file_pid is not None and group_id is None:
        print(
            f"  warning: ack file {ack_path.name} is scoped to project "
            f"'{file_pid}' but the current project scope is unresolved — ignoring it "
            f"(no cross-project leak; showing findings)"
        )
        return {}
    if group_id is not None and file_pid is not None and file_pid != group_id:
        print(
            f"  warning: ack file {ack_path.name} is scoped to project "
            f"'{file_pid}', not '{group_id}' — ignoring it (no cross-project leak)"
        )
        return {}
    return data.get("acks", {})


def save_acks(ack_path: Path, group_id: str, acks: dict) -> None:
    """Write the ack sidecar, stamped with the resolved project id. Refuses to
    overwrite a file owned by a different project (protects another project's acks)."""
    if ack_path.is_file():
        try:
            existing = json.loads(ack_path.read_text(encoding="utf-8"))
            other = existing.get("project_id")
            if other is not None and other != group_id:
                raise SystemExit(
                    f"refusing to overwrite ack file {ack_path} owned by project "
                    f"'{other}' (resolved project is '{group_id}')."
                )
        except json.JSONDecodeError:
            pass
    ack_path.parent.mkdir(parents=True, exist_ok=True)
    ack_path.write_text(
        json.dumps({"schema": 1, "project_id": group_id, "acks": acks}, indent=2)
        + "\n",
        encoding="utf-8",
    )


# --- Detect orchestration + reporting -----------------------------------------


def load_sidecar(fingerprints_dir: Path, template_name: str) -> dict | None:
    path = fingerprints_dir / (Path(template_name).stem + FINGERPRINT_SUFFIX)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"  warning: could not read sidecar {path.name} — skipping")
        return None


def detect(sanctum_dir: Path, fingerprints_dir: Path, acks: dict) -> list[Finding]:
    """Classify every present sanctum file against its reference sidecar. Read-only —
    never writes a sanctum file or a template."""
    findings: list[Finding] = []
    for op_name, template_name in SANCTUM_FILES.items():
        op_path = sanctum_dir / op_name
        if not op_path.is_file():
            continue
        sidecar = load_sidecar(fingerprints_dir, template_name)
        if sidecar is None:
            continue
        findings.extend(
            classify_file(op_name, op_path.read_text(encoding="utf-8"), sidecar, acks)
        )
    return findings


def report(findings: list[Finding], show_diff: bool) -> None:
    """Batched, severity-ranked notify (BP-173 §5). The notify itself is a cheap
    count + pointer (index-not-log, BP-159); the full diff is on-demand (--show-diff).
    """
    active = [f for f in findings if not f.suppressed]
    suppressed = [f for f in findings if f.suppressed]
    ordered = sort_findings(active)

    by_sev = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in ordered:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1

    print(
        f"\ncontent drift: {len(ordered)} recommendation(s) "
        f"(HIGH {by_sev['HIGH']} · MEDIUM {by_sev['MEDIUM']} · LOW {by_sev['LOW']})"
        + (f"; {len(suppressed)} acknowledged (suppressed)" if suppressed else "")
    )
    if not ordered:
        print("  no action recommended — your sanctum is current.")
        return

    for f in ordered:
        print(f"\n  [{f.severity}] {f.drift_class}  {f.op_filename} → {f.heading}")
        print(f"    {f.rationale}")
        print(f"    ack with: --ack {f.ack_key}")
        if show_diff and f.diff_preview:
            for line in f.diff_preview.splitlines():
                print(f"      {line}")
    if not show_diff:
        print("\n  (re-run with --show-diff to preview each change)")
    print("\n  Nothing changes until you choose. v1 is detect + acknowledge only.")


def do_ack(
    keys: list[str], findings: list[Finding], ack_path: Path, group_id: str, acks: dict
) -> int:
    """Record an ack for each drifting unit named, keyed by the current reference
    fingerprint so it re-surfaces only when the reference changes (BP-173 §4)."""
    by_key = {f.ack_key: f for f in findings}
    changed = False
    for key in keys:
        f = by_key.get(key)
        if f is None:
            print(
                f"  skip --ack {key}: no current drift for that unit (nothing to ack)"
            )
            continue
        acks[key] = {
            "reference_fingerprint": f.reference_fingerprint,
            "class": f.drift_class,
        }
        print(f"  acked {key} (suppressed until the reference unit changes)")
        changed = True
    if changed:
        save_acks(ack_path, group_id, acks)
        print(f"  wrote {ack_path}")
    return 0


def do_prune_ack(
    findings: list[Finding], ack_path: Path, group_id: str, acks: dict
) -> int:
    """Drop ack entries whose unit no longer drifts at the acked reference
    fingerprint (BP-173 §4 prune pass)."""
    live = {
        f.ack_key: f.reference_fingerprint
        for f in findings
        if f.drift_class in ACTIONABLE
    }
    dropped = [
        key
        for key, entry in list(acks.items())
        if live.get(key) != entry.get("reference_fingerprint")
    ]
    for key in dropped:
        del acks[key]
        print(f"  pruned stale ack: {key}")
    if dropped:
        save_acks(ack_path, group_id, acks)
        print(f"  wrote {ack_path} ({len(dropped)} stale entr(ies) removed)")
    else:
        print("  no stale ack entries to prune.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Content-drift detection for per-operator sanctum files: detect "
            "(read-only) + acknowledge. Never writes a sanctum file in v1."
        ),
    )
    parser.add_argument(
        "path",
        help="Sanctum directory (scans the 8 sanctum files), or the assets dir with "
        "--emit-fingerprints.",
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="Show the full previewable diff per recommendation (default: count + pointer).",
    )
    parser.add_argument(
        "--ack",
        action="append",
        default=[],
        metavar="FILE::unit-id",
        help="Acknowledge an intentional divergence (writes the per-project ack sidecar). Repeatable.",
    )
    parser.add_argument(
        "--prune-ack",
        action="store_true",
        help="Drop ack entries whose unit no longer drifts (writes the ack sidecar).",
    )
    parser.add_argument(
        "--group-id",
        default=None,
        help="Project scope (group_id). When omitted it is resolved via the canonical resolver.",
    )
    parser.add_argument(
        "--fingerprints-dir",
        default=None,
        help=f"Where the reference *{FINGERPRINT_SUFFIX} sidecars live "
        f"(default: the runtime sanctum-init assets dir).",
    )
    parser.add_argument(
        "--ack-file",
        default=None,
        help="Override the ack sidecar path (default: <project-root>/"
        + ACK_FILENAME
        + ").",
    )
    parser.add_argument(
        "--emit-fingerprints",
        action="store_true",
        help="Maintenance: (re)generate the *.fingerprints.json sidecars from the "
        "templates in <path>. Reads templates; never modifies them.",
    )
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f"Path not found: {root}")
        return 1

    if args.emit_fingerprints:
        print(f"aim-content-drift · emitting fingerprint sidecars from {root}")
        return emit_fingerprints(root)

    if not root.is_dir():
        print(f"Expected a sanctum directory: {root}")
        return 1

    fingerprints_dir = (
        Path(args.fingerprints_dir)
        if args.fingerprints_dir
        else DEFAULT_FINGERPRINTS_DIR
    )
    if not fingerprints_dir.is_dir():
        print(
            f"Fingerprints dir not found: {fingerprints_dir}\n"
            f"Pass --fingerprints-dir, or install the runtime so the reference "
            f"sidecars are available."
        )
        return 1

    writes_ack = bool(args.ack) or args.prune_ack
    group_id: str | None = args.group_id
    if writes_ack and group_id is None:
        try:
            group_id = resolve_scope(None, str(root))
        except Exception as exc:  # import or fail-loud resolution error
            print(
                f"Cannot resolve project scope for ack bookkeeping ({exc}). "
                f"Pass --group-id explicitly."
            )
            return 1
    elif group_id is None:
        # Plain detect: scope is only needed to validate an ack file if one exists.
        try:
            group_id = resolve_scope(None, str(root))
        except Exception:
            group_id = None  # offline / unresolved — proceed without ack validation

    ack_path = Path(args.ack_file) if args.ack_file else default_ack_path(root)
    acks = load_acks(ack_path, group_id)

    print("aim-content-drift · DETECT (read-only — no sanctum file will be changed)")
    print(f"sanctum: {root.resolve()}")
    print(f"reference: {fingerprints_dir}")

    findings = detect(root, fingerprints_dir, acks)

    if args.ack:
        if group_id is None:
            print("Cannot ack without a resolvable project scope. Pass --group-id.")
            return 1
        return do_ack(args.ack, findings, ack_path, group_id, acks)
    if args.prune_ack:
        if group_id is None:
            print(
                "Cannot prune acks without a resolvable project scope. Pass --group-id."
            )
            return 1
        return do_prune_ack(findings, ack_path, group_id, acks)

    report(findings, args.show_diff)
    return 0


if __name__ == "__main__":
    sys.exit(main())
