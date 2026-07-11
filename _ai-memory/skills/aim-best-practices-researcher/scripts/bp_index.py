#!/usr/bin/env python3
# _ai-memory/skills/aim-best-practices-researcher/scripts/bp_index.py
"""Update the best-practices INDEX for BP-*.md files.

``--write`` appends any BP-*.md files missing from the existing index.md
table (matched by BP-ID) without touching already-present rows or any other
content in the file — it never regenerates a curated INDEX. If no index.md
exists yet, a fresh one is generated from disk (bootstrap only).

Modes (mutually exclusive):
  --write  Append missing BP rows to an existing index.md (idempotent,
           non-destructive); bootstrap a fresh index.md if none exists yet.
  --check  Fire-only-if-missing: silent on the happy path (every BP file has an
           INDEX row, matched by BP-ID); prints offenders to stderr and exits
           non-zero when a BP file has no INDEX row (or index.md is absent
           while BP files exist).

Usage:
    bp_index.py --write  oversight/knowledge/best-practices
    bp_index.py --check  oversight/knowledge/best-practices
"""

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

INDEX_NAME = "index.md"
BP_GLOB = "BP-*.md"

# CommonMark base plus the built-in GFM `table` block rule. Not the "gfm-like"
# preset: that also enables `linkify`, which needs linkify-it-py (absent in the
# ai-memory venv) and raises ModuleNotFoundError. Enabling just `table` is the
# minimal, dependency-safe configuration for locating pipe tables.
_MD = MarkdownIt("commonmark").enable("table")

