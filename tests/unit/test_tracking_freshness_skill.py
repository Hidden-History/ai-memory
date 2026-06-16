"""Unit tests for aim-tracking-freshness skill script (PLAN-028 P0-4c).

Covers:
- Status classification (open/closed) for both bugs and tech-debt, including
  all closed-class token variants seen in the live oversight tree and the
  LIKELY FIXED edge case.
- Companion-file exclusion via the duplicate-ID heuristic.
- Title and severity field extraction.
- Verbatim status rendering (no truncation) in both INDEX renderers.
- Pipe-character escaping in table cells.
- Divergence detection via compute_staleness and parse_index_ids.
- Integration: --check / --write exit-code contract against a fixture tree.

These tests use only small in-memory fixtures and temporary directories.
They do NOT depend on the live oversight/ tree.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the skill script via importlib (it lives outside any installable package)
# ---------------------------------------------------------------------------

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "_ai-memory"
    / "pov"
    / "skills"
    / "aim-tracking-freshness"
    / "scripts"
    / "tracking_freshness.py"
)

_spec = importlib.util.spec_from_file_location("tracking_freshness", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

classify_status = _mod.classify_status
normalize_status = _mod.normalize_status
extract_raw_status = _mod.extract_raw_status
extract_title = _mod.extract_title
extract_severity = _mod.extract_severity
render_bugs_index = _mod.render_bugs_index
render_td_index = _mod.render_td_index
render_closed_shard = _mod.render_closed_shard
_status_summary = _mod._status_summary
find_records = _mod.find_records
parse_index_ids = _mod.parse_index_ids
parse_closed_shard_ids = _mod.parse_closed_shard_ids
compute_staleness = _mod.compute_staleness
parse_record_file = _mod.parse_record_file
BUG_RECORD_RE = _mod.BUG_RECORD_RE
TD_RECORD_RE = _mod.TD_RECORD_RE
Record = _mod.Record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_file(dirpath: Path, filename: str, content: str = "") -> None:
    (dirpath / filename).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# TestStatusClassification
# ---------------------------------------------------------------------------


class TestStatusClassification:
    """Tests for classify_status — the core open/closed decision."""

    # ── Bugs: closed-class tokens ─────────────────────────────────────────

    @pytest.mark.parametrize(
        "raw",
        [
            "FIXED",
            "✅ FIXED",
            "✅ FIXED (2026-01-31)",
            "**FIXED** PM #284 — long note here",
            "FIXED v2.4.0 (released...)",
            "FIXED — shipped in v2.4.1",
            "FIXED (commit `abc123`, PM #99)",
            "FIX APPLIED",
            "FIX APPLIED (uncommitted)",
            "FIX-APPLIED",
            "FIX APPLIED (commit `f7073cf` on `feature/v2.0.5-sprint`)",
            "RESOLVED",
            "**RESOLVED** v2.4.0 (long note)",
            "❌ NOT A BUG - By Design (2026-02-05)",
            "NOT A BUG — `group_id` is the actual project identity field",
            "NOT-A-BUG",
            "🔗 DUPLICATE - See BUG-060",
            "RECLASSIFIED → TECH-DEBT-543 (Will directive)",
        ],
    )
    def test_bugs_closed(self, raw: str) -> None:
        assert (
            classify_status(raw, "bug") is True
        ), f"Expected CLOSED for bug status: {raw!r}"

    @pytest.mark.parametrize(
        "raw",
        [
            "OPEN",
            "Open",
            "open",
            "NEW",
            "New",
            "new",
            "OPEN — fix dispatched",
            "NEW — Fix Pending",
            "ROOT CAUSE IDENTIFIED - Awaiting Debug Confirmation",
            "DEBUG INSTRUMENTATION ADDED",
            "Awaiting reproduction with debug logging enabled.",
            "REOPENED (PM #295, 2026-05-18) — REGRESSION",
        ],
    )
    def test_bugs_open(self, raw: str) -> None:
        assert (
            classify_status(raw, "bug") is False
        ), f"Expected OPEN for bug status: {raw!r}"

    def test_likely_fixed_remains_open(self) -> None:
        """LIKELY FIXED must remain open despite containing the FIXED substring.

        With leading-token matching, ``LIKELY`` is the operative word and is
        not in the closed-class set, so the guard is no longer the mechanism —
        but the behaviour is preserved.
        """
        raw = "⚠️ LIKELY FIXED / NEEDS TESTING (2026-02-05)"
        assert classify_status(raw, "bug") is False

    def test_empty_status_is_open(self) -> None:
        """Empty status string defaults to open (no closed token present)."""
        assert classify_status("", "bug") is False

    # ── Leading-token / substring-isolation tests (fix-r3) ───────────────

    def test_reopened_with_trailing_fixed_is_open(self) -> None:
        """BUG-301 class: REOPENED + historical FIXED in trailing clause → OPEN.

        This is the motivating bug for fix-r3: the substring approach falsely
        classified BUG-301 as CLOSED because 'FIXED' appeared in the historical
        context clause after 'REOPENED'.
        """
        raw = (
            "REOPENED (PM #295, 2026-05-18) — REGRESSION: the v2.4.0 fix + "
            "v2.4.1 regression coverage did NOT hold; the identical AttributeError "
            "recurs at [ST]. Previously: FIXED v2.4.0; regression coverage v2.4.1 (PR #143)."
        )
        assert (
            classify_status(raw, "bug") is False
        ), "REOPENED status with trailing FIXED clause must remain OPEN"

    def test_closed_token_mid_text_does_not_close(self) -> None:
        """A closed-class token appearing only mid-text does NOT close the record."""
        # FIXED only in middle; leading token is 'NEEDS'
        raw = "NEEDS TESTING — was FIXED in the branch but regressed"
        assert classify_status(raw, "bug") is False

    def test_leading_closed_token_closes(self) -> None:
        """A closed-class token at the very start → record is closed."""
        assert classify_status("FIXED — shipped in v2.4.1", "bug") is True
        assert classify_status("RESOLVED — shipped", "bug") is True

    def test_leading_multiword_not_a_bug_closes(self) -> None:
        """Multi-word leading token NOT A BUG → closed."""
        assert classify_status("NOT A BUG — by design", "bug") is True

    def test_leading_multiword_fix_applied_closes(self) -> None:
        """Multi-word leading token FIX APPLIED → closed."""
        assert classify_status("FIX APPLIED (commit abc123)", "bug") is True

    # ── TDs: closed-class tokens ──────────────────────────────────────────

    @pytest.mark.parametrize(
        "raw",
        [
            "IMPLEMENTED",
            "✅ IMPLEMENTED (Testing Pending)",
            "IMPLEMENTED (all phases complete on `feature/v2.0.4-cleanup`, pending merge)",
            "RESOLVED",
            "**RESOLVED** v2.4.0 (released...)",
            "RESOLVED — shipped in v2.4.1",
            "FIXED",
            "**FIXED** PM #284 — Option B closed",
            "FIXED — shipped in v2.4.1",
        ],
    )
    def test_td_closed(self, raw: str) -> None:
        assert (
            classify_status(raw, "td") is True
        ), f"Expected CLOSED for td status: {raw!r}"

    @pytest.mark.parametrize(
        "raw",
        [
            "Open",
            "OPEN",
            "PLANNING",
            "PLANNED",
            "NEW",
            "DEFERRED",
            "OPEN — DEFERRED to post-v2.4.0 hygiene pass",
            "OPEN — ROUTED to PLANNING phase per MC-03",
        ],
    )
    def test_td_open(self, raw: str) -> None:
        assert (
            classify_status(raw, "td") is False
        ), f"Expected OPEN for td status: {raw!r}"

    # ── TD: DEFERRED alone must stay open ─────────────────────────────────

    def test_td_deferred_alone_is_open(self) -> None:
        """DEFERRED is not in the TD closed-class — item is still tracked."""
        assert classify_status("DEFERRED", "td") is False

    # ── Bugs: VERIFIED and CLOSED are now canonical closed tokens (A.2) ──

    def test_bug_verified_is_closed(self) -> None:
        """VERIFIED is a canonical closed token for bugs per template contract."""
        assert classify_status("Verified", "bug") is True
        assert classify_status("VERIFIED", "bug") is True
        assert classify_status("Verified (PM #295)", "bug") is True

    def test_bug_closed_is_closed(self) -> None:
        """CLOSED is a canonical closed token for bugs per template contract."""
        assert classify_status("Closed", "bug") is True
        assert classify_status("CLOSED", "bug") is True
        assert classify_status("CLOSED — archived", "bug") is True

    def test_bug_reopened_is_open(self) -> None:
        """Reopened is an open-class token per template contract."""
        assert classify_status("Reopened", "bug") is False
        assert classify_status("REOPENED", "bug") is False

    # ── TD: CLOSED, WONT FIX, WON'T FIX are now canonical closed tokens (A.2) ──

    def test_td_closed_is_closed(self) -> None:
        """CLOSED is a canonical closed token for TDs per template contract."""
        assert classify_status("Closed", "td") is True
        assert classify_status("CLOSED", "td") is True
        assert classify_status("CLOSED — migrated to PLAN-028", "td") is True

    def test_td_wont_fix_variants_are_closed(self) -> None:
        """WONT FIX and WON'T FIX are canonical closed tokens for TDs."""
        assert classify_status("WONT FIX", "td") is True
        assert classify_status("WON'T FIX", "td") is True
        assert classify_status("Won't Fix", "td") is True
        assert classify_status("Wont Fix — out of scope", "td") is True

    def test_td_reopened_is_open(self) -> None:
        """Reopened is an open-class token for TDs."""
        assert classify_status("Reopened", "td") is False
        assert classify_status("REOPENED", "td") is False

    # ── normalize_status strips correctly ────────────────────────────────

    def test_variation_selector_stripped_adjacent_to_token(self) -> None:
        """U+FE0F variation selector directly adjacent to a closed token must still close.

        ⚠️ = U+26A0 (WARNING SIGN) + U+FE0F (VARIATION SELECTOR-16).  If U+FE0F is not
        stripped by _EMOJI_RE, it becomes the first char of the normalized string and
        ``re.match(r"^FIXED\\b", ...)`` fails, silently mis-classifying the record OPEN.
        """
        assert classify_status("⚠️FIXED", "bug") is True

    def test_zwj_stripped_adjacent_to_token(self) -> None:
        """U+200D ZWJ directly adjacent to a closed token must still close.

        U+200D (ZERO WIDTH JOINER) is used in multi-codepoint emoji sequences.
        If not stripped it becomes the first char of the normalized string and
        the leading-token match fails.
        """
        assert classify_status("‍FIXED", "bug") is True

    def test_normalize_strips_emoji(self) -> None:
        result = normalize_status("✅ FIXED (2026-01-31)")
        assert "✅" not in result
        assert "FIXED" in result

    def test_normalize_strips_bold_markers(self) -> None:
        result = normalize_status("**FIXED** PM #284")
        assert "**" not in result
        assert "FIXED" in result

    def test_normalize_uppercases(self) -> None:
        assert normalize_status("Open") == "OPEN"
        assert normalize_status("new") == "NEW"

    # ── extract_raw_status handles both formats ───────────────────────────

    def test_extract_colon_format(self) -> None:
        text = "# BUG-001: Some title\n\n**Status**: FIXED\n\n## Details"
        assert extract_raw_status(text) == "FIXED"

    def test_extract_table_format(self) -> None:
        text = "## BUG-301: Title\n\n| Field | Value |\n|-------|-------|\n| **Status** | REOPENED (PM #295) |\n"
        result = extract_raw_status(text)
        assert result == "REOPENED (PM #295)"

    def test_extract_returns_none_when_absent(self) -> None:
        text = "# BUG-001: Some title\n\n## Summary\nNo status line here."
        assert extract_raw_status(text) is None

    def test_extract_colon_inside_bold_format(self) -> None:
        """**Status:** value (colon INSIDE bold) must be parsed correctly.

        10 files in the live oversight tree use this variant, including
        BUG-044 (**Status:** ✅ FIXED) and TECH-DEBT-089 (**Status:** IMPLEMENTED).
        """
        text = "# BUG-044: Some title\n\n**Status:** ✅ FIXED (2026-01-31)\n"
        result = extract_raw_status(text)
        assert result == "✅ FIXED (2026-01-31)"

    def test_extract_colon_inside_bold_classified_correctly(self) -> None:
        """Records using **Status:** colon-inside-bold must be classified correctly."""
        # Bug: FIXED via colon-inside-bold → closed
        assert classify_status("✅ FIXED (2026-01-31)", "bug") is True
        # TD: IMPLEMENTED via colon-inside-bold → closed
        assert classify_status("IMPLEMENTED ✅", "td") is True
        # TD: PLANNED via colon-inside-bold → open
        assert classify_status("PLANNED", "td") is False
        # Bug: DUPLICATE via colon-inside-bold → closed
        assert classify_status("🔗 DUPLICATE - See TECH-DEBT-140", "bug") is True

    def test_extract_colon_inside_bold_td_implemented(self) -> None:
        """TECH-DEBT-089 pattern: **Status:** IMPLEMENTED (...) → closed."""
        text = "# TECH-DEBT-089: GitHub Workflows Setup\n\n**Status:** IMPLEMENTED (all 5 sub-tasks A-E completed)\n"
        raw = extract_raw_status(text)
        assert raw == "IMPLEMENTED (all 5 sub-tasks A-E completed)"
        assert classify_status(raw, "td") is True

    def test_extract_colon_takes_priority_over_table(self) -> None:
        """When both formats appear, colon format wins."""
        text = "**Status**: FIXED\n" "| **Status** | OPEN |\n"
        assert extract_raw_status(text) == "FIXED"


