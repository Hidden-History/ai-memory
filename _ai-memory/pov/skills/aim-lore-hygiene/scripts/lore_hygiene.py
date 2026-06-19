#!/usr/bin/env python3
"""Per-operator sanctum lore-file hygiene — cap enforcement, anchored compaction,
and the prune-vs-archive decision rule (BP-159 / BP-165).

FILE-content hygiene for always-injected sanctum files (LORE.md, MEMORY.md): keep
each under the ~200-line cap so rules don't "get lost in the noise" and adherence
stays high. This is NOT Qdrant-point purging by age — that is ``aim-purge``, a
separate domain (PLAN-028 P0-3).

Design (W-07 skills-with-scripts): this is the deterministic, fragile core invoked
BY PATH from SKILL.md. The model orchestrates (which files, what order, how to read
the plan); this script does the exact line-counting, marker-classification, and
structural compaction. Anything genuinely semantic (rewriting prose to fewer words)
is surfaced as a FLAG for a human/LLM pass — the script never silently truncates
recall-value content (the "memory blindness" guard, BP-159 §6).

Safety:
- ``--dry-run`` is the DEFAULT. Without ``--apply`` nothing is ever written.
- ``--apply`` writes a timestamped ``.bak`` sidecar before mutating each file.
- Archived entries move to a local cold-tier file and leave a one-line pointer in
  the hot file. Nothing with recall value is deleted without being archived first.

Usage:
    # Dry-run audit of a sanctum dir (DEFAULT — never mutates):
    python3 lore_hygiene.py <sanctum-path>

    # Apply the plan after reviewing it:
    python3 lore_hygiene.py <sanctum-path> --apply

    # Audit a single file with an explicit cap:
    python3 lore_hygiene.py <sanctum-path>/LORE.md --cap 200

    # Also push archived entries to the Qdrant cold tier (best-effort, opt-in):
    python3 lore_hygiene.py <sanctum-path> --apply --qdrant --group-id <project>
"""

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Shared governance core (single canonical source, no copy-paste). The install
# copies _ai-memory/pov/ verbatim, so resolving from __file__ is install-robust:
# this script lives at pov/skills/aim-lore-hygiene/scripts/, so parents[3] is pov/
# and pov/lib/governance/ holds the shared Contract + conservation modules — the
# SAME modules aim-tracking-rotate imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib" / "governance"))
import conservation  # pov/lib/governance is on sys.path (above)
from contract import Contract

# --- Constants (no voodoo: every value carries its BP-159/BP-165 rationale) ---

# BP-159 §2: always-injected instruction/memory files standardize on a ~200-line
# ceiling — models reliably follow ~150-200 distinct instructions and Claude Code's
# MEMORY.md silently truncates past line 200 (claude-code #25006).
CAP_LINES = 200

# BP-165 DELTA-1: compact when a file crosses ~80% of its cap. 2026 sources put
# Claude Code auto-compaction at 83.5% with proactive /compact recommended 70-90%;
# 0.80 sits safely inside that band. At CAP_LINES=200 the trigger is 160 lines.
COMPACT_AT = 0.80

# The sanctum hot files this skill curates by default, their caps, and their fix
# strategy now live in SANCTUM_CONTRACTS (below). CLAUDE.md (BP-165 DELTA-2, 300-line
# companion cap) lives at project root, not the sanctum, so it is not scanned by
# default — pass it explicitly with --cap 300 if desired.

# BP-159 §6 prune-vs-archive decision rule, expressed as explicit inline markers.
# Marker-driven classification is the deterministic, safe subset: utility/LRU
# scoring needs retrieval telemetry the script cannot see, so we never GUESS that
# an entry is low-utility — the operator (or an upstream LLM pass) tags it.
# PRUNE = delete: superseded / contradicted / proven-wrong / expired TTL.
PRUNE_MARKERS = ("[superseded]", "[contradicted]", "[wrong]", "[obsolete]", "[prune]")
# ARCHIVE = move to cold tier + leave a pointer: stale-but-historically-meaningful.
ARCHIVE_MARKERS = ("[stale]", "[archive]")
# [expired:YYYY-MM-DD] is a TTL entry — delete once the date has passed (BP-159 §6).
EXPIRY_RE = re.compile(r"\[expired:(\d{4}-\d{2}-\d{2})\]")

# Cold-tier archive location (BP-159 §3: cold tier may be a vector DB OR sharded
# files). Local archive files are the always-available, testable cold tier; the
# optional --qdrant push layers the vector tier on top.
ARCHIVE_SUBDIR = "references/lore-archive"

# Truncation length for the one-line hot-file pointer left behind on archive.
POINTER_SUMMARY_CHARS = 80

# Per-class governance contracts (TASK-077 A2 caps + B3 per-class fix strategy).
# The Contract is the SHARED frozen dataclass from pov/lib/governance/contract.py
# (the same model aim-tracking-rotate uses) — declared per sanctum class here, no
# local copy. Strategy is derived from the contract (see strategy_for):
#   - compact     : marker-driven prune/archive/dedup (the existing LORE/MEMORY
#                   behavior) + the shared conservation 0-lost proof on relocation.
#   - section-cap : keep the last N entries under a symbolic section anchor and
#                   relocate older ones losslessly (PERSONA ## Evolution Log → 10).
#   - check-only  : cap-CHECK + report; an over-cap identity file HALTs (non-zero)
#                   and is NEVER auto-relocated (CREED / BOND).
# A2 gives explicit line/KB caps for CREED (120/8), BOND (100/12) and sanctum
# MEMORY (80/4). For LORE the 200-line family cap (BP-159 §2) is reporting-only —
# the lore-hygiene fix is tag-driven (A2 "Part B is separate and tag-driven"); the
# 25 KB mirrors A2's LORE budget. PERSONA's active governance is the last-10
# section cap, so its file line/KB are the family default (reporting-only).
# NOTE: sanctum MEMORY is kept on the existing 200-line compact behavior (not the
# A2 80/4 ceiling-only) to preserve current tested behavior; flagged for review.
SANCTUM_CONTRACTS: dict[str, Contract] = {
    "CREED.md": Contract(120, 8.0, "creed", rotatable=False),
    "PERSONA.md": Contract(
        CAP_LINES,
        25.0,
        "persona",
        rotatable=True,
        section_anchor="## Evolution Log",
        section_keep_last=10,
    ),
    "LORE.md": Contract(CAP_LINES, 25.0, "lore", rotatable=True),
    "BOND.md": Contract(100, 12.0, "bond", rotatable=False),
    "MEMORY.md": Contract(CAP_LINES, 25.0, "sanctum-memory", rotatable=True),
}


