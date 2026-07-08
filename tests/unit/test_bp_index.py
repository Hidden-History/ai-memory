"""Tests for the best-practices INDEX generator (#292 / AIM-010).

bp_index.py rebuilds INDEX.md from disk (idempotent, not append-only) and, in
--check mode, fires only when a BP-*.md file has no INDEX row.
"""

from __future__ import annotations

import importlib.util
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

    index = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert "BP-001" in index and "BP-002" in index
    _, err = capsys.readouterr()
    assert "INDEX regenerated" in err


def test_write_is_idempotent_on_disk(tmp_path):
    _write_bp(tmp_path, "BP-001-a.md", "# A\n")
    _run(["--write", str(tmp_path)])
    first = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    _run(["--write", str(tmp_path)])
    second = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert first == second  # no append-only drift


def test_write_empty_dir_writes_placeholder(tmp_path):
    rc = _run(["--write", str(tmp_path)])
    assert rc == 0
    index = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
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
    assert "INDEX.md" in err


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
# F1/F2 regression (#303 review) — a curated 5-col INDEX must never be
# regenerated, only appended to; --check must match by BP-ID, not filename.
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
    p = tmp_path / "INDEX.md"
    p.write_text(_CURATED_INDEX_FIXTURE, encoding="utf-8")
    return p


def _write_curated_bp_files(tmp_path: Path) -> None:
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")


def test_row_ids_ignores_status_legend_table_and_prose(tmp_path):
    ids = mod._row_ids(_CURATED_INDEX_FIXTURE.split("\n"))
    # Only the Quick Reference table's own rows — not the Status Legend
    # table's rows (**CURRENT** etc.), and not the "BP-004" mentioned in
    # BP-002's Topic prose.
    assert ids == {"BP-001", "BP-002", "BP-003"}


def test_write_preserves_curated_index_and_appends_missing(tmp_path):
    _write_curated_index(tmp_path)
    _write_curated_bp_files(tmp_path)
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n**Date**: 2026-02-01\n")

    rc = _run(["--write", str(tmp_path)])
    assert rc == 0

    after_lines = (tmp_path / "INDEX.md").read_text(encoding="utf-8").split("\n")

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
    first = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    _run(["--write", str(tmp_path)])
    second = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert first == second  # second run finds nothing missing: true no-op


def test_write_refuses_unparseable_existing_index(tmp_path, capsys):
    index_path = tmp_path / "INDEX.md"
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
# Regression (#303): _find_bp_table must bound its row sweep to actual BP
# data rows (not any adjacent pipe-table), and cmd_check must be scoped to
# the canonical table (not whole-document _row_ids).
# ---------------------------------------------------------------------------

# No blank line between the last BP row and a foreign table's header — a
# table butted directly against the BP table with no blank line.
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


def test_write_no_blank_line_before_foreign_table(tmp_path):
    index_path = tmp_path / "INDEX.md"
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

    # New row lands immediately after the last real BP row, before the
    # foreign table's header — not spliced into or after the foreign table.
    new_row_idx = after_lines.index("| BP-004 | Delta Topic | TBD | 2026-02-01 | TBD |")
    gamma_idx = after_lines.index(
        "| BP-003 | Gamma Topic | NEEDS_REVIEW | 2026-01-03 | Informed |"
    )
    status_header_idx = after_lines.index("| Status | Meaning |")
    assert gamma_idx < new_row_idx < status_header_idx


def test_check_not_fooled_by_bp_id_in_foreign_table_row(tmp_path, capsys):
    # A row in a *non-canonical* pipe-table (e.g. a legend) whose first cell
    # happens to be a real BP-ID must not mask a genuinely-missing row in
    # the canonical table — cmd_check must be scoped to the canonical table,
    # not whole-document _row_ids.
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
    index_path = tmp_path / "INDEX.md"
    index_path.write_text(fixture, encoding="utf-8")
    _write_bp(tmp_path, "BP-001-a.md", "# Alpha Topic\n")
    _write_bp(tmp_path, "BP-002-b.md", "# Beta Topic\n")
    _write_bp(tmp_path, "BP-003-c.md", "# Gamma Topic\n")
    _write_bp(tmp_path, "BP-004-new.md", "# Delta Topic\n")

    rc = _run(["--check", str(tmp_path)])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "BP-004-new.md" in err