# ---------------------------------------------------------------------------
# TestCompanionExclusion
# ---------------------------------------------------------------------------


class TestCompanionExclusion:
    """Tests for find_records — companion file detection."""

    def test_single_file_per_id_is_primary(self, tmp_path: Path) -> None:
        """A file with a unique numeric ID is a primary record; no companions."""
        _write_file(tmp_path, "BUG-003-agent-response-capture-broken.md")
        _write_file(tmp_path, "BUG-004-root-cause-analysis.md")

        records, companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert len(companions) == 0
        assert skipped == set()
        assert "BUG-003-agent-response-capture-broken.md" in records
        assert "BUG-004-root-cause-analysis.md" in records

    def test_companion_excluded_when_same_id(self, tmp_path: Path) -> None:
        """When two files share ID 020, the alphabetically-later one is a companion."""
        _write_file(tmp_path, "BUG-020-duplicate-sessionstart.md")
        _write_file(tmp_path, "BUG-020-investigation-report.md")

        records, companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert records == ["BUG-020-duplicate-sessionstart.md"]
        assert len(companions) == 1
        assert skipped == set()
        companion_name, reason = companions[0]
        assert companion_name == "BUG-020-investigation-report.md"
        assert "020" in reason
        assert "BUG-020-duplicate-sessionstart.md" in reason

    def test_companion_reason_names_primary(self, tmp_path: Path) -> None:
        """Exclusion reason must explicitly name the primary record file."""
        _write_file(tmp_path, "BUG-020-duplicate-sessionstart.md")
        _write_file(tmp_path, "BUG-020-investigation-report.md")

        _, companions, _ = find_records(tmp_path, BUG_RECORD_RE, "bug")

        _, reason = companions[0]
        assert "BUG-020-duplicate-sessionstart.md" in reason

    def test_non_matching_files_excluded_by_pattern(self, tmp_path: Path) -> None:
        """INDEX.md, BUG_TEMPLATE.md, ROOT_CAUSE_TEMPLATE.md are not records."""
        _write_file(tmp_path, "INDEX.md")
        _write_file(tmp_path, "BUG_TEMPLATE.md")
        _write_file(tmp_path, "ROOT_CAUSE_TEMPLATE.md")
        _write_file(tmp_path, "BUG-001-real-record.md")

        records, companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert records == ["BUG-001-real-record.md"]
        assert companions == []
        # BUG_TEMPLATE uses underscore → does NOT start with "BUG-" so not skipped
        assert skipped == set()

    def test_td_glob_uses_tech_debt_prefix(self, tmp_path: Path) -> None:
        """TD records use TECH-DEBT-NNN prefix; files with TD-NNN are not matched."""
        _write_file(tmp_path, "TECH-DEBT-072-missing-collection-size-metric.md")
        _write_file(tmp_path, "TD-072-wrong-prefix.md")  # should NOT match
        _write_file(tmp_path, "INDEX.md")

        records, companions, skipped = find_records(tmp_path, TD_RECORD_RE, "td")

        assert records == ["TECH-DEBT-072-missing-collection-size-metric.md"]
        assert companions == []
        # TD-072 does not start with TECH-DEBT- → not skipped
        assert skipped == set()

    def test_records_sorted_numerically(self, tmp_path: Path) -> None:
        """Primary records are returned sorted by numeric ID (not lexicographic)."""
        _write_file(tmp_path, "BUG-009-early.md")
        _write_file(tmp_path, "BUG-100-late.md")
        _write_file(tmp_path, "BUG-020-middle.md")

        records, _, _ = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert records == [
            "BUG-009-early.md",
            "BUG-020-middle.md",
            "BUG-100-late.md",
        ]

    def test_multiple_companions_per_id(self, tmp_path: Path) -> None:
        """Three files with the same ID: first is primary, two are companions."""
        _write_file(tmp_path, "BUG-001-alpha.md")
        _write_file(tmp_path, "BUG-001-beta.md")
        _write_file(tmp_path, "BUG-001-gamma.md")

        records, companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert records == ["BUG-001-alpha.md"]
        assert len(companions) == 2
        assert skipped == set()
        companion_names = [c[0] for c in companions]
        assert "BUG-001-beta.md" in companion_names
        assert "BUG-001-gamma.md" in companion_names

    def test_mixed_td_primary_and_companion(self, tmp_path: Path) -> None:
        """TD companion detection works the same as for bugs.

        ``investigation-notes`` sorts before ``missing-metric`` alphabetically,
        so ``investigation-notes`` is the primary and ``missing-metric`` is the
        companion.
        """
        _write_file(tmp_path, "TECH-DEBT-072-missing-metric.md")
        _write_file(tmp_path, "TECH-DEBT-072-investigation-notes.md")

        records, companions, skipped = find_records(tmp_path, TD_RECORD_RE, "td")

        # "investigation-notes" < "missing-metric" alphabetically → primary
        assert records == ["TECH-DEBT-072-investigation-notes.md"]
        assert len(companions) == 1
        assert companions[0][0] == "TECH-DEBT-072-missing-metric.md"
        assert skipped == set()

    def test_status_bearing_file_promoted_to_primary(self, tmp_path: Path) -> None:
        """When the alphabetically-first file has no **Status** header but a
        later file does, the status-bearing file is promoted to primary.

        BUG-020-duplicate-sessionstart.md (empty) < BUG-020-investigation-report.md
        alphabetically, but only investigation-report carries a Status header,
        so it is promoted.
        """
        _write_file(tmp_path, "BUG-020-duplicate-sessionstart.md", "# BUG-020\n\n")
        _write_file(
            tmp_path,
            "BUG-020-investigation-report.md",
            "# BUG-020\n\n**Status**: OPEN\n",
        )

        records, companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert records == ["BUG-020-investigation-report.md"]
        assert len(companions) == 1
        assert companions[0][0] == "BUG-020-duplicate-sessionstart.md"
        assert skipped == set()

    def test_slug_less_bug_file_matches(self, tmp_path: Path) -> None:
        """BUG-001.md (no slug) must match BUG_RECORD_RE and be enumerated as a record."""
        _write_file(tmp_path, "BUG-001.md", "# BUG-001: Some Bug\n\n**Status**: OPEN\n")
        _write_file(tmp_path, "BUG-002-with-slug.md", "**Status**: FIXED\n")

        records, companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert "BUG-001.md" in records
        assert "BUG-002-with-slug.md" in records
        assert companions == []
        assert skipped == set()

    def test_slug_less_td_file_matches(self, tmp_path: Path) -> None:
        """TECH-DEBT-010.md (no slug) must match TD_RECORD_RE."""
        _write_file(tmp_path, "TECH-DEBT-010.md", "**Status**: RESOLVED\n")

        records, companions, skipped = find_records(tmp_path, TD_RECORD_RE, "td")

        assert "TECH-DEBT-010.md" in records
        assert companions == []
        assert skipped == set()

    def test_skipped_uppercase_slug_detected(self, tmp_path: Path) -> None:
        """BUG-005-BAD_SLUG.md starts with BUG- but fails the pattern → skipped."""
        _write_file(tmp_path, "BUG-005-BAD_SLUG.md")
        _write_file(tmp_path, "BUG-006-good-slug.md")

        records, _companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert "BUG-006-good-slug.md" in records
        assert "BUG-005-BAD_SLUG.md" in skipped

    def test_skipped_wrong_extension_detected(self, tmp_path: Path) -> None:
        """BUG-007-some-bug.txt starts with BUG- but has wrong extension → skipped."""
        _write_file(tmp_path, "BUG-007-some-bug.txt")
        _write_file(tmp_path, "BUG-008-real.md")

        records, _companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        assert "BUG-008-real.md" in records
        assert "BUG-007-some-bug.txt" in skipped

    def test_uppercase_only_slug_is_accepted_as_record(self, tmp_path: Path) -> None:
        """BUG-005-BADSLUG.md (uppercase letters, no underscore) is accepted.

        CR-4 regression: BUG_RECORD_RE uses re.IGNORECASE, so the character
        class [a-z0-9-] also matches uppercase letters.  A slug that contains
        only letters and hyphens (no underscore, no wrong extension) is valid
        regardless of case.  SKILL.md previously misstated that an uppercase
        slug is skipped — only underscores / wrong extensions / etc. cause a
        skip.
        """
        _write_file(tmp_path, "BUG-005-BADSLUG.md")
        _write_file(tmp_path, "BUG-006-good-slug.md")

        records, _companions, skipped = find_records(tmp_path, BUG_RECORD_RE, "bug")

        # Uppercase-only slug: accepted as a normal record, NOT skipped
        assert (
            "BUG-005-BADSLUG.md" in records
        ), "BUG-005-BADSLUG.md should be accepted — re.IGNORECASE covers uppercase slugs."
        assert (
            "BUG-005-BADSLUG.md" not in skipped
        ), "BUG-005-BADSLUG.md must NOT appear in the skipped set."
        assert "BUG-006-good-slug.md" in records


