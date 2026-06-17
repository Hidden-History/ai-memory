#!/usr/bin/env python3
"""
tracking_rotate.py — aim-tracking-rotate backing script.

The rotate companion to aim-tracking-freshness (freshness detects drift; rotate
bounds bloat). Two modes:

  --check            The session-close enforcement gate. For every governed
                     oversight file, read its cap from the file's own
                     front-matter contract (D2) and fall back to a built-in
                     filename->cap registry when the front-matter is absent
                     (the D2 no-clobber carry-over case). Measure wc -l / wc -c.
                     On any breach, emit a SYSTEM FAILURE block (file, size,
                     cap, remedy command) and exit non-zero so closeout cannot
                     declare complete while a governed file is over cap.

  --apply <file>     The fix (BP-167 Part C rotation). Move whole entries (never
                     splitting an entry) into a dated archive shard, update the
                     manifest (append-only-log) or the reconciliation banner
                     (register), write a thin live pointer, and verify counts.
                     Append-only-logs/live-indexes rotate the OLDEST entries by
                     recency; registers rotate by RESOLVED status (an open/active
                     entry is never archived). Within a shard the append order is
                     monotonic; across shards/rotations it is not guaranteed.

Ownership boundary (vs aim-tracking-freshness / D5): rotate owns the
append-only-log + register archival. --check enforces the cap on every governed
file; --apply auto-rotation is currently shipped only for the id-H3 append-only
log (decision-log shards + manifest). The table-under-severity registers and
multi-table live-indexes (blockers-log, risk-register, SESSION_WORK_INDEX,
session-index/INDEX) are --check-enforced but --apply-deferred to TD-655 (see
MANUAL_ROTATION_FILES) — they rotate by hand for now. rotate does NOT touch the
generated bugs/INDEX.md or tech-debt/INDEX.md — those and their CLOSED.md shards
are owned by aim-tracking-freshness.

Contract source of truth: PARZIVAL-OVERSIGHT-SOT.md §14 (D1 cap mapping, D2
per-seed values) and BP-167 Part C (rotation lifecycle).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Governed-file contract registry (fallback when front-matter is absent)
# ---------------------------------------------------------------------------
#
# Values are the authoritative caps from SOT §14 D1/D2. Only rotate-owned files
# appear here; bugs/INDEX.md and tech-debt/INDEX.md are deliberately absent
# (aim-tracking-freshness owns those — no double ownership).
#
# rotatable=True  -> --apply performs entry rotation.
# rotatable=False -> check-only (heartbeat / thin register: rotation_trigger
#                    none); --apply refuses with a clear message.


@dataclass(frozen=True)
class Contract:
    cap_lines: int
    cap_kb: float
    klass: str
    rotatable: bool
    archive_target: str | None = None
    index_file: str | None = None
    # Entry-boundary regex for this file (overrides the global default). Table-
    # row files (live-index) carry '^\\| '; H3-entry files inherit the default.
    entry_pattern: str | None = None


# Relative-path (POSIX) -> Contract. Keys are matched against the file's path
# relative to the oversight root.
FALLBACK_REGISTRY: dict[str, Contract] = {
    "project-status.md": Contract(60, 6, "heartbeat", False),
    "SESSION_WORK_INDEX.md": Contract(
        80,
        12,
        "live-index",
        True,
        archive_target="session-index/INDEX.md",
        entry_pattern=r"^\| ",
    ),
    "tracking/task-tracker.md": Contract(40, 3, "register", False),
    "tracking/blockers-log.md": Contract(
        100,
        15,
        "register",
        True,
        archive_target="tracking/blockers-archive-{YYYY}.md",
    ),
    "tracking/risk-register.md": Contract(
        120,
        12,
        "register",
        True,
        archive_target="tracking/risk-archive-{YYYY}.md",
    ),
    "tracking/decision-log.md": Contract(
        150,
        50,
        "append-only-log",
        True,
        archive_target="tracking/archive/decision-log-ARCHIVE-{YYYY-MM}.md",
        index_file="tracking/decision-log-INDEX.md",
    ),
    "session-index/INDEX.md": Contract(
        120,
        10,
        "live-index",
        True,
        archive_target="session-index/archive/{YYYY-Q}.md",
        entry_pattern=r"^\| ",
    ),
}

# Generated INDEX files owned by aim-tracking-freshness. Even if a future seed
# made one of these look rotatable (cap + rotation_trigger:on-* + archive_target),
# --apply must refuse it here — no double ownership.
FRESHNESS_OWNED: frozenset[str] = frozenset({"bugs/INDEX.md", "tech-debt/INDEX.md"})

# Governed files whose REAL seed format is a table-under-severity/status register
# or a multi-table live-index, where the entry-boundary auto-rotation here cannot
# safely move whole records (DEC-PM339-D7, Will-approved Option A). Verified
# against the seed templates:
#   - blockers-log.md  : "Active Blockers" TABLE + "### BLK-" Detail H3 +
#                        "Resolved Blockers" TABLE — archiving the H3 details
#                        orphans the matching table rows.
#   - risk-register.md : TABLE rows under "### Critical/High/Medium/Low" severity
#                        headers — the H3 boundary matches a severity header, not
#                        a record.
#   - SESSION_WORK_INDEX.md : FOUR distinct tables (Active Task / Last 5 Sessions
#                        / Active Blockers / High Priority Risks); a bare '^\\| '
#                        match sheds rows from the wrong table, and the
#                        last-5 window is hand-managed (ordering not guaranteed
#                        newest-first).
#   - session-index/INDEX.md : "### [Month YYYY]" H3 sections + Current-Year and
#                        Archive tables — mixed structure.
# --check still enforces their caps (they stay in FALLBACK_REGISTRY); --apply
# refuses them non-destructively and points at manual rotation. Field-aware safe
# auto-rotation for these formats is deferred to TD-655. Enforced by rel-path
# (not the front-matter contract) so a future cap-contract seed cannot re-enable
# an unsafe --apply.
MANUAL_ROTATION_FILES: frozenset[str] = frozenset(
    {
        "tracking/blockers-log.md",
        "tracking/risk-register.md",
        "SESSION_WORK_INDEX.md",
        "session-index/INDEX.md",
    }
)

# Latest SESSION_HANDOFF_*.md (detail-record, whole-file, 60/8). Discovered by
# glob rather than fixed path; --apply on a handoff is not supported here
# (handoff archival is owned by close step-03).
HANDOFF_CONTRACT = Contract(60, 8, "detail-record", False)
HANDOFF_GLOB = "session-logs/SESSION_HANDOFF_*.md"

# Default entry boundary: an id-prefixed markdown H3 heading (DEC-/BUG-/BLK-/
# RISK-/TD-…). Requiring an id prefix (2-4 uppercase letters + '-') avoids
# matching quoted/section headings such as '### Critical' or '### Notes' that
# would otherwise split a real entry. Override with --entry-pattern (or the
# per-file contract entry_pattern) for table-row formats (e.g. '^\\| ').
DEFAULT_ENTRY_PATTERN = r"^### [A-Z]{2,4}-"

# Idempotent live-pointer marker.
POINTER_MARKER = "<!-- aim-tracking-rotate:pointer -->"

DEC_ID_RE = re.compile(r"\b(DEC-[A-Za-z0-9][A-Za-z0-9-]*)\b")

# Generic entry-id token (DEC-/BUG-/BLK-/RISK-/TD-…) used for dedup + the
# post-write id-conservation check.
ENTRY_ID_RE = re.compile(r"\b([A-Z]{2,4}-[A-Za-z0-9][A-Za-z0-9-]*)\b")

# A register entry is "resolved" (eligible to archive) only with an explicit
# resolved-class status; anything else is treated as OPEN and never archived.
RESOLVED_STATUS_RE = re.compile(
    r"(?im)^\s*[*_`]*\s*status\s*[*_`]*\s*:\s*[*_`]*\s*"
    r"(resolved|closed|done|fixed|mitigated)\b"
)


# ---------------------------------------------------------------------------
# Front-matter + sizing
# ---------------------------------------------------------------------------


def split_front_matter(text: str) -> tuple[str, str]:
    """Split a leading ``---``-fenced YAML block from the body.

    Returns ``(front_matter_including_fences, remainder)``. If there is no
    front matter, returns ``("", text)``.
    """
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---", 4)
    if end == -1:
        return "", text
    # Advance to the end of the closing fence line.
    line_end = text.find("\n", end + 1)
    if line_end == -1:
        line_end = len(text)
    return text[: line_end + 1], text[line_end + 1 :]


def parse_contract_front_matter(front_matter: str) -> Contract | None:
    """Build a Contract from front-matter keys, or None if caps are absent."""
    if not front_matter:
        return None
    values: dict[str, str] = {}
    for line in front_matter.splitlines():
        m = re.match(r"^([A-Za-z_]+):\s*(.+?)\s*$", line)
        if m:
            values[m.group(1)] = m.group(2).strip().strip("'\"")
    if "cap_lines" not in values or "cap_kb" not in values:
        return None
    try:
        cap_lines = int(values["cap_lines"])
        cap_kb = float(values["cap_kb"])
    except ValueError:
        return None
    trigger = values.get("rotation_trigger", "none").strip()
    archive = values.get("archive_target") or None
    if archive in {"N/A", "n/a", "none", "None"}:
        archive = None
    index_file = values.get("index_file") or None
    if index_file in {"N/A", "n/a", "none", "None"}:
        index_file = None
    entry_pattern = values.get("entry_pattern") or None
    if entry_pattern in {"N/A", "n/a", "none", "None"}:
        entry_pattern = None
    return Contract(
        cap_lines=cap_lines,
        cap_kb=cap_kb,
        klass=values.get("class", "unknown"),
        rotatable=trigger.startswith("on-close") and archive is not None,
        archive_target=archive,
        index_file=index_file,
        entry_pattern=entry_pattern,
    )


def measure(text: str) -> tuple[int, int]:
    """Return ``(lines, bytes)`` mirroring ``wc -l`` / ``wc -c``."""
    return text.count("\n"), len(text.encode("utf-8"))


def over_cap(lines: int, nbytes: int, contract: Contract) -> bool:
    return lines > contract.cap_lines or nbytes > contract.cap_kb * 1024


def atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (tempfile + ``os.replace``).

    Guarantees a reader/interrupted re-run never observes a half-written file,
    so the shard + live + manifest writes are crash-consistent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".rotate-tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# File discovery + contract resolution
# ---------------------------------------------------------------------------


@dataclass
class GovernedFile:
    path: Path
    rel: str
    contract: Contract
    source: str  # "front-matter" | "fallback-registry"


def resolve_contract(path: Path, rel: str) -> tuple[Contract, str] | None:
    """Resolve a file's contract: front-matter first, then fallback registry.

    Returns ``(contract, source)`` or None when the file is not governed.
    """
    if path.is_file():
        fm, _ = split_front_matter(path.read_text(encoding="utf-8"))
        fm_contract = parse_contract_front_matter(fm)
        if fm_contract is not None:
            return fm_contract, "front-matter"
    if rel in FALLBACK_REGISTRY:
        return FALLBACK_REGISTRY[rel], "fallback-registry"
    return None


def discover_governed(oversight_root: Path) -> list[GovernedFile]:
    """Enumerate the governed files that exist under the oversight root."""
    governed: list[GovernedFile] = []
    for rel in FALLBACK_REGISTRY:
        path = oversight_root / rel
        if not path.is_file():
            continue
        resolved = resolve_contract(path, rel)
        if resolved is not None:
            contract, source = resolved
            governed.append(GovernedFile(path, rel, contract, source))

    # Latest handoff (detail-record): glob, pick the lexically-greatest name
    # (dated SESSION_HANDOFF_YYYY-MM-DD_* sorts chronologically).
    handoffs = sorted(oversight_root.glob(HANDOFF_GLOB))
    if handoffs:
        latest = handoffs[-1]
        rel = latest.relative_to(oversight_root).as_posix()
        resolved = resolve_contract(latest, rel)
        contract, source = (
            resolved
            if resolved is not None
            else (HANDOFF_CONTRACT, "fallback-registry")
        )
        governed.append(GovernedFile(latest, rel, contract, source))

    return governed


def effective_entry_pattern(contract: Contract, explicit: str | None) -> str:
    """Resolve the entry-boundary regex: explicit CLI > contract > default."""
    return explicit or contract.entry_pattern or DEFAULT_ENTRY_PATTERN


# ---------------------------------------------------------------------------
# --check : the enforcement gate
# ---------------------------------------------------------------------------


def script_invocation() -> str:
    """A copy-pasteable path to this script for remedy commands."""
    return f"python {Path(__file__).resolve()}"


def rotation_can_help(
    path: Path, contract: Contract, entry_pattern: str, now: datetime
) -> bool:
    """Simulate --apply: would rotation bring this file at or under cap?

    Returns False when there is nothing eligible to rotate (no entries, or a
    register with only OPEN entries) or when even the maximal rotation leaves
    the file over cap (preamble/open-set alone exceeds it) — i.e. the remedy is
    a hand-trim, not --apply.
    """
    parsed = parse_entries(path.read_text(encoding="utf-8"), entry_pattern)
    if not parsed.entries:
        return False
    pointer_line = _pointer_line(contract, render_period(contract.archive_target, now))
    kept, moved = select_kept_moved(parsed, contract, pointer_line, None)
    if not moved:
        return False
    new_text = _render_live(parsed.front_matter, parsed.preamble, pointer_line, kept)
    return not over_cap(*measure(new_text), contract)


def run_check(oversight_root: Path) -> int:
    governed = discover_governed(oversight_root)
    now = datetime.now()
    breaches: list[str] = []
    for gf in governed:
        lines, nbytes = measure(gf.path.read_text(encoding="utf-8"))
        if not over_cap(lines, nbytes, gf.contract):
            continue
        kb = nbytes / 1024
        if gf.rel in MANUAL_ROTATION_FILES:
            remedy = (
                f"rotate {gf.rel} by hand — move resolved/old rows to its "
                "archive table/shard (table-row / mixed-format auto-rotation "
                "is deferred to TD-655)"
            )
        elif gf.contract.rotatable and gf.contract.archive_target:
            eff = effective_entry_pattern(gf.contract, None)
            if rotation_can_help(gf.path, gf.contract, eff, now):
                ep = (
                    f" --entry-pattern '{gf.contract.entry_pattern}'"
                    if gf.contract.entry_pattern
                    else ""
                )
                remedy = (
                    f"{script_invocation()} --apply {gf.path} "
                    f"--oversight-root {oversight_root}{ep}"
                )
            else:
                remedy = (
                    f"trim {gf.rel} by hand — rotation is exhausted (no "
                    "eligible entry to archive, or preamble alone exceeds cap)"
                )
        else:
            remedy = (
                f"trim {gf.rel} by hand — class '{gf.contract.klass}' is not "
                "rotatable (rotation_trigger: none)"
            )
        breaches.append(
            "\n".join(
                [
                    "  ┌─ SYSTEM FAILURE: oversight file over cap",
                    f"  │  file:   {gf.rel}",
                    f"  │  size:   {lines} lines / {kb:.1f} KB",
                    f"  │  cap:    {gf.contract.cap_lines} lines / "
                    f"{gf.contract.cap_kb} KB ({gf.contract.klass}, "
                    f"via {gf.source})",
                    f"  │  remedy: {remedy}",
                    "  └─",
                ]
            )
        )

    if breaches:
        print(
            "aim-tracking-rotate --check: FAIL — "
            f"{len(breaches)} governed file(s) over cap.\n",
            file=sys.stderr,
        )
        print("\n\n".join(breaches), file=sys.stderr)
        print(
            "\nCloseout is BLOCKED until every governed file is at or under cap.",
            file=sys.stderr,
        )
        return 1

    print(
        f"aim-tracking-rotate --check: PASS — {len(governed)} governed file(s) "
        "within cap."
    )
    return 0


# ---------------------------------------------------------------------------
# --apply : entry-boundary rotation (BP-167 Part C)
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    header: str
    block: str  # full text of the entry incl. its header line + trailing lines


@dataclass
class ParsedFile:
    front_matter: str
    preamble: str
    entries: list[Entry] = field(default_factory=list)


def parse_entries(text: str, entry_pattern: str) -> ParsedFile:
    """Split a file into front-matter, preamble, and an ordered entry list.

    Entry boundaries inside fenced code blocks (```` ``` ```` / ``~~~``) are
    ignored so a heading quoted in an entry body never starts a phantom entry
    or splits a real one mid-body.
    """
    front_matter, body = split_front_matter(text)
    body_no_pointer = strip_pointer(body)
    lines = body_no_pointer.splitlines(keepends=True)
    entry_re = re.compile(entry_pattern)
    fence_re = re.compile(r"^\s*(`{3,}|~{3,})")

    boundaries: list[int] = []
    in_fence = False
    fence_char = ""
    for i, ln in enumerate(lines):
        fm = fence_re.match(ln)
        if fm:
            char = fm.group(1)[0]  # '`' or '~'
            if not in_fence:
                in_fence = True
                fence_char = char
            elif char == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if not in_fence and entry_re.match(ln):
            boundaries.append(i)

    if not boundaries:
        return ParsedFile(front_matter, body_no_pointer, [])

    preamble = "".join(lines[: boundaries[0]])
    entries: list[Entry] = []
    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(lines)
        block = "".join(lines[start:end])
        entries.append(Entry(header=lines[start].rstrip("\n"), block=block))
    return ParsedFile(front_matter, preamble, entries)


