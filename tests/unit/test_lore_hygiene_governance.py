"""Unit tests for the TASK-077 B2/B3 governance additions to aim-lore-hygiene.

Lives under repo ``tests/`` (CI's ``testpaths``) — the skill's own
``aim-lore-hygiene/tests/`` is outside CI discovery, so the load-bearing
governance proofs are asserted here where ``pytest tests/`` will run them.

Covers:
- B2 shared-core import: lore_hygiene uses the SAME Contract + conservation
  modules as aim-tracking-rotate (pov/lib/governance), no local copies.
- B2 conservation proof: prove-then-commit leaves originals byte-identical on a
  forced failure; a dropped (count-loss) relocation is caught (multiset).
- B3 PERSONA section-cap: ## Evolution Log keeps the last N rows, relocates older
  ones losslessly, leaves one pointer; symbolic anchor (never line numbers).
- B3 CREED/BOND check-only: an over-cap identity file HALTs (non-zero) and is
  never mutated.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "_ai-memory/pov/skills/aim-lore-hygiene/scripts/lore_hygiene.py"

_spec = importlib.util.spec_from_file_location("lore_hygiene", _SCRIPT)
_lh = importlib.util.module_from_spec(_spec)
sys.modules["lore_hygiene"] = _lh
_spec.loader.exec_module(_lh)

from datetime import date  # noqa: E402

TODAY = date(2026, 6, 19)


# ---------------------------------------------------------------------------
# B2 — shared-core import (no local Contract/conservation copies)
# ---------------------------------------------------------------------------


def test_uses_shared_contract_and_conservation() -> None:
    # The Contract dataclass is the shared one from pov/lib/governance/contract.py.
    assert _lh.Contract.__module__ == "contract"
    # conservation resolves to the canonical lib/governance copy, not a sibling.
    assert _lh.conservation.__file__.replace("\\", "/").endswith(
        "_ai-memory/pov/lib/governance/conservation.py"
    )
    # And the shared content-set helpers are present (not re-implemented locally).
    for fn in (
        "build_content_set",
        "build_content_set_from_texts",
        "assert_no_content_loss",
    ):
        assert hasattr(_lh.conservation, fn)


# ---------------------------------------------------------------------------
# B2 — prove-then-commit conservation
# ---------------------------------------------------------------------------


def _write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def test_forced_conservation_failure_leaves_original_byte_identical(
    tmp_path: Path,
) -> None:
    """A plan that drops an 'archived' entry from hot WITHOUT putting it in the
    archive must be refused — apply_plan returns False and writes nothing."""
    hot = tmp_path / "LORE.md"
    original = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        "- A genuine lesson that must never vanish.\n"
        "- A second kept lesson.\n"
    )
    _write(hot, original)
    before_bytes = hot.read_bytes()

    # A BUGGY plan: claims to archive the first lesson but new_text simply omits it
    # and archived_blocks is empty (the silent-drop relocation bug the proof guards).
    plan = _lh.FilePlan(
        filename="LORE.md",
        cap=200,
        original_lines=len(original.splitlines()),
        new_text=(
            "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
            "- A second kept lesson.\n"
        ),
        archived_blocks=[],
        actions=[
            _lh.EntryAction(
                "- A genuine lesson that must never vanish.",
                "## Things Learned the Hard Way",
                "archive",
                "buggy: claims archive but drops it",
            )
        ],
    )

    ok = _lh.apply_plan(hot, plan, TODAY, qdrant=False, group_id="", agent_id="x")
    assert ok is False
    assert hot.read_bytes() == before_bytes, "hot file mutated despite failed proof"
    assert not (
        tmp_path / "references" / "lore-archive"
    ).exists(), "archive written despite failed proof"
    assert not list(
        tmp_path.glob("LORE.md.*.bak")
    ), "backup written despite failed proof"


def test_multiset_count_loss_is_caught() -> None:
    """prove_conservation catches a dropped one-of-two identical lines (multiset)."""
    # Two identical hot lines; after-state keeps only one; nothing declared removed.
    line = "- duplicated lesson line"
    before_hot = Counter({line: 2, "- other": 1})
    # Drive the assertion the proof uses directly with the shared helper.
    after = _lh.conservation.build_content_set_from_texts(
        [f"{line}\n- other\n"]  # only ONE copy of the duplicated line survives
    )
    with pytest.raises(AssertionError):
        _lh.conservation.assert_no_content_loss(before_hot, after)


def test_idempotent_rerun_after_archival_does_not_false_fail(tmp_path: Path) -> None:
    """The crash-rerun collapse (entry in BOTH hot and archive → one archived copy)
    must NOT be mis-flagged as a loss (the split-baseline fix)."""
    sanc = tmp_path
    hot = sanc / "LORE.md"
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        "- [stale] Historical decision 0 about the old pipeline.\n"
        "  Context that mattered at the time.\n"
    )
    _write(hot, content)
    r1 = _run_cli(str(sanc), "--apply")
    assert r1.returncode == 0, r1.stderr
    # Re-introduce the same [stale] entry and re-apply (crash-rerun).
    _write(hot, content)
    r2 = _run_cli(str(sanc), "--apply")
    assert r2.returncode == 0, r2.stderr
    archive = (sanc / "references/lore-archive/LORE.archive.md").read_text()
    assert archive.count("Historical decision 0 about the old pipeline.") == 1


# ---------------------------------------------------------------------------
# B3 — PERSONA ## Evolution Log section-cap
# ---------------------------------------------------------------------------


def _persona(rows: int) -> str:
    head = (
        "---\ntype: sanctum-persona\nagent: parzival\n---\n\n# Persona\n\n"
        "## Identity\n\n- **Name:** Parzival\n\n"
        "## Evolution Log\n\n"
        "*Identity-level changes only.*\n\n"
        "| Date | Identity shift | Why |\n"
        "|------|----------------|-----|\n"
    )
    body = "".join(
        f"| 2026-06-{i:02d} | Shift number {i}. | Reason {i}. |\n"
        for i in range(1, rows + 1)
    )
    return head + body


def test_persona_section_cap_keeps_last_n_and_relocates_rest(tmp_path: Path) -> None:
    contract = _lh.SANCTUM_CONTRACTS["PERSONA.md"]
    assert contract.section_anchor == "## Evolution Log"
    keep = contract.section_keep_last
    text = _persona(rows=keep + 7)  # 7 over the cap
    plan = _lh.plan_section_cap(text, "PERSONA.md", contract, TODAY)

    # Exactly the 7 oldest rows relocate.
    assert len([a for a in plan.actions if a.action == "archive"]) == 7
    # Newest `keep` rows remain in hot; the 7 oldest do not.
    for i in range(keep + 1, keep + 8):  # newest rows kept
        assert f"Shift number {i}." in plan.new_text
    for i in range(1, 8):  # oldest rows relocated out of hot
        assert f"| 2026-06-{i:02d} | Shift number {i}." not in plan.new_text
    # Exactly one pointer left behind, and the structural table header survived.
    assert plan.new_text.count("_[archived 2026-06-19]_") == 1
    assert "| Date | Identity shift | Why |" in plan.new_text
    # Relocated rows are preserved verbatim in the archive block.
    assert plan.archived_blocks
    for i in range(1, 8):
        assert f"| 2026-06-{i:02d} | Shift number {i}." in plan.archived_blocks[0]


def test_persona_section_cap_under_cap_is_noop(tmp_path: Path) -> None:
    contract = _lh.SANCTUM_CONTRACTS["PERSONA.md"]
    text = _persona(rows=contract.section_keep_last)  # exactly at cap
    plan = _lh.plan_section_cap(text, "PERSONA.md", contract, TODAY)
    assert not plan.has_changes
    assert plan.archived_blocks == []


def test_persona_section_cap_apply_conserves(tmp_path: Path) -> None:
    contract = _lh.SANCTUM_CONTRACTS["PERSONA.md"]
    hot = tmp_path / "PERSONA.md"
    _write(hot, _persona(rows=contract.section_keep_last + 5))
    plan = _lh.plan_section_cap(
        _lh.read_preserving_newlines(hot), "PERSONA.md", contract, TODAY
    )
    ok = _lh.apply_plan(hot, plan, TODAY, qdrant=False, group_id="", agent_id="x")
    assert ok is True
    archive = (tmp_path / "references/lore-archive/PERSONA.archive.md").read_text()
    # Every relocated row survives in the cold archive.
    for i in range(1, 6):
        assert f"Shift number {i}." in archive


# ---------------------------------------------------------------------------
# B3 — CREED / BOND check-only (HALT on over-cap, never mutate)
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_creed_over_cap_halts_and_does_not_mutate(tmp_path: Path) -> None:
    creed = tmp_path / "CREED.md"
    # 130 lines > the 120-line CREED cap.
    _write(
        creed,
        "---\ntype: sanctum-creed\n---\n\n# Creed\n"
        + "\n".join(f"- Standing order {i}." for i in range(130))
        + "\n",
    )
    before = creed.read_bytes()
    r = _run_cli(str(tmp_path), "--apply")
    assert r.returncode == 1, r.stdout  # over-cap identity file HALTs
    assert "OVER CAP" in r.stdout
    assert "check-only" in r.stdout
    assert creed.read_bytes() == before, "check-only class was mutated"
    assert not list(
        tmp_path.glob("CREED.md.*.bak")
    ), "check-only class was backed up/mutated"


def test_creed_under_cap_passes(tmp_path: Path) -> None:
    creed = tmp_path / "CREED.md"
    _write(creed, "---\ntype: sanctum-creed\n---\n\n# Creed\n\n- One standing order.\n")
    r = _run_cli(str(tmp_path), "--apply")
    assert r.returncode == 0, r.stderr
    assert "within cap" in r.stdout


# ---------------------------------------------------------------------------
# B5 — session-close --check gate (sanctum classes)
# ---------------------------------------------------------------------------


def test_check_gate_clean_passes(tmp_path: Path) -> None:
    _write(tmp_path / "CREED.md", "---\ntype: creed\n---\n# Creed\n- one\n")
    _write(tmp_path / "PERSONA.md", _persona(rows=5))  # under the 10-row cap
    # LORE present + under cap → exercises the compact strategy path (test-gap fix).
    _write(tmp_path / "LORE.md", "---\ntype: lore\n---\n# Lore\n- a small lesson\n")
    r = _run_cli(str(tmp_path), "--check")
    assert r.returncode == 0, r.stderr
    assert "PASS" in r.stdout


def test_check_gate_lore_oversize_untagged_is_reporting_only(tmp_path: Path) -> None:
    """A sanctum dir whose ONLY breach is an over-size, untagged LORE → --check
    exits 0 (warning printed), never mutates. The compact-class file-size cap is
    reporting-only per A2 (tag-driven rotation is not a closeout blocker)."""
    lore = tmp_path / "LORE.md"
    # >200 lines AND >25 KB, with ZERO tagged entries (so --apply would be a no-op).
    big = "- A genuine untagged lesson with enough prose to grow the file. " * 4
    _write(
        lore,
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        + "\n".join(f"{big} entry {i}" for i in range(260))
        + "\n",
    )
    n_lines = len(lore.read_text(encoding="utf-8").splitlines())
    n_kb = len(lore.read_bytes()) / 1024
    assert (
        n_lines > 200 and n_kb > 25
    ), f"fixture not over cap: {n_lines}L / {n_kb:.1f}KB"
    before = lore.read_bytes()

    r = _run_cli(str(tmp_path), "--check")
    assert r.returncode == 0, r.stderr  # reporting-only → exit 0
    assert "WARNING" in r.stdout and "LORE.md" in r.stdout
    assert "reporting-only" in r.stdout
    assert "SYSTEM FAILURE" not in r.stderr
    assert lore.read_bytes() == before  # read-only, never mutated


def test_check_gate_blocks_on_breach_without_mutating(tmp_path: Path) -> None:
    # CREED over its line cap + PERSONA Evolution Log over the 10-entry cap.
    _write(
        tmp_path / "CREED.md",
        "---\ntype: creed\n---\n# Creed\n"
        + "\n".join(f"- o{i}" for i in range(130))
        + "\n",
    )
    _write(tmp_path / "PERSONA.md", _persona(rows=15))
    # An over-size LORE alongside the real breaches: compact-class size is
    # reporting-only, so it must NOT appear as a breach (test-gap fix — confirms
    # the compact path is exercised even when blocking breaches exist).
    _write(
        tmp_path / "LORE.md",
        "---\ntype: lore\n---\n# Lore\n"
        + "\n".join(f"- lesson {i}" for i in range(260))
        + "\n",
    )
    creed_before = (tmp_path / "CREED.md").read_bytes()
    persona_before = (tmp_path / "PERSONA.md").read_bytes()
    lore_before = (tmp_path / "LORE.md").read_bytes()

    r = _run_cli(str(tmp_path), "--check")
    assert r.returncode == 1
    assert "SYSTEM FAILURE" in r.stderr
    assert "CREED.md" in r.stderr and "PERSONA.md" in r.stderr
    assert "BLOCKED" in r.stderr
    # LORE is reporting-only: a WARNING on stdout, never a breach on stderr.
    assert "LORE.md" not in r.stderr
    assert "WARNING" in r.stdout and "LORE.md" in r.stdout
    # Read-only: no file touched, no backup, no archive.
    assert (tmp_path / "CREED.md").read_bytes() == creed_before
    assert (tmp_path / "PERSONA.md").read_bytes() == persona_before
    assert (tmp_path / "LORE.md").read_bytes() == lore_before
    assert not list(tmp_path.glob("*.bak"))
    assert not (tmp_path / "references").exists()


def test_check_rejects_apply_combo(tmp_path: Path) -> None:
    _write(tmp_path / "CREED.md", "---\ntype: creed\n---\n# Creed\n- one\n")
    r = _run_cli(str(tmp_path), "--check", "--apply")
    assert r.returncode != 0
    assert "read-only" in (r.stderr + r.stdout)
