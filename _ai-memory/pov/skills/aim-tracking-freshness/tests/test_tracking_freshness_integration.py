"""
Integration tests for aim-tracking-freshness (PLAN-028 P0-4c, A.6).

All tests invoke tracking_freshness.py via subprocess against temporary
fixture trees, asserting observable behaviour at the filesystem and stdout/
stderr level.  No live oversight/ tree is touched.

Coverage:
- Slug-less and slug-ful filenames both scanned
- VERIFIED / Closed / Reopened status handling (A.2 token contract)
- Empty tracking tree → honest "0 records" message, never false-clean ✓
- Missing bugs/ or tech-debt/ directory → graceful degradation (A.4)
- Missing INDEX when records exist → surfaced + counted in --check (A.3)
- Skipped record-shaped files (uppercase slug, wrong extension) → counted in --check (A.3)
- TD closed-token alignment (CLOSED, WONT FIX, WON'T FIX canonical)
- --write regeneration creates missing INDEXes and exits 0
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "tracking_freshness.py"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _run(oversight: Path, mode: str = "--check") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), mode, "--oversight-root", str(oversight)],
        capture_output=True,
        text=True,
    )


def _make_oversight(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create an oversight/ root with empty bugs/ and tech-debt/ dirs.

    Returns (oversight, bugs_dir, td_dir).
    """
    oversight = tmp_path / "oversight"
    bugs_dir = oversight / "bugs"
    td_dir = oversight / "tech-debt"
    bugs_dir.mkdir(parents=True)
    td_dir.mkdir()
    return oversight, bugs_dir, td_dir


def _write_minimal_indexes(bugs_dir: Path, td_dir: Path) -> None:
    """Write minimal valid INDEX files with empty Open/Closed sections."""
    (bugs_dir / "INDEX.md").write_text(
        "# Bug Tracker Index\n\n" "## Open\n\n" "## Closed Bugs\n\n",
        encoding="utf-8",
    )
    (td_dir / "INDEX.md").write_text(
        "# Technical Debt Index\n\n"
        "## Open Technical Debt\n\n"
        "## Closed Technical Debt\n\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# T1 — slug-less filename is accepted
# ---------------------------------------------------------------------------


class TestSlugLessFilenames:
    def test_slug_less_bug_file_is_scanned(self, tmp_path: Path) -> None:
        """BUG-001.md (no slug) is enumerated and scanned."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-001.md").write_text(
            "# BUG-001: Some Bug\n\n**Status**: New\n", encoding="utf-8"
        )
        _write_minimal_indexes(bugs_dir, td_dir)

        result = _run(oversight, "--check")
        # BUG-001 is open; INDEX has it absent → shows up in MISSING FROM INDEX
        assert result.returncode == 1
        assert "1 records" in result.stdout or "Bugs scanned : 1" in result.stdout

    def test_slug_ful_bug_file_is_scanned(self, tmp_path: Path) -> None:
        """BUG-002-some-slug.md is enumerated and scanned."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-002-some-slug.md").write_text(
            "# BUG-002: Another Bug\n\n**Status**: OPEN\n", encoding="utf-8"
        )
        _write_minimal_indexes(bugs_dir, td_dir)

        result = _run(oversight, "--check")
        assert result.returncode == 1  # missing from index
        assert "Bugs scanned : 1" in result.stdout

    def test_slug_less_and_slug_ful_coexist(self, tmp_path: Path) -> None:
        """Both slug-less and slug-ful files are enumerated in the same scan."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-001.md").write_text("**Status**: FIXED\n", encoding="utf-8")
        (bugs_dir / "BUG-002-slug.md").write_text(
            "**Status**: OPEN\n", encoding="utf-8"
        )
        _write_minimal_indexes(bugs_dir, td_dir)

        result = _run(oversight, "--check")
        assert "Bugs scanned : 2" in result.stdout

    def test_slug_less_td_file_is_scanned(self, tmp_path: Path) -> None:
        """TECH-DEBT-010.md (no slug) is enumerated and scanned."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (td_dir / "TECH-DEBT-010.md").write_text(
            "**Status**: RESOLVED\n", encoding="utf-8"
        )
        _write_minimal_indexes(bugs_dir, td_dir)

        result = _run(oversight, "--check")
        assert "TDs scanned  : 1" in result.stdout


# ---------------------------------------------------------------------------
# T2 — VERIFIED / Closed / Reopened status handling
# ---------------------------------------------------------------------------