def strip_pointer(body: str) -> str:
    """Remove any existing rotate live-pointer line (idempotency)."""
    kept = [ln for ln in body.splitlines(keepends=True) if POINTER_MARKER not in ln]
    return "".join(kept)


def entry_key(entry: Entry) -> str:
    """A stable dedup/conservation key for an entry.

    Prefers an id token (DEC-/BUG-/BLK-/RISK-/TD-…); else the first table cell
    for a pipe-row; else the stripped header text.
    """
    m = ENTRY_ID_RE.search(entry.header)
    if m:
        return m.group(1)
    h = entry.header.strip()
    if h.startswith("|"):
        cells = [c.strip() for c in h.strip("|").split("|")]
        cells = [c for c in cells if c]
        if cells:
            return cells[0]
    return h.lstrip("#").strip()


def is_resolved(entry: Entry) -> bool:
    """True only when the entry carries an explicit resolved-class status.

    Default-OPEN: anything without a clear resolved marker is treated as active
    and is never archived (H-5 — a still-open blocker must not be evicted).
    """
    return bool(RESOLVED_STATUS_RE.search(entry.block))


def select_kept_moved(
    parsed: ParsedFile,
    contract: Contract,
    pointer_line: str,
    keep_override: int | None,
) -> tuple[list[Entry], list[Entry]]:
    """Partition entries into (kept-live, moved-to-archive).

    - register: rotate by RESOLVED status. Archive the oldest RESOLVED entries
      until under cap; OPEN/active entries are never moved. If only OPEN entries
      remain and it is still over cap, that is the exhausted case (caller emits
      a hand-trim remedy).
    - append-only-log / live-index: rotate by recency — keep as many NEWEST
      entries as fit under both caps; the oldest remainder rotate out.

    Entries are newest-first (index 0 newest, last index oldest).
    """
    entries = parsed.entries
    n = len(entries)
    fixed = parsed.front_matter + parsed.preamble + pointer_line

    if contract.klass == "register":
        moved_idx: set[int] = set()

        def kept_size(midx: set[int]) -> tuple[int, int]:
            live = fixed + "".join(
                e.block for j, e in enumerate(entries) if j not in midx
            )
            return measure(live)

        lines, nbytes = kept_size(moved_idx)
        # Oldest first: newest-first list => walk highest (oldest) index down.
        for i in range(n - 1, -1, -1):
            if not over_cap(lines, nbytes, contract):
                break
            if is_resolved(entries[i]):
                moved_idx.add(i)
                lines, nbytes = kept_size(moved_idx)
        kept = [e for j, e in enumerate(entries) if j not in moved_idx]
        moved = [e for j, e in enumerate(entries) if j in moved_idx]
        return kept, moved

    # Recency path (append-only-log / live-index).
    if keep_override is not None:
        keep = max(0, min(keep_override, n))
    else:
        keep = 0
        for k in range(n, -1, -1):
            candidate = fixed + "".join(e.block for e in entries[:k])
            if not over_cap(*measure(candidate), contract):
                keep = k
                break
    return entries[:keep], entries[keep:]


