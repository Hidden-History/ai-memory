"""
contract.py — Shared governed-file Contract model.

A frozen dataclass describing the cap + rotation policy for one governed
context-hot file class. Canonical, single-source: imported by both
aim-tracking-rotate (oversight classes) and aim-lore-hygiene (sanctum
classes), and by the session-close --check gate. No copy-paste.

cap_lines / cap_kb     The line and KB ceilings for the class.
klass                  The governance class label (heartbeat / register /
                       append-only-log / live-index / auto-memory-index /
                       sanctum identity class, etc.).
rotatable=True         --apply performs entry rotation/relocation.
rotatable=False        check-only (heartbeat / thin register / identity
                       directive file); --apply refuses with a clear message.
archive_target         Relative archive path for relocated entries (templated
                       with {YYYY} where dated shards are used).
index_file             Sibling index/pointer file, where the class maintains one.
entry_pattern          Entry-boundary regex override for this file. Table-row
                       files (live-index) carry '^\\| '; H3-entry files inherit
                       the global default.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    # Section-cap policy (sanctum classes). When set, the fix keeps the last
    # ``section_keep_last`` entries under the ``section_anchor`` heading (symbolic
    # anchor, never line numbers) and relocates older ones losslessly — e.g.
    # PERSONA's ``## Evolution Log`` → last 10. Unused by classes that whole-file
    # rotate or check-only (both leave these None).
    section_anchor: str | None = None
    section_keep_last: int | None = None
