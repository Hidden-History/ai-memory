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

  --apply <file>     The fix (BP-167 Part C rotation). Move the OLDEST
                     CONTIGUOUS block of whole entries (never splitting an
                     entry) into a dated archive shard, update the manifest
                     (append-only-log) or the reconciliation banner (register),
                     write a thin live pointer, and verify counts. Chronology
                     is preserved by construction.

Ownership boundary (vs aim-tracking-freshness / D5): rotate owns the
append-only-log + register archival (decision-log shards + manifest,
blockers/risk archive, SESSION_WORK_INDEX tail-shed, session-index quarterly).
It does NOT touch the generated bugs/INDEX.md or tech-debt/INDEX.md — those and
their CLOSED.md shards are owned by aim-tracking-freshness.

Contract source of truth: PARZIVAL-OVERSIGHT-SOT.md §14 (D1 cap mapping, D2
per-seed values) and BP-167 Part C (rotation lifecycle).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
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
    ),
    "tracking/task-tracker.md": Contract(40, 2.5, "register", False),
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
    ),
}

# Latest SESSION_HANDOFF_*.md (detail-record, whole-file, 60/8). Discovered by
# glob rather than fixed path; --apply on a handoff is not supported here
# (handoff archival is owned by close step-03).
HANDOFF_CONTRACT = Contract(60, 8, "detail-record", False)
HANDOFF_GLOB = "session-logs/SESSION_HANDOFF_*.md"

# Default entry boundary: a markdown H3 heading. Override with --entry-pattern
# for table-row formats (e.g. session-index: '^\\| ').
DEFAULT_ENTRY_PATTERN = r"^### "

# Idempotent live-pointer marker.
POINTER_MARKER = "<!-- aim-tracking-rotate:pointer -->"

DEC_ID_RE = re.compile(r"\b(DEC-[A-Za-z0-9][A-Za-z0-9-]*)\b")


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
    return Contract(
        cap_lines=cap_lines,
        cap_kb=cap_kb,
        klass=values.get("class", "unknown"),
        rotatable=trigger.startswith("on-close") and archive is not None,
        archive_target=archive,
        index_file=index_file,
    )


def measure(text: str) -> tuple[int, int]:
    """Return ``(lines, bytes)`` mirroring ``wc -l`` / ``wc -c``."""
    return text.count("\n"), len(text.encode("utf-8"))


def over_cap(lines: int, nbytes: int, contract: Contract) -> bool:
    return lines > contract.cap_lines or nbytes > contract.cap_kb * 1024


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


# ---------------------------------------------------------------------------
# --check : the enforcement gate
# ---------------------------------------------------------------------------


def script_invocation() -> str:
    """A copy-pasteable path to this script for remedy commands."""
    return f"python {Path(__file__).resolve()}"