def render_period(archive_target: str, now: datetime) -> str:
    out = archive_target
    out = out.replace("{YYYY-MM}", now.strftime("%Y-%m"))
    out = out.replace("{YYYY-Q}", f"{now.year}-Q{(now.month - 1) // 3 + 1}")
    out = out.replace("{YYYY}", now.strftime("%Y"))
    return out


def _pointer_line(contract: Contract, shard_rel: str) -> str:
    return (
        f"> Older entries archived → `{shard_rel}`"
        + (f" (manifest: `{contract.index_file}`)" if contract.index_file else "")
        + f". {POINTER_MARKER}\n"
    )


def _render_live(
    front_matter: str, preamble: str, pointer_line: str, kept: list[Entry]
) -> str:
    pre = preamble
    if pre and not pre.endswith("\n"):
        pre += "\n"
    return front_matter + pre + pointer_line + "".join(e.block for e in kept)


class ShardCollisionError(Exception):
    """A moved entry shares an id with an existing shard entry of DIFFERENT body.

    This is NOT an idempotent replay (which would be id AND body identical) — it
    is a real id clash whose content would be lost if the move were silently
    skipped. Raised so the caller aborts before the live file is rewritten,
    leaving both shard and live untouched.
    """

    def __init__(self, shard: Path, ids: list[str]) -> None:
        self.shard = shard
        self.ids = ids
        super().__init__(
            f"{', '.join(ids)} already archived in {shard.name} with different body"
        )