def strategy_for(contract: Contract) -> str:
    """Map a sanctum Contract to its fix strategy (B3)."""
    if contract.klass in ("creed", "bond"):
        return "check-only"
    if contract.section_anchor is not None:
        return "section-cap"
    return "compact"


@dataclass
class EntryAction:
    """One classified entry and what should happen to it."""

    text: str  # full entry text (may be multi-line)
    section: str  # owning "## section" header, or "" for preamble
    action: str  # "keep" | "prune" | "archive" | "dedup"
    reason: str  # human-readable justification for the plan


@dataclass
class FilePlan:
    """The compaction plan for a single file — pure data, no I/O performed."""

    filename: str
    cap: int
    original_lines: int
    new_text: str
    archived_blocks: list[str] = field(default_factory=list)
    actions: list[EntryAction] = field(default_factory=list)

    @property
    def trigger(self) -> int:
        return int(self.cap * COMPACT_AT)

    @property
    def projected_lines(self) -> int:
        return len(self.new_text.splitlines())

    @property
    def over_cap(self) -> bool:
        return self.original_lines > self.cap

    @property
    def over_trigger(self) -> bool:
        return self.original_lines >= self.trigger

    @property
    def counts(self) -> dict[str, int]:
        out = {"prune": 0, "archive": 0, "dedup": 0}
        for a in self.actions:
            if a.action in out:
                out[a.action] += 1
        return out

    @property
    def has_changes(self) -> bool:
        return any(a.action != "keep" for a in self.actions)

    @property
    def residual_over_cap(self) -> int:
        """Lines still over cap after mechanical compaction (needs a semantic pass)."""
        return max(0, self.projected_lines - self.cap)


