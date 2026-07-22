"""Tests for the Parzival two-phase startup loaders (TASK-077 A3).

Covers:
- the deterministic cap helpers (PERSONA Evolution Log, LORE recency slice,
  project-status head cap, section selection),
- the consolidated loader builds (activation Tier-A, session Tier-B),
- the vital-floor guard (the startup output contains the never-cut items),
- no-duplicate-load across the two phases,
- a CI-runnable LORE re-bloat ceiling guard, and
- a live-gated per-phase token-budget assertion against the real workspace.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

LOADER_DIR = (
    Path(__file__).resolve().parents[2] / "_ai-memory/pov/skills/aim-parzival-loader"
)
sys.path.insert(0, str(LOADER_DIR))

import activation_loader  # noqa: E402
import loader_common as lc  # noqa: E402
import session_loader  # noqa: E402

# Loaded by path (not sys.path) so its module name never collides with the
# aim-tracking-freshness skill's own test suite importing the same file.
_FRESHNESS_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "_ai-memory/pov/skills/aim-tracking-freshness/scripts/tracking_freshness.py"
)
_freshness_spec = importlib.util.spec_from_file_location(
    "tracking_freshness_for_loader_test", _FRESHNESS_SCRIPT
)
tracking_freshness = importlib.util.module_from_spec(_freshness_spec)
_freshness_spec.loader.exec_module(tracking_freshness)

# --------------------------------------------------------------------------- #
# Fixtures — a minimal sanctum + oversight + config tree                        #
# --------------------------------------------------------------------------- #

PERSONA_TEMPLATE = """# PERSONA

## Identity

Parzival.

## Evolution Log

Birth: 2026-05-07, First Breath.

Per-session identity history is **not** maintained here.

| Date | Identity shift | Why |
|------|----------------|-----|
{rows}
"""

LORE_TEMPLATE = """# LORE — Parzival

## Bootstrapping LORE for a New Project

Scaffold instructions (should be excluded from the slice).

## System Architecture

The structural architecture section.

## Key Design Decisions

The structural decisions section.

## Patterns & Conventions

The structural patterns section.

## Things Learned the Hard Way

{bullets}