# ---------------------------------------------------------------------------
# TestTitleExtraction
# ---------------------------------------------------------------------------


class TestTitleExtraction:
    """Tests for extract_title — all heading formats and fallback behaviour."""

    def test_h1_colon_strips_prefix(self) -> None:
        """Standard H1 colon format strips BUG-NNN: prefix correctly."""
        text = "# BUG-003: Agent Response Capture Broken\n"
        assert extract_title(text, "BUG-003-agent-response-capture-broken.md") == (
            "Agent Response Capture Broken"
        )

    def test_h1_em_dash_stripped(self) -> None:
        """H1 with U+2014 em-dash separator strips ID prefix (BUG-281+ pattern)."""
        text = "# BUG-283 — Bootstrap path missing `_ai-memory/` segment\n"
        result = extract_title(text, "BUG-283-bootstrap-path.md")
        assert result == "Bootstrap path missing `_ai-memory/` segment"

    def test_h2_heading(self) -> None:
        """H2 headings are matched (BUG-288..307 table-format pattern)."""
        text = "## BUG-291: `init-sanctum.py` Never Auto-Invoked\n"
        result = extract_title(text, "BUG-291-init-sanctum-not-auto-invoked.md")
        assert result == "`init-sanctum.py` Never Auto-Invoked"

    def test_title_field_wins_over_heading(self) -> None:
        """``**Title**:`` field wins over any heading, including 'Bug Report'."""
        text = (
            "# Bug Report\n\n"
            "**Title**: install.sh fails with spaces in PATH\n"
            "**Status**: OPEN\n"
        )
        result = extract_title(text, "BUG-047-installer-fails-with-spaces-in-path.md")
        assert result == "install.sh fails with spaces in PATH"

    def test_title_field_colon_inside_bold(self) -> None:
        """``**Title:**`` (colon inside bold) is also recognised."""
        text = "# Bug Report\n\n**Title:** Some explicit title\n"
        result = extract_title(text, "BUG-050-some-bug.md")
        assert result == "Some explicit title"

    def test_generic_heading_falls_to_desluggify(self) -> None:
        """'Bug Report' heading with no ``**Title**`` field falls back to de-slugify."""
        text = "# Bug Report\n\n**Status**: OPEN\n"
        result = extract_title(text, "BUG-047-installer-fails-with-spaces-in-path.md")
        assert result == "Installer Fails With Spaces In Path"

    def test_td_h1_colon_strips_prefix(self) -> None:
        """TECH-DEBT H1 colon format strips prefix correctly."""
        text = "# TECH-DEBT-089: GitHub Workflows Setup\n"
        result = extract_title(text, "TECH-DEBT-089-github-workflows-setup.md")
        assert result == "GitHub Workflows Setup"

    def test_no_heading_desluggifies_filename(self) -> None:
        """No heading at all falls back to de-slugify."""
        text = "**Status**: OPEN\n"
        result = extract_title(text, "BUG-100-some-obscure-bug.md")
        assert result == "Some Obscure Bug"

    def test_technical_debt_item_generic_heading_falls_to_desluggify(self) -> None:
        """'Technical Debt Item' heading (TECH-DEBT-152/154 pattern) falls back to de-slugify."""
        text = "# Technical Debt Item\n\n**Status**: IMPLEMENTED\n"
        result = extract_title(
            text, "TECH-DEBT-152-architecture-doc-keyword-trigger-mismatch.md"
        )
        assert result == "Architecture Doc Keyword Trigger Mismatch"

    def test_slug_less_bug_file_desluggifies_to_empty(self) -> None:
        """BUG-001.md with a generic heading and no **Title** field returns empty title.

        A slug-less file has nothing to de-slugify; extract_title must return "" rather
        than echoing "BUG-001" as a title.
        """
        text = "# Bug Report\n\n**Status**: OPEN\n"
        result = extract_title(text, "BUG-001.md")
        assert result == "", f"Expected empty title for slug-less file, got {result!r}"

    def test_slug_less_bug_file_with_good_heading(self) -> None:
        """BUG-001.md with a descriptive heading extracts from the heading normally."""
        text = "# BUG-001: Some Useful Title\n\n**Status**: OPEN\n"
        result = extract_title(text, "BUG-001.md")
        assert result == "Some Useful Title"

    def test_slug_less_td_file_desluggifies_to_empty(self) -> None:
        """TECH-DEBT-010.md with a generic heading returns empty title."""
        text = "# Technical Debt Item\n\n**Status**: RESOLVED\n"
        result = extract_title(text, "TECH-DEBT-010.md")
        assert result == ""


