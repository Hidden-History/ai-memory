"""Tests for lore_hygiene.py (BP-165 B.4 — subprocess + tmp_path seam).

Covers the architecture spec's required scenarios:
  T1 — --dry-run (DEFAULT) mutates nothing (sha256 unchanged)
  T2 — over-cap file → plan proposes compaction
  T3 — --apply brings the file ≤ cap
  T4 — idempotency: a second --apply is a no-op (sha256 stable)
  T5 — an archived entry leaves a one-line pointer + a cold-tier archive file
  T6 — a superseded entry is DELETED, not archived
  plus a realistic-size (production-scale) LORE fixture.

Every test runs the script via subprocess against a tmp_path fixture, asserting
observable behaviour at the filesystem level (no mocks).
"""

import hashlib
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "lore_hygiene.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lore(keep: int = 150, prune: int = 40, archive: int = 12, dup: int = 8) -> str:
    """Build a controllable LORE.md fixture.

    Returns a file that is over the 200-line cap and reducible back under it via
    prune (drop) + archive (multi-line → 1-line pointer) + dedup (drop repeats).
    """
    lines = [
        "---",
        "type: sanctum-lore",
        "agent: parzival",
        "tier: 3",
        "load: session-start",
        "---",
        "",
        "# Lore",
        "",
        "## System Architecture",
        "",
    ]
    lines += [
        f"- Keep fact {i}: component {i} connects to service {i}." for i in range(keep)
    ]
    lines += ["", "## Things Learned the Hard Way", ""]
    lines += [
        f"- [superseded] Old belief {i} that was later proven wrong."
        for i in range(prune)
    ]
    for i in range(archive):
        lines += [
            f"- [stale] Historical decision {i} about the old pipeline.",
            "  Context that mattered at the time but is now background.",
            "  A second continuation line of detail for this decision.",
        ]
    # Exact duplicates of an early keep entry — should dedup to one.
    lines += ["- Keep fact 0: component 0 connects to service 0." for _ in range(dup)]
    lines += [""]
    return "\n".join(lines) + "\n"


def _write_lore(tmp_path: Path, content: str | None = None) -> Path:
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    lore = sanctum / "LORE.md"
    lore.write_text(content if content is not None else _lore())
    return lore


def test_T1_dry_run_mutates_nothing(tmp_path):
    lore = _write_lore(tmp_path)
    sanctum = lore.parent
    before = _sha(lore)

    # Default invocation (no --apply) must be read-only.
    r = _run(str(sanctum))
    assert r.returncode == 0, r.stderr
    assert "DRY-RUN" in r.stdout

    assert _sha(lore) == before, "dry-run modified the file"
    assert not list(sanctum.glob("*.bak")), "dry-run created a backup"
    assert not (
        sanctum / "references" / "lore-archive"
    ).exists(), "dry-run wrote an archive"


def test_T2_over_cap_plan_proposes_compaction(tmp_path):
    lore = _write_lore(tmp_path)
    original = len(lore.read_text().splitlines())
    assert original > 200, "fixture should be over cap"

    r = _run(str(lore.parent))
    assert r.returncode == 0, r.stderr
    assert "OVER CAP" in r.stdout
    # The plan must propose concrete actions.
    assert "[prune]" in r.stdout
    assert "[archive]" in r.stdout
    assert "projected:" in r.stdout


def test_T3_apply_brings_file_under_cap(tmp_path):
    lore = _write_lore(tmp_path)
    assert len(lore.read_text().splitlines()) > 200

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr

    after = len(lore.read_text().splitlines())
    assert after <= 200, f"file still over cap after --apply ({after} lines)"
    # A timestamped backup must have been written before mutation.
    assert list(lore.parent.glob("LORE.md.*.bak")), "no backup sidecar written"


def test_T4_apply_is_idempotent(tmp_path):
    lore = _write_lore(tmp_path)

    r1 = _run(str(lore.parent), "--apply")
    assert r1.returncode == 0, r1.stderr
    sha_after_first = _sha(lore)

    r2 = _run(str(lore.parent), "--apply")
    assert r2.returncode == 0, r2.stderr
    assert _sha(lore) == sha_after_first, "second --apply changed an already-clean file"
    assert "no changes" in r2.stdout.lower()


def test_T5_archive_leaves_pointer_and_cold_file(tmp_path):
    lore = _write_lore(tmp_path)
    sanctum = lore.parent

    r = _run(str(sanctum), "--apply")
    assert r.returncode == 0, r.stderr

    archive = sanctum / "references" / "lore-archive" / "LORE.archive.md"
    assert archive.exists(), "cold-tier archive file not created"
    archive_text = archive.read_text()
    assert "Historical decision 0 about the old pipeline." in archive_text

    hot = lore.read_text()
    assert "_[archived " in hot and "→" in hot, "no one-line pointer left in hot file"
    # The full multi-line archived detail must NOT remain in the hot file.
    assert "A second continuation line of detail" not in hot


