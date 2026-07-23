#!/usr/bin/env python3
"""Template-parity conform engine (PLAN-035 P3, Axis B — grounded in BP-190 + §3b).

Closes the "preserve-only" gap: the PLAN-033 reconcile engine keeps operator DATA
but never ADOPTS a new template STRUCTURE (`reconcile_engine.MIGRATIONS` holds only
`0001_baseline`, so every ``CONFLICT`` returns ``preserved`` with no write). This
module is the missing structural-adoption half — it brings a drifted oversight file
into conformance with its shipped template's *required skeleton*, add-only, under a
data-safety gate proven on testV2 (PM #411).

WHY THERE IS NO HAND-CODED ``0002+`` TRANSFORM CHAIN (read this before looking for one)
----------------------------------------------------------------------------------------
BP-190 §4.2 (authored 2026-07-15, *before* PLAN-035 P2 shipped) imagined Axis B as an
ordered chain of hand-coded ``Migration(from_v -> to_v, transform)`` units — one
imperative transform per structural delta, Alembic-style. That model is obsolete here,
by design, for three reasons:

  1. **Two-sources-of-truth trap.** P2 built the machine-readable structural spec that
     BP-190 itself said *"does not exist anywhere"* — the registry ``required_skeleton``
     (``scripts/template_parity/oversight-templates.yaml``) plus the oracle that diffs
     it (``template_parity_oracle.py``). A hand-coded transform would RE-ENCODE that
     skeleton as imperative code: a second, drifting copy of the same truth.
  2. **The done-gate is per-element, not a version integer.** Conformance is measured
     as ``0 STRUCT_NONCONFORMANT`` — a per-section / per-field / per-key subset check
     (BP-189 open-world subset). A monotonic ``format_version`` counter cannot express
     "section X present, field Y missing"; only the live registry diff can.
  3. **Nothing is left to hand-code.** The three fix kinds (§3b) partition exhaustively:
     Kind A (add missing sections/fields) and Kind B (set a frontmatter discriminant)
     are both computed *live* from the registry — deterministic, no transform needed;
     Kind C (renumber/restructure) is NOT safely scriptable and is HUMAN-IN-THE-LOOP.
     There is no residual auto-applying structural transform to encode.

So the "ordered apply-once migration unit" of BP-190 survives as a *registry-declared
conform operation* — (file, its registry family, current template) — applied once and
recorded in a ledger. BP-190's ledger MECHANICS are kept intact (apply-once, permanent
audit row, baseline floor, archive convention, ``resolved``-stamp for out-of-band
edits, generated ``UPDATE-RUNBOOK.md``). Only the imagined transform bodies are gone.

THE THREE FIX KINDS (§3b, PM #411 live-test intelligence)
---------------------------------------------------------
  Kind A — missing sections / ``required_fields``: add in template order, content-
           preserving. **Deterministic.** Added as BARE STRUCTURE only (a heading + a
           blank line; an empty ``**Field**:`` label) — the oracle checks *presence*,
           so empty structure reaches ``0 STRUCT``; real values are filled in later by
           the operator (HIL). **Never a ``[TODO]``/placeholder token** on a live file
           (§3b) — the PM #411 prototype's ``key: [TODO]`` frontmatter insertion is a
           defect this engine does NOT reproduce.
  Kind B — a plan-family member carrying no ``match_frontmatter`` discriminant (the
           oracle's "no registry family matches its plan_role discriminant" orphan):
           set ``plan_role: standalone``. A file whose name/title signals it is really
           a ``master`` spine or a ``session`` child is FLAGGED, never guessed.
  Kind C — the file carries its own parallel heading/numbering scheme, so a blind
           add-only would duplicate or orphan real content. **NOT scriptable** — routed
           to the runbook's Needs-attention section for a human semantic remap, then
           recorded out-of-band via the ``resolved`` stamp (reconcile_helper P1).

FRONTMATTER VALUE POLICY (data-safety line)
-------------------------------------------
A missing required frontmatter key is auto-filled ONLY when it is a *structural
constant* the template ships with a concrete value — ``class`` / ``cap_lines`` /
``cap_kb`` (identical for every instance of a class; sourced verbatim from the shipped
template's own frontmatter). Every OTHER required key (``plan_id`` / ``type`` /
``status`` / ``master_plan`` / ``step_id`` / ``session``) is a per-instance semantic
value the engine cannot invent — the shipped templates carry only placeholders/enum
literals for them (``plan_id: PLAN-<SLUG>``, ``status: draft | approved | ...``).
A file missing any such key is routed to HUMAN-IN-THE-LOOP (Needs-attention), NEVER
auto-filled with a guessed or placeholder value.

DATA-SAFETY GATE (every write; BP-187 §4 + the PM #411 proven flow)
-------------------------------------------------------------------
per-file backup -> no-line-loss precheck -> crash-atomic write -> FULL-CAPTURE oracle
re-verify (the oracle is run in-process capture, never piped through head/tail/grep —
a truncated read produced a FALSE "conformant" verdict in the field, §3b) -> per-file
gate assertion -> restore-the-backup-on-ANY-failure. Insert/move only, never delete a
line. A file counts as conformed only if its own STRUCT findings cleared AND every
original non-empty line survives.

This module is deterministic and import-testable (no network, no randomness). It is
invoked BY PATH from ``reconcile_helper.py``'s ``conform`` / ``runbook`` subcommands
(W-07 skills-with-scripts), mirroring how ``reconcile_helper`` invokes
``reconcile_engine``. It imports the shipped oracle (for parsing/finding parity) and
``reconcile_engine.atomic_write`` (the proven crash-atomic writer) by path — it changes
neither.
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# --------------------------------------------------------------------------- #
# Install/repo layout — portable across the source worktree AND the ~/.ai-memory
# runtime (identical relative structure): this file lives at
#   <root>/_ai-memory/pov/skills/aim-content-drift/scripts/conform_engine.py
# so parents[5] == <root>, under which the shipped oracle/registry/templates live.
# --------------------------------------------------------------------------- #
_SCRIPT_DIR = Path(__file__).resolve().parent
_INSTALL_ROOT = _SCRIPT_DIR.parents[4]  # <root>

DEFAULT_ORACLE = (
    _INSTALL_ROOT / "scripts" / "template_parity" / "template_parity_oracle.py"
)
DEFAULT_REGISTRY = (
    _INSTALL_ROOT / "scripts" / "template_parity" / "oversight-templates.yaml"
)
DEFAULT_TEMPLATES_ROOT = _INSTALL_ROOT / "templates" / "oversight"

# The conform ledger — sibling to the reconcile dispositions ledger (BP-190 §4.4:
# a permanent apply-once audit record). Apply-once itself is oracle-MEASURED (a
# conformant file is simply not in the pending set — a live measurement that cannot
# drift, unlike a stored "already done" flag); this ledger is the durable audit trail
# the UPDATE-RUNBOOK's Applied section reads.
CONFORM_LEDGER_REL = ".audit/state/conform-ledger.json"
CONFORM_LEDGER_SCHEMA_VERSION = "1.0"

# Structural-constant frontmatter keys the template ships concrete and identical for
# every instance of a class — the ONLY keys safe to auto-fill (see module docstring).
_AUTO_FILL_FRONTMATTER_KEYS = frozenset({"class", "cap_lines", "cap_kb"})

# A template value that is not a real value — a placeholder or an enum-literal list
# (``PLAN-<SLUG>``, ``draft | approved | ...``, ``[YYYY]``). Never copied to a live file.
_PLACEHOLDER_RE = re.compile(r"[<\[]|\bTODO\b|\bYYYY\b|\bXXX\b|\|")

# Kind-C classifier thresholds (ported from the PM #411 prototype, cold-verified).
_COVERAGE_MIN_SECTIONS = 3
_COVERAGE_MISSING_RATIO = 0.75
_STUB_MAX_BODY_LINES = 5

_DISCRIMINANT_MSG = (
    "discriminant"  # substring of the oracle's plan-family orphan message
)
_MISSING_PREFIX = "missing: "


# --------------------------------------------------------------------------- #
# Sibling-module loading by path (skill scripts are not importable as a package).
# --------------------------------------------------------------------------- #
def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_reconcile_engine = _load_by_path(
    "reconcile_engine", _SCRIPT_DIR / "reconcile_engine.py"
)
atomic_write = _reconcile_engine.atomic_write


@dataclass(frozen=True)
class ConformConfig:
    """Everything a conform run resolves against. All shipped artifacts are
    overridable so tests can point at a fixture — but every default is derived from
    the portable ``parents[5]`` layout, never a maintainer-specific path."""

    project_root: Path
    oracle_path: Path = DEFAULT_ORACLE
    registry_path: Path = DEFAULT_REGISTRY
    templates_root: Path = DEFAULT_TEMPLATES_ROOT

    def ledger_path(self) -> Path:
        return self.project_root / CONFORM_LEDGER_REL


def default_config(project_root: str | Path) -> ConformConfig:
    return ConformConfig(project_root=Path(project_root).resolve())


# --------------------------------------------------------------------------- #
# Oracle invocation (FULL-CAPTURE, JSON) + registry / template access.
# --------------------------------------------------------------------------- #
def run_oracle(cfg: ConformConfig) -> list[dict]:
    """Run the shipped oracle and return its findings as structured dicts.

    JSON format + in-process capture is full-capture by construction — the output is
    never piped through ``head``/``tail``/``grep`` (§3b: a truncated read produced a
    false "conformant" verdict). A non-JSON / failed run raises, fail-loud, rather than
    silently yielding an empty (=> "everything conformant") result.
    """
    proc = subprocess.run(
        [
            sys.executable,
            str(cfg.oracle_path),
            "--registry",
            str(cfg.registry_path),
            "--project-root",
            str(cfg.project_root),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        findings = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"conform: oracle did not return JSON (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout[:200]!r}"
        ) from exc
    if not isinstance(findings, list):
        raise RuntimeError("conform: oracle JSON was not a list of findings")
    return findings


def load_registry(cfg: ConformConfig) -> dict[str, dict]:
    """Registry entries indexed by their ``template`` id."""
    data = yaml.safe_load(cfg.registry_path.read_text(encoding="utf-8"))
    entries = data.get("templates", []) if isinstance(data, dict) else []
    if not entries:
        raise RuntimeError(f"conform: no templates in registry {cfg.registry_path}")
    return {e["template"]: e for e in entries}


def _template_file(cfg: ConformConfig, entry: dict) -> Path:
    """The shipped template file backing a registry entry (ground truth for section
    order and structural-constant frontmatter values)."""
    tmpl = entry["template"]
    rel = (
        tmpl[len("templates/oversight/") :]
        if tmpl.startswith("templates/oversight/")
        else tmpl
    )
    return cfg.templates_root / rel


# --------------------------------------------------------------------------- #
# Structure parsing — reuse the oracle's own helpers so "is this heading present"
# matches the oracle's judgement exactly (avoids a classifier/oracle disagreement).
# --------------------------------------------------------------------------- #
_oracle = _load_by_path("template_parity_oracle", DEFAULT_ORACLE)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    return _oracle._parse_frontmatter(text)


def _extract_headings(body: str) -> list[str]:
    return _oracle._extract_headings(body)


def _heading_present(required: str, headings: list[str], match_case: bool) -> bool:
    return _oracle._heading_present(required, headings, match_case)


def _heading_line_index(
    required: str, body_lines: list[str], match_case: bool
) -> int | None:
    """Line index (within ``body_lines``) of the first heading matching ``required``
    under the oracle's word-boundary prefix rule, for insertion-anchor math."""
    needle = required[:-1] if required.endswith("*") else required
    flags = 0 if match_case else re.IGNORECASE
    pattern = re.compile(re.escape(needle) + r"(?![A-Za-z0-9])", flags)
    for i, line in enumerate(body_lines):
        if line.startswith("#") and pattern.match(line.rstrip()):
            return i
    return None


