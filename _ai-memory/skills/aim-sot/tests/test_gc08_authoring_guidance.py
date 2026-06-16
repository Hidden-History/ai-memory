"""GC-08: Structural contract test — aim-sot authoring guidance.

Asserts the structural integrity of the C/D authoring layer:
- SKILL.md contains ## Authoring with the 4 named rubric booleans (D1–D4) inline (BP-034 T2).
- references/authoring-guide.md covers all 7 project types and documents the emit gate.
- references/grading-exemplars.md covers all 3 verdict bands (PASS, WEAK, FAIL).

Behavioral grading against the golden set is Parzival's verify step — not in scope here.

Run targeted only (BUG-008 — do not run the full suite):
    pytest tests/test_gc08_authoring_guidance.py
"""
import re
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
GUIDE = SKILL_DIR / "references" / "authoring-guide.md"
EXEMPLARS = SKILL_DIR / "references" / "grading-exemplars.md"


def test_skill_md_authoring_section_present():
    """## Authoring section must exist in SKILL.md."""
    text = SKILL_MD.read_text()
    assert "## Authoring" in text, "SKILL.md missing ## Authoring section"


def test_skill_md_rubric_exposes_four_named_booleans():
    """D1, D2, D3, D4 must all appear in SKILL.md (rubric is inline per BP-034 T2)."""
    text = SKILL_MD.read_text()
    for dim in ("D1", "D2", "D3", "D4"):
        assert dim in text, f"SKILL.md rubric missing dimension {dim}"


def test_skill_md_references_both_guide_files():
    """SKILL.md ## Authoring must link to both references/ files by name."""
    text = SKILL_MD.read_text()
    assert "authoring-guide" in text, "SKILL.md missing link to references/authoring-guide.md"
    assert "grading-exemplars" in text, "SKILL.md missing link to references/grading-exemplars.md"


def test_guide_checklist_covers_seven_types():
    """authoring-guide.md must name all 7 project types."""
    text = GUIDE.read_text().lower()
    required_types = [
        "library",
        "web app",
        "service",
        "monorepo",
        "cli",
        "data",
        "infrastructure",
    ]
    for t in required_types:
        assert t in text, f"authoring-guide.md checklist missing type: '{t}'"


def test_guide_emit_gate_documented():
    """authoring-guide.md must document that FAIL blocks the registry emit."""
    text = GUIDE.read_text()
    assert "FAIL" in text, "authoring-guide.md missing FAIL keyword"
    gate_pattern = re.compile(
        r"(never emit|no.*?emit|fail.*?block)",
        re.IGNORECASE | re.DOTALL,
    )
    assert gate_pattern.search(text), (
        "authoring-guide.md missing emit-gate phrase "
        "(expected 'never emit … FAIL' or 'FAIL blocks' or equivalent)"
    )


def test_exemplars_cover_all_verdict_bands():
    """grading-exemplars.md must contain PASS, WEAK, and FAIL verdict examples."""
    text = EXEMPLARS.read_text()
    for verdict in ("PASS", "WEAK", "FAIL"):
        assert verdict in text, f"grading-exemplars.md missing verdict band: {verdict}"


def test_guide_emit_template_names_all_required_fields():
    """authoring-guide.md emit template must name all 6 required schema fields."""
    text = GUIDE.read_text()
    required_fields = ["id", "kind", "boundary_type", "sot_location", "owner", "description"]
    for field in required_fields:
        assert field in text, f"authoring-guide.md emit template missing required field: '{field}'"


def test_guide_documents_both_enum_sets():
    """authoring-guide.md must document all kind and boundary_type enum values."""
    text = GUIDE.read_text()
    kind_values = [
        "service", "library", "application", "api",
        "data", "infrastructure", "decision", "documentation",
    ]
    for v in kind_values:
        assert v in text, f"authoring-guide.md missing kind enum value: '{v}'"
    for v in ("path", "component", "concern"):
        assert v in text, f"authoring-guide.md missing boundary_type enum value: '{v}'"


def test_guide_zero_invalid_kind_tokens():
    """
    Every 'X / boundary_type' cell in authoring-guide.md §2.x tables must have X in the
    valid kind enum. Two field-marker forms are exempt and do NOT require enum membership:
      - Parenthesised cell, e.g. '(owner field)' → allowed (not a standalone entry).
      - Bare token with no '/ boundary' suffix, e.g. 'links' → allowed (field-marker).
    Cells of the form 'X / boundary_type' are standalone-entry rows; X MUST be a valid kind.
    This ensures 'links / concern' and 'cli / component' FAIL even if bare 'links' passes.
    """
    VALID_KINDS = {
        "service", "library", "application", "api",
        "data", "infrastructure", "decision", "documentation",
    }

    text = GUIDE.read_text()

    # Scope to §2 block only (## 2. … up to ## 3. or end of file)
    sec2_match = re.search(
        r"^(## 2\..+?)(?=^## 3\.|\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert sec2_match, "Could not locate §2 block in authoring-guide.md"
    sec2_text = sec2_match.group(1)

    invalid = []
    for line in sec2_text.splitlines():
        # Only process table data rows (pipe-delimited)
        if not line.startswith("|"):
            continue
        # Skip separator rows (e.g. |---|---|)
        if re.match(r"^\|\s*[-:]+\s*\|", line):
            continue
        # col[0]=empty, col[1]=canonical-part, col[2]=kind/boundary, col[3]=sot-location, …
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 4:
            continue
        kind_cell = cols[2]

        # Skip the column-header row (contains both "kind" and "boundary" as labels)
        if re.search(r"\bkind\b.*\bboundary\b", kind_cell, re.IGNORECASE):
            continue

        # Form 1: parenthesised → field-marker; allowed per §2 note
        if kind_cell.startswith("("):
            continue

        # Form 2: 'X / boundary_type' → standalone-entry row; X must be in the kind enum
        slash_match = re.match(r"^`?(\w+)`?\s*/\s*`?\w+`?$", kind_cell)
        if slash_match:
            kind_token = slash_match.group(1).lower()
            if kind_token not in VALID_KINDS:
                invalid.append(f"  non-enum kind={kind_token!r} in cell: {kind_cell!r}")
            continue

        # Form 3: bare token (no '/' and not parenthesised) → field-marker; allowed per §2 note

    assert not invalid, (
        "authoring-guide.md §2 tables have non-enum kind tokens in 'X / boundary_type' cells:\n"
        + "\n".join(invalid)
    )