def test_T6_superseded_is_deleted_not_archived(tmp_path):
    lore = _write_lore(tmp_path)
    sanctum = lore.parent

    r = _run(str(sanctum), "--apply")
    assert r.returncode == 0, r.stderr

    hot = lore.read_text()
    archive_path = sanctum / "references" / "lore-archive" / "LORE.archive.md"
    archive_text = archive_path.read_text() if archive_path.exists() else ""

    needle = "Old belief 0 that was later proven wrong."
    assert needle not in hot, "superseded entry survived in the hot file"
    assert (
        needle not in archive_text
    ), "superseded entry was archived (should be deleted)"


def test_expired_ttl_and_strikethrough_are_pruned(tmp_path):
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        "- [expired:2000-01-01] A TTL entry whose date has long passed.\n"
        "- ~~A struck-out belief that was reversed.~~\n"
        "- A current, valid fact that must be kept.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()
    assert "A TTL entry whose date has long passed" not in hot
    assert "struck-out belief" not in hot
    assert "A current, valid fact that must be kept." in hot


def test_clean_under_cap_file_is_noop(tmp_path):
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## System Architecture\n\n"
        "- A small, clean, current fact.\n- Another durable fact.\n"
    )
    lore = _write_lore(tmp_path, content)
    before = _sha(lore)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    assert _sha(lore) == before, "clean under-cap file was modified"
    assert not list(lore.parent.glob("*.bak"))


def test_realistic_size_production_lore(tmp_path):
    """feedback_realistic_size_production_artifact_tests — exercise a production-scale
    LORE file (well over cap, mixed content) end to end."""
    lore = _write_lore(tmp_path, _lore(keep=130, prune=60, archive=20, dup=10))
    original = len(lore.read_text().splitlines())
    assert original > 250, "realistic fixture should be substantially over cap"

    # Dry-run reports the over-cap state without mutating.
    before = _sha(lore)
    r_dry = _run(str(lore.parent))
    assert r_dry.returncode == 0, r_dry.stderr
    assert "OVER CAP" in r_dry.stdout
    assert _sha(lore) == before

    # Apply brings it under cap and produces a backup + archive.
    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    assert len(lore.read_text().splitlines()) <= 200
    assert (lore.parent / "references" / "lore-archive" / "LORE.archive.md").exists()


def test_residual_over_cap_flags_not_truncates(tmp_path):
    """memory-blindness guard (BP-159 §6): when a file is over cap with only unique,
    current keep-entries, the script flags a residual instead of silently truncating."""
    # 210 unique, unprunable, unarchivable entries — mechanical compaction cannot
    # get under 200 without semantic summarization, which the script refuses to fake.
    lore = _write_lore(tmp_path, _lore(keep=210, prune=0, archive=0, dup=0))
    n_keep_before = lore.read_text().count("- Keep fact ")

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr

    hot = lore.read_text()
    assert (
        len(hot.splitlines()) > 200
    ), "file was truncated under cap (memory blindness!)"
    assert hot.count("- Keep fact ") == n_keep_before, "keep entries were lost"
    assert (
        "manual/LLM semantic summarization" in r.stdout.lower()
        or "still" in r.stdout.lower()
    )