def _normalize_heading(text: str) -> str:
    """Strip heading markers / leading numbering / a trailing ``*`` / a trailing
    parenthetical / trailing punctuation, and case-fold — for Kind-C collision
    detection only (never for oracle-parity matching)."""
    t = re.sub(r"^#+\s*", "", text.strip())
    t = re.sub(r"^\d+\.\s*", "", t)
    t = t.rstrip("*").strip()
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)
    # strip trailing colon/hyphen and en/em dash (u2013/u2014, escaped to keep the
    # ambiguous-unicode linter quiet) so headings that end in a dash still normalize.
    t = re.sub("[:\\-\u2013\u2014]+$", "", t).strip()
    return re.sub(r"\s+", " ", t).lower()


def _body_content_line_count(body: str) -> int:
    """Non-empty, non-heading body lines — a stub proxy (a rotated-empty tracking
    file has nothing to orphan, so the full skeleton is safe to add even at high
    missing-coverage)."""
    return len(
        [
            ln
            for ln in body.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
    )


# --------------------------------------------------------------------------- #
# Frontmatter value resolution (structural-constant keys only).
# --------------------------------------------------------------------------- #
def resolve_frontmatter_value(cfg: ConformConfig, entry: dict, key: str) -> str | None:
    """A real, concrete value for a missing frontmatter ``key``, or ``None`` if the
    engine must NOT set it deterministically (=> route the file to HIL).

    Only structural-constant keys are eligible, and only when the shipped template
    carries a concrete (non-placeholder) value for them. Everything else -> ``None``.
    """
    if key not in _AUTO_FILL_FRONTMATTER_KEYS:
        return None
    tmpl = _template_file(cfg, entry)
    if not tmpl.is_file():
        return None
    fm, _ = _parse_frontmatter(tmpl.read_text(encoding="utf-8", errors="replace"))
    if key not in fm:
        return None
    raw = fm[key]
    value = "" if raw is None else str(raw)
    if not value.strip() or _PLACEHOLDER_RE.search(value):
        return None
    return value


# --------------------------------------------------------------------------- #
# Finding split + per-file kind classification.
# --------------------------------------------------------------------------- #
@dataclass
class FileDecision:
    path: str
    template: str | None
    kind: str  # "A" | "B" | "C" | "HIL"
    reason: str | None
    missing_sections: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    missing_frontmatter_keys: list[str] = field(default_factory=list)
    extra_headings: list[str] = field(default_factory=list)


def _split_missing(
    entry: dict, missing: list[str]
) -> tuple[list[str], list[str], list[str]]:
    skeleton = entry.get("required_skeleton", {}) or {}
    req_sections = set(skeleton.get("required_sections", []))
    req_fields = set(skeleton.get("required_fields", []))
    req_fm = set(skeleton.get("required_frontmatter_keys", []))
    sections = [m for m in missing if m in req_sections]
    fields = [m for m in missing if m in req_fields]
    fm_keys = [m for m in missing if m in req_fm]
    return sections, fields, fm_keys


def classify_file(
    cfg: ConformConfig, entry: dict, path: Path, missing: list[str]
) -> FileDecision:
    """Classify one nonconformant file's fix kind (A / C / HIL) from its missing
    elements + its own on-disk structure. (Kind B is a separate finding shape.)"""
    rel = str(path.relative_to(cfg.project_root))
    sections, fields, fm_keys = _split_missing(entry, missing)

    skeleton = entry.get("required_skeleton", {}) or {}
    required_sections = skeleton.get("required_sections", [])
    match_case = skeleton.get("match_case", True)

    body = _parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))[1]
    heading_texts = _extract_headings(body)
    body_lines = body.splitlines()

    # --- Kind-C triggers (any one fires) --------------------------------------
    is_stub = _body_content_line_count(body) <= _STUB_MAX_BODY_LINES
    req_n, miss_n = len(required_sections), len(sections)
    coverage_fire = (
        req_n >= _COVERAGE_MIN_SECTIONS
        and (miss_n / req_n) >= _COVERAGE_MISSING_RATIO
        and not is_stub
    )
    collisions = []
    for ms in sections:
        nms = _normalize_heading(ms)
        if not nms:
            continue
        for h in heading_texts:
            nh = _normalize_heading(h)
            if nh and (nms in nh or nh in nms):
                collisions.append((ms, h))
                break
    present_positions = [
        idx
        for idx in (
            _heading_line_index(s, body_lines, match_case) for s in required_sections
        )
        if idx is not None
    ]
    order_violation = present_positions != sorted(present_positions)

    extra_headings = [
        h
        for h in heading_texts
        if not h.startswith("# ")
        and not any(
            _normalize_heading(h) == _normalize_heading(s) for s in required_sections
        )
    ]

    if coverage_fire or collisions or order_violation:
        reasons = []
        if coverage_fire:
            reasons.append(
                f"coverage: {miss_n}/{req_n} required sections missing (>=75%, non-stub)"
            )
        if collisions:
            reasons.append(
                "heading collision: "
                + "; ".join(f"missing '{a}' ~ existing '{b}'" for a, b in collisions)
            )
        if order_violation:
            reasons.append("required-section order mismatch vs. template")
        return FileDecision(
            rel,
            entry["template"],
            "C",
            "; ".join(reasons),
            sections,
            fields,
            fm_keys,
            extra_headings,
        )

    # --- Kind A vs HIL: any missing frontmatter key we cannot fill => HIL ------
    unfillable = [
        k for k in fm_keys if resolve_frontmatter_value(cfg, entry, k) is None
    ]
    if unfillable:
        return FileDecision(
            rel,
            entry["template"],
            "HIL",
            "requires real frontmatter value(s): " + ", ".join(unfillable),
            sections,
            fields,
            fm_keys,
            extra_headings,
        )
    return FileDecision(
        rel, entry["template"], "A", None, sections, fields, fm_keys, extra_headings
    )