def append_to_shard(
    shard: Path, moved: list[Entry], source_rel: str, entry_pattern: str
) -> int:
    """Append moved entries to the shard idempotently. Returns rows appended.

    Re-running --apply after an interruption must not double-append: an entry
    whose id AND body already match an archived entry is a safe replay and is
    skipped (mirrors the manifest dedup). But an entry whose id matches an
    existing shard entry with a DIFFERENT body is a collision, not a replay —
    silently skipping it would drop the live entry's content (the post-write
    id-count check cannot catch this: the id stays conserved while its body is
    lost). Such collisions raise ShardCollisionError so the caller aborts before
    the live file is rewritten. Writes atomically.
    """
    shard.parent.mkdir(parents=True, exist_ok=True)
    moved_new = moved
    if shard.is_file():
        existing_text = shard.read_text(encoding="utf-8")
        existing_bodies: dict[str, set[str]] = {}
        for e in parse_entries(existing_text, entry_pattern).entries:
            existing_bodies.setdefault(entry_key(e), set()).add(e.block.strip())
        moved_new = []
        collisions: list[str] = []
        for e in moved:
            key = entry_key(e)
            bodies = existing_bodies.get(key)
            if bodies is None:
                moved_new.append(e)
            elif e.block.strip() in bodies:
                continue  # idempotent replay — same id AND body already archived
            else:
                collisions.append(key)  # same id, different body — never drop
        if collisions:
            raise ShardCollisionError(shard, collisions)
        if not moved_new:
            return 0
        sep = "" if existing_text.endswith("\n") else "\n"
        atomic_write(shard, existing_text + sep + "".join(e.block for e in moved_new))
        return len(moved_new)

    header = (
        f"# Archive — rotated from `{source_rel}`\n\n"
        "Period-labelled archive shard. Entries are appended in rotation order "
        "and never re-sorted: order is monotonic *within* a shard, but across "
        "shards/rotations it is not guaranteed (BP-167 Part C).\n\n"
    )
    atomic_write(shard, header + "".join(e.block for e in moved_new))
    return len(moved_new)


