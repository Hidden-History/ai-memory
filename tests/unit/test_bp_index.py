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