def classify_kind_b(path: Path) -> tuple[str, str | None]:
    """('FIX' | 'FLAGGED', reason) for a plan-family discriminant orphan. A master
    spine / session child signal FLAGS the file (never guessed); everything else is a
    safe ``plan_role: standalone``."""
    fm, body = _parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    title = next((ln for ln in body.splitlines() if ln.startswith("# ")), "")
    signals = []
    if "MASTER" in path.name.upper():
        signals.append("filename contains MASTER")
    if re.search(r"\bmaster\b", title, re.IGNORECASE):
        signals.append("H1 title contains 'master'")
    if fm and ("master_plan" in fm or "step_id" in fm):
        signals.append("frontmatter carries master_plan/step_id")
    return ("FLAGGED", "; ".join(signals)) if signals else ("FIX", None)


@dataclass
class Classification:
    kind_a: list[FileDecision] = field(default_factory=list)
    kind_c: list[FileDecision] = field(default_factory=list)
    hil: list[FileDecision] = field(default_factory=list)
    kind_b_fix: list[dict] = field(default_factory=list)  # {"path", "template"}
    kind_b_flagged: list[dict] = field(default_factory=list)  # {"path", "reason"}
    over_cap: list[dict] = field(default_factory=list)
    unmanaged: list[dict] = field(default_factory=list)
    struct_total: int = 0


