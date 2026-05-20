#!/usr/bin/env python3
"""
tracking_freshness.py — aim-tracking-freshness backing script.

Scans oversight/bugs/BUG-*.md and oversight/tech-debt/TECH-DEBT-*.md,
classifies each record as open or closed from its authoritative **Status**
header, and either reports divergences from the current INDEX (--check) or
regenerates both INDEX files and then reports (--write).

The **Status** header in each record file is authoritative.
Status is NEVER inferred from filename or INDEX section placement.

Contract source of truth: _ai-memory/pov/templates/bug-report.template.md
and tech-debt-report.template.md (slug-optional filenames; see SKILL.md §Contract).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------

# A.1 — slug is optional: BUG-001.md and BUG-001-slug.md both match.
BUG_RECORD_RE = re.compile(r"^BUG-(\d+)(?:-[a-z0-9-]+)?\.md$", re.IGNORECASE)
TD_RECORD_RE = re.compile(r"^TECH-DEBT-(\d+)(?:-[a-z0-9-]+)?\.md$", re.IGNORECASE)

# Closed-class keyword sets — grounded on template contract (A.2).
#
# Bug canonical (from bug-report.template.md status workflow):
#   Fixed, Verified, Closed
# Tolerated legacy / extended forms confirmed in the live oversight tree:
#   RESOLVED, NOT A BUG, NOT-A-BUG, DUPLICATE, RECLASSIFIED,
#   FIX APPLIED, FIX-APPLIED
BUGS_CLOSED_TOKENS: list[str] = [
    "FIXED",
    "VERIFIED",
    "CLOSED",
    "RESOLVED",
    "NOT A BUG",
    "NOT-A-BUG",
    "DUPLICATE",
    "RECLASSIFIED",
    "FIX APPLIED",
    "FIX-APPLIED",
]

# TD canonical: RESOLVED, CLOSED, WONT FIX, WON'T FIX
# Tolerated legacy: IMPLEMENTED, FIXED
TD_CLOSED_TOKENS: list[str] = [
    "RESOLVED",
    "CLOSED",
    "WONT FIX",
    "WON'T FIX",
    "IMPLEMENTED",
    "FIXED",
]

# Severity display order for INDEX grouping
_SEV_PRIORITY: dict[str, int] = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
}

# Regex patterns for extracting fields from record file text
#
# Three colon-format variants confirmed in live oversight tree (PM #297):
#   **Status**: value   — colon outside bold (most common)
#   **Status:** value   — colon inside bold (10 files, e.g. BUG-044, TECH-DEBT-089)
# Pattern: \*\*Status:?\*\*:?\s*(.+) matches both; the two :? slots cover each position.
_STATUS_COLON_RE = re.compile(r"^\*\*Status:?\*\*:?\s*(.+)$", re.MULTILINE)
_STATUS_TABLE_RE = re.compile(r"^\|\s*\*\*Status\*\*\s*\|\s*(.+?)\s*\|", re.MULTILINE)

# Severity: same colon-outside / colon-inside dual pattern as Status.
# **Severity**: value  or  **Severity:** value
_SEV_COLON_RE = re.compile(
    r"^\*\*Severity:?\*\*:?\s*(.+)$", re.MULTILINE | re.IGNORECASE
)
_SEV_TABLE_RE = re.compile(
    r"^\|\s*\*\*Severity\*\*\s*\|\s*(.+?)\s*\|", re.MULTILINE | re.IGNORECASE
)

# Severity alias map: non-standard tokens found in older bug files.
_SEV_ALIASES: dict[str, str] = {
    "MAJOR": "HIGH",
    "MINOR": "LOW",
    "BLOCKER": "CRITICAL",
}
_SEV_KNOWN: frozenset[str] = frozenset(["CRITICAL", "HIGH", "MEDIUM", "LOW"])

# Title: explicit **Title**: field (used by records with generic headings, e.g. BUG-047 group).
_TITLE_FIELD_RE = re.compile(r"^\*\*Title:?\*\*:?\s*(.+)$", re.MULTILINE)

# H1 or H2 headings; companion regex strips the ID prefix.
# ID prefix formats confirmed in live tree:
#   BUG-NNN: Title       (colon separator)
#   BUG-NNN — Title      (U+2014 em-dash, newer bugs BUG-281+)
#   BUG-NNN Title        (space only, e.g. BUG-004 Root Cause Analysis)
#   TECH-DEBT-NNN: Title (all TD files)
# The character class [:\s—]+ covers all separators after the numeric ID.
_H_RE = re.compile(r"^#{1,2}\s+(.+)$", re.MULTILINE)
_ID_PREFIX_RE = re.compile(r"^(?:BUG|TECH-DEBT)-\d+[:\s—]+", re.IGNORECASE)

# Generic headings that carry no useful title; fall back to de-slugify when matched.
_GENERIC_HEADING_RE = re.compile(
    r"^(?:bug\s+report|technical\s+debt\s+item|root\s+cause\s+analysis|investigation\s+report)$",
    re.IGNORECASE,
)

_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FFFF☀-➿⌀-⏿️‍]")
_BOLD_RE = re.compile(r"\*+")

# INDEX section markers for divergence detection
_OPEN_SECTION_RE = re.compile(r"^##\s+Open", re.MULTILINE | re.IGNORECASE)
_CLOSED_SECTION_RE = re.compile(r"^##\s+Closed", re.MULTILINE | re.IGNORECASE)

# Evidence token patterns for --verify-code-state (F-1)
_SHA_EVIDENCE_RE = re.compile(r"\b([0-9a-f]{7,40})\b")
_PR_REF_EVIDENCE_RE = re.compile(r"#(\d{1,4})\b")
_FILE_PATH_EVIDENCE_RE = re.compile(
    r"[a-zA-Z0-9_][a-zA-Z0-9_.-]*/[a-zA-Z0-9/_.-]+\.[a-zA-Z0-9]{1,5}"
)

# Decision-log DEC ID patterns for F-2
_DEC_RANGE_RE = re.compile(r"DEC-PM(\d+)-D(\d+)\.\.D(\d+)")
_DEC_INDIVIDUAL_RE = re.compile(r"DEC-PM(\d+)-D(\d+)")
_DEC_BODY_HEADING_RE = re.compile(r"^### (DEC-PM\d+-D\d+)", re.MULTILINE)
_DECISION_LOG_HR_RE = re.compile(r"^---$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Record data class
# ---------------------------------------------------------------------------


class Record:
    """Parsed representation of a single bug or TD record file."""

    __slots__ = (
        "filename",
        "is_closed",
        "kind",
        "numeric_id",
        "raw_status",
        "sev",
        "title",
    )

    def __init__(
        self,
        filename: str,
        numeric_id: str,
        kind: str,
        raw_status: str,
        is_closed: bool,
        sev: str = "",
        title: str = "",
    ) -> None:
        self.filename = filename
        self.numeric_id = numeric_id
        self.kind = kind  # "bug" | "td"
        self.raw_status = raw_status  # verbatim from file (may be empty)
        self.is_closed = is_closed
        self.sev = sev  # e.g. "CRITICAL", "HIGH", "MEDIUM", "LOW", ""
        self.title = title  # display title (H1 with ID prefix stripped)


# ---------------------------------------------------------------------------
# Status / severity parsing helpers
# ---------------------------------------------------------------------------


def extract_raw_status(text: str) -> str | None:
    """Return raw Status value from record file text.

    Three formats are handled (all confirmed in the live oversight tree):

    1. ``**Status**: value``  — colon outside bold (most common)
    2. ``**Status:** value``  — colon inside bold (10 files)
    3. ``| **Status** | value |`` — table-row format (54 files)

    Colon formats (1 & 2) are tried first via a single regex; falls back
    to the table-row format.  Returns None when none of the three is found.
    """
    m = _STATUS_COLON_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _STATUS_TABLE_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def normalize_status(raw: str) -> str:
    """Strip emoji and markdown bold markers, then uppercase."""
    text = _BOLD_RE.sub("", raw)
    text = _EMOJI_RE.sub("", text)
    return text.strip().upper()


def classify_status(raw: str, kind: str) -> bool:
    """Return True (is_closed) if the status STARTS WITH a closed-class token.

    Uses leading-token matching, not substring-anywhere matching.  A
    closed-class token counts only when it appears at the very beginning of the
    normalized status string, followed by a word boundary.

    This prevents false CLOSED classifications for statuses such as::

        REOPENED (PM #295) — Previously: FIXED v2.4.0; regression …

    where ``FIXED`` appears only in a historical clause.  The operative word
    ``REOPENED`` is at the leading position → the record remains open.

    Multi-word closed tokens (``NOT A BUG``, ``FIX APPLIED``) must also appear
    at the leading position to match.

    Closed-class tokens differ by record type:
    - bugs: FIXED, VERIFIED, CLOSED, RESOLVED, NOT A BUG, NOT-A-BUG,
            DUPLICATE, RECLASSIFIED, FIX APPLIED, FIX-APPLIED
    - td:   RESOLVED, CLOSED, WONT FIX, WON'T FIX, IMPLEMENTED, FIXED
    """
    normalized = normalize_status(raw)
    tokens = BUGS_CLOSED_TOKENS if kind == "bug" else TD_CLOSED_TOKENS
    return any(re.match(rf"^{re.escape(tok)}\b", normalized) for tok in tokens)


def _normalize_sev_raw(raw: str) -> str:
    """Normalize a raw severity string to a bare CRITICAL/HIGH/MEDIUM/LOW token.

    Strips markdown bold markers, uppercases the result, then takes the leading
    run of ASCII letters.  Non-severity values (``N/A``, ``Closed``, template
    placeholders, etc.) return an empty string.

    Examples:
        ``HIGH (install-blocking)``  →  ``HIGH``
        ``**HIGH** (escalated…)``    →  ``HIGH``
        ``Minor``                    →  ``LOW``  (alias)
        ``N/A (closed)``             →  ``""``
    """
    cleaned = re.sub(r"\*+", "", raw).strip().upper()
    m = re.match(r"^([A-Z]+)", cleaned)
    if not m:
        return ""
    token = _SEV_ALIASES.get(m.group(1), m.group(1))
    return token if token in _SEV_KNOWN else ""


def extract_severity(text: str) -> str:
    """Return normalized severity string (CRITICAL/HIGH/MEDIUM/LOW), or empty string.

    Handles all severity field formats found in the live oversight tree:
    - ``**Severity**: HIGH``         — colon outside bold
    - ``**Severity:** High``         — colon inside bold (e.g. BUG-044)
    - ``| **Severity** | HIGH |``    — table-row format
    - Parenthetical noise stripped; aliases (Major→HIGH, Minor→LOW) applied.
    """
    m = _SEV_COLON_RE.search(text)
    if m:
        return _normalize_sev_raw(m.group(1).strip())
    m = _SEV_TABLE_RE.search(text)
    if m:
        return _normalize_sev_raw(m.group(1).strip())
    return ""


def _de_slugify(filename: str) -> str:
    """Convert a slug filename to a readable title (last-resort fallback).

    Returns the slug portion of the filename as a title-cased phrase, or an
    empty string when the filename has no slug (e.g. ``BUG-001.md``).  An
    empty return signals that ``extract_title`` should not echo the bare ID.

    Examples:
        ``BUG-047-installer-fails-with-spaces-in-path.md``
                 → ``Installer Fails With Spaces In Path``
        ``BUG-001.md``  → ``""``  (no slug to de-slugify)
    """
    stem = Path(filename).stem
    # Strip the ID prefix including its trailing hyphen if present; the
    # (?:-|$) alternate matches end-of-string for slug-less stems so the
    # entire stem is consumed and cleaned becomes "".
    cleaned = re.sub(r"^(?:BUG|TECH-DEBT)-\d+(?:-|$)", "", stem, flags=re.IGNORECASE)
    return cleaned.replace("-", " ").title()


def extract_title(text: str, filename: str) -> str:
    """Extract display title from record text.

    Priority:
    1. ``**Title**:`` / ``**Title:**`` field (used by records with generic headings
       such as the BUG-047..056 group that use ``# Bug Report`` as H1).
    2. H1 or H2 heading with the BUG-NNN / TECH-DEBT-NNN prefix stripped.
       Headings that resolve to noise tokens (``Bug Report``,
       ``Root Cause Analysis``, ``Investigation Report``) are skipped.
    3. De-slugified filename (``BUG-047-installer-fails-…`` → readable words).
       Returns empty string for slug-less files (``BUG-001.md``) to avoid
       echoing the bare ID as a title.
    """
    # 1. Explicit **Title**: field
    m = _TITLE_FIELD_RE.search(text)
    if m:
        raw = m.group(1).strip()
        if raw:
            return raw

    # 2. H1 or H2 heading
    m = _H_RE.search(text)
    if m:
        heading = m.group(1).strip()
        stripped = _ID_PREFIX_RE.sub("", heading).strip()
        if stripped and not _GENERIC_HEADING_RE.match(stripped):
            return stripped

    # 3. De-slugify filename as last resort (returns "" for slug-less filenames)
    return _de_slugify(filename)


# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------


def find_records(
    dirpath: Path,
    pattern_re: re.Pattern,
    kind: str,
) -> tuple[list[str], list[tuple[str, str]], set[str]]:
    """Enumerate primary record files, companion files, and skipped files in *dirpath*.

    Steps:
    1. Collect all filenames matching *pattern_re*; ignore everything else
       (templates, INDEX.md, root-cause analysis templates).
    2. Group matching filenames by numeric ID.
    3. Within each group the alphabetically-first filename is the primary
       record; every additional filename in the group is a companion.
    4. Collect filenames that start with the record prefix (``BUG-`` or
       ``TECH-DEBT-``) but do not match the full *pattern_re* — these are
       malformed record-shaped files (wrong extension, uppercase slug,
       underscore slug, etc.) that would otherwise be silently ignored.

    If *dirpath* does not exist, returns three empty collections (graceful
    degradation — the caller reports the absent directory).

    Returns:
        records    — sorted list of primary filenames
        companions — list of ``(filename, exclusion_reason)`` for companions
        skipped    — set of record-shaped filenames that failed the full regex
    """
    _PREFIX = "BUG-" if kind == "bug" else "TECH-DEBT-"

    by_id: dict[str, list[str]] = defaultdict(list)
    skipped: set[str] = set()

    if not dirpath.is_dir():
        return [], [], skipped

    try:
        entries = sorted(os.listdir(dirpath))
    except OSError as exc:
        raise SystemExit(f"ERROR: Cannot list {dirpath}: {exc}") from exc

    for name in entries:
        m = pattern_re.match(name)
        if m:
            by_id[m.group(1)].append(name)
        elif name.upper().startswith(_PREFIX):
            # Starts with the record prefix but fails the full pattern —
            # likely a malformed filename (wrong extension, uppercase slug, etc.)
            skipped.add(name)

    records: list[str] = []
    companions: list[tuple[str, str]] = []
    for numeric_id in sorted(by_id.keys(), key=lambda x: int(x)):
        names = by_id[numeric_id]
        if len(names) == 1:
            primary = names[0]
        else:
            # Prefer the member carrying a parseable **Status** header;
            # fall back to alphabetically-first if none has one.
            primary = names[0]
            for name in names:
                try:
                    text = (dirpath / name).read_text(
                        encoding="utf-8", errors="replace"
                    )
                except OSError:
                    continue
                if extract_raw_status(text):
                    primary = name
                    break

        records.append(primary)
        for companion_name in names:
            if companion_name == primary:
                continue
            reason = (
                f"shares {kind.upper()} numeric ID {numeric_id} "
                f"with primary record {primary}"
            )
            companions.append((companion_name, reason))

    return records, companions, skipped


def parse_record_file(path: Path, kind: str) -> Record:
    """Parse a single record file into a :class:`Record`."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return Record(
            filename=path.name,
            numeric_id="???",
            kind=kind,
            raw_status="",
            is_closed=False,
            sev="",
            title=f"[UNREADABLE: {exc}]",
        )

    raw_status = extract_raw_status(text) or ""
    is_closed = classify_status(raw_status, kind) if raw_status else False
    sev = extract_severity(text)
    title = extract_title(text, path.name)

    re_map = {"bug": BUG_RECORD_RE, "td": TD_RECORD_RE}
    fm = re_map[kind].match(path.name)
    numeric_id = fm.group(1) if fm else "???"

    return Record(
        filename=path.name,
        numeric_id=numeric_id,
        kind=kind,
        raw_status=raw_status,
        is_closed=is_closed,
        sev=sev,
        title=title,
    )


# ---------------------------------------------------------------------------
# Existing INDEX parsing (for divergence detection)
# ---------------------------------------------------------------------------


def parse_index_ids(
    index_path: Path,
    id_prefix: str,
) -> tuple[list[str], list[str]]:
    """Parse an existing INDEX.md and return ``(open_ids, closed_ids)``.

    *id_prefix* is ``"BUG"`` or ``"TECH-DEBT"``.  Returns numeric IDs
    (as strings) found in each section based on section-header boundaries.
    """
    if not index_path.exists():
        return [], []

    text = index_path.read_text(encoding="utf-8", errors="replace")

    open_match = _OPEN_SECTION_RE.search(text)
    closed_match = _CLOSED_SECTION_RE.search(text)

    if not open_match:
        print(
            f"WARNING: parse_index_ids: no '## Open' section found in {index_path}",
            file=sys.stderr,
        )
    if not closed_match:
        print(
            f"WARNING: parse_index_ids: no '## Closed' section found in {index_path}",
            file=sys.stderr,
        )

    if not open_match and not closed_match:
        return [], []

    row_re = re.compile(
        rf"\|\s*{re.escape(id_prefix)}-(\d+)\s*\|",
        re.IGNORECASE,
    )

    open_ids: list[str] = []
    closed_ids: list[str] = []

    for m in row_re.finditer(text):
        pos = m.start()
        numeric = m.group(1)

        in_open = open_match is not None and pos > open_match.start()
        in_closed = closed_match is not None and pos > closed_match.start()

        if in_open and in_closed:
            # Row follows both section headers — attribute to the later one.
            if open_match.start() > closed_match.start():
                open_ids.append(numeric)
            else:
                closed_ids.append(numeric)
        elif in_closed:
            closed_ids.append(numeric)
        elif in_open:
            open_ids.append(numeric)
        # else: before any section header → ignored (header/preamble rows)

    return open_ids, closed_ids


# ---------------------------------------------------------------------------
# Staleness analysis
# ---------------------------------------------------------------------------


def compute_staleness(
    bugs_records: list[Record],
    td_records: list[Record],
    companions: list[tuple[str, str]],
    bugs_index: Path,
    td_index: Path,
    all_skipped: set[str] | None = None,
) -> dict:
    """Compare file-scan results against the existing INDEX files.

    Returns a dict with keys:
    - ``companions``      — list of ``(filename, reason)``
    - ``divergences``     — list of dicts ``{file, status, detail}``
    - ``orphan_bug_ids``  — numeric IDs in bugs INDEX with no matching file
    - ``orphan_td_ids``   — numeric IDs in TD INDEX with no matching file
    - ``missing_bug``     — bug filenames not referenced in bugs INDEX
    - ``missing_td``      — TD filenames not referenced in TD INDEX
    - ``no_status``       — filenames with no parseable Status header
    - ``skipped``         — record-shaped filenames that failed the full regex
    - ``missing_indexes`` — INDEX paths absent when their record dirs have files
    """
    bugs_open_idx, bugs_closed_idx = parse_index_ids(bugs_index, "BUG")
    td_open_idx, td_closed_idx = parse_index_ids(td_index, "TECH-DEBT")

    all_bugs_idx_ids = set(bugs_open_idx) | set(bugs_closed_idx)
    all_td_idx_ids = set(td_open_idx) | set(td_closed_idx)
    all_bug_file_ids = {r.numeric_id for r in bugs_records}
    all_td_file_ids = {r.numeric_id for r in td_records}

    divergences: list[dict] = []

    for r in bugs_records:
        if r.numeric_id in bugs_open_idx and r.is_closed:
            divergences.append(
                {
                    "file": r.filename,
                    "status": r.raw_status,
                    "detail": "Classified CLOSED by script but in Open section of bugs/INDEX.md",
                }
            )
        elif r.numeric_id in bugs_closed_idx and not r.is_closed:
            divergences.append(
                {
                    "file": r.filename,
                    "status": r.raw_status,
                    "detail": "Classified OPEN by script but in Closed section of bugs/INDEX.md",
                }
            )

    for r in td_records:
        if r.numeric_id in td_open_idx and r.is_closed:
            divergences.append(
                {
                    "file": r.filename,
                    "status": r.raw_status,
                    "detail": "Classified CLOSED by script but in Open section of tech-debt/INDEX.md",
                }
            )
        elif r.numeric_id in td_closed_idx and not r.is_closed:
            divergences.append(
                {
                    "file": r.filename,
                    "status": r.raw_status,
                    "detail": "Classified OPEN by script but in Closed section of tech-debt/INDEX.md",
                }
            )

    orphan_bug_ids = sorted(all_bugs_idx_ids - all_bug_file_ids, key=lambda x: int(x))
    orphan_td_ids = sorted(all_td_idx_ids - all_td_file_ids, key=lambda x: int(x))
    missing_bug = sorted(
        r.filename for r in bugs_records if r.numeric_id not in all_bugs_idx_ids
    )
    missing_td = sorted(
        r.filename for r in td_records if r.numeric_id not in all_td_idx_ids
    )
    no_status = [r.filename for r in bugs_records + td_records if not r.raw_status]

    # Missing INDEX files — surfaced when records exist but no INDEX is present.
    # Counted in --check failure; --write creates them so they are not errors there.
    missing_indexes: list[str] = []
    if bugs_records and not bugs_index.exists():
        missing_indexes.append("bugs/INDEX.md")
    if td_records and not td_index.exists():
        missing_indexes.append("tech-debt/INDEX.md")

    return {
        "companions": companions,
        "divergences": divergences,
        "orphan_bug_ids": orphan_bug_ids,
        "orphan_td_ids": orphan_td_ids,
        "missing_bug": missing_bug,
        "missing_td": missing_td,
        "no_status": no_status,
        "skipped": sorted(all_skipped) if all_skipped else [],
        "missing_indexes": missing_indexes,
    }


# ---------------------------------------------------------------------------
# INDEX rendering
# ---------------------------------------------------------------------------


def _sev_key(sev: str) -> int:
    return _SEV_PRIORITY.get(sev.upper().strip(), 99)


def _truncate(s: str, limit: int = 70) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _table_cell(s: str) -> str:
    """Escape pipe characters in a markdown table cell value.

    A literal ``|`` in a status or title value would inject extra column
    delimiters and break the markdown table structure.
    """
    return s.replace("|", "\\|")


def render_bugs_index(
    records: list[Record],
    companions: list[tuple[str, str]],
    now_str: str,
) -> str:
    """Render the full text of oversight/bugs/INDEX.md."""
    open_records = sorted(
        [r for r in records if not r.is_closed],
        key=lambda r: (_sev_key(r.sev), int(r.numeric_id)),
    )
    closed_records = [r for r in records if r.is_closed]

    n_total = len(records)
    n_open = len(open_records)
    n_closed = len(closed_records)

    sev_counts: dict[str, int] = defaultdict(int)
    for r in open_records:
        sev_counts[r.sev.upper() or "UNSPECIFIED"] += 1

    sev_parts = []
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        count = sev_counts.get(sev, 0)
        if count:
            sev_parts.append(
                f"**{count} {sev}**" if sev == "CRITICAL" else f"{count} {sev}"
            )
    other = n_open - sum(
        sev_counts.get(s, 0) for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    )
    if other:
        sev_parts.append(f"{other} other/unspecified")
    sev_summary = ", ".join(sev_parts) if sev_parts else "none"

    companion_note = ""
    if companions:
        names_str = ", ".join(f"`{c[0]}`" for c in companions)
        companion_note = f"; companion file(s) excluded: {names_str}"

    lines = [
        "# Bug Tracker Index",
        "",
        f"**Last Updated**: {now_str} (aim-tracking-freshness rebuild — per-file `**Status**` scan of all {n_total} BUG records{companion_note}.)",
        "**Authority for status**: the individual `BUG-*.md` file, read directly.",
        "**Method**: per-file `**Status**` header scan (colon and table-row formats) of every `bugs/BUG-*.md`; companion files excluded per duplicate-ID rule.",
        "",
        "---",
        "",
        "## Quick Stats",
        "",
        "| Category | Count |",
        "|----------|-------|",
        f"| **BUG records (files, excl. companion)** | {n_total} |",
        f"| **Open / actionable** | {n_open} |",
        f"| **Closed** (FIXED / VERIFIED / CLOSED / RESOLVED / NOT-A-BUG / DUPLICATE / RECLASSIFIED / FIX-APPLIED) | {n_closed} |",
        "",
        f"Open breakdown: {sev_summary}.",
        "",
        "> **GC-18 note**: an index of this size is inherently large; this file IS the navigation layer, kept whole and grouped by status rather than sharded.",
        "",
        "---",
        "",
        "## Open / Actionable Bugs",
        "",
        "Grouped by severity. Status text is quoted verbatim from each file.",
        "",
        "| ID | Sev | Title | Status (verbatim) | Link |",
        "|----|-----|-------|-------------------|------|",
    ]

    for r in open_records:
        bid = f"BUG-{r.numeric_id}"
        sev = r.sev or "—"
        title = _table_cell(_truncate(r.title, 60))
        status = _table_cell(r.raw_status)
        link = f"[file](./{r.filename})"
        lines.append(f"| {bid} | {sev} | {title} | {status} | {link} |")

    lines += [
        "",
        "---",
        "",
        "## Closed Bugs",
        "",
        "| ID | Title | Status (verbatim) | Link |",
        "|----|-------|-------------------|------|",
    ]

    for r in closed_records:
        bid = f"BUG-{r.numeric_id}"
        title = _table_cell(_truncate(r.title, 70))
        status = _table_cell(r.raw_status)
        link = f"[file](./{r.filename})"
        lines.append(f"| {bid} | {title} | {status} | {link} |")

    lines += [
        "",
        "---",
        "",
        f"*Regenerated by aim-tracking-freshness, {now_str}. Authority: per-file `**Status**` header scan.*",
        "",
    ]

    return "\n".join(lines)


def render_td_index(
    records: list[Record],
    companions: list[tuple[str, str]],
    now_str: str,
) -> str:
    """Render the full text of oversight/tech-debt/INDEX.md."""
    open_records = sorted(
        [r for r in records if not r.is_closed],
        key=lambda r: (_sev_key(r.sev), int(r.numeric_id)),
    )
    closed_records = [r for r in records if r.is_closed]

    n_total = len(records)
    n_open = len(open_records)
    n_closed = len(closed_records)

    sev_counts: dict[str, int] = defaultdict(int)
    for r in open_records:
        sev_counts[r.sev.upper() or "UNSPECIFIED"] += 1

    sev_parts = []
    for sev in ("HIGH", "MEDIUM", "LOW"):
        count = sev_counts.get(sev, 0)
        if count:
            sev_parts.append(f"{count} {sev}")
    unspec = sev_counts.get("UNSPECIFIED", 0)
    if unspec:
        sev_parts.append(f"{unspec} unspecified")
    sev_summary = ", ".join(sev_parts) if sev_parts else "none"

    companion_note = ""
    if companions:
        names_str = ", ".join(f"`{c[0]}`" for c in companions)
        companion_note = f"; companion file(s) excluded: {names_str}"

    lines = [
        "# Technical Debt Index",
        "",
        f"**Last Updated**: {now_str} (aim-tracking-freshness rebuild — per-file `**Status**` scan of all {n_total} standalone TD files{companion_note}.)",
        "**Authority for status**: the individual `TECH-DEBT-*.md` file, read directly.",
        f"**Scope note**: this index covers the **{n_total} standalone TD files** only.",
        "",
        "---",
        "",
        "## Quick Stats",
        "",
        "| Category | Count |",
        "|----------|-------|",
        f"| **Standalone TD files** | {n_total} |",
        f"| **Open** (NEW / IN PROGRESS / REOPENED / DEFERRED) | {n_open} |",
        f"| **Closed** (RESOLVED / CLOSED / WONT FIX / WON'T FIX / IMPLEMENTED / FIXED) | {n_closed} |",
        "",
        f"Open severity: {sev_summary}.",
        "",
        "> **GC-18 note**: this file IS the navigation layer for all standalone TD records; kept whole, grouped by status.",
        "",
        "---",
        "",
        "## Open Technical Debt",
        "",
        "Grouped by severity. Status text quoted verbatim from each file.",
        "",
        "| ID | Sev | Title | Status (verbatim) | Link |",
        "|----|-----|-------|-------------------|------|",
    ]

    for r in open_records:
        tid = f"TECH-DEBT-{r.numeric_id}"
        sev = r.sev or "—"
        title = _table_cell(_truncate(r.title, 60))
        status = _table_cell(r.raw_status)
        link = f"[file](./{r.filename})"
        lines.append(f"| {tid} | {sev} | {title} | {status} | {link} |")

    lines += [
        "",
        "---",
        "",
        "## Closed Technical Debt",
        "",
        "| ID | Title | Status (verbatim) | Link |",
        "|----|-------|-------------------|------|",
    ]

    for r in closed_records:
        tid = f"TECH-DEBT-{r.numeric_id}"
        title = _table_cell(_truncate(r.title, 70))
        status = _table_cell(r.raw_status)
        link = f"[file](./{r.filename})"
        lines.append(f"| {tid} | {title} | {status} | {link} |")

    lines += [
        "",
        "---",
        "",
        f"*Regenerated by aim-tracking-freshness, {now_str}. Authority: per-file `**Status**` header scan.*",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------


def _hr() -> None:
    print("-" * 72)


def print_staleness_report(
    staleness: dict,
    bugs_records: list[Record],
    td_records: list[Record],
    mode: str,
) -> None:
    """Print the full staleness report to stdout."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    bugs_open = sum(1 for r in bugs_records if not r.is_closed)
    bugs_closed = sum(1 for r in bugs_records if r.is_closed)
    td_open = sum(1 for r in td_records if not r.is_closed)
    td_closed = sum(1 for r in td_records if r.is_closed)

    print()
    _hr()
    print(f"  aim-tracking-freshness  [{mode.upper()} MODE]  {now}")
    _hr()
    print(
        f"  Bugs scanned : {len(bugs_records)} records  ({bugs_open} open, {bugs_closed} closed)"
    )
    print(
        f"  TDs scanned  : {len(td_records)} records  ({td_open} open, {td_closed} closed)"
    )
    print()

    # ── 1. Companions excluded (always named explicitly) ──────────────────
    companions = staleness["companions"]
    print(f"COMPANIONS EXCLUDED: {len(companions)}")
    if companions:
        for fname, reason in companions:
            print(f"  •  {fname}")
            print(f"     Reason: {reason}")
    else:
        print("  (none)")
    print()

    # ── 2. Skipped record-shaped files ────────────────────────────────────
    skipped = staleness.get("skipped", [])
    print(f"SKIPPED — RECORD-SHAPED FILES FAILING FULL PATTERN: {len(skipped)}")
    if skipped:
        print(
            "  These files start with BUG-/TECH-DEBT- but failed the filename"
            " pattern"
        )
        print(
            "  (wrong extension, uppercase/underscore slug, etc.)."
            " They are excluded from scanning."
        )
        print("  Each counts as an issue in --check mode.")
        for fname in sorted(skipped):
            print(f"  ✗  {fname}")
    else:
        print("  (none)")
    print()

    # ── 3. No-Status warnings ─────────────────────────────────────────────
    no_status = staleness["no_status"]
    print(f"WARNING — NO STATUS HEADER: {len(no_status)}")
    if no_status:
        for fname in no_status:
            print(f"  ⚠  {fname}")
    else:
        print("  (none)")
    print()

    # ── 4. Divergences — surfaced prominently ────────────────────────────
    divs = staleness["divergences"]
    print(f"DIVERGENCES (record Status vs INDEX placement): {len(divs)}")
    if divs:
        print("  These records are mis-classified in the current INDEX:")
        print()
        for d in divs:
            print(f"  ✗  {d['file']}")
            print(f"     Status : \"{d['status']}\"")
            print(f"     Detail : {d['detail']}")
            print()
    else:
        print("  ✓  No divergences — all INDEX placements match file Status headers.")
    print()

    # ── 5. Orphan INDEX rows ──────────────────────────────────────────────
    ob = staleness["orphan_bug_ids"]
    ot = staleness["orphan_td_ids"]
    total_orphans = len(ob) + len(ot)
    print(f"ORPHAN INDEX ROWS (in INDEX but no matching file): {total_orphans}")
    if ob:
        print(f"  Bugs  : {', '.join('BUG-' + i for i in ob)}")
    if ot:
        print(f"  TDs   : {', '.join('TECH-DEBT-' + i for i in ot)}")
    if not total_orphans:
        print("  (none)")
    print()

    # ── 6. Missing from INDEX ─────────────────────────────────────────────
    mb = staleness["missing_bug"]
    mt = staleness["missing_td"]
    total_missing = len(mb) + len(mt)
    print(
        f"MISSING FROM INDEX (file found, not in either INDEX section): {total_missing}"
    )
    if mb:
        print("  Bugs missing:")
        for f in mb:
            print(f"    •  {f}")
    if mt:
        print("  TDs missing:")
        for f in mt:
            print(f"    •  {f}")
    if not total_missing:
        print("  (none)")
    print()

    # ── 7. Missing INDEX files ────────────────────────────────────────────
    missing_indexes = staleness.get("missing_indexes", [])
    print(
        f"MISSING INDEX FILES (records exist but INDEX.md absent): {len(missing_indexes)}"
    )
    if missing_indexes:
        for idx_path in missing_indexes:
            print(f"  ✗  {idx_path}")
        if mode == "write":
            print("  → INDEX files will be created by this --write run.")
        else:
            print("  → Run with --write to create missing INDEX files.")
    else:
        print("  (none)")
    print()

    _hr()
    total_records = len(bugs_records) + len(td_records)
    total_issues = (
        len(divs) + total_orphans + total_missing + len(no_status) + len(skipped)
    )
    if mode == "check":
        total_issues += len(missing_indexes)

    if total_records == 0 and total_issues == 0:
        print("  RESULT: 0 records scanned — empty/absent tracking tree.")
    elif total_issues == 0:
        print("  RESULT: INDEX files are fully in sync with file Status headers. ✓")
    else:
        print(f"  RESULT: {total_issues} issue(s) found.")
        if mode == "check":
            print("          Run with --write to regenerate INDEX files.")
        else:
            print(
                "          INDEX files have been regenerated (see Wrote: lines above)."
            )
    _hr()
    print()


# ---------------------------------------------------------------------------
# F-1: Phantom-open candidate detection (--verify-code-state)
# ---------------------------------------------------------------------------


def resolve_source_repo(args: argparse.Namespace, oversight_root: Path) -> Path | None:
    """Resolve source git repo path from --source-repo, env var, or default heuristic.

    Resolution order: ``--source-repo`` CLI flag → ``AI_MEMORY_SOURCE_REPO`` env var
    → ``../ai-memory`` relative to the oversight root (workspace-layout heuristic).
    Returns ``None`` when the resolved path does not exist.
    """
    if getattr(args, "source_repo", None):
        p = Path(args.source_repo).expanduser().resolve()
    elif "AI_MEMORY_SOURCE_REPO" in os.environ:
        p = Path(os.environ["AI_MEMORY_SOURCE_REPO"]).expanduser().resolve()
    else:
        p = (oversight_root.parent / "ai-memory").resolve()
    return p if p.is_dir() else None


def _git_available() -> bool:
    return shutil.which("git") is not None


def _run_git(cmd: list, cwd: Path, timeout: float = 5.0) -> tuple[bool, str]:
    """Run a git sub-command; return (success, stdout).

    Returns (False, "") on timeout or OS error — callers treat this as "no evidence".
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout
    except subprocess.TimeoutExpired:
        return False, ""
    except OSError:
        return False, ""


def extract_evidence_tokens(text: str, numeric_id: str, kind: str) -> dict:
    """Extract evidence tokens (SHAs, PR refs, file paths) from a record file body.

    Returns a dict with keys: record_id, shas, pr_refs, file_paths.
    """
    id_prefix = "BUG" if kind == "bug" else "TECH-DEBT"
    record_id = f"{id_prefix}-{numeric_id}"

    shas: set = set(_SHA_EVIDENCE_RE.findall(text))

    pr_refs: set = set()
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for m in _PR_REF_EVIDENCE_RE.finditer(line):
            num = int(m.group(1))
            if 1 <= num <= 9999:
                pr_refs.add(m.group(1))

    file_paths: set = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "*", "+")):
            for m in _FILE_PATH_EVIDENCE_RE.finditer(stripped):
                file_paths.add(m.group(0))

    return {
        "record_id": record_id,
        "shas": shas,
        "pr_refs": pr_refs,
        "file_paths": file_paths,
    }