def test_scans_both_hot_files_in_a_sanctum_dir(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    (sanctum / "LORE.md").write_text(_lore())
    (sanctum / "MEMORY.md").write_text(
        "---\ntype: sanctum-memory\n---\n\n# Memory\n\n## Pending Items\n\n"
        "| Item | Owner | Unblock |\n|------|-------|--------|\n"
        "| [superseded] old task | x | y |\n| live task | a | b |\n"
    )

    r = _run(str(sanctum))
    assert r.returncode == 0, r.stderr
    assert "LORE.md" in r.stdout and "MEMORY.md" in r.stdout


# --- H1: leading-only marker matching (prose mention / trailing must NOT prune) --


def test_H1_prose_mention_kept_leading_tag_pruned(tmp_path):
    """A marker mentioned in prose is recall-worthy and must be KEPT; only a marker
    in the anchored LEADING position classifies the entry. Fails on the old
    substring-anywhere matcher, which self-destructively prunes the prose entry."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Patterns & Conventions\n\n"
        "- Tag an entry [superseded] when it is no longer accurate.\n"
        "- [superseded] Old belief that was later proven wrong.\n"
        "- A current, durable fact with no marker at all.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    # Prose mention — KEPT (the H1 regression: old code wrongly pruned this).
    assert "Tag an entry [superseded] when it is no longer accurate." in hot
    # Leading anchored tag — pruned.
    assert "Old belief that was later proven wrong." not in hot
    # Untagged fact — kept.
    assert "A current, durable fact with no marker at all." in hot


def test_M_trailing_prose_marker_is_kept(tmp_path):
    """LEADING-ONLY anchoring (M-TRAILING-PROSE): an entry whose prose merely *ends*
    in a marker token is recall-worthy and must be KEPT. Fails on the cycle-1
    trailing-zone matcher, which wrongly pruned it."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Patterns & Conventions\n\n"
        "- A fact retired only at the end of its life [obsolete]\n"
        "- The deploy rule changed after the incident [superseded]\n"
        "- [superseded] An entry actually tagged for prune at the front.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    # Prose ending in a marker token — KEPT (trailing anchoring removed in cycle-2).
    assert "A fact retired only at the end of its life [obsolete]" in hot
    assert "The deploy rule changed after the incident [superseded]" in hot
    # A genuine leading tag still prunes.
    assert "An entry actually tagged for prune at the front." not in hot


def test_M_multiline_entry_leading_tag_handled(tmp_path):
    """LEADING-ONLY anchoring: a multi-line entry with a LEADING tag is classified by
    its first line; a multi-line entry whose marker only *ends* the first line is
    KEPT (no trailing-zone miss/over-reach)."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        "- [stale] A historical decision about the old pipeline.\n"
        "  A continuation line with the detail that mattered then.\n"
        "- A live decision whose first line ends in a token [obsolete]\n"
        "  and continues with detail that must be kept.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()
    archive = (
        lore.parent / "references" / "lore-archive" / "LORE.archive.md"
    ).read_text()

    # Leading [stale] on a multi-line entry → archived (pointer in hot, detail cold).
    assert "A historical decision about the old pipeline." in archive
    assert "A continuation line with the detail that mattered then." not in hot
    assert "_[archived " in hot
    # Marker only ending the first line → KEPT in full (both lines).
    assert "A live decision whose first line ends in a token [obsolete]" in hot
    assert "and continues with detail that must be kept." in hot


# --- H2: table header/separator rows are never deduped --------------------------


def test_H2_two_same_schema_tables_keep_headers_and_separators(tmp_path):
    """Two tables sharing a column schema must each retain their header + separator
    after --apply. Fails on the old file-global dedup, which drops the 2nd header."""
    content = (
        "---\ntype: sanctum-memory\n---\n\n# Memory\n\n"
        "## Pending Items\n\n"
        "| Item | Owner | Unblock |\n|------|-------|--------|\n"
        "| task one | alice | review |\n\n"
        "## Insights to Carry\n\n"
        "| Item | Owner | Unblock |\n|------|-------|--------|\n"
        "| task two | bob | merge |\n"
    )
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    mem = sanctum / "MEMORY.md"
    mem.write_text(content)

    r = _run(str(mem), "--apply")
    assert r.returncode == 0, r.stderr
    hot = mem.read_text()

    assert (
        hot.count("| Item | Owner | Unblock |") == 2
    ), "a table header was deduped away"
    assert hot.count("|------|-------|--------|") == 2, "a separator was deduped away"
    assert "| task one | alice | review |" in hot
    assert "| task two | bob | merge |" in hot


# --- M1: same-day applies must not overwrite the prior backup -------------------


def test_M1_two_same_day_applies_produce_distinct_backups(tmp_path):
    lore = _write_lore(tmp_path)
    r1 = _run(str(lore.parent), "--apply")
    assert r1.returncode == 0, r1.stderr
    assert len(list(lore.parent.glob("LORE.md.*.bak"))) == 1

    # Re-introduce same-day drift and apply again — must not clobber the 1st backup.
    lore.write_text(_lore())
    r2 = _run(str(lore.parent), "--apply")
    assert r2.returncode == 0, r2.stderr

    backups = sorted(lore.parent.glob("LORE.md.*.bak"))
    assert len(backups) == 2, "second same-day apply overwrote the first backup"
    assert backups[0].name != backups[1].name


# --- M2: --qdrant degrades gracefully when the runtime/Qdrant is absent ---------


def test_M2_qdrant_runtime_absent_is_graceful_noop(tmp_path):
    lore = _write_lore(tmp_path)
    sanctum = lore.parent

    r = _run(str(sanctum), "--apply", "--qdrant", "--group-id", "testproj")
    assert r.returncode == 0, r.stderr  # no hard dependency, no crash

    # The local archive (source of truth) is written regardless of the Qdrant tier.
    assert (sanctum / "references" / "lore-archive" / "LORE.archive.md").exists()
    # The Qdrant path executed and reported its status (push or graceful skip).
    assert "qdrant:" in r.stdout


# --- M3: classification marker must not leak into the pointer body --------------


def test_M3_marker_stripped_from_pointer(tmp_path):
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        "- [stale] Historical decision about the old pipeline.\n"
        "  Detail that now lives behind the index line.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    assert "_[archived " in hot, "no pointer was left"
    assert "[stale]" not in hot, "classification marker leaked into the pointer"
    assert "Historical decision about the old pipeline." in hot


# --- M4: --cap override, multi-file apply, single-file invocation ----------------


def test_M4_cap_override_changes_over_cap_status(tmp_path):
    # ~225 unique keep-lines: over the 200 default, comfortably under a 300 override.
    lore = _write_lore(tmp_path, _lore(keep=210, prune=0, archive=0, dup=0))
    n = len(lore.read_text().splitlines())
    assert 200 < n < 300, n

    r_default = _run(str(lore))
    assert "OVER CAP" in r_default.stdout

    r_override = _run(str(lore), "--cap", "300")
    assert r_override.returncode == 0, r_override.stderr
    assert "OVER CAP" not in r_override.stdout
    assert "/300 lines" in r_override.stdout


def test_M4_multi_file_apply_mutates_both(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    (sanctum / "LORE.md").write_text(_lore())
    (sanctum / "MEMORY.md").write_text(
        "---\ntype: sanctum-memory\n---\n\n# Memory\n\n## Pending Items\n\n"
        "- [superseded] an old pending item that is now done.\n"
        "- a live pending item to keep.\n"
    )

    r = _run(str(sanctum), "--apply")
    assert r.returncode == 0, r.stderr
    assert list(sanctum.glob("LORE.md.*.bak"))
    assert list(sanctum.glob("MEMORY.md.*.bak"))

    mem = (sanctum / "MEMORY.md").read_text()
    assert "an old pending item that is now done." not in mem
    assert "a live pending item to keep." in mem


def test_M4_single_file_invocation(tmp_path):
    lore = _write_lore(tmp_path)
    # Pass the FILE itself (not the sanctum dir).
    r = _run(str(lore), "--apply")
    assert r.returncode == 0, r.stderr
    assert len(lore.read_text().splitlines()) <= 200
    assert list(lore.parent.glob("LORE.md.*.bak"))


# --- L1: --cap <= 0 is guarded (no ZeroDivisionError) ---------------------------


def test_L1_cap_zero_is_guarded(tmp_path):
    lore = _write_lore(tmp_path)
    r = _run(str(lore), "--cap", "0")
    assert r.returncode != 0
    assert "--cap must be a positive integer" in r.stderr


# --- L3: a crash-rerun must not duplicate cold-tier entries ----------------------


def test_L3_rerun_does_not_duplicate_cold_entries(tmp_path):
    """Simulates a crash between cold-append and hot-write: the hot file keeps its
    [stale] entry, so a rerun re-archives it. The cold tier must stay deduplicated."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        "- [stale] Historical decision 0 about the old pipeline.\n"
        "  Context that mattered at the time.\n"
    )
    lore = _write_lore(tmp_path, content)

    r1 = _run(str(lore.parent), "--apply")
    assert r1.returncode == 0, r1.stderr

    # Re-introduce the same [stale] entry (the crash-rerun scenario) and re-apply.
    lore.write_text(content)
    r2 = _run(str(lore.parent), "--apply")
    assert r2.returncode == 0, r2.stderr

    archive = (
        lore.parent / "references" / "lore-archive" / "LORE.archive.md"
    ).read_text()
    assert (
        archive.count("Historical decision 0 about the old pipeline.") == 1
    ), "cold tier accumulated a duplicate on rerun"