# Filename form: BP-<digits>-<slug>.md  (slug optional)
_BP_FILE_RE = re.compile(r"^BP-(\d+)(?:-(.*))?\.md$")
# First markdown H1 in a BP file.
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# "**Date**: YYYY-MM-DD" metadata line.
_DATE_RE = re.compile(r"^\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE)
# A BP-ID in a table row's first cell, e.g. "BP-001" (id-keyed, not filename).
_ROW_ID_RE = re.compile(r"^BP-(\d+)$", re.IGNORECASE)
# "Total findings: N" footer line (mechanical count, safe to bump on append).
_TOTAL_FINDINGS_RE = re.compile(r"(Total findings:\s*)(\d+)")

# Marker-delimited managed region (BP-059 Part A). When these HTML-comment
# sentinels are present, the span between them is the canonical index by
# *declaration* — robust to a legitimate 2nd top-level BP table or a renamed
# header that top-level header-sniffing would otherwise refuse. Detection
# anchors on the stable prefixes; emission uses the full lines. Markers absent
# -> fall back to top-level-only + header-sniff selection (non-breaking for
# legacy, marker-free indexes).
_BEGIN_ANCHOR = "<!-- BEGIN bp-index"
_END_ANCHOR = "<!-- END bp-index"
_END_MARKER = f"{_END_ANCHOR} -->"


def _begin_marker(script_hint: str) -> str:
    """The full BEGIN-marker line emitted on bootstrap (anchors on the stable
    ``_BEGIN_ANCHOR`` prefix; the parenthetical carries the regenerate hint)."""
    return (
        f"{_BEGIN_ANCHOR} (generated; edit BP-*.md, then re-run "
        f"{script_hint} --write <this-dir>) -->"
    )


class BPFile:
    """A parsed BP-*.md file: numeric id, display title, optional date."""

    def __init__(self, path: Path, numeric_id: int, title: str, date: str | None):
        self.path = path
        self.numeric_id = numeric_id
        self.title = title
        self.date = date

    @property
    def display_id(self) -> str:
        return f"BP-{self.numeric_id:03d}"


def _table_cell(s: str) -> str:
    """Escape pipe characters so a value can't break the markdown table."""
    return s.replace("|", "\\|")


def _title_for(filename_slug: str | None, body: str) -> str:
    """Derive a display title: first H1 (minus a 'Research Report:' prefix),
    falling back to the humanized filename slug, then an empty string."""
    m = _H1_RE.search(body)
    if m:
        title = m.group(1).strip()
        title = re.sub(r"^Research Report:\s*", "", title, flags=re.IGNORECASE)
        if title:
            return title
    if filename_slug:
        return filename_slug.replace("-", " ").strip()
    return ""


def scan_bp_files(bp_dir: Path) -> list[BPFile]:
    """Scan a directory for BP-*.md files, sorted by numeric BP-ID ascending."""
    found: list[BPFile] = []
    for path in bp_dir.glob(BP_GLOB):
        if not path.is_file():
            continue
        m = _BP_FILE_RE.match(path.name)
        if not m:
            continue
        numeric_id = int(m.group(1))
        slug = m.group(2)
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            body = ""
        date_m = _DATE_RE.search(body)
        found.append(
            BPFile(
                path=path,
                numeric_id=numeric_id,
                title=_title_for(slug, body),
                date=date_m.group(1) if date_m else None,
            )
        )
    found.sort(key=lambda b: b.numeric_id)
    return found


def render_index(bp_files: list[BPFile], script_hint: str) -> str:
    """Render the full text of index.md from the scanned BP files."""
    lines = ["# Best Practices Index", ""]
    if not bp_files:
        lines.append("_No best practices recorded yet._")
        lines.append("")
        return "\n".join(lines)

    # Wrap the generated table in the marker-delimited managed region so a
    # subsequent --write keys canonical selection off the markers (BP-059
    # Part A) rather than re-sniffing the header. The empty branch above emits
    # no markers on purpose — there is no table to wrap, and a lone BEGIN
    # without an END would be malformed.
    lines.append(_begin_marker(script_hint))
    lines.append("| BP | Topic | Date | File |")
    lines.append("|----|-------|------|------|")
    for b in bp_files:
        lines.append(
            f"| {b.display_id} | {_table_cell(b.title)} | "
            f"{b.date or '—'} | {_table_cell(b.path.name)} |"
        )
    lines.append(_END_MARKER)
    lines.append("")
    return "\n".join(lines)


def _looks_like_bp_header(cells: list[str]) -> bool:
    return bool(cells) and cells[0].strip().lower() in ("bp-id", "bp id", "bp")


def _header_cells_of(tokens: list, table_open_idx: int) -> list[str]:
    """Return the flat list of header-cell strings for the table whose
    ``table_open`` is at ``table_open_idx`` (the first thead row's cells)."""
    header: list[str] = []
    section = None
    j = table_open_idx + 1
    while j < len(tokens) and tokens[j].type != "table_close":
        tok = tokens[j]
        if tok.type == "thead_open":
            section = "head"
        elif tok.type == "tbody_open":
            section = "body"
        elif tok.type == "inline" and section == "head":
            header.append(tok.content)
        j += 1
    return header


def _row_ids_of(tokens: list, table_open_idx: int) -> set[str]:
    """Return every BP-ID found in the first cell of each row of the table
    whose ``table_open`` is at ``table_open_idx``, read from the parser's
    row/cell tokens (not raw source lines). Reading membership this way is
    container-agnostic — the parser has already unwrapped the inline cell
    content, so a ``> `` blockquote or list-item prefix on the source line is
    gone (id-keyed — header/divider first cells and BP-IDs mentioned in
    non-first cells never match). This reads whatever table it is handed;
    canonical *selection* is top-level-only, so ``_find_bp_table`` never hands
    it a nested table — nested tables are intentionally not selected as
    canonical."""
    ids: set[str] = set()
    cell_idx = -1
    j = table_open_idx + 1
    while j < len(tokens) and tokens[j].type != "table_close":
        tok = tokens[j]
        if tok.type == "tr_open":
            cell_idx = -1
        elif tok.type in ("td_open", "th_open"):
            cell_idx += 1
        elif tok.type == "inline" and cell_idx == 0:
            m = _ROW_ID_RE.match(tok.content.strip())
            if m:
                ids.add(f"BP-{int(m.group(1)):03d}")
        j += 1
    return ids


# Sentinel returned by ``_marker_region`` when markers are present but not a
# single well-ordered BEGIN..END pair — distinct from ``None`` (markers absent).
_MALFORMED_MARKERS = object()


def _anchor_match(stripped: str, anchor: str) -> bool:
    """True when ``stripped`` opens with ``anchor`` followed by a boundary —
    whitespace or the ``-->`` close. So ``<!-- BEGIN bp-index (…) -->`` and a
    hand-authored ``<!-- END bp-index-->`` match, but an unrelated
    ``<!-- BEGIN bp-index-experimental -->`` does not (the trailing ``-e…`` is
    neither whitespace nor ``-->``)."""
    if not stripped.startswith(anchor):
        return False
    rest = stripped[len(anchor):]
    return rest[:1].isspace() or rest.startswith("-->") or rest == ""


def _marker_region(tokens: list):
    """Locate the marker-delimited managed region (BP-059 Part A) from the
    parser's **top-level** ``html_block`` tokens.

    Returns:
      - ``None`` when no bp-index markers are present — the caller falls back to
        top-level-only + header-sniff selection (non-breaking for legacy,
        marker-free indexes).
      - ``(begin_line, end_line)`` — the 0-based source lines of the BEGIN and
        END marker blocks — when exactly one BEGIN precedes exactly one END.
      - ``_MALFORMED_MARKERS`` when markers are present but not a single
        well-ordered pair (one-sided, reversed, or duplicated); the caller
        refuses to write. A specific hint is printed **here, at the detection
        site**, so the caller signatures stay unchanged.

    Only top-level (``level == 0``) markers count: one nested in a
    blockquote/list item is not a document-level delimiter (mirrors the
    top-level-only table rule)."""
    begins: list[int] = []
    ends: list[int] = []
    for tok in tokens:
        if tok.type != "html_block" or tok.level != 0 or not tok.map:
            continue
        stripped = tok.content.lstrip()
        if _anchor_match(stripped, _BEGIN_ANCHOR):
            begins.append(tok.map[0])
        elif _anchor_match(stripped, _END_ANCHOR):
            ends.append(tok.map[0])
    if not begins and not ends:
        return None
    if len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]:
        return (begins[0], ends[0])
    print(
        "ERROR: malformed bp-index markers: expected exactly one "
        "'<!-- BEGIN bp-index ... -->' before one '<!-- END bp-index -->' "
        f"(found {len(begins)} BEGIN, {len(ends)} END) — the marker region "
        "is unusable.",
        file=sys.stderr,
    )
    return _MALFORMED_MARKERS