# ---------------------------------------------------------------------------
# TestSeverityNormalization
# ---------------------------------------------------------------------------


class TestSeverityNormalization:
    """Tests for extract_severity — all format variants and alias normalization."""

    def test_clean_high(self) -> None:
        assert extract_severity("**Severity**: HIGH\n") == "HIGH"

    def test_clean_medium(self) -> None:
        assert extract_severity("**Severity**: MEDIUM\n") == "MEDIUM"

    def test_clean_low(self) -> None:
        assert extract_severity("**Severity**: LOW\n") == "LOW"

    def test_clean_critical(self) -> None:
        assert extract_severity("**Severity**: CRITICAL\n") == "CRITICAL"

    def test_parenthetical_noise_stripped(self) -> None:
        """Parenthetical annotation after token is discarded."""
        text = (
            "**Severity**: HIGH (install-blocking + security-class — secrets wrong)\n"
        )
        assert extract_severity(text) == "HIGH"

    def test_mixed_case_high(self) -> None:
        assert extract_severity("**Severity**: High\n") == "HIGH"

    def test_minor_maps_to_low(self) -> None:
        assert extract_severity("**Severity**: Minor\n") == "LOW"

    def test_major_maps_to_high(self) -> None:
        assert extract_severity("**Severity**: Major\n") == "HIGH"

    def test_blocker_maps_to_critical(self) -> None:
        assert extract_severity("**Severity**: Blocker\n") == "CRITICAL"

    def test_bold_in_table_cell(self) -> None:
        """``| **Severity** | **HIGH** (note) |`` strips the inner bold."""
        text = "| **Severity** | **HIGH** (escalated from LOW per PM #281) |\n"
        assert extract_severity(text) == "HIGH"

    def test_colon_inside_bold(self) -> None:
        """``**Severity:** High`` (colon inside bold, e.g. BUG-044) is parsed."""
        text = "**Severity:** High\n"
        assert extract_severity(text) == "HIGH"

    def test_table_row_clean(self) -> None:
        """``| **Severity** | LOW |`` table-row format."""
        text = "| **Severity** | LOW |\n"
        assert extract_severity(text) == "LOW"

    def test_non_severity_value_returns_empty(self) -> None:
        """Non-severity strings (N/A, Closed, NOT A BUG) return empty string."""
        assert extract_severity("**Severity**: N/A (closed)\n") == ""
        assert extract_severity("**Severity**: Closed\n") == ""
        assert extract_severity("**Severity**: NOT A BUG\n") == ""

    def test_absent_returns_empty(self) -> None:
        """No Severity field returns empty string."""
        assert extract_severity("**Status**: OPEN\n") == ""

    def test_low_with_trailing_period(self) -> None:
        """``LOW.`` (period after token) normalizes to ``LOW``."""
        text = "**Severity**: LOW. Theoretical bypass not observed.\n"
        assert extract_severity(text) == "LOW"