# --- H3: archiving a tagged table content row must not corrupt the table ---------


def test_H3_archive_tagged_table_row_no_corruption_no_leak(tmp_path):
    """An [archive]-tagged table CONTENT row must NOT inject an inline bullet pointer
    into the table body (mid-table line break + leaked pipes/marker). The table must
    stay well-formed, the archived content must reach the cold tier, and no marker or
    table pipe may leak into the hot file. Fails on 94de5fa, where the archive branch
    emitted pointer_for(unit) for the table row before the is_table_row guard."""
    content = (
        "---\ntype: sanctum-memory\n---\n\n# Memory\n\n## Pending Items\n\n"
        "| Item | Owner | Unblock |\n|------|-------|--------|\n"
        "| live task one | alice | review |\n"
        "| [archive] old pipeline migration row | bob | done |\n"
        "| live task two | carol | merge |\n"
    )
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    mem = sanctum / "MEMORY.md"
    mem.write_text(content)

    r = _run(str(mem), "--apply")
    assert r.returncode == 0, r.stderr
    hot = mem.read_text()

    # Table stays well-formed: header + separator + the two live rows survive intact.
    assert hot.count("| Item | Owner | Unblock |") == 1
    assert hot.count("|------|-------|--------|") == 1
    assert "| live task one | alice | review |" in hot
    assert "| live task two | carol | merge |" in hot

    # No inline bullet pointer injected into the table body, and NO marker/pipe leak:
    # the archived row's content (and its marker) must be gone from the hot file.
    assert "_[archived " not in hot, "an inline pointer bullet was injected into table"
    assert "[archive] old pipeline migration row" not in hot
    assert "old pipeline migration row" not in hot, "archived table content leaked hot"

    # No malformed bullet-with-pipes line survived anywhere in the hot file.
    for line in hot.splitlines():
        if line.lstrip().startswith("-"):
            assert "|" not in line, f"a bullet line leaked table pipes: {line!r}"

    # The archived row content is preserved in the cold tier (data safety).
    archive = (
        sanctum / "references" / "lore-archive" / "MEMORY.archive.md"
    ).read_text()
    assert "old pipeline migration row" in archive


