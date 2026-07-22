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
generated bugs/INDEX.md, tech-debt/INDEX.md, or deferrals/INDEX.md (PLAN-035
P2.6) — those and their CLOSED.md shards are owned by aim-tracking-freshness,
which self-archives closed-class records (Resolved/Dropped for deferrals)
into each directory's own CLOSED.md, the register-class event-archive outcome,
implemented on the generated-index path rather than this module's.

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

# Shared governance core (single canonical source, no copy-paste). The install
# copies _ai-memory/pov/ verbatim, so resolving from __file__ is install-robust:
# this script lives at pov/skills/aim-tracking-rotate/scripts/, so parents[3] is
# pov/ and pov/lib/governance/ holds the shared Contract + conservation modules.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib" / "governance"))
from contract import Contract


def _load_conservation():
    """Return the shared governance conservation module (cached after first load)."""
    cached = getattr(_load_conservation, "_cache", None)
    if cached is None:
        import conservation  # pov/lib/governance is on sys.path (above)

        _load_conservation._cache = conservation
    return _load_conservation._cache


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
# Contract is the shared frozen dataclass from pov/lib/governance/contract.py.


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
    "tracking/task-tracker.md": Contract(60, 4.5, "register", False),
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
    "tracking/technical-debt.md": Contract(
        150,
        15,
        "register",
        True,
        archive_target="tracking/technical-debt-archive-{YYYY}.md",
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
FRESHNESS_OWNED: frozenset[str] = frozenset(
    {"bugs/INDEX.md", "tech-debt/INDEX.md", "deferrals/INDEX.md"}
)

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
#   - technical-debt.md : "### TD-NNN:" detail H3 entries + "### <Category>"
#                        summary tables in "Debt by Category" — H3-boundary
#                        rotation would orphan table rows referencing those TDs.
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
        "tracking/technical-debt.md",
        "SESSION_WORK_INDEX.md",
        "session-index/INDEX.md",
    }
)

# Latest SESSION_HANDOFF_*.md (detail-record, whole-file, 60/8). Discovered by
# glob rather than fixed path; --apply on a handoff is not supported here
# (handoff archival is owned by close step-03).
HANDOFF_CONTRACT = Contract(60, 8, "detail-record", False)
HANDOFF_GLOB = "session-logs/SESSION_HANDOFF_*.md"

# auto-memory-index class: Claude Code auto-memory MEMORY.md.
# Cap = whichever-comes-first (line OR byte). Soft target ~ 180 lines so the
# agent has a visible runway before hitting the 200-line load window.
AUTO_MEMORY_CONTRACT = Contract(200, 25.0, "auto-memory-index", False)
_MEMORY_LOG_SHAPE_MAX_LINES = 2  # non-blank lines per entry in an index
_MEMORY_LOG_SHAPE_MAX_CHARS = 200  # total chars per entry in an index

# Default entry boundary: an id-prefixed markdown H3 heading (DEC-/BUG-/BLK-/
# RISK-/TD-…). Requiring an id prefix (2-4 uppercase letters + '-') avoids
# matching quoted/section headings such as '### Critical' or '### Notes' that
# would otherwise split a real entry. Override with --entry-pattern (or the
# per-file contract entry_pattern) for table-row formats (e.g. '^\\| ').
DEFAULT_ENTRY_PATTERN = r"^### [A-Z]{2,4}-"

# Fallback entry boundary for the session-block append-only-log format (#291):
# a governed append-only-log may use a numbered session heading ('## S12 ...')
# instead of id-prefixed H3 entries. When the default id-H3 pattern finds zero
# entries in an append-only-log, retry with this pattern before reporting
# "no entries detected" (see parse_entries_with_fallback).
SESSION_BLOCK_ENTRY_PATTERN = r"^## S\d+ "

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
    parsed, _ = parse_entries_with_fallback(
        path.read_text(encoding="utf-8"), contract, entry_pattern
    )
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

    # auto-memory-index: WARN only — never blocks the gate; surface even when
    # oversight files are over cap so both issues land in one check run.
    memory_md = resolve_memory_md()
    memory_warns: list[str] = []
    if memory_md:
        memory_warns = list(_check_memory_md(memory_md))
    for warn in memory_warns:
        print(f"  WARN: {warn}", file=sys.stderr)

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