def _only_match(rel: str, only: list[str] | None) -> bool:
    return only is None or any(o in rel for o in only)


def classify(
    cfg: ConformConfig, findings: list[dict], only: list[str] | None = None
) -> Classification:
    """Partition the oracle's findings into the actionable fix kinds. OVER_CAP is
    surfaced for the runbook pointer but is NEVER a conform target (rotation's domain,
    §3b); UNMANAGED / MISSING_TARGET / CONVENTION_VIOLATION are not section work."""
    registry = load_registry(cfg)
    result = Classification()
    for f in findings:
        verdict, rel = f.get("verdict"), f.get("path", "")
        if verdict == "OVER_CAP":
            result.over_cap.append(f)
            continue
        if verdict == "UNMANAGED":
            result.unmanaged.append(f)
            continue
        if verdict != "STRUCT_NONCONFORMANT":
            continue  # MISSING_TARGET / CONVENTION_VIOLATION — not conform's concern
        result.struct_total += 1
        if not _only_match(rel, only):
            continue
        # Kind-B: plan-family discriminant orphan (no owning template on the finding).
        if not f.get("template") and _DISCRIMINANT_MSG in f.get("message", ""):
            verd, reason = classify_kind_b(cfg.project_root / rel)
            if verd == "FIX":
                result.kind_b_fix.append({"path": rel, "template": None})
            else:
                result.kind_b_flagged.append({"path": rel, "reason": reason})
            continue
        # Kind-A / C / HIL: a "missing: ..." finding against a known template family.
        entry = registry.get(f.get("template"))
        msg = f.get("message", "")
        if entry is None or not msg.startswith(_MISSING_PREFIX):
            continue
        missing = [
            m.strip() for m in msg[len(_MISSING_PREFIX) :].split(",") if m.strip()
        ]
        decision = classify_file(cfg, entry, cfg.project_root / rel, missing)
        {"A": result.kind_a, "C": result.kind_c, "HIL": result.hil}[
            decision.kind
        ].append(decision)
    return result