def _query_merged_shas(
    record_id: str,
    source_repo: Path,
    timeout: float = 5.0,
) -> tuple[list, list, dict]:
    """Query git for commits mentioning record_id.

    Returns (merged_shas, all_shas, touched_files_by_sha).
    merged_shas: abbreviated SHAs reachable from main.
    all_shas: abbreviated SHAs from --all search.
    touched_files_by_sha: {sha: [file, ...]}.
    """
    ok, out = _run_git(
        ["git", "log", "--all", "--oneline", f"--grep={record_id}"],
        source_repo,
        timeout=timeout,
    )
    all_shas: list = []
    if ok and out.strip():
        for line in out.strip().splitlines():
            parts = line.split(None, 1)
            if parts:
                all_shas.append(parts[0])

    if not all_shas:
        return [], [], {}

    ok2, out2 = _run_git(
        ["git", "log", "--oneline", f"--grep={record_id}", "main"],
        source_repo,
        timeout=timeout,
    )
    merged_shas: list = []
    if ok2 and out2.strip():
        for line in out2.strip().splitlines():
            parts = line.split(None, 1)
            if parts:
                merged_shas.append(parts[0])

    touched_files_by_sha: dict = {}
    for sha in merged_shas:
        # --root makes diff-tree emit touched files for a root commit too;
        # otherwise root commits return empty output and path-overlap scoring
        # silently collapses to MEDIUM.
        ok3, out3 = _run_git(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha],
            source_repo,
            timeout=timeout,
        )
        if ok3:
            touched_files_by_sha[sha] = [f for f in out3.strip().splitlines() if f]

    return merged_shas, all_shas, touched_files_by_sha