def parse_entries_with_fallback(
    text: str, contract: Contract, entry_pattern: str
) -> tuple[ParsedFile, str]:
    """Parse entries; on zero matches with the default id-H3 pattern on an
    append-only-log, retry with the session-block boundary (#291).

    ``entry_pattern`` here is the already-resolved effective pattern
    (explicit CLI flag > contract > default) — the fallback only triggers
    when that resolution landed on the built-in default, so an explicit
    override (CLI or contract ``entry_pattern``) is never second-guessed.

    Returns ``(parsed, pattern_used)``.
    """
    parsed = parse_entries(text, entry_pattern)
    if (
        not parsed.entries
        and entry_pattern == DEFAULT_ENTRY_PATTERN
        and contract.klass == "append-only-log"
    ):
        fallback_parsed = parse_entries(text, SESSION_BLOCK_ENTRY_PATTERN)
        if fallback_parsed.entries:
            return fallback_parsed, SESSION_BLOCK_ENTRY_PATTERN
    return parsed, entry_pattern


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
    # pointer_line is included in fixed so each candidate/live size probe matches
    # what _render_live produces: front_matter + preamble + pointer + entries.
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


def _normalize_eol(text: str) -> str:
    """Normalize line endings only (CRLF/CR -> LF) for body-equality compares.

    EOL-ONLY: maps ``\\r\\n`` then bare ``\\r`` to ``\\n`` so a true replay that
    differs from its archived twin solely in line endings compares equal across
    mixed-EOL hosts. It touches NO other whitespace — two bodies differing in any
    non-EOL way still compare unequal, so a real id clash still raises a collision.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _compute_shard_append(
    shard: Path,
    moved: list[Entry],
    source_rel: str,
    entry_pattern: str,
) -> tuple[str, int]:
    """Compute the new shard text and count WITHOUT writing to disk.

    Idempotent: same-id/same-body entries in the existing shard are skipped.
    Raises ShardCollisionError on same-id/different-body.
    Returns ``(new_shard_text, appended_count)``.
    """
    moved_new = moved
    if shard.is_file():
        existing_text = shard.read_text(encoding="utf-8")
        existing_bodies: dict[str, set[str]] = {}
        for e in parse_entries(existing_text, entry_pattern).entries:
            existing_bodies.setdefault(entry_key(e), set()).add(
                _normalize_eol(e.block).strip()
            )
        moved_new = []
        collisions: list[str] = []
        for e in moved:
            key = entry_key(e)
            bodies = existing_bodies.get(key)
            if bodies is None:
                moved_new.append(e)
            elif _normalize_eol(e.block).strip() in bodies:
                continue  # idempotent replay — same id AND body already archived
            else:
                collisions.append(key)  # same id, different body — never drop
        if collisions:
            # Order-preserving dedup: one id can collide multiple times in a batch;
            # exc.ids / the printed [:10] / the message must list it once.
            raise ShardCollisionError(shard, list(dict.fromkeys(collisions)))
        if not moved_new:
            return existing_text, 0
        sep = "" if existing_text.endswith("\n") else "\n"
        return existing_text + sep + "".join(e.block for e in moved_new), len(moved_new)

    header = (
        f"# Archive — rotated from `{source_rel}`\n\n"
        "Period-labelled archive shard. Entries are appended in rotation order "
        "and never re-sorted: order is monotonic *within* a shard, but across "
        "shards/rotations it is not guaranteed (BP-167 Part C).\n\n"
    )
    return header + "".join(e.block for e in moved_new), len(moved_new)


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
    new_text, appended = _compute_shard_append(shard, moved, source_rel, entry_pattern)
    if appended > 0 or not shard.is_file():
        shard.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(shard, new_text)
    return appended


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
    # Fence an unfenced entry-format example BEFORE parsing to prevent scaffold
    # strip: an unfenced ### DEC-[ID] example would be mis-parsed as Entry 0.
    text, _apply_fenced = _fence_for_apply(text, rel)
    before_lines, before_bytes = measure(text)
    parsed, eff_pattern = parse_entries_with_fallback(text, contract, eff_pattern)
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

    # 0. Backup before any mutation.
    _backup_file(file_path, now)

    # 1. Compute shard text in memory (prove-before-write: shard not written yet).
    shard = oversight_root / shard_rel
    try:
        new_shard_text, appended = _compute_shard_append(shard, moved, rel, eff_pattern)
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

    # 3. Compute new live text and prove conservation using in-memory shard text
    #    (shard not yet written — abort leaves live file and shard both intact).
    new_text = _render_live(parsed.front_matter, new_preamble, pointer_line, kept)
    after_lines, after_bytes = measure(new_text)

    computed_live_ids = Counter(
        entry_key(e) for e in parse_entries(new_text, eff_pattern).entries
    )
    shard_parse_ids = [
        entry_key(e) for e in parse_entries(new_shard_text, eff_pattern).entries
    ]
    after_counter = computed_live_ids + Counter(shard_parse_ids)
    violations = [
        (eid, cnt, after_counter.get(eid, 0))
        for eid, cnt in pre_ids.items()
        if after_counter.get(eid, 0) != cnt
    ]
    if violations:
        print(
            "ERROR: id-conservation check FAILED — aborting before live rewrite "
            f"({rel}) — an entry was lost or duplicated:",
            file=sys.stderr,
        )
        for eid, was, now_count in violations[:10]:
            print(
                f"    {eid}: was {was} pre-write, now {now_count} live+shard",
                file=sys.stderr,
            )
        print(
            "  Live file and shard are both unchanged.",
            file=sys.stderr,
        )
        return 1

    # 4. Conservation proved — commit shard then live atomically.
    if appended > 0:
        shard.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(shard, new_shard_text)
    atomic_write(file_path, new_text)

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
                    else "  banner:   "
                    + ("updated" if banner_updated else "none present")
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
# --fix : conformance-first cap-fix with conservation proof
# ---------------------------------------------------------------------------


class SiblingCollisionError(Exception):
    """A MEMORY.md entry's target sibling slug already holds a different body.

    Raised when the sibling file exists but does not contain this exact block.
    This mirrors ShardCollisionError: same identity, conflicting content —
    BP-038 "do not silently merge." The caller must abort without mutation.
    Normal cases: block absent (sibling does not exist) → create; block already
    present (identical) → skip (idempotent); sibling exists + different body → raise.
    """

    def __init__(self, sibling: Path, preview: str) -> None:
        self.sibling = sibling
        super().__init__(
            f"Sibling {sibling.name} already exists with different content "
            f"for entry: {preview!r}"
        )


def _backup_file(path: Path, now: datetime) -> None:
    """Write a timestamped .bak copy of path before any mutation."""
    bak = path.with_name(f"{path.name}.{now.strftime('%Y%m%d%H%M%S')}.bak")
    bak.write_bytes(path.read_bytes())


def _resolve_template_dir() -> Path:
    """Resolve the oversight template directory.

    Prefers AI_MEMORY_INSTALL_DIR env var when its templates/ subtree exists;
    otherwise derives from this script's location (six directory levels up
    lands at the install root).  The existence check lets test environments
    that set AI_MEMORY_INSTALL_DIR to a dummy path fall back safely.
    """
    install_dir = os.environ.get("AI_MEMORY_INSTALL_DIR")
    if install_dir:
        p = Path(install_dir).expanduser() / "templates" / "oversight"
        if p.is_dir():
            return p
    # Fallback: script-relative (also covers test envs with a dummy install dir).
    # scripts/ -> aim-tracking-rotate/ -> skills/ -> pov/ -> _ai-memory/ -> root/
    return Path(__file__).resolve().parents[5] / "templates" / "oversight"


def _read_template_fm(rel: str) -> str:
    """Read the front-matter block from the template for rel, or empty string."""
    tpl = _resolve_template_dir() / rel
    if not tpl.is_file():
        return ""
    fm, _ = split_front_matter(tpl.read_text(encoding="utf-8"))
    return fm


def _contract_for_text(text: str, rel: str) -> Contract | None:
    """Resolve contract from in-memory text without reading the file from disk."""
    fm, _ = split_front_matter(text)
    c = parse_contract_front_matter(fm)
    if c is not None:
        return c
    return FALLBACK_REGISTRY.get(rel)


def _fence_entry_format_section(text: str, tpl_body: str) -> tuple[str, bool]:
    """Replace an unfenced ## Entry Format example with the template's fenced one."""
    ef_pat = re.compile(
        r"^(## Entry Format\n)(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
    )
    ef_m = ef_pat.search(text)
    if not ef_m:
        return text, False
    ef_body = ef_m.group(2)
    # Already fenced → nothing to do.
    if re.search(r"^```", ef_body, re.MULTILINE):
        return text, False
    # Only repair if there's an unfenced ### DEC-style example.
    if not re.search(r"^### [A-Z]{2,4}-", ef_body, re.MULTILINE):
        return text, False
    tpl_ef_m = ef_pat.search(tpl_body)
    if not tpl_ef_m:
        return text, False
    new_text = text[: ef_m.start()] + tpl_ef_m.group(0) + text[ef_m.end() :]
    return new_text, True