def split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    """Return (frontmatter_lines, body_lines). Frontmatter is preserved verbatim."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], lines
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return lines[: idx + 1], lines[idx + 1 :]
    # Unterminated fence — treat the whole file as body rather than guessing.
    return [], lines


def detect_newline(text: str) -> str:
    """Return the file's dominant line ending so untouched content is re-emitted with
    it; default LF when none is present (L-CRLF).

    Parsing strips endings via ``splitlines()`` and reassembly joins with ``"\\n"``, so
    without this a CRLF (or lone-CR) file would be silently rewritten with LF endings —
    not byte-preserving for untouched content. A single dominant ending is chosen so the
    rewrite is uniform (never a mixed-ending file).
    """
    crlf = text.count("\r\n")
    lone_cr = text.count("\r") - crlf
    lone_lf = text.count("\n") - crlf
    if crlf and crlf >= lone_lf and crlf >= lone_cr:
        return "\r\n"
    if lone_cr and lone_cr > lone_lf:
        return "\r"
    return "\n"


def read_preserving_newlines(path: Path) -> str:
    """Read text WITHOUT universal-newline translation so the original line ending stays
    visible to ``detect_newline`` (``Path.read_text`` would collapse CRLF/CR to LF)."""
    return path.read_bytes().decode("utf-8")


def is_bullet(line: str) -> bool:
    # L-PLUS-BULLET: ``+`` is a valid GFM unordered-list bullet alongside ``-``/``*``.
    return bool(re.match(r"\s*([-*+]|\d+\.)\s+", line))


def is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def is_pointer(line: str) -> bool:
    """A pointer we previously left behind — never re-process it (idempotency)."""
    return "_[archived " in line and "→" in line


# --- Structural-construct recognizers (the keep-when-uncertain backstop) ---------
#
# parse_entries is STRUCTURE-AWARE: it only ever lets the classifier/dedup touch
# units it can confidently identify as genuine CONTENT (bullets, paragraphs, table
# content rows). Every structural or ambiguous construct — code fences, thematic
# breaks, table header+separator rows, blockquotes, indented code, raw HTML — is
# emitted as an opaque ``__passthrough__`` unit: copied through byte-for-byte, never
# classified, deduped, split, or rewritten. Data-safety beats cleverness: this skill
# mutates the operator's OWN memory, so anything we cannot confidently classify we
# KEEP intact (BP-159 §6 governing principle).

# CommonMark code fence: 3+ backticks or tildes, up to 3 leading spaces of indent.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

# CommonMark thematic break: 3+ matching ``-``/``*``/``_``, optional inner spaces.
_THEMATIC_BREAK_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")


def _fence_marker(line: str) -> tuple[str, int] | None:
    """Return (fence_char, run_length) if ``line`` is a code-fence delimiter, else None."""
    m = _FENCE_RE.match(line)
    if not m:
        return None
    seq = m.group(1)
    return seq[0], len(seq)


def _is_fence_close(line: str, fence_char: str, fence_len: int) -> bool:
    """A closing fence: same char, length ≥ opening run, and NO info string (CommonMark)."""
    m = _FENCE_RE.match(line)
    if not m:
        return False
    seq = m.group(1)
    if seq[0] != fence_char or len(seq) < fence_len:
        return False
    return line[m.end() :].strip() == ""


def is_thematic_break(line: str) -> bool:
    return bool(_THEMATIC_BREAK_RE.match(line))


def is_blockquote(line: str) -> bool:
    return line.lstrip(" ").startswith(">")


def is_indented_code(line: str) -> bool:
    """A line indented ≥4 spaces (or a leading tab) — opaque at a unit boundary.

    Only meaningful at the START of a fresh unit: bullet/paragraph continuation lines
    are absorbed by their own branches and never reach this check, so a 4-space indent
    here is a standalone indented-code block (CommonMark), kept opaque.
    """
    if not line.strip():
        return False
    if line.startswith("\t"):
        return True
    return len(line) - len(line.lstrip(" ")) >= 4


def is_html_block_start(line: str) -> bool:
    return line.lstrip(" ").startswith("<")


def parse_entries(body_lines: list[str]) -> list[tuple[str, str]]:
    """Group body lines into (section, unit_text) units — STRUCTURE-AWARE.

    Genuine CONTENT units carry their owning ``## section`` (or "" for preamble) and
    are the ONLY units the classifier/dedup ever act on: bullets (plus indented
    continuation lines), table CONTENT rows, and contiguous paragraphs.

    Everything else is emitted with a special tag so reassembly preserves document
    shape AND so it is never classified/deduped/split:
      - ``__blank__``       — a blank line
      - ``__header__``      — an ATX ``#`` heading line
      - ``__passthrough__`` — an opaque structural/uncertain block kept byte-for-byte:
        a whole code fence (open→close inclusive), a thematic break, a table
        header+separator pair, a blockquote, an indented-code block, or a raw-HTML
        block gathered to its blank-line terminator (CommonMark HTML block type 6/7 —
        inner lines need NOT start with ``<``). Unterminated fences and an HTML block
        running to EOF keep their remainder opaque (keep-when-uncertain).
    """
    entries: list[tuple[str, str]] = []
    section = ""
    i = 0
    n = len(body_lines)
    while i < n:
        line = body_lines[i]
        stripped = line.strip()

        if not stripped:
            entries.append(("__blank__", ""))
            i += 1
            continue

        if stripped.startswith("#"):
            if stripped.startswith("## "):
                section = stripped
            entries.append(("__header__", line))
            i += 1
            continue

        # Code fence → the ENTIRE block (delimiters + body) is one opaque unit.
        fence = _fence_marker(line)
        if fence is not None:
            fence_char, fence_len = fence
            block = [line]
            i += 1
            while i < n:
                block.append(body_lines[i])
                closed = _is_fence_close(body_lines[i], fence_char, fence_len)
                i += 1
                if closed:
                    break
            # Unterminated fence falls through here with the remainder kept opaque.
            entries.append(("__passthrough__", "\n".join(block)))
            continue

        # Thematic break (``---``/``***``/``___``) — structural, never deduped.
        if is_thematic_break(line):
            entries.append(("__passthrough__", line))
            i += 1
            continue

        if is_table_row(line):
            # A header followed by a separator opens a real table: BOTH rows are
            # structural passthrough (a tagged header is never classified — M-TBL-HDR,
            # never orphan a separator). The contiguous CONTENT rows that follow are
            # genuine content (classified/dropped-in-place, but never deduped — H2).
            if i + 1 < n and is_table_separator(body_lines[i + 1]):
                entries.append(("__passthrough__", line))
                entries.append(("__passthrough__", body_lines[i + 1]))
                i += 2
                while (
                    i < n
                    and is_table_row(body_lines[i])
                    and not is_table_separator(body_lines[i])
                ):
                    entries.append((section, body_lines[i]))
                    i += 1
                continue
            # A pipe row not forming a header+separator table (e.g. a lone separator
            # or a malformed one-off row) → treat as a content row; plan_file's
            # is_table_separator guard still passes a bare separator through opaque.
            entries.append((section, line))
            i += 1
            continue

        # Keep-when-uncertain: blockquotes and indented code are opaque KEEP, gathered
        # by their own same-kind predicate (every line starts with ``>`` / is indented
        # ≥4) — that predicate IS correct for these two constructs.
        if is_blockquote(line) or is_indented_code(line):
            same = is_blockquote if is_blockquote(line) else is_indented_code
            block = [line]
            i += 1
            while i < n and body_lines[i].strip() and same(body_lines[i]):
                block.append(body_lines[i])
                i += 1
            entries.append(("__passthrough__", "\n".join(block)))
            continue

        # Raw-HTML block (CommonMark HTML block type 6/7): opaque KEEP from the start
        # line to its BLANK-LINE terminator (or EOF) — inner lines need NOT start with
        # ``<`` (a ``<div>`` / inner content / ``</div>`` block is ONE opaque unit). Every
        # inner line — INCLUDING any that begins with ``#`` (an HTML-comment ``# TODO``, a
        # CSS ``#id`` selector, an inner ``##``) — stays inside the opaque unit and is NEVER
        # re-classified/deduped/pruned/split. The gather has NO inner-content stop rule: a
        # same-kind ``startswith('<')`` predicate or a ``#``-guard would terminate at the
        # first such inner line and leak the block's remainder into the paragraph branch to
        # be classified/deduped/pruned — silent corruption of the operator's file. A block
        # running to EOF with no trailing blank keeps its remainder opaque
        # (keep-when-uncertain). Cross-section dedup safety (an HTML block that absorbs a
        # following ``## heading`` because there is no blank line between them) is handled
        # in plan_file's dedup layer, which resets the ``seen`` set on every opaque/header
        # boundary — NOT by stopping the gather here on inner content.
        if is_html_block_start(line):
            block = [line]
            i += 1
            while i < n and body_lines[i].strip():
                block.append(body_lines[i])
                i += 1
            entries.append(("__passthrough__", "\n".join(block)))
            continue

        if is_bullet(line):
            block = [line]
            i += 1
            # Absorb indented continuation lines belonging to this bullet.
            while (
                i < n
                and body_lines[i].strip()
                and body_lines[i].startswith((" ", "\t"))
            ):
                block.append(body_lines[i])
                i += 1
            entries.append((section, "\n".join(block)))
            continue

        # Paragraph: contiguous content lines, broken by any structural construct so a
        # following fence/break/table is never swallowed into a classifiable unit.
        block = [line]
        i += 1
        while i < n:
            nxt = body_lines[i]
            if (
                not nxt.strip()
                or nxt.strip().startswith("#")
                or is_bullet(nxt)
                or is_table_row(nxt)
                or is_thematic_break(nxt)
                or _fence_marker(nxt) is not None
                or is_blockquote(nxt)
                or is_html_block_start(nxt)
            ):
                break
            block.append(nxt)
            i += 1
        entries.append((section, "\n".join(block)))
    return entries


def is_table_separator(text: str) -> bool:
    """A markdown table header *separator* row like ``|---|---|`` — never an entry.

    L-DASH-CELL: tightened so *every* cell is a true GFM separator cell — optional
    leading/trailing colon around one or more dashes (``---``, ``:---``, ``---:``,
    ``:---:``). The previous loose ``[\\s:|-]+`` class accepted any mix of dashes,
    colons, pipes and spaces, so a bare-dash *content* row could slip through
    unclassified. A single-dash cell (``| - | - |``) is a valid GFM separator and
    is still treated as one (kept, structural) — that passthrough is benign.
    """
    s = text.strip()
    if not s.startswith("|"):
        return False
    cells = s.strip("|").split("|")
    return bool(cells) and all(re.fullmatch(r"\s*:?-+:?\s*", cell) for cell in cells)


# Strip a leading list/table prefix so a marker tag sitting in the ANCHORED leading
# position can be matched: bullet (``- ``/``* ``/``+ ``), ordered number (``1. ``),
# or the first table-cell pipe (``| ``).
_LEADING_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_LEADING_CELL_RE = re.compile(r"^\s*\|\s*")


def _anchor_zone(text: str) -> str:
    """Return the lowercased LEADING zone where a marker tag is *anchored* (H1).

    A marker classifies an entry ONLY when it sits in the single dedicated leading
    position: the first line with its bullet/number prefix removed, or the first
    cell of a table row. A marker merely *mentioned* in prose — or one that merely
    *ends* a line of prose — falls outside this zone and is ignored, so recall-worthy
    content is never self-destructively pruned.

    Trailing-zone anchoring was removed in cycle-2: a trailing tag pruned prose that
    happened to end in a marker token (M-TRAILING-PROSE), silently missed a trailing
    tag on a multi-line entry's first line (M-MULTILINE-TRAILING-MISS), and missed
    trailing punctuation (TGT-4). Leading-only is the single unambiguous convention
    (see decision-rule.md).
    """
    lines = text.strip().splitlines()
    first = lines[0] if lines else ""
    lead = _LEADING_PREFIX_RE.sub("", first)
    return _LEADING_CELL_RE.sub("", lead).strip().lower()


def classify(text: str, today: date) -> tuple[str, str]:
    """Apply the BP-159 §6 decision rule to one entry. Returns (action, reason).

    Markers are matched only in the anchored LEADING position (a leading tag after
    the bullet/number prefix or in the first table cell), never as a bare substring
    elsewhere in the prose nor at the trailing end (H1, leading-only).
    """
    lead = _anchor_zone(text)

    def anchored(marker: str) -> bool:
        return lead.startswith(marker)

    for marker in PRUNE_MARKERS:
        if anchored(marker):
            return "prune", f"tagged {marker} — superseded/contradicted/low-utility"

    # GFM strikethrough across the WHOLE entry content = struck-out / superseded.
    # M-STRIKE-PARTIAL: prune only when a single ``~~…~~`` span covers all of the
    # (prefix-stripped) content — an entry with live, un-struck text between two
    # spans (``~~old~~ but still relevant ~~Y~~``) is KEPT, not pruned.
    stripped = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", text.strip()).strip()
    if re.fullmatch(r"~~(?:(?!~~).)*~~", stripped, re.DOTALL):
        return "prune", "struck-out (~~...~~) — superseded"

    # TTL marker, anchored leading only.
    m = EXPIRY_RE.match(lead)
    if m:
        try:
            when = date.fromisoformat(m.group(1))
        except ValueError:
            when = None
        if when and when < today:
            return "prune", f"TTL expired on {m.group(1)}"

    for marker in ARCHIVE_MARKERS:
        if anchored(marker):
            return (
                "archive",
                f"tagged {marker} — stale-but-meaningful, archived to cold tier",
            )

    return "keep", ""


def normalize(text: str) -> str:
    """Whitespace-insensitive key for duplicate detection."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def _strip_leading_markers(body: str) -> str:
    """Drop any leading classification marker(s) from a pointer body (M3) so the
    one-line pointer reads clean (the ``_[archived …]_`` prefix already records it)."""
    changed = True
    while changed:
        changed = False
        for marker in PRUNE_MARKERS + ARCHIVE_MARKERS:
            if body.lower().startswith(marker):
                body = body[len(marker) :].lstrip()
                changed = True
    return body


