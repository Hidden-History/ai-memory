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

import pytest

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
MANUAL_ROTATION_FILES = _mod.MANUAL_ROTATION_FILES
append_to_shard = _mod.append_to_shard
Entry = _mod.Entry
ShardCollisionError = _mod.ShardCollisionError
AUTO_MEMORY_CONTRACT = _mod.AUTO_MEMORY_CONTRACT
run_fix_memory_md = _mod.run_fix_memory_md
run_fix = _mod.run_fix
_check_memory_md = _mod._check_memory_md
_entry_needs_relocation = _mod._entry_needs_relocation
_has_log_shape_violation = _mod._has_log_shape_violation
_sibling_name_for = _mod._sibling_name_for
SiblingCollisionError = _mod.SiblingCollisionError


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


def _synthetic_register_fm(
    archive: str = "tracking/sample-archive-{YYYY}.md",
    cap_lines: int = 100,
    cap_kb: float = 15,
) -> str:
    """Front-matter for a synthetic, *non-production* register file.

    The production registers (blockers-log / risk-register) refuse --apply and
    defer to TD-655 (MANUAL_ROTATION_FILES). The status-based register-rotation
    code stays dormant for TD-655; these synthetic-register tests keep it
    covered via a rel-path NOT in MANUAL_ROTATION_FILES.
    """
    return (
        "---\n"
        "class: register\n"
        "read_path: section-anchored\n"
        f"cap_lines: {cap_lines}\n"
        f"cap_kb: {cap_kb}\n"
        "rotation_trigger: on-close-over-cap\n"
        f"archive_target: {archive}\n"
        "---\n"
    )


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


def test_apply_prefix_sibling_root_no_crash(tmp_path: Path) -> None:
    """A file in a *prefix-sibling* dir of oversight-root (root '.../oversight',
    file '.../oversight-backup/...') must not crash the rel computation.

    The old ``str(file).startswith(str(root))`` containment test is True for a
    prefix-sibling, so ``relative_to`` raised an uncaught ValueError. The
    ``is_relative_to`` guard makes it fall back cleanly to ``file_path.name``.
    """
    root = _make_oversight(tmp_path)
    sibling = tmp_path / "oversight-backup" / "tracking"
    sibling.mkdir(parents=True)
    log = sibling / "decision-log.md"
    log.write_text(_decision_log(3), encoding="utf-8")

    result = _run("--apply", str(log), "--oversight-root", str(root))

    # No uncaught traceback from the rel computation.
    assert "Traceback" not in result.stderr, result.stderr
    assert "ValueError" not in result.stderr, result.stderr
    # Falls back to file_path.name and reaches the governed-file check cleanly.
    assert result.returncode == 1
    assert "not a governed file" in result.stderr


def _decision_log_seed(n_entries: int) -> str:
    """decision-log.md in its REAL seed shape: title + 'How to Use' +
    'Entry Format' (with the literal ``### DEC-[ID]:`` example) + '## Decisions'
    with newest-first entries. Mirrors templates/oversight/tracking/decision-log.md
    so the archive-end (oldest = tail) is verified against the format operators
    actually get.
    """
    head = (
        "# Decision Log\n\n"
        "**Last Updated**: 2026-06-16\n"
        "**Format**: Append-only — add new entries at the top, newest first\n\n"
        "---\n\n"
        "## How to Use\n\n"
        "- Quick decisions go here (1-3 lines per entry)\n\n"
        "## Entry Format\n\n"
        "### DEC-[ID]: [Decision Topic]\n"
        "- **Date**: [YYYY-MM-DD]\n"
        "- **Status**: [Active/Superseded]\n\n"
        "---\n\n"
        "## Decisions\n\n"
    )
    # Newest-first: DEC-PM{n} at the top, DEC-PM001 oldest at the bottom.
    blocks = "".join(
        f"### DEC-PM{i:03d}-D1: decision number {i}\n"
        f"- **Date**: 2026-06-{(i % 28) + 1:02d}\n"
        f"- **Decision**: did thing {i}.\n"
        f"- **Rationale**: because {i}.\n"
        f"- **Status**: Active\n\n"
        for i in range(n_entries, 0, -1)
    )
    return head + blocks


