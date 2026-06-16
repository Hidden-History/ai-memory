"""Unit tests for the aim-tracking-rotate skill script (PLAN-028 D3).

Covers:
- --check exit-code contract: zero when compliant, non-zero on breach, across
  BOTH the front-matter cap path and the built-in fallback-registry path.
- Front-matter cap overrides the fallback registry.
- --apply rotation: oldest contiguous block moved without splitting an entry,
  manifest updated (append-only-log), reconciliation banner updated (register),
  thin live pointer written, entry counts conserved.
- --apply refuses non-rotatable (heartbeat / thin) files.
- Pointer write is idempotent across repeated --apply runs.

Fixtures are small synthetic trees in tmp_path; no dependency on the live
oversight/ tree.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the skill script via importlib (lives outside any installable package)
# ---------------------------------------------------------------------------

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "_ai-memory"
    / "pov"
    / "skills"
    / "aim-tracking-rotate"
    / "scripts"
    / "tracking_rotate.py"
)

_spec = importlib.util.spec_from_file_location("tracking_rotate", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
# Register before exec so dataclasses can resolve the module by __module__.
sys.modules["tracking_rotate"] = _mod
_spec.loader.exec_module(_mod)

measure = _mod.measure
over_cap = _mod.over_cap
split_front_matter = _mod.split_front_matter
parse_contract_front_matter = _mod.parse_contract_front_matter
parse_entries = _mod.parse_entries
is_resolved = _mod.is_resolved
FALLBACK_REGISTRY = _mod.FALLBACK_REGISTRY
DEFAULT_ENTRY_PATTERN = _mod.DEFAULT_ENTRY_PATTERN
POINTER_MARKER = _mod.POINTER_MARKER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _make_oversight(tmp_path: Path) -> Path:
    root = tmp_path / "oversight"
    (root / "tracking").mkdir(parents=True)
    (root / "session-index").mkdir(parents=True)
    (root / "session-logs").mkdir(parents=True)
    return root


def _decision_log(n_entries: int) -> str:
    """Newest-first decision log: DEC-PM{n} newest at top, DEC-PM001 oldest."""
    head = (
        "# Decision Log\n\n"
        "**Purpose**: Track all architectural and project decisions.\n\n"
        "**Last Updated**: 2026-06-16\n\n"
    )
    blocks = []
    for i in range(n_entries, 0, -1):
        blocks.append(
            f"### DEC-PM{i:03d}-D1 — decision number {i}\n\n"
            f"Decision: did thing {i}.\nRationale: because {i}.\n\n"
        )
    return head + "".join(blocks)


def _blockers_log(n_entries: int, active: int) -> str:
    """Newest-first blockers register. The newest ``active`` entries carry
    ``Status: Open``; the oldest ``n_entries - active`` carry ``Status: Resolved``
    (eligible to archive). H-5: an OPEN entry must never be archived.
    """
    head = (
        "# Blockers Log\n\n"
        f"**{active} active as of PM #10**\n\n"
        "## Active Blockers\n\n"
    )
    blocks = []
    for i in range(n_entries, 0, -1):
        status = "Open" if i > (n_entries - active) else "Resolved"
        blocks.append(
            f"### BUG-{i:03d}: blocker {i}\n\n"
            f"**Status**: {status}\n\nSome detail line {i}.\n\n"
        )
    return head + "".join(blocks)


def _table_index(n_rows: int, title: str) -> str:
    """Newest-first table-row live-index (SWI / session-index shape).

    Header row ``| ID | Summary |`` + separator are preamble-adjacent; data rows
    ``| S-### | ... |`` are the rotatable entries (entry_pattern ``^\\| ``).
    """
    head = f"# {title}\n\n## Sessions\n\n| ID | Summary |\n|---|---|\n"
    rows = "".join(
        f"| S-{i:03d} | summary line number {i} goes here for bulk |\n"
        for i in range(n_rows, 0, -1)
    )
    return head + rows


# ---------------------------------------------------------------------------
# --check : fallback-registry path
# ---------------------------------------------------------------------------


def test_check_passes_compliant_fallback_registry(tmp_path: Path) -> None:
    root = _make_oversight(tmp_path)
    (root / "tracking" / "decision-log.md").write_text(
        _decision_log(3), encoding="utf-8"
    )
    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_check_fails_over_cap_fallback_registry(tmp_path: Path) -> None:
    root = _make_oversight(tmp_path)
    # decision-log cap is 150 lines via fallback registry; 80 entries blow it.
    (root / "tracking" / "decision-log.md").write_text(
        _decision_log(80), encoding="utf-8"
    )
    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 1
    assert "SYSTEM FAILURE" in result.stderr
    assert "fallback-registry" in result.stderr
    assert "decision-log.md" in result.stderr


# ---------------------------------------------------------------------------
# --check : front-matter path (and override)
# ---------------------------------------------------------------------------


def test_check_fails_over_cap_front_matter(tmp_path: Path) -> None:
    root = _make_oversight(tmp_path)
    body = "\n".join(f"line {i}" for i in range(20)) + "\n"
    fm = (
        "---\n"
        "class: live-index\n"
        "read_path: whole-file\n"
        "cap_lines: 3\n"
        "cap_kb: 1\n"
        "rotation_trigger: on-close-over-cap\n"
        "archive_target: session-index/INDEX.md\n"
        "---\n"
    )
    (root / "SESSION_WORK_INDEX.md").write_text(fm + body, encoding="utf-8")
    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 1
    assert "via front-matter" in result.stderr


def test_front_matter_cap_overrides_registry(tmp_path: Path) -> None:
    root = _make_oversight(tmp_path)
    # task-tracker registry cap is 40 lines; a generous front-matter cap must win.
    body = "\n".join(f"line {i}" for i in range(100)) + "\n"
    fm = (
        "---\n"
        "class: register\n"
        "read_path: section-anchored\n"
        "cap_lines: 5000\n"
        "cap_kb: 5000\n"
        "rotation_trigger: none\n"
        "---\n"
    )
    (root / "tracking" / "task-tracker.md").write_text(fm + body, encoding="utf-8")
    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# --apply : append-only-log (manifest)
# ---------------------------------------------------------------------------


def test_apply_decision_log_rotates_and_updates_manifest(tmp_path: Path) -> None:
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    log.write_text(_decision_log(80), encoding="utf-8")

    result = _run(
        "--apply", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    # Live file now within cap.
    new_text = log.read_text(encoding="utf-8")
    lines, _ = measure(new_text)
    assert lines <= FALLBACK_REGISTRY["tracking/decision-log.md"].cap_lines

    # Thin pointer present (exactly one).
    assert new_text.count(POINTER_MARKER) == 1

    # Shard exists and holds the OLDEST entries (DEC-PM001 must be archived).
    shard = root / "tracking" / "archive" / "decision-log-ARCHIVE-2026-06.md"
    assert shard.is_file()
    shard_text = shard.read_text(encoding="utf-8")
    assert "DEC-PM001-D1" in shard_text
    assert "DEC-PM001-D1" not in new_text  # oldest left the live file

    # Newest entry stays live.
    assert "DEC-PM080-D1" in new_text

    # Manifest updated with archived ids.
    manifest = root / "tracking" / "decision-log-INDEX.md"
    assert manifest.is_file()
    manifest_text = manifest.read_text(encoding="utf-8")
    assert "DEC-PM001-D1" in manifest_text
    assert "decision-log-ARCHIVE-2026-06.md" in manifest_text

    # Count conservation: live entries + archived entries == original 80.
    live_entries = parse_entries(new_text, DEFAULT_ENTRY_PATTERN).entries
    archived_entries = parse_entries(
        "## archive\n" + shard_text, DEFAULT_ENTRY_PATTERN
    ).entries
    assert len(live_entries) + len(archived_entries) == 80

    # No entry split: every archived block starts with its own header.
    for e in archived_entries:
        assert e.block.lstrip().startswith("### DEC-")


def test_apply_idempotent_pointer(tmp_path: Path) -> None:
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    log.write_text(_decision_log(80), encoding="utf-8")
    _run("--apply", str(log), "--oversight-root", str(root), "--period", "2026-06")
    _run("--apply", str(log), "--oversight-root", str(root), "--period", "2026-06")
    # Re-running must not stack pointer lines.
    assert log.read_text(encoding="utf-8").count(POINTER_MARKER) == 1


# ---------------------------------------------------------------------------
# --apply : register (banner)
# ---------------------------------------------------------------------------


def test_apply_register_updates_banner(tmp_path: Path) -> None:
    root = _make_oversight(tmp_path)
    blk = root / "tracking" / "blockers-log.md"
    # 10 newest OPEN, 50 oldest RESOLVED -> resolved rotate out, open stay live.
    blk.write_text(_blockers_log(60, active=10), encoding="utf-8")

    result = _run(
        "--apply", str(blk), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = blk.read_text(encoding="utf-8")
    kept = parse_entries(new_text, DEFAULT_ENTRY_PATTERN).entries
    # M-1: banner reflects the OPEN count, with no stale "as of PM #X" suffix.
    open_kept = sum(1 for e in kept if not is_resolved(e))
    assert open_kept == 10
    assert f"**{open_kept} active**" in new_text
    assert "as of PM" not in new_text

    archive = root / "tracking" / "blockers-archive-2026.md"
    assert archive.is_file()
    assert POINTER_MARKER in new_text

    # H-5: every archived entry is RESOLVED — no open/active entry was evicted.
    archived = parse_entries(
        "## arch\n" + archive.read_text(encoding="utf-8"), DEFAULT_ENTRY_PATTERN
    ).entries
    for e in archived:
        assert is_resolved(e), f"archived an OPEN entry: {e.header}"

    # H-6: count conservation — live + archived == original.
    assert len(kept) + len(archived) == 60


def test_apply_register_never_archives_old_open_blocker(tmp_path: Path) -> None:
    """H-5: an OPEN blocker that is the OLDEST entry must stay live; only
    RESOLVED entries are archived even though they are newer than it.
    """
    root = _make_oversight(tmp_path)
    blk = root / "tracking" / "blockers-log.md"
    head = "# Blockers Log\n\n**1 active as of PM #9**\n\n## Active Blockers\n\n"
    blocks = []
    for i in range(40, 0, -1):  # newest-first: BUG-040 .. BUG-001 (oldest)
        status = "Open" if i == 1 else "Resolved"
        blocks.append(
            f"### BUG-{i:03d}: blocker {i}\n\n**Status**: {status}\n\nDetail {i}.\n\n"
        )
    blk.write_text(head + "".join(blocks), encoding="utf-8")

    result = _run(
        "--apply", str(blk), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = blk.read_text(encoding="utf-8")
    archive = root / "tracking" / "blockers-archive-2026.md"
    archived_text = archive.read_text(encoding="utf-8") if archive.is_file() else ""

    # The old OPEN blocker remains live and was NOT archived.
    assert "### BUG-001:" in new_text
    assert "### BUG-001:" not in archived_text
    # Everything that WAS archived is resolved.
    archived = parse_entries("## arch\n" + archived_text, DEFAULT_ENTRY_PATTERN).entries
    assert archived, "expected some resolved entries to be archived"
    for e in archived:
        assert is_resolved(e), f"archived an OPEN entry: {e.header}"


# ---------------------------------------------------------------------------
# --apply : atomicity + idempotency (H-1)
# ---------------------------------------------------------------------------


def test_apply_reapply_no_double_append(tmp_path: Path) -> None:
    """H-1 reproduction: a repeated --apply (e.g. after an interrupted run where
    the live write was lost) must NOT double-append the same entries to the
    shard.
    """
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    shard = root / "tracking" / "archive" / "decision-log-ARCHIVE-2026-06.md"

    log.write_text(_decision_log(80), encoding="utf-8")
    _run("--apply", str(log), "--oversight-root", str(root), "--period", "2026-06")
    first_count = shard.read_text(encoding="utf-8").count("### DEC-")

    # Simulate the lost-live-write interruption: live is back to the full 80.
    log.write_text(_decision_log(80), encoding="utf-8")
    _run("--apply", str(log), "--oversight-root", str(root), "--period", "2026-06")
    second = shard.read_text(encoding="utf-8")

    assert (
        second.count("### DEC-") == first_count
    ), f"shard double-appended: {first_count} -> {second.count('### DEC-')}"
    ids = re.findall(r"### (DEC-\S+)", second)
    assert len(ids) == len(set(ids)), "duplicate ids in shard after re-apply"


# ---------------------------------------------------------------------------
# --apply : live-index table-row rotation (H-3)
# ---------------------------------------------------------------------------


def test_apply_session_work_index_table_rows(tmp_path: Path) -> None:
    """H-3: SESSION_WORK_INDEX.md rotates by table row (contract entry_pattern
    '^\\| '), not the H3 default — previously found zero entries.
    """
    root = _make_oversight(tmp_path)
    swi = root / "SESSION_WORK_INDEX.md"
    swi.write_text(_table_index(100, "Session Work Index"), encoding="utf-8")

    result = _run(
        "--apply", str(swi), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = swi.read_text(encoding="utf-8")
    lines, _ = measure(new_text)
    assert lines <= FALLBACK_REGISTRY["SESSION_WORK_INDEX.md"].cap_lines

    archive = root / "session-index" / "INDEX.md"
    assert archive.is_file()
    archive_text = archive.read_text(encoding="utf-8")
    assert "| S-001 |" in archive_text  # oldest row archived
    assert "| S-100 |" in new_text  # newest row kept live
    assert "| ID | Summary |" in new_text  # header row retained
    assert POINTER_MARKER in new_text


def test_apply_session_index_table_rows(tmp_path: Path) -> None:
    """H-3: session-index/INDEX.md rotates by table row into a quarterly shard."""
    root = _make_oversight(tmp_path)
    idx = root / "session-index" / "INDEX.md"
    idx.write_text(_table_index(150, "Session Index"), encoding="utf-8")

    result = _run(
        "--apply", str(idx), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = idx.read_text(encoding="utf-8")
    lines, _ = measure(new_text)
    assert lines <= FALLBACK_REGISTRY["session-index/INDEX.md"].cap_lines

    shard = root / "session-index" / "archive" / "2026-Q2.md"
    assert shard.is_file()
    assert "| S-001 |" in shard.read_text(encoding="utf-8")
    assert POINTER_MARKER in new_text


# ---------------------------------------------------------------------------
# --apply / --check : exhausted (deadlock) path (H-4)
# ---------------------------------------------------------------------------


def _all_open_blockers(n: int) -> str:
    head = f"# Blockers Log\n\n**{n} active as of PM #9**\n\n## Active Blockers\n\n"
    blocks = "".join(
        f"### BUG-{i:03d}: blocker {i}\n\n**Status**: Open\n\nDetail line {i}.\n\n"
        for i in range(n, 0, -1)
    )
    return head + blocks


def test_apply_exhausted_exits_nonzero(tmp_path: Path) -> None:
    """H-4: when every live entry is OPEN and the file is over cap, --apply
    cannot rotate it under cap — it must exit non-zero with a hand-trim remedy
    (never exit 0, which would deadlock the gate into re-running --apply).
    """
    root = _make_oversight(tmp_path)
    blk = root / "tracking" / "blockers-log.md"
    blk.write_text(_all_open_blockers(80), encoding="utf-8")

    result = _run(
        "--apply", str(blk), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 1
    assert "exhausted" in result.stderr.lower()


def test_check_remedy_handtrim_when_exhausted(tmp_path: Path) -> None:
    """H-4: --check's remedy for an exhausted file points to a hand-trim, NOT
    back to --apply.
    """
    root = _make_oversight(tmp_path)
    blk = root / "tracking" / "blockers-log.md"
    blk.write_text(_all_open_blockers(80), encoding="utf-8")

    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 1
    assert "by hand" in result.stderr
    assert "--apply" not in result.stderr  # do not loop the operator back


# ---------------------------------------------------------------------------
# parse_entries : never split an entry on a heading-in-body (H-2)
# ---------------------------------------------------------------------------


def test_parse_entries_ignores_heading_in_fenced_body() -> None:
    """H-2: a markdown heading quoted inside an entry's fenced code block must
    NOT start a phantom entry or split the real entry mid-body.
    """
    text = (
        "# Decision Log\n\n"
        "### DEC-PM900-D1 — real decision\n\n"
        "Decision: do the thing.\n\n"
        "```md\n"
        "### DEC-OLD-style heading quoted in the body, not a real entry\n"
        "more body text inside the fence\n"
        "```\n\n"
        "Rationale: because reasons.\n\n"
        "### DEC-PM901-D1 — second real decision\n\n"
        "Decision: another.\n\n"
    )
    entries = parse_entries(text, DEFAULT_ENTRY_PATTERN).entries
    assert [e.header for e in entries] == [
        "### DEC-PM900-D1 — real decision",
        "### DEC-PM901-D1 — second real decision",
    ]
    # The quoted heading stayed inside the first entry's body (no split).
    assert "DEC-OLD-style" in entries[0].block


def test_parse_entries_ignores_non_id_section_heading() -> None:
    """H-2 (id-form default): a non-id H3 such as '### Notes' is not an entry
    boundary, so it cannot create a phantom entry.
    """
    text = (
        "# Log\n\n"
        "### DEC-PM1-D1 — real\n\nbody one\n\n"
        "### Notes\n\nthis is a section heading, not an entry\n\n"
        "### RISK-001 — real risk\n\nbody two\n\n"
    )
    entries = parse_entries(text, DEFAULT_ENTRY_PATTERN).entries
    assert [e.header for e in entries] == [
        "### DEC-PM1-D1 — real",
        "### RISK-001 — real risk",
    ]


# ---------------------------------------------------------------------------
# --apply : refuses non-rotatable
# ---------------------------------------------------------------------------


def test_apply_refuses_heartbeat(tmp_path: Path) -> None:
    root = _make_oversight(tmp_path)
    ps = root / "project-status.md"
    ps.write_text("# project-status.md\n\nfield: value\n", encoding="utf-8")
    result = _run("--apply", str(ps), "--oversight-root", str(root))
    assert result.returncode == 1
    assert "rotation_trigger: none" in result.stderr


# ---------------------------------------------------------------------------
# Unit-level: sizing + front-matter parsing
# ---------------------------------------------------------------------------


def test_measure_matches_wc_semantics() -> None:
    assert measure("a\nb\nc\n") == (3, 6)
    assert measure("a\nb\nc") == (2, 5)  # no trailing newline -> last line uncounted


def test_over_cap_either_axis() -> None:
    contract = FALLBACK_REGISTRY["tracking/decision-log.md"]
    assert over_cap(contract.cap_lines + 1, 0, contract) is True
    assert over_cap(0, int(contract.cap_kb * 1024) + 1, contract) is True
    assert over_cap(0, 0, contract) is False


def test_front_matter_parse_requires_caps() -> None:
    fm, _ = split_front_matter("---\nclass: register\n---\nbody\n")
    assert parse_contract_front_matter(fm) is None  # no caps -> not a contract
    fm2, _ = split_front_matter(
        "---\nclass: register\ncap_lines: 10\ncap_kb: 2\n---\nx\n"
    )
    c = parse_contract_front_matter(fm2)
    assert c is not None
    assert c.cap_lines == 10
    assert c.cap_kb == 2.0