def pointer_for(text: str, today: date, archive_relpath: str) -> str:
    """One-line hot-file pointer left where an archived entry used to be."""
    body = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", text.strip().splitlines()[0]).strip()
    body = _strip_leading_markers(body)
    if len(body) > POINTER_SUMMARY_CHARS:
        body = body[:POINTER_SUMMARY_CHARS].rstrip() + "…"
    return f"- _[archived {today.isoformat()}]_ {body} → {archive_relpath}"


def collapse_blanks(lines: list[str]) -> list[str]:
    """Collapse runs of >1 blank line into a single blank line."""
    out: list[str] = []
    for line in lines:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    # Trim trailing blanks.
    while out and not out[-1].strip():
        out.pop()
    return out


def plan_file(text: str, filename: str, cap: int, today: date) -> FilePlan:
    """Compute the compaction plan for one file's text. Pure — performs no I/O."""
    original_lines = len(text.splitlines())
    frontmatter, body_lines = split_frontmatter(text)
    units = parse_entries(body_lines)

    archive_relpath = f"{ARCHIVE_SUBDIR}/{Path(filename).stem}.archive.md"
    actions: list[EntryAction] = []
    archived_blocks: list[str] = []
    # Dedup is bounded by STRUCTURAL BOUNDARIES: the ``seen`` set collapses duplicate
    # content only within a contiguous run uninterrupted by a heading or opaque block.
    # The key still carries the owning ``## section`` so identical text under DIFFERENT
    # sections stays distinct, and ``seen`` is cleared on every ``__header__`` /
    # ``__passthrough__`` boundary below (the section-independent guard that closes the
    # cross-section-dedup HIGH even when an HTML block absorbs the next heading). A
    # file-global set would silently drop the second as a "duplicate" (M-XSEC).
    seen: set[tuple[str, str]] = set()
    out_body: list[str] = []

    for section, unit in units:
        # Structural / opaque units are copied through byte-for-byte: blank lines,
        # headers, and every __passthrough__ block (code fences, thematic breaks,
        # table header+separator pairs, blockquotes, indented code, raw HTML). They
        # are NEVER classified, deduped, or split — the keep-when-uncertain backstop.
        #
        # A __header__ or __passthrough__ is a STRUCTURAL BOUNDARY: it RESETS the dedup
        # ``seen`` set so two identical content entries on opposite sides of it are BOTH
        # kept — a heading or opaque block between twins means they are not a safe dedup
        # pair (keep-when-uncertain). This is the section-independent fix for the
        # cross-section-dedup HIGH: even when an HTML/comment block absorbs a following
        # ``## heading`` (so ``section`` does not advance), the passthrough boundary still
        # clears ``seen``, so the next run's first occurrence is kept rather than dropped
        # as a phantom same-section duplicate. ``__blank__`` is ordinary spacing between
        # bullets and does NOT reset — genuine adjacent duplicates separated only by blank
        # lines must still collapse keep-first.
        if section in ("__header__", "__passthrough__"):
            seen.clear()
            out_body.append(unit)
            continue
        if section == "__blank__":
            out_body.append(unit)
            continue

        # Never re-process a pointer we left on a prior run (idempotency) or a bare
        # table separator that reached us as a content row (structural, not content).
        if is_pointer(unit) or is_table_separator(unit):
            out_body.append(unit)
            continue

        action, reason = classify(unit, today)

        if action == "prune":
            actions.append(EntryAction(unit, section, "prune", reason))
            continue

        if action == "archive":
            actions.append(EntryAction(unit, section, "archive", reason))
            sec_label = section.lstrip("# ").strip() or "(preamble)"
            archived_blocks.append(
                f"## [{today.isoformat()}] archived from {filename} — {sec_label}\n\n{unit}\n"
            )
            # H3: a table content row must NEVER yield an inline bullet pointer.
            # pointer_for() emits a ``- _[archived …]_ …`` bullet line; injecting
            # that mid-table would break the table AND leak the row's pipes/marker
            # into the hot file (the leading-strip in pointer_for can't clean an
            # interior ``|``). Drop the row in place so the table stays well-formed
            # — the full row content is preserved in the cold archive block above.
            # Non-table entries still leave the dated one-line pointer.
            if not is_table_row(unit):
                out_body.append(pointer_for(unit, today, archive_relpath))
            continue

        # keep — table rows (header/separator/content) are NEVER deduped: a file-
        # global seen set would silently drop the header + separator of a second
        # same-schema table and corrupt it (H2). Markers still prune/archive a
        # tagged content row above; structural rows simply pass through.
        if is_table_row(unit):
            actions.append(EntryAction(unit, section, "keep", ""))
            out_body.append(unit)
            continue

        # keep — but drop exact duplicates within the SAME section (BP-159 §7 dedup),
        # keeping the first. Scoping by section preserves identical-but-distinct entries
        # that live under different ``## section`` headers.
        key = (section, normalize(unit))
        if key in seen:
            actions.append(
                EntryAction(unit, section, "dedup", "duplicate within the same section")
            )
            continue
        seen.add(key)
        actions.append(EntryAction(unit, section, "keep", ""))
        out_body.append(unit)

    body = collapse_blanks(out_body)
    new_text = "\n".join(frontmatter + body)
    if new_text and not new_text.endswith("\n"):
        new_text += "\n"
    # Re-emit untouched content with the file's original line ending (L-CRLF). Internal
    # text is ending-stripped, so it holds only LF separators — a single replace yields
    # a uniform, never-mixed file.
    newline = detect_newline(text)
    if newline != "\n":
        new_text = new_text.replace("\n", newline)

    return FilePlan(
        filename=filename,
        cap=cap,
        original_lines=original_lines,
        new_text=new_text,
        archived_blocks=archived_blocks,
        actions=actions,
    )