def test_apply_decision_log_seed_format(tmp_path: Path) -> None:
    """Verify --apply on a fixture matching the REAL decision-log seed: the
    OLDEST real decisions (tail) are archived, the NEWEST stay live, ids are
    conserved, and the live file lands within cap.
    """
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    before = _decision_log_seed(60)
    log.write_text(before, encoding="utf-8")
    pre_ids = set(re.findall(r"### (DEC-PM\d+-D1)", before))

    result = _run(
        "--apply", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = log.read_text(encoding="utf-8")
    lines, _ = measure(new_text)
    assert lines <= FALLBACK_REGISTRY["tracking/decision-log.md"].cap_lines

    shard = root / "tracking" / "archive" / "decision-log-ARCHIVE-2026-06.md"
    shard_text = shard.read_text(encoding="utf-8")

    # Archive end is correct: oldest (DEC-PM001) archived, newest (DEC-PM060) live.
    assert "DEC-PM001-D1" in shard_text
    assert "DEC-PM001-D1" not in new_text
    assert "DEC-PM060-D1" in new_text
    assert "DEC-PM060-D1" not in shard_text

    # The 'Entry Format' example heading stays in the live file (kept at head),
    # never archived, and the live pointer is present.
    assert "### DEC-[ID]: [Decision Topic]" in new_text
    assert POINTER_MARKER in new_text

    # Id conservation across live + shard for every real decision id.
    live_ids = set(re.findall(r"### (DEC-PM\d+-D1)", new_text))
    shard_ids = set(re.findall(r"### (DEC-PM\d+-D1)", shard_text))
    assert live_ids | shard_ids == pre_ids
    assert not (live_ids & shard_ids)  # no id both live and archived


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
    """Status-based register rotation (dormant for TD-655) on a *synthetic*
    register at a non-production rel-path. The production registers refuse
    --apply (see the MANUAL_ROTATION_FILES tests below); this keeps the
    register-rotation code that TD-655 will reuse under test.
    """
    root = _make_oversight(tmp_path)
    reg = root / "tracking" / "sample-register.md"
    # 10 newest OPEN, 50 oldest RESOLVED -> resolved rotate out, open stay live.
    reg.write_text(
        _synthetic_register_fm() + _blockers_log(60, active=10), encoding="utf-8"
    )

    result = _run(
        "--apply", str(reg), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = reg.read_text(encoding="utf-8")
    kept = parse_entries(new_text, DEFAULT_ENTRY_PATTERN).entries
    # M-1: banner reflects the OPEN count, with no stale "as of PM #X" suffix.
    open_kept = sum(1 for e in kept if not is_resolved(e))
    assert open_kept == 10
    assert f"**{open_kept} active**" in new_text
    assert "as of PM" not in new_text

    archive = root / "tracking" / "sample-archive-2026.md"
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
    """H-5: an OPEN entry that is the OLDEST must stay live; only RESOLVED
    entries are archived even though they are newer than it. Exercised on a
    synthetic register (production registers refuse --apply; TD-655).
    """
    root = _make_oversight(tmp_path)
    reg = root / "tracking" / "sample-register.md"
    head = "# Sample Register\n\n**1 active as of PM #9**\n\n## Active\n\n"
    blocks = []
    for i in range(40, 0, -1):  # newest-first: BUG-040 .. BUG-001 (oldest)
        status = "Open" if i == 1 else "Resolved"
        blocks.append(
            f"### BUG-{i:03d}: blocker {i}\n\n**Status**: {status}\n\nDetail {i}.\n\n"
        )
    reg.write_text(_synthetic_register_fm() + head + "".join(blocks), encoding="utf-8")

    result = _run(
        "--apply", str(reg), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = reg.read_text(encoding="utf-8")
    archive = root / "tracking" / "sample-archive-2026.md"
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


def test_append_to_shard_replay_same_id_and_body_skips(tmp_path: Path) -> None:
    """MED-1: same id AND identical body is a safe replay — skipped, not
    double-appended, no error."""
    shard = tmp_path / "tracking" / "archive" / "shard.md"
    entry = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\n\nOriginal body.\n\n",
    )
    first = append_to_shard(shard, [entry], "decision-log.md", DEFAULT_ENTRY_PATTERN)
    again = append_to_shard(shard, [entry], "decision-log.md", DEFAULT_ENTRY_PATTERN)
    assert first == 1
    assert again == 0
    assert shard.read_text(encoding="utf-8").count("### DEC-PM001-D1") == 1


def test_append_to_shard_same_id_different_body_refuses(tmp_path: Path) -> None:
    """MED-1: same id with a DIFFERENT body is a collision, not a replay. It
    must raise rather than silently drop, and leave the shard untouched."""
    shard = tmp_path / "tracking" / "archive" / "shard.md"
    original = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\n\nOriginal body.\n\n",
    )
    append_to_shard(shard, [original], "decision-log.md", DEFAULT_ENTRY_PATTERN)

    collider = Entry(
        header="### DEC-PM001-D1 — changed",
        block="### DEC-PM001-D1 — changed\n\nDIFFERENT body.\n\n",
    )
    with pytest.raises(ShardCollisionError) as exc:
        append_to_shard(shard, [collider], "decision-log.md", DEFAULT_ENTRY_PATTERN)
    assert "DEC-PM001-D1" in exc.value.ids
    # Non-destructive: the shard still holds only the original body.
    text = shard.read_text(encoding="utf-8")
    assert "Original body." in text
    assert "DIFFERENT body." not in text


def test_apply_collision_does_not_drop_live_entry(tmp_path: Path) -> None:
    """MED-1 end-to-end: when an entry being rotated out collides with a
    different-bodied shard entry of the same id, --apply must refuse (exit 1)
    and leave the live file completely untouched — no silent data loss."""
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    shard = root / "tracking" / "archive" / "decision-log-ARCHIVE-2026-06.md"

    # Pre-seed the shard with DEC-PM001-D1 carrying a DIFFERENT body than the
    # one the live log will try to rotate out (DEC-PM001-D1 is the oldest, so it
    # is in the moved set).
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text(
        "# Archive\n\n### DEC-PM001-D1 — decision number 1\n\n"
        "Decision: SOMETHING ELSE entirely.\nRationale: divergent.\n\n",
        encoding="utf-8",
    )

    live = _decision_log(80)
    log.write_text(live, encoding="utf-8")
    result = _run(
        "--apply", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 1
    assert "collision" in result.stderr.lower()
    assert "DEC-PM001-D1" in result.stderr
    # Live file is byte-for-byte unchanged (entry was NOT dropped).
    assert log.read_text(encoding="utf-8") == live


def test_append_to_shard_replay_crlf_vs_lf_skips(tmp_path: Path) -> None:
    """LOW-A: a moved entry differing from its same-id shard twin ONLY by
    CRLF<->LF line endings is an idempotent replay — skipped (returns 0), not a
    spurious collision on a mixed-EOL host."""
    shard = tmp_path / "tracking" / "archive" / "shard.md"
    lf_entry = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\n\nOriginal body line one.\nLine two.\n\n",
    )
    first = append_to_shard(shard, [lf_entry], "decision-log.md", DEFAULT_ENTRY_PATTERN)
    crlf_entry = Entry(
        header="### DEC-PM001-D1 — original",
        block=(
            "### DEC-PM001-D1 — original\r\n\r\n"
            "Original body line one.\r\nLine two.\r\n\r\n"
        ),
    )
    again = append_to_shard(
        shard, [crlf_entry], "decision-log.md", DEFAULT_ENTRY_PATTERN
    )
    assert first == 1
    assert again == 0  # EOL-only difference => idempotent replay, no raise
    assert shard.read_text(encoding="utf-8").count("### DEC-PM001-D1") == 1


def test_append_to_shard_crlf_non_eol_difference_still_collides(
    tmp_path: Path,
) -> None:
    """LOW-A false-negative GUARD: EOL normalization must NOT collapse a real
    body difference. A CRLF moved entry whose body differs in a NON-EOL way
    (changed word) from its same-id shard twin STILL raises ShardCollisionError —
    proving the fix did not re-introduce the MED-1 silent-loss class."""
    shard = tmp_path / "tracking" / "archive" / "shard.md"
    original = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\n\nOriginal body.\n\n",
    )
    append_to_shard(shard, [original], "decision-log.md", DEFAULT_ENTRY_PATTERN)

    crlf_changed = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\r\n\r\nDIFFERENT body.\r\n\r\n",
    )
    with pytest.raises(ShardCollisionError) as exc:
        append_to_shard(shard, [crlf_changed], "decision-log.md", DEFAULT_ENTRY_PATTERN)
    assert "DEC-PM001-D1" in exc.value.ids
    # Non-destructive: the shard still holds only the original body.
    text = shard.read_text(encoding="utf-8")
    assert "Original body." in text
    assert "DIFFERENT body." not in text


