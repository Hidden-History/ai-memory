"""TASK-077 Part C — auto-memory MEMORY.md index-not-log tests.

Targets the Claude-Code auto-memory file's `--fix-memory-md` path in
tracking_rotate.py (NOT the sanctum MEMORY.md). Lives under repo `tests/`
(CI's testpaths).

- C1: the content-model trigger relocates a paragraph-embedding entry even in an
  UNDER-cap file (validation-lock).
- TD-671: a relocation pointer label strips a leading `### ` markdown header.
- TD-674: a conservation failure injected at the content-set boundary aborts the
  run non-zero and leaves the live file byte-identical with no sibling written.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = (
    _REPO_ROOT / "_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py"
)
_spec = importlib.util.spec_from_file_location("tracking_rotate", _SCRIPT)
tr = importlib.util.module_from_spec(_spec)
sys.modules["tracking_rotate"] = tr
_spec.loader.exec_module(tr)

NOW = datetime(2026, 6, 19)


# ---------------------------------------------------------------------------
# C1 — content-model trigger fires under cap (not only over size cap)
# ---------------------------------------------------------------------------


def test_c1_under_cap_paragraph_entry_is_relocated(tmp_path: Path) -> None:
    md_dir = tmp_path / "memory"
    md_dir.mkdir()
    md = md_dir / "MEMORY.md"
    # Tiny file — far under the 200-line / 25 KB cap — but with ONE entry that is
    # a 3-line paragraph (a content-model / log-shape violation).
    md.write_text(
        "# AI Memory\n\n## Active Work\n\n"
        "**Topic A**: first line of a paragraph entry.\n"
        "second line continues the same thought.\n"
        "third line concludes the paragraph.\n",
        encoding="utf-8",
    )
    lines = len(md.read_text().splitlines())
    assert lines < tr.AUTO_MEMORY_CONTRACT.cap_lines  # provably under cap

    rc = tr.run_fix_memory_md(md, NOW)
    assert rc == 0
    after = md.read_text(encoding="utf-8")
    # The paragraph was relocated to a sibling and replaced by a one-line pointer.
    siblings = [p for p in md_dir.glob("*.md") if p.name != "MEMORY.md"]
    assert siblings, "under-cap paragraph entry was not relocated"
    # The 3rd line lands ONLY in the sibling (the pointer echoes line 1=title,
    # line 2=hook), so it must be gone from the hot index.
    assert "third line concludes the paragraph." not in after
    assert "third line concludes the paragraph." in siblings[0].read_text()
    assert "](" in after and "- [" in after  # pointer present


# ---------------------------------------------------------------------------
# TD-671 — pointer label strips a leading markdown header prefix
# ---------------------------------------------------------------------------


def test_td671_make_pointer_strips_leading_hashes() -> None:
    ptr = tr._make_pointer(
        "### Topic-01\na hook line of detail\nthird line\n", "entry_topic01.md"
    )
    assert ptr == "- [Topic-01](entry_topic01.md) — a hook line of detail\n"
    assert "[###" not in ptr and "[ #" not in ptr


def test_td671_relocated_heading_entry_pointer_has_no_hash(tmp_path: Path) -> None:
    md_dir = tmp_path / "memory"
    md_dir.mkdir()
    md = md_dir / "MEMORY.md"
    md.write_text(
        "# AI Memory\n\n## Notes\n\n"
        "### Heading Entry\nfirst detail line\nsecond detail line\n",
        encoding="utf-8",
    )
    rc = tr.run_fix_memory_md(md, NOW)
    assert rc == 0
    after = md.read_text(encoding="utf-8")
    assert "[Heading Entry]" in after
    assert "[### Heading Entry]" not in after


# ---------------------------------------------------------------------------
# TD-674 — conservation failure at the boundary aborts, file byte-identical
# ---------------------------------------------------------------------------


def test_td674_conservation_failure_aborts_byte_identical(
    tmp_path, monkeypatch
) -> None:
    md_dir = tmp_path / "memory"
    md_dir.mkdir()
    md = md_dir / "MEMORY.md"
    md.write_text(
        "# AI Memory\n\n## Active Work\n\n"
        "**Topic**: UNIQUE_CONSERVED_LINE marker.\n"
        "second line of the entry.\n"
        "third line of the entry.\n",
        encoding="utf-8",
    )
    before_bytes = md.read_bytes()

    # Inject a loss at the content-set boundary: the virtual after-state drops the
    # conserved marker line, so assert_no_content_loss must fail and abort.
    cons = tr._load_conservation()
    real_from_texts = cons.build_content_set_from_texts

    def dropping(texts):
        counts = real_from_texts(texts)
        counts.subtract({"**Topic**: UNIQUE_CONSERVED_LINE marker.": 1})
        return +counts  # unary + drops non-positive counts (the dropped line)

    monkeypatch.setattr(cons, "build_content_set_from_texts", dropping)

    rc = tr.run_fix_memory_md(md, NOW)
    assert rc == 1, "run must abort non-zero on a conservation failure"
    assert md.read_bytes() == before_bytes, "live MEMORY.md was not byte-identical"
    # No sibling was committed (prove-then-commit: nothing written on failure).
    assert [p.name for p in md_dir.glob("*.md")] == ["MEMORY.md"]
