#!/usr/bin/env python3
"""Shared helpers for the Parzival two-phase startup loaders.

Both ``activation_loader.py`` (Tier A) and ``session_loader.py`` (Tier B +
oversight) import this module. It is deterministic and dependency-free at
runtime: every cap in the approved A2 cap table is enforced by line / byte /
entry counts, never by a tokenizer. (Token budgets are a separate concern,
verified by the test suite, which imports the project's ``count_tokens``.)

A2 cap table (oversight/tasks/task077-startup-governance/A2-CAP-TABLE-APPROVED.md):
- project-status.md : head cap to Contract(60 lines, 6 KB)
- PERSONA.md        : ## Evolution Log -> keep last 10 identity-shift rows
- LORE.md           : recency-weighted slice (structural sections + newest
                      "Things Learned" lessons up to 25 KB + a pointer)
- BOND.md           : full load (vital floor); marker-scan only at activation
- CREED / MEMORY    : full load (small; ceiling only)

Sections are matched by symbolic markdown headers, never line numbers
(no-brittle-refs rule).
"""

from __future__ import annotations

from pathlib import Path

KB = 1024


def read_text(path: str | Path) -> str:
    """Return a file's text, or "" if it is missing/unreadable.

    Missing sanctum/oversight files are a valid state (sanctum may be pre-First
    Breath), so the loaders degrade gracefully rather than raising.
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def split_h2(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split markdown into ``(preamble, [(title, block), ...])`` at ``## `` headers.

    ``preamble`` is everything before the first ``## `` line (may be "").
    Each ``block`` includes its own ``## `` header line through the line before
    the next ``## `` header.
    """
    preamble: list[str] = []
    sections: list[list] = []
    cur: list | None = None
    for ln in text.splitlines(keepends=True):
        if ln.startswith("## "):
            cur = [ln[3:].strip(), [ln]]
            sections.append(cur)
        elif cur is None:
            preamble.append(ln)
        else:
            cur[1].append(ln)
    return "".join(preamble), [(t, "".join(b)) for t, b in sections]


def cap_head(text: str, max_lines: int, max_kb: int, pointer_path: str) -> str:
    """Head-cap ``text`` to ``min(max_lines, max_kb)`` (Contract head cap).

    Returns the text unchanged if already within both caps; otherwise keeps the
    head up to whichever bound binds first and appends a one-line pointer.
    """
    max_bytes = max_kb * KB
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines and len(text.encode("utf-8")) <= max_bytes:
        return text
    kept: list[str] = []
    size = 0
    for ln in lines[:max_lines]:
        b = len(ln.encode("utf-8"))
        if kept and size + b > max_bytes:
            break
        kept.append(ln)
        size += b
    body = "".join(kept).rstrip()
    return f"{body}\n\n_(… capped at startup — full file: {pointer_path})_\n"


def select_sections(
    text: str,
    *,
    keep: list[str] | None = None,
    drop: list[str] | None = None,
) -> str:
    """Return preamble + a subset of ``## `` sections.

    With ``keep``: only sections whose title starts with a listed prefix.
    With ``drop``: all sections except those whose title starts with a listed
    prefix. Exactly one of ``keep`` / ``drop`` should be given.
    """
    preamble, sections = split_h2(text)
    out = [preamble.rstrip("\n")] if preamble.strip() else []
    for title, block in sections:
        if keep is not None:
            if any(title.startswith(p) for p in keep):
                out.append(block.rstrip("\n"))
        elif drop is not None:
            if not any(title.startswith(p) for p in drop):
                out.append(block.rstrip("\n"))
        else:
            out.append(block.rstrip("\n"))
    return "\n\n".join(p for p in out if p) + "\n"


def cap_evolution_log(text: str, keep_rows: int, pointer_path: str) -> str:
    """Cap PERSONA's ``## Evolution Log`` table to its last ``keep_rows`` rows.

    The Evolution Log is a markdown table (newest row at the bottom). The
    standing preamble (Birth line + the "not maintained here" note), the table
    header, and the separator row are always kept; only the oldest *data* rows
    are dropped, with a pointer noting how many. All other PERSONA sections are
    passed through verbatim.
    """
    preamble, sections = split_h2(text)
    parts = [preamble.rstrip("\n")] if preamble.strip() else []
    for title, block in sections:
        if title == "Evolution Log":
            parts.append(_cap_log_table(block, keep_rows, pointer_path).rstrip("\n"))
        else:
            parts.append(block.rstrip("\n"))
    return "\n\n".join(p for p in parts if p) + "\n"


