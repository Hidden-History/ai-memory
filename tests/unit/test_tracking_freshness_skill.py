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
import re
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
render_deferrals_index = _mod.render_deferrals_index
render_closed_shard = _mod.render_closed_shard
_status_summary = _mod._status_summary
_warn_if_over_cap = _mod._warn_if_over_cap
find_records = _mod.find_records
parse_index_ids = _mod.parse_index_ids
parse_closed_shard_ids = _mod.parse_closed_shard_ids
compute_staleness = _mod.compute_staleness
parse_record_file = _mod.parse_record_file
BUG_RECORD_RE = _mod.BUG_RECORD_RE
TD_RECORD_RE = _mod.TD_RECORD_RE
DEFER_RECORD_RE = _mod.DEFER_RECORD_RE
DEFER_INDEX_CAP_LINES = _mod.DEFER_INDEX_CAP_LINES
DEFER_INDEX_CAP_KB = _mod.DEFER_INDEX_CAP_KB
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

    # ── Deferrals: RESOLVED/DROPPED are the closed-class (DEFERRAL_TEMPLATE.md) ──

    @pytest.mark.parametrize(
        "raw",
        [
            "RESOLVED",
            "**RESOLVED** v2.4.0 (long note)",
            "RESOLVED — revisited and closed",
            "DROPPED",
            "DROPPED — no longer relevant",
        ],
    )
    def test_defer_closed(self, raw: str) -> None:
        assert (
            classify_status(raw, "defer") is True
        ), f"Expected CLOSED for defer status: {raw!r}"

    @pytest.mark.parametrize(
        "raw",
        [
            "Deferred",
            "DEFERRED",
            "Revisiting",
            "REVISITING",
            "DEFERRED — trigger not yet met",
        ],
    )
    def test_defer_canonical_open(self, raw: str) -> None:
        assert (
            classify_status(raw, "defer") is False
        ), f"Expected OPEN for defer status: {raw!r}"

    @pytest.mark.parametrize(
        "raw",
        ["Postponed", "On Hold", "TBD", "Unknown", ""],
    )
    def test_defer_malformed_status_is_open(self, raw: str) -> None:
        """A non-canonical status is open-class (denylist, not allowlist) —
        must never be silently classified closed. Mirrors R2 fix #4: the
        session_loader surface must agree with this on any status string."""
        assert (
            classify_status(raw, "defer") is False
        ), f"Expected OPEN (safer default) for malformed defer status: {raw!r}"

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

    def test_extract_colon_with_leading_list_marker(self) -> None:
        """A leading `- ` list marker before **Status** must still parse (#290)."""
        text = "# TECH-DEBT-100: Some title\n\n- **Status**: In Progress\n"
        assert extract_raw_status(text) == "In Progress"

    def test_extract_table_format_hard_wrapped_cell(self) -> None:
        """A hard-wrapped table-format Status cell must still parse (TD-1083 D2).

        Live instance: TECH-DEBT-934 wraps its Status value across three
        physical lines with no leading `|` on the continuation lines. The
        full cell text — all three lines, trimmed — must be recovered, not
        merely a non-None/truncated prefix.
        """
        text = (
            "| **ID** | TECH-DEBT-934 |\n"
            "| **Severity** | Low |\n"
            "| **Status** | **OPEN — rescoped, not discharged.** The original "
            "zero-matches claim (PM #421/#423) is\n"
            "  discharged; the PM #432 unbounded-search-timeout claim is live "
            "and independently corroborated (see\n"
            '  "Currency check" below). |\n'
            "| **Surfaced** | PM #421 |\n"
        )
        result = extract_raw_status(text)
        assert result == (
            "**OPEN — rescoped, not discharged.** The original zero-matches "
            "claim (PM #421/#423) is\n"
            "  discharged; the PM #432 unbounded-search-timeout claim is live "
            "and independently corroborated (see\n"
            '  "Currency check" below).'
        )

    def test_extract_table_format_wrapped_cell_does_not_swallow_next_row(
        self,
    ) -> None:
        """Wrap-tolerance must not swallow an adjacent row's pipe (false-positive guard).

        A malformed Status cell missing its closing pipe, immediately
        followed by a real table row, must not have the next row's content
        folded into the Status value.
        """
        text = (
            "| **Status** | wrapped text without closing pipe on this line\n"
            "| **Severity** | HIGH |\n"
        )
        assert (
            extract_raw_status(text) == "wrapped text without closing pipe on this line"
        )


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

    def test_slug_less_bug_file_falls_back_to_stem(self) -> None:
        """BUG-001.md with a generic heading and no **Title** field falls back to the stem.

        A slug-less file has nothing to de-slugify; extract_title must return the bare
        stem ("BUG-001") so the INDEX never renders a blank Title cell.
        """
        text = "# Bug Report\n\n**Status**: OPEN\n"
        result = extract_title(text, "BUG-001.md")
        assert (
            result == "BUG-001"
        ), f"Expected stem fallback for slug-less file, got {result!r}"

    def test_slug_less_bug_file_with_good_heading(self) -> None:
        """BUG-001.md with a descriptive heading extracts from the heading normally."""
        text = "# BUG-001: Some Useful Title\n\n**Status**: OPEN\n"
        result = extract_title(text, "BUG-001.md")
        assert result == "Some Useful Title"

    def test_slug_less_td_file_falls_back_to_stem(self) -> None:
        """TECH-DEBT-010.md with a generic heading falls back to the stem.

        A slug-less file has nothing to de-slugify; extract_title must return the bare
        stem ("TECH-DEBT-010") so the INDEX never renders a blank Title cell.
        """
        text = "# Technical Debt Item\n\n**Status**: RESOLVED\n"
        result = extract_title(text, "TECH-DEBT-010.md")
        assert result == "TECH-DEBT-010"


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

    def test_table_row_hard_wrapped_cell_full_value(self) -> None:
        """``_SEV_TABLE_RE`` must capture the FULL wrapped cell (TD-1083 D2 twin).

        ``_SEV_TABLE_RE`` has the identical shape and blindness as
        ``_STATUS_TABLE_RE`` four lines away. Assert the complete multi-line
        raw capture directly — not just that ``extract_severity``'s
        normalized token still comes out right, which would pass even if
        only the first line were captured.
        """
        text = (
            "| **Severity** | HIGH (escalated from LOW per PM #281 — see the\n"
            "  discussion thread for full rationale) |\n"
        )
        m = _mod._SEV_TABLE_RE.search(text)
        assert m is not None
        assert m.group(1) == (
            "HIGH (escalated from LOW per PM #281 — see the\n"
            "  discussion thread for full rationale)"
        )
        assert extract_severity(text) == "HIGH"

    def test_table_row_wrapped_cell_does_not_swallow_next_row(self) -> None:
        """Wrap-tolerance in ``_SEV_TABLE_RE`` must not swallow an adjacent row."""
        text = (
            "| **Severity** | wrapped text without closing pipe on this line\n"
            "| **Status** | OPEN |\n"
        )
        m = _mod._SEV_TABLE_RE.search(text)
        assert m is not None
        assert m.group(1) == "wrapped text without closing pipe on this line"

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

    def test_leading_list_marker(self) -> None:
        """A leading `- ` list marker before **Severity** must still parse (#290)."""
        assert extract_severity("- **Severity**: High\n") == "HIGH"


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

    def test_eight_word_prefix_exactly_64_chars_stays_within_budget(self) -> None:
        """Word-truncated 8-word prefix landing exactly on 64 chars stays ≤64.

        Regression for the off-by-one in the char guard: with a strict ``>`` the
        64-char word-prefix skipped char-truncation, then the appended ellipsis
        pushed the cell to 65 chars. The ``>=`` guard trims to 63 first.
        """
        # 8 tokens summing to exactly 64 chars (incl. the 7 interior spaces):
        # one 8-char word + seven 7-char words = 57 chars + 7 spaces = 64.
        prefix = " ".join(["a" * 8] + ["b" * 7] * 7)
        assert len(prefix) == 64, "precondition: 8-word prefix is exactly 64 chars"
        # A 9th word forces word-level truncation so the ellipsis path is taken.
        summary = _status_summary(prefix + " ninth")
        assert summary.endswith("…")
        assert len(summary) <= 64, f"summary exceeded 64 chars: {summary!r}"