def plan_section_cap(
    text: str, filename: str, contract: Contract, today: date
) -> FilePlan:
    """Section-cap fix (B3 PERSONA): keep the last ``section_keep_last`` table
    CONTENT rows under the symbolic ``section_anchor`` heading and relocate the
    older ones losslessly to the cold archive, leaving one pointer below the table.

    Symbolic section anchor only — NEVER line numbers. Does NOT whole-file rotate;
    only the named section is capped. Pure — performs no I/O. The relocated rows go
    to ``archived_blocks`` (apply_plan proves conservation over hot + archive).
    """
    anchor = contract.section_anchor
    keep = contract.section_keep_last
    original_lines = len(text.splitlines())
    frontmatter, body_lines = split_frontmatter(text)
    units = parse_entries(body_lines)
    archive_relpath = f"{ARCHIVE_SUBDIR}/{Path(filename).stem}.archive.md"

    # Genuine table CONTENT rows under the anchored section, oldest first (document
    # order). Header/separator/pointer rows are structural and are never moved.
    row_idxs = [
        i
        for i, (section, unit) in enumerate(units)
        if section == anchor
        and is_table_row(unit)
        and not is_table_separator(unit)
        and not is_pointer(unit)
    ]

    actions: list[EntryAction] = []
    archived_blocks: list[str] = []
    relocate: set[int] = set()
    if keep is not None and len(row_idxs) > keep:
        relocate = set(row_idxs[: len(row_idxs) - keep])
        sec_label = anchor.lstrip("# ").strip()
        moved_rows = [units[i][1] for i in sorted(relocate)]
        archived_blocks.append(
            f"## [{today.isoformat()}] archived from {filename} — {sec_label}\n\n"
            + "\n".join(moved_rows)
            + "\n"
        )
        for i in sorted(relocate):
            actions.append(
                EntryAction(
                    units[i][1],
                    anchor,
                    "archive",
                    f"section-cap: older than last {keep}",
                )
            )

    # Reassemble: drop relocated rows in place; after the LAST kept row of the
    # anchored section leave ONE one-line pointer to the cold archive (a table
    # content row never gets an inline bullet pointer — H3 — so it follows the table).
    last_kept = max((i for i in row_idxs if i not in relocate), default=-1)
    out_body: list[str] = []
    for i, (_section, unit) in enumerate(units):
        if i in relocate:
            continue
        out_body.append(unit)
        if relocate and i == last_kept:
            sec_label = anchor.lstrip("# ").strip()
            out_body.append(
                f"- _[archived {today.isoformat()}]_ {len(relocate)} older "
                f"{sec_label} entr(ies) → {archive_relpath}"
            )

    body = collapse_blanks(out_body)
    new_text = "\n".join(frontmatter + body)
    if new_text and not new_text.endswith("\n"):
        new_text += "\n"
    newline = detect_newline(text)
    if newline != "\n":
        new_text = new_text.replace("\n", newline)

    return FilePlan(
        filename=filename,
        cap=contract.cap_lines,
        original_lines=original_lines,
        new_text=new_text,
        archived_blocks=archived_blocks,
        actions=actions,
    )


