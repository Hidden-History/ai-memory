#!/usr/bin/env python3
"""ci_gates — PLAN-035 P2 Phase B Wave-2: C2/C4/C5 CI-blocking, source-repo-only
template-parity wiring gates (PLAN-035 §3a). These validate the shipped
template-parity registry itself and its wiring into the POV tree — they run
against the AI-Memory source repo only; a user project never runs them
(contrast with the report-only, per-user-project `template_parity_oracle.py`).

Gates:
  C2  every shipped `templates/oversight/**/*.md` file (excluding `.audit/`
      and dotfiles) is registered (a registry entry's `template:` field
      names it), and every registry entry declares a valid `produces`
      (`singleton` or `family`). A missing/invalid `produces` is
      CI-blocking — closes TD-859's fail-open, where such an entry was
      silently skipped by C1/C3 instead of being flagged.
  C4  wiring resolution (C4-design.md §3), two directions:
      (a) every registry `consumed_by` value resolves to a node in
          `oversight-schema.yaml::consumers`.
      (b) every `oversight/...` reference across the ENTIRE `_ai-memory/pov/`
          tree resolves to a backed registry target/glob at top-level-
          subdirectory granularity; a reference to an area AI-Memory ships
          no template for is UNBACKED (DEC-PM409-D2).
  C5  every registry template entry declares a `class`.

Exit code is CI-blocking: non-zero if any gate reports a finding.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from template_parity_oracle import (
    UNBACKED,
    Finding,
    declared_pattern,
    load_registry,
)

# ── Finding verdicts owned by this script ────────────────────────────────────

TEMPLATE_UNREGISTERED = "TEMPLATE_UNREGISTERED"
PRODUCES_INVALID = "PRODUCES_INVALID"
CONSUMER_UNKNOWN = "CONSUMER_UNKNOWN"
CLASS_MISSING = "CLASS_MISSING"

VALID_PRODUCES = {"singleton", "family"}

# ── C2 — template registration + valid `produces` ────────────────────────────


def check_c2_registration(templates_dir: Path, entries: list[dict]) -> list[Finding]:
    """C2 (PLAN-035 §3a). Direction 1: every shipped `*.md` file under
    `templates_dir`, excluding `.audit/` and any dotfile/dot-dir path
    component, must be some entry's `template:` value. Direction 2: every
    registry entry must declare `produces` as `singleton` or `family` —
    TD-859 fail-open closure.
    """
    findings: list[Finding] = []
    registered = {e.get("template") for e in entries}

    if templates_dir.is_dir():
        for path in sorted(templates_dir.rglob("*.md")):
            rel_parts = path.relative_to(templates_dir).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            template_id = f"templates/oversight/{'/'.join(rel_parts)}"
            if template_id not in registered:
                findings.append(
                    Finding(
                        verdict=TEMPLATE_UNREGISTERED,
                        template=None,
                        path=template_id,
                        message="shipped template has no registry entry",
                    )
                )

    for entry in entries:
        if entry.get("produces") not in VALID_PRODUCES:
            findings.append(
                Finding(
                    verdict=PRODUCES_INVALID,
                    template=entry.get("template"),
                    path=entry.get("template") or "?",
                    message="produces missing or invalid (must be singleton or family)",
                )
            )
    return findings


# ── C4(a) — consumer resolution ───────────────────────────────────────────────


def load_schema_consumers(schema_path: Path) -> set[str]:
    """Return the schema's known consumer names, or an empty set on a
    read/parse failure (permission error, missing file, TOCTOU race,
    malformed YAML) -- degrades like the rest of this pipeline instead of
    crashing with a raw traceback (cf. reconcile_helper.load_ledger); any
    `consumed_by` value then correctly surfaces as CONSUMER_UNKNOWN instead
    of the whole gate run dying (PR #336)."""
    try:
        with schema_path.open() as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return set()
    consumers = data.get("consumers") if isinstance(data, dict) else None
    return set(consumers.keys()) if isinstance(consumers, dict) else set()


def check_c4a_consumer_resolution(
    entries: list[dict], consumers: set[str]
) -> list[Finding]:
    """C4(a) (C4-design.md §3.1). Every `consumed_by` value must name a node
    in the schema's `consumers:` vocabulary. Empty/absent `consumed_by` is
    legal and produces no finding."""
    findings: list[Finding] = []
    for entry in entries:
        for value in entry.get("consumed_by") or []:
            if value not in consumers:
                findings.append(
                    Finding(
                        verdict=CONSUMER_UNKNOWN,
                        template=entry.get("template"),
                        path=declared_pattern(entry),
                        message=f"unknown consumer: {value}",
                    )
                )
    return findings


# ── C4(b) — reference resolution + UNBACKED ──────────────────────────────────

_OVERSIGHT_REF_RE = re.compile(r"oversight/[A-Za-z0-9_.*/-]+")
_HAS_WORD_CHAR_RE = re.compile(r"[A-Za-z0-9_]")

# The `*`/`.` allowance in _OVERSIGHT_REF_RE's char class exists for
# legitimate in-string globs/extensions (e.g. `oversight/bugs/*.md`); it also
# greedily swallows adjacent trailing markdown noise into the match itself --
# a bold-close `**` or a sentence-ending period. Trimmed post-match so
# `**oversight/x.md**` / `oversight/x.md.` resolve to the same key as the
# clean `oversight/x.md` instead of a spurious UNBACKED (PR #336).
_TRAILING_MD_NOISE_RE = re.compile(r"[*.]+$")

# Build/VCS noise that is not part of the shipped POV source tree (gitignored
# — see .gitignore `__pycache__/` / `*.pyc`). Excluded so compiled bytecode
# debris cannot inject spurious `oversight/...`-shaped byte sequences into the
# reference surface.
_SKIP_DIR_NAMES = {"__pycache__", ".git"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def _normalize_ref(match: str) -> str:
    """C4-design.md §3.2 normalization. A single path segment after
    `oversight/` that carries a `.` extension is a root-level singleton file
    (e.g. `oversight/project-status.md`) -> key = the exact match. Anything
    else — a deeper path, or a single segment with no extension (a directory
    named without its trailing slash, e.g. `oversight/bugs`) — normalizes to
    its first-segment directory form `oversight/<dir>/`."""
    rest = match[len("oversight/") :]
    segs = rest.split("/")
    if len(segs) == 1 and "." in segs[0]:
        return match
    return f"oversight/{segs[0]}/"


def extract_pov_references(pov_dir: Path) -> dict[str, set[str]]:
    """C4-design.md §3.2/§3.6. Scans every shipped file under `pov_dir` for
    `oversight/...` path tokens, normalizes each to its resolution key, and
    dedups to (key -> {referencing source files}) edges. Drops punctuation-
    only matches (`oversight/.`, a bare `oversight/`) per the §3.6 scope
    guard — a match with no word character after `oversight/` is a regex
    artifact, not a reference.
    """
    edges: dict[str, set[str]] = {}
    if not pov_dir.is_dir():
        return edges
    for path in sorted(pov_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix in _SKIP_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(pov_dir.parent).as_posix()
        for match in set(_OVERSIGHT_REF_RE.findall(text)):
            match = _TRAILING_MD_NOISE_RE.sub("", match)
            rest = match[len("oversight/") :]
            if not _HAS_WORD_CHAR_RE.search(rest):
                continue
            edges.setdefault(_normalize_ref(match), set()).add(rel)
    return edges


def _is_backed(key: str, declared_patterns: list[str]) -> bool:
    """C4-design.md §3.2 BACKED rule: a root singleton key must exactly
    match some entry's declared target; a directory key is backed if some
    entry's declared target/glob starts with it (the directory ships >=1
    template)."""
    if key.endswith("/"):
        return any(pattern.startswith(key) for pattern in declared_patterns)
    return key in declared_patterns


def check_c4b_reference_backing(pov_dir: Path, entries: list[dict]) -> list[Finding]:
    """C4(b) (C4-design.md §3.2-§3.3). One Finding per (UNBACKED key,
    referencing file) edge, so the multiplicity anchor (§3.4: tasks x2,
    reports x3) is directly the finding count for that key.
    """
    edges = extract_pov_references(pov_dir)
    declared_patterns = [declared_pattern(entry) for entry in entries]
    findings: list[Finding] = []
    for key in sorted(edges):
        if _is_backed(key, declared_patterns):
            continue
        for source in sorted(edges[key]):
            findings.append(
                Finding(
                    verdict=UNBACKED,
                    template=None,
                    path=key,
                    message=f"referenced in {source} but no shipped template backs it",
                )
            )
    return findings


# ── C5 — every entry declares a class ────────────────────────────────────────


def check_c5_class(entries: list[dict]) -> list[Finding]:
    """C5 (PLAN-035 §3a): every registry template entry declares `class`."""
    findings: list[Finding] = []
    for entry in entries:
        if not entry.get("class"):
            findings.append(
                Finding(
                    verdict=CLASS_MISSING,
                    template=entry.get("template"),
                    path=entry.get("template") or "?",
                    message="registry entry has no `class`",
                )
            )
    return findings


# ── Dispatch ──────────────────────────────────────────────────────────────────


def run_all_gates(repo_root: Path) -> list[Finding]:
    registry_path = (
        repo_root / "scripts" / "template_parity" / "oversight-templates.yaml"
    )
    templates_dir = repo_root / "templates" / "oversight"
    schema_path = (
        repo_root
        / "_ai-memory"
        / "_memory"
        / "parzival-sidecar"
        / "oversight-schema.yaml"
    )
    pov_dir = repo_root / "_ai-memory" / "pov"

    entries = load_registry(registry_path)
    consumers = load_schema_consumers(schema_path)

    findings: list[Finding] = []
    findings.extend(check_c2_registration(templates_dir, entries))
    findings.extend(check_c4a_consumer_resolution(entries, consumers))
    findings.extend(check_c4b_reference_backing(pov_dir, entries))
    findings.extend(check_c5_class(entries))
    return findings


# ── Report ────────────────────────────────────────────────────────────────────


def render_text(findings: list[Finding], repo_root: Path) -> str:
    if not findings:
        return f"template-parity-ci-gates (CI-blocking): PARITY_OK — no findings — {repo_root}"
    lines = [
        f"template-parity-ci-gates (CI-blocking): {len(findings)} finding(s) — {repo_root}"
    ]
    lines.extend(f.render() for f in findings)
    return "\n".join(lines)


def render_json(findings: list[Finding]) -> str:
    return json.dumps([asdict(f) for f in findings], indent=2)


# ── CLI ───────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="template-parity-ci-gates",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="AI-Memory source repo root (default: cwd)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="report output format",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()

    findings = run_all_gates(repo_root)

    if args.format == "json":
        print(render_json(findings))
    else:
        print(render_text(findings, repo_root))

    # CI-blocking, unlike the report-only oracle (PLAN-035 §3a).
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