*Prune ruthlessly. LORE is for what you USE.*
"""


def _persona(n_rows: int) -> str:
    rows = "\n".join(
        f"| 2026-05-{i:02d} | shift number {i} | reason {i} |"
        for i in range(1, n_rows + 1)
    )
    return PERSONA_TEMPLATE.format(rows=rows)


def _lore(n_bullets: int, bullet_bytes: int = 200) -> str:
    bullets = "\n".join(
        f"- **lesson {i}** " + ("x" * bullet_bytes) for i in range(1, n_bullets + 1)
    )
    return LORE_TEMPLATE.format(bullets=bullets)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path
    pov = root / "_ai-memory/pov"
    (pov / "constraints/global").mkdir(parents=True)
    (pov / "constraints/maintenance").mkdir(parents=True)
    (pov / "workflows").mkdir(parents=True)
    sanctum = root / "_ai-memory/sanctum/parzival"
    sanctum.mkdir(parents=True)
    oversight = root / "oversight"
    (oversight / "tracking").mkdir(parents=True)
    (oversight / "bugs").mkdir(parents=True)
    (oversight / "tech-debt").mkdir(parents=True)

    (pov / "config.yaml").write_text(
        'sanctum_path: "{project-root}/_ai-memory/sanctum"\n'
        'oversight_path: "{project-root}/oversight"\n'
        'constraints_path: "{project-root}/_ai-memory/pov/constraints"\n'
        'workflows_path: "{project-root}/_ai-memory/pov/workflows"\n',
        encoding="utf-8",
    )
    (oversight / "project-status.md").write_text(
        "# project-status.md\n\n```yaml\ncurrent_phase: maintenance\n```\n",
        encoding="utf-8",
    )
    (pov / "constraints/global/constraints.md").write_text(
        "# Global\nGC rules\n", encoding="utf-8"
    )
    (pov / "constraints/maintenance/constraints.md").write_text(
        "# Maintenance\nMC rules\n", encoding="utf-8"
    )
    (pov / "workflows/WORKFLOW-MAP.md").write_text(
        "# Workflow Map\nroutes\n", encoding="utf-8"
    )

    (sanctum / "CREED.md").write_text(
        "# CREED\nMission: oversight.\n", encoding="utf-8"
    )
    (sanctum / "PERSONA.md").write_text(_persona(25), encoding="utf-8")
    (sanctum / "LORE.md").write_text(_lore(60), encoding="utf-8")
    (sanctum / "MEMORY.md").write_text("# MEMORY\ntiny.\n", encoding="utf-8")
    (sanctum / "BOND.md").write_text(
        "# BOND\n\n## Owner\n\nOwner is wb.\n\n"
        "## Things They've Asked Me to Remember\n\nRemember X.\n\n"
        "## Things to Avoid\n\nAvoid Y.\n",
        encoding="utf-8",
    )

    (oversight / "SESSION_WORK_INDEX.md").write_text(
        "# Session Work Index\n\n## Active Task\n\nTASK-077.\n", encoding="utf-8"
    )
    (oversight / "tracking/task-tracker.md").write_text(
        "# Task Tracker\n\n## Active Tasks\n\nTASK-077 in progress.\n\n"
        "## Previous Sprint\n\nold sprint noise.\n",
        encoding="utf-8",
    )
    (oversight / "tracking/blockers-log.md").write_text(
        "# Blockers\n\n## Active Blockers\n\nBLK-004 open.\n\n"
        "## Resolved Blockers\n\nBLK-001 resolved noise.\n",
        encoding="utf-8",
    )
    (oversight / "tracking/risk-register.md").write_text(
        "# Risk\n\n## Active Risks\n\nRISK-013 high.\n\n"
        "## Resolved Risks\n\nRISK-001 resolved noise.\n",
        encoding="utf-8",
    )
    (oversight / "bugs/INDEX.md").write_text(
        "# Bugs\n\n## Quick Stats\n\nOpen: 3.\n\n## Open / Actionable Bugs\n\nBUG noise.\n",
        encoding="utf-8",
    )
    (oversight / "tech-debt/INDEX.md").write_text(
        "# TD\n\n## Quick Stats\n\nOpen: 5.\n\n## Open Technical Debt\n\nTD noise.\n",
        encoding="utf-8",
    )
    return root


# --------------------------------------------------------------------------- #
# Cap-helper unit tests                                                         #
# --------------------------------------------------------------------------- #


def test_persona_evolution_log_keeps_last_n_rows():
    out = lc.cap_evolution_log(_persona(25), 10, "P.md")
    data_rows = [ln for ln in out.splitlines() if ln.startswith("| 2026-05-")]
    assert len(data_rows) == 10
    assert "| 2026-05-25 | shift number 25 |" in out  # newest kept
    assert "| 2026-05-01 | shift number 1 |" not in out  # oldest dropped
    assert "## Identity" in out  # other sections preserved
    assert "older identity-shift rows capped" in out  # pointer present


def test_persona_under_cap_is_noop():
    src = _persona(5)
    assert lc.cap_evolution_log(src, 10, "P.md").strip() == src.strip()


def test_lore_slice_structure_and_recency():
    # 200 bullets x ~200 B = ~40 KB of lessons > the 25 KB cap, so the oldest
    # are dropped and the newest kept.
    out = lc.lore_slice(_lore(200), 25, "L.md")
    assert "## System Architecture" in out
    assert "## Key Design Decisions" in out
    assert "## Patterns & Conventions" in out
    assert "## Bootstrapping LORE for a New Project" not in out  # scaffold excluded
    assert "**lesson 200**" in out  # newest kept
    assert "**lesson 1** " not in out  # oldest dropped
    assert "*Prune ruthlessly." in out  # footer preserved
    assert "recency-weighted slice" in out  # pointer present


def test_lore_slice_byte_ceiling_holds_under_rebloat():
    # 10k bullets of 500 bytes each = ~5 MB input; slice must stay <= 25 KB.
    out = lc.lore_slice(_lore(10_000, bullet_bytes=500), 25, "L.md")
    assert len(out.encode("utf-8")) <= 25 * 1024
    assert "**lesson 10000**" in out  # newest always kept


def test_lore_slice_keeps_newest_even_when_one_bullet_exceeds_budget():
    out = lc.lore_slice(_lore(3, bullet_bytes=40_000), 25, "L.md")
    assert "**lesson 3**" in out  # newest kept despite exceeding budget


def test_cap_head_over_and_under():
    over = "\n".join(f"line {i}" for i in range(100)) + "\n"
    capped = lc.cap_head(over, 10, 6, "ps.md")
    assert capped.count("\n") < 100
    assert "capped at startup" in capped
    under = "a\nb\nc\n"
    assert lc.cap_head(under, 10, 6, "ps.md") == under


def test_select_sections_keep_and_drop():
    text = "# T\n\n## Quick Stats\n\nopen 1\n\n## Open Bugs\n\nnoise\n"
    assert "open 1" in lc.select_sections(text, keep=["Quick Stats"])
    assert "noise" not in lc.select_sections(text, keep=["Quick Stats"])
    assert "noise" not in lc.select_sections(text, drop=["Open"])


def test_cap_done_section_keeps_last_3_rows():
    text = (
        "# Task Tracker\n\n## Active Tasks\n\n| ID | Status |\n|----|--------|\n"
        "| T9 | In Progress |\n\n"
        "## Done\n\n| ID | Title | Status |\n|----|-------|--------|\n"
        + "".join(f"| D{i} | task {i} | Done |\n" for i in range(1, 8))
    )
    out = lc.cap_done_section(text, 3, "tt.md")
    done_rows = [
        ln for ln in out.splitlines() if ln.startswith("| D") and "Done |" in ln
    ]
    assert len(done_rows) == 3  # only last 3 Done rows kept
    assert "| D7 | task 7 | Done |" in out  # newest kept
    assert "| D1 | task 1 | Done |" not in out  # oldest dropped
    assert "## Active Tasks" in out  # other sections preserved
    assert "| T9 | In Progress |" in out  # Active Tasks table untouched
    assert "older Done rows capped" in out  # pointer present


def test_cap_done_section_under_cap_is_noop():
    text = (
        "# Task Tracker\n\n## Done\n\n| ID | Title | Status |\n|----|-------|--------|\n"
        "| D1 | task 1 | Done |\n| D2 | task 2 | Done |\n"
    )
    out = lc.cap_done_section(text, 3, "tt.md")
    assert "| D1 | task 1 | Done |" in out
    assert "| D2 | task 2 | Done |" in out
    assert "capped at startup" not in out


def test_first_breath_marker_and_phase():
    assert lc.first_breath_marker("## Owner\n_Filled during First Breath_\n")
    assert not lc.first_breath_marker("## Owner\nwb\n")
    assert lc.current_phase("```yaml\ncurrent_phase: release\n```") == "release"
    assert lc.current_phase("no phase here") is None


def test_first_breath_marker_scoped_to_owner():
    # Owner filled, scaffold prose surviving in another section (Working Style)
    # must NOT re-trigger First Breath (the D9-F1 false positive).
    filled = (
        "# Bond\n\n## Owner\n\n**Name:** wb\nRole: founder.\n\n"
        "## Working Style\n\n_Filled during First Breath and refined over time._\n"
    )
    assert not lc.first_breath_marker(filled)
    # Genuinely-empty Owner (scaffold marker present) -> True.
    empty = (
        "# Bond\n\n## Owner\n\n**Name:** {user_name}\n\n"
        "_Filled during First Breath: role, what success looks like._\n"
    )
    assert lc.first_breath_marker(empty)
    # No ## Owner section at all -> fail-safe False (never re-First-Breath).
    assert not lc.first_breath_marker("# Bond\n\n## Working Style\n\nfast.\n")


def test_first_breath_marker_real_name_with_surviving_seed():
    # The fill workflow appended a real owner Name but left the seed line in
    # ## Owner. A real Name alongside a surviving seed line must NOT re-trigger
    # First Breath (TD-737 false-positive case).
    bond = (
        "# Bond\n\n## Owner\n\n**Name:** Will\nRole: founder.\n\n"
        "_Filled during First Breath: role, what success looks like._\n"
    )
    assert not lc.first_breath_marker(bond)


def test_first_breath_marker_blank_name_with_surviving_seed():
    # ## Owner with a blank/whitespace-only Name value (no real name, no
    # {user_name} placeholder token) alongside a surviving seed line -> the
    # owner has not been established, so First Breath IS still needed (TD-737).
    bond = (
        "# Bond\n\n## Owner\n\n**Name:**   \nRole: founder.\n\n"
        "_Filled during First Breath: role, what success looks like._\n"
    )
    assert lc.first_breath_marker(bond)


def test_first_breath_marker_scaffold_substitution_shape():
    # sanctum-init substitutes a real Name into the template at scaffold time,
    # before First Breath ever runs, leaving the seed line untouched and no
    # other Owner content. This must still report PRESENT (issue #269).
    bond = (
        "# Bond\n\n## Owner\n\n**Name:** Developer\n\n"
        "_Filled during First Breath: role, what they're trying to accomplish, "
        "what success looks like for them, what they care about that surprises "
        "others._\n"
    )
    assert lc.first_breath_marker(bond)


def test_first_breath_marker_real_content_not_seed_prefixed():
    # Genuine italic Owner content that does NOT match the literal seed
    # substring (e.g. "_really_ hates surprises") must still count as real
    # extra content -- the guard must not treat "any line starting with _" as
    # seed-related.
    bond = (
        "# Bond\n\n## Owner\n\n**Name:** Will\n\n_really_ hates surprises.\n\n"
        "_Filled during First Breath: role, what success looks like._\n"
    )
    assert not lc.first_breath_marker(bond)


def test_first_breath_marker_wrapped_seed_untouched_scaffold():
    # Seed sentence hard-wrapped across physical lines on an otherwise
    # untouched scaffold. The continuation line carries no seed substring of
    # its own; it must still be classified as part of the seed paragraph, not
    # counted as extra content (must still report PRESENT -> True).
    bond = (
        "# Bond\n\n## Owner\n\n**Name:** Will\n\n"
        "_Filled during First Breath: role, what they are trying to accomplish,\n"
        "what success looks like for them, what they care about that surprises others._\n"
    )
    assert lc.first_breath_marker(bond)


def test_first_breath_marker_wrapped_real_content_still_extra():
    # Genuine (non-seed) Owner content that happens to be wrapped across
    # physical lines must still count as extra content on every line -- the
    # paragraph grouping must not swallow real filled-in prose.
    bond = (
        "# Bond\n\n## Owner\n\n**Name:** Will\n\n"
        "Role: founder, deeply committed\nto quality and craft.\n\n"
        "_Filled during First Breath: role, what success looks like._\n"
    )
    assert not lc.first_breath_marker(bond)


def test_resolve_paths_substitutes_root(workspace: Path):
    paths = lc.resolve_paths(workspace)
    assert paths["sanctum_path"] == workspace / "_ai-memory/sanctum"
    assert paths["oversight_path"] == workspace / "oversight"


# --------------------------------------------------------------------------- #
# Consolidated loader builds                                                    #
# --------------------------------------------------------------------------- #


def test_activation_build_order_and_caps(workspace: Path):
    out = activation_loader.build(workspace)
    headers = [ln for ln in out.splitlines() if ln.startswith("## [loader] ")]
    titles = [h.replace("## [loader] ", "") for h in headers]
    assert titles == [
        "config.yaml",
        "project-status.md",
        "constraints/global/constraints.md",
        "constraints/maintenance/constraints.md",
        "sanctum/CREED.md",
        "sanctum/PERSONA.md",
        "sanctum/BOND.md (First-Breath marker-scan)",
        "workflows/WORKFLOW-MAP.md",
    ]
    assert "Mission: oversight." in out  # CREED full
    assert "older identity-shift rows capped" in out  # PERSONA capped
    assert "First-Breath marker ABSENT" in out  # BOND marker-scan, filled


def test_session_build_scopes(workspace: Path):
    full = session_loader.build(workspace, scope="all")
    assert "Owner is wb." in full  # BOND vital floor
    assert "Remember X." in full
    assert "Avoid Y." in full
    assert "recency-weighted slice" in full  # LORE slice
    assert "BLK-004 open." in full  # active blocker summary
    assert "BLK-001 resolved noise." not in full  # resolved dropped
    assert "Open: 3." in full  # bugs Quick Stats
    assert "BUG noise." not in full  # bug detail dropped

    oversight_only = session_loader.build(workspace, scope="oversight")
    assert "Owner is wb." not in oversight_only
    sanctum_only = session_loader.build(workspace, scope="sanctum")
    assert "BLK-004 open." not in sanctum_only
    assert "Owner is wb." in sanctum_only


def test_session_build_missing_bug_td_index_fires_marker(workspace: Path):
    # #289 — an absent bugs/tech-debt INDEX must fire a marker, not be
    # silently skipped (fire-only-if-missing).
    (workspace / "oversight/bugs/INDEX.md").unlink()
    (workspace / "oversight/tech-debt/INDEX.md").unlink()
    out = session_loader.build(workspace, scope="oversight")
    assert (
        "bugs INDEX absent — bug counts unavailable; run /aim-tracking-freshness" in out
    )
    assert (
        "tech-debt INDEX absent — TD counts unavailable; run /aim-tracking-freshness"
        in out
    )


# DEFERRAL_TEMPLATE.md's identity block is a table, not a leading-bold line —
# these fixtures mirror the real template shape so the test actually exercises
# the table-aware regex fix (#410 Lane D candidate 1/4), not a colon-form stand-in.
_DEFER_TABLE_TEMPLATE = """## DEFER-{id}: {title}