def _repair_sections(text: str, tpl_body: str) -> tuple[str, list[str]]:
    """Ensure all template ## sections present; fence entry-format example."""
    repairs: list[str] = []

    tpl_headers = re.findall(r"^## .+$", tpl_body, re.MULTILINE)
    for hdr in tpl_headers:
        if re.search(re.escape(hdr), text, re.MULTILINE):
            continue
        sec_pat = re.compile(
            re.escape(hdr) + r"\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
        )
        m = sec_pat.search(tpl_body)
        if m:
            if not text.endswith("\n"):
                text += "\n"
            text += "\n" + m.group(0)
            repairs.append(f"added missing section '{hdr}'")

    text, fenced = _fence_entry_format_section(text, tpl_body)
    if fenced:
        repairs.append("fenced entry-format example in '## Entry Format'")

    return text, repairs


def _ensure_conformance(
    file_path: Path,
    rel: str,
    text: str,
) -> tuple[str, str]:
    """Ensure D2 front-matter, required ## sections, and fenced entry-format example.

    Returns ``(new_text, message_or_empty)``.
    """
    repairs: list[str] = []

    # Step 1: Add D2 front-matter if absent.
    fm, _ = split_front_matter(text)
    if not fm:
        tpl_fm = _read_template_fm(rel)
        if tpl_fm:
            text = tpl_fm + text
            repairs.append("added D2 front-matter")

    # Step 2: For append-only-log class, ensure required sections + fenced example.
    # Resolve from in-memory text (front-matter may have just been added above).
    contract = _contract_for_text(text, rel)
    if contract is not None and contract.klass == "append-only-log":
        tpl_path = _resolve_template_dir() / rel
        if tpl_path.is_file():
            _, tpl_body = split_front_matter(tpl_path.read_text(encoding="utf-8"))
            text, sec_msgs = _repair_sections(text, tpl_body)
            repairs.extend(sec_msgs)

    return text, "; ".join(repairs) if repairs else ""