# --------------------------------------------------------------------------- #
# Kind-A / Kind-B edit construction (pure line insertion — no-line-loss by build).
# --------------------------------------------------------------------------- #
def _field_hosts(cfg: ConformConfig, entry: dict) -> dict[str, str | None]:
    """{required_field: hosting required_section} read from the shipped template
    (canonical placement), so an added field lands under the right section."""
    skeleton = entry.get("required_skeleton", {}) or {}
    req_fields = skeleton.get("required_fields", [])
    req_sections = skeleton.get("required_sections", [])
    match_case = skeleton.get("match_case", True)
    hosts: dict[str, str | None] = {}
    tmpl = _template_file(cfg, entry)
    if not req_fields or not tmpl.is_file():
        return hosts
    body = _parse_frontmatter(tmpl.read_text(encoding="utf-8", errors="replace"))[1]
    current = None
    for line in body.splitlines():
        if line.startswith("#"):
            for s in req_sections:
                if _heading_line_index(s, [line], match_case) is not None:
                    current = s
                    break
        for fname in req_fields:
            if fname not in hosts and re.match(
                r"^\*\*" + re.escape(fname) + r"\*\*\s*:", line.strip()
            ):
                hosts[fname] = current
    return hosts


def _section_block(required_text: str, fields: list[str]) -> list[str]:
    """A missing section as clean structure: heading + blank line, plus any empty
    ``**Field**:`` labels that live under it. No filler, no [TODO] (§3b)."""
    heading = required_text[:-1] if required_text.endswith("*") else required_text
    block = [heading + "\n", "\n"]
    for fname in fields:
        block.append(f"**{fname}**:\n")
    if fields:
        block.append("\n")
    return block