| Field | Value |
|-------|-------|
| **Deferral ID** | DEFER-{id} |
| **Date** | 2026-01-01 |
| **Status** | {status} |
| **Revisit-Trigger** | {trigger} |
| **Deferred-By** | PM#1 |
| **Points-To** | self |

### What was deferred
Test deferral.

### Why
Test reason.

### Revisit criteria
Test criteria.
"""


def _write_defer(
    deferrals_dir: Path, numeric_id: str, status: str, trigger: str
) -> None:
    deferrals_dir.mkdir(parents=True, exist_ok=True)
    (deferrals_dir / f"DEFER-{numeric_id}.md").write_text(
        _DEFER_TABLE_TEMPLATE.format(
            id=numeric_id,
            title=f"deferred item {numeric_id}",
            status=status,
            trigger=trigger,
        ),
        encoding="utf-8",
    )


def test_session_build_surfaces_open_deferrals_table_format(workspace: Path):
    deferrals_dir = workspace / "oversight/deferrals"
    _write_defer(
        deferrals_dir, "001", "Deferred", "Date: 2020-01-01"
    )  # past -> TRIGGER MET
    _write_defer(deferrals_dir, "002", "Deferred", "Phase: P3")  # non-date, not flagged
    _write_defer(
        deferrals_dir, "003", "Resolved", "Date: 2020-01-01"
    )  # closed, not surfaced

    out = session_loader.build(workspace, scope="oversight")

    assert "oversight/deferrals (Open Deferrals)" in out
    assert "2 open" in out
    assert "DEFER-001" in out
    assert "DEFER-002" in out
    assert "DEFER-003" not in out  # Resolved — closed-class, not open

    assert "TRIGGER MET" in out
    triggered_section = out.split("TRIGGER MET")[1]
    assert "DEFER-001: date trigger passed (2020-01-01)" in triggered_section
    assert (
        "DEFER-002" not in triggered_section
    )  # Phase trigger — not mechanically checkable


def test_session_build_fires_nothing_when_no_open_deferrals(workspace: Path):
    # fire-only-on-open: absent oversight/deferrals/ dir emits nothing.
    out_absent = session_loader.build(workspace, scope="oversight")
    assert "Open Deferrals" not in out_absent

    # All-closed deferrals dir also emits nothing (never a "0 open" line).
    deferrals_dir = workspace / "oversight/deferrals"
    _write_defer(deferrals_dir, "001", "Resolved", "Date: 2020-01-01")
    out_all_closed = session_loader.build(workspace, scope="oversight")
    assert "Open Deferrals" not in out_all_closed


@pytest.mark.parametrize(
    "status",
    ["Postponed", "On Hold", "TBD", "Unknown"],
)
def test_loader_and_freshness_agree_on_malformed_defer_status(
    workspace: Path, status: str
) -> None:
    """A non-canonical Status (neither DEFERRED/REVISITING nor RESOLVED/DROPPED)
    must be OPEN on both session-start surfaces — never silently hidden by the
    loader while the freshness INDEX counts it open (the R2 fix #4 divergence)."""
    deferrals_dir = workspace / "oversight/deferrals"
    _write_defer(deferrals_dir, "001", status, "Phase: P3")

    out = session_loader.build(workspace, scope="oversight")
    loader_says_open = "DEFER-001" in out

    freshness_says_open = not tracking_freshness.classify_status(status, "defer")

    assert loader_says_open is True, f"loader hid malformed status {status!r}"
    assert freshness_says_open is True, f"freshness closed malformed status {status!r}"
    assert loader_says_open == freshness_says_open


# --------------------------------------------------------------------------- #
# PR #336 — deferrals status/trigger normalization                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", ["**Resolved**", "✅ Resolved"])
def test_is_defer_closed_agrees_with_tracking_freshness_classify_status(
    status: str,
) -> None:
    """_is_defer_closed did only .strip().upper() -- markdown-bold and emoji
    Status values must classify closed the same way
    tracking_freshness.classify_status does, so the two session-start
    surfaces never disagree."""
    assert session_loader._is_defer_closed(status) is True
    assert tracking_freshness.classify_status(status, "defer") is True


def test_is_defer_closed_agrees_with_tracking_freshness_on_backtick_status() -> None:
    """Backtick-wrapping is template-modeled only for Revisit-Trigger, not
    Status; a backtick-wrapped status must classify OPEN on both surfaces —
    locks the parity this fix restores."""
    status = "`Resolved`"
    assert session_loader._is_defer_closed(status) is False
    assert tracking_freshness.classify_status(status, "defer") is False


@pytest.mark.parametrize("status", ["**Resolved**", "✅ Resolved"])
def test_session_build_hides_markdown_wrapped_closed_deferral(
    workspace: Path, status: str
) -> None:
    deferrals_dir = workspace / "oversight/deferrals"
    _write_defer(deferrals_dir, "001", status, "Phase: P3")
    out = session_loader.build(workspace, scope="oversight")
    assert "DEFER-001" not in out


def test_session_build_surfaces_backtick_wrapped_status_as_open(
    workspace: Path,
) -> None:
    deferrals_dir = workspace / "oversight/deferrals"
    _write_defer(deferrals_dir, "001", "`Resolved`", "Phase: P3")
    out = session_loader.build(workspace, scope="oversight")
    assert "DEFER-001" in out  # not template-modeled — must surface as open


def test_defer_backtick_date_trigger_fires_trigger_met(workspace: Path) -> None:
    """_DEFER_DATE_TRIGGER_RE required literal 'Date:' at position 0, which
    DEFERRAL_TEMPLATE.md's modeled backtick-wrapped form (`` `Date:
    <YYYY-MM-DD>` ``) never satisfied -- TRIGGER MET silently never fired."""
    deferrals_dir = workspace / "oversight/deferrals"
    _write_defer(deferrals_dir, "001", "Deferred", "`Date: 2020-01-01`")
    out = session_loader.build(workspace, scope="oversight")
    assert "TRIGGER MET" in out
    triggered_section = out.split("TRIGGER MET")[1]
    assert "DEFER-001: date trigger passed (2020-01-01)" in triggered_section


def test_normalize_status_value_strips_bold_and_emoji_not_backticks() -> None:
    assert lc.normalize_status_value("**Resolved**") == "RESOLVED"
    assert lc.normalize_status_value("✅ Resolved") == "RESOLVED"
    assert lc.normalize_status_value("`Resolved`") == "`RESOLVED`"


def test_normalize_trigger_value_strips_bold_emoji_and_backticks() -> None:
    assert lc.normalize_trigger_value("`Resolved`") == "RESOLVED"
    assert lc.normalize_trigger_value("`Date: 2020-01-01`") == "DATE: 2020-01-01"


def test_read_text_degrades_on_invalid_utf8(tmp_path: Path) -> None:
    """loader_common.read_text caught only OSError -- an invalid UTF-8 byte
    in a user-authored file raised an uncaught UnicodeDecodeError (a
    ValueError), crashing the whole session-start loader. Must degrade like
    the rest of the loader (never raise)."""
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"Status: \xff\xfe invalid utf-8\n")
    assert "invalid utf-8" in lc.read_text(bad)