def _cap_log_table(
    block: str,
    keep_rows: int,
    pointer_path: str,
    label: str = "older identity-shift rows",
) -> str:
    lines = block.splitlines(keepends=True)
    rows = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")]
    # Need header + separator + more than keep_rows data rows to be worth capping.
    if len(rows) <= keep_rows + 2:
        return block
    sep = rows[1]
    data = rows[2:]
    drop = len(data) - keep_rows
    kept = data[-keep_rows:]
    head = lines[: sep + 1]
    tail = lines[rows[-1] + 1 :]
    pointer = (
        f"\n_(… {drop} {label} capped at startup — " f"full log: {pointer_path})_\n\n"
    )
    return "".join(head) + pointer + "".join(lines[i] for i in kept) + "".join(tail)


def cap_done_section(text: str, keep_rows: int, pointer_path: str) -> str:
    """Cap the task-tracker ``## Done`` table to its last ``keep_rows`` rows.

    step-01 spec loads the task tracker active sections only and keeps just the
    last 3 ``## Done`` rows (older Done rows live in the archive). ``## Done`` is
    NOT a Resolved/Closed/Previous-Sprint section, so ``select_sections(drop=…)``
    keeps it — without this cap the whole Done table would reload and re-bloat
    startup. Only the ``## Done`` table data rows are trimmed; every other section
    (and a Done table at/under cap) passes through verbatim.
    """
    preamble, sections = split_h2(text)
    parts = [preamble.rstrip("\n")] if preamble.strip() else []
    for title, block in sections:
        if title == "Done":
            parts.append(
                _cap_log_table(
                    block, keep_rows, pointer_path, label="older Done rows"
                ).rstrip("\n")
            )
        else:
            parts.append(block.rstrip("\n"))
    return "\n\n".join(p for p in parts if p) + "\n"


def lore_slice(
    text: str,
    max_kb: int,
    pointer_path: str,
    structural: tuple[str, ...] = (
        "System Architecture",
        "Key Design Decisions",
        "Patterns & Conventions",
    ),
    lessons_title: str = "Things Learned the Hard Way",
) -> str:
    """Build the recency-weighted LORE slice.

    Always includes the file title line + the named ``structural`` sections
    verbatim, then fills the remaining byte budget with the MOST RECENT lessons
    from the ``lessons_title`` section (newest are at the tail of the file), and
    appends a one-line pointer to the full LORE.md. At least the single newest
    lesson is always kept even if it alone exceeds the remaining budget.
    """
    max_bytes = max_kb * KB
    preamble, sections = split_h2(text)
    secmap = dict(sections)

    fixed_parts: list[str] = []
    for ln in preamble.splitlines():
        if ln.startswith("# "):
            fixed_parts.append(ln.strip() + "\n")
            break
    for t in structural:
        if t in secmap:
            fixed_parts.append(secmap[t].rstrip() + "\n")
    fixed = "\n".join(fixed_parts)

    # Reserve room for the join newline + the trailing pointer so the whole
    # slice stays within max_bytes (a true ceiling, not just the bullet budget).
    pointer_reserve = 256
    remaining = max_bytes - len(fixed.encode("utf-8")) - pointer_reserve
    lessons_block, dropped = _tail_entries(secmap.get(lessons_title, ""), remaining)
    pointer = (
        f"\n_(… recency-weighted slice — {dropped} older lessons elided; "
        f"full history in: {pointer_path})_\n"
    )
    return f"{fixed}\n{lessons_block}{pointer}"