def _has_revert_on_main(
    record_id: str, source_repo: Path, timeout: float = 5.0
) -> bool:
    """Return True if a revert commit for record_id is reachable from main."""
    ok, out = _run_git(
        ["git", "log", "--oneline", f"--grep=Revert.*{record_id}", "main"],
        source_repo,
        timeout=timeout,
    )
    return ok and bool(out.strip())


def _bug_mtime_predates_fix(
    record_path: Path, record_id: str, source_repo: Path, timeout: float = 5.0
) -> bool:
    """Return True if the record file mtime predates the latest fix commit date."""
    try:
        rec_mtime = record_path.stat().st_mtime
    except OSError:
        return False

    ok, out = _run_git(
        ["git", "log", "--format=%ct", f"--grep={record_id}", "main"],
        source_repo,
        timeout=timeout,
    )
    if not ok or not out.strip():
        return False

    for line in out.strip().splitlines():
        try:
            commit_ts = float(line.strip())
            if rec_mtime < commit_ts:
                return True
        except ValueError:
            continue
    return False


def score_phantom_confidence(
    merged_shas: list,
    all_shas: list,
    touched_files_by_sha: dict,
    evidence_tokens: dict,
    record_path: Path,
    source_repo: Path,
) -> str | None:
    """Return confidence level (HIGH/MEDIUM/LOW) or None when record should not be flagged.

    HIGH: ≥1 commit on main, file-path overlap with bug body, record mtime predates fix.
    MEDIUM: ≥1 commit on main, no file-path overlap (commit message is the only link).
    LOW: evidence exists (tokens in file or commits in --all) but none merged to main;
         also LOW when a revert commit is reachable from main alongside the fix commit.
    None: no git evidence and no inline evidence tokens — skip this record.
    """
    record_id = evidence_tokens["record_id"]

    if not merged_shas:
        has_any_evidence = bool(
            all_shas or evidence_tokens["shas"] or evidence_tokens["pr_refs"]
        )
        return "LOW" if has_any_evidence else None

    if _has_revert_on_main(record_id, source_repo):
        return "LOW"

    all_touched: set = set()
    for files in touched_files_by_sha.values():
        all_touched.update(files)

    evidence_paths = evidence_tokens["file_paths"]
    has_path_overlap = False
    if evidence_paths and all_touched:
        for ep in evidence_paths:
            ep_base = ep.split("/")[-1]
            for tf in all_touched:
                tf_base = tf.split("/")[-1]
                if ep == tf or ep_base == tf_base:
                    has_path_overlap = True
                    break
            if has_path_overlap:
                break

    mtime_predates = _bug_mtime_predates_fix(record_path, record_id, source_repo)

    if has_path_overlap and mtime_predates:
        return "HIGH"
    return "MEDIUM"


