#!/usr/bin/env python3
"""Parzival session-start loader (Tier B + oversight — the ``/pov:parzival-start`` phase).

Emits a single consolidated, capped context block of the FILE-based session
context in the approved A2 order. The Qdrant cross-session section (bootstrap
L1/L2/L3) and the L1 handoff gate stay in their own step (step-01b /
aim-parzival-bootstrap) — this loader never reads a handoff file (the most
recent handoff comes from bootstrap L1; the file is read only on the existing
CASE-A/CASE-B fallback).

``--scope`` selects which slice to emit so the step files can honor the A2
interleave (oversight summaries -> bootstrap Qdrant -> sanctum Tier B):
  oversight : SESSION_WORK_INDEX (full) + tracking active sections + bugs/TD Quick Stats
  sanctum   : LORE recency slice + BOND (full, vital floor) + sanctum MEMORY (full)
  all       : oversight then sanctum (default; used by the budget/smoke tests)

Approved A2 caps:
  - tracking files : active sections only (Resolved/Closed/archive dropped)
  - bugs/TD INDEX  : ## Quick Stats only
  - LORE.md        : recency-weighted slice <= 25 KB + pointer
  - BOND.md        : full (vital floor)
  - sanctum MEMORY : full (tiny)

Usage:
    session_loader.py [PROJECT_ROOT] [--scope oversight|sanctum|all]
PROJECT_ROOT defaults to the current working directory.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from loader_common import (
    cap_done_section,
    lore_slice,
    read_text,
    resolve_paths,
    select_sections,
)

# Approved A2 cap (identity-file cap is a Will call; see A2-CAP-TABLE-APPROVED.md).
LORE_SLICE_CAP_KB = 25

# Sections dropped from the tracking files (active-only). Title-prefix match.
TRACKING_DROP = ["Resolved", "Closed", "Previous Sprint", "Risk Categories"]

# step-01 spec: the task-tracker ``## Done`` section loads only the last N rows.
DONE_KEEP_ROWS = 3

# Fire-only-if-missing markers for the bugs/tech-debt INDEX files (fresh installs
# lack both until the first ``aim-tracking-freshness --write`` run).
_INDEX_ABSENT_MARKERS = {
    "bugs/INDEX.md": "bugs INDEX absent — bug counts unavailable; run /aim-tracking-freshness",
    "tech-debt/INDEX.md": "tech-debt INDEX absent — TD counts unavailable; run /aim-tracking-freshness",
}

# Open Deferrals surface (PLAN-035 P2.6 / PM #410) — fire-only-on-open pattern,
# same shape as the Pending Updates surface in step-02-compile-status.md: emit
# nothing when there is nothing to report, never print "0 open". DEFERRAL_TEMPLATE.md's
# identity block is a table (`| **Status** | value |`), not a leading-bold line —
# the record is brand new (no legacy colon-format data to tolerate), so only the
# table-row form is matched, mirroring aim-tracking-freshness's _STATUS_TABLE_RE.
_DEFER_RECORD_RE = re.compile(r"^DEFER-(\d+)(?:-[a-z0-9-]+)?\.md$", re.IGNORECASE)
_DEFER_STATUS_RE = re.compile(r"^\|\s*\*\*Status\*\*\s*\|\s*(.+?)\s*\|", re.MULTILINE)
_DEFER_TRIGGER_RE = re.compile(
    r"^\|\s*\*\*Revisit-Trigger\*\*\s*\|\s*(.+?)\s*\|", re.MULTILINE
)
_DEFER_DATE_TRIGGER_RE = re.compile(r"^Date:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


def _emit(title: str, body: str) -> str:
    return f"## [loader] {title}\n\n{body.rstrip()}\n"


def _deferrals_block(paths: dict[str, Path]) -> list[str]:
    oversight = paths["oversight_path"]
    deferrals_dir = oversight / "deferrals"
    if not deferrals_dir.is_dir():
        return []

    open_lines: list[str] = []
    triggered_lines: list[str] = []
    today = date.today()

    for name in sorted(deferrals_dir.iterdir()):
        if not _DEFER_RECORD_RE.match(name.name):
            continue
        text = read_text(name)
        if not text:
            continue
        status_m = _DEFER_STATUS_RE.search(text)
        status = status_m.group(1).strip() if status_m else ""
        if not status.upper().startswith(("DEFERRED", "REVISITING")):
            continue  # Resolved/Dropped — not open, do not surface

        trigger_m = _DEFER_TRIGGER_RE.search(text)
        trigger = trigger_m.group(1).strip() if trigger_m else "(no trigger set)"
        open_lines.append(f"- {name.stem}: {trigger}")

        date_m = _DEFER_DATE_TRIGGER_RE.match(trigger)
        if date_m:
            try:
                trigger_date = date.fromisoformat(date_m.group(1))
            except ValueError:
                trigger_date = None
            if trigger_date and trigger_date <= today:
                triggered_lines.append(
                    f"- {name.stem}: date trigger passed ({date_m.group(1)})"
                )

    if not open_lines:
        return []  # fire-only-on-open: nothing deferred, emit nothing

    body = f"{len(open_lines)} open:\n" + "\n".join(open_lines)
    if triggered_lines:
        body += "\n\nTRIGGER MET (revisit now):\n" + "\n".join(triggered_lines)
    return [_emit("oversight/deferrals (Open Deferrals)", body)]


def _oversight_blocks(paths: dict[str, Path]) -> list[str]:
    oversight = paths["oversight_path"]
    blocks: list[str] = []

    swi = read_text(oversight / "SESSION_WORK_INDEX.md")
    blocks.append(
        _emit("oversight/SESSION_WORK_INDEX.md", swi or "(absent — first session)")
    )

    for rel in (
        "tracking/task-tracker.md",
        "tracking/blockers-log.md",
        "tracking/risk-register.md",
    ):
        text = read_text(oversight / rel)
        if not text:
            continue
        body = select_sections(text, drop=TRACKING_DROP)
        if rel == "tracking/task-tracker.md":
            body = cap_done_section(body, DONE_KEEP_ROWS, str(oversight / rel))
        blocks.append(_emit(f"oversight/{rel} (active sections)", body))

    for rel in ("bugs/INDEX.md", "tech-debt/INDEX.md"):
        text = read_text(oversight / rel)
        body = (
            select_sections(text, keep=["Quick Stats"])
            if text
            else _INDEX_ABSENT_MARKERS[rel]
        )
        blocks.append(_emit(f"oversight/{rel} (Quick Stats)", body))
    blocks.extend(_deferrals_block(paths))
    return blocks


def _sanctum_blocks(paths: dict[str, Path]) -> list[str]:
    sanctum = paths["sanctum_path"] / "parzival"
    blocks: list[str] = []

    lore_path = sanctum / "LORE.md"
    lore_text = read_text(lore_path)
    if lore_text:
        blocks.append(
            _emit(
                "sanctum/LORE.md (recency-weighted slice)",
                lore_slice(lore_text, LORE_SLICE_CAP_KB, str(lore_path)),
            )
        )
    else:
        blocks.append(_emit("sanctum/LORE.md", "(absent — sanctum not initialized)"))

    # BOND.md — full (vital floor: Owner + Things-Asked + Things-Avoid).
    bond_text = read_text(sanctum / "BOND.md")
    blocks.append(
        _emit("sanctum/BOND.md (full — vital floor)", bond_text or "(absent)")
    )

    # sanctum MEMORY.md — full (tiny). NOT the Claude-Code auto-memory file.
    mem_text = read_text(sanctum / "MEMORY.md")
    blocks.append(_emit("sanctum/MEMORY.md (full)", mem_text or "(absent)"))
    return blocks


def build(project_root: Path, scope: str = "all") -> str:
    paths = resolve_paths(project_root)
    blocks: list[str] = []
    if scope in ("oversight", "all"):
        blocks.extend(_oversight_blocks(paths))
    if scope in ("sanctum", "all"):
        blocks.extend(_sanctum_blocks(paths))

    header = (
        f"# Parzival Session-Start Context (Tier B + oversight — scope={scope}, capped per A2)\n\n"
        "Consolidated, capped file-based session context. The Qdrant "
        "cross-session section + L1 handoff gate load separately (step-01b). "
        "Full files remain on disk at full size.\n"
    )
    return header + "\n" + "\n".join(blocks)


def _parse_scope(argv: list[str]) -> tuple[Path, str]:
    root = Path.cwd()
    scope = "all"
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--scope":
            if i + 1 >= len(argv):
                raise SystemExit("--scope requires a value: oversight|sanctum|all")
            scope = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--scope="):
            scope = arg.split("=", 1)[1]
        else:
            root = Path(arg).resolve()
        i += 1
    if scope not in ("oversight", "sanctum", "all"):
        raise SystemExit(f"--scope must be oversight|sanctum|all, got '{scope}'")
    return root, scope


def main(argv: list[str]) -> int:
    root, scope = _parse_scope(argv)
    sys.stdout.write(build(root, scope))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