class TestStatusTokenContract:
    def test_verified_closes_bug(self, tmp_path: Path) -> None:
        """A bug with Status: Verified is classified closed."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-010-verified-bug.md").write_text(
            "# BUG-010: Verified Bug\n\n**Status**: Verified\n", encoding="utf-8"
        )
        bugs_index = bugs_dir / "INDEX.md"
        bugs_index.write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "## Closed Bugs\n\n"
            "| BUG-010 | Verified Bug | Verified | [file](./BUG-010-verified-bug.md) |\n",
            encoding="utf-8",
        )
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        assert result.returncode == 0, (
            f"Verified bug in Closed section should exit 0.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "fully in sync" in result.stdout

    def test_closed_closes_bug(self, tmp_path: Path) -> None:
        """A bug with Status: Closed is classified closed."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-011-closed-bug.md").write_text(
            "**Status**: Closed\n", encoding="utf-8"
        )
        bugs_index = bugs_dir / "INDEX.md"
        bugs_index.write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "## Closed Bugs\n\n"
            "| BUG-011 | Closed Bug | Closed | [file](./BUG-011-closed-bug.md) |\n",
            encoding="utf-8",
        )
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        assert result.returncode == 0, (
            f"Closed bug in Closed section should exit 0.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_reopened_is_open(self, tmp_path: Path) -> None:
        """A bug with Status: Reopened placed in Closed section is a divergence."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-012-reopened.md").write_text(
            "**Status**: Reopened\n", encoding="utf-8"
        )
        bugs_index = bugs_dir / "INDEX.md"
        bugs_index.write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "## Closed Bugs\n\n"
            "| BUG-012 | Reopened Bug | FIXED | [file](./BUG-012-reopened.md) |\n",
            encoding="utf-8",
        )
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        assert result.returncode == 1
        assert "DIVERGENCES" in result.stdout
        assert "BUG-012-reopened.md" in result.stdout

    def test_td_closed_token_is_closed(self, tmp_path: Path) -> None:
        """TECH-DEBT with Status: Closed is classified closed."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        _write_minimal_indexes(bugs_dir, td_dir)
        (td_dir / "TECH-DEBT-020-something.md").write_text(
            "**Status**: Closed\n", encoding="utf-8"
        )
        # Overwrite TD index to place in Closed
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n"
            "| TECH-DEBT-020 | Something | Closed | [file](./TECH-DEBT-020-something.md) |\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        assert result.returncode == 0, (
            f"TD Closed in Closed section should exit 0.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_td_wont_fix_is_closed(self, tmp_path: Path) -> None:
        """TECH-DEBT with Status: WONT FIX is classified closed."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        _write_minimal_indexes(bugs_dir, td_dir)
        (td_dir / "TECH-DEBT-021-wontfix.md").write_text(
            "**Status**: WONT FIX\n", encoding="utf-8"
        )
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n"
            "| TECH-DEBT-021 | Wont Fix Item | WONT FIX | [file](./TECH-DEBT-021-wontfix.md) |\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        assert result.returncode == 0, (
            f"TD WONT FIX in Closed section should exit 0.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_td_wont_fix_apostrophe_is_closed(self, tmp_path: Path) -> None:
        """TECH-DEBT with Status: WON'T FIX (apostrophe) is classified closed."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        _write_minimal_indexes(bugs_dir, td_dir)
        (td_dir / "TECH-DEBT-022-wontfix2.md").write_text(
            "**Status**: WON'T FIX\n", encoding="utf-8"
        )
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n"
            "| TECH-DEBT-022 | Item | WON'T FIX | [file](./TECH-DEBT-022-wontfix2.md) |\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        assert result.returncode == 0, (
            f"TD WON'T FIX in Closed section should exit 0.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# T3 — empty tracking tree: honest message, never false-clean
# ---------------------------------------------------------------------------


class TestEmptyTree:
    def test_empty_bugs_and_td_dirs_no_false_clean(self, tmp_path: Path) -> None:
        """An empty tracking tree must print '0 records scanned', NOT '✓ in sync'."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        _write_minimal_indexes(bugs_dir, td_dir)

        result = _run(oversight, "--check")
        assert result.returncode == 0
        assert "0 records scanned" in result.stdout, (
            "Empty tree must print '0 records scanned', not a false-clean ✓.\n"
            f"stdout: {result.stdout}"
        )
        assert "fully in sync" not in result.stdout, (
            "Empty tree must NOT print 'fully in sync ✓' — that is a false-clean.\n"
            f"stdout: {result.stdout}"
        )


# ---------------------------------------------------------------------------
# T4 — missing bugs/ or tech-debt/ directory: graceful degradation
# ---------------------------------------------------------------------------


class TestMissingDirectory:
    def test_missing_bugs_dir_is_not_a_hard_error(self, tmp_path: Path) -> None:
        """A missing bugs/ directory must not exit 1 due to SystemExit (A.4)."""
        oversight = tmp_path / "oversight"
        oversight.mkdir()
        td_dir = oversight / "tech-debt"
        td_dir.mkdir()
        # No bugs/ dir at all
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        # Should not crash — stderr may carry a NOTE but no hard ERROR
        assert "Traceback" not in result.stderr, (
            f"Missing bugs/ dir should not raise an exception.\n"
            f"stderr: {result.stderr}"
        )
        assert (
            "0 records scanned" in result.stdout or "Bugs scanned : 0" in result.stdout
        )

    def test_missing_td_dir_is_not_a_hard_error(self, tmp_path: Path) -> None:
        """A missing tech-debt/ directory must not exit 1 due to SystemExit (A.4)."""
        oversight = tmp_path / "oversight"
        oversight.mkdir()
        bugs_dir = oversight / "bugs"
        bugs_dir.mkdir()
        # No tech-debt/ dir at all
        (bugs_dir / "INDEX.md").write_text(
            "# Bug Tracker Index\n\n" "## Open\n\n" "## Closed Bugs\n\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        assert "Traceback" not in result.stderr
        assert "TDs scanned  : 0" in result.stdout

    def test_missing_oversight_root_is_hard_error(self, tmp_path: Path) -> None:
        """A missing oversight/ root is still a hard error (non-zero exit)."""
        nonexistent = tmp_path / "does-not-exist"
        result = _run(nonexistent, "--check")
        assert result.returncode != 0
        assert "ERROR" in result.stderr


# ---------------------------------------------------------------------------
# T5 — missing INDEX when records exist: surfaced + counted in --check
# ---------------------------------------------------------------------------


class TestMissingIndex:
    def test_missing_bugs_index_counted_in_check(self, tmp_path: Path) -> None:
        """When bugs/ has records but no INDEX.md, --check exits 1 and reports it."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-001-some-bug.md").write_text(
            "**Status**: OPEN\n", encoding="utf-8"
        )
        # No bugs/INDEX.md written
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n",
            encoding="utf-8",
        )

        result = _run(oversight, "--check")
        assert result.returncode == 1, (
            f"Missing bugs INDEX with records present should exit 1.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "MISSING INDEX" in result.stdout
        assert "bugs/INDEX.md" in result.stdout

    def test_missing_td_index_counted_in_check(self, tmp_path: Path) -> None:
        """When tech-debt/ has records but no INDEX.md, --check exits 1 and reports it."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "INDEX.md").write_text(
            "# Bug Tracker Index\n\n" "## Open\n\n" "## Closed Bugs\n\n",
            encoding="utf-8",
        )
        (td_dir / "TECH-DEBT-001-something.md").write_text(
            "**Status**: OPEN\n", encoding="utf-8"
        )
        # No tech-debt/INDEX.md

        result = _run(oversight, "--check")
        assert result.returncode == 1
        assert "tech-debt/INDEX.md" in result.stdout

    def test_write_creates_missing_index(self, tmp_path: Path) -> None:
        """--write creates missing INDEX files and exits 0."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-001-some-bug.md").write_text(
            "**Status**: OPEN\n", encoding="utf-8"
        )
        (td_dir / "TECH-DEBT-001-some-td.md").write_text(
            "**Status**: RESOLVED\n", encoding="utf-8"
        )
        # Neither index exists

        result = _run(oversight, "--write")
        assert result.returncode == 0, (
            f"--write should exit 0 after creating missing INDEXes.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert (bugs_dir / "INDEX.md").exists()
        assert (td_dir / "INDEX.md").exists()

        # Post-write --check should find the newly created indexes and no missing
        check_result = _run(oversight, "--check")
        assert (
            "MISSING INDEX FILES (records exist but INDEX.md absent): 0"
            in check_result.stdout
        )


# ---------------------------------------------------------------------------
# T6 — skipped record-shaped files: counted in --check failure
# ---------------------------------------------------------------------------


class TestSkippedFiles:
    def test_uppercase_slug_file_is_skipped(self, tmp_path: Path) -> None:
        """BUG-005-BAD_SLUG.md starts with BUG- but has an uppercase slug → skipped."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        _write_minimal_indexes(bugs_dir, td_dir)
        (bugs_dir / "BUG-005-BAD_SLUG.md").write_text(
            "**Status**: OPEN\n", encoding="utf-8"
        )

        result = _run(oversight, "--check")
        assert result.returncode == 1, (
            "Skipped record-shaped files must count toward --check failure.\n"
            f"stdout: {result.stdout}"
        )
        assert "SKIPPED" in result.stdout
        assert "BUG-005-BAD_SLUG.md" in result.stdout

    def test_wrong_extension_file_is_skipped(self, tmp_path: Path) -> None:
        """BUG-007-some-bug.txt starts with BUG- but has wrong extension → skipped."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        _write_minimal_indexes(bugs_dir, td_dir)
        (bugs_dir / "BUG-007-some-bug.txt").write_text(
            "**Status**: OPEN\n", encoding="utf-8"
        )

        result = _run(oversight, "--check")
        assert result.returncode == 1
        assert "BUG-007-some-bug.txt" in result.stdout

    def test_valid_file_alongside_skipped_is_scanned(self, tmp_path: Path) -> None:
        """A valid BUG-008-real.md alongside a skipped file is still scanned."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        _write_minimal_indexes(bugs_dir, td_dir)
        (bugs_dir / "BUG-007-bad.txt").write_text(
            "**Status**: OPEN\n", encoding="utf-8"
        )
        (bugs_dir / "BUG-008-real.md").write_text(
            "**Status**: OPEN\n", encoding="utf-8"
        )

        result = _run(oversight, "--check")
        assert "Bugs scanned : 1" in result.stdout  # only the valid file
        assert "BUG-007-bad.txt" in result.stdout  # skipped section


# ---------------------------------------------------------------------------
# T7 — --write regeneration
# ---------------------------------------------------------------------------


class TestWriteRegeneration:
    def test_write_corrects_divergence(self, tmp_path: Path) -> None:
        """--write exits 0 and corrects a divergence; subsequent --check exits 0."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-301-reopened-bug.md").write_text(
            "# BUG-301: Reopened Bug\n\n"
            "**Status**: REOPENED (PM #295) — regression\n"
            "**Severity**: HIGH\n",
            encoding="utf-8",
        )
        (bugs_dir / "INDEX.md").write_text(
            "# Bug Tracker Index\n\n"
            "## Open\n\n"
            "## Closed Bugs\n\n"
            "| BUG-301 | Reopened Bug | FIXED | [file](./BUG-301-reopened-bug.md) |\n",
            encoding="utf-8",
        )
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n",
            encoding="utf-8",
        )

        # --check detects divergence
        check_pre = _run(oversight, "--check")
        assert check_pre.returncode == 1

        # --write corrects it
        write_result = _run(oversight, "--write")
        assert write_result.returncode == 0, (
            f"--write should exit 0.\n"
            f"stdout: {write_result.stdout}\nstderr: {write_result.stderr}"
        )

        # Post-write --check should pass
        check_post = _run(oversight, "--check")
        assert check_post.returncode == 0, (
            f"Post-write --check should exit 0.\n"
            f"stdout: {check_post.stdout}\nstderr: {check_post.stderr}"
        )
        assert "fully in sync" in check_post.stdout

    def test_write_slug_less_record_included_in_index(self, tmp_path: Path) -> None:
        """--write includes slug-less records in the generated INDEX."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-001.md").write_text(
            "# BUG-001: Slug-less Bug\n\n**Status**: OPEN\n**Severity**: HIGH\n",
            encoding="utf-8",
        )
        (td_dir / "TECH-DEBT-001.md").write_text(
            "# TECH-DEBT-001: Slug-less TD\n\n**Status**: OPEN\n",
            encoding="utf-8",
        )
        # No INDEXes yet

        result = _run(oversight, "--write")
        assert result.returncode == 0

        bugs_index_text = (bugs_dir / "INDEX.md").read_text(encoding="utf-8")
        assert "BUG-001" in bugs_index_text

        td_index_text = (td_dir / "INDEX.md").read_text(encoding="utf-8")
        assert "TECH-DEBT-001" in td_index_text

    def test_write_idempotent_slug_less(self, tmp_path: Path) -> None:
        """Two consecutive --write runs on a slug-less tree produce identical INDEXes."""
        oversight, bugs_dir, td_dir = _make_oversight(tmp_path)
        (bugs_dir / "BUG-001.md").write_text(
            "# BUG-001: Some Bug\n\n**Status**: OPEN\n**Severity**: LOW\n",
            encoding="utf-8",
        )
        (td_dir / "INDEX.md").write_text(
            "# Technical Debt Index\n\n"
            "## Open Technical Debt\n\n"
            "## Closed Technical Debt\n\n",
            encoding="utf-8",
        )

        _run(oversight, "--write")
        first_text = (bugs_dir / "INDEX.md").read_text(encoding="utf-8")

        _run(oversight, "--write")
        second_text = (bugs_dir / "INDEX.md").read_text(encoding="utf-8")

        assert first_text == second_text