# ---------------------------------------------------------------------------
# TestStatusVerbatim
# ---------------------------------------------------------------------------


class TestStatusSummary:
    """Verify status is summarized (truncated) in the rendered INDEX while
    classification (``is_closed``) is unaffected — display truncation is
    classification-safe (D5 Fix A)."""

    def _make_record(self, status: str, is_closed: bool = False) -> Record:
        return Record(
            filename="BUG-301-test.md",
            numeric_id="301",
            kind="bug",
            raw_status=status,
            is_closed=is_closed,
            sev="HIGH",
            title="Test Bug",
        )

    def test_long_open_status_truncated(self) -> None:
        """A long open status is summarized (≤64 chars), not emitted verbatim."""
        long_status = (
            "REOPENED (PM #295, 2026-05-18) — REGRESSION: the v2.4.0 fix + "
            "v2.4.1 regression coverage did NOT hold; the identical AttributeError recurs"
        )
        assert len(long_status) > 64, "precondition: status exceeds the summary budget"
        rendered = render_bugs_index([self._make_record(long_status)], [], "2026-05-18")
        assert (
            long_status not in rendered
        ), "long status must be summarized, not verbatim"
        summary = _status_summary(long_status)
        assert summary in rendered, "the summarized status must appear in the INDEX"
        assert len(summary) <= 64

    def test_long_closed_status_truncated(self) -> None:
        """A long closed status is summarized (≤64 chars), not emitted verbatim."""
        long_status = (
            "FIXED v2.4.0 (released 2026-05-13, tag `v2.4.0`, merge `93ad34b`, PR #131) "
            "— 3-component MVF bundle landed: C-1 structured WARN log + Prometheus counter"
        )
        assert len(long_status) > 64, "precondition: status exceeds the summary budget"
        rendered = render_bugs_index(
            [self._make_record(long_status, is_closed=True)], [], "2026-05-18"
        )
        assert (
            long_status not in rendered
        ), "long closed status must be summarized, not verbatim"
        summary = _status_summary(long_status)
        assert summary in rendered, "the summarized status must appear in the INDEX"
        assert len(summary) <= 64

    def test_500_char_status_classification_unchanged(self) -> None:
        """500-char status → cell ≤64 chars AND ``is_closed`` unchanged.

        classify_status reads the full raw status at parse time; the display
        summary never feeds classification (D5 classification-invariance).
        """
        long_closed = "FIXED " + "detail " * 80  # > 500 chars, classifies CLOSED
        assert len(long_closed) > 500
        assert classify_status(long_closed, "bug") is True
        record = self._make_record(
            long_closed, is_closed=classify_status(long_closed, "bug")
        )
        rendered = render_bugs_index([record], [], "2026-05-18")
        summary = _status_summary(long_closed)
        assert len(summary) <= 64
        assert long_closed not in rendered
        assert record.is_closed is True


# ---------------------------------------------------------------------------
# TestRenderTdIndex
# ---------------------------------------------------------------------------


class TestRenderTdIndex:
    """Tests for render_td_index — analogous coverage to TestStatusVerbatim."""

    def _make_td_record(self, status: str, is_closed: bool = False) -> Record:
        return Record(
            filename="TECH-DEBT-001-test.md",
            numeric_id="001",
            kind="td",
            raw_status=status,
            is_closed=is_closed,
            sev="HIGH",
            title="Test TD",
        )

    def test_long_open_status_truncated(self) -> None:
        """render_td_index summarizes a long open status (≤64 chars, not verbatim)."""
        long_status = (
            "OPEN — DEFERRED to post-v2.4.0 hygiene pass per directive PM #296; "
            "blocked on PLAN-028 P0 baseline rebuild completing first"
        )
        assert len(long_status) > 64
        rendered = render_td_index(
            [self._make_td_record(long_status)], [], "2026-05-18"
        )
        assert long_status not in rendered
        summary = _status_summary(long_status)
        assert summary in rendered
        assert len(summary) <= 64

    def test_long_closed_status_truncated(self) -> None:
        """render_td_index summarizes a long closed status (≤64 chars, not verbatim)."""
        long_status = (
            "IMPLEMENTED (all phases complete on feature/v2.0.4-cleanup, pending merge) "
            "— closed per PM #284 review; all sub-tasks A-E verified"
        )
        assert len(long_status) > 64
        rendered = render_td_index(
            [self._make_td_record(long_status, is_closed=True)], [], "2026-05-18"
        )
        assert long_status not in rendered
        summary = _status_summary(long_status)
        assert summary in rendered
        assert len(summary) <= 64

    def test_companion_note_in_header(self) -> None:
        """render_td_index wires the companions param: excluded names appear in header."""
        companions = [
            ("TECH-DEBT-072-investigation-notes.md", "shares TD numeric ID 072")
        ]
        rendered = render_td_index(
            [self._make_td_record("OPEN")], companions, "2026-05-18"
        )
        assert "companion file(s) excluded" in rendered
        assert "`TECH-DEBT-072-investigation-notes.md`" in rendered

    def test_no_companion_note_when_empty(self) -> None:
        """render_td_index omits the companion note when there are no companions."""
        rendered = render_td_index([self._make_td_record("OPEN")], [], "2026-05-18")
        assert "companion file(s) excluded" not in rendered


# ---------------------------------------------------------------------------
# TestClosedShardAndFrontMatter
# ---------------------------------------------------------------------------


