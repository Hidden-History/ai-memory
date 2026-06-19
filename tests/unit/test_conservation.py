"""
Unit tests for the conservation.py helper module.

Imported via importlib (same pattern as test_tracking_rotate_skill.py) so the
module does not need to be on sys.path.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "_ai-memory/pov/skills/aim-tracking-rotate/scripts"
)
_CONSERVATION_PATH = _SCRIPTS_DIR / "conservation.py"

_cspec = importlib.util.spec_from_file_location("conservation", _CONSERVATION_PATH)
_cmod = importlib.util.module_from_spec(_cspec)
sys.modules["conservation"] = _cmod
_cspec.loader.exec_module(_cmod)

build_id_manifest = _cmod.build_id_manifest
assert_no_id_loss = _cmod.assert_no_id_loss
build_content_set = _cmod.build_content_set
assert_no_content_loss = _cmod.assert_no_content_loss
ENTRY_ID_RE = _cmod.ENTRY_ID_RE


# ---------------------------------------------------------------------------
# build_id_manifest
# ---------------------------------------------------------------------------


def test_build_id_manifest_empty_list() -> None:
    counts = build_id_manifest([])
    assert counts == Counter()


def test_build_id_manifest_nonexistent_path(tmp_path: Path) -> None:
    ghost = tmp_path / "does_not_exist.md"
    counts = build_id_manifest([ghost])
    assert counts == Counter()


def test_build_id_manifest_single_file(tmp_path: Path) -> None:
    f = tmp_path / "log.md"
    f.write_text(
        "### DEC-001 — First\ncontent\n\n### DEC-002 — Second\nmore\n",
        encoding="utf-8",
    )
    counts = build_id_manifest([f])
    assert counts["DEC-001"] == 1
    assert counts["DEC-002"] == 1
    assert counts.total() >= 2


def test_build_id_manifest_multiple_files(tmp_path: Path) -> None:
    live = tmp_path / "live.md"
    shard = tmp_path / "shard.md"
    live.write_text("### DEC-010 — Live\nstuff\n", encoding="utf-8")
    shard.write_text(
        "### DEC-001 — Old\narchived\n### DEC-002 — Older\narchived\n", encoding="utf-8"
    )
    counts = build_id_manifest([live, shard])
    assert counts["DEC-010"] >= 1
    assert counts["DEC-001"] >= 1
    assert counts["DEC-002"] >= 1


def test_build_id_manifest_token_variety(tmp_path: Path) -> None:
    f = tmp_path / "register.md"
    f.write_text(
        "| BLK-001 | active |\n| RISK-042 | open |\n| TD-655 | open |\n",
        encoding="utf-8",
    )
    counts = build_id_manifest([f])
    assert "BLK-001" in counts
    assert "RISK-042" in counts
    assert "TD-655" in counts


# ---------------------------------------------------------------------------
# assert_no_id_loss
# ---------------------------------------------------------------------------


def test_assert_no_id_loss_identical() -> None:
    before = Counter({"DEC-001": 1, "DEC-002": 1})
    after = Counter({"DEC-001": 1, "DEC-002": 1})
    assert_no_id_loss(before, after)  # must not raise


def test_assert_no_id_loss_after_superset() -> None:
    before = Counter({"DEC-001": 1})
    after = Counter({"DEC-001": 2, "DEC-999": 5})
    assert_no_id_loss(before, after)  # more copies in after is fine


def test_assert_no_id_loss_no_loss_empty_before() -> None:
    assert_no_id_loss(Counter(), Counter())


def test_assert_no_id_loss_raises_on_loss() -> None:
    before = Counter({"DEC-001": 1, "DEC-002": 1})
    after = Counter({"DEC-001": 1})  # DEC-002 dropped
    with pytest.raises(AssertionError, match="DEC-002"):
        assert_no_id_loss(before, after)


def test_assert_no_id_loss_raises_lists_up_to_ten(tmp_path: Path) -> None:
    # More than 10 IDs lost — sample is capped at 10.
    before = Counter({f"DEC-{i:03d}": 1 for i in range(15)})
    after: Counter[str] = Counter()
    with pytest.raises(AssertionError, match="15 entry ID"):
        assert_no_id_loss(before, after)


# ---------------------------------------------------------------------------
# build_content_set
# ---------------------------------------------------------------------------


def test_build_content_set_empty() -> None:
    result = build_content_set([])
    assert result == Counter()


def test_build_content_set_strips_blank_lines(tmp_path: Path) -> None:
    f = tmp_path / "mem.md"
    f.write_text("\nline one\n\nline two\n", encoding="utf-8")
    result = build_content_set([f])
    assert "line one" in result
    assert "line two" in result
    # Blank lines are NOT in the set
    assert "" not in result


def test_build_content_set_union_across_files(tmp_path: Path) -> None:
    main_md = tmp_path / "MEMORY.md"
    sibling = tmp_path / "feedback_example.md"
    main_md.write_text(
        "# Index\n- [Ex](feedback_example.md) — hook\n", encoding="utf-8"
    )
    sibling.write_text("Full detail text about the example.\n", encoding="utf-8")
    result = build_content_set([main_md, sibling])
    assert "# Index" in result
    assert "Full detail text about the example." in result


def test_build_content_set_nonexistent_path_ignored(tmp_path: Path) -> None:
    ghost = tmp_path / "ghost.md"
    result = build_content_set([ghost])
    assert result == Counter()


# ---------------------------------------------------------------------------
# assert_no_content_loss
# ---------------------------------------------------------------------------


def test_assert_no_content_loss_ok() -> None:
    before = Counter({"line one": 1, "line two": 1})
    after = Counter({"line one": 1, "line two": 1, "extra line": 1})
    assert_no_content_loss(before, after)  # must not raise


def test_assert_no_content_loss_same_set() -> None:
    c = Counter({"a": 1, "b": 1, "c": 1})
    assert_no_content_loss(c, c)  # must not raise


def test_assert_no_content_loss_raises() -> None:
    before = Counter({"line one": 1, "line two": 1, "line three": 1})
    after = Counter({"line one": 1})  # two lines missing
    with pytest.raises(AssertionError, match="2 content line"):
        assert_no_content_loss(before, after)


def test_assert_no_content_loss_relocation_scenario(tmp_path: Path) -> None:
    """Prove that a relocation (move body from MEMORY.md to sibling) passes."""
    memory_md = tmp_path / "MEMORY.md"
    sibling = tmp_path / "project_build.md"

    # Before: dense session note lives inline in MEMORY.md.
    dense_body = (
        "Build v2.7.0 details: Phase 1 done, Phase 2 in progress.\n"
        "Key decision: use option A for the integration path.\n"
    )
    memory_md.write_text(f"# Index\n{dense_body}", encoding="utf-8")

    before_set = build_content_set([memory_md])

    # After relocation: body moves to sibling; MEMORY.md keeps only a pointer.
    sibling.write_text(dense_body, encoding="utf-8")
    memory_md.write_text(
        "# Index\n- [Build v2.7.0](project_build.md) — Phase 1+2 progress\n",
        encoding="utf-8",
    )

    after_set = build_content_set([memory_md, sibling])
    assert_no_content_loss(before_set, after_set)  # must not raise


# ---------------------------------------------------------------------------
# Multiset-specific tests (count-based correctness)
# ---------------------------------------------------------------------------


def test_assert_no_id_loss_raises_on_count_reduction() -> None:
    """A count reduction (2→1) must fail even though the ID is still present.

    The presence-only check (count>0 before, count>0 after) would silently
    pass; the count-based check catches the partial loss.
    """
    before = Counter({"DEC-001": 2})
    after = Counter({"DEC-001": 1})
    with pytest.raises(AssertionError, match="DEC-001"):
        assert_no_id_loss(before, after)


def test_assert_no_id_loss_equal_count_passes() -> None:
    before = Counter({"DEC-001": 2, "DEC-002": 3})
    after = Counter({"DEC-001": 2, "DEC-002": 3})
    assert_no_id_loss(before, after)  # must not raise


def test_assert_no_content_loss_duplicate_line_loss() -> None:
    """Losing one of two identical lines must raise.

    The frozenset-based check would silently pass (the line is still present);
    the Counter-based check catches the count reduction.
    """
    before = Counter({"repeated line": 2, "other line": 1})
    after = Counter({"repeated line": 1, "other line": 1})
    with pytest.raises(AssertionError, match="1 content line"):
        assert_no_content_loss(before, after)


def test_assert_no_content_loss_count_increase_passes() -> None:
    """A line appearing MORE times after is fine (content added, not lost)."""
    before = Counter({"line a": 1})
    after = Counter({"line a": 3, "line b": 2})
    assert_no_content_loss(before, after)  # must not raise