def _fence_for_apply(text: str, rel: str) -> tuple[str, bool]:
    """Fence an unfenced entry-format example before parsing in run_apply.

    Only applied to append-only-log class files with a matching template.
    The fence replaces the unfenced example with the template's fenced version
    so the entry-boundary pattern ignores it during parsing.
    Returns ``(possibly_modified_text, was_fenced)``.
    """
    contract = _contract_for_text(text, rel)
    if contract is None or contract.klass != "append-only-log":
        return text, False
    tpl_path = _resolve_template_dir() / rel
    if not tpl_path.is_file():
        return text, False
    _, tpl_body = split_front_matter(tpl_path.read_text(encoding="utf-8"))
    return _fence_entry_format_section(text, tpl_body)


def _archive_whole_and_rewrite_lean(
    file_path: Path,
    rel: str,
    oversight_root: Path,
    now: datetime,
) -> tuple[Path, str]:
    """Archive the whole file verbatim to a timestamped shard.

    Rewrites the live file as a minimal index + pointer. Returns
    ``(shard_path, shard_rel)``.
    """
    stem = Path(rel).stem
    parent_rel = str(Path(rel).parent.as_posix())
    shard_rel = (
        f"{parent_rel}/archive/{stem}-ARCHIVE-{now.strftime('%Y-%m-%d_%H%M%S')}.md"
    )
    shard = oversight_root / shard_rel

    text = file_path.read_text(encoding="utf-8")
    atomic_write(shard, text)

    # Lean live: template front-matter + extracted title + pointer
    tpl_fm = _read_template_fm(rel)
    title_match = re.search(r"^#+ (.+)$", text, re.MULTILINE)
    title = (
        title_match.group(1).strip() if title_match else stem.replace("-", " ").title()
    )
    pointer_ln = f"\n> All prior records archived → `{shard_rel}`. {POINTER_MARKER}\n"
    atomic_write(file_path, tpl_fm + f"# {title}\n" + pointer_ln)

    return shard, shard_rel