class TestClosedShardAndFrontMatter:
    """Fix B / GAP-2: CLOSED.md sharding, last-10 inline window, D2 front-matter,
    and INDEX + CLOSED.md (union) id-parsing."""

    def _closed_bug(self, n: int) -> Record:
        return Record(
            filename=f"BUG-{n:03d}-x.md",
            numeric_id=f"{n:03d}",
            kind="bug",
            raw_status="FIXED",
            is_closed=True,
            sev="LOW",
            title=f"Closed bug {n}",
        )

    def test_bugs_index_has_d2_front_matter(self) -> None:
        """Generated bugs INDEX opens with the D2 register contract front-matter."""
        rendered = render_bugs_index([self._closed_bug(1)], [], "2026-06-16")
        assert rendered.startswith("---\nclass: register\n")
        assert "read_path: section-anchored" in rendered
        assert "cap_lines: 100" in rendered
        assert "cap_kb: 12" in rendered
        assert "archive_target: CLOSED.md" in rendered

    def test_td_index_has_d2_front_matter(self) -> None:
        """Generated TD INDEX opens with the D2 register contract front-matter (150/18)."""
        td_rec = Record(
            filename="TECH-DEBT-001-x.md",
            numeric_id="001",
            kind="td",
            raw_status="RESOLVED",
            is_closed=True,
            sev="LOW",
            title="Closed TD",
        )
        rendered = render_td_index([td_rec], [], "2026-06-16")
        assert rendered.startswith("---\nclass: register\n")
        assert "cap_lines: 150" in rendered
        assert "cap_kb: 18" in rendered
        assert "archive_target: CLOSED.md" in rendered

    def test_closed_section_caps_at_last_10_with_pointer(self) -> None:
        """INDEX ## Closed lists only the most recent 10 + a count pointer."""
        records = [self._closed_bug(n) for n in range(1, 16)]  # 15 closed
        rendered = render_bugs_index(records, [], "2026-06-16")
        assert "[Full closed history → ./CLOSED.md] (15)" in rendered
        closed_section = rendered.split("## Closed Bugs", 1)[1]
        # 10 inline rows = the 10 highest numeric IDs (006..015)
        assert "BUG-015" in closed_section
        assert "BUG-006" in closed_section
        assert "BUG-005" not in closed_section  # oldest 5 sharded out
        row_count = sum(
            1 for ln in closed_section.splitlines() if ln.startswith("| BUG-")
        )
        assert row_count == 10

    def test_closed_shard_holds_full_history_and_is_idempotent(self) -> None:
        """CLOSED.md holds every closed record and re-renders byte-identical."""
        records = [self._closed_bug(n) for n in range(1, 16)]
        shard_a = render_closed_shard(records, "bug", "2026-06-16")
        shard_b = render_closed_shard(records, "bug", "2026-06-16")
        assert shard_a == shard_b  # idempotent
        for n in range(1, 16):
            assert f"BUG-{n:03d}" in shard_a  # full history (all 15)

    def test_gap2_sharded_closed_records_not_false_missing(
        self, tmp_path: Path
    ) -> None:
        """--check parses INDEX + CLOSED.md (union) → zero false missing_* after sharding."""
        bugs_dir = tmp_path / "bugs"
        td_dir = tmp_path / "tech-debt"
        bugs_dir.mkdir()
        td_dir.mkdir()
        for n in range(1, 16):
            (bugs_dir / f"BUG-{n:03d}-x.md").write_text(
                f"# BUG-{n:03d}: X\n\n**Status**: FIXED\n**Severity**: LOW\n",
                encoding="utf-8",
            )
        bugs_records = [
            parse_record_file(bugs_dir / f"BUG-{n:03d}-x.md", "bug")
            for n in range(1, 16)
        ]
        bugs_index = bugs_dir / "INDEX.md"
        bugs_index.write_text(
            render_bugs_index(bugs_records, [], "2026-06-16"), encoding="utf-8"
        )
        (bugs_dir / "CLOSED.md").write_text(
            render_closed_shard(bugs_records, "bug", "2026-06-16"), encoding="utf-8"
        )
        td_index = td_dir / "INDEX.md"
        td_index.write_text(
            "# Technical Debt Index\n\n## Open\n\n## Closed\n\n", encoding="utf-8"
        )

        staleness = compute_staleness(bugs_records, [], [], bugs_index, td_index)
        # The 5 oldest closed bugs are only in CLOSED.md; GAP-2 union prevents
        # them from being reported as missing from the INDEX.
        assert staleness["missing_bug"] == []

    def test_parse_closed_shard_ids_reads_rows(self, tmp_path: Path) -> None:
        """parse_closed_shard_ids returns every BUG id listed in a CLOSED.md shard."""
        records = [self._closed_bug(n) for n in range(1, 4)]
        shard = tmp_path / "CLOSED.md"
        shard.write_text(
            render_closed_shard(records, "bug", "2026-06-16"), encoding="utf-8"
        )
        ids = parse_closed_shard_ids(shard, "BUG")
        assert set(ids) == {"001", "002", "003"}
        assert parse_closed_shard_ids(tmp_path / "NONE.md", "BUG") == []


# ---------------------------------------------------------------------------
# TestTableCellEscaping
# ---------------------------------------------------------------------------


class TestTableCellEscaping:
    """Verify that '|' in status or title values is escaped in table cell output."""

    def test_pipe_in_open_status_escaped_in_bugs_index(self) -> None:
        """A status containing '|' must be escaped to avoid breaking the markdown table."""
        record = Record(
            filename="BUG-001-test.md",
            numeric_id="001",
            kind="bug",
            raw_status="OPEN | see comment",
            is_closed=False,
            sev="HIGH",
            title="Test Bug",
        )
        rendered = render_bugs_index([record], [], "2026-05-18")
        assert "OPEN \\| see comment" in rendered

    def test_pipe_in_closed_status_escaped_in_bugs_index(self) -> None:
        """Closed-section status '|' also escaped."""
        record = Record(
            filename="BUG-001-test.md",
            numeric_id="001",
            kind="bug",
            raw_status="FIXED | see BUG-060 | dup",
            is_closed=True,
            sev="HIGH",
            title="Test Bug",
        )
        rendered = render_bugs_index([record], [], "2026-05-18")
        assert "FIXED \\| see BUG-060 \\| dup" in rendered

    def test_pipe_in_title_escaped_in_bugs_index(self) -> None:
        """A title containing '|' must be escaped."""
        record = Record(
            filename="BUG-001-test.md",
            numeric_id="001",
            kind="bug",
            raw_status="OPEN",
            is_closed=False,
            sev="HIGH",
            title="Crash in a|b parser",
        )
        rendered = render_bugs_index([record], [], "2026-05-18")
        assert "a\\|b" in rendered

    def test_pipe_in_td_status_escaped(self) -> None:
        """render_td_index also escapes '|' in status."""
        record = Record(
            filename="TECH-DEBT-001-test.md",
            numeric_id="001",
            kind="td",
            raw_status="OPEN | blocked on BUG-301 | deferred",
            is_closed=False,
            sev="HIGH",
            title="Test TD",
        )
        rendered = render_td_index([record], [], "2026-05-18")
        assert "OPEN \\| blocked on BUG-301 \\| deferred" in rendered


# ---------------------------------------------------------------------------
# TestParseIndexIds
# ---------------------------------------------------------------------------


class TestParseIndexIds:
    """Unit tests for parse_index_ids — section-boundary bucketing logic."""

    def test_open_before_closed(self, tmp_path: Path) -> None:
        """Standard layout: ## Open above ## Closed."""
        index_path = tmp_path / "INDEX.md"
        index_path.write_text(
            "# Bug Index\n\n"
            "## Open\n\n"
            "| BUG-001 | OPEN |\n"
            "| BUG-002 | NEW |\n\n"
            "## Closed\n\n"
            "| BUG-003 | FIXED |\n",
            encoding="utf-8",
        )
        open_ids, closed_ids = parse_index_ids(index_path, "BUG")
        assert "001" in open_ids
        assert "002" in open_ids
        assert "003" in closed_ids
        assert "003" not in open_ids

    def test_closed_before_open(self, tmp_path: Path) -> None:
        """Non-standard layout: ## Closed above ## Open — IDs still bucketed correctly."""
        index_path = tmp_path / "INDEX.md"
        index_path.write_text(
            "# Bug Index\n\n"
            "## Closed\n\n"
            "| BUG-003 | FIXED |\n\n"
            "## Open\n\n"
            "| BUG-001 | OPEN |\n",
            encoding="utf-8",
        )
        open_ids, closed_ids = parse_index_ids(index_path, "BUG")
        assert "001" in open_ids
        assert "003" in closed_ids
        assert "003" not in open_ids

    def test_nonexistent_index_returns_empty(self, tmp_path: Path) -> None:
        """A missing INDEX file returns two empty lists without raising."""
        open_ids, closed_ids = parse_index_ids(tmp_path / "NONEXISTENT.md", "BUG")
        assert open_ids == []
        assert closed_ids == []

    def test_ids_before_sections_are_ignored(self, tmp_path: Path) -> None:
        """IDs in the preamble (before any section header) are not attributed."""
        index_path = tmp_path / "INDEX.md"
        index_path.write_text(
            "# Index\n\n"
            "| BUG-999 | preamble row |\n\n"  # before any ## section
            "## Open\n\n"
            "| BUG-001 | OPEN |\n",
            encoding="utf-8",
        )
        open_ids, closed_ids = parse_index_ids(index_path, "BUG")
        assert "001" in open_ids
        assert "999" not in open_ids
        assert "999" not in closed_ids


