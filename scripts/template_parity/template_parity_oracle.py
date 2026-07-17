#!/usr/bin/env python3
"""template-parity-oracle — PLAN-035 P2 keystone: report-only template-parity
conformance for shipped singletons and template-instantiated record families.

**Phase B (this file, as of this commit): real check logic.** Structure and
control flow — argparse CLI, target/glob resolution, check dispatch, report
rendering — were wired in Phase A. C1/C3/C6 and the UNMANAGED scan now
implement the real comparison semantics against the frozen registry.

Checks (PLAN-035 §3a), all runtime + report-only + per-user-project:
  C1  required_skeleton ⊆ actual — singletons AND every glob (family) match.
      BP-189 open-world subset semantic: missing required elements are
      flagged; extras and all values are out of scope.
  C3  every declared `produces: singleton` target resolves to an actual
      on-disk file (a `produces: family` glob resolving to zero is legitimate).
  C6  conventions (entry_pattern/order, cap_lines/cap_kb) — asserted, not
      trusted from the declaration. The report discloses which other
      declared convention sub-keys it does NOT check.
  --  a family-glob member matching no entry's match_frontmatter
      discriminant (e.g. a plan with a malformed/absent plan_role) ->
      STRUCT_NONCONFORMANT, naming the discriminant key only.
  --  AI-Memory-owned paths matching no registry entry -> UNMANAGED
      (informational; a user's own files/dirs are silent, never flagged).

C2/C4/C5 (CI-blocking, source-repo-only wiring checks) are OUT OF SCOPE for
this script — see PLAN-035 §3a.

Never prints file contents or values — only template ids, relative paths, and
missing-element/convention NAMES (CLAUDE.md §7).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

# ── Finding model ────────────────────────────────────────────────────────────

STRUCT_NONCONFORMANT = "STRUCT_NONCONFORMANT"
CONVENTION_VIOLATION = "CONVENTION_VIOLATION"
OVER_CAP = "OVER_CAP"
UNMANAGED = "UNMANAGED"
MISSING_TARGET = "MISSING_TARGET"
# UNBACKED is reserved for the C4 wiring direction (a POV-workflow reference
# to a target with no shipped template) — out of scope for this runtime
# script (DEC-PM409-D2). Never emitted here; kept in FINDING_TYPES so the
# verdict vocabulary stays complete for downstream consumers (e.g. C4 CI gate).
UNBACKED = "UNBACKED"

FINDING_TYPES = {
    STRUCT_NONCONFORMANT,
    CONVENTION_VIOLATION,
    OVER_CAP,
    UNMANAGED,
    MISSING_TARGET,
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
        raise SystemExit(
            f"template-parity-oracle: no templates in registry {registry_path}"
        )
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


def _apply_glob_exclude(entry: dict, resolved: list[Path]) -> list[Path]:
    """Drop registry-declared `glob_exclude` basenames/patterns (e.g.
    `README.md`, `_TEMPLATE.md`, `EXAMPLE_*.md`) from a family's resolved
    member list. These are shipped decoys/documentation living alongside
    real instances in the same glob'd directory, not record instances to
    structurally check — matched against them they'd both fail C1 (they're
    stubs, not real content) and pollute the UNMANAGED-coverage set."""
    excludes = entry.get("glob_exclude")
    if not excludes:
        return resolved
    return [
        p for p in resolved if not any(fnmatch.fnmatch(p.name, pat) for pat in excludes)
    ]


# ── Structure parsing helpers ────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_YAML_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)
_INT_RE = re.compile(r"\d+")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split leading `---`-delimited YAML frontmatter off a markdown file.
    Returns ({} if absent/unparsable, the remaining body text)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        fm = None
    return (fm if isinstance(fm, dict) else {}), text[m.end() :]


def _extract_headings(body: str) -> list[str]:
    return [line.rstrip() for line in body.splitlines() if line.startswith("#")]


def _heading_present(required: str, headings: list[str], match_case: bool) -> bool:
    """A required heading matches if some actual heading starts with it AND
    the next character (if any) is not alphanumeric — a word-boundary-aware
    prefix match. The registry pins some headings truncated (a trailing `*`
    marker, e.g. `## Ordering rule*` for the on-disk `## Ordering rule (gate
    BUILD/VERIFY, not thought)`; or unmarked-but-prefix-normalized, e.g.
    `## Current Year` for `## Current Year: [YYYY]` — see reconcile-notes.md).
    Plain startswith() would also match `## Active Task` against an unrelated
    `## Active Tasks` heading (verified against the live SESSION_WORK_INDEX.md
    — a real false-negative); the word-boundary guard rejects that while still
    allowing the intentional truncated/prefix-normalized pins above.
    """
    needle = required[:-1] if required.endswith("*") else required
    flags = 0 if match_case else re.IGNORECASE
    pattern = re.compile(re.escape(needle) + r"(?![A-Za-z0-9])", flags)
    return any(pattern.match(h) for h in headings)


def _extract_yaml_body_keys(body: str) -> set:
    """Top-level keys of the first fenced ```yaml block in a markdown body
    (e.g. project-status.md's routing block)."""
    m = _YAML_FENCE_RE.search(body)
    if not m:
        return set()
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return set()
    return set(data.keys()) if isinstance(data, dict) else set()


def _bold_field_present(name: str, body: str) -> bool:
    """A leading-bold `**Key**:` metadata line (e.g. `**Sprint**: ...`)."""
    pattern = re.compile(r"^\*\*" + re.escape(name) + r"\*\*\s*:", re.MULTILINE)
    return bool(pattern.search(body))


def _apply_match_frontmatter(entry: dict, resolved: list[Path]) -> list[Path]:
    """Route family-glob members to the entry whose `match_frontmatter`
    discriminant (e.g. `plan_role`) they actually carry (PLAN-035 §3a
    match_frontmatter — the plan-family discriminant). Entries with no
    `match_frontmatter` apply to every resolved member unfiltered."""
    match = entry.get("match_frontmatter")
    if not match:
        return resolved
    matched = []
    for path in resolved:
        fm, _ = _parse_frontmatter(_read_text(path))
        if all(fm.get(k) == v for k, v in match.items()):
            matched.append(path)
    return matched


# ── C1 / C3 / C6 / UNMANAGED (real logic) ────────────────────────────────────


def check_c1_required_skeleton(
    entry: dict, resolved: list[Path], project_root: Path
) -> list[Finding]:
    """C1 — required_skeleton ⊆ actual, singleton + every glob member (PLAN-035
    §3a; BP-189 §2.2 open-world subset semantic). Missing required elements
    are flagged by NAME only; extras and all values are out of scope.

    Honors every skeleton kind present in the frozen registry:
      - required_sections           — markdown ATX headings (prefix match)
      - required_frontmatter_keys   — top-level keys of `---` frontmatter
      - required_yaml_body_keys     — top-level keys of a fenced ```yaml body
                                       block (e.g. project-status.md)
      - required_yaml_keys (kind: yaml) — top-level keys of a pure-YAML file
                                       (e.g. PROJECT_STANDARDS.yaml; not named
                                       in the C1 task brief's 4-kind list but
                                       present in the frozen registry — see
                                       completion report)
      - required_fields             — leading-bold `**Key**:` metadata lines
    and `match_frontmatter` routing for plan-family globs.
    """
    skeleton = entry.get("required_skeleton")
    if not skeleton:
        return []
    targets = _apply_match_frontmatter(entry, _apply_glob_exclude(entry, resolved))
    match_case = skeleton.get("match_case", True)
    findings: list[Finding] = []
    for path in targets:
        text = _read_text(path)
        missing: list[str] = []

        if skeleton.get("kind") == "yaml":
            try:
                data = yaml.safe_load(text)
            except yaml.YAMLError:
                data = None
            keys = set(data.keys()) if isinstance(data, dict) else set()
            missing.extend(
                k for k in skeleton.get("required_yaml_keys", []) if k not in keys
            )
        else:
            fm, body = _parse_frontmatter(text)
            headings = _extract_headings(body)
            missing.extend(
                s
                for s in skeleton.get("required_sections", [])
                if not _heading_present(s, headings, match_case)
            )
            missing.extend(
                k for k in skeleton.get("required_frontmatter_keys", []) if k not in fm
            )
            yaml_body_keys = _extract_yaml_body_keys(body)
            missing.extend(
                k
                for k in skeleton.get("required_yaml_body_keys", [])
                if k not in yaml_body_keys
            )
            missing.extend(
                f
                for f in skeleton.get("required_fields", [])
                if not _bold_field_present(f, body)
            )

        if missing:
            findings.append(
                Finding(
                    verdict=STRUCT_NONCONFORMANT,
                    template=entry.get("template"),
                    path=str(path.relative_to(project_root)),
                    message="missing: " + ", ".join(missing),
                )
            )
    return findings


def check_c3_declared_target_present(
    entry: dict, resolved: list[Path], project_root: Path
) -> list[Finding]:
    """C3 — every declared `produces: singleton` target resolves to an actual
    on-disk file (PLAN-035 §3a). Own verdict token `MISSING_TARGET`
    (DEC-PM409-D2) — never `UNBACKED`, which is reserved for the C4 wiring
    direction and is out of scope for this script.

    A `produces: family` glob resolving to zero files is NOT checked here —
    zero instances of a record family (e.g. no bugs filed yet, no fix-specs
    written yet) is a legitimate state, not a missing artifact; flagging it
    would break the fresh-install-zero-findings invariant (PLAN-035 §5).
    """
    if entry.get("produces") != "singleton":
        return []
    if not entry.get("target"):
        return []
    if _apply_glob_exclude(entry, resolved):
        return []
    return [
        Finding(
            verdict=MISSING_TARGET,
            template=entry.get("template"),
            path=declared_pattern(entry),
            message="declared target resolved to zero files",
        )
    ]


_TRAILING_SUBID_RE = re.compile(r"-D\d+\s*$")


def _entry_sort_key(entry_text: str) -> int | None:
    """Recency proxy for an `entry_pattern` match: the integer embedded in
    its SESSION-level token (e.g. `### DEC-PM407-D6` -> 407), found by first
    stripping the trailing `-D<n>` sub-entry suffix and then taking the
    first embedded integer in what remains. Entries from the same write
    (e.g. one session's `DEC-PM407-D1..D8`) are appended in ascending
    sub-sequence within their own block — real, valid usage (verified
    against the live decision-log.md) — so the sub-id number must never
    leak into the key; stripping it first is what makes that hold.

    Returns None ("abstain") when the stripped stem has no digits at all
    (e.g. `DEC-HOTFIX-D1`) — a numberless prefix's recency relative to its
    neighbors cannot be reliably determined, so it must never be guessed at
    (a prior version used the FIRST embedded integer anywhere in the text,
    which picked up the sub-id itself for numberless prefixes and false-
    flagged legitimate `D1/D2/D3` same-session order — see PLAN-035 P2
    Phase B fix round)."""
    stem = _TRAILING_SUBID_RE.sub("", entry_text)
    m = _INT_RE.search(stem)
    return int(m.group(0)) if m else None


def _find_order_violation(body: str, entry_pattern: str) -> str | None:
    """Walk matched entries top-to-bottom; flag the first one whose session
    key is GREATER than the last determinate key seen above it — i.e. a
    newer session-block appearing after (below) an older one, the real PM
    #407 "appended to bottom" defect (a session's entries landed below an
    older session's instead of being prepended above it).

    Entries with an indeterminate key (`_entry_sort_key` returns None) are
    skipped for comparison in both directions — they neither trigger nor
    clear a violation — so recency that can't be reliably read from the id
    never produces a guessed finding; the last determinate key stays the
    comparison anchor across them.
    """
    regex = re.compile(entry_pattern, re.MULTILINE)
    entries = [m.group(0).strip() for m in regex.finditer(body)]
    prev_key: int | None = None
    for entry_text in entries:
        key = _entry_sort_key(entry_text)
        if key is None:
            continue
        if prev_key is not None and key > prev_key:
            return entry_text
        prev_key = key
    return None


def check_c6_conventions(
    entry: dict, resolved: list[Path], project_root: Path
) -> list[Finding]:
    """C6 — convention conformance: entry_pattern/order (CONVENTION_VIOLATION,
    naming the offending entry) and cap_lines/cap_kb (OVER_CAP, measured
    against the file's actual line count / byte size) — asserted, not trusted
    from the declaration (PLAN-035 §3a).
    """
    conventions = entry.get("conventions")
    if not conventions:
        return []
    findings: list[Finding] = []
    for path in _apply_glob_exclude(entry, resolved):
        rel = str(path.relative_to(project_root))
        text = _read_text(path)

        if (
            "entry_pattern" in conventions
            and conventions.get("order") == "newest_first"
        ):
            offender = _find_order_violation(text, conventions["entry_pattern"])
            if offender:
                findings.append(
                    Finding(
                        verdict=CONVENTION_VIOLATION,
                        template=entry.get("template"),
                        path=rel,
                        message=f"order violation (newest_first): {offender}",
                    )
                )

        over: list[str] = []
        cap_lines = conventions.get("cap_lines")
        if cap_lines is not None and len(text.splitlines()) > cap_lines:
            over.append("cap_lines")
        cap_kb = conventions.get("cap_kb")
        if cap_kb is not None and path.stat().st_size / 1024 > cap_kb:
            over.append("cap_kb")
        if over:
            findings.append(
                Finding(
                    verdict=OVER_CAP,
                    template=entry.get("template"),
                    path=rel,
                    message="over cap: " + ", ".join(over),
                )
            )
    return findings


def _owned_roots(entries: list[dict]) -> set[str]:
    """AI-Memory-owned directories: the union of parent dirs the registry's
    declared targets/globs live in (PLAN-035 §3a). For a glob, the parent is
    the deepest non-wildcard path prefix. Non-recursive by construction — a
    directory is owned only if the registry declares a target/glob whose
    immediate parent it is; nested directories under an owned root that are
    themselves undeclared (e.g. a maintainer's own `oversight/tasks/` scratch
    tree) are NOT owned roots and stay out of scan scope (the product/user
    boundary Done-When test)."""
    roots = set()
    for entry in entries:
        parts = declared_pattern(entry).split("/")[:-1]
        prefix = []
        for part in parts:
            if any(ch in part for ch in "*?["):
                break
            prefix.append(part)
        if prefix:
            roots.add("/".join(prefix))
    return roots


_DEBRIS_SUFFIXES = (".bak",)
_DEBRIS_PREFIXES = (".audit",)


def find_unmanaged(
    entries: list[dict], resolved_by_entry: dict[int, list[Path]], project_root: Path
) -> list[Finding]:
    """AI-Memory-owned paths under project_root matching no registry entry
    (PLAN-035 §3a; informational). "A user's own files/dirs are not our
    business — silent." Scoped to `_owned_roots(entries)`, scanned
    non-recursively (direct file children only).

    This is a deliberate, permanent boundary, not a to-do: a directory is in
    scope only if the registry declares a target/glob whose immediate parent
    it is. Nested subdirectories under an owned root (e.g. an `.audit/`
    logs tree, a maintainer's own scratch subdir) are NEVER descended into,
    on purpose — recursing would flood UNMANAGED with debris (snapshot
    `.bak` files, log dirs, ad hoc notes) on every run and is exactly what
    breaks the product/user-boundary invariant (PLAN-035 §5): a user's own
    files anywhere under an owned root, not just its direct children, are
    not this oracle's business. Known non-template debris that can still
    land as a *direct* child of an owned root (editor/tooling snapshots) is
    skipped explicitly below rather than flagged.
    """
    covered = {p.resolve() for paths in resolved_by_entry.values() for p in paths}
    findings: list[Finding] = []
    for root in sorted(_owned_roots(entries)):
        root_path = project_root / root
        if not root_path.is_dir():
            continue
        for path in sorted(root_path.iterdir()):
            if path.is_dir():
                continue
            if path.name.endswith(_DEBRIS_SUFFIXES) or path.name.startswith(
                _DEBRIS_PREFIXES
            ):
                continue
            if path.resolve() in covered:
                continue
            findings.append(
                Finding(
                    verdict=UNMANAGED,
                    template=None,
                    path=str(path.relative_to(project_root)),
                    message="file under an AI-Memory-owned root matches no registry entry",
                )
            )
    return findings


def find_family_discriminant_orphans(
    entries: list[dict], resolved_by_entry: dict[int, list[Path]], project_root: Path
) -> list[Finding]:
    """A file that matches a family's raw PATH-glob but matches NO entry's
    `match_frontmatter` discriminant among the entries sharing that glob is
    otherwise invisible: every entry's own `_apply_match_frontmatter` routes
    around it (so C1 never runs on it), yet it's still in `resolved_by_entry`
    (so `find_unmanaged`'s covered set hides it too). Net effect without this
    check: a plan with a malformed/typo/absent discriminant key (e.g.
    `plan_role: standalon`, or no `plan_role` at all) produces zero findings
    — the exact 54-plan defect class PLAN-035 P2 exists to catch.

    Groups entries by identical glob string among those declaring
    `match_frontmatter`, and flags any raw-glob member matched by none of
    them. Names the discriminant KEY only (e.g. `plan_role`), never the
    file's actual value (CLAUDE.md §7).
    """
    groups: dict[str, list[int]] = {}
    for i, entry in enumerate(entries):
        if "glob" in entry and entry.get("match_frontmatter"):
            groups.setdefault(_strip_project_token(entry["glob"]), []).append(i)

    findings: list[Finding] = []
    flagged: set[Path] = set()
    for idxs in groups.values():
        raw = resolved_by_entry[idxs[0]]
        for i in idxs:
            raw = _apply_glob_exclude(entries[i], raw)

        discriminant_keys: set[str] = set()
        matched_any: set[Path] = set()
        for i in idxs:
            entry = entries[i]
            discriminant_keys.update(entry["match_frontmatter"].keys())
            matched_any.update(_apply_match_frontmatter(entry, raw))

        for path in raw:
            if path in matched_any or path in flagged:
                continue
            flagged.add(path)
            findings.append(
                Finding(
                    verdict=STRUCT_NONCONFORMANT,
                    template=None,
                    path=str(path.relative_to(project_root)),
                    message="no registry family matches its "
                    + "/".join(sorted(discriminant_keys))
                    + " discriminant",
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
    findings.extend(
        find_family_discriminant_orphans(entries, resolved_by_entry, project_root)
    )
    findings.extend(find_unmanaged(entries, resolved_by_entry, project_root))
    return findings


# ── Report ────────────────────────────────────────────────────────────────────

# Convention sub-keys the frozen registry declares that C6 does not assert
# (id_pattern, status_values, filename_pattern, etc. — free-text/enum rules
# not yet wired into script-verifiable checks). Kept in sync manually with
# check_c6_conventions' actual coverage.
CHECKED_CONVENTION_KEYS = {"entry_pattern", "order", "cap_lines", "cap_kb"}


def unchecked_convention_dimensions(entries: list[dict]) -> list[str]:
    """Convention sub-keys declared across `entries` that C6 does not check
    (PLAN-035 §3a declares ~20; C6 asserts 4). A PARITY_OK / clean report
    must not be read as "fully convention-conformant" when dimensions like
    `id_pattern` or `status_values` were never asserted at all — this makes
    that gap explicit in the report rather than leaving it silently inert.
    """
    declared: set[str] = set()
    for entry in entries:
        conventions = entry.get("conventions")
        if conventions:
            declared.update(conventions.keys())
    return sorted(declared - CHECKED_CONVENTION_KEYS)


def render_text(
    findings: list[Finding],
    project_root: Path,
    unchecked_conventions: list[str] | None = None,
) -> str:
    if not findings:
        lines = [
            f"template-parity-oracle (report-only): PARITY_OK — no findings — {project_root}"
        ]
    else:
        lines = [
            f"template-parity-oracle (report-only): {len(findings)} finding(s) — {project_root}"
        ]
        lines.extend(f.render() for f in findings)
    if unchecked_conventions:
        lines.append(
            "note: convention dimensions declared but not checked by this oracle: "
            + ", ".join(unchecked_conventions)
        )
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
        "--registry",
        type=Path,
        required=True,
        help="path to the template-parity registry YAML",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="project root to check for conformance",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="report output format",
    )
    args = parser.parse_args(argv)

    entries = load_registry(args.registry)
    findings = run_checks(entries, args.project_root)

    if args.format == "json":
        print(render_json(findings))
    else:
        print(
            render_text(
                findings, args.project_root, unchecked_convention_dimensions(entries)
            )
        )

    # Report-only, always (PLAN-035 §3a runtime posture / BP-185 Gate 3
    # doctrine) — this script never blocks. CI-blocking checks (C2/C4/C5)
    # are a separate, out-of-scope surface.
    return 0


if __name__ == "__main__":
    sys.exit(main())