def report_check_only(filename: str, text: str, contract: Contract) -> bool:
    """Cap-CHECK for identity classes (B3 CREED/BOND). Never mutates, never
    relocates. Returns True if over cap (line OR KB) so the caller HALTs non-zero —
    identity directives are relocated by hand, never auto-moved.
    """
    n_lines = len(text.splitlines())
    n_kb = len(text.encode("utf-8")) / 1024
    over = n_lines > contract.cap_lines or n_kb > contract.cap_kb
    print(f"\n{filename}")
    print(
        f"  {n_lines}/{contract.cap_lines} lines · {n_kb:.1f}/{contract.cap_kb} KB "
        f"({contract.klass}, check-only)"
    )
    if over:
        print(
            "  OVER CAP — identity file; HALT + report. Identity directives are NOT "
            "auto-relocated — trim/relocate by hand (B3)."
        )
    else:
        print("  within cap ✓")
    return over


def _default_contract() -> Contract:
    """Contract for a file outside the sanctum registry: line-only compact (the
    historical single-file behavior; --cap overrides cap_lines)."""
    return Contract(CAP_LINES, 25.0, "lore", rotatable=True)


def resolve_targets(path: Path) -> list[tuple[Path, Contract]]:
    """Resolve the CLI path to a list of (file, Contract) targets."""
    if path.is_file():
        return [(path, SANCTUM_CONTRACTS.get(path.name) or _default_contract())]
    if path.is_dir():
        targets: list[tuple[Path, Contract]] = []
        for name, contract in SANCTUM_CONTRACTS.items():
            candidate = path / name
            if candidate.is_file():
                targets.append((candidate, contract))
        return targets
    return []


def print_plan(plan: FilePlan) -> None:
    pct = round(100 * plan.original_lines / plan.cap)
    status = (
        "OVER CAP"
        if plan.over_cap
        else ("over trigger" if plan.over_trigger else "under trigger")
    )
    print(f"\n{plan.filename}")
    print(
        f"  {plan.original_lines}/{plan.cap} lines ({pct}% — {status}; "
        f"compaction trigger {plan.trigger} = {int(COMPACT_AT * 100)}%)"
    )
    if not plan.has_changes:
        if plan.over_cap:
            print(
                f"  actions: none available mechanically — STILL {plan.residual_over_cap} "
                f"over cap; needs a manual/LLM semantic-summarization pass "
                f"(no auto-truncation)"
            )
        else:
            print("  actions: none (clean, no-op)")
        return
    c = plan.counts
    print(
        f"  actions: prune {c['prune']} · archive {c['archive']} · dedup {c['dedup']}"
    )
    for a in plan.actions:
        if a.action == "keep":
            continue
        first = a.text.strip().splitlines()[0]
        if len(first) > 70:
            first = first[:70].rstrip() + "…"
        print(f"    [{a.action}] {first}   ({a.reason})")
    print(f"  projected: {plan.projected_lines} lines", end="")
    if plan.residual_over_cap:
        print(
            f"  — STILL {plan.residual_over_cap} over cap; "
            f"needs a manual/LLM semantic-summarization pass (no auto-truncation)"
        )
    else:
        print("  (≤ cap ✓)")


def write_backup(path: Path, today: date) -> Path:
    """Timestamped sidecar backup before any mutation.

    Two distinct applies on the same day must not collide (M1): a same-day backup
    already on disk is never overwritten — a ``.N`` counter is appended so every
    apply preserves its own pre-mutation original.
    """
    stamp = today.isoformat()
    backup = path.parent / f"{path.name}.{stamp}.bak"
    n = 1
    while backup.exists():
        backup = path.parent / f"{path.name}.{stamp}.{n}.bak"
        n += 1
    # Byte-faithful copy (read_bytes/write_bytes) so the pre-mutation original is
    # preserved exactly — including its CRLF/CR line endings (L-CRLF).
    backup.write_bytes(path.read_bytes())
    return backup


def push_to_qdrant(blocks: list[str], group_id: str, agent_id: str) -> bool:
    """Best-effort push of archived blocks to the Qdrant cold tier (BP-165 B.1).

    Reuses the runtime ``memory.storage`` import path used by bootstrap/sanctum-init.
    Gracefully degrades to a no-op when the runtime or Qdrant is unavailable — the
    local archive file is always the source of truth; Qdrant is an additive tier.
    """
    install_src = Path.home() / ".ai-memory" / "src"
    if str(install_src) not in sys.path:
        sys.path.insert(0, str(install_src))
    try:
        from memory.storage import MemoryStorage
    except Exception as exc:  # runtime not installed / import error
        print(f"  qdrant: skipped — memory.storage unavailable ({exc})")
        return False
    try:
        storage = MemoryStorage()
        for block in blocks:
            storage.store_agent_memory(
                content=block,
                memory_type="agent_memory",
                group_id=group_id,
                agent_id=agent_id,
            )
        print(f"  qdrant: pushed {len(blocks)} archived block(s) to cold tier")
        return True
    except Exception as exc:  # Qdrant down, etc.
        print(f"  qdrant: skipped — push failed ({exc})")
        return False