# --- TGT-1: a prune-tagged table content row is dropped in place, table valid -----


def test_TGT1_prune_tagged_table_row_dropped_table_valid(tmp_path):
    """A [prune]-tagged table CONTENT row is dropped in place; the table stays valid
    and nothing is written to the cold tier (prune deletes; archive preserves)."""
    content = (
        "---\ntype: sanctum-memory\n---\n\n# Memory\n\n## Pending Items\n\n"
        "| Item | Owner | Unblock |\n|------|-------|--------|\n"
        "| live task one | alice | review |\n"
        "| [superseded] a row that is now wrong | bob | n/a |\n"
        "| live task two | carol | merge |\n"
    )
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    mem = sanctum / "MEMORY.md"
    mem.write_text(content)

    r = _run(str(mem), "--apply")
    assert r.returncode == 0, r.stderr
    hot = mem.read_text()

    assert hot.count("| Item | Owner | Unblock |") == 1
    assert hot.count("|------|-------|--------|") == 1
    assert "| live task one | alice | review |" in hot
    assert "| live task two | carol | merge |" in hot
    # The pruned row is gone, with no marker/pipe residue and no pointer bullet.
    assert "a row that is now wrong" not in hot
    assert "_[archived " not in hot
    # Pruned (not archived): no cold-tier file is created for it.
    archive_path = sanctum / "references" / "lore-archive" / "MEMORY.archive.md"
    if archive_path.exists():
        assert "a row that is now wrong" not in archive_path.read_text()


# --- M-STRIKE-PARTIAL: only a FULLY-struck entry is pruned -----------------------


def test_M_strike_partial_kept_full_struck_pruned(tmp_path):
    """Partial strikethrough (live un-struck text between spans) is KEPT; only a
    single ~~...~~ span covering the whole entry is pruned. Fails on 94de5fa, whose
    starts-with-~~ and ends-with-~~ test wrongly pruned the partial entry."""
    # The first entry both STARTS and ENDS with a ~~ span but has live, un-struck
    # text between them — this is the exact shape the cycle-1 starts-/ends-with-~~
    # check wrongly pruned.
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        "- ~~old approach~~ but still relevant, see ~~ticket Y~~\n"
        "- ~~A belief fully struck out because it was reversed.~~\n"
        "- A current, valid fact with no strikethrough.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    # Partial strikethrough with interior live text — KEPT.
    assert "but still relevant, see" in hot
    # Fully-struck entry — pruned.
    assert "A belief fully struck out because it was reversed." not in hot
    # Untagged fact — kept.
    assert "A current, valid fact with no strikethrough." in hot


# --- L-PLUS-BULLET: '+' bullets are recognized ----------------------------------