def test_vital_floor_present_across_phases(workspace: Path):
    act = activation_loader.build(workspace)
    ses = session_loader.build(workspace, scope="all")
    combined = act + ses
    # CREED (activation) + BOND directives + active task + blocker/risk summaries.
    assert "Mission: oversight." in combined
    assert "Owner is wb." in combined
    assert "Remember X." in combined
    assert "Avoid Y." in combined
    assert "TASK-077" in combined
    assert "BLK-004 open." in combined
    assert "RISK-013 high." in combined


def test_parse_scope_missing_value_errors():
    # --scope as the last arg with no following value → clear SystemExit, not crash.
    with pytest.raises(SystemExit):
        session_loader._parse_scope(["session_loader.py", "--scope"])


def test_parse_scope_valid_value_parses():
    _root, scope = session_loader._parse_scope(
        ["session_loader.py", "--scope", "sanctum"]
    )
    assert scope == "sanctum"


def test_no_duplicate_load_bond_body(workspace: Path):
    # BOND's body must appear only at session-start; activation marker-scans it.
    act = activation_loader.build(workspace)
    ses = session_loader.build(workspace, scope="all")
    assert "Owner is wb." not in act  # activation does NOT load BOND body
    assert "Owner is wb." in ses
    # LORE/PERSONA bodies are single-phase too.
    assert "## System Architecture" not in act
    assert "## System Architecture" in ses


