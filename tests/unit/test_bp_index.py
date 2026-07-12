"""Tests for the best-practices INDEX generator (#292 / AIM-010).

bp_index.py rebuilds INDEX.md from disk (idempotent, not append-only) and, in
--check mode, fires only when a BP-*.md file has no INDEX row.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "_ai-memory"
    / "skills"
    / "aim-best-practices-researcher"
    / "scripts"
    / "bp_index.py"
)


def _load_module():
    for key in list(sys.modules.keys()):
        if "bp_index_under_test" in key:
            del sys.modules[key]
    spec = importlib.util.spec_from_file_location("bp_index_under_test", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _write_bp(bp_dir: Path, name: str, body: str = "") -> Path:
    p = bp_dir / name
    p.write_text(body, encoding="utf-8")
    return p


def _run(argv: list[str]) -> int:
    old = sys.argv
    sys.argv = ["bp_index.py", *argv]
    try:
        return mod.main()
    finally:
        sys.argv = old


# ---------------------------------------------------------------------------
# Scan + render
# ---------------------------------------------------------------------------


def test_script_exists():
    assert _SCRIPT.exists(), f"script not found: {_SCRIPT}"


def test_scan_parses_id_title_date_sorted(tmp_path):
    _write_bp(
        tmp_path,
        "BP-002-httpx-timeouts.md",
        "# Research Report: HTTPX Timeouts\n\n**Date**: 2026-05-30\n",
    )
    _write_bp(
        tmp_path,
        "BP-010-python-typing.md",
        "# Research Report: Python Typing\n\n**Date**: 2026-06-01\n",
    )
    _write_bp(tmp_path, "BP-1-no-heading.md", "just body, no H1\n")

    files = mod.scan_bp_files(tmp_path)

    assert [f.numeric_id for f in files] == [1, 2, 10]  # ascending
    assert files[0].title == "no heading"  # slug fallback
    assert files[1].title == "HTTPX Timeouts"  # H1, prefix stripped
    assert files[1].date == "2026-05-30"
    assert files[2].date == "2026-06-01"
    assert files[0].display_id == "BP-001"


def test_non_bp_files_ignored(tmp_path):
    _write_bp(tmp_path, "BP-001-real.md", "# Real\n")
    _write_bp(tmp_path, "README.md", "not a bp\n")
    _write_bp(tmp_path, "INDEX.md", "existing index\n")

    files = mod.scan_bp_files(tmp_path)
    assert [f.path.name for f in files] == ["BP-001-real.md"]


def test_render_is_idempotent(tmp_path):
    _write_bp(tmp_path, "BP-003-foo.md", "# Foo\n**Date**: 2026-01-01\n")
    files = mod.scan_bp_files(tmp_path)
    first = mod.render_index(files, "bp_index.py")
    second = mod.render_index(mod.scan_bp_files(tmp_path), "bp_index.py")
    assert first == second
    assert "BP-003" in first


def test_pipe_in_title_is_escaped(tmp_path):
    _write_bp(tmp_path, "BP-004-x.md", "# A | B pipe title\n")
    out = mod.render_index(mod.scan_bp_files(tmp_path), "bp_index.py")
    assert "A \\| B pipe title" in out


# ---------------------------------------------------------------------------
# --write
# ---------------------------------------------------------------------------


def test_write_creates_index_with_all_rows(tmp_path, capsys):
    _write_bp(tmp_path, "BP-001-a.md", "# A\n")
    _write_bp(tmp_path, "BP-002-b.md", "# B\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0

    index = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "BP-001" in index and "BP-002" in index
    _, err = capsys.readouterr()
    assert "INDEX regenerated" in err


def test_write_is_idempotent_on_disk(tmp_path):
    _write_bp(tmp_path, "BP-001-a.md", "# A\n")
    _run(["--write", str(tmp_path)])
    first = (tmp_path / "index.md").read_text(encoding="utf-8")
    _run(["--write", str(tmp_path)])
    second = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert first == second  # no append-only drift


def test_write_empty_dir_writes_placeholder(tmp_path):
    rc = _run(["--write", str(tmp_path)])
    assert rc == 0
    index = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "No best practices recorded yet" in index


# ---------------------------------------------------------------------------
# --check  (fire-only-if-missing)
# ---------------------------------------------------------------------------


def test_check_silent_when_all_indexed(tmp_path, capsys):
    _write_bp(tmp_path, "BP-001-a.md", "# A\n")
    _write_bp(tmp_path, "BP-002-b.md", "# B\n")
    _run(["--write", str(tmp_path)])
    capsys.readouterr()  # drain the write NOTE

    rc = _run(["--check", str(tmp_path)])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out == "" and err == ""  # silent happy path


def test_check_fires_on_unindexed_bp(tmp_path, capsys):
    _write_bp(tmp_path, "BP-001-a.md", "# A\n")
    _run(["--write", str(tmp_path)])
    capsys.readouterr()
    # Add a new BP without regenerating the INDEX.
    _write_bp(tmp_path, "BP-002-new.md", "# New\n")

    rc = _run(["--check", str(tmp_path)])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "BP-002-new.md" in err


def test_check_fires_when_index_absent(tmp_path, capsys):
    _write_bp(tmp_path, "BP-001-a.md", "# A\n")

    rc = _run(["--check", str(tmp_path)])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "index.md" in err


def test_check_silent_when_no_bp_files(tmp_path, capsys):
    rc = _run(["--check", str(tmp_path)])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out == "" and err == ""


def test_missing_dir_is_non_fatal(tmp_path, capsys):
    missing = tmp_path / "does-not-exist"
    assert _run(["--check", str(missing)]) == 0
    assert _run(["--write", str(missing)]) == 0
    _, err = capsys.readouterr()
    assert "absent" in err


def test_requires_a_mode(tmp_path):
    import pytest

    with pytest.raises(SystemExit):
        _run([str(tmp_path)])  # neither --write nor --check


# ---------------------------------------------------------------------------
# A curated multi-column INDEX must never be regenerated, only appended to;
# --check matches by BP-ID (a table row's first cell), not filename or a
# BP-ID mentioned in prose.
# ---------------------------------------------------------------------------

# Structurally faithful to the real oversight/knowledge/best-practices/
# INDEX.md: 5-col curated table (Status/Confidence are hand-curated, not
# derivable from BP-*.md on disk), a Status Legend table (different header,
# must not be mistaken for the BP table), Usage/Finding-Files sections, and
# a mechanical "Total findings" footer separate from the human "Last
# updated" verification date. BP-002's Topic deliberately mentions another
# BP-ID in prose to guard against whole-document substring matching.
_CURATED_INDEX_FIXTURE = (
    "# Best Practices Index\n"
    "\n"
    "This index tracks all researched best practices for this project.\n"
    "\n"
    "## Quick Reference\n"
    "\n"
    "| BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "|-------|-------|--------|---------------|------------|\n"
    "| BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |\n"
    "| BP-002 | Beta Topic (extends BP-004 concept) | CURRENT | 2026-01-02 | Informed |\n"
    "| BP-003 | Gamma Topic | NEEDS_REVIEW | 2026-01-03 | Informed |\n"
    "\n"
    "## Status Legend\n"
    "\n"
    "| Status | Meaning |\n"
    "|--------|---------|\n"
    "| **CURRENT** | Actively applicable, verified within 6 months |\n"
    "| **NEEDS_REVIEW** | Older than 6 months, should re-verify |\n"
    "\n"
    "## Usage\n"
    "\n"
    "1. **Before researching**: Check this index for existing findings\n"
    "\n"
    "## Finding Files\n"
    "\n"
    "All findings are stored in this directory as `BP-XXX-[topic].md`\n"
    "\n"
    "---\n"
    "\n"
    "*Last updated: 2026-01-03*\n"
    "*Total findings: 3*\n"
)


def _write_curated_index(tmp_path: Path) -> Path:
    p = tmp_path / "index.md"
    p.write_text(_CURATED_INDEX_FIXTURE, encoding="utf-8")
    return p


def _write_curated_bp_files(tmp_path: Path) -> None:
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")


def test_canonical_membership_excludes_status_legend_and_prose():
    table = mod._find_bp_table(_CURATED_INDEX_FIXTURE)
    assert table is not None
    _, _, ids = table
    # Membership is scoped to the canonical BP-ID table's source-line span
    # (from the parser): the Status Legend is a separate table (a blank line
    # precedes it, so it is a distinct table_open), and the "BP-004" in
    # BP-002's Topic is prose in a non-first cell — neither is a canonical row.
    assert ids == {"BP-001", "BP-002", "BP-003"}


def test_write_preserves_curated_index_and_appends_missing(tmp_path):
    _write_curated_index(tmp_path)
    _write_curated_bp_files(tmp_path)
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n**Date**: 2026-02-01\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0

    after_lines = (tmp_path / "index.md").read_text(encoding="utf-8").split("\n")

    # Every original line survives byte-for-byte, except the mechanically
    # bumped footer count (checked separately below).
    for line in _CURATED_INDEX_FIXTURE.split("\n"):
        if line.startswith("*Total findings:"):
            continue
        assert line in after_lines, f"original line dropped: {line!r}"

    # New row appended: BP-ID/Topic/date derived, curated-only columns (Status,
    # Confidence) get the TBD placeholder — never a guessed legend value.
    assert "| BP-004 | Delta Topic | TBD | 2026-02-01 | TBD |" in after_lines

    # Footer count mechanically bumped 3 -> 4; human verification date
    # untouched (an automated append is not a human verification event).
    assert "*Total findings: 4*" in after_lines
    assert "*Last updated: 2026-01-03*" in after_lines

    # A curated file must never be marked as tool-generated.
    assert "GENERATED by bp_index.py" not in "\n".join(after_lines)


# ---------------------------------------------------------------------------
# F-1: real installs on this machine (live + shipped templates) name the
# curated file lowercase `index.md`. On a case-sensitive filesystem — this
# one included — INDEX_NAME must resolve to that real file, not an uppercase
# variant, or --write treats the curated index as absent and bootstraps a
# wrong-schema rival file alongside it, orphaning the curated content. This
# is a genuine repro on this filesystem, not a simulation.
# ---------------------------------------------------------------------------


def test_write_targets_real_lowercase_index_no_uppercase_sibling(tmp_path):
    _write_curated_index(tmp_path)  # writes tmp_path / "index.md"
    _write_curated_bp_files(tmp_path)
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n**Date**: 2026-02-01\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0

    # The curated lowercase file was found and appended to, not orphaned.
    after = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "| BP-004 | Delta Topic | TBD | 2026-02-01 | TBD |" in after
    assert "GENERATED by bp_index.py" not in after  # still the curated file

    # No wrong-schema uppercase sibling was bootstrapped alongside it.
    index_variants = sorted(p.name for p in tmp_path.glob("*ndex.md"))
    assert index_variants == ["index.md"]


def test_write_is_true_noop_when_nothing_missing(tmp_path):
    index_path = _write_curated_index(tmp_path)
    _write_curated_bp_files(tmp_path)
    before = index_path.read_text(encoding="utf-8")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0
    assert index_path.read_text(encoding="utf-8") == before  # byte-identical


def test_write_append_is_idempotent(tmp_path):
    _write_curated_index(tmp_path)
    _write_curated_bp_files(tmp_path)
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n")

    _run(["--write", str(tmp_path)])
    first = (tmp_path / "index.md").read_text(encoding="utf-8")
    _run(["--write", str(tmp_path)])
    second = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert first == second  # second run finds nothing missing: true no-op


def test_write_refuses_unparseable_existing_index(tmp_path, capsys):
    index_path = tmp_path / "index.md"
    index_path.write_text("not a table, just prose\n", encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# A\n")
    before = index_path.read_text(encoding="utf-8")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 1
    assert index_path.read_text(encoding="utf-8") == before  # untouched
    _, err = capsys.readouterr()
    assert "refusing to overwrite" in err


def test_check_id_aware_silent_on_curated_index(tmp_path, capsys):
    _write_curated_index(tmp_path)
    _write_curated_bp_files(tmp_path)

    rc = _run(["--check", str(tmp_path)])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out == "" and err == ""


def test_check_not_fooled_by_prose_mention(tmp_path, capsys):
    # BP-002's Topic cell mentions "BP-004" in prose; BP-004 itself has no
    # row. A whole-document substring/filename match would wrongly treat
    # that mention as an INDEX row for BP-004 — id-aware first-cell matching
    # must not be fooled.
    _write_curated_index(tmp_path)
    _write_curated_bp_files(tmp_path)
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n")

    rc = _run(["--check", str(tmp_path)])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "BP-004-new.md" in err


# ---------------------------------------------------------------------------
# Table boundaries come from the GFM parser's source map (token.map). Per the
# GFM tables extension, contiguous pipe rows with no blank line between them
# form ONE table; a blank line starts a new table. cmd_check reads membership
# only from the canonical table's span, so a BP-ID first cell elsewhere in the
# document (a separate table) cannot mask a genuinely-missing canonical row.
# ---------------------------------------------------------------------------

# A foreign table (non-BP-ID header) butted directly against the BP table with
# no blank line between them. Per GFM this is a single table, so the foreign
# rows fall inside the canonical table's source-map span.
_ADJACENT_TABLE_INDEX_FIXTURE = (
    "# Best Practices Index\n"
    "\n"
    "| BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "|-------|-------|--------|---------------|------------|\n"
    "| BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |\n"
    "| BP-002 | Beta Topic | CURRENT | 2026-01-02 | Informed |\n"
    "| BP-003 | Gamma Topic | NEEDS_REVIEW | 2026-01-03 | Informed |\n"
    "| Status | Meaning |\n"
    "|--------|---------|\n"
    "| **CURRENT** | Actively applicable, verified within 6 months |\n"
)


def test_write_butted_foreign_table_appends_at_merged_table_end(tmp_path):
    index_path = tmp_path / "index.md"
    index_path.write_text(_ADJACENT_TABLE_INDEX_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n**Date**: 2026-02-01\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0

    after_lines = index_path.read_text(encoding="utf-8").split("\n")

    # Every foreign-table line survives byte-for-byte.
    for line in _ADJACENT_TABLE_INDEX_FIXTURE.split("\n"):
        if (
            line.startswith("| Status")
            or line.startswith("|--------")
            or line.startswith("| **CURRENT**")
        ):
            assert line in after_lines, f"foreign table line dropped: {line!r}"

    # The foreign rows' first cells (Status, **CURRENT**) are not BP-IDs, so
    # they are never counted as members. Because GFM treats the butted rows as
    # part of the same table, the new row appends at the end of that single
    # merged table — after the foreign rows, not before them.
    new_row_idx = after_lines.index("| BP-004 | Delta Topic | TBD | 2026-02-01 | TBD |")
    current_idx = after_lines.index(
        "| **CURRENT** | Actively applicable, verified within 6 months |"
    )
    assert new_row_idx > current_idx


def test_check_not_fooled_by_bp_id_in_foreign_table_row(tmp_path, capsys):
    # A row in a *non-canonical* pipe-table (e.g. a legend) whose first cell
    # happens to be a real BP-ID must not mask a genuinely-missing row in
    # the canonical table — cmd_check must be scoped to the canonical table,
    # not whole-document membership.
    fixture = (
        "# Best Practices Index\n"
        "\n"
        "| BP-ID | Topic | Status | Last Verified | Confidence |\n"
        "|-------|-------|--------|---------------|------------|\n"
        "| BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |\n"
        "| BP-002 | Beta Topic | CURRENT | 2026-01-02 | Informed |\n"
        "| BP-003 | Gamma Topic | NEEDS_REVIEW | 2026-01-03 | Informed |\n"
        "\n"
        "## Unrelated Table\n"
        "\n"
        "| BP-ID | Note |\n"
        "|-------|------|\n"
        "| BP-004 | not a real canonical index row |\n"
    )
    index_path = tmp_path / "index.md"
    index_path.write_text(fixture, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n")

    rc = _run(["--check", str(tmp_path)])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "BP-004-new.md" in err


# ---------------------------------------------------------------------------
# A non-BP-ID row *inside* the canonical table (a divider/note/spacer) is
# still within the table's source-map span, so BP rows after it are counted;
# the divider's first cell simply doesn't match the BP-ID pattern.
# ---------------------------------------------------------------------------

# A divider row between BP-002 and BP-003 whose first cell isn't a BP-ID.
_MIDTABLE_DIVIDER_INDEX_FIXTURE = (
    "# Best Practices Index\n"
    "\n"
    "| BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "|-------|-------|--------|---------------|------------|\n"
    "| BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |\n"
    "| BP-002 | Beta Topic | CURRENT | 2026-01-02 | Informed |\n"
    "| **Archived below** | | | | |\n"
    "| BP-003 | Gamma Topic | NEEDS_REVIEW | 2026-01-03 | Informed |\n"
)


def test_write_mid_table_divider_does_not_drop_or_duplicate_row(tmp_path):
    index_path = tmp_path / "index.md"
    index_path.write_text(_MIDTABLE_DIVIDER_INDEX_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0

    after = index_path.read_text(encoding="utf-8")
    # BP-003's original row survives, uncounted-as-missing — no duplicate
    # appended after it.
    assert after.count("BP-003") == 1
    assert "| BP-003 | Gamma Topic | NEEDS_REVIEW | 2026-01-03 | Informed |" in after
    # The divider row itself is untouched.
    assert "| **Archived below** | | | | |" in after


def test_check_mid_table_divider_not_false_flagged_missing(tmp_path, capsys):
    index_path = tmp_path / "index.md"
    index_path.write_text(_MIDTABLE_DIVIDER_INDEX_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")

    rc = _run(["--check", str(tmp_path)])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out == "" and err == ""  # BP-003 must not be false-flagged missing


# ---------------------------------------------------------------------------
# A second BP-ID-headed table butted directly against the canonical one with
# no blank line between them. Per the GFM tables extension this is a single
# table: the second header/separator and its data rows become body rows of the
# one table. So a butted "| BP-050 |" row is a genuine member of the canonical
# table, and a new row appends at the end of that single merged table.
# ---------------------------------------------------------------------------

# The "| BP-050 |" row is butted against the canonical table with no blank
# line, so per GFM it is a body row of the one table.
_BUTTED_BPID_FOREIGN_TABLE_FIXTURE = (
    "# Best Practices Index\n"
    "\n"
    "| BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "|-------|-------|--------|---------------|------------|\n"
    "| BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |\n"
    "| BP-002 | Beta Topic | CURRENT | 2026-01-02 | Informed |\n"
    "| BP-003 | Gamma Topic | NEEDS_REVIEW | 2026-01-03 | Informed |\n"
    "| BP-ID | Note |\n"
    "|-------|------|\n"
    "| BP-050 | archived cross-reference, not a canonical row |\n"
)


def test_check_butted_bp_id_row_counts_as_member(tmp_path, capsys):
    # Per GFM, the butted "| BP-050 |" row is a body row of the one canonical
    # table, so BP-050 is a genuine member. --check must be silent when a
    # BP-050 file exists on disk — the row already indexes it.
    index_path = tmp_path / "index.md"
    index_path.write_text(_BUTTED_BPID_FOREIGN_TABLE_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")
    _write_bp(tmp_path, "BP-050-d.md", "# Delta Topic\n")

    rc = _run(["--check", str(tmp_path)])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out == "" and err == ""


def test_write_butted_bp_id_table_appends_after_butted_rows(tmp_path):
    index_path = tmp_path / "index.md"
    index_path.write_text(_BUTTED_BPID_FOREIGN_TABLE_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")
    # BP-050 already has a member row (the butted row), so it must NOT be
    # re-appended; BP-099 is genuinely missing and must be appended.
    _write_bp(tmp_path, "BP-050-e.md", "# Epsilon Topic\n")
    _write_bp(tmp_path, "BP-099-new.md", "# Omega Topic\n**Date**: 2026-02-01\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0

    after = index_path.read_text(encoding="utf-8")
    after_lines = after.split("\n")

    # The butted rows survive byte-for-byte, exactly once — not duplicated,
    # not mutated.
    for line in (
        "| BP-ID | Note |",
        "|-------|------|",
        "| BP-050 | archived cross-reference, not a canonical row |",
    ):
        assert after_lines.count(line) == 1, f"butted table line altered: {line!r}"

    # BP-050 is already a member (the butted row), so its file is deduped —
    # no second BP-050 row is appended.
    assert "Epsilon Topic" not in after

    # The genuinely-missing BP-099 appends at the end of the single merged
    # table — after the butted BP-050 row.
    new_row_idx = after_lines.index("| BP-099 | Omega Topic | TBD | 2026-02-01 | TBD |")
    butted_row_idx = after_lines.index(
        "| BP-050 | archived cross-reference, not a canonical row |"
    )
    assert new_row_idx > butted_row_idx


# ---------------------------------------------------------------------------
# Two BP-ID-headed tables separated by a blank line are two DISTINCT top-level
# ``table_open``s (both level 0). Per the BP-059 fail-safe, more than one
# top-level BP-ID table is ambiguous -> _find_bp_table refuses (returns None)
# rather than guessing which is canonical. This intentionally overrides the
# old "pick the first" premise: on multiple top-level candidates we refuse,
# never silently pick one and risk appending to / trusting the wrong table.
# ---------------------------------------------------------------------------

_BLANK_DELIMITED_SECOND_BP_TABLE_FIXTURE = (
    "# Best Practices Index\n"
    "\n"
    "| BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "|-------|-------|--------|---------------|------------|\n"
    "| BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |\n"
    "| BP-002 | Beta Topic | CURRENT | 2026-01-02 | Informed |\n"
    "\n"
    "## Archived\n"
    "\n"
    "| BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "|-------|-------|--------|---------------|------------|\n"
    "| BP-090 | Archived Topic | ARCHIVED | 2025-01-01 | Informed |\n"
)


def test_blank_delimited_two_top_level_bp_tables_are_ambiguous_refuse():
    # Both tables are top-level (level 0) and BP-ID-headed -> two canonical
    # candidates -> ambiguous -> None (refuse-on-ambiguity, never guess).
    assert mod._find_bp_table(_BLANK_DELIMITED_SECOND_BP_TABLE_FIXTURE) is None


def test_write_two_top_level_bp_tables_refuses(tmp_path, capsys):
    # Two top-level BP-ID tables -> ambiguous -> --write refuses (rc 1),
    # leaving the file byte-identical (curated content preserved).
    index_path = tmp_path / "index.md"
    index_path.write_text(_BLANK_DELIMITED_SECOND_BP_TABLE_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    before = index_path.read_text(encoding="utf-8")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 1
    assert index_path.read_text(encoding="utf-8") == before  # byte-identical
    _, err = capsys.readouterr()
    assert "refusing to overwrite" in err


# ---------------------------------------------------------------------------
# Encoding robustness: a leading UTF-8 BOM and CRLF line endings must not
# hide the canonical table. The BOM is stripped and CRLF is normalized to LF
# (via read_text's universal newlines) before parsing.
# ---------------------------------------------------------------------------


def test_check_silent_on_bom_prefixed_index(tmp_path, capsys):
    index_path = tmp_path / "index.md"
    index_path.write_text("﻿" + _CURATED_INDEX_FIXTURE, encoding="utf-8")
    _write_curated_bp_files(tmp_path)

    rc = _run(["--check", str(tmp_path)])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out == "" and err == ""  # BOM stripped: table still found, all indexed


def test_check_silent_on_crlf_index(tmp_path, capsys):
    index_path = tmp_path / "index.md"
    index_path.write_bytes(_CURATED_INDEX_FIXTURE.replace("\n", "\r\n").encode("utf-8"))
    _write_curated_bp_files(tmp_path)

    rc = _run(["--check", str(tmp_path)])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out == "" and err == ""  # CRLF normalized: table still found, all indexed


# ---------------------------------------------------------------------------
# Blockquote-nested INDEX (#303): a table written inside a blockquote
# (``> | BP-XXX | … |``) tokenizes as a table *inside* a blockquote
# (``table_open.level >= 1``). Canonical selection is top-level-only, so a
# nested table is NOT selected as canonical — the BP-059 fail-safe. When the
# nested table is the only BP-ID table present, ``_find_bp_table`` returns
# None: --write refuses (it never splices an un-prefixed row into a blockquoted
# table, the A-F1/E-F2 corruption) and --check reports every BP file as
# unindexed rather than trusting a nested table.
# ---------------------------------------------------------------------------

_BLOCKQUOTE_NESTED_INDEX_FIXTURE = (
    "# Best Practices Index\n"
    "\n"
    "> | BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "> |-------|-------|--------|---------------|------------|\n"
    "> | BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |\n"
    "> | BP-002 | Beta Topic | CURRENT | 2026-01-02 | Informed |\n"
)


def test_blockquote_nested_table_not_selected_as_canonical():
    # The blockquote-nested BP table is level>=1, so it is not top-level and
    # not eligible as canonical. It is the only BP table here, so
    # _find_bp_table returns None (fail-safe: nested tables are never
    # canonical — the real fix for #303, not membership-from-raw-lines).
    assert mod._find_bp_table(_BLOCKQUOTE_NESTED_INDEX_FIXTURE) is None


def test_write_blockquote_index_refuses(tmp_path, capsys):
    # The only BP table is blockquote-nested -> no top-level canonical table ->
    # --write refuses (rc 1) and leaves the file byte-identical (a refusal
    # writes nothing; the old bug spliced an un-prefixed row into it instead).
    index_path = tmp_path / "index.md"
    index_path.write_text(_BLOCKQUOTE_NESTED_INDEX_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    before = index_path.read_text(encoding="utf-8")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 1
    assert index_path.read_text(encoding="utf-8") == before  # byte-identical
    _, err = capsys.readouterr()
    assert "refusing to overwrite" in err


def test_check_blockquote_index_flags_as_unindexed(tmp_path, capsys):
    # A nested table is not trusted as the canonical index -> --check reports
    # both BP files as unindexed (fail-safe), not the old silent pass.
    index_path = tmp_path / "index.md"
    index_path.write_text(_BLOCKQUOTE_NESTED_INDEX_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")

    rc = _run(["--check", str(tmp_path)])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "BP-001-a.md" in err and "BP-002-b.md" in err


# ---------------------------------------------------------------------------
# E-F1: a nested (blockquoted) example table precedes the real top-level table.
# Top-level-only selection must skip the nested example and select the real
# table — the nested BP-999 is never treated as canonical, and appends target
# the real top-level table.
# ---------------------------------------------------------------------------

_NESTED_EXAMPLE_BEFORE_REAL_TABLE_FIXTURE = (
    "# Best Practices Index\n"
    "\n"
    "Here is an example of the index format:\n"
    "\n"
    "> | BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "> |-------|-------|--------|---------------|------------|\n"
    "> | BP-999 | Example Row | CURRENT | 2026-01-01 | Verified |\n"
    "\n"
    "| BP-ID | Topic | Status | Last Verified | Confidence |\n"
    "|-------|-------|--------|---------------|------------|\n"
    "| BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |\n"
)


def test_nested_example_before_real_table_selects_and_appends_top_level(tmp_path):
    # Selection skips the level>=1 blockquoted example (BP-999) and picks the
    # real top-level table (BP-001) — the E-F1 repro.
    table = mod._find_bp_table(_NESTED_EXAMPLE_BEFORE_REAL_TABLE_FIXTURE)
    assert table is not None
    _, _, ids = table
    assert ids == {"BP-001"}  # nested BP-999 example never selected

    index_path = tmp_path / "index.md"
    index_path.write_text(_NESTED_EXAMPLE_BEFORE_REAL_TABLE_FIXTURE, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-new.md", "# Beta Topic\n**Date**: 2026-02-01\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0
    after = index_path.read_text(encoding="utf-8")
    after_lines = after.split("\n")

    # BP-002 appended into the real top-level table, after BP-001's row.
    new_idx = after_lines.index("| BP-002 | Beta Topic | TBD | 2026-02-01 | TBD |")
    real_idx = after_lines.index(
        "| BP-001 | Alpha Topic | CURRENT | 2026-01-01 | Verified |"
    )
    assert new_idx > real_idx
    # The blockquoted example is untouched — never selected, never gained a row.
    assert "> | BP-999 | Example Row | CURRENT | 2026-01-01 | Verified |" in after_lines
    assert after.count("BP-999") == 1


# ---------------------------------------------------------------------------
# Atomic write (BP-059 write-safety #5): both write paths go through
# atomic_write_text (same-dir temp file + os.replace), so an interruption
# leaves the old file or the new file — never a truncated one — and no temp
# file is leaked on the happy path.
# ---------------------------------------------------------------------------


def test_atomic_write_leaves_original_intact_on_replace_failure(tmp_path, monkeypatch):
    # Simulate a crash at the os.replace step: the original INDEX.md must be
    # byte-identical (never truncated), and the temp file must not be leaked.
    import pytest

    _write_curated_index(tmp_path)
    _write_curated_bp_files(tmp_path)
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n")  # forces an append
    index_path = tmp_path / "index.md"
    before = index_path.read_text(encoding="utf-8")

    def _boom(src, dst):
        raise OSError("simulated crash before rename completes")

    monkeypatch.setattr(mod.os, "replace", _boom)

    with pytest.raises(OSError):
        _run(["--write", str(tmp_path)])

    # Old file preserved byte-for-byte — atomic write never truncates in place.
    assert index_path.read_text(encoding="utf-8") == before
    # No leaked temp file (the except clause unlinks it on failure).
    assert list(tmp_path.glob("index.md*.tmp")) == []


def test_atomic_write_leaves_no_temp_file_on_success(tmp_path):
    # A normal append cleans up its temp file (os.replace consumes it).
    _write_curated_index(tmp_path)
    _write_curated_bp_files(tmp_path)
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("index.md*.tmp")) == []
    assert "BP-004" in (tmp_path / "index.md").read_text(encoding="utf-8")


def test_atomic_write_preserves_existing_file_mode(tmp_path):
    # os.replace() gives the new inode the temp file's mode unless we fix it
    # up — a pre-existing 644 file must stay 644, not become mkstemp's 600.
    target = tmp_path / "INDEX.md"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o644)

    mod.atomic_write_text(target, "new")

    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_new_file_respects_umask_not_0600(tmp_path):
    # A brand-new file should get the umask-respecting default (like a plain
    # open()/write_text() would), not mkstemp's fixed 0600.
    target = tmp_path / "INDEX.md"
    assert not target.exists()

    mod.atomic_write_text(target, "new")

    umask = os.umask(0)
    os.umask(umask)
    expected_mode = 0o666 & ~umask
    assert stat.S_IMODE(target.stat().st_mode) == expected_mode


def test_atomic_write_through_symlink_writes_through(tmp_path):
    # A symlinked target must be written through to the real file — not
    # clobbered into a regular file by os.replace().
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real_file = real_dir / "INDEX.md"
    real_file.write_text("old", encoding="utf-8")

    link_dir = tmp_path / "linked"
    link_dir.mkdir()
    link = link_dir / "INDEX.md"
    link.symlink_to(real_file)

    mod.atomic_write_text(link, "new")

    assert link.is_symlink()
    assert os.path.realpath(link) == str(real_file)
    assert real_file.read_text(encoding="utf-8") == "new"
