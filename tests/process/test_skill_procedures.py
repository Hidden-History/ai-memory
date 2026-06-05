"""Contract: Section-C embedded-procedure skill structural assertions.

Tests SKILL.md files for all three Section-C skills:
  1. SKILL.md file exists
  2. Frontmatter has non-empty 'name' and 'description'
  3. Body contains at least one H2 section (## ...)

Skills and their roots (two different roots — NOT a single skills directory):
  aim-agent-dispatch         → _ai-memory/pov/skills/  (pov skill)
  aim-agent-lifecycle        → _ai-memory/pov/skills/  (pov skill)
  aim-best-practices-researcher → _ai-memory/skills/   (core skill)

Scope notes (see INDEX.md for full coverage table):
  - aim-agent-sanctum-init: covered by the existing idempotency test suite
    (tests/test_install_sanctum_preservation.py); not duplicated here.
"""

import pytest

from .conftest import CORE_SKILLS_ROOT, SKILLS_ROOT, parse_frontmatter

# (skill_name, skill_md_path) — explicit per-skill paths because the three
# Section-C skills live under two different roots.
_SECTION_C_SKILLS = [
    ("aim-agent-dispatch", SKILLS_ROOT / "aim-agent-dispatch/SKILL.md"),
    ("aim-agent-lifecycle", SKILLS_ROOT / "aim-agent-lifecycle/SKILL.md"),
    (
        "aim-best-practices-researcher",
        CORE_SKILLS_ROOT / "aim-best-practices-researcher/SKILL.md",
    ),
]


@pytest.mark.process
@pytest.mark.parametrize(
    "skill_name,skill_md",
    _SECTION_C_SKILLS,
    ids=[name for name, _ in _SECTION_C_SKILLS],
)
def test_skill_md_exists(skill_name, skill_md):
    assert skill_md.exists(), f"SKILL.md not found for {skill_name}: {skill_md}"


@pytest.mark.process
@pytest.mark.parametrize(
    "skill_name,skill_md",
    _SECTION_C_SKILLS,
    ids=[name for name, _ in _SECTION_C_SKILLS],
)
def test_skill_frontmatter_schema(skill_name, skill_md):
    if not skill_md.exists():
        pytest.skip(f"SKILL.md not found: {skill_name}")
    fm = parse_frontmatter(skill_md)
    assert fm.get("name"), f"Missing/empty 'name' in {skill_md}"
    assert fm.get("description"), f"Missing/empty 'description' in {skill_md}"


@pytest.mark.process
@pytest.mark.parametrize(
    "skill_name,skill_md",
    _SECTION_C_SKILLS,
    ids=[name for name, _ in _SECTION_C_SKILLS],
)
def test_skill_has_h2_section(skill_name, skill_md):
    if not skill_md.exists():
        pytest.skip(f"SKILL.md not found: {skill_name}")
    text = skill_md.read_text(encoding="utf-8")
    h2_lines = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert h2_lines, f"{skill_md}: SKILL.md has no '## ' sections"