# --------------------------------------------------------------------------- #
# Live-gated per-phase token-budget guard (VERIFICATION item 1 + 7)            #
# --------------------------------------------------------------------------- #

_LIVE_ROOT = Path(
    os.environ.get("AI_MEMORY_LOADER_LIVE_ROOT", "/mnt/e/projects/ai-memory-testV2")
)
_ACTIVATION_BUDGET = 13_501
_SESSION_FILE_BUDGET = 26_249


def _count_tokens_or_skip():
    try:
        repo_src = Path(__file__).resolve().parents[2] / "src"
        sys.path.insert(0, str(repo_src))
        from memory.chunking.truncation import count_tokens

        return count_tokens
    except Exception as e:
        pytest.skip(f"project tokenizer unavailable: {e}")


@pytest.mark.skipif(
    not (_LIVE_ROOT / "_ai-memory/sanctum/parzival/LORE.md").exists(),
    reason="live workspace sanctum not present (CI / fresh checkout)",
)
def test_live_phase_token_budgets_within_a2_targets():
    count_tokens = _count_tokens_or_skip()
    act = activation_loader.build(_LIVE_ROOT)
    ses = session_loader.build(_LIVE_ROOT, scope="all")
    act_tok = count_tokens(act)
    ses_tok = count_tokens(ses)
    assert act_tok <= _ACTIVATION_BUDGET, f"activation {act_tok} > {_ACTIVATION_BUDGET}"
    assert (
        ses_tok <= _SESSION_FILE_BUDGET
    ), f"session {ses_tok} > {_SESSION_FILE_BUDGET}"
    # Vital floor must survive the real-file capping too.
    assert "## Owner" in ses
