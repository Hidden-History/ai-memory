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