def _tail_entries(section_text: str, budget_bytes: int) -> tuple[str, int]:
    """Keep the newest ``- `` bullets in a section that fit ``budget_bytes``.

    Returns ``(rebuilt_section, dropped_count)``. The section header (lines
    before the first bullet) and any footer (lines after the last bullet, e.g.
    a trailing italic note) are always preserved. Kept bullets are emitted in
    original chronological order; at least the newest bullet is always kept.
    """
    lines = section_text.splitlines(keepends=True)
    bullet_idx = [i for i, ln in enumerate(lines) if ln.startswith("- ")]
    if not bullet_idx:
        return section_text, 0
    first, last = bullet_idx[0], bullet_idx[-1]
    header = lines[:first]
    footer = lines[last + 1 :]

    entries: list[list[str]] = []
    for ln in lines[first : last + 1]:
        if ln.startswith("- "):
            entries.append([ln])
        else:
            entries[-1].append(ln)
    entry_str = ["".join(e) for e in entries]

    # The header + footer count against the budget too, so the rebuilt section
    # stays within budget_bytes (the newest bullet is always kept regardless).
    fixed_bytes = len("".join(header + footer).encode("utf-8"))
    avail = budget_bytes - fixed_bytes
    kept: list[str] = []
    size = 0
    for s in reversed(entry_str):
        b = len(s.encode("utf-8"))
        if kept and size + b > avail:
            break
        kept.append(s)
        size += b
    kept.reverse()
    dropped = len(entry_str) - len(kept)
    body = "".join(header) + "".join(kept) + "".join(footer)
    return body, dropped


def _owner_needs_first_breath(owner_block: str) -> bool:
    """True when BOND's ``## Owner`` Name field still needs First Breath.

    Combined rule (TD-737 + scaffold-substitution fix): needs First Breath iff
    the literal ``**Name:** {user_name}`` placeholder token is present, OR the
    seed line (``_Filled during First Breath``) survives AND the Owner content
    is not yet substantively filled -- i.e. lacks either a real Name value or
    any content beyond the Name field and the seed line itself. If the seed
    line is entirely absent, the Owner has already been edited/established by
    some other path and must NOT re-trigger (fail-safe). A real Name with a
    surviving seed line but no other content is the scaffold-substitution case
    (sanctum-init substitutes a real Name at scaffold time, before First
    Breath ever runs) and DOES still need First Breath.
    """
    if "**Name:** {user_name}" in owner_block:
        return True
    if "_Filled during First Breath" not in owner_block:
        return False
    has_real_name = False
    has_extra_content = False
    for line in owner_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("## "):
            continue
        if stripped.startswith("**Name:**"):
            value = stripped[len("**Name:**") :].strip()
            if value and value != "{user_name}":
                has_real_name = True
            continue
        if "_Filled during First Breath" in stripped:
            continue
        has_extra_content = True
    return not (has_real_name and has_extra_content)


def first_breath_marker(bond_text: str) -> bool:
    """True when BOND.md's ``## Owner`` section still needs First Breath.

    A cheap marker-scan (NOT a full Tier-B load): activation reads only this
    signal from BOND.md. The scan is scoped to the ``## Owner`` block, since
    establishing the owner is exactly what First Breath does. The check gates on
    the Owner *Name* field (placeholder vs real value) via the combined rule in
    ``_owner_needs_first_breath``, NOT on bare presence of the
    ``_Filled during First Breath`` seed string -- a surviving seed line
    alongside real Name content must NOT re-trigger a destructive
    re-First-Breath (TD-737). A BOND with no ``## Owner`` section returns False
    (fail-safe: never re-trigger First Breath).
    """
    _, sections = split_h2(bond_text)
    for title, block in sections:
        if title == "Owner":
            return _owner_needs_first_breath(block)
    return False


def resolve_paths(project_root: Path) -> dict[str, Path]:
    """Resolve the POV path variables from config.yaml under ``project_root``.

    Reads ``_ai-memory/pov/config.yaml`` and substitutes the ``{project-root}``
    placeholder. Falls back to the conventional layout for any path the config
    does not define, so a missing/partial config never blocks startup.
    """
    root = Path(project_root)
    defaults = {
        "constraints_path": root / "_ai-memory/pov/constraints",
        "workflows_path": root / "_ai-memory/pov/workflows",
        "oversight_path": root / "oversight",
        "skills_path": root / "_ai-memory/pov/skills",
        "sanctum_path": root / "_ai-memory/sanctum",
    }
    config_text = read_text(root / "_ai-memory/pov/config.yaml")
    for line in config_text.splitlines():
        line = line.strip()
        if line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in defaults:
            value = value.strip().strip('"').strip("'")
            if value:
                defaults[key] = Path(value.replace("{project-root}", str(root)))
    return defaults


def current_phase(project_status_text: str) -> str | None:
    """Extract ``current_phase`` from project-status.md's fenced yaml block."""
    for line in project_status_text.splitlines():
        s = line.strip()
        if s.startswith("current_phase:"):
            phase = s.split(":", 1)[1].strip().strip('"').strip("'")
            return phase or None
    return None