def _find_bp_table(text: str):
    """Locate the canonical best-practices table with a spec-compliant GFM
    parser and return ``(header_cells, last_table_line_idx, existing_ids)``,
    or ``None`` when there is not exactly one canonical table (see below).

    The boundary comes from the parser's source map (``table_open.map =
    [start_line, end_line)``), not a hand-rolled line scan: the parser
    implements the GFM tables grammar, so contiguous pipe rows (no blank
    line between them) are one table by definition.

    - ``header_cells`` are the canonical table's header-row cells.
    - ``last_table_line_idx`` is ``end_line - 1`` — the last source line of
      the table; new rows splice in right after it (the spec table end).
    - ``existing_ids`` are the BP-IDs found in the first cell of each of the
      table's own row tokens (parser-derived, not raw source lines) — header/
      separator/divider rows don't match, and BP-IDs mentioned in prose are
      outside a row's first cell, so neither corrupts membership.

    Two selection paths, both **fail-safe** (exactly-one-or-refuse):

    - **Marker region present** (``_marker_region`` returns a span): the region
      is canonical **by declaration**. Any single top-level ``table_open`` whose
      source-map span sits *inside* the region is selected — the BP-ID header is
      **not** re-sniffed here, so a legitimately renamed header still resolves
      (BP-059 Part A). The line-bounds filter excludes everything outside the
      region: a 2nd top-level BP table, the Status Legend, etc. Malformed
      markers -> ``None`` (refuse).
    - **No markers** (``None``): unchanged legacy behavior — only a top-level
      ``table_open`` (``token.level == 0``; a blockquote/list-nested table is
      level >= 1) with a BP-ID header is eligible. The header-sniff is what
      excludes the Status Legend when there are no markers.

    In either path, if exactly one eligible table exists it is canonical; if
    **zero or more than one** do (including a stray 2nd BP table *inside* the
    region), this returns ``None`` and callers refuse to write / report every BP
    file as missing rather than guess (BP-059 refuse-on-ambiguity). A table
    butted directly against another with no blank line is, per GFM, one
    ``table_open`` span."""
    tokens = _MD.parse(text)
    region = _marker_region(tokens)
    if region is _MALFORMED_MARKERS:
        return None

    matches = []
    for k, tok in enumerate(tokens):
        # Only a top-level table is eligible. ``token.level`` is the parser's
        # container-nesting depth: a top-level ``table_open`` is level 0; one
        # nested inside a blockquote/list item is level >= 1.
        if tok.type != "table_open" or tok.level != 0:
            continue
        start, end = tok.map  # [start_line, end_line)
        if region is not None:
            # Region path: canonical by declaration. Keep only tables whose
            # span sits inside the region; do NOT re-sniff the header (renamed
            # headers must still resolve).
            if not (region[0] < start and end <= region[1]):
                continue
            header_cells = _header_cells_of(tokens, k)
            # The in-region table must still be a best-practices table: it has
            # BP-ID rows, or a BP-ID header on a declared-empty placeholder.
            # Otherwise the markers were misplaced around a non-BP table (e.g.
            # the Status Legend) — refuse rather than corrupt it with new rows.
            if not (_row_ids_of(tokens, k) or _looks_like_bp_header(header_cells)):
                print(
                    "ERROR: bp-index markers wrap a table that is not the "
                    "best-practices table (no BP-ID rows, no BP-ID header) — "
                    "refusing to treat it as canonical. Move the markers "
                    "around the BP table.",
                    file=sys.stderr,
                )
                return None
        else:
            # Fallback (marker-free): a top-level table with a BP-ID header.
            header_cells = _header_cells_of(tokens, k)
            if not _looks_like_bp_header(header_cells):
                continue
        matches.append((header_cells, end - 1, _row_ids_of(tokens, k)))
    # Fail-safe: canonical only when unambiguous. Exactly one eligible table ->
    # canonical; zero or more than one -> None (callers refuse / report
    # all-missing, never guess).
    if len(matches) == 1:
        return matches[0]
    return None