def update_manifest(manifest: Path, moved: list[Entry], shard_rel: str) -> int:
    """Append/refresh manifest rows for each moved entry. Returns rows written."""
    manifest.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Decision Log — Manifest\n\n"
        "Single maintained index of **archived** decisions (BP-167 Part C): one "
        "row per archived entry id → title → location → status. O(1) by-id "
        "lookup across the archived shards (live entries remain in "
        "`decision-log.md`).\n\n"
        "| ID | Title | Location | Status |\n"
        "|---|---|---|---|\n"
    )
    text = manifest.read_text(encoding="utf-8") if manifest.is_file() else header
    if "| ID | Title | Location | Status |" not in text:
        text = header + text
    existing_ids = set(re.findall(r"^\|\s*(DEC-\S+)\s*\|", text, re.MULTILINE))

    rows: list[str] = []
    for e in moved:
        m = DEC_ID_RE.search(e.header)
        entry_id = m.group(1) if m else e.header.lstrip("# ").split(" ")[0].strip()
        if entry_id in existing_ids:
            continue
        existing_ids.add(entry_id)
        title = e.header.lstrip("# ").strip()
        if m:
            title = title.replace(entry_id, "").lstrip(" —-").strip()
        title = title.replace("|", "\\|") or "(untitled)"
        rows.append(f"| {entry_id} | {title} | {shard_rel} | archived |")

    if rows:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n".join(rows) + "\n"
    atomic_write(manifest, text)
    return len(rows)


