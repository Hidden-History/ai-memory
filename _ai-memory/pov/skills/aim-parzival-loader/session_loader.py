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

import sys
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


def _emit(title: str, body: str) -> str:
    return f"## [loader] {title}\n\n{body.rstrip()}\n"


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
        if text:
            blocks.append(
                _emit(
                    f"oversight/{rel} (Quick Stats)",
                    select_sections(text, keep=["Quick Stats"]),
                )
            )
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