def _render_row(header_cells: list[str], b: BPFile) -> str:
    """Render a new table row matching an existing table's column layout.
    Derivable columns (BP-ID, Topic, File, a verification date) are filled
    in; anything else (e.g. curated-only Status/Confidence) gets the literal
    placeholder ``TBD`` — greppable, and can't be mistaken for a real
    curated value (unlike e.g. reusing a legend value such as NEEDS_REVIEW).

    Column 0 is always the BP-ID, by position — this is the cell membership is
    read from (``_row_ids_of``), so a renamed first-column header still lands
    the BP-ID where the next run looks for it (append stays idempotent)."""
    cells = []
    for i, name in enumerate(header_cells):
        key = name.strip().lower()
        if i == 0:
            cells.append(b.display_id)
        elif key in ("topic", "title"):
            cells.append(_table_cell(b.title))
        elif key == "file":
            cells.append(_table_cell(b.path.name))
        elif "date" in key or "verified" in key:
            cells.append(b.date or "TBD")
        else:
            cells.append("TBD")
    return "| " + " | ".join(cells) + " |"


def _bump_total_findings(text: str, new_total: int) -> str:
    """Update a '*Total findings: N*' footer to the post-append count. A
    no-op if the line isn't present. Mechanical count only — the human
    '*Last updated*' verification date is never touched by an append."""
    return _TOTAL_FINDINGS_RE.sub(rf"\g<1>{new_total}", text, count=1)


def atomic_write_text(target: Path, data: str) -> None:
    """Write ``data`` to ``target`` atomically: a same-directory temp file +
    ``os.replace()``. ``os.replace`` is an atomic rename within one filesystem,
    so a crash / full disk / SIGKILL mid-write leaves either the intact old
    file or the complete new file — never a truncated one (a plain
    ``write_text`` truncates first). The temp file must share ``target``'s
    directory so the rename stays on one filesystem. ``newline=""`` writes
    ``data`` byte-for-byte (this repo is LF-only, matching the previous
    ``write_text`` behavior on this platform); ``fsync`` adds durability across
    power loss (not atomicity). ``target`` is resolved through symlinks first,
    so a symlinked target is written through (the link stays intact) rather
    than clobbered by the replace. The temp file's permission bits are set to
    match ``target``'s existing permission bits (or the umask-respecting
    default for a new file) before the swap, so ``os.replace``'s fresh inode
    doesn't silently change permissions. Stdlib only — zero new dependency."""
    real_target = Path(os.path.realpath(target))
    try:
        mode = os.stat(real_target).st_mode & 0o777
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask

    fd, tmp = tempfile.mkstemp(
        dir=str(real_target.parent), prefix=real_target.name, suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, real_target)  # atomic swap
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)  # don't leak the temp file on failure
            except OSError:
                pass