def _phantom_table_rows(candidates: list) -> list:
    """Render markdown table rows for a list of phantom-open candidate dicts."""
    rows = [
        "| Record | File Status | Fix commit(s) on main | Files touched | Record mtime |",
        "|--------|-------------|------------------------|---------------|--------------|",
    ]
    for c in candidates:
        record = c["record"]
        commits = ", ".join(c["merged_shas"][:3])
        if len(c["merged_shas"]) > 3:
            commits += f" (+{len(c['merged_shas']) - 3} more)"
        all_touched = c["all_touched"]
        files_preview = list(all_touched)[:4]
        files_str = ", ".join(files_preview)
        if len(all_touched) > 4:
            files_str += f" (+{len(all_touched) - 4} more)"
        try:
            mtime_str = datetime.fromtimestamp(
                c["record_path"].stat().st_mtime, tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except OSError:
            mtime_str = "unknown"
        id_prefix = "BUG" if record.kind == "bug" else "TECH-DEBT"
        rid = f"{id_prefix}-{record.numeric_id}"
        status_cell = _table_cell(record.raw_status[:60])
        rows.append(
            f"| {rid} | {status_cell} | {commits or '—'} | {files_str or '—'} | {mtime_str} |"
        )
    return rows


def print_phantom_report_section(
    high: list,
    medium: list,
    low: list,
) -> None:
    """Print the PHANTOM-OPEN CANDIDATES section to stdout."""
    print()
    _hr()
    total = len(high) + len(medium) + len(low)
    print(
        f"  PHANTOM-OPEN CANDIDATES "
        f"(file says OPEN, git says FIXED): {total} candidate(s)"
    )
    _hr()
    print()

    if not total:
        print("  ✓  No phantom-open candidates detected.")
        print()
        return

    if high:
        print(f"HIGH confidence — likely phantom-open ({len(high)})")
        print()
        for row in _phantom_table_rows(high):
            print(row)
        print()

    if medium:
        print(
            f"MEDIUM confidence — commit exists, no file-path overlap ({len(medium)})"
        )
        print()
        for row in _phantom_table_rows(medium):
            print(row)
        print()

    if low:
        print(f"LOW confidence — evidence in file, not yet merged to main ({len(low)})")
        print()
        for row in _phantom_table_rows(low):
            print(row)
        print()


def write_phantom_sidecar(
    high: list,
    medium: list,
    low: list,
    oversight_root: Path,
    now_str: str,
) -> None:
    """Write oversight/reports/PHANTOM-OPEN-CANDIDATES.md (created if absent)."""
    reports_dir = oversight_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    sidecar = reports_dir / "PHANTOM-OPEN-CANDIDATES.md"

    total = len(high) + len(medium) + len(low)
    lines = [
        "# Phantom-Open Candidates",
        "",
        f"**Generated**: {now_str}",
        f"**Total candidates**: {total}",
        "",
        "> Records whose file `**Status**` says OPEN but whose git history suggests",
        "> a fix is already merged to main. Requires human triage to confirm and update Status.",
        "",
        "---",
        "",
    ]
    if not total:
        lines += ["✓ No phantom-open candidates detected.", ""]
    else:
        for label, bucket in (
            (f"## HIGH confidence — likely phantom-open ({len(high)})", high),
            (
                f"## MEDIUM confidence — commit exists, no file-path overlap ({len(medium)})",
                medium,
            ),
            (
                f"## LOW confidence — evidence in file, not yet merged to main ({len(low)})",
                low,
            ),
        ):
            if bucket:
                lines += [label, ""]
                lines += _phantom_table_rows(bucket)
                lines += [""]

    sidecar.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote sidecar: {sidecar}")


def run_verify_code_state(
    open_records_with_dirs: list,
    source_repo: Path | None,
    oversight_root: Path,
    args: argparse.Namespace,
) -> None:
    """Orchestrate the phantom-open sweep: query git, score, print, write sidecar."""
    if source_repo is None:
        guessed = (oversight_root.parent / "ai-memory").resolve()
        print(
            f"NOTE: --verify-code-state requested but source repo not resolved "
            f"(checked AI_MEMORY_SOURCE_REPO env var and {guessed}).",
            file=sys.stderr,
        )
        return

    if not _git_available():
        print(
            "NOTE: --verify-code-state requested but 'git' binary not found in PATH.",
            file=sys.stderr,
        )
        return

    # Apply --bug-id filter
    bug_id_filter = getattr(args, "bug_id", None)
    if bug_id_filter:
        norm = bug_id_filter.upper()
        open_records_with_dirs = [
            (r, d)
            for r, d in open_records_with_dirs
            if (f"BUG-{r.numeric_id}" == norm or f"TECH-DEBT-{r.numeric_id}" == norm)
        ]

    # Apply --last-n-sessions filter (N most recently modified open records)
    last_n = getattr(args, "last_n_sessions", None)
    if last_n is not None and last_n > 0:

        def _mtime(item: tuple) -> float:
            r, d = item
            try:
                return (d / r.filename).stat().st_mtime
            except OSError:
                return 0.0

        open_records_with_dirs = sorted(
            open_records_with_dirs, key=_mtime, reverse=True
        )[:last_n]

    high: list = []
    medium: list = []
    low: list = []

    for record, record_dir in open_records_with_dirs:
        record_path = record_dir / record.filename
        try:
            text = record_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        tokens = extract_evidence_tokens(text, record.numeric_id, record.kind)
        merged_shas, all_shas, touched_files_by_sha = _query_merged_shas(
            tokens["record_id"], source_repo
        )
        confidence = score_phantom_confidence(
            merged_shas,
            all_shas,
            touched_files_by_sha,
            tokens,
            record_path,
            source_repo,
        )
        if confidence is None:
            continue

        all_touched: set = set()
        for files in touched_files_by_sha.values():
            all_touched.update(files)

        candidate = {
            "record": record,
            "record_path": record_path,
            "confidence": confidence,
            "merged_shas": merged_shas,
            "all_shas": all_shas,
            "all_touched": all_touched,
        }
        if confidence == "HIGH":
            high.append(candidate)
        elif confidence == "MEDIUM":
            medium.append(candidate)
        else:
            low.append(candidate)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print_phantom_report_section(high, medium, low)
    write_phantom_sidecar(high, medium, low, oversight_root, now_str)


# ---------------------------------------------------------------------------
# F-2: Decision-log body coverage check (folded into --check / --write)
# ---------------------------------------------------------------------------


def _parse_dec_ids_from_text(text: str) -> set:
    """Extract all DEC-PMnnn-Dn IDs from text, expanding range notation.

    Range ``DEC-PM299-D1..D8`` expands to DEC-PM299-D1 through DEC-PM299-D8.
    Individual ``DEC-PM299-D1`` references outside a range are also collected.
    Deduplication is applied.
    """
    found: set = set()
    range_positions: set = set()

    for m in _DEC_RANGE_RE.finditer(text):
        pm_num = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3))
        for d in range(start, end + 1):
            found.add(f"DEC-PM{pm_num}-D{d}")
        range_positions.update(range(m.start(), m.end()))

    for m in _DEC_INDIVIDUAL_RE.finditer(text):
        if m.start() not in range_positions:
            found.add(f"DEC-PM{m.group(1)}-D{m.group(2)}")

    return found