def update_banner(parsed: ParsedFile, remaining: int) -> tuple[str, bool]:
    """Set the register reconciliation banner count to ``remaining``.

    Rewrites ``N active [as of PM #X]`` to ``M active`` — the stale ``as of
    PM #X`` qualifier is dropped rather than left pointing at an old session.

    Returns ``(new_preamble, updated)``.
    """
    pattern = re.compile(r"\d+\s+active(?:\s+as of[^\n*]*)?")
    if pattern.search(parsed.preamble):
        return pattern.sub(f"{remaining} active", parsed.preamble, count=1), True
    return parsed.preamble, False


def run_apply(
    file_path: Path,
    oversight_root: Path,
    entry_pattern: str | None,
    keep_override: int | None,
    now: datetime,
) -> int:
    if not file_path.is_file():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        return 1

    rel = (
        file_path.resolve().relative_to(oversight_root.resolve()).as_posix()
        if file_path.resolve().is_relative_to(oversight_root.resolve())
        else file_path.name
    )

    # Ownership guard: generated INDEX files belong to aim-tracking-freshness;
    # never rotate them here even if a seed made them look rotatable.
    if rel in FRESHNESS_OWNED:
        print(
            f"ERROR: {rel} is owned by aim-tracking-freshness (generated INDEX) "
            "— not rotatable by aim-tracking-rotate.",
            file=sys.stderr,
        )
        return 1

    # Manual-rotation guard (DEC-PM339-D7 Option A): refuse the table-under-
    # severity / mixed-format registers BEFORE any read or write — safe field-
    # aware auto-rotation is deferred to TD-655. Non-destructive: nothing is
    # mutated, exit non-zero.
    if rel in MANUAL_ROTATION_FILES:
        print(
            f"REFUSED: {rel} is a table-row / mixed-format register (table rows "
            "under severity/status sections, or a multi-table live-index). Safe "
            "field-aware auto-rotation is deferred to TD-655, so --apply makes "
            "NO changes here.\n"
            "  Rotate manually: move the resolved/oldest rows into the archive "
            "table/shard by hand. `--check` still enforces the cap.",
            file=sys.stderr,
        )
        return 1

    resolved = resolve_contract(file_path, rel)
    if resolved is None:
        print(
            f"ERROR: {rel} is not a governed file (no contract).",
            file=sys.stderr,
        )
        return 1
    contract, _ = resolved

    if not contract.rotatable or not contract.archive_target:
        print(
            f"ERROR: {rel} is class '{contract.klass}' "
            "(rotation_trigger: none) — not a rotatable file. "
            "Heartbeat/thin files are trimmed in place, not rotated.",
            file=sys.stderr,
        )
        return 1

    eff_pattern = effective_entry_pattern(contract, entry_pattern)
    text = file_path.read_text(encoding="utf-8")
    before_lines, before_bytes = measure(text)
    parsed = parse_entries(text, eff_pattern)
    if not parsed.entries:
        print(
            f"ERROR: no entries detected in {rel} with pattern "
            f"{eff_pattern!r}; nothing to rotate.",
            file=sys.stderr,
        )
        return 1

    pre_ids = Counter(entry_key(e) for e in parsed.entries)

    shard_rel = render_period(contract.archive_target, now)
    pointer_line = _pointer_line(contract, shard_rel)

    kept, moved = select_kept_moved(parsed, contract, pointer_line, keep_override)

    if not moved:
        # Nothing eligible: either already within cap, or exhausted.
        if over_cap(before_lines, before_bytes, contract):
            print(
                f"ERROR: {rel} is over cap but no entry is eligible to rotate "
                "(register holds only OPEN entries, or the sole entry exceeds "
                "the cap). Rotation exhausted — trim by hand.",
                file=sys.stderr,
            )
            return 1
        print(
            f"{rel}: already within cap — no entries rotated "
            f"({before_lines} lines / {before_bytes / 1024:.1f} KB).",
        )
        return 0

    # 1. Archive shard (idempotent + atomic). A same-id/different-body clash is
    #    refused here, BEFORE the live rewrite, so nothing is dropped.
    shard = oversight_root / shard_rel
    try:
        appended = append_to_shard(shard, moved, rel, eff_pattern)
    except ShardCollisionError as exc:
        print(
            f"ERROR: shard collision in {shard_rel} — an entry being archived "
            "shares an id with an already-archived entry but has different "
            "content. Refusing to silently drop it; the live file was NOT "
            "modified. Resolve the id clash by hand:",
            file=sys.stderr,
        )
        for eid in exc.ids[:10]:
            print(f"    {eid}", file=sys.stderr)
        return 1

    # 2. Reconciliation: manifest (append-only-log) OR banner (register).
    manifest_rows = 0
    banner_updated = False
    new_preamble = parsed.preamble
    if contract.index_file:
        manifest_rows = update_manifest(
            oversight_root / contract.index_file, moved, shard_rel
        )
    if contract.klass == "register":
        # Banner counts OPEN entries still live — kept may include some newest
        # RESOLVED entries that fit under cap, which are NOT "active".
        open_kept = sum(1 for e in kept if not is_resolved(e))
        new_preamble, banner_updated = update_banner(parsed, open_kept)

    # 3. Rewrite live file atomically = front-matter + preamble + pointer + kept.
    new_text = _render_live(parsed.front_matter, new_preamble, pointer_line, kept)
    atomic_write(file_path, new_text)
    after_lines, after_bytes = measure(new_text)

    # 4. REAL post-write check: re-read live + shard and assert per-id count
    #    conservation for every pre-write id (no entry lost, none duplicated /
    #    double-appended). Replaces the old tautological slice/startswith asserts.
    live_ids = [
        entry_key(e)
        for e in parse_entries(
            file_path.read_text(encoding="utf-8"), eff_pattern
        ).entries
    ]
    shard_ids = [
        entry_key(e)
        for e in parse_entries(shard.read_text(encoding="utf-8"), eff_pattern).entries
    ]
    after_counter = Counter(live_ids) + Counter(shard_ids)
    violations = [
        (eid, cnt, after_counter.get(eid, 0))
        for eid, cnt in pre_ids.items()
        if after_counter.get(eid, 0) != cnt
    ]
    if violations:
        print(
            "ERROR: id-conservation check FAILED after rotation "
            f"({rel}) — an entry was lost or duplicated:",
            file=sys.stderr,
        )
        for eid, was, now_count in violations[:10]:
            print(
                f"    {eid}: was {was} pre-write, now {now_count} live+shard",
                file=sys.stderr,
            )
        return 1

    print(
        "\n".join(
            [
                f"aim-tracking-rotate --apply: {rel}",
                f"  entries:  {len(parsed.entries)} total → {len(kept)} kept / "
                f"{len(moved)} archived ({appended} appended to shard)",
                f"  shard:    {shard_rel}",
                (
                    f"  manifest: {manifest_rows} row(s) → {contract.index_file}"
                    if contract.index_file
                    else f"  banner:   {'updated' if banner_updated else 'none present'}"
                ),
                "  pointer:  written",
                f"  live now: {after_lines} lines / {after_bytes / 1024:.1f} KB "
                f"(was {before_lines} / {before_bytes / 1024:.1f} KB; "
                f"cap {contract.cap_lines} / {contract.cap_kb})",
            ]
        )
    )

    if not kept:
        print(
            "  WARNING: every entry was archived (including the newest) — the "
            "live file now holds no entries; keep ≥1 newest by hand if needed.",
            file=sys.stderr,
        )

    if over_cap(after_lines, after_bytes, contract):
        # H-4: do NOT exit 0 — the gate must not loop back to --apply forever.
        print(
            "ERROR: live file still over cap after rotating every eligible "
            "entry (preamble / open-set alone exceeds the cap). Rotation "
            "exhausted — trim by hand.",
            file=sys.stderr,
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# Oversight-root resolution + entry point
# ---------------------------------------------------------------------------


def resolve_oversight_root(args: argparse.Namespace) -> Path:
    """Resolve oversight root: --oversight-root > env var > ./oversight."""
    if args.oversight_root:
        p = Path(args.oversight_root).expanduser().resolve()
    elif "AI_MEMORY_OVERSIGHT_ROOT" in os.environ:
        p = Path(os.environ["AI_MEMORY_OVERSIGHT_ROOT"]).expanduser().resolve()
    else:
        p = (Path.cwd() / "oversight").resolve()
    if not p.is_dir():
        print(
            f"ERROR: oversight root not found at {p}\n"
            "       Pass --oversight-root <path> or set AI_MEMORY_OVERSIGHT_ROOT.",
            file=sys.stderr,
        )
        sys.exit(1)
    return p


def resolve_now(period: str | None) -> datetime:
    """Deterministic period override for tests; else wall-clock."""
    if period:
        # Accept YYYY-MM or YYYY-MM-DD.
        for fmt in ("%Y-%m-%d", "%Y-%m"):
            try:
                return datetime.strptime(period, fmt)
            except ValueError:
                continue
        print(
            f"ERROR: --period must be YYYY-MM or YYYY-MM-DD (got {period!r}).",
            file=sys.stderr,
        )
        sys.exit(1)
    return datetime.now()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Enforce oversight-file caps at session-close (--check) and rotate "
            "an over-cap file's oldest entries into a dated archive shard "
            "(--apply)."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Gate: fail (exit non-zero) if any governed file is over cap.",
    )
    mode.add_argument(
        "--apply",
        metavar="FILE",
        help="Rotate the oldest entries of FILE into a dated archive shard.",
    )
    parser.add_argument(
        "--oversight-root",
        help="Path to the oversight/ root (default: env or ./oversight).",
    )
    parser.add_argument(
        "--entry-pattern",
        default=None,
        help=(
            "Regex matching an entry-boundary line. Default resolution: this "
            "flag > the file's contract entry_pattern > the built-in id-prefixed "
            f"H3 default ({DEFAULT_ENTRY_PATTERN!r}). Use '^\\| ' for table-row "
            "registers."
        ),
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=None,
        help="Force the number of NEWEST entries to keep live (overrides cap fit).",
    )
    parser.add_argument(
        "--period",
        default=None,
        help="Archive period override (YYYY-MM or YYYY-MM-DD); default = today.",
    )
    args = parser.parse_args(argv)

    oversight_root = resolve_oversight_root(args)

    if args.check:
        return run_check(oversight_root)
    return run_apply(
        Path(args.apply).expanduser(),
        oversight_root,
        args.entry_pattern,
        args.keep,
        resolve_now(args.period),
    )


if __name__ == "__main__":
    raise SystemExit(main())