def _write_append(bp_files: list[BPFile], index_path: Path) -> int:
    """Append BP files missing (by BP-ID) from an existing index.md, leaving
    every existing row and all surrounding content byte-for-byte untouched.

    Limitation: read_text()/write_text() use Python's universal-newline
    handling, so any CRLF in the source file is normalized to LF on write.
    A leading BOM is likewise stripped. Not preserved on purpose — this repo
    is LF-only with no BOM."""
    text = index_path.read_text(encoding="utf-8").lstrip("﻿")
    lines = text.split("\n")
    table = _find_bp_table(text)

    if table is None:
        if not bp_files:
            print(
                f"NOTE: {index_path} has no BP-ID table and no BP files "
                "are present — nothing to do.",
                file=sys.stderr,
            )
            return 0
        print(
            f"ERROR: {index_path} exists but no single top-level BP-ID table "
            "could be identified (none found, or more than one) — refusing to "
            "overwrite curated content. Fix the table by hand, or remove the "
            "file to bootstrap a fresh INDEX.",
            file=sys.stderr,
        )
        return 1

    header_cells, last_row_idx, existing_ids = table
    missing = [b for b in bp_files if b.display_id not in existing_ids]
    if not missing:
        print(
            f"INDEX up to date: {len(bp_files)} best practice(s), 0 "
            f"appended -> {index_path}",
            file=sys.stderr,
        )
        return 0

    new_rows = [_render_row(header_cells, b) for b in missing]
    spliced = lines[: last_row_idx + 1] + new_rows + lines[last_row_idx + 1 :]
    out_text = _bump_total_findings(
        "\n".join(spliced), len(existing_ids) + len(missing)
    )
    atomic_write_text(index_path, out_text)
    print(
        f"INDEX appended: {len(missing)} new best practice(s), "
        f"{len(existing_ids)} preserved -> {index_path}",
        file=sys.stderr,
    )
    return 0


def cmd_write(bp_dir: Path, index_path: Path, script_hint: str) -> int:
    bp_files = scan_bp_files(bp_dir)

    if not index_path.is_file():
        # Bootstrap: nothing curated exists yet to protect.
        atomic_write_text(index_path, render_index(bp_files, script_hint))
        print(
            f"INDEX regenerated: {len(bp_files)} best practice(s) -> {index_path}",
            file=sys.stderr,
        )
        return 0

    return _write_append(bp_files, index_path)


def cmd_check(bp_dir: Path, index_path: Path) -> int:
    bp_files = scan_bp_files(bp_dir)
    if not bp_files:
        # Nothing to index — silent happy path.
        return 0
    if not index_path.is_file():
        print(
            f"MISSING: {index_path} does not exist but "
            f"{len(bp_files)} BP file(s) are present — run --write.",
            file=sys.stderr,
        )
        for b in bp_files:
            print(f"  - {b.path.name}", file=sys.stderr)
        return 1
    # Scoped to the canonical BP table (same table --write appends to), not
    # whole-document membership — otherwise a BP-ID first-cell in any other
    # pipe-table would falsely mask a genuinely-missing canonical row. No
    # canonical table found -> empty membership (fail-safe: everything
    # reports missing, mirroring _write_append's refusal in that case).
    table = _find_bp_table(index_path.read_text(encoding="utf-8").lstrip("﻿"))
    indexed = table[2] if table else set()
    missing = [b for b in bp_files if b.display_id not in indexed]
    if not missing:
        # Every BP file has a matching BP-ID row — silent (fire-only-if-missing).
        return 0
    print(
        f"MISSING: {len(missing)} best practice(s) have no INDEX row "
        "— run --write to regenerate:",
        file=sys.stderr,
    )
    for b in missing:
        print(f"  - {b.path.name}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Append missing BP-*.md rows to the best-practices index.md "
            "(--write) or verify every BP-*.md has a matching BP-ID row "
            "(--check)."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write",
        action="store_true",
        help=(
            "Append missing BP-*.md rows to index.md (idempotent, "
            "non-destructive); bootstrap a fresh index.md if none exists."
        ),
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help=(
            "Silent when every BP file has an INDEX row; non-zero and lists "
            "offenders when any BP file is unindexed."
        ),
    )
    parser.add_argument(
        "bp_dir",
        metavar="BP_DIR",
        help="Directory holding BP-*.md and index.md "
        "(e.g. oversight/knowledge/best-practices).",
    )
    args = parser.parse_args()

    bp_dir = Path(args.bp_dir)
    index_path = bp_dir / INDEX_NAME
    script_hint = f"{Path(__file__).name}"

    if not bp_dir.is_dir():
        # Non-fatal: nothing to do if the directory has not been scaffolded.
        print(f"NOTE: directory absent — nothing to index: {bp_dir}", file=sys.stderr)
        return 0

    if args.write:
        return cmd_write(bp_dir, index_path, script_hint)
    return cmd_check(bp_dir, index_path)


if __name__ == "__main__":
    sys.exit(main())