def run_fix(
    file_path: Path,
    oversight_root: Path,
    now: datetime,
) -> int:
    """Fix one oversight file: conformance → cap-fix by class → conservation proof."""
    if not file_path.is_file():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        return 1

    rel = (
        file_path.resolve().relative_to(oversight_root.resolve()).as_posix()
        if file_path.resolve().is_relative_to(oversight_root.resolve())
        else file_path.name
    )

    if rel in FRESHNESS_OWNED:
        print(f"SKIPPED: {rel} is owned by aim-tracking-freshness.", file=sys.stderr)
        return 0

    resolved = resolve_contract(file_path, rel)
    if resolved is None:
        print(
            f"ERROR: {rel} is not a governed file (no contract).",
            file=sys.stderr,
        )
        return 1
    contract, _ = resolved

    if contract.klass == "detail-record":
        print(
            f"SKIPPED: {rel} is class 'detail-record' — rotation owned by "
            "session-close step-03.",
            file=sys.stderr,
        )
        return 0

    text = file_path.read_text(encoding="utf-8")
    lines, nbytes = measure(text)
    print(
        f"aim-tracking-rotate --fix: {rel}\n"
        f"  before: {lines} lines / {nbytes / 1024:.1f} KB "
        f"(cap {contract.cap_lines} / {contract.cap_kb})"
    )

    if not over_cap(lines, nbytes, contract):
        print("  already within cap — no action needed.")
        return 0

    # Pre-check: refuse early for append-only-log with rotation_trigger: none
    # to avoid mutating (conformance fence) before a guaranteed error in run_apply.
    if contract.klass == "append-only-log" and not contract.rotatable:
        print(
            f"  ERROR: {rel} is an append-only-log with rotation_trigger: none — "
            "cannot auto-fix. Trim by hand.",
            file=sys.stderr,
        )
        return 1

    # Conservation baseline — captured before any write; fail loudly if unreadable.
    conservation = _load_conservation()
    before_ids = conservation.build_id_manifest(
        [file_path], conservation.ENTRY_ID_RE, raise_on_error=True
    )

    _backup_file(file_path, now)

    # Step 2a: add D2 front-matter if missing.
    text, conf_msg = _ensure_conformance(file_path, rel, text)
    if conf_msg:
        atomic_write(file_path, text)
        print(f"  conformance: {conf_msg}")
        resolved = resolve_contract(file_path, rel)
        if resolved is not None:
            contract, _ = resolved

    # Step 2b: cap-fix by class.
    archive_path: Path | None = None
    if contract.klass == "append-only-log" or (
        contract.klass == "register"
        and rel not in MANUAL_ROTATION_FILES
        and contract.rotatable
    ):
        rc = run_apply(file_path, oversight_root, None, None, now)
        if rc != 0:
            return rc
        if contract.archive_target:
            archive_path = oversight_root / render_period(contract.archive_target, now)
    elif (
        rel in MANUAL_ROTATION_FILES
        or contract.klass == "live-index"
        or (contract.klass == "register" and not contract.rotatable)
    ):
        _, shard_rel = _archive_whole_and_rewrite_lean(
            file_path, rel, oversight_root, now
        )
        archive_path = oversight_root / shard_rel
        print(f"  archived whole → {shard_rel}")
    elif contract.klass == "heartbeat":
        tpl_fm = _read_template_fm(rel)
        if tpl_fm:
            _, body = split_front_matter(text)
            new_hb_text = tpl_fm + body
            atomic_write(file_path, new_hb_text)
            print("  heartbeat: refreshed front-matter from template")
            hl, hb = measure(new_hb_text)
            if over_cap(hl, hb, contract):
                print(
                    f"  ERROR: heartbeat body still over cap "
                    f"({hl}L / {hb / 1024:.1f}KB, cap "
                    f"{contract.cap_lines} / {contract.cap_kb}KB). "
                    "Trim the body by hand.",
                    file=sys.stderr,
                )
                return 1
        else:
            print(
                f"  heartbeat: no template for {rel} — trim by hand.",
                file=sys.stderr,
            )
            return 1
    else:
        print(
            f"  class '{contract.klass}': no automatic fix — trim by hand.",
            file=sys.stderr,
        )
        return 1

    # Step 2c: conservation proof.
    check_paths = [file_path]
    if archive_path and archive_path.is_file():
        check_paths.append(archive_path)
    after_ids = conservation.build_id_manifest(check_paths, conservation.ENTRY_ID_RE)
    try:
        conservation.assert_no_id_loss(before_ids, after_ids)
    except AssertionError as exc:
        print(f"ERROR: conservation FAILED: {exc}", file=sys.stderr)
        return 1

    new_text = file_path.read_text(encoding="utf-8")
    new_lines, new_bytes = measure(new_text)
    n_before = sum(before_ids.values())
    n_after = sum(after_ids.values())
    print(
        f"  after:        {new_lines} lines / {new_bytes / 1024:.1f} KB\n"
        f"  conservation: {n_before} ID tokens before → {n_after} after, 0 lost ✓"
    )
    if over_cap(new_lines, new_bytes, contract):
        print(
            "  WARNING: still over cap — run again or trim by hand.",
            file=sys.stderr,
        )
    return 0


# ---------------------------------------------------------------------------
# auto-memory-index class: MEMORY.md lossless relocation
# ---------------------------------------------------------------------------

# One-line pointer format recognised by MEMORY.md index: - [Title](file.md) — hook
_POINTER_LINE_RE = re.compile(
    r"^\s*[-*]\s+\[[^\]]+\]\([^)]+\)\s*[—–-]\s*.+$"  # noqa: RUF001
)


def _is_memory_pointer(line: str) -> bool:
    return bool(_POINTER_LINE_RE.match(line.strip()))


def _has_log_shape_violation(text: str) -> bool:
    """True if ``text`` contains at least one block that needs relocation."""
    for block in _split_into_blocks(text):  # noqa: SIM110  # pre-existing loop; unrelated to Lane C
        if _entry_needs_relocation(block):
            return True
    return False


def _entry_needs_relocation(block: str) -> bool:
    """True if a content block should be relocated to a sibling file.

    A list of pointer-format lines (``- [Title](file.md) — hook``) is the
    conformant index format and is never marked for relocation, regardless
    of how many pointer lines appear in one block.
    """
    stripped = block.strip()
    if not stripped:
        return False
    non_blank = [ln for ln in stripped.splitlines() if ln.strip()]
    # All lines are already pointers → conformant; no relocation.
    if all(_is_memory_pointer(ln) for ln in non_blank):
        return False
    return (
        len(stripped) > _MEMORY_LOG_SHAPE_MAX_CHARS
        or len(non_blank) > _MEMORY_LOG_SHAPE_MAX_LINES
    )