# ---------------------------------------------------------------------------
# TestDivergenceDetection
# ---------------------------------------------------------------------------


class TestDivergenceDetection:
    """Integration-level tests for compute_staleness — the divergence pipeline."""

    def _make_minimal_td_index(self, td_dir: Path) -> Path:
        """Write a minimal TD INDEX with empty Open/Closed sections."""
        td_index = td_dir / "INDEX.md"
        td_index.write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n",
            encoding="utf-8",
        )
        return td_index

    def test_reopened_in_closed_section_is_divergence(self, tmp_path: Path) -> None:
        """BUG-301-class: file says REOPENED but INDEX has it in Closed section.

        This is the primary motivating scenario for the skill: a bug was closed
        in the INDEX but subsequently reopened in its record file; compute_staleness
        must surface exactly that divergence.
        """
        bugs_dir = tmp_path / "bugs"
        td_dir = tmp_path / "tech-debt"
        bugs_dir.mkdir()
        td_dir.mkdir()

        (bugs_dir / "BUG-301-some-bug.md").write_text(
            "# BUG-301: Some Bug\n\n"
            "**Status**: REOPENED (PM #295) — regression\n"
            "**Severity**: HIGH\n",
            encoding="utf-8",
        )
        bugs_index = bugs_dir / "INDEX.md"
        bugs_index.write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "| ID | Sev | Title | Status | Link |\n"
            "|----|-----|-------|--------|------|\n\n"
            "## Closed Bugs\n\n"
            "| ID | Title | Status | Link |\n"
            "|----|-------|--------|------|\n"
            "| BUG-301 | Some Bug | FIXED | [file](./BUG-301-some-bug.md) |\n",
            encoding="utf-8",
        )
        td_index = self._make_minimal_td_index(td_dir)

        bugs_records = [parse_record_file(bugs_dir / "BUG-301-some-bug.md", "bug")]
        assert bugs_records[0].is_closed is False  # REOPENED → open

        staleness = compute_staleness(bugs_records, [], [], bugs_index, td_index)

        assert len(staleness["divergences"]) == 1
        div = staleness["divergences"][0]
        assert div["file"] == "BUG-301-some-bug.md"
        assert "REOPENED" in div["status"]
        assert "Closed" in div["detail"]

    def test_correctly_placed_records_have_no_divergences(self, tmp_path: Path) -> None:
        """All records placed correctly → zero divergences."""
        bugs_dir = tmp_path / "bugs"
        td_dir = tmp_path / "tech-debt"
        bugs_dir.mkdir()
        td_dir.mkdir()

        (bugs_dir / "BUG-001-open-bug.md").write_text(
            "# BUG-001: Open Bug\n\n**Status**: OPEN\n", encoding="utf-8"
        )
        (bugs_dir / "BUG-002-fixed-bug.md").write_text(
            "# BUG-002: Fixed Bug\n\n**Status**: FIXED\n", encoding="utf-8"
        )
        bugs_index = bugs_dir / "INDEX.md"
        bugs_index.write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "| BUG-001 | OPEN |\n\n"
            "## Closed Bugs\n\n"
            "| BUG-002 | FIXED |\n",
            encoding="utf-8",
        )
        td_index = self._make_minimal_td_index(td_dir)

        bugs_records = [
            parse_record_file(bugs_dir / "BUG-001-open-bug.md", "bug"),
            parse_record_file(bugs_dir / "BUG-002-fixed-bug.md", "bug"),
        ]
        staleness = compute_staleness(bugs_records, [], [], bugs_index, td_index)

        assert staleness["divergences"] == []

    def test_orphan_index_row_detected(self, tmp_path: Path) -> None:
        """INDEX references BUG-999 but no BUG-999-*.md file exists → orphan."""
        bugs_dir = tmp_path / "bugs"
        td_dir = tmp_path / "tech-debt"
        bugs_dir.mkdir()
        td_dir.mkdir()

        (bugs_dir / "BUG-001-open-bug.md").write_text(
            "# BUG-001: Open Bug\n\n**Status**: OPEN\n", encoding="utf-8"
        )
        bugs_index = bugs_dir / "INDEX.md"
        bugs_index.write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "| BUG-001 | OPEN |\n"
            "| BUG-999 | OPEN |\n\n"  # orphan — no file on disk
            "## Closed Bugs\n\n",
            encoding="utf-8",
        )
        td_index = self._make_minimal_td_index(td_dir)

        bugs_records = [parse_record_file(bugs_dir / "BUG-001-open-bug.md", "bug")]
        staleness = compute_staleness(bugs_records, [], [], bugs_index, td_index)

        assert "999" in staleness["orphan_bug_ids"]
        assert "001" not in staleness["orphan_bug_ids"]

    def test_missing_from_index_detected(self, tmp_path: Path) -> None:
        """BUG-002-*.md exists on disk but is absent from the INDEX → missing."""
        bugs_dir = tmp_path / "bugs"
        td_dir = tmp_path / "tech-debt"
        bugs_dir.mkdir()
        td_dir.mkdir()

        (bugs_dir / "BUG-001-open-bug.md").write_text(
            "# BUG-001\n\n**Status**: OPEN\n", encoding="utf-8"
        )
        (bugs_dir / "BUG-002-new-bug.md").write_text(
            "# BUG-002\n\n**Status**: NEW\n", encoding="utf-8"
        )
        bugs_index = bugs_dir / "INDEX.md"
        bugs_index.write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "| BUG-001 | OPEN |\n\n"  # BUG-002 absent
            "## Closed Bugs\n\n",
            encoding="utf-8",
        )
        td_index = self._make_minimal_td_index(td_dir)

        bugs_records = [
            parse_record_file(bugs_dir / "BUG-001-open-bug.md", "bug"),
            parse_record_file(bugs_dir / "BUG-002-new-bug.md", "bug"),
        ]
        staleness = compute_staleness(bugs_records, [], [], bugs_index, td_index)

        assert "BUG-002-new-bug.md" in staleness["missing_bug"]
        assert "BUG-001-open-bug.md" not in staleness["missing_bug"]


# ---------------------------------------------------------------------------
# TestCheckWriteContract
# ---------------------------------------------------------------------------


