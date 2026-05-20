"""
Integration tests for decision-log body-coverage check (TD-554, F-2).

Tests invoke tracking_freshness.py --check against temporary oversight trees.
The live oversight tree is never touched.

Fixtures use realistic-shaped decision-log content per
``feedback_realistic_size_production_artifact_tests``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "tracking_freshness.py"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_minimal_oversight(tmp_path: Path) -> Path:
    """Create oversight/ with empty bugs/ and tech-debt/ index files.

    Returns the oversight Path.  Callers add tracking/decision-log.md as needed.
    """
    oversight = tmp_path / "oversight"
    bugs_dir = oversight / "bugs"
    td_dir = oversight / "tech-debt"
    bugs_dir.mkdir(parents=True)
    td_dir.mkdir()
    (bugs_dir / "INDEX.md").write_text(
        "# Bug Tracker Index\n\n## Open\n\n## Closed Bugs\n\n",
        encoding="utf-8",
    )
    (td_dir / "INDEX.md").write_text(
        "# Technical Debt Index\n\n"
        "## Open Technical Debt\n\n"
        "## Closed Technical Debt\n\n",
        encoding="utf-8",
    )
    return oversight


def _write_decision_log(oversight: Path, content: str) -> Path:
    tracking_dir = oversight / "tracking"
    tracking_dir.mkdir(exist_ok=True)
    log_path = tracking_dir / "decision-log.md"
    log_path.write_text(content, encoding="utf-8")
    return log_path


def _run_check(oversight: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--oversight-root", str(oversight)],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# F2-1: Header references missing from body → DRIFT-DEC-MISSING, exit 1
# ---------------------------------------------------------------------------


class TestDecisionLogMissingFlagged:
    def test_header_dec_missing_flagged(self, tmp_path: Path) -> None:
        """DEC IDs in header but absent from body ### headings → DRIFT-DEC-MISSING, exit 1."""
        decision_log = (
            "# Decision Log\n\n"
            "**Last Updated**: 2099-06-01\n\n"
            "**DEC-PM999-D1..D3**: Three decisions recorded during PM #999 sprint.\n\n"
            "  - DEC-PM999-D1: Adopt range notation for batched decision entries\n"
            "    to reduce header verbosity when multiple decisions share a PM session.\n"
            "  - DEC-PM999-D2: Write body coverage checker into tracking_freshness.py\n"
            "    rather than as a standalone script; folded into --check.\n"
            "  - DEC-PM999-D3: EXIT-1 on DRIFT-DEC-MISSING; DRIFT-DEC-ORPHAN is\n"
            "    informational-only (ℹ) and does not affect exit code.\n\n"  # noqa: RUF001
            "---\n\n"
            "### DEC-PM999-D2\n\n"
            "**Decision**: Body coverage checker folded into tracking_freshness.py `--check`.\n\n"
            "**Rationale**: Keeps the entire audit surface in a single invocable skill\n"
            "rather than requiring users to remember a second script. The coverage\n"
            "check is lightweight (file read + regex) and fits naturally alongside\n"
            "the existing staleness and status-drift checks.\n\n"
            "**Impact**: `--check` exit-1 now also fires when header refs are missing\n"
            "from the body. Teams must keep body headings in sync with header summaries.\n\n"
        )
        oversight = _make_minimal_oversight(tmp_path)
        _write_decision_log(oversight, decision_log)

        result = _run_check(oversight)

        assert result.returncode != 0, (
            "Expected non-zero exit code when DRIFT-DEC-MISSING exists.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "DRIFT-DEC-MISSING" in result.stdout, result.stdout
        assert "DEC-PM999-D1" in result.stdout, result.stdout
        assert "DEC-PM999-D3" in result.stdout, result.stdout
        # D2 is present in body — must NOT appear as missing
        missing_lines = [ln for ln in result.stdout.splitlines() if "✗" in ln]
        missing_ids = " ".join(missing_lines)
        assert "DEC-PM999-D2" not in missing_ids, (
            "DEC-PM999-D2 has a body heading and must not be flagged MISSING.\n"
            f"stdout: {result.stdout}"
        )


# ---------------------------------------------------------------------------
# F2-2: Body heading with no header ref → DRIFT-DEC-ORPHAN, exit 0
# ---------------------------------------------------------------------------


class TestDecisionLogOrphanFlagged:
    def test_body_orphan_flagged_informational(self, tmp_path: Path) -> None:
        """### body heading with no header reference → DRIFT-DEC-ORPHAN, exit 0."""
        decision_log = (
            "# Decision Log\n\n"
            "**Last Updated**: 2099-06-01\n\n"
            "No decisions recorded in the header summary for this session.\n\n"
            "---\n\n"
            "### DEC-PM999-D1\n\n"
            "**Decision**: Adopt .env.secrets split for secret-class keys at install time.\n\n"
            "**Rationale**: World-readable .env files expose secrets to any process that\n"
            "can read the install directory. Moving secrets to chmod-600 .env.secrets\n"
            "limits exposure to the owning user and prevents accidental logging of env\n"
            "dumps that include the full .env payload.\n\n"
            "**Impact**: Installer must be updated to split keys at install time.\n"
            "Existing installations require a one-time migration script.\n\n"
        )
        oversight = _make_minimal_oversight(tmp_path)
        _write_decision_log(oversight, decision_log)

        result = _run_check(oversight)

        assert result.returncode == 0, (
            "DRIFT-DEC-ORPHAN is informational; must not cause non-zero exit.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "DRIFT-DEC-ORPHAN" in result.stdout, result.stdout
        assert "DEC-PM999-D1" in result.stdout, result.stdout
        assert "ℹ" in result.stdout, (  # noqa: RUF001
            "ORPHAN entries must use ℹ marker.\n"  # noqa: RUF001
            f"stdout: {result.stdout}"
        )
        # No missing IDs → must show coverage-complete confirmation
        assert "✓" in result.stdout, (
            "Expected ✓ coverage-complete marker when MISSING count is zero.\n"
            f"stdout: {result.stdout}"
        )


# ---------------------------------------------------------------------------
# F2-3: Header and body in sync → no drift, ✓ message, exit 0
# ---------------------------------------------------------------------------


class TestDecisionLogCleanRoundTrip:
    def test_header_and_body_match_no_drift(self, tmp_path: Path) -> None:
        """Header D1..D3 + all three body headings → zero drift, ✓ message, exit 0."""
        decision_log = (
            "# Decision Log\n\n"
            "**Last Updated**: 2099-06-01\n\n"
            "**DEC-PM999-D1..D3**: Decisions from PM #999 correctness sprint.\n\n"
            "  - DEC-PM999-D1: Use SHA-256 for chunk deduplication over UUID5.\n"
            "  - DEC-PM999-D2: Fold decision-log coverage check into --check.\n"
            "  - DEC-PM999-D3: EXIT-1 on DRIFT-DEC-MISSING only; ORPHAN is ℹ.\n\n"  # noqa: RUF001
            "---\n\n"
            "### DEC-PM999-D1\n\n"
            "**Decision**: SHA-256 for chunk deduplication in the injection pipeline.\n\n"
            "**Rationale**: UUID5 provides namespace-scoped uniqueness but is not\n"
            "content-addressed — two chunks with identical text but different metadata\n"
            "get different IDs. SHA-256 is deterministic on content, enabling exact\n"
            "deduplication across re-injection of unchanged documents.\n\n"
            "**Impact**: Existing chunk IDs in Qdrant are UUID5; migration required\n"
            "before dedup logic can be applied to the live collection.\n\n"
            "### DEC-PM999-D2\n\n"
            "**Decision**: Decision-log coverage check folded into `--check` default.\n\n"
            "**Rationale**: Same rationale as noted in header — keeps audit surface\n"
            "consolidated. No additional flag required by the user.\n\n"
            "**Impact**: `--check` exit-1 now fires on DRIFT-DEC-MISSING.\n\n"
            "### DEC-PM999-D3\n\n"
            "**Decision**: Only DRIFT-DEC-MISSING causes exit-1; DRIFT-DEC-ORPHAN\n"
            "is informational.\n\n"
            "**Rationale**: Orphan body headings represent historical decisions whose\n"
            "header summary was not retroactively updated. That is a minor hygiene\n"
            "issue, not a blocking correctness problem. MISSING refs, by contrast,\n"
            "indicate that a body entry was promised but never written — a gap in\n"
            "the decision record that reviewers rely on.\n\n"
            "**Impact**: Teams may accumulate orphan headings without CI failure.\n\n"
        )
        oversight = _make_minimal_oversight(tmp_path)
        _write_decision_log(oversight, decision_log)

        result = _run_check(oversight)

        assert result.returncode == 0, (
            "Expected zero exit when header and body are fully in sync.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "DRIFT-DEC-MISSING" in result.stdout, result.stdout
        assert (
            "DRIFT-DEC-MISSING (header ref, no body entry): 0" in result.stdout
        ), f"Expected zero MISSING count.\nstdout: {result.stdout}"
        assert (
            "DRIFT-DEC-ORPHAN (body heading, no header ref): 0" in result.stdout
        ), f"Expected zero ORPHAN count.\nstdout: {result.stdout}"
        assert "✓" in result.stdout, (
            "Expected ✓ coverage-complete marker.\n" f"stdout: {result.stdout}"
        )


# ---------------------------------------------------------------------------
# F2-4: Missing decision-log.md → graceful skip, NOTE in stderr, exit 0
# ---------------------------------------------------------------------------


class TestDecisionLogMissingFile:
    def test_missing_decision_log_graceful_skip(self, tmp_path: Path) -> None:
        """No tracking/decision-log.md → NOTE in stderr, zero MISSING, exit 0."""
        oversight = _make_minimal_oversight(tmp_path)
        # Intentionally do NOT create tracking/ or decision-log.md

        result = _run_check(oversight)

        assert result.returncode == 0, (
            "Missing decision-log.md must not cause non-zero exit.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "NOTE" in result.stderr, (
            "Expected NOTE in stderr when decision-log.md is absent.\n"
            f"stderr: {result.stderr}"
        )
        assert "decision-log" in result.stderr.lower(), result.stderr
        # No DRIFT-DEC-MISSING entries expected
        assert "✗" not in result.stdout, (
            "No MISSING markers expected when decision-log.md is absent.\n"
            f"stdout: {result.stdout}"
        )