def _slugify(text: str) -> str:
    """Derive a lowercase filesystem-safe slug from text."""
    clean = re.sub(r"[*_`\[\]()#>~|]", " ", text)
    clean = re.sub(r"\s+", "_", clean.strip().lower())
    clean = re.sub(r"[^a-z0-9_]", "", clean)
    return clean[:40].strip("_") or "entry"


def _sibling_name_for(section_header: str, entry_text: str) -> str:
    """Derive a deterministic sibling filename from section context + entry text."""
    section = section_header.lstrip("#").strip().lower()
    first_line = next((ln.strip() for ln in entry_text.splitlines() if ln.strip()), "")
    slug = _slugify(first_line[:80])

    if "feedback" in section:
        return f"feedback_{slug}.md"
    if any(w in section for w in ("project", "active", "task", "sprint", "build")):
        return f"project_{slug}.md"
    if "next" in section or "step" in section:
        return "next_steps.md"
    section_slug = _slugify(section[:25])
    return f"{section_slug}_{slug}.md"


def _clean_pointer_label(line: str) -> str:
    """Strip a leading markdown header prefix (TD-671: ``### Topic`` → ``Topic``)
    then inline emphasis markers, so a pointer label reads ``[Topic]`` not
    ``[### Topic]``."""
    return re.sub(r"[*_`]", "", re.sub(r"^\s*#{1,6}\s+", "", line)).strip()


def _make_pointer(entry_text: str, sibling_name: str) -> str:
    """Build a one-line ``- [Title](sibling.md) — hook`` pointer."""
    lines = [ln.strip() for ln in entry_text.splitlines() if ln.strip()]
    first_line = lines[0] if lines else "Detail"
    title = _clean_pointer_label(first_line)[:60].strip()
    hook_src = lines[1] if len(lines) > 1 else first_line
    hook = _clean_pointer_label(hook_src)[:80].strip()
    return f"- [{title}]({sibling_name}) — {hook}\n"


def _parse_memory_sections(text: str) -> list[tuple[str, str]]:
    """Split MEMORY.md into ``(section_header, section_body)`` pairs.

    Content before the first ``##`` header uses ``""`` as the header key.
    """
    sections: list[tuple[str, str]] = []
    current_header = ""
    current_lines: list[str] = []

    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            sections.append((current_header, "".join(current_lines)))
            current_header = line.rstrip("\n")
            current_lines = []
        else:
            current_lines.append(line)

    sections.append((current_header, "".join(current_lines)))
    return sections


def _split_into_blocks(content: str) -> list[str]:
    """Split section content into paragraph blocks, preserving blank-line tokens."""
    result: list[str] = []
    current: list[str] = []
    for line in content.splitlines(keepends=True):
        if line.strip():
            current.append(line)
        else:
            if current:
                result.append("".join(current))
                current = []
            result.append(line)
    if current:
        result.append("".join(current))
    return result


def _block_in_file(block_norm: str, file_text: str) -> bool:
    """True iff block_norm exactly matches one of the paragraph blocks in file_text."""
    for existing in _split_into_blocks(file_text):
        if _normalize_eol(existing).strip() == block_norm:
            return True
    return False


def _fix_section(
    section_content: str,
    section_header: str,
    memory_dir: Path,
    pending_writes: dict[Path, str],
) -> tuple[str, bool]:
    """Relocate over-long entries in one section to sibling files.

    Appends to an existing sibling if the block is not already there
    (idempotent on re-run: already-present blocks are not duplicated).
    Writes are staged in ``pending_writes``; the caller commits them once
    the full pass succeeds.
    Returns ``(new_content, was_changed)``.
    """
    blocks = _split_into_blocks(section_content)
    new_blocks: list[str] = []
    changed = False

    for block in blocks:
        if not block.strip():
            new_blocks.append(block)
            continue
        if not _entry_needs_relocation(block):
            new_blocks.append(block)
            continue

        sibling_name = _sibling_name_for(section_header, block)
        sibling_path = memory_dir / sibling_name
        block_norm = _normalize_eol(block).strip()

        # Resolve current sibling content: prefer staged (not-yet-written) over disk.
        if sibling_path in pending_writes:
            current = pending_writes[sibling_path]
        elif sibling_path.is_file():
            current = sibling_path.read_text(encoding="utf-8")
        else:
            current = ""

        if current and _block_in_file(block_norm, current):
            # Already present — idempotent replay, just write the pointer.
            pass
        elif current:
            # Sibling exists but holds a different body — refuse (BP-038).
            raise SiblingCollisionError(sibling_path, block[:60])
        else:
            # New sibling.
            pending_writes[sibling_path] = block

        new_blocks.append(_make_pointer(block, sibling_name))
        changed = True

    return "".join(new_blocks), changed