def _virtual_archive_text(archive_path: Path, blocks: list[str]) -> tuple[str, int]:
    """Return (would-be cold-archive text, n_appended) WITHOUT writing.

    Mirrors the same-string idempotent skip used at commit time so the proven
    after-state is byte-for-byte what gets written. A block already present in the
    existing archive (same-day crash-rerun) is skipped — never duplicated, never
    lost (L3 / TGT-2: a cross-day rerun re-adds under a new dated header by design).
    """
    existing = archive_path.read_text(encoding="utf-8") if archive_path.exists() else ""
    new_text = existing
    appended = 0
    for block in blocks:
        if block in existing:
            continue
        new_text += block + "\n"
        appended += 1
    return new_text, appended


def prove_conservation(
    path: Path, plan: FilePlan, archive_path: Path, new_archive_text: str
) -> None:
    """Shared 0-lost proof over hot + cold-archive, BEFORE any write (B2).

    Two invariants, both via the shared ``conservation`` module (no local copy),
    computed on the VIRTUAL after-state so a failure leaves every original
    byte-identical (prove-then-commit):

    1. No HOT content lost — every content line in the hot file that is NOT
       intentionally removed (prune deletes a superseded/contradicted/expired
       entry; dedup drops an exact in-section duplicate) must survive in the
       would-be hot file OR the would-be cold archive. A relocation that silently
       drops an entry → its lines are in the baseline but in neither after-text →
       ``assert_no_content_loss`` raises (multiset, so a dropped one-of-two
       duplicate is caught).
    2. Cold archive never shrinks — it is append-only; every pre-existing archive
       line is still present after.

    The before-baseline is split (hot vs archive) rather than unioned so a
    legitimate crash-rerun — where an entry already archived is re-introduced into
    the hot file and the fix collapses the hot+archive duplicate back to a single
    archived copy — is NOT mis-flagged as a multiset count loss.
    """
    removed: Counter[str] = Counter()
    for a in plan.actions:
        if a.action in ("prune", "dedup"):
            for line in a.text.splitlines():
                s = line.strip()
                if s:
                    removed[s] += 1

    before_hot = conservation.build_content_set([path], raise_on_error=True)
    after_union = conservation.build_content_set_from_texts(
        [plan.new_text, new_archive_text]
    )
    conservation.assert_no_content_loss(before_hot - removed, after_union)

    before_archive = conservation.build_content_set([archive_path])
    after_archive = conservation.build_content_set_from_texts([new_archive_text])
    conservation.assert_no_content_loss(before_archive, after_archive)


def apply_plan(
    path: Path, plan: FilePlan, today: date, qdrant: bool, group_id: str, agent_id: str
) -> bool:
    """Mutate the file per its plan: prove conservation, then backup + write.

    Returns True on success (or clean no-op), False if the conservation proof
    failed (in which case NOTHING was written — every original is byte-identical).
    """
    if not plan.has_changes:
        if plan.over_cap:
            print(
                f"  {plan.filename}: WARNING — {plan.residual_over_cap} over cap with no "
                f"mechanical actions available; manual/LLM semantic summarization required "
                f"(not auto-truncated)"
            )
        else:
            print(f"  {plan.filename}: no changes — skipped")
        return True

    archive_path = path.parent / ARCHIVE_SUBDIR / f"{path.stem}.archive.md"
    new_archive_text, appended = _virtual_archive_text(
        archive_path, plan.archived_blocks
    )

    # Prove-then-commit: prove the 0-lost property on the VIRTUAL after-state before
    # touching disk, so a failed proof leaves the hot file AND the archive untouched.
    try:
        prove_conservation(path, plan, archive_path, new_archive_text)
    except AssertionError as exc:
        print(
            f"  {plan.filename}: ERROR conservation FAILED — {exc}; "
            f"NOTHING written (original byte-identical).",
            file=sys.stderr,
        )
        return False

    backup = write_backup(path, today)
    print(f"  {plan.filename}: backed up → {backup.name}")

    if plan.archived_blocks:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        # Write the full proven archive text (existing + appended), so the on-disk
        # archive is exactly the state the proof covered.
        archive_path.write_text(new_archive_text, encoding="utf-8")
        print(f"  {plan.filename}: archived {appended} entr(ies) → {archive_path.name}")
        if qdrant:
            push_to_qdrant(plan.archived_blocks, group_id, agent_id)

    # write_bytes (not write_text) so the line endings already baked into new_text are
    # emitted verbatim with no os.linesep retranslation (L-CRLF).
    path.write_bytes(plan.new_text.encode("utf-8"))
    print(
        f"  {plan.filename}: rewritten ({plan.original_lines} → {plan.projected_lines} lines)"
    )
    print(f"  {plan.filename}: conservation — 0 lines lost (hot + archive) ✓")
    if plan.residual_over_cap:
        print(
            f"  {plan.filename}: WARNING — still {plan.residual_over_cap} over cap; "
            f"manual/LLM semantic summarization required (not auto-truncated)"
        )
    return True


def _invocation() -> str:
    return f"python3 {Path(__file__).resolve()}"


def _count_section_rows(text: str, anchor: str) -> int:
    """Count genuine table CONTENT rows under the anchored section (B5/section-cap)."""
    _fm, body_lines = split_frontmatter(text)
    return sum(
        1
        for section, unit in parse_entries(body_lines)
        if section == anchor
        and is_table_row(unit)
        and not is_table_separator(unit)
        and not is_pointer(unit)
    )