def build_kind_a_text(
    cfg: ConformConfig, entry: dict, path: Path, decision: FileDecision
) -> str:
    """Splice missing sections / fields / (structural-constant) frontmatter keys into
    ``path``'s text. Original lines are only copied forward or surrounded by inserts —
    never rewritten, reordered, or dropped."""
    skeleton = entry.get("required_skeleton", {}) or {}
    required_sections = skeleton.get("required_sections", [])
    match_case = skeleton.get("match_case", True)

    text = path.read_text(encoding="utf-8", errors="replace")
    _, body = _parse_frontmatter(text)
    body_lines = body.splitlines(keepends=True)

    field_host = _field_hosts(cfg, entry)
    present_idx = {}
    for s in required_sections:
        idx = _heading_line_index(s, [ln.rstrip("\n") for ln in body_lines], match_case)
        if idx is not None:
            present_idx[s] = idx

    # Group runs of consecutive missing sections; anchor each run before the next
    # present required section (or at end-of-body if none follows).
    missing_sections = set(decision.missing_sections)
    section_inserts: list[tuple[int, list[str]]] = []
    i, n = 0, len(required_sections)
    while i < n:
        if required_sections[i] in missing_sections:
            run = []
            while i < n and required_sections[i] in missing_sections:
                run.append(required_sections[i])
                i += 1
            anchor = next(
                (
                    present_idx[required_sections[k]]
                    for k in range(i, n)
                    if required_sections[k] in present_idx
                ),
                None,
            )
            block: list[str] = []
            for sec in run:
                flds = [
                    fn for fn in decision.missing_fields if field_host.get(fn) == sec
                ]
                block.extend(_section_block(sec, flds))
            section_inserts.append(
                (anchor if anchor is not None else len(body_lines), block)
            )
        else:
            i += 1

    # Fields whose host section already exists: insert right after that heading.
    field_inserts: dict[int, list[str]] = {}
    for fname in decision.missing_fields:
        host = field_host.get(fname)
        if host in present_idx:
            field_inserts.setdefault(present_idx[host] + 1, []).append(
                f"**{fname}**:\n"
            )

    all_inserts = section_inserts + list(field_inserts.items())
    all_inserts.sort(key=lambda x: x[0], reverse=True)  # bottom-up: indices stay valid
    new_body_lines = list(body_lines)
    for idx, lines in all_inserts:
        new_body_lines[idx:idx] = lines
    new_body = "".join(new_body_lines)

    prefix = text[
        : len(text) - len(body)
    ]  # frontmatter block + delimiters, verbatim ("" if none)

    # Structural-constant frontmatter keys — set the shipped template's real value.
    fm_values = {
        k: resolve_frontmatter_value(cfg, entry, k)
        for k in decision.missing_frontmatter_keys
    }
    fm_values = {k: v for k, v in fm_values.items() if v is not None}
    if not fm_values:
        return prefix + new_body

    if prefix.strip().startswith("---"):
        pre_lines = prefix.splitlines(keepends=True)
        close_i = next(
            (
                j
                for j in range(1, len(pre_lines))
                if pre_lines[j].rstrip("\r\n") == "---"
            ),
            None,
        )
        if close_i is None:
            raise ValueError(f"{path}: frontmatter opened but never closed")
        pre_lines[close_i:close_i] = [f"{k}: {v}\n" for k, v in fm_values.items()]
        prefix = "".join(pre_lines)
    else:
        prefix = (
            "---\n"
            + "".join(f"{k}: {v}\n" for k, v in fm_values.items())
            + "---\n"
            + prefix
        )
    return prefix + new_body


