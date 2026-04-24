"""Unit tests for load_sanctum_tier_b (sanctum Tier B wiring — PLAN-025 Phase 3 P3-03).

Function under test: load_sanctum_tier_b in sanctum_tier_b.py (Option P import).
Spec: p3-01-sanctum-wiring-spec.md §6.1.
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch

# Add the skill dir to sys.path so we can import the sibling module (Option P).
_SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SKILL_DIR))

from sanctum_tier_b import load_sanctum_tier_b


def _make_sanctum(tmp_path: Path) -> Path:
    """Create the expected sanctum/parzival/ sub-tree inside tmp_path and return the sanctum root."""
    sanctum = tmp_path / "sanctum"
    (sanctum / "parzival").mkdir(parents=True)
    return sanctum


def test_load_sanctum_tier_b_both_present(tmp_path):
    """Both LORE.md and BOND.md present — output contains both sections in order."""
    sanctum = _make_sanctum(tmp_path)
    (sanctum / "parzival" / "LORE.md").write_text("User origin story.", encoding="utf-8")
    (sanctum / "parzival" / "BOND.md").write_text("Relationship state.", encoding="utf-8")

    result = load_sanctum_tier_b(sanctum)

    lore_pos = result.index("## Sanctum — LORE")
    bond_pos = result.index("## Sanctum — BOND")
    assert lore_pos < bond_pos, "LORE section must appear before BOND section"
    assert "User origin story." in result
    assert "Relationship state." in result


def test_load_sanctum_tier_b_only_lore(tmp_path):
    """Only LORE.md present — output contains LORE section only, no BOND."""
    sanctum = _make_sanctum(tmp_path)
    (sanctum / "parzival" / "LORE.md").write_text("User origin story.", encoding="utf-8")

    result = load_sanctum_tier_b(sanctum)

    assert "## Sanctum — LORE" in result
    assert "User origin story." in result
    assert "## Sanctum — BOND" not in result


def test_load_sanctum_tier_b_only_bond(tmp_path):
    """Only BOND.md present — output contains BOND section only, no LORE."""
    sanctum = _make_sanctum(tmp_path)
    (sanctum / "parzival" / "BOND.md").write_text("Relationship state.", encoding="utf-8")

    result = load_sanctum_tier_b(sanctum)

    assert "## Sanctum — BOND" in result
    assert "Relationship state." in result
    assert "## Sanctum — LORE" not in result


def test_load_sanctum_tier_b_neither(tmp_path):
    """Neither LORE.md nor BOND.md present — output is empty string."""
    sanctum = _make_sanctum(tmp_path)

    result = load_sanctum_tier_b(sanctum)

    assert result == ""


def test_load_sanctum_tier_b_empty_file(tmp_path):
    """LORE.md exists but contains only whitespace — LORE section omitted."""
    sanctum = _make_sanctum(tmp_path)
    (sanctum / "parzival" / "LORE.md").write_text("   \n\t  \n", encoding="utf-8")
    (sanctum / "parzival" / "BOND.md").write_text("Relationship state.", encoding="utf-8")

    result = load_sanctum_tier_b(sanctum)

    assert "## Sanctum — LORE" not in result
    assert "## Sanctum — BOND" in result
    assert "Relationship state." in result


def test_load_sanctum_tier_b_oserror_graceful(tmp_path):
    """OSError on LORE.md read — BOND section still emits, no exception bubbles."""
    sanctum = _make_sanctum(tmp_path)
    lore_path = sanctum / "parzival" / "LORE.md"
    bond_path = sanctum / "parzival" / "BOND.md"
    lore_path.write_text("User origin story.", encoding="utf-8")
    bond_path.write_text("Relationship state.", encoding="utf-8")

    original_read_text = Path.read_text

    def patched_read_text(self, *args, **kwargs):
        if self.name == "LORE.md":
            raise OSError("Permission denied (simulated)")
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", patched_read_text):
        result = load_sanctum_tier_b(sanctum)

    # Must not raise; BOND must still emit
    assert "## Sanctum — BOND" in result
    assert "Relationship state." in result
    # LORE was blocked by OSError — should not appear
    assert "## Sanctum — LORE" not in result