def test_append_to_shard_internal_whitespace_difference_still_collides(
    tmp_path: Path,
) -> None:
    """LOW-A false-negative GUARD (internal whitespace): ``_normalize_eol`` must
    normalize line endings ONLY — never collapse internal whitespace. Two
    same-id entries whose bodies differ ONLY by an internal single vs double
    space are a real id clash, so the second STILL raises ShardCollisionError.
    Makes the EOL-only guarantee load-bearing against a future stray
    ``.replace(" ", "")`` that would silently re-introduce the MED-1 loss class."""
    shard = tmp_path / "tracking" / "archive" / "shard.md"
    original = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\n\nfoo  bar\n\n",
    )
    append_to_shard(shard, [original], "decision-log.md", DEFAULT_ENTRY_PATTERN)

    collider = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\n\nfoo bar\n\n",
    )
    with pytest.raises(ShardCollisionError) as exc:
        append_to_shard(shard, [collider], "decision-log.md", DEFAULT_ENTRY_PATTERN)
    assert "DEC-PM001-D1" in exc.value.ids
    # Non-destructive: the shard still holds the original double-space body, not
    # the new single-space one.
    text = shard.read_text(encoding="utf-8")
    assert "foo  bar" in text
    assert "foo bar" not in text


def test_append_to_shard_replay_bare_cr_vs_lf_skips(tmp_path: Path) -> None:
    """LOW-A (bare CR): a moved entry differing from its same-id shard twin ONLY
    by classic-Mac bare-CR (``\\r``) vs LF line endings is an idempotent replay —
    skipped (returns 0), not a spurious collision. Exercises the second
    ``.replace("\\r", "\\n")`` in ``_normalize_eol``."""
    shard = tmp_path / "tracking" / "archive" / "shard.md"
    lf_entry = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\n\nOriginal body line one.\nLine two.\n\n",
    )
    first = append_to_shard(shard, [lf_entry], "decision-log.md", DEFAULT_ENTRY_PATTERN)
    cr_entry = Entry(
        header="### DEC-PM001-D1 — original",
        block=(
            "### DEC-PM001-D1 — original\r\r" "Original body line one.\rLine two.\r\r"
        ),
    )
    again = append_to_shard(shard, [cr_entry], "decision-log.md", DEFAULT_ENTRY_PATTERN)
    assert first == 1
    assert again == 0  # bare-CR-only difference => idempotent replay, no raise
    assert shard.read_text(encoding="utf-8").count("### DEC-PM001-D1") == 1


def test_append_to_shard_dedups_repeated_collision_ids(tmp_path: Path) -> None:
    """LOW-B: when one id collides multiple times in a single batch, the
    ShardCollisionError ids list is de-duplicated — the id appears exactly once."""
    shard = tmp_path / "tracking" / "archive" / "shard.md"
    original = Entry(
        header="### DEC-PM001-D1 — original",
        block="### DEC-PM001-D1 — original\n\nOriginal body.\n\n",
    )
    append_to_shard(shard, [original], "decision-log.md", DEFAULT_ENTRY_PATTERN)

    collider_a = Entry(
        header="### DEC-PM001-D1 — variant A",
        block="### DEC-PM001-D1 — variant A\n\nBody A.\n\n",
    )
    collider_b = Entry(
        header="### DEC-PM001-D1 — variant B",
        block="### DEC-PM001-D1 — variant B\n\nBody B.\n\n",
    )
    with pytest.raises(ShardCollisionError) as exc:
        append_to_shard(
            shard, [collider_a, collider_b], "decision-log.md", DEFAULT_ENTRY_PATTERN
        )
    assert exc.value.ids == ["DEC-PM001-D1"]
    assert exc.value.ids.count("DEC-PM001-D1") == 1


# ---------------------------------------------------------------------------
# --apply : table-row / mixed-format registers REFUSE (DEC-PM339-D7, TD-655)
# ---------------------------------------------------------------------------


def _multitable_swi(n_sessions: int) -> str:
    """SESSION_WORK_INDEX.md in its REAL seed shape: four distinct tables.

    A bare '^\\| ' match would shed rows from the wrong table, so --apply must
    refuse this file rather than rotate it.
    """
    sessions = "".join(
        f"| 2026-06-{i:02d} | TASK-{i:03d} | did thing {i} | ✅ |\n"
        for i in range(n_sessions, 0, -1)
    )
    return (
        "# Session Work Index\n\n## Current Sprint\n\n**Sprint**: S1\n\n"
        "## Active Task\n\n| Field | Value |\n|-------|-------|\n"
        "| ID | TASK-999 |\n| Status | In Progress |\n\n"
        "## Last 5 Sessions\n\n| Date | Task ID | Summary | Status |\n"
        "|------|---------|---------|--------|\n" + sessions + "\n"
        "## Active Blockers\n\n| ID | Description | Status |\n|----|----|----|\n"
        "| BLK-001 | a blocker | Awaiting X |\n\n"
        "## High Priority Risks\n\n| ID | Risk | Mitigation |\n|----|----|----|\n"
        "| RISK-001 | a risk | do a thing |\n"
    )


def _seed_blockers_log(n_resolved: int) -> str:
    """blockers-log.md in its REAL seed shape: Active table + BLK Detail H3 +
    Resolved table."""
    resolved_rows = "".join(
        f"| BLK-{i:03d} | blocker {i} | fixed it | 2026-06-{i:02d} | learned {i} |\n"
        for i in range(n_resolved, 0, -1)
    )
    return (
        "# Blockers Log\n\n**Last Updated**: 2026-06-16\n\n"
        "## Active Blockers\n\n| ID | Blocker | Severity | Status |\n"
        "|----|---------|----------|--------|\n"
        "| BLK-900 | active one | High | Active |\n\n"
        "## Blocker Details\n\n"
        "### BLK-900: active one\n\n**Status**: Active\n\nDetail.\n\n"
        "## Resolved Blockers\n\n| ID | Blocker | Resolution | Date | Learning |\n"
        "|----|---------|------------|------|----------|\n" + resolved_rows
    )


def _seed_risk_register(n_rows: int) -> str:
    """risk-register.md in its REAL seed shape: rows under '### Critical/High/...'
    severity headers."""
    rows = "".join(
        f"| RISK-{i:03d} | risk {i} | impact | Med | mitigate {i} | who | Open |\n"
        for i in range(n_rows, 0, -1)
    )
    return (
        "# Risk Register\n\n**Last Updated**: 2026-06-16\n\n"
        "## Active Risks\n\n### Critical\n\n"
        "| ID | Risk | Impact | Likelihood | Mitigation | Owner | Status |\n"
        "|----|------|--------|------------|------------|-------|--------|\n" + rows
    )