def build_kind_b_text(path: Path) -> str:
    """Set ``plan_role: standalone`` in (or prepend) the frontmatter block."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    if lines and lines[0].rstrip("\r\n") == "---":
        close = next(
            (i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"), None
        )
        if close is None:
            raise ValueError(f"{path}: frontmatter opened but never closed")
        return "".join([*lines[:close], "plan_role: standalone\n", *lines[close:]])
    return "".join(["---\n", "plan_role: standalone\n", "---\n", *lines])


# --------------------------------------------------------------------------- #
# The per-file data-safety gate.
# --------------------------------------------------------------------------- #
def _lines_preserved(original: str, new: str) -> bool:
    orig = Counter(ln for ln in original.splitlines() if ln.strip())
    got = Counter(ln for ln in new.splitlines() if ln.strip())
    return all(got[k] >= v for k, v in orig.items())


def apply_with_gate(cfg: ConformConfig, path: Path, new_text: str, gate_fn) -> dict:
    """backup -> no-line-loss precheck -> crash-atomic write -> FULL-CAPTURE oracle
    re-verify -> gate_fn -> restore-the-backup on ANY failure. ``gate_fn(findings,
    rel) -> (ok, reason)``. Never leaves a partial write behind."""
    original = path.read_text(encoding="utf-8", errors="replace")
    if not _lines_preserved(original, new_text):
        return {
            "status": "failed",
            "reason": "line-loss detected pre-write (aborted, no write)",
        }
    backup_path = atomic_write(path, new_text, backup=True)
    try:
        findings = run_oracle(cfg)
        rel = str(path.relative_to(cfg.project_root))
        ok, reason = gate_fn(findings, rel)
        if not ok:
            _restore(backup_path, path)
            return {"status": "failed", "reason": reason, "restored": True}
        return {"status": "fixed", "backup_path": backup_path}
    except Exception as exc:
        _restore(backup_path, path)
        return {"status": "failed", "reason": f"exception: {exc}", "restored": True}


def _restore(backup_path: str | None, path: Path) -> None:
    if backup_path and Path(backup_path).exists():
        import os

        os.replace(backup_path, path)


def _struct_for(findings: list[dict], rel: str) -> list[dict]:
    return [
        f
        for f in findings
        if f.get("verdict") == "STRUCT_NONCONFORMANT" and f.get("path") == rel
    ]


def gate_kind_a(findings: list[dict], rel: str):
    remaining = _struct_for(findings, rel)
    if remaining:
        return False, "STRUCT findings remain after edit: " + "; ".join(
            f.get("message", "") for f in remaining
        )
    return True, None


def gate_kind_b(findings: list[dict], rel: str):
    still = [
        f
        for f in _struct_for(findings, rel)
        if _DISCRIMINANT_MSG in f.get("message", "")
    ]
    if still:
        return False, "plan_role discriminant finding still present after edit"
    return True, None


# --------------------------------------------------------------------------- #
# Conform ledger (BP-190 §4.4 audit record; apply-once is oracle-measured).
# --------------------------------------------------------------------------- #
def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_conform_ledger(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("conformed", {})
    data.setdefault("archived", [])
    return data


def record_conform(
    ledger: dict, rel: str, kind: str, action: str, backup_path: str | None
) -> None:
    """Record a successful conform. Permanent audit row (BP-190 §4.4); a prior record
    for the same path is pushed to ``archived`` (the archive convention in this model —
    latest active, full history retained), never deleted."""
    conformed = ledger.setdefault("conformed", {})
    if rel in conformed:
        ledger.setdefault("archived", []).append(conformed[rel])
    conformed[rel] = {
        "kind": kind,
        "action_taken": action,
        "backup_path": backup_path,
        "recorded_at": _now(),
    }
    ledger["schema_version"] = CONFORM_LEDGER_SCHEMA_VERSION
    ledger["updated_at"] = _now()


def write_conform_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(
        path, json.dumps(ledger, indent=2, sort_keys=True) + "\n", backup=False
    )


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def conform(
    cfg: ConformConfig,
    *,
    kinds: str = "AB",
    only: list[str] | None = None,
    apply: bool = True,
) -> dict:
    """Run one conform pass. ``kinds`` selects which pass(es) WRITE ({'A'},{'B'},{'A','B'}).
    Kind B is applied first (it can expose a fresh Kind-A section gap under the
    now-matched family); the tree is then re-classified before the Kind-A pass. Every
    write is individually gated; Kind C / HIL are never written (surfaced only)."""
    kinds_set = set(kinds.upper())
    findings = run_oracle(cfg)
    cls = classify(cfg, findings, only)
    registry = load_registry(cfg)
    ledger_path = cfg.ledger_path()
    ledger = load_conform_ledger(ledger_path)
    out = {
        "b_fixed": [],
        "b_flagged": list(cls.kind_b_flagged),
        "b_failed": [],
        "a_fixed": [],
        "a_failed": [],
        "c_skipped": [d.path for d in cls.kind_c],
        "hil": [d.path for d in cls.hil],
        "over_cap": [f["path"] for f in cls.over_cap],
    }

    if not apply:
        out["a_pending"] = [d.path for d in cls.kind_a]
        out["b_pending"] = [b["path"] for b in cls.kind_b_fix]
        return out

    if "B" in kinds_set:
        for b in cls.kind_b_fix:
            path = cfg.project_root / b["path"]
            res = apply_with_gate(cfg, path, build_kind_b_text(path), gate_kind_b)
            if res["status"] == "fixed":
                record_conform(
                    ledger, b["path"], "B", "conformed-kind-b", res.get("backup_path")
                )
                out["b_fixed"].append(b["path"])
            else:
                out["b_failed"].append({"path": b["path"], "reason": res["reason"]})
        # Re-classify: a Kind-B fix may have exposed section gaps under the matched family.
        cls = classify(cfg, run_oracle(cfg), only)
        out["c_skipped"] = [d.path for d in cls.kind_c]
        out["hil"] = [d.path for d in cls.hil]

    if "A" in kinds_set:
        for d in cls.kind_a:
            entry = registry.get(d.template)
            path = cfg.project_root / d.path
            try:
                new_text = build_kind_a_text(cfg, entry, path, d)
            except Exception as exc:
                out["a_failed"].append(
                    {"path": d.path, "reason": f"build exception: {exc}"}
                )
                continue
            res = apply_with_gate(cfg, path, new_text, gate_kind_a)
            if res["status"] == "fixed":
                record_conform(
                    ledger, d.path, "A", "conformed-kind-a", res.get("backup_path")
                )
                out["a_fixed"].append(d.path)
            else:
                # Gate restored the backup — reclassify as needs-attention (HIL), never
                # a silent half-fix (§3b flag-and-restore).
                out["a_failed"].append({"path": d.path, "reason": res["reason"]})

    write_conform_ledger(ledger_path, ledger)
    return out


# --------------------------------------------------------------------------- #
# UPDATE-RUNBOOK.md (BP-190 §4.5 — Pending / Applied / Needs-attention).
# --------------------------------------------------------------------------- #
def render_runbook(cfg: ConformConfig, only: list[str] | None = None) -> str:
    """Render the conform-lane runbook from the LIVE oracle diff + the conform ledger.
    Pending = auto-conformable (Kind A/B) not yet conformed; Applied = ledger audit
    rows; Needs-attention = Kind C + HIL (each with the out-of-band ``resolved``
    escape hatch). OVER_CAP is EXCLUDED from conform and shown only as a pointer to the
    aim-tracking-rotate lane."""
    findings = run_oracle(cfg)
    cls = classify(cfg, findings, only)
    ledger = load_conform_ledger(cfg.ledger_path())
    conformed = ledger.get("conformed", {})

    lines = ["# Update Runbook — conform lane (generated from live oracle diff)", ""]

    lines.append("## Pending (auto-conformable — run to adopt template structure)")
    pend = [("B", b["path"], "plan_role discriminant") for b in cls.kind_b_fix] + [
        (
            "A",
            d.path,
            "missing: "
            + ", ".join(
                d.missing_sections + d.missing_fields + d.missing_frontmatter_keys
            ),
        )
        for d in cls.kind_a
    ]
    if pend:
        for kind, path, why in sorted(pend, key=lambda x: x[1]):
            lines.append(f"- [Kind {kind}] {path}")
            lines.append(f"    {why}")
            lines.append(
                f"    Apply:  reconcile_helper.py conform --project-root {cfg.project_root} --only {path}"
            )
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Applied (audit trail — from the conform ledger)")
    if conformed:
        for path in sorted(conformed):
            rec = conformed[path]
            lines.append(
                f"- {path}  [{rec.get('action_taken')}]  {rec.get('recorded_at')}"
                f"  (backup: {rec.get('backup_path')})"
            )
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Needs-attention (human-in-the-loop — not safely scriptable)")
    na = [("C", d.path, d.reason) for d in cls.kind_c] + [
        ("HIL", d.path, d.reason) for d in cls.hil
    ]
    if na:
        for kind, path, why in sorted(na, key=lambda x: x[1]):
            lines.append(f"- [{kind}] {path}")
            lines.append(f"    {why}")
            lines.append("    After hand-conforming, record it out-of-band:")
            lines.append(
                f"    reconcile_helper.py reconcile --project-root {cfg.project_root} --id {path} --disposition resolved"
            )
    else:
        lines.append("- (none)")
    lines.append("")

    if cls.over_cap:
        lines.append(
            f"## Excluded — OVER_CAP ({len(cls.over_cap)}) — NOT conform's domain"
        )
        lines.append(
            "These are rotation's concern (aim-tracking-rotate), never section work (§3b)."
        )
        for f in sorted(cls.over_cap, key=lambda x: x["path"]):
            lines.append(f"- {f['path']}")
        lines.append("")
    return "\n".join(lines)


def write_runbook(
    cfg: ConformConfig, out_path: Path, only: list[str] | None = None
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(out_path, render_runbook(cfg, only), backup=False)
    return out_path


# --------------------------------------------------------------------------- #
# CLI (thin; the helper is the real entry point).
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="PLAN-035 P3 template-parity conform engine (Axis B)."
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--kinds", default="AB", choices=["A", "B", "AB", "BA"])
    parser.add_argument("--only", default=None)
    parser.add_argument(
        "--runbook", default=None, help="write UPDATE-RUNBOOK.md to this path and exit"
    )
    args = parser.parse_args(argv)

    cfg = default_config(args.project_root)
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    if args.runbook:
        write_runbook(cfg, Path(args.runbook), only)
        print(f"runbook written: {args.runbook}")
        return 0
    result = conform(cfg, kinds=args.kinds, only=only, apply=not args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