def run_check(path: Path) -> int:
    """Session-close cap gate for sanctum classes (B5). Read-only: report every
    governed sanctum file over its cap with a remedy and exit non-zero on any
    breach so closeout cannot complete over a breach. NEVER mutates.

    Mirrors the aim-tracking-rotate --check contract (SYSTEM FAILURE block per
    breach, non-zero exit) so the session-close gate covers BOTH the oversight
    classes (aim-tracking-rotate) AND the sanctum classes (here).
    """
    targets = resolve_targets(path)
    if not targets:
        print(f"aim-lore-hygiene --check: no governed sanctum files at {path}.")
        return 0
    breaches: list[str] = []
    for file_path, contract in targets:
        text = read_preserving_newlines(file_path)
        strategy = strategy_for(contract)
        if strategy == "section-cap":
            rows = _count_section_rows(text, contract.section_anchor)
            if rows <= contract.section_keep_last:
                continue
            size = f"{rows} '{contract.section_anchor}' entries"
            cap = f"last {contract.section_keep_last} ({contract.klass})"
            remedy = (
                f"{_invocation()} {file_path} --apply  "
                "(section-cap relocates older entries, conservation-proven)"
            )
        else:
            n_lines = len(text.splitlines())
            n_kb = len(text.encode("utf-8")) / 1024
            if not (n_lines > contract.cap_lines or n_kb > contract.cap_kb):
                continue
            size = f"{n_lines} lines / {n_kb:.1f} KB"
            cap = (
                f"{contract.cap_lines} lines / {contract.cap_kb} KB ({contract.klass})"
            )
            if strategy == "compact":
                # A2: the compact-class file-SIZE cap is REPORTING-ONLY — the full
                # file stays on disk at full size and lore-hygiene file rotation is
                # tag-driven (Part B), NOT a session-close blocker. Print a WARNING
                # so growth stays visible, but do NOT add a breach or exit non-zero
                # (an untagged over-size LORE would otherwise block closeout with no
                # remedy, since --apply is a no-op on it).
                print(
                    f"  WARNING — {file_path.name}: {size} over cap {cap}; "
                    "reporting-only (tag-driven compaction is not a closeout "
                    f"blocker — A2). Optional: {_invocation()} {file_path} --apply"
                )
                continue
            # check-only (CREED/BOND): identity files HALT on over-cap (BLOCKING).
            remedy = (
                f"trim {file_path.name} by hand — identity class "
                f"'{contract.klass}' is never auto-relocated (B3)"
            )
        breaches.append(
            "\n".join(
                [
                    "  ┌─ SYSTEM FAILURE: sanctum file over cap",
                    f"  │  file:   {file_path.name}",
                    f"  │  size:   {size}",
                    f"  │  cap:    {cap}",
                    f"  │  remedy: {remedy}",
                    "  └─",
                ]
            )
        )
    if breaches:
        print(
            f"aim-lore-hygiene --check: FAIL — {len(breaches)} sanctum file(s) over cap.\n",
            file=sys.stderr,
        )
        print("\n\n".join(breaches), file=sys.stderr)
        print(
            "\nCloseout is BLOCKED until every governed sanctum file is at or under cap.",
            file=sys.stderr,
        )
        return 1
    print(
        f"aim-lore-hygiene --check: PASS — {len(targets)} sanctum file(s) within cap."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanctum lore-file hygiene: cap enforcement, anchored compaction, prune-vs-archive.",
    )
    parser.add_argument(
        "path", help="Sanctum directory (scans LORE.md/MEMORY.md) or a single file."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Mutate files. Without this flag the script is read-only (dry-run DEFAULT).",
    )
    parser.add_argument(
        "--cap",
        type=int,
        default=None,
        help=f"Override the line cap (default {CAP_LINES}; per-file caps apply when scanning a dir).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Session-close cap gate: read-only, exit non-zero on any over-cap "
        "governed sanctum file (CREED/PERSONA/LORE/BOND/MEMORY). Never mutates.",
    )
    parser.add_argument(
        "--qdrant",
        action="store_true",
        help="On --apply, also push archived entries to the Qdrant cold tier (best-effort, opt-in).",
    )
    parser.add_argument(
        "--group-id",
        default=None,
        help="Project scope (group_id) for the Qdrant push. Required with --qdrant.",
    )
    parser.add_argument(
        "--agent-id", default="parzival", help="Agent id for the Qdrant push."
    )
    args = parser.parse_args()

    if args.cap is not None and args.cap <= 0:
        parser.error(f"--cap must be a positive integer (got {args.cap}).")
    if args.check and args.apply:
        parser.error("--check is read-only and cannot be combined with --apply.")
    if args.qdrant and not args.apply:
        parser.error("--qdrant requires --apply (dry-run never writes anywhere).")
    if args.qdrant and not args.group_id:
        parser.error(
            "--qdrant requires --group-id (project scope is required-explicit, W-09)."
        )

    root = Path(args.path).resolve()

    # B5 session-close gate: read-only breach check across all sanctum classes.
    if args.check:
        return run_check(root)

    targets = resolve_targets(root)
    if not targets:
        print(f"No lore files found at {root} (expected a sanctum dir or a file).")
        return 1

    today = date.today()
    mode = "APPLY" if args.apply else "DRY-RUN (read-only — no files will be changed)"
    print(f"aim-lore-hygiene · {mode}")
    print(f"target: {root}")

    plans: list[tuple[Path, FilePlan]] = []
    halt = False  # an over-cap check-only file or a failed conservation proof
    for file_path, contract in targets:
        text = read_preserving_newlines(file_path)
        strategy = strategy_for(contract)
        if strategy == "check-only":
            if report_check_only(file_path.name, text, contract):
                halt = True
            continue
        if strategy == "section-cap":
            plan = plan_section_cap(text, file_path.name, contract, today)
        else:  # compact
            cap = args.cap if args.cap is not None else contract.cap_lines
            plan = plan_file(text, file_path.name, cap, today)
        plans.append((file_path, plan))
        print_plan(plan)

    if args.apply:
        print("\napplying:")
        for file_path, plan in plans:
            ok = apply_plan(
                file_path, plan, today, args.qdrant, args.group_id or "", args.agent_id
            )
            if not ok:
                halt = True
    else:
        actionable = sum(1 for _, p in plans if p.has_changes)
        print(
            f"\n{actionable} file(s) have proposed changes. Re-run with --apply to write."
        )

    return 1 if halt else 0


if __name__ == "__main__":
    sys.exit(main())