class TestCheckWriteContract:
    """CLI exit-code contract: --check exits 1 on drift; --write exits 0 on success."""

    def _build_drifted_tree(self, tmp_path: Path) -> Path:
        """Return an oversight/ root with BUG-301 mis-placed in the Closed INDEX section."""
        oversight = tmp_path / "oversight"
        bugs_dir = oversight / "bugs"
        td_dir = oversight / "tech-debt"
        bugs_dir.mkdir(parents=True)
        td_dir.mkdir()

        (bugs_dir / "BUG-301-test-bug.md").write_text(
            "# BUG-301: Test Bug\n\n"
            "**Status**: REOPENED (PM #295) — regression\n"
            "**Severity**: HIGH\n",
            encoding="utf-8",
        )
        (bugs_dir / "INDEX.md").write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "| ID | Sev | Title | Status | Link |\n"
            "|----|-----|-------|--------|------|\n\n"
            "---\n\n"
            "## Closed Bugs\n\n"
            "| ID | Title | Status | Link |\n"
            "|----|-------|--------|------|\n"
            "| BUG-301 | Test Bug | FIXED | [file](./BUG-301-test-bug.md) |\n",
            encoding="utf-8",
        )
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "| ID | Sev | Title | Status | Link |\n"
            "|----|-----|-------|--------|------|\n\n"
            "---\n\n"
            "## Closed Technical Debt\n\n"
            "| ID | Title | Status | Link |\n"
            "|----|-------|--------|------|\n",
            encoding="utf-8",
        )
        return oversight

    def test_check_exits_1_on_drift(self, tmp_path: Path) -> None:
        """--check exits 1 when the INDEX placement disagrees with file Status."""
        oversight = self._build_drifted_tree(tmp_path)
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--check",
                "--oversight-root",
                str(oversight),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"--check should exit 1 on drift; got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_write_exits_0_and_corrects_drift(self, tmp_path: Path) -> None:
        """--write exits 0 (drift corrected is success); post-write --check exits 0."""
        oversight = self._build_drifted_tree(tmp_path)

        write_result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--write",
                "--oversight-root",
                str(oversight),
            ],
            capture_output=True,
            text=True,
        )
        assert write_result.returncode == 0, (
            f"--write should exit 0 after correcting drift; got {write_result.returncode}\n"
            f"stdout: {write_result.stdout}\nstderr: {write_result.stderr}"
        )

        # Subsequent --check must confirm no remaining drift
        check_result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--check",
                "--oversight-root",
                str(oversight),
            ],
            capture_output=True,
            text=True,
        )
        assert check_result.returncode == 0, (
            f"Post-write --check should exit 0; got {check_result.returncode}\n"
            f"stdout: {check_result.stdout}\nstderr: {check_result.stderr}"
        )

    def test_write_idempotent(self, tmp_path: Path) -> None:
        """Two consecutive --write runs produce byte-identical INDEX files."""
        oversight = self._build_drifted_tree(tmp_path)
        bugs_index = oversight / "bugs" / "INDEX.md"
        td_index = oversight / "tech-debt" / "INDEX.md"

        for _ in range(2):
            subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPT_PATH),
                    "--write",
                    "--oversight-root",
                    str(oversight),
                ],
                capture_output=True,
                text=True,
                check=True,
            )

        # Read after both writes — second write must produce same content as first
        # (same-day timestamp means date portion is identical)
        first_bugs = bugs_index.read_text(encoding="utf-8")
        first_td = td_index.read_text(encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--write",
                "--oversight-root",
                str(oversight),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        assert bugs_index.read_text(encoding="utf-8") == first_bugs
        assert td_index.read_text(encoding="utf-8") == first_td

    # ── CR-1 regression: --write must not crash on absent subdir ─────────

    def test_write_absent_bugs_dir_does_not_crash(self, tmp_path: Path) -> None:
        """--write exits 0 and does not crash when bugs/ is absent.

        CR-1 regression: before the fix, writing bugs/INDEX.md when bugs/ did
        not exist raised FileNotFoundError.  After the fix, the absent collection
        is skipped gracefully (NOTE to stderr) and --write succeeds.
        """
        oversight = tmp_path / "oversight"
        td_dir = oversight / "tech-debt"
        td_dir.mkdir(parents=True)
        (td_dir / "TECH-DEBT-001-some-td.md").write_text(
            "# TECH-DEBT-001\n\n**Status**: OPEN\n", encoding="utf-8"
        )
        # No bugs/ dir at all

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--write",
                "--oversight-root",
                str(oversight),
            ],
            capture_output=True,
            text=True,
        )

        assert "Traceback" not in result.stderr, (
            f"--write must not raise an exception when bugs/ is absent.\n"
            f"stderr: {result.stderr}"
        )
        assert "FileNotFoundError" not in result.stderr, (
            f"--write must not raise FileNotFoundError when bugs/ is absent.\n"
            f"stderr: {result.stderr}"
        )
        assert result.returncode == 0, (
            f"--write should exit 0 even when bugs/ is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # The td INDEX must still be written
        assert (
            td_dir / "INDEX.md"
        ).exists(), "tech-debt/INDEX.md must be created even when bugs/ is absent."

    def test_write_absent_td_dir_does_not_crash(self, tmp_path: Path) -> None:
        """--write exits 0 and does not crash when tech-debt/ is absent.

        Symmetric regression test for the tech-debt side of CR-1.
        """
        oversight = tmp_path / "oversight"
        bugs_dir = oversight / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "BUG-001-some-bug.md").write_text(
            "# BUG-001\n\n**Status**: OPEN\n**Severity**: HIGH\n",
            encoding="utf-8",
        )
        # No tech-debt/ dir at all

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--write",
                "--oversight-root",
                str(oversight),
            ],
            capture_output=True,
            text=True,
        )

        assert "Traceback" not in result.stderr, (
            f"--write must not raise an exception when tech-debt/ is absent.\n"
            f"stderr: {result.stderr}"
        )
        assert result.returncode == 0, (
            f"--write should exit 0 even when tech-debt/ is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert (
            bugs_dir / "INDEX.md"
        ).exists(), "bugs/INDEX.md must be created even when tech-debt/ is absent."

    # ── CR-2 regression: --check must detect missing INDEX per collection ──

    def test_check_missing_index_detected_when_other_dir_absent(
        self, tmp_path: Path
    ) -> None:
        """--check flags a missing bugs INDEX even when tech-debt/ dir is absent.

        CR-2 regression: per-collection missing-INDEX detection must fire
        independently.  A present collection (bugs/ exists + records found) with
        no INDEX.md is always a counted issue and forces a non-zero exit, even
        when the other collection's directory (tech-debt/) does not exist.
        """
        oversight = tmp_path / "oversight"
        bugs_dir = oversight / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "BUG-001-open-record.md").write_text(
            "# BUG-001: Open Record\n\n**Status**: OPEN\n**Severity**: HIGH\n",
            encoding="utf-8",
        )
        # No bugs/INDEX.md
        # No tech-debt/ directory at all

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--check",
                "--oversight-root",
                str(oversight),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, (
            "--check must exit 1 when bugs/ has records but no INDEX.md, "
            "regardless of tech-debt/ being absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # Must surface the missing INDEX, not a false-clean ✓
        assert (
            "MISSING INDEX FILES" in result.stdout
        ), "'MISSING INDEX FILES' section must be present in output."
        assert (
            "bugs/INDEX.md" in result.stdout
        ), "'bugs/INDEX.md' must appear in the MISSING INDEX section."
        assert (
            "fully in sync" not in result.stdout
        ), "--check must NOT print 'fully in sync ✓' — that is a false-clean."