# ---------------------------------------------------------------------------
# TestRenderTdIndex
# ---------------------------------------------------------------------------


class TestRenderTdIndex:
    """Tests for render_td_index — analogous coverage to TestStatusVerbatim."""

    def _make_td_record(
        self, status: str, is_closed: bool = False, sev: str = "HIGH"
    ) -> Record:
        return Record(
            filename="TECH-DEBT-001-test.md",
            numeric_id="001",
            kind="td",
            raw_status=status,
            is_closed=is_closed,
            sev=sev,
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

    def test_open_breakdown_includes_critical(self) -> None:
        """A CRITICAL-severity open TD record must appear in the Open breakdown (TD-1083).

        Regression for the dropped-bucket defect: the TD writer's severity
        loop previously enumerated only HIGH/MEDIUM/LOW, so an open CRITICAL
        record was tallied into ``n_open`` but never printed.
        """
        rendered = render_td_index(
            [self._make_td_record("OPEN", sev="CRITICAL")], [], "2026-08-22"
        )
        assert "CRITICAL" in rendered

    def test_open_breakdown_sums_to_open_count_with_critical_and_unknown_severity(
        self,
    ) -> None:
        """The Open breakdown must sum to n_open even with CRITICAL and an unknown
        severity token present (TD-1083 D1 — residual form, not a literal tuple).

        A fix that merely adds ``"CRITICAL"`` to the enumerated tuple would pass
        a CRITICAL-only check but still drop an unrecognized severity token
        silently. This fixture carries both, so only a self-balancing residual
        (``other = n_open - sum(known buckets)``) can pass it.
        """
        records = [
            self._make_td_record("OPEN", sev="CRITICAL"),
            self._make_td_record("OPEN", sev="HIGH"),
            self._make_td_record("OPEN", sev="MEDIUM"),
            self._make_td_record("OPEN", sev="LOW"),
            self._make_td_record("OPEN", sev="SOMETHING-UNKNOWN"),
        ]
        rendered = render_td_index(records, [], "2026-08-22")

        breakdown_line = next(
            line for line in rendered.splitlines() if line.startswith("Open severity:")
        )
        counts = [int(n) for n in re.findall(r"(\d+)\s+\S", breakdown_line)]
        assert sum(counts) == len(records)
        assert "CRITICAL" in breakdown_line

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
# TestRenderDeferralsIndex
# ---------------------------------------------------------------------------


class TestRenderDeferralsIndex:
    """Tests for render_deferrals_index (PLAN-035 P2.6, Lane D)."""

    def _make_defer_record(
        self, numeric_id: str, status: str, is_closed: bool
    ) -> Record:
        return Record(
            filename=f"DEFER-{numeric_id}-test.md",
            numeric_id=numeric_id,
            kind="defer",
            raw_status=status,
            is_closed=is_closed,
            sev="",
            title=f"Deferred item {numeric_id}",
        )

    def test_quick_stats_counts(self) -> None:
        """Quick Stats reports total/open/closed matching the input records."""
        records = [
            self._make_defer_record("001", "Deferred", is_closed=False),
            self._make_defer_record("002", "Revisiting", is_closed=False),
            self._make_defer_record("003", "Resolved", is_closed=True),
        ]
        rendered = render_deferrals_index(records, [], "2026-07-17")

        assert "| **Deferral records (files, excl. companion)** | 3 |" in rendered
        assert "| **Open** (Deferred / Revisiting) | 2 |" in rendered
        assert "| **Closed** (Resolved / Dropped) | 1 |" in rendered

    def test_open_section_lists_open_records_only(self) -> None:
        """## Open Deferrals lists only open records, not closed ones."""
        records = [
            self._make_defer_record("001", "Deferred", is_closed=False),
            self._make_defer_record("002", "Resolved", is_closed=True),
        ]
        rendered = render_deferrals_index(records, [], "2026-07-17")

        open_section = rendered.split("## Open Deferrals", 1)[1].split(
            "## Closed Deferrals", 1
        )[0]
        assert "DEFER-001" in open_section
        assert "DEFER-002" not in open_section

    def test_closed_section_lists_closed_records_only(self) -> None:
        """## Closed Deferrals lists only closed records, not open ones."""
        records = [
            self._make_defer_record("001", "Deferred", is_closed=False),
            self._make_defer_record("002", "Resolved", is_closed=True),
        ]
        rendered = render_deferrals_index(records, [], "2026-07-17")

        closed_section = rendered.split("## Closed Deferrals", 1)[1]
        assert "DEFER-002" in closed_section
        assert "DEFER-001" not in closed_section

    def test_no_severity_column(self) -> None:
        """Deferrals INDEX has no Severity column (DEFERRAL_TEMPLATE.md has none)."""
        rendered = render_deferrals_index(
            [self._make_defer_record("001", "Deferred", is_closed=False)],
            [],
            "2026-07-17",
        )
        assert "| ID | Title | Status | Link |" in rendered
        assert "| ID | Sev |" not in rendered
        assert "Sev |" not in rendered

    def test_d2_front_matter(self) -> None:
        """Generated deferrals INDEX opens with the D2 register contract front-matter."""
        rendered = render_deferrals_index(
            [self._make_defer_record("001", "Deferred", is_closed=False)],
            [],
            "2026-07-17",
        )
        assert rendered.startswith("---\nclass: register\n")
        assert "read_path: section-anchored" in rendered
        assert f"cap_lines: {DEFER_INDEX_CAP_LINES}" in rendered
        assert f"cap_kb: {DEFER_INDEX_CAP_KB}" in rendered
        assert "archive_target: ./CLOSED.md" in rendered

    def test_companion_note_in_header(self) -> None:
        """render_deferrals_index wires the companions param into the header note."""
        companions = [
            ("DEFER-072-investigation-notes.md", "shares DEFER numeric ID 072")
        ]
        rendered = render_deferrals_index(
            [self._make_defer_record("001", "Deferred", is_closed=False)],
            companions,
            "2026-07-17",
        )
        assert "companion file(s) excluded" in rendered
        assert "`DEFER-072-investigation-notes.md`" in rendered


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
        assert 'owns: "generated bug-or-TD index + closed-history shard"' in rendered
        assert "cap_lines: 100" in rendered
        assert "cap_kb: 12" in rendered
        assert "rotation_trigger: none" in rendered
        assert "archive_target: ./CLOSED.md" in rendered

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
        assert 'owns: "generated bug-or-TD index + closed-history shard"' in rendered
        assert "cap_lines: 150" in rendered
        assert "cap_kb: 18" in rendered
        assert "rotation_trigger: none" in rendered
        assert "archive_target: ./CLOSED.md" in rendered

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

    def test_closed_shard_defer_kind_uses_defer_labels(self) -> None:
        """render_closed_shard(kind="defer") uses the Deferral label/prefix, not bug/TD."""
        record = Record(
            filename="DEFER-001-test.md",
            numeric_id="001",
            kind="defer",
            raw_status="Resolved",
            is_closed=True,
            sev="",
            title="Closed deferral",
        )
        shard = render_closed_shard([record], "defer", "2026-07-17")
        assert "Closed Deferral Records — Full History" in shard
        assert "DEFER-001" in shard
        assert "BUG-001" not in shard

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

    def test_closed_shard_only_match_not_misattributed_to_index(
        self, tmp_path: Path
    ) -> None:
        """Fix (LOW): an open record correctly in the INDEX Open section whose ID
        also appears (stale) in CLOSED.md must NOT be reported as a divergence
        attributed to the INDEX Closed section.

        The divergence-detail message attributes a placement to the INDEX, so it
        reads the INDEX-only closed list; the CLOSED.md shard union feeds only the
        missing_*/orphan computation. Before the fix the union leaked into the
        divergence check and produced a false "in Closed section of bugs/INDEX.md".
        """
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
            "| BUG-001 | OPEN |\n\n"  # correctly placed in Open
            "## Closed Bugs\n\n",
            encoding="utf-8",
        )
        # Stale shard still lists BUG-001 as closed (the shard is regenerated
        # wholesale on --write, so a stale entry is plausible mid-cycle).
        (bugs_dir / "CLOSED.md").write_text(
            "# Closed Bug Records\n\n"
            "| ID | Title | Status | Link |\n"
            "|----|-------|--------|------|\n"
            "| BUG-001 | Open Bug | FIXED | [file](./BUG-001-open-bug.md) |\n",
            encoding="utf-8",
        )
        td_index = self._make_minimal_td_index(td_dir)

        bugs_records = [parse_record_file(bugs_dir / "BUG-001-open-bug.md", "bug")]
        staleness = compute_staleness(bugs_records, [], [], bugs_index, td_index)

        assert staleness["divergences"] == [], (
            "a CLOSED.md-only closed match must not be misattributed to the "
            "INDEX Closed section"
        )
        # Union still suppresses a false missing_* for the sharded ID.
        assert staleness["missing_bug"] == []


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