def run_check(oversight_root: Path) -> int:
    governed = discover_governed(oversight_root)
    breaches: list[str] = []
    for gf in governed:
        lines, nbytes = measure(gf.path.read_text(encoding="utf-8"))
        if not over_cap(lines, nbytes, gf.contract):
            continue
        kb = nbytes / 1024
        remedy = (
            f"{script_invocation()} --apply {gf.path} "
            f"--oversight-root {oversight_root}"
            if gf.contract.rotatable
            else (
                f"trim {gf.rel} by hand — class '{gf.contract.klass}' is "
                "overwrite-in-place / thin (rotation_trigger: none)"
            )
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
    """Split a file into front-matter, preamble, and an ordered entry list."""
    front_matter, body = split_front_matter(text)
    body_no_pointer = strip_pointer(body)
    lines = body_no_pointer.splitlines(keepends=True)
    entry_re = re.compile(entry_pattern)

    boundaries = [i for i, ln in enumerate(lines) if entry_re.match(ln)]
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


def select_oldest_block(
    parsed: ParsedFile,
    contract: Contract,
    pointer_line: str,
    keep_override: int | None,
) -> int:
    """Return how many of the OLDEST entries to move.

    Entries are newest-first (newest at index 0, oldest last), so the oldest
    contiguous block is the tail. We keep as many newest entries as fit under
    both caps; the remainder (oldest) rotate out. With ``keep_override`` the
    caller forces the kept-newest count.
    """
    n = len(parsed.entries)
    if keep_override is not None:
        return max(0, n - max(0, min(keep_override, n)))

    fixed = parsed.front_matter + parsed.preamble + pointer_line
    for keep in range(n, -1, -1):
        candidate = fixed + "".join(e.block for e in parsed.entries[:keep])
        lines, nbytes = measure(candidate)
        if not over_cap(lines, nbytes, contract):
            return n - keep
    # Even zero kept entries is over cap (preamble alone too big) -> move all.
    return n


def render_period(archive_target: str, now: datetime) -> str:
    out = archive_target
    out = out.replace("{YYYY-MM}", now.strftime("%Y-%m"))
    out = out.replace("{YYYY-Q}", f"{now.year}-Q{(now.month - 1) // 3 + 1}")
    out = out.replace("{YYYY}", now.strftime("%Y"))
    return out


def append_to_shard(shard: Path, moved: list[Entry], source_rel: str) -> None:
    shard.parent.mkdir(parents=True, exist_ok=True)
    moved_text = "".join(e.block for e in moved)
    if shard.is_file():
        existing = shard.read_text(encoding="utf-8")
        sep = "" if existing.endswith("\n") else "\n"
        shard.write_text(existing + sep + moved_text, encoding="utf-8")
    else:
        header = (
            f"# Archive — rotated from `{source_rel}`\n\n"
            "Contiguous, period-labelled archive shard. Append-ordered; never "
            "re-sorted. Chronology is preserved by construction (BP-167 Part C).\n\n"
        )
        shard.write_text(header + moved_text, encoding="utf-8")


def update_manifest(manifest: Path, moved: list[Entry], shard_rel: str) -> int:
    """Append/refresh manifest rows for each moved entry. Returns rows written."""
    manifest.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Decision Log — Manifest\n\n"
        "Single maintained index (BP-167 Part C): one row per entry id → "
        "title → location → status. O(1) by-id lookup across all shards.\n\n"
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
    manifest.write_text(text, encoding="utf-8")
    return len(rows)


def update_banner(parsed: ParsedFile, remaining: int) -> tuple[str, bool]:
    """Set the register reconciliation banner count to ``remaining``.

    Returns ``(new_preamble, updated)``.
    """
    pattern = re.compile(r"(\d+)(\s+active as of)")
    if pattern.search(parsed.preamble):
        return pattern.sub(rf"{remaining}\2", parsed.preamble, count=1), True
    return parsed.preamble, False


def run_apply(
    file_path: Path,
    oversight_root: Path,
    entry_pattern: str,
    keep_override: int | None,
    now: datetime,
) -> int:
    if not file_path.is_file():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        return 1

    rel = (
        file_path.resolve().relative_to(oversight_root.resolve()).as_posix()
        if str(file_path.resolve()).startswith(str(oversight_root.resolve()))
        else file_path.name
    )
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

    text = file_path.read_text(encoding="utf-8")
    before_lines, before_bytes = measure(text)
    parsed = parse_entries(text, entry_pattern)
    if not parsed.entries:
        print(
            f"ERROR: no entries detected in {rel} with pattern "
            f"{entry_pattern!r}; nothing to rotate.",
            file=sys.stderr,
        )
        return 1

    shard_rel = render_period(contract.archive_target, now)
    pointer_line = (
        f"> Older entries archived → `{shard_rel}`"
        + (f" (manifest: `{contract.index_file}`)" if contract.index_file else "")
        + f". {POINTER_MARKER}\n"
    )

    move_count = select_oldest_block(parsed, contract, pointer_line, keep_override)
    if move_count == 0:
        print(
            f"{rel}: already within cap — no entries rotated "
            f"({before_lines} lines / {before_bytes / 1024:.1f} KB).",
        )
        return 0

    total = len(parsed.entries)
    kept = parsed.entries[: total - move_count]
    moved = parsed.entries[total - move_count :]

    # 1. Archive shard.
    shard = oversight_root / shard_rel
    append_to_shard(shard, moved, rel)

    # 2. Reconciliation: manifest (append-only-log) OR banner (register).
    manifest_rows = 0
    banner_updated = False
    new_preamble = parsed.preamble
    if contract.index_file:
        manifest_rows = update_manifest(
            oversight_root / contract.index_file, moved, shard_rel
        )
    if contract.klass == "register":
        new_preamble, banner_updated = update_banner(parsed, len(kept))

    # 3. Rewrite live file = front-matter + preamble + pointer + kept entries.
    pre = new_preamble
    if pre and not pre.endswith("\n"):
        pre += "\n"
    new_text = parsed.front_matter + pre + pointer_line + "".join(e.block for e in kept)
    file_path.write_text(new_text, encoding="utf-8")

    # 4. Verify counts.
    after_lines, after_bytes = measure(new_text)
    assert len(kept) + len(moved) == total, "entry count mismatch after rotation"
    for e in moved:
        assert e.block.startswith(e.header), "entry split detected"

    print(
        "\n".join(
            [
                f"aim-tracking-rotate --apply: {rel}",
                f"  entries:  {total} total → {len(kept)} kept / "
                f"{len(moved)} archived",
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
    if over_cap(after_lines, after_bytes, contract):
        print(
            "  WARNING: live file still over cap after moving all entries — "
            "preamble alone exceeds the cap; trim it by hand.",
            file=sys.stderr,
        )
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
        default=DEFAULT_ENTRY_PATTERN,
        help=(
            "Regex matching an entry-boundary line (default: H3 heading "
            f"{DEFAULT_ENTRY_PATTERN!r}). Use '^\\| ' for table-row registers."
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