def _reassemble_memory(sections: list[tuple[str, str]]) -> str:
    """Reassemble section pairs back into a MEMORY.md text."""
    parts: list[str] = []
    for header, body in sections:
        if header:
            parts.append(header + "\n")
        parts.append(body)
    return "".join(parts)


def run_fix_memory_md(memory_md: Path, now: datetime) -> int:
    """Fix MEMORY.md: relocate over-long entries to sibling files."""
    memory_dir = memory_md.parent
    conservation = _load_conservation()

    # Conservation baseline — BEFORE reads; fail loudly if unreadable.
    before_set = conservation.build_content_set(
        list(memory_dir.glob("*.md")), raise_on_error=True
    )

    text = memory_md.read_text(encoding="utf-8")
    lines, nbytes = measure(text)
    print(
        f"aim-tracking-rotate --fix-memory-md: {memory_md}\n"
        f"  before: {lines} lines / {nbytes / 1024:.1f} KB "
        f"(cap {AUTO_MEMORY_CONTRACT.cap_lines} / {AUTO_MEMORY_CONTRACT.cap_kb})"
    )

    log_shaped = _has_log_shape_violation(text)
    if not over_cap(lines, nbytes, AUTO_MEMORY_CONTRACT) and not log_shaped:
        print("  already within cap and no log-shape entries — no action needed.")
        return 0

    _backup_file(memory_md, now)

    sections = _parse_memory_sections(text)
    new_sections: list[tuple[str, str]] = []
    changed = False
    # Sibling writes are staged here; committed atomically after the full pass
    # so a mid-run error never leaves orphaned siblings while MEMORY.md is intact.
    pending_writes: dict[Path, str] = {}

    try:
        for header, content in sections:
            new_content, sec_changed = _fix_section(
                content, header, memory_dir, pending_writes
            )
            new_sections.append((header, new_content))
            changed = changed or sec_changed
    except SiblingCollisionError as exc:
        print(
            f"ERROR: sibling collision — {exc}. "
            "MEMORY.md was NOT modified; relocate or rename the sibling by hand.",
            file=sys.stderr,
        )
        return 1

    if not changed:
        print(
            "  no relocatable entries found (all blocks ≤2 lines / ≤200 chars "
            "or already pointer-format) — no action taken."
        )
        return 0

    # Compute new MEMORY.md text and build virtual after-state (prove before write).
    new_text = _reassemble_memory(new_sections)

    all_md_after: dict[Path, str] = {}
    for p in memory_dir.glob("*.md"):
        all_md_after[p] = p.read_text(encoding="utf-8")
    all_md_after[memory_md] = new_text
    all_md_after.update(pending_writes)

    # Build the virtual after-state via the shared conservation helper (same
    # canonical multiset used everywhere) — proven BEFORE any write.
    after_set = conservation.build_content_set_from_texts(all_md_after.values())
    try:
        conservation.assert_no_content_loss(before_set, after_set)
    except AssertionError as exc:
        print(f"ERROR: conservation FAILED: {exc}", file=sys.stderr)
        return 1

    # Conservation proved — commit sibling writes then MEMORY.md atomically.
    for sib_path, sib_content in pending_writes.items():
        atomic_write(sib_path, sib_content)
    atomic_write(memory_md, new_text)

    new_lines, new_bytes = measure(new_text)
    print(
        f"  after:        {new_lines} lines / {new_bytes / 1024:.1f} KB\n"
        f"  conservation: union before ⊆ union after, 0 lines lost ✓"
    )
    if over_cap(new_lines, new_bytes, AUTO_MEMORY_CONTRACT):
        print(
            "  WARNING: still over cap — run again or trim by hand.",
            file=sys.stderr,
        )
    return 0


def run_fix_all(
    oversight_root: Path, now: datetime, include_memory_md: bool = False
) -> int:
    """Fix every governed oversight file, then MEMORY.md if opted in."""
    governed = discover_governed(oversight_root)
    results: list[int] = []
    for gf in governed:
        rc = run_fix(gf.path, oversight_root, now)
        results.append(rc)

    memory_md = resolve_memory_md()
    if memory_md:
        if include_memory_md:
            results.append(run_fix_memory_md(memory_md, now))
        else:
            print(
                f"NOTICE: --fix-all skipped auto-memory MEMORY.md at {memory_md}.\n"
                "  Pass --include-memory-md to include it."
            )

    if not results:
        print("aim-tracking-rotate --fix-all: no governed files found.")
        return 0
    errors = sum(1 for r in results if r != 0)
    print(
        f"\naim-tracking-rotate --fix-all: {len(results)} file(s) processed, "
        f"{errors} error(s)."
    )
    return max(results)


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