# ---------------------------------------------------------------------------
# TestDeferralsWriteWiring — PLAN-035 P2.6 Lane D --write CLI contract
# ---------------------------------------------------------------------------


class TestDeferralsWriteWiring:
    """--write wiring for oversight/deferrals/ (generated-only, no --check
    divergence contract — see module docstring)."""

    def _build_defer_tree(self, tmp_path: Path) -> Path:
        oversight = tmp_path / "oversight"
        deferrals_dir = oversight / "deferrals"
        deferrals_dir.mkdir(parents=True)
        (deferrals_dir / "DEFER-001-open-item.md").write_text(
            "## DEFER-001: Open item\n\n"
            "| Field | Value |\n|-------|-------|\n"
            "| **Status** | Deferred |\n",
            encoding="utf-8",
        )
        (deferrals_dir / "DEFER-002-closed-item.md").write_text(
            "## DEFER-002: Closed item\n\n"
            "| Field | Value |\n|-------|-------|\n"
            "| **Status** | Resolved |\n",
            encoding="utf-8",
        )
        return oversight

    def test_write_generates_deferrals_index_and_closed(self, tmp_path: Path) -> None:
        """--write regenerates deferrals/INDEX.md and deferrals/CLOSED.md."""
        oversight = self._build_defer_tree(tmp_path)

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

        assert result.returncode == 0, (
            f"--write should exit 0 for a deferrals-only tree.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        defer_idx = oversight / "deferrals" / "INDEX.md"
        defer_closed = oversight / "deferrals" / "CLOSED.md"
        assert defer_idx.exists(), "deferrals/INDEX.md must be written."
        assert defer_closed.exists(), "deferrals/CLOSED.md must be written."

        idx_text = defer_idx.read_text(encoding="utf-8")
        assert "DEFER-001" in idx_text
        assert "| **Open** (Deferred / Revisiting) | 1 |" in idx_text
        assert "| **Closed** (Resolved / Dropped) | 1 |" in idx_text
        assert "DEFER-002" in defer_closed.read_text(encoding="utf-8")

    def test_write_absent_deferrals_dir_no_note_no_crash(self, tmp_path: Path) -> None:
        """--write silently skips deferrals/ when absent — optional-seed, no NOTE noise."""
        oversight = tmp_path / "oversight"
        bugs_dir = oversight / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "BUG-001-x.md").write_text(
            "# BUG-001\n\n**Status**: OPEN\n**Severity**: HIGH\n", encoding="utf-8"
        )
        # No oversight/deferrals/ dir at all.

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

        assert result.returncode == 0
        assert "Traceback" not in result.stderr
        assert not (oversight / "deferrals").exists()
        assert "deferrals directory absent" not in result.stderr

    def test_write_skipped_defer_file_surfaces_note_to_stderr(
        self, tmp_path: Path
    ) -> None:
        """A malformed DEFER-*.md (record-shaped, fails full pattern) is surfaced
        via a stderr NOTE (R2 fix #5) rather than silently dropped."""
        oversight = tmp_path / "oversight"
        deferrals_dir = oversight / "deferrals"
        deferrals_dir.mkdir(parents=True)
        (deferrals_dir / "DEFER-001-ok.md").write_text(
            "## DEFER-001: OK\n\n| Field | Value |\n|-------|-------|\n"
            "| **Status** | Deferred |\n",
            encoding="utf-8",
        )
        (deferrals_dir / "DEFER-bad-id.md").write_text("malformed", encoding="utf-8")

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

        assert result.returncode == 0
        assert "DEFER-bad-id.md" in result.stderr
        assert "NOTE" in result.stderr

    def test_write_idempotent_for_deferrals(self, tmp_path: Path) -> None:
        """Two consecutive --write runs produce byte-identical deferrals/INDEX.md."""
        oversight = self._build_defer_tree(tmp_path)
        defer_idx = oversight / "deferrals" / "INDEX.md"

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
        first = defer_idx.read_text(encoding="utf-8")

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
        assert defer_idx.read_text(encoding="utf-8") == first


