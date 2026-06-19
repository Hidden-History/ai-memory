#!/usr/bin/env python3
"""Parzival activation loader (Tier A — the ``/pov:parzival`` phase).

Emits a single consolidated, capped context block in the approved A2 order so
activation is one script call instead of scattered file reads. Caps are applied
at load time; the full files stay on disk at full size.

Approved A2 Tier-A order:
  1. config.yaml                         (full — agent reads session vars here)
  2. project-status.md                   (head-capped to Contract 60 lines / 6 KB)
  3. constraints/global/constraints.md   (full)
  4. constraints/{phase}/constraints.md  (full — phase from project-status)
  5. sanctum CREED.md                    (full)
  6. sanctum PERSONA.md                  (Evolution Log -> last 10 rows)
  7. sanctum BOND.md                     (First-Breath marker-scan only, NOT a load)
  8. workflows/WORKFLOW-MAP.md           (full)

Usage:
    activation_loader.py [PROJECT_ROOT]
PROJECT_ROOT defaults to the current working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from loader_common import (
    cap_evolution_log,
    cap_head,
    current_phase,
    first_breath_marker,
    read_text,
    resolve_paths,
)

# Approved A2 caps (identity-file caps are a Will call; see A2-CAP-TABLE-APPROVED.md).
PROJECT_STATUS_CAP_LINES = 60
PROJECT_STATUS_CAP_KB = 6
PERSONA_EVOLUTION_KEEP_ROWS = 10


def _emit(title: str, body: str) -> str:
    return f"## [loader] {title}\n\n{body.rstrip()}\n"


def build(project_root: Path) -> str:
    paths = resolve_paths(project_root)
    sanctum = paths["sanctum_path"] / "parzival"
    blocks: list[str] = []

    # 1. config.yaml — full (session variables live here)
    config_path = Path(project_root) / "_ai-memory/pov/config.yaml"
    blocks.append(_emit("config.yaml", read_text(config_path) or "(absent)"))

    # 2. project-status.md — head-capped to Contract(60, 6)
    status_path = paths["oversight_path"] / "project-status.md"
    status_text = read_text(status_path)
    if status_text:
        blocks.append(
            _emit(
                "project-status.md",
                cap_head(
                    status_text,
                    PROJECT_STATUS_CAP_LINES,
                    PROJECT_STATUS_CAP_KB,
                    str(status_path),
                ),
            )
        )
    else:
        blocks.append(_emit("project-status.md", "(absent — first session)"))

    # 3. global constraints — full
    blocks.append(
        _emit(
            "constraints/global/constraints.md",
            read_text(paths["constraints_path"] / "global/constraints.md")
            or "(absent)",
        )
    )

    # 4. phase constraints — full (phase resolved from project-status)
    phase = current_phase(status_text)
    if phase:
        phase_file = paths["constraints_path"] / phase / "constraints.md"
        blocks.append(
            _emit(
                f"constraints/{phase}/constraints.md",
                read_text(phase_file)
                or f"(absent — no constraints for phase '{phase}')",
            )
        )

    # 5. CREED.md — full
    blocks.append(
        _emit("sanctum/CREED.md", read_text(sanctum / "CREED.md") or "(absent)")
    )

    # 6. PERSONA.md — Evolution Log capped to last 10 rows
    persona_path = sanctum / "PERSONA.md"
    persona_text = read_text(persona_path)
    if persona_text:
        blocks.append(
            _emit(
                "sanctum/PERSONA.md",
                cap_evolution_log(
                    persona_text, PERSONA_EVOLUTION_KEEP_ROWS, str(persona_path)
                ),
            )
        )
    else:
        blocks.append(_emit("sanctum/PERSONA.md", "(absent)"))

    # 7. BOND.md — First-Breath marker-scan ONLY (cheap; not a Tier-B load)
    bond_text = read_text(sanctum / "BOND.md")
    if not bond_text:
        marker_line = "BOND.md absent — sanctum not yet initialized (run First Breath)."
    elif first_breath_marker(bond_text):
        marker_line = (
            "First-Breath marker PRESENT — owner unknown to this Parzival; "
            "run first-breath workflow before proceeding."
        )
    else:
        marker_line = (
            "First-Breath marker ABSENT — BOND is filled; full BOND loads at "
            "session-start (Tier B), not here."
        )
    blocks.append(_emit("sanctum/BOND.md (First-Breath marker-scan)", marker_line))

    # 8. WORKFLOW-MAP.md — full
    blocks.append(
        _emit(
            "workflows/WORKFLOW-MAP.md",
            read_text(paths["workflows_path"] / "WORKFLOW-MAP.md") or "(absent)",
        )
    )

    header = (
        "# Parzival Activation Context (Tier A — capped per A2)\n\n"
        "Consolidated, capped startup context. Full files remain on disk at "
        "full size; pointers mark where content was elided.\n"
    )
    return header + "\n" + "\n".join(blocks)


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    sys.stdout.write(build(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