def resolve_memory_md(project_cwd: Path | None = None) -> Path | None:
    """Resolve the auto-memory MEMORY.md path for the current project.

    Resolution order: ``$autoMemoryDirectory``  or
    ``~/.claude/projects/<slug>/memory/``, where ``<slug>`` = project cwd
    with every ``/`` replaced by ``-``.  Returns ``None`` when the file does
    not exist (MEMORY.md is optional — not every project uses it).
    """
    cwd = project_cwd or Path.cwd()
    auto_memory_dir = os.environ.get("autoMemoryDirectory")  # noqa: SIM112
    if auto_memory_dir:
        base = Path(auto_memory_dir).expanduser()
    else:
        slug = str(cwd).replace("/", "-")
        base = Path.home() / ".claude" / "projects" / slug / "memory"
    candidate = base / "MEMORY.md"
    return candidate if candidate.is_file() else None


def _check_memory_md(memory_md: Path) -> list[str]:
    """Return WARN strings for cap or log-shape issues in MEMORY.md.

    Issues are warnings (not gate failures): MEMORY.md is not an oversight
    file and its cap is a load-window advisory, not a hard enforcement gate.
    """
    warnings: list[str] = []
    text = memory_md.read_text(encoding="utf-8")
    lines, nbytes = measure(text)

    if over_cap(lines, nbytes, AUTO_MEMORY_CONTRACT):
        warnings.append(
            f"MEMORY.md over cap: {lines} lines / {nbytes / 1024:.1f} KB "
            f"(cap {AUTO_MEMORY_CONTRACT.cap_lines}L"
            f" / {AUTO_MEMORY_CONTRACT.cap_kb}KB) — run `--fix-memory-md`"
        )

    # Log-shape: any paragraph block > allowed per-entry limits.
    # A block of pointer-format lines is the conformant index shape — skip it.
    section_header_re = re.compile(r"^#{1,3} ")
    for block in _split_into_blocks(text):
        stripped = block.strip()
        if not stripped:
            continue
        block_lines = [ln for ln in stripped.splitlines() if ln.strip()]
        # A lone section header (no body) is structural, not a log entry.
        if len(block_lines) == 1 and section_header_re.match(stripped):
            continue
        non_blank = [ln for ln in stripped.splitlines() if ln.strip()]
        if all(_is_memory_pointer(ln) for ln in non_blank):
            continue  # list of pointers is conformant, not a log-shape violation
        if (
            len(non_blank) > _MEMORY_LOG_SHAPE_MAX_LINES
            or len(stripped) > _MEMORY_LOG_SHAPE_MAX_CHARS
        ):
            preview = stripped[:60].replace("\n", " ")
            warnings.append(
                f"MEMORY.md index-not-log violation: "
                f"{len(non_blank)} lines / {len(stripped)} chars in entry "
                f"(max {_MEMORY_LOG_SHAPE_MAX_LINES} lines / "
                f"{_MEMORY_LOG_SHAPE_MAX_CHARS} chars): {preview!r}…"
            )
            break  # first violation only — avoid output spam

    return warnings


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
            "Enforce oversight-file caps at session-close (--check), rotate "
            "an over-cap file's oldest entries into a dated archive shard "
            "(--apply), or fix an over-cap file non-interactively (--fix / "
            "--fix-all / --fix-memory-md)."
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
    mode.add_argument(
        "--fix",
        metavar="FILE",
        help=(
            "Fix FILE non-interactively: add front-matter, cap-fix by class, "
            "prove conservation. Archive-only; emits a plan + conservation report."
        ),
    )
    mode.add_argument(
        "--fix-all",
        action="store_true",
        help="Fix all governed oversight files, then MEMORY.md if resolvable.",
    )
    mode.add_argument(
        "--fix-memory-md",
        action="store_true",
        help=(
            "Fix MEMORY.md only: relocate over-long entries to sibling files "
            "and prove conservation across the full union."
        ),
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
    parser.add_argument(
        "--include-memory-md",
        action="store_true",
        default=False,
        help=(
            "With --fix-all: also fix the real auto-memory MEMORY.md. "
            "Skipped by default since --fix-all is usually scoped to "
            "--oversight-root."
        ),
    )
    args = parser.parse_args(argv)

    # --fix-memory-md does not need an oversight root.
    if args.fix_memory_md:
        memory_md = resolve_memory_md()
        if memory_md is None:
            print(
                "ERROR: MEMORY.md not found. "
                "Set $autoMemoryDirectory or run from the project root.",
                file=sys.stderr,
            )
            return 1
        return run_fix_memory_md(memory_md, resolve_now(args.period))

    oversight_root = resolve_oversight_root(args)
    now = resolve_now(args.period)

    if args.check:
        return run_check(oversight_root)
    if args.apply:
        return run_apply(
            Path(args.apply).expanduser(),
            oversight_root,
            args.entry_pattern,
            args.keep,
            now,
        )
    if args.fix:
        return run_fix(Path(args.fix).expanduser(), oversight_root, now)
    # --fix-all
    return run_fix_all(oversight_root, now, getattr(args, "include_memory_md", False))


if __name__ == "__main__":
    raise SystemExit(main())