# ---------------------------------------------------------------------------
# TestWarnIfOverCap
# ---------------------------------------------------------------------------


class TestWarnIfOverCap:
    """Fix 4: _warn_if_over_cap is a sensor — stderr WARNING when over cap, and
    silent + no-op (no raise, no exit) when under cap."""

    def test_over_line_cap_emits_warning(self, capsys, tmp_path: Path) -> None:
        path = tmp_path / "INDEX.md"
        content = "\n".join(["line"] * 50)  # 50 lines, over a 10-line cap
        ret = _warn_if_over_cap(path, content, cap_lines=10, cap_kb=1000)
        captured = capsys.readouterr()
        assert ret is None  # return unchanged — sensor, not a crash
        assert "WARNING" in captured.err
        assert "over cap" in captured.err
        assert captured.out == ""  # nothing on stdout

    def test_over_kb_cap_emits_warning(self, capsys, tmp_path: Path) -> None:
        path = tmp_path / "INDEX.md"
        content = "x" * 4096  # 4 KB, single line, over a 1-KB cap
        _warn_if_over_cap(path, content, cap_lines=1000, cap_kb=1)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "over cap" in captured.err

    def test_under_cap_no_warning(self, capsys, tmp_path: Path) -> None:
        path = tmp_path / "INDEX.md"
        content = "\n".join(["line"] * 5)  # tiny, well under both caps
        ret = _warn_if_over_cap(path, content, cap_lines=100, cap_kb=12)
        captured = capsys.readouterr()
        assert ret is None
        assert captured.err == ""
        assert captured.out == ""