def parse_decision_log_header_ids(header_text: str) -> set:
    """Extract DEC-PMnnn-Dn IDs from the decision-log header block."""
    return _parse_dec_ids_from_text(header_text)


def parse_decision_log_body_ids(full_text: str) -> set:
    """Extract DEC-PMnnn-Dn IDs from decision-log ``### DEC-PMnnn-Dn`` body headings."""
    found: set = set()
    for m in _DEC_BODY_HEADING_RE.finditer(full_text):
        found.add(m.group(1))
    return found


def check_decision_log_coverage(
    oversight_root: Path,
) -> tuple[list, list]:
    """Parse tracking/decision-log.md and return (missing_ids, orphan_ids).

    missing_ids: DEC IDs referenced in the header block with no body ``### heading``.
    orphan_ids: DEC IDs with a body ``### heading`` but not referenced in the header block.
    Returns ([], []) with a NOTE to stderr when the file is absent or unreadable.
    """
    log_path = oversight_root / "tracking" / "decision-log.md"
    if not log_path.exists():
        print(
            f"NOTE: decision-log.md not found at {log_path} "
            "— decision-log coverage check skipped.",
            file=sys.stderr,
        )
        return [], []

    try:
        full_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(
            f"NOTE: could not read {log_path}: {exc} "
            "— decision-log coverage check skipped.",
            file=sys.stderr,
        )
        return [], []

    hr_match = _DECISION_LOG_HR_RE.search(full_text)
    if hr_match:
        header_text = full_text[: hr_match.start()]
    else:
        print(
            "NOTE: decision-log.md has no '---' separator — "
            "treating entire file as header block.",
            file=sys.stderr,
        )
        header_text = full_text

    header_ids = parse_decision_log_header_ids(header_text)
    body_ids = parse_decision_log_body_ids(full_text)

    missing = sorted(header_ids - body_ids)
    orphan = sorted(body_ids - header_ids)
    return missing, orphan