def test_L_plus_bullet_is_classified(tmp_path):
    """A '+' unordered-list bullet must be recognized so a leading tag on it acts.
    Fails on 94de5fa, where is_bullet/_LEADING_PREFIX_RE ignored '+', leaving the
    leading marker unanchored and the entry wrongly kept."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Things Learned the Hard Way\n\n"
        "+ [superseded] An old belief on a plus-bullet, now wrong.\n"
        "+ A current fact on a plus-bullet that must be kept.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    assert "An old belief on a plus-bullet, now wrong." not in hot
    assert "A current fact on a plus-bullet that must be kept." in hot


# --- Structure-aware parser (cycle-3 root-cause): structural constructs are opaque -
#
# The whole data-corruption class (fenced content deduped/pruned, thematic-break
# dedup, tagged-table-header archive, keep-when-uncertain) closes at once because the
# parser now classifies/dedups GENUINE CONTENT ENTRIES ONLY; every structural or
# ambiguous construct is opaque passthrough. Each test below FAILS on f5b26b5.


def test_FENCE_markerless_bullet_list_survives_intact(tmp_path):
    """H-FENCE: a fenced bullet-list with NO markers must survive byte-for-byte — both
    fence delimiters AND the fenced bullets. Fails on f5b26b5, where the parser saw
    the fenced bullets as content: identical lines (incl. the closing ```` ``` ````)
    deduped away, corrupting the fence."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Code Examples\n\n"
        "```\n"
        "- step one in the example\n"
        "- step two in the example\n"
        "- step one in the example\n"  # an exact dup line — must NOT be deduped
        "```\n"
        "\n"
        "- A real bullet after the fence to keep.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    assert hot.count("```") == 2, "a fence delimiter was lost (fence corrupted)"
    assert hot.count("- step one in the example") == 2, "fenced dup line was deduped"
    assert "- step two in the example" in hot
    assert "- A real bullet after the fence to keep." in hot


def test_FENCE_marker_leading_line_inside_fence_is_kept(tmp_path):
    """A marker-leading line INSIDE a code fence is fenced content, not a tagged entry,
    and must be KEPT. Fails on f5b26b5, which pruned it as a [prune]-tagged bullet."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Code Examples\n\n"
        "```bash\n"
        "- [prune] this is example text demonstrating a marker, not a real entry\n"
        "echo done\n"
        "```\n"
        "- [prune] a genuine tagged entry OUTSIDE the fence, which IS pruned.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    # Inside the fence → kept verbatim (fence delimiters intact).
    assert hot.count("```") == 2
    assert "- [prune] this is example text demonstrating a marker" in hot
    assert "echo done" in hot
    # The genuine tagged entry outside the fence is still pruned.
    assert "a genuine tagged entry OUTSIDE the fence" not in hot


def test_FENCE_unterminated_keeps_remainder_opaque(tmp_path):
    """An unterminated fence keeps its remainder opaque (keep-when-uncertain) — nothing
    inside it is classified/deduped."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Code Examples\n\n"
        "```\n"
        "- [superseded] looks tagged but is inside an unterminated fence\n"
        "- a duplicate line\n"
        "- a duplicate line\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    assert "looks tagged but is inside an unterminated fence" in hot
    assert hot.count("- a duplicate line") == 2, "deduped inside an unterminated fence"


def test_TBL_HDR_tagged_header_keeps_table_valid(tmp_path):
    """M-TBL-HDR: a tagged table HEADER row is structural — it must NOT be classified/
    removed, so the separator is never orphaned. Fails on f5b26b5, which archived the
    tagged header and left a dangling separator (corrupt table)."""
    content = (
        "---\ntype: sanctum-memory\n---\n\n# Memory\n\n## Pending Items\n\n"
        "| [stale] Item | Owner | Unblock |\n"
        "|------|-------|--------|\n"
        "| live row one | alice | review |\n"
        "| live row two | bob | merge |\n"
    )
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    mem = sanctum / "MEMORY.md"
    mem.write_text(content)

    r = _run(str(mem), "--apply")
    assert r.returncode == 0, r.stderr
    hot = mem.read_text()

    # The tagged header survives intact, atop its separator — table stays valid.
    assert "| [stale] Item | Owner | Unblock |" in hot, "tagged header was removed"
    assert hot.count("|------|-------|--------|") == 1, "separator orphaned/removed"
    assert "| live row one | alice | review |" in hot
    assert "| live row two | bob | merge |" in hot
    # Nothing was archived (the header is structural, not a stale content entry).
    archive_path = sanctum / "references" / "lore-archive" / "MEMORY.archive.md"
    assert not archive_path.exists() or "Item" not in archive_path.read_text()


def test_THEMATIC_breaks_are_not_deduped(tmp_path):
    """Repeated thematic breaks (``---`` three times) are structural delimiters, never deduped.
    Fails on f5b26b5, which deduped the repeats down to one."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Sections\n\n"
        "- first fact\n\n"
        "---\n\n"
        "- second fact\n\n"
        "---\n\n"
        "- third fact\n\n"
        "---\n\n"
        "- fourth fact\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    # Count standalone ``---`` lines in the BODY (excludes the frontmatter fence,
    # which is split off and reattached verbatim).
    body = hot.split("\n---\n", 1)[-1]  # drop frontmatter open+close
    assert body.count("\n---\n") == 3, "a thematic break was deduped away"
    for fact in ("first", "second", "third", "fourth"):
        assert f"- {fact} fact" in hot


def test_UNCERTAIN_blockquote_and_html_kept_unchanged(tmp_path):
    """Keep-when-uncertain: blockquotes and raw-HTML blocks are ambiguous constructs →
    kept opaque, never classified or deduped, even when they contain a marker token or
    duplicate lines. Fails on f5b26b5, which pruned the [superseded]-leading blockquote
    line and deduped the repeated HTML line."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Notes\n\n"
        "> [superseded] a quoted line that merely shows a marker, kept opaque\n"
        "> a second quoted line\n"
        "\n"
        '<div class="callout">a raw html block</div>\n'
        "\n"
        '<div class="callout">a raw html block</div>\n'  # dup across a blank line
        "\n"
        "- a normal fact to keep\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    assert "> [superseded] a quoted line that merely shows a marker" in hot
    assert "> a second quoted line" in hot
    assert hot.count('<div class="callout">a raw html block</div>') == 2
    assert "- a normal fact to keep" in hot


def test_REALISTIC_memory_file_only_genuine_entry_acted_on(tmp_path):
    """A realistic MEMORY.md-shaped file (frontmatter + bullets + two same-schema
    tables + a fenced code block + prose mentioning markers + ONE real tagged entry):
    only the genuine tagged entry is acted on; everything structural is byte-preserved.
    Fails on f5b26b5 across multiple constructs at once."""
    content = (
        "---\n"
        "type: sanctum-memory\n"
        "agent: parzival\n"
        "---\n"
        "\n"
        "# Memory\n"
        "\n"
        "## Conventions\n"
        "\n"
        "- Tag an entry [superseded] in prose when it is no longer accurate.\n"
        "- A durable convention with no marker.\n"
        "\n"
        "## Pending Items\n"
        "\n"
        "| Item | Owner | Unblock |\n"
        "|------|-------|--------|\n"
        "| pending task A | alice | review |\n"
        "\n"
        "## Insights to Carry\n"
        "\n"
        "| Item | Owner | Unblock |\n"
        "|------|-------|--------|\n"
        "| insight B | bob | n/a |\n"
        "\n"
        "## Snippets\n"
        "\n"
        "```text\n"
        "- [prune] example showing how to tag a line — NOT a real entry\n"
        "- a sample documentation line\n"
        "- a sample documentation line\n"  # exact dup inside the fence
        "```\n"
        "\n"
        "## Decisions\n"
        "\n"
        "- [superseded] the one genuine tagged entry that should be pruned.\n"
        "- a live decision to keep.\n"
    )
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    mem = sanctum / "MEMORY.md"
    mem.write_text(content)

    r = _run(str(mem), "--apply")
    assert r.returncode == 0, r.stderr
    hot = mem.read_text()

    # ONLY the genuine tagged entry is gone.
    assert "the one genuine tagged entry that should be pruned." not in hot
    assert "- a live decision to keep." in hot

    # Everything structural is byte-preserved.
    assert "- Tag an entry [superseded] in prose when it is no longer accurate." in hot
    assert "- A durable convention with no marker." in hot
    assert hot.count("| Item | Owner | Unblock |") == 2, "a table header was lost"
    assert hot.count("|------|-------|--------|") == 2, "a table separator was lost"
    assert "| pending task A | alice | review |" in hot
    assert "| insight B | bob | n/a |" in hot
    assert hot.count("```") == 2, "a code fence delimiter was lost"
    assert "- [prune] example showing how to tag a line — NOT a real entry" in hot
    assert hot.count("- a sample documentation line") == 2, "fenced dup line deduped"

    # Exactly one prune action, no archive/dedup churn on structure.
    assert "prune 1" in r.stdout
    assert "archive 0" in r.stdout
    assert "dedup 0" in r.stdout


# --- H-HTML: multi-line raw-HTML blocks stay fully opaque (blank-line terminated) ---
#
# On f24547f the keep-when-uncertain HTML arm gathered with ``same=is_html_block_start``,
# stopping at the first inner line not starting with ``<``; inner lines then leaked to
# the paragraph/bullet branch and were classified/deduped/pruned. The tests below FAIL
# on f24547f (inner content pruned/deduped) and pass once HTML is gathered to its
# blank-line terminator as one opaque unit.


def test_HTML_multiline_block_inner_marker_and_dup_preserved(tmp_path):
    """A multi-line ``<div>`` / inner-marker-line / ``</div>`` block is ONE opaque unit:
    the whole block is byte-preserved, a leading-marker inner line is NOT pruned, and a
    repeated inner line is NOT deduped. Fails on f24547f (inner ``[superseded]`` line
    pruned; repeated inner line deduped to one)."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Notes\n\n"
        '<div class="callout">\n'
        "- [superseded] inner content that looks taggable but is inside the block\n"
        "- a repeated inner line\n"
        "- a repeated inner line\n"
        "</div>\n"
        "\n"
        "- a real fact to keep.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    assert '<div class="callout">' in hot
    assert "</div>" in hot
    assert (
        "- [superseded] inner content that looks taggable but is inside the block"
        in hot
    ), "inner HTML marker line was pruned (block not opaque)"
    assert hot.count("- a repeated inner line") == 2, "inner HTML dup line was deduped"
    assert "- a real fact to keep." in hot

    # (f) idempotent: a second apply changes nothing.
    sha1 = _sha(lore)
    r2 = _run(str(lore.parent), "--apply")
    assert r2.returncode == 0, r2.stderr
    assert _sha(lore) == sha1, "second apply mutated an already-clean HTML block"


def test_HTML_block_to_eof_no_trailing_blank_is_opaque(tmp_path):
    """An HTML block running to EOF with no trailing blank line keeps its remainder
    opaque. Fails on f24547f, where the inner ``[prune]`` line was pruned and the dup
    inner line deduped."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Notes\n\n"
        "<div>\n"
        "- [prune] looks tagged but is inside an HTML block that runs to EOF\n"
        "- dup inner line\n"
        "- dup inner line\n"
        "</div>"  # no trailing newline / blank line — block runs to EOF
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    assert "<div>" in hot and "</div>" in hot
    assert (
        "- [prune] looks tagged but is inside an HTML block that runs to EOF" in hot
    ), "inner marker line pruned in an HTML-to-EOF block"
    assert hot.count("- dup inner line") == 2, "inner dup line deduped in HTML-to-EOF"

    sha1 = _sha(lore)
    r2 = _run(str(lore.parent), "--apply")
    assert r2.returncode == 0, r2.stderr
    assert _sha(lore) == sha1, "second apply mutated an HTML-to-EOF block"


def test_HTML_after_paragraph_not_swallowed(tmp_path):
    """A paragraph immediately followed by an HTML block start: the paragraph is its own
    classifiable entry (so a duplicate paragraph dedups) and the HTML is opaque (not
    swallowed into the paragraph). Fails on f24547f, where the HTML start was glued into
    the paragraph (no html break in the paragraph break-set), so the standalone duplicate
    paragraph did NOT dedup and survived twice."""
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n## Notes\n\n"
        "Prose that must stay its own entry.\n"
        '<div class="x">a callout right after the prose</div>\n'
        "\n"
        "Prose that must stay its own entry.\n"
    )
    lore = _write_lore(tmp_path, content)

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    # Paragraph classified → the standalone duplicate is deduped to one occurrence.
    assert (
        hot.count("Prose that must stay its own entry.") == 1
    ), "HTML was swallowed into the paragraph (duplicate paragraph not deduped)"
    # HTML kept opaque, byte-preserved.
    assert '<div class="x">a callout right after the prose</div>' in hot

    sha1 = _sha(lore)
    r2 = _run(str(lore.parent), "--apply")
    assert r2.returncode == 0, r2.stderr
    assert _sha(lore) == sha1, "second apply was not idempotent"


# --- M-XSEC-DEDUP: dedup is section-scoped ---------------------------------------


def test_dedup_is_section_scoped(tmp_path):
    """Two identical content lines under DIFFERENT ``## section``s are BOTH kept; two
    identical lines within ONE section dedup to the first. Fails on f24547f, whose
    file-global ``seen`` set dropped the cross-section twin (one occurrence survived).
    """
    content = (
        "---\ntype: sanctum-lore\n---\n\n# Lore\n\n"
        "## Section A\n\n"
        "- identical content line\n"
        "- identical content line\n"  # within-section dup → second deduped
        "- a unique A line\n\n"
        "## Section B\n\n"
        "- identical content line\n"  # cross-section twin → KEPT
        "- a unique B line\n"
    )
    lore = _write_lore(tmp_path, content)
    assert lore.read_text().count("- identical content line") == 3

    r = _run(str(lore.parent), "--apply")
    assert r.returncode == 0, r.stderr
    hot = lore.read_text()

    # One in Section A (within-section dup collapsed) + one in Section B (cross-section
    # twin kept) = two. f24547f's file-global dedup leaves only one.
    assert (
        hot.count("- identical content line") == 2
    ), "cross-section identical entry was wrongly deduped (or within-section not deduped)"
    assert "- a unique A line" in hot
    assert "- a unique B line" in hot

    sha1 = _sha(lore)
    r2 = _run(str(lore.parent), "--apply")
    assert r2.returncode == 0, r2.stderr
    assert _sha(lore) == sha1, "second apply was not idempotent"


# --- L-CRLF: the file's original line ending is preserved ------------------------


def test_CRLF_input_keeps_crlf_no_mixing(tmp_path):
    """A CRLF file with one genuine prune keeps CRLF on untouched lines and never emits
    a mixed-ending file. Fails on f24547f, which read with universal-newline translation
    and rewrote the file with LF (no CRLF in the output)."""
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    lore = sanctum / "LORE.md"
    content = (
        "---\r\n"
        "type: sanctum-lore\r\n"
        "---\r\n"
        "\r\n"
        "# Lore\r\n"
        "\r\n"
        "## Things Learned the Hard Way\r\n"
        "\r\n"
        "- [superseded] an old belief that is now wrong\r\n"
        "- a durable fact to keep\r\n"
        "- another durable fact to keep\r\n"
    )
    lore.write_bytes(content.encode("utf-8"))

    r = _run(str(sanctum), "--apply")
    assert r.returncode == 0, r.stderr

    raw = lore.read_bytes()
    assert b"\r\n" in raw, "CRLF line endings were not preserved"
    # No mixing: stripping every CRLF leaves no lone LF.
    assert b"\n" not in raw.replace(b"\r\n", b""), "output mixed CRLF and LF endings"

    text = raw.decode("utf-8")
    assert (
        "an old belief that is now wrong" not in text
    ), "the tagged entry was not pruned"
    assert "a durable fact to keep" in text
    assert "another durable fact to keep" in text

    # A byte-faithful backup preserves the original CRLF too.
    backup = next(iter(sanctum.glob("LORE.md.*.bak")))
    assert b"\r\n" in backup.read_bytes(), "backup did not preserve CRLF"

    # (f) idempotent: a second apply changes nothing (still CRLF, no churn).
    sha1 = _sha(lore)
    r2 = _run(str(sanctum), "--apply")
    assert r2.returncode == 0, r2.stderr
    assert _sha(lore) == sha1, "second apply mutated the CRLF file"