def test_apply_refuses_blockers_log_non_destructive(tmp_path: Path) -> None:
    """--apply on the production blockers-log refuses without mutating the file
    (DEC-PM339-D7 Option A; table-under-status, deferred to TD-655)."""
    root = _make_oversight(tmp_path)
    blk = root / "tracking" / "blockers-log.md"
    before = _seed_blockers_log(60)
    blk.write_text(before, encoding="utf-8")

    result = _run(
        "--apply", str(blk), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 1
    assert "REFUSED" in result.stderr
    assert "TD-655" in result.stderr
    # Non-destructive: file unchanged and no archive shard created.
    assert blk.read_text(encoding="utf-8") == before
    assert not (root / "tracking" / "blockers-archive-2026.md").exists()


def test_apply_refuses_risk_register_non_destructive(tmp_path: Path) -> None:
    """--apply on the production risk-register refuses without mutating the file
    (rows under severity headers; deferred to TD-655)."""
    root = _make_oversight(tmp_path)
    rsk = root / "tracking" / "risk-register.md"
    before = _seed_risk_register(80)
    rsk.write_text(before, encoding="utf-8")

    result = _run(
        "--apply", str(rsk), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 1
    assert "REFUSED" in result.stderr
    assert "TD-655" in result.stderr
    assert rsk.read_text(encoding="utf-8") == before
    assert not (root / "tracking" / "risk-archive-2026.md").exists()


def test_apply_refuses_session_work_index_non_destructive(tmp_path: Path) -> None:
    """--apply on the multi-table SESSION_WORK_INDEX refuses (a bare '^\\| ' match
    would shed rows from the wrong table); deferred to TD-655."""
    root = _make_oversight(tmp_path)
    swi = root / "SESSION_WORK_INDEX.md"
    before = _multitable_swi(40)
    swi.write_text(before, encoding="utf-8")

    result = _run(
        "--apply", str(swi), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 1
    assert "REFUSED" in result.stderr
    assert swi.read_text(encoding="utf-8") == before
    # session-index/INDEX.md must not have been written as a side effect.
    assert not (root / "session-index" / "INDEX.md").exists()


def test_apply_refuses_session_index_non_destructive(tmp_path: Path) -> None:
    """--apply on session-index/INDEX.md refuses (mixed month-H3 + tables);
    deferred to TD-655."""
    root = _make_oversight(tmp_path)
    idx = root / "session-index" / "INDEX.md"
    before = (
        "# Session Index\n\n## Current Year: 2026\n\n### June 2026\n\n"
        "| Week | Dates | Sessions | Key Work |\n|------|-------|----------|------|\n"
        "| Week 1 | Jun 01 - Jun 07 | 3 | did stuff |\n\n"
        "## Archive\n\n| Quarter | Sessions | Location |\n|---|---|---|\n"
        "| 2026-Q1 | 12 | archive/2026-Q1.md |\n"
    )
    idx.write_text(before, encoding="utf-8")

    result = _run(
        "--apply", str(idx), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 1
    assert "REFUSED" in result.stderr
    assert idx.read_text(encoding="utf-8") == before


def test_all_manual_files_refuse_apply(tmp_path: Path) -> None:
    """Every rel-path in MANUAL_ROTATION_FILES refuses --apply non-destructively
    (guards against a future registry edit silently re-enabling one)."""
    assert len(MANUAL_ROTATION_FILES) == 4
    for expected in (
        "tracking/blockers-log.md",
        "tracking/risk-register.md",
        "SESSION_WORK_INDEX.md",
        "session-index/INDEX.md",
    ):
        assert expected in MANUAL_ROTATION_FILES
    for rel in MANUAL_ROTATION_FILES:
        root = _make_oversight(tmp_path / rel.replace("/", "_"))
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        before = f"# {rel}\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
        target.write_text(before, encoding="utf-8")
        result = _run("--apply", str(target), "--oversight-root", str(root))
        assert result.returncode == 1, rel
        assert "REFUSED" in result.stderr, rel
        assert target.read_text(encoding="utf-8") == before, rel


def test_check_still_enforces_cap_on_manual_files(tmp_path: Path) -> None:
    """--check stays UNIVERSAL: a manual-rotation register over cap still blocks
    closeout, with a manual (TD-655) remedy that does NOT loop back to --apply."""
    root = _make_oversight(tmp_path)
    # blockers-log cap is 100 lines; 60 resolved rows + details blow past it.
    blk = root / "tracking" / "blockers-log.md"
    blk.write_text(
        _seed_blockers_log(120) + "\n".join(f"x {i}" for i in range(60)) + "\n",
        encoding="utf-8",
    )

    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 1
    assert "SYSTEM FAILURE" in result.stderr
    assert "blockers-log.md" in result.stderr
    assert "TD-655" in result.stderr
    assert "by hand" in result.stderr
    assert "--apply" not in result.stderr  # do not loop the operator back


# ---------------------------------------------------------------------------
# --apply / --check : exhausted (deadlock) path (H-4)
# ---------------------------------------------------------------------------


def _all_open_register(n: int) -> str:
    head = f"# Sample Register\n\n**{n} active as of PM #9**\n\n## Active\n\n"
    blocks = "".join(
        f"### BUG-{i:03d}: blocker {i}\n\n**Status**: Open\n\nDetail line {i}.\n\n"
        for i in range(n, 0, -1)
    )
    return head + blocks


def _decision_log_huge_preamble() -> str:
    """A decision-log whose preamble alone exceeds the 150-line cap: even the
    maximal rotation cannot bring it under cap (exhausted)."""
    head = (
        "# Decision Log\n\n"
        + "".join(f"preamble narrative line {i}\n" for i in range(160))
        + "\n## Decisions\n\n"
    )
    entries = (
        "### DEC-PM002-D1 — two\n\nbody two\n\n"
        "### DEC-PM001-D1 — one\n\nbody one\n\n"
    )
    return head + entries


def test_apply_exhausted_exits_nonzero(tmp_path: Path) -> None:
    """H-4: when every live entry is OPEN and the file is over cap, --apply
    cannot rotate it under cap — it must exit non-zero with a hand-trim remedy
    (never exit 0, which would deadlock the gate into re-running --apply).
    Exercised on a synthetic register (production registers refuse --apply).
    """
    root = _make_oversight(tmp_path)
    reg = root / "tracking" / "sample-register.md"
    reg.write_text(_synthetic_register_fm() + _all_open_register(80), encoding="utf-8")

    result = _run(
        "--apply", str(reg), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 1
    assert "exhausted" in result.stderr.lower()


def test_check_remedy_handtrim_when_exhausted(tmp_path: Path) -> None:
    """H-4: --check's remedy for an exhausted file (here the supported
    append-only decision-log whose preamble alone exceeds cap) points to a
    hand-trim, NOT back to --apply.
    """
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    log.write_text(_decision_log_huge_preamble(), encoding="utf-8")

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


# ---------------------------------------------------------------------------
# Friction #2: task-tracker cap raised to 60 lines / 4.5 KB
# ---------------------------------------------------------------------------


def test_friction2_task_tracker_cap() -> None:
    """task-tracker fallback-registry cap must be 60 lines / 4.5 KB."""
    contract = FALLBACK_REGISTRY["tracking/task-tracker.md"]
    assert contract.cap_lines == 60
    assert contract.cap_kb == 4.5


def test_check_task_tracker_passes_at_new_cap(tmp_path: Path) -> None:
    """A task-tracker file of 55 lines (old 40-line cap would have failed) passes."""
    root = _make_oversight(tmp_path)
    # 55 content lines: old cap=40 would have failed, new cap=60 should pass.
    body = "\n".join(f"task-line {i}" for i in range(55)) + "\n"
    (root / "tracking" / "task-tracker.md").write_text(body, encoding="utf-8")
    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


# ---------------------------------------------------------------------------
# Friction #3: section scaffold preserved after --apply (golden-reference shape)
# ---------------------------------------------------------------------------

_THREE_SECTION_HEAD = (
    "# Decision Log\n\n"
    "**Last Updated**: 2026-06-18\n\n"
    "---\n\n"
    "## How to Use\n\n"
    "- Quick decisions go here.\n\n"
    "## Entry Format\n\n"
    "```md\n"
    "### DEC-[ID]: [Decision Topic]\n"
    "- **Status**: [Active/Superseded]\n"
    "```\n\n"
    "---\n\n"
    "## Decisions\n\n"
)


def _three_section_log(n_entries: int) -> str:
    """decision-log with the real three-section preamble (fenced entry example)."""
    blocks = "".join(
        f"### DEC-PM{i:03d}-D1: decision {i}\n"
        f"- **Date**: 2026-06-{(i % 28) + 1:02d}\n"
        f"- **Status**: Active\n\n"
        for i in range(n_entries, 0, -1)
    )
    return _THREE_SECTION_HEAD + blocks


def test_apply_preserves_section_scaffold(tmp_path: Path) -> None:
    """Golden-reference shape: after --apply on a three-section decision-log,
    all ## section headers survive and the pointer sits directly under
    ## Decisions with kept entries beneath it.
    """
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    log.write_text(_three_section_log(60), encoding="utf-8")

    result = _run(
        "--apply", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = log.read_text(encoding="utf-8")

    # All three ## section headers must survive.
    assert "## How to Use" in new_text, "## How to Use header stripped"
    assert "## Entry Format" in new_text, "## Entry Format header stripped"
    assert "## Decisions" in new_text, "## Decisions header stripped"

    # Pointer must be under ## Decisions (golden reference: pointer sits
    # directly under ## Decisions with kept entries beneath it).
    decisions_pos = new_text.index("## Decisions")
    pointer_pos = new_text.index(POINTER_MARKER)
    newest_pos = new_text.index("DEC-PM060-D1")

    assert pointer_pos > decisions_pos, "pointer must come after ## Decisions"
    assert newest_pos > pointer_pos, "kept entries must follow pointer"


def test_apply_unfenced_log_scaffold_preserved(tmp_path: Path) -> None:
    """Bare --apply on an over-cap decision-log with an unfenced entry-format
    example must preserve all three ## section headers.

    The scaffold-strip bug: an unfenced ### DEC-[ID]: example was mis-parsed as
    Entry 0, causing ## Decisions to appear inside the kept block (mangled preamble,
    pointer between ## Entry Format and ## Decisions). _fence_for_apply now fences
    the example before parse_entries so the preamble is intact.

    Non-vacuous assertions (item 2b): these fail WITHOUT the fence fix even on a
    newest-first seed where ## Decisions stays 'visible' but in the wrong position.
    """
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    # _decision_log_seed has an UNFENCED entry-format example (the S102 trigger).
    log.write_text(_decision_log_seed(80), encoding="utf-8")

    result = _run(
        "--apply", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = log.read_text(encoding="utf-8")
    assert "## How to Use" in new_text, "## How to Use stripped by --apply"
    assert "## Entry Format" in new_text, "## Entry Format stripped by --apply"
    assert "## Decisions" in new_text, "## Decisions stripped by --apply"

    # Non-vacuous structural assertions (fail without _fence_for_apply):
    # 1. Entry-format example must be fenced in the output.
    ef_pos = new_text.index("## Entry Format")
    decisions_pos = new_text.index("## Decisions")
    ef_body = new_text[ef_pos:decisions_pos]
    assert "```" in ef_body, "entry-format example must be fenced after --apply"
    # 2. Pointer must NOT sit between ## Entry Format and ## Decisions.
    pointer_pos = new_text.index(POINTER_MARKER)
    assert not (
        ef_pos < pointer_pos < decisions_pos
    ), "pointer sits between ## Entry Format and ## Decisions — preamble mangled"

    # ID conservation across live + shard.
    before_ids = set(re.findall(r"DEC-PM\d+-D1", _decision_log_seed(80)))
    shard_files = list((root / "tracking" / "archive").glob("decision-log-*.md"))
    assert shard_files, "Expected a shard file after --apply"
    after_text = new_text + shard_files[0].read_text(encoding="utf-8")
    after_ids = set(re.findall(r"DEC-PM\d+-D1", after_text))
    assert before_ids == after_ids, f"ID loss: {before_ids - after_ids}"


# ---------------------------------------------------------------------------
# auto-memory-index class: --check WARN semantics
# ---------------------------------------------------------------------------


def _production_memory_md(lines: int = 240) -> str:
    """Return a production-size MEMORY.md exceeding the 200-line cap.

    The first ~120 lines hold a dense session-notes section (log-shape violations),
    the remaining lines simulate feedback pointer entries (already pointer format).
    """
    # Dense session notes section (log-shape violations).
    dense_section = "## Active Project: Build Phase\n\n"
    for i in range(1, 50):
        # Each block is 3+ lines — clearly over _MEMORY_LOG_SHAPE_MAX_LINES.
        dense_section += (
            f"**Session {i:03d} notes**: completed tasks {i}-{i+2}.\n"
            f"Key decisions: used option A for integration path {i}.\n"
            f"Next: verify component {i} passes all acceptance tests.\n"
            f"\n"
        )

    # Feedback section with pointer-format entries (conformant — no relocation).
    feedback_section = "## Feedback\n\n"
    for i in range(1, 40):
        feedback_section += (
            f"- [feedback-rule-{i:03d}](feedback_rule_{i:03d}.md) "
            f"— always follow rule {i}\n"
        )

    # Next steps (short, conformant).
    next_section = "\n## Next Steps\n\n- Reinstate after review\n"

    full_text = (
        "# AI Memory — Session Memory\n\n"
        + dense_section
        + feedback_section
        + next_section
    )
    # Pad to exactly `lines` lines if under; return as-is if already long enough.
    current = full_text.count("\n")
    if current < lines:
        full_text += "\n" * (lines - current)
    return full_text


def test_check_memory_md_over_cap_is_warn_not_fail(tmp_path: Path, monkeypatch) -> None:
    """--check must exit 0 (PASS gate) even when MEMORY.md is over cap; the
    over-cap condition is surfaced as a WARN line on stderr, not a gate failure.
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    md.write_text(_production_memory_md(240), encoding="utf-8")

    root = _make_oversight(tmp_path)
    monkeypatch.setenv("autoMemoryDirectory", str(memory_dir))

    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 0, f"--check must exit 0; stderr: {result.stderr}"
    assert "WARN" in result.stderr
    assert "MEMORY.md" in result.stderr


def test_check_memory_md_log_shape_warn(tmp_path: Path, monkeypatch) -> None:
    """A MEMORY.md with multi-line log-style entries triggers a log-shape WARN
    even when the file is under the line cap.
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    # Under 200 lines but has a multi-line paragraph block
    dense_entry = (
        "Dense session entry that is well over 200 characters total "
        "and also spans multiple non-blank lines in the file.\n"
        "Second line of the same block — this exceeds the 2-line index limit.\n"
        "Third line — clearly violates the index-not-log constraint.\n"
    )
    md.write_text(f"# Index\n\n{dense_entry}\n", encoding="utf-8")

    root = _make_oversight(tmp_path)
    monkeypatch.setenv("autoMemoryDirectory", str(memory_dir))

    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 0
    assert "WARN" in result.stderr
    assert "index-not-log" in result.stderr


def test_check_memory_md_hash3_dense_entry_warn(tmp_path: Path, monkeypatch) -> None:
    """SHOULD #3: a ### Topic + dense-body block must trigger a log-shape WARN.

    The dominant MEMORY.md shape has ### Topic headers with dense bodies; previously
    the section_header_re skipped any ### -led block regardless of body size.
    Only a lone ### header line (no body) should be treated as structural.
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    # Under cap (< 200 lines) but has a ### Topic + dense body (log-shape violation).
    md.write_text(
        "# Index\n\n"
        "## Active Project\n\n"
        "### Session notes\n"
        "Completed Phase 1 tasks.\n"
        "Key decision: use option A.\n"
        "Next: verify integration passes.\n"
        "\n",
        encoding="utf-8",
    )

    root = _make_oversight(tmp_path)
    monkeypatch.setenv("autoMemoryDirectory", str(memory_dir))

    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 0, "--check must exit 0 (WARN not gate failure)"
    assert "WARN" in result.stderr, "Expected WARN for ### -led dense entry"


def test_check_memory_md_conformant_no_warn(tmp_path: Path, monkeypatch) -> None:
    """A conformant MEMORY.md (under cap, all pointer lines) produces no WARN."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    # 10-line file, all one-line pointers
    pointers = "".join(
        f"- [Topic {i}](topic_{i}.md) — short hook for topic {i}\n" for i in range(10)
    )
    md.write_text(f"# Index\n\n## Feedback\n\n{pointers}", encoding="utf-8")

    root = _make_oversight(tmp_path)
    monkeypatch.setenv("autoMemoryDirectory", str(memory_dir))

    result = _run("--check", "--oversight-root", str(root))
    assert result.returncode == 0
    assert "WARN" not in result.stderr


def test_entry_needs_relocation_pointer_skipped() -> None:
    """A single-line pointer-format block must NOT be marked for relocation."""
    pointer = "- [Title](feedback_something.md) — short hook\n"
    assert _entry_needs_relocation(pointer) is False


def test_entry_needs_relocation_dense_block() -> None:
    """A multi-line dense block IS marked for relocation."""
    dense = (
        "Dense session note spanning many lines.\n"
        "Second line here.\n"
        "Third line makes it clearly over the limit.\n"
    )
    assert _entry_needs_relocation(dense) is True


# ---------------------------------------------------------------------------
# --fix-memory-md: lossless relocation with production-size fixture
# ---------------------------------------------------------------------------


def test_fix_memory_md_reduces_to_under_cap(tmp_path: Path) -> None:
    """--fix-memory-md on a 240-line MEMORY.md must bring it under the 200-line cap."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    md.write_text(_production_memory_md(240), encoding="utf-8")
    from datetime import datetime

    now = datetime(2026, 6, 18)
    rc = run_fix_memory_md(md, now)
    assert rc == 0

    new_lines, new_bytes = measure(md.read_text(encoding="utf-8"))
    assert new_lines <= AUTO_MEMORY_CONTRACT.cap_lines or new_bytes <= int(
        AUTO_MEMORY_CONTRACT.cap_kb * 1024
    ), f"still over cap: {new_lines} lines / {new_bytes} bytes"


def test_fix_memory_md_conservation(tmp_path: Path) -> None:
    """Every content line present before --fix-memory-md is present in the
    union of MEMORY.md + siblings after — zero lines lost.
    """
    import importlib.util as _ilu

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    original_text = _production_memory_md(240)
    md.write_text(original_text, encoding="utf-8")

    # Load conservation module directly to build before-set.
    _cpath = _SCRIPT_PATH.parent / "conservation.py"
    _cs = _ilu.spec_from_file_location("conservation_test", _cpath)
    _cm = _ilu.module_from_spec(_cs)
    _cs.loader.exec_module(_cm)

    before_set = _cm.build_content_set(list(memory_dir.glob("*.md")))

    from datetime import datetime

    rc = run_fix_memory_md(md, datetime(2026, 6, 18))
    assert rc == 0

    after_set = _cm.build_content_set(list(memory_dir.glob("*.md")))
    _cm.assert_no_content_loss(before_set, after_set)


def test_fix_memory_md_idempotent(tmp_path: Path) -> None:
    """Running --fix-memory-md a second time on an already-fixed MEMORY.md
    must be a no-op: same file content, no extra siblings created.
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    md.write_text(_production_memory_md(240), encoding="utf-8")

    from datetime import datetime

    now1 = datetime(2026, 6, 18, 10, 0, 0)
    now2 = datetime(2026, 6, 18, 10, 0, 1)

    rc1 = run_fix_memory_md(md, now1)
    assert rc1 == 0

    text_after_first = md.read_text(encoding="utf-8")
    siblings_after_first = set(memory_dir.glob("*.md")) - {md}

    rc2 = run_fix_memory_md(md, now2)
    assert rc2 == 0

    text_after_second = md.read_text(encoding="utf-8")
    siblings_after_second = set(memory_dir.glob("*.md")) - {md}

    # No new siblings on second run (ignoring .bak files).
    md_siblings_second = {p for p in siblings_after_second if p.suffix == ".md"}
    md_siblings_first = {p for p in siblings_after_first if p.suffix == ".md"}
    assert (
        md_siblings_second == md_siblings_first
    ), "Second run created unexpected new sibling files"
    # MEMORY.md content unchanged.
    assert text_after_second == text_after_first


def test_fix_memory_md_sibling_collision_refused(tmp_path: Path) -> None:
    """When a target sibling already exists with different content,
    --fix-memory-md must refuse and leave MEMORY.md unmodified (MUST #2 / BP-038).
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    # Must be over the 200-line cap to trigger relocation.
    md.write_text(_production_memory_md(240), encoding="utf-8")

    # Pick the first dense block from _production_memory_md to pre-create the sibling.
    entry_001 = (
        "**Session 001 notes**: completed tasks 1-3.\n"
        "Key decisions: used option A for integration path 1.\n"
        "Next: verify component 1 passes all acceptance tests.\n"
    )
    sibling_name = _sibling_name_for("## Active Project: Build Phase", entry_001)
    sibling = memory_dir / sibling_name
    prior_content = "Totally different content that conflicts.\n"
    sibling.write_text(prior_content, encoding="utf-8")

    original_md = md.read_text(encoding="utf-8")

    from datetime import datetime

    rc = run_fix_memory_md(md, datetime(2026, 6, 18))
    assert rc != 0, "Expected non-zero rc on sibling collision"
    assert (
        md.read_text(encoding="utf-8") == original_md
    ), "MEMORY.md must be unchanged on collision"
    assert (
        sibling.read_text(encoding="utf-8") == prior_content
    ), "Sibling must be unchanged"


# ---------------------------------------------------------------------------
# --fix: oversight files (decision log via --apply delegation)
# ---------------------------------------------------------------------------


def test_fix_decision_log_over_cap(tmp_path: Path) -> None:
    """--fix on an over-cap decision log must bring it within cap and pass
    a subsequent --check.
    """
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    # 80 entries → well over the 150-line cap for decision-log.
    log.write_text(_decision_log_seed(80), encoding="utf-8")

    result = _run(
        "--fix", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, f"--fix failed: {result.stderr}"
    assert "conservation" in result.stdout

    # After fix, --check must pass.
    check = _run("--check", "--oversight-root", str(root))
    assert check.returncode == 0, f"--check failed after --fix: {check.stderr}"


def test_fix_already_within_cap_is_noop(tmp_path: Path) -> None:
    """--fix on a within-cap file must exit 0 without touching the file."""
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    small = _decision_log_seed(5)
    log.write_text(small, encoding="utf-8")

    result = _run(
        "--fix", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr
    assert "already within cap" in result.stdout
    # File unchanged
    assert log.read_text(encoding="utf-8") == small


def test_fix_creates_backup(tmp_path: Path) -> None:
    """--fix must create a timestamped .bak backup before writing."""
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    log.write_text(_decision_log_seed(80), encoding="utf-8")

    result = _run(
        "--fix", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    bak_files = list((root / "tracking").glob("decision-log.md.*.bak"))
    assert len(bak_files) >= 1, "No backup file created by --fix"


def test_apply_creates_backup(tmp_path: Path) -> None:
    """--apply must create a timestamped .bak backup before rewriting (Fix #5)."""
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    log.write_text(_decision_log_seed(80), encoding="utf-8")

    result = _run(
        "--apply", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    bak_files = list((root / "tracking").glob("decision-log.md.*.bak"))
    assert len(bak_files) >= 1, "No backup file created by --apply"


def test_fix_task_tracker_over_cap_routes_to_archive(tmp_path: Path) -> None:
    """--fix on an over-cap non-rotatable register (task-tracker.md, rotatable=False)
    must route to archive-whole-verbatim rather than refusing (Fix #7).
    """
    root = _make_oversight(tmp_path)
    tracker = root / "tracking" / "task-tracker.md"
    # 80 lines > 60-line cap; plain text (no front-matter — relies on FALLBACK_REGISTRY)
    lines = "\n".join(
        f"TASK-{i:03d}: task description number {i}" for i in range(1, 81)
    )
    tracker.write_text(lines + "\n", encoding="utf-8")

    result = _run(
        "--fix", str(tracker), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = tracker.read_text(encoding="utf-8")
    assert (
        POINTER_MARKER in new_text
    ), "--fix on task-tracker must write the pointer marker"

    archive_files = list(
        (root / "tracking" / "archive").glob("task-tracker-ARCHIVE-*.md")
    )
    assert (
        len(archive_files) == 1
    ), "Expected exactly one archive shard for task-tracker"


def test_fix_decision_log_unfenced_scaffold_preserved(tmp_path: Path) -> None:
    """--fix on a decision-log with an unfenced entry-format example must preserve
    all three ## section headers in the live file after rotation.

    The scaffold-strip bug: the unfenced ``### DEC-[ID]:`` in ``## Entry Format``
    was treated as an entry boundary so ``## Decisions`` rode inside Entry 0's
    block and was stripped when that block was archived.  _ensure_conformance now
    fences the example first so parse_entries ignores it.

    Genuine regression guard (item 2b): a simple substring check is vacuous on
    newest-first seeds because ``## Decisions`` rides inside the kept Entry 0 block
    regardless of the fix. The extra assertions below fail WITHOUT the fence fix.
    """
    root = _make_oversight(tmp_path)
    log = root / "tracking" / "decision-log.md"
    log.write_text(_decision_log_seed(80), encoding="utf-8")

    result = _run(
        "--fix", str(log), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = log.read_text(encoding="utf-8")
    assert "## How to Use" in new_text, "## How to Use stripped by --fix"
    assert "## Entry Format" in new_text, "## Entry Format stripped by --fix"
    assert "## Decisions" in new_text, "## Decisions stripped by --fix"

    # Non-vacuous structural assertions (fail without the fence fix):
    # 1. The entry-format example must be fenced after --fix.
    ef_pos = new_text.index("## Entry Format")
    decisions_pos = new_text.index("## Decisions")
    ef_body = new_text[ef_pos:decisions_pos]
    assert "```" in ef_body, "entry-format example must be fenced by --fix"
    # 2. Pointer must NOT sit between ## Entry Format and ## Decisions — without
    #    the fix the pointer lands between them (example rendered as Entry 0).
    pointer_pos = new_text.index(POINTER_MARKER)
    assert not (
        ef_pos < pointer_pos < decisions_pos
    ), "pointer sits between ## Entry Format and ## Decisions — preamble not rebuilt"


def test_fix_section_cx1_refuse_on_existing_sibling(tmp_path: Path) -> None:
    """CX-1 regression: a block whose target sibling exists with different content
    must REFUSE (not silently treat the block as already relocated via substring match).

    With the old substring check: block embedded as substring of sibling was silently
    treated as 'already relocated' — block dropped from MEMORY.md without appearing
    as a standalone entry in the sibling. The fix: exact paragraph equality check +
    refuse on collision (MUST #2 / BP-038).
    """
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"

    cx1_entry = (
        "**Session 001 notes**: completed tasks 1-3.\n"
        "Key decisions: used option A for integration path 1.\n"
        "Next: verify component 1 passes all acceptance tests.\n"
    )
    # Must be over the 200-line cap to trigger run_fix_memory_md's relocation pass.
    md.write_text(_production_memory_md(240), encoding="utf-8")

    sibling_name = _sibling_name_for("## Active Project: Build Phase", cx1_entry)
    sibling = memory_dir / sibling_name
    sibling.write_text(
        "Embedded substring: **Session 001 notes**: completed tasks 1-3. more text.\n"
        "Different paragraph with unrelated content.\n",
        encoding="utf-8",
    )

    original_md = md.read_text(encoding="utf-8")
    original_sib = sibling.read_text(encoding="utf-8")

    from datetime import datetime

    rc = run_fix_memory_md(md, datetime(2026, 6, 18))
    assert rc != 0, "Expected non-zero rc on sibling collision (CX-1)"
    assert md.read_text(encoding="utf-8") == original_md, "MEMORY.md must be unchanged"
    assert (
        sibling.read_text(encoding="utf-8") == original_sib
    ), "Sibling must be unchanged"


# ---------------------------------------------------------------------------
# --fix-memory-md: log-shape trigger (under cap but log-shaped)
# ---------------------------------------------------------------------------


def test_fix_memory_md_log_shape_under_cap(tmp_path: Path) -> None:
    """--fix-memory-md on an under-cap but log-shaped MEMORY.md must relocate
    the log-shaped entries and produce a conformant index (BP-038 MAJOR-2).
    """
    from datetime import datetime

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    md = memory_dir / "MEMORY.md"
    # Under 200 lines but has a multi-line log-shape block.
    log_block = (
        "**Session 001 notes**: completed tasks 1-3.\n"
        "Key decisions: used option A for integration path 1.\n"
        "Next: verify component 1 passes all acceptance tests.\n"
    )
    text = (
        "# AI Memory\n\n"
        "## Active Project\n\n" + log_block + "\n"
        "## Feedback\n\n"
        "- [rule-001](feedback_rule_001.md) — short pointer hook\n"
    )
    md.write_text(text, encoding="utf-8")
    # Confirm fixture is under cap but has a log-shape violation.
    assert measure(text)[0] < AUTO_MEMORY_CONTRACT.cap_lines
    assert _has_log_shape_violation(text)

    rc = run_fix_memory_md(md, datetime(2026, 6, 18))
    assert rc == 0

    new_text = md.read_text(encoding="utf-8")
    # Log-shape block must have been relocated out of MEMORY.md.
    assert log_block.strip() not in new_text
    # A sibling must contain the relocated block.
    siblings = [p for p in memory_dir.glob("*.md") if p != md and p.suffix == ".md"]
    assert any(
        log_block.strip() in p.read_text(encoding="utf-8") for p in siblings
    ), "log-shape block must appear in a sibling file after relocation"

    # Idempotent: second run is a no-op (conformant → no change).
    rc2 = run_fix_memory_md(md, datetime(2026, 6, 18, 10, 0, 1))
    assert rc2 == 0
    assert md.read_text(encoding="utf-8") == new_text


# ---------------------------------------------------------------------------
# --fix: heartbeat and live-index branches
# ---------------------------------------------------------------------------


def test_fix_heartbeat_refreshes_front_matter(tmp_path: Path) -> None:
    """--fix on an over-cap heartbeat (project-status.md) refreshes the
    template front-matter and brings the file under cap when the body fits
    within the template FM budget.
    """
    root = _make_oversight(tmp_path)
    ps = root / "project-status.md"
    # Bloated front-matter (~25 lines) + 40-line body → over the 60-line cap.
    # Template FM is ~12 lines; 12 + 40 = 52 lines, under cap after refresh.
    bloated_fm = (
        "---\n"
        + "".join(f"# verbose-padding-{i}: filler\n" for i in range(20))
        + "cap_lines: 60\ncap_kb: 6\nclass: heartbeat\nrotation_trigger: none\n---\n"
    )
    body = "# project-status.md\n\n" + "".join(f"field_{i}: value\n" for i in range(40))
    ps.write_text(bloated_fm + body, encoding="utf-8")

    before_lines, _ = measure(ps.read_text(encoding="utf-8"))
    assert before_lines > 60  # confirm over cap

    result = _run(
        "--fix", str(ps), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    after_lines, _ = measure(ps.read_text(encoding="utf-8"))
    assert after_lines <= 60, f"heartbeat still over cap after fix: {after_lines} lines"
    # Body content preserved.
    assert "field_0: value" in ps.read_text(encoding="utf-8")


def test_fix_live_index_archives_whole(tmp_path: Path) -> None:
    """--fix on an over-cap live-index (SESSION_WORK_INDEX.md) archives the whole
    file verbatim and rewrites a lean index with a pointer.
    """
    root = _make_oversight(tmp_path)
    swi = root / "SESSION_WORK_INDEX.md"
    # 120 lines > 80-line cap for SESSION_WORK_INDEX.md.
    body = "".join(
        f"| session-{i:03d} | task-{i:03d} | did thing {i} | done |\n"
        for i in range(120)
    )
    swi.write_text(body, encoding="utf-8")

    result = _run(
        "--fix", str(swi), "--oversight-root", str(root), "--period", "2026-06"
    )
    assert result.returncode == 0, result.stderr

    new_text = swi.read_text(encoding="utf-8")
    assert POINTER_MARKER in new_text, "--fix must write the pointer marker"

    archive_files = list((root / "archive").glob("SESSION_WORK_INDEX-ARCHIVE-*.md"))
    assert (
        len(archive_files) == 1
    ), f"Expected 1 archive shard, found {len(archive_files)}"
    assert "session-001" in archive_files[0].read_text(encoding="utf-8")