def print_decision_log_report(missing: list, orphan: list) -> None:
    """Print the DECISION-LOG COVERAGE section to stdout."""
    print()
    _hr()
    print("  DECISION-LOG COVERAGE (header block refs vs body ### headings)")
    _hr()
    print()

    print(f"DRIFT-DEC-MISSING (header ref, no body entry): {len(missing)}")
    if missing:
        for dec_id in missing:
            print(
                f"  ✗  {dec_id}"
                "  (referenced in header summary, no ### body heading found)"
            )
    else:
        print("  (none)")
    print()

    print(f"DRIFT-DEC-ORPHAN (body heading, no header ref): {len(orphan)}")
    if orphan:
        for dec_id in orphan:
            print(
                f"  ℹ  {dec_id}"  # noqa: RUF001
                "  (### body heading exists, not referenced in current header summary)"
            )
    else:
        print("  (none)")
    print()

    if not missing:
        print("  ✓  Decision-log body coverage is complete.")
    print()


# ---------------------------------------------------------------------------
# Oversight root resolution
# ---------------------------------------------------------------------------


def resolve_oversight_root(args: argparse.Namespace) -> Path:
    """Resolve oversight root from CLI arg, env var, or CWD-relative default.

    Priority: ``--oversight-root`` > ``AI_MEMORY_OVERSIGHT_ROOT`` env var >
    ``./oversight`` relative to current working directory.
    """
    if args.oversight_root:
        p = Path(args.oversight_root).expanduser().resolve()
    elif "AI_MEMORY_OVERSIGHT_ROOT" in os.environ:
        p = Path(os.environ["AI_MEMORY_OVERSIGHT_ROOT"]).expanduser().resolve()
    else:
        p = (Path.cwd() / "oversight").resolve()

    if not p.is_dir():
        print(
            f"ERROR: oversight root not found at {p}\n"
            f"       Pass --oversight-root <path> or set AI_MEMORY_OVERSIGHT_ROOT,\n"
            f"       or run from the workspace root that contains oversight/.",
            file=sys.stderr,
        )
        sys.exit(1)
    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Scan oversight tracking files, report staleness divergences "
            "between file Status headers and INDEX placement, and optionally "
            "regenerate both INDEX.md files."
        )
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Read-only: print staleness report without writing any files.",
    )
    mode_group.add_argument(
        "--write",
        action="store_true",
        help="Regenerate both INDEX.md files, then print report.",
    )
    parser.add_argument(
        "--oversight-root",
        metavar="PATH",
        default=None,
        help=(
            "Path to the oversight/ directory "
            "(default: ./oversight relative to CWD, "
            "overridden by AI_MEMORY_OVERSIGHT_ROOT env var)."
        ),
    )
    parser.add_argument(
        "--verify-code-state",
        action="store_true",
        help=(
            "Cross-check open records against source git history to detect "
            "phantom-open candidates (file Status OPEN, fix commits merged to main). "
            "Advisory only — does not change --check exit code."
        ),
    )
    parser.add_argument(
        "--source-repo",
        metavar="PATH",
        default=None,
        help=(
            "Path to the source git repo for --verify-code-state "
            "(default: AI_MEMORY_SOURCE_REPO env var, then ../ai-memory relative to oversight root)."
        ),
    )
    parser.add_argument(
        "--last-n-sessions",
        metavar="N",
        type=int,
        default=None,
        help=(
            "Limit --verify-code-state sweep to the N most recently modified open records."
        ),
    )
    parser.add_argument(
        "--bug-id",
        metavar="RECORD-ID",
        default=None,
        help=(
            "Limit --verify-code-state to a single record (e.g. BUG-273 or TECH-DEBT-547)."
        ),
    )
    args = parser.parse_args()

    mode = "check" if args.check else "write"
    oversight_root = resolve_oversight_root(args)
    bugs_dir = oversight_root / "bugs"
    td_dir = oversight_root / "tech-debt"
    bugs_idx = bugs_dir / "INDEX.md"
    td_idx = td_dir / "INDEX.md"

    # A.4 — degrade gracefully on absent sub-dirs; only the oversight root is a
    # hard error (handled in resolve_oversight_root above).
    for d, label in ((bugs_dir, "bugs"), (td_dir, "tech-debt")):
        if not d.is_dir():
            print(
                f"NOTE: {label} directory absent — not scaffolded: {d}",
                file=sys.stderr,
            )

    # ── Enumerate files ────────────────────────────────────────────────────
    bug_filenames, bug_companions, bug_skipped = find_records(
        bugs_dir, BUG_RECORD_RE, "bug"
    )
    td_filenames, td_companions, td_skipped = find_records(td_dir, TD_RECORD_RE, "td")
    all_companions = bug_companions + td_companions
    all_skipped = bug_skipped | td_skipped

    # ── Parse record files ────────────────────────────────────────────────
    bugs_records = [parse_record_file(bugs_dir / fn, "bug") for fn in bug_filenames]
    td_records = [parse_record_file(td_dir / fn, "td") for fn in td_filenames]

    # ── Compute staleness ─────────────────────────────────────────────────
    staleness = compute_staleness(
        bugs_records, td_records, all_companions, bugs_idx, td_idx, all_skipped
    )

    # ── Write mode: regenerate INDEX files first ──────────────────────────
    # CR-1 guard: if a collection's directory is absent, skip writing its INDEX
    # and report it the same way --check does (NOTE to stderr). --write must
    # never crash on a missing subdir.
    if mode == "write":
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if bugs_dir.is_dir():
            bugs_content = render_bugs_index(bugs_records, bug_companions, now_str)
            bugs_idx.write_text(bugs_content, encoding="utf-8")
            print(f"Wrote: {bugs_idx}")
        else:
            print(
                f"NOTE: bugs directory absent — not scaffolded: {bugs_dir}",
                file=sys.stderr,
            )

        if td_dir.is_dir():
            td_content = render_td_index(td_records, td_companions, now_str)
            td_idx.write_text(td_content, encoding="utf-8")
            print(f"Wrote: {td_idx}")
        else:
            print(
                f"NOTE: tech-debt directory absent — not scaffolded: {td_dir}",
                file=sys.stderr,
            )

    # ── Print report (both modes) ─────────────────────────────────────────
    print_staleness_report(staleness, bugs_records, td_records, mode)

    # ── F-1: Phantom-open candidate detection (advisory, no exit-code change) ─
    if args.verify_code_state:
        source_repo = resolve_source_repo(args, oversight_root)
        open_records_with_dirs = [
            (r, bugs_dir) for r in bugs_records if not r.is_closed
        ] + [(r, td_dir) for r in td_records if not r.is_closed]
        run_verify_code_state(open_records_with_dirs, source_repo, oversight_root, args)

    # ── F-2: Decision-log body coverage check (DRIFT-DEC-MISSING → exit 1) ─
    missing_decs, orphan_decs = check_decision_log_coverage(oversight_root)
    print_decision_log_report(missing_decs, orphan_decs)

    # Exit-code contract:
    # --check : exits 1 if any divergence, orphan, missing, skipped, missing
    #           index, no-status record, or DRIFT-DEC-MISSING is found; exits 0
    #           when INDEX files are fully in sync and decision-log coverage is clean.
    #           Phantom-open candidates (--verify-code-state) are advisory only.
    # --write : exits 0 on a successful write (drift found-and-corrected is a
    #           successful outcome; the INDEX is now correct).  Use --check as
    #           the gating command in CI.
    if mode == "check":
        issues = (
            len(staleness["divergences"])
            + len(staleness["orphan_bug_ids"])
            + len(staleness["orphan_td_ids"])
            + len(staleness["missing_bug"])
            + len(staleness["missing_td"])
            + len(staleness["no_status"])
            + len(staleness["skipped"])
            + len(staleness["missing_indexes"])
            + len(missing_decs)
        )
        if issues:
            sys.exit(1)


if __name__ == "__main__":
    main()
