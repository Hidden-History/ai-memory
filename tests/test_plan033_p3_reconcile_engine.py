"""Tests for the PLAN-033 P3 template-drift reconciliation engine (BP-187).

The engine lives at
``_ai-memory/pov/skills/aim-content-drift/scripts/reconcile_engine.py`` — outside any
importable package (a skill script invoked by path) — so it is loaded here via
``importlib.util.spec_from_file_location`` (the established repo pattern, mirrors
``tests/test_aim_doctor.py``). This test file lives under ``tests/`` so CI collects it
(TD-812: CI only collects ``tests/``).

Coverage (maps 1:1 to the P3 DONE-WHEN):
  - decide(): all 4 BP-187 cells (§2.2 table).
  - classify(): digest-triple -> decision, incl. the B="" fail-safe -> CONFLICT.
  - load_manifest(): parse the frozen P1 schema; reject unknown MAJOR, accept MINOR.
  - compute_hash(): == hashlib sha256 of raw bytes (installer parity).
  - is_stale(): unchanged / deployed-mutated / template-moved / deployed-gone.
  - format_version read/write: roundtrip, upsert, no-frontmatter raises.
  - apply_migrations(): ordered chain, idempotent, gap fail-loud, N/A tolerance.
  - atomic_write(): content + .bak + same-dir temp + no temp leak + crash cleanup.
  - reconcile_entry(): all 4 decisions dispatched + staleness-skip + ZERO-DATA-LOSS
    integration on a realistic bugs/INDEX.md-shaped fixture.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load the engine by file location (it is not part of the `memory` package).
_ENGINE_PATH = (
    Path(__file__).resolve().parent.parent
    / "_ai-memory"
    / "pov"
    / "skills"
    / "aim-content-drift"
    / "scripts"
    / "reconcile_engine.py"
)
_spec = importlib.util.spec_from_file_location("reconcile_engine", _ENGINE_PATH)
engine = importlib.util.module_from_spec(_spec)
# Register before exec: the module uses @dataclass, whose decorator looks up
# sys.modules[cls.__module__] — exec_module() would fail without this.
sys.modules[_spec.name] = engine
_spec.loader.exec_module(engine)

Decision = engine.Decision


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #
def _entry(
    *,
    base: str,
    deployed: str,
    new: str,
    path: str = "tracking/x.md",
    classification: str = "MANAGED_MERGE_REQUIRED",
):
    """Build a ReconcileEntry with just the digest triple that matters."""
    return engine.ReconcileEntry(
        id=path,
        path=f"oversight/{path}",
        classification=classification,
        old_shipped_hash=base,
        deployed_hash=deployed,
        new_template_hash=new,
        suggested_action="merge",
        rationale="test",
        severity="high",
        order=0,
    )


# A realistic data-bearing oversight file: YAML frontmatter (installer-owned
# STRUCTURE) + a data body (operator-owned rows). Modeled on the real
# oversight/bugs/INDEX.md shape. No format_version stamp yet (pre-P3 state).
INDEX_FIXTURE = """\
---
class: register
read_path: section-anchored
owns: "generated bug-or-TD index + closed-history shard"
cap_lines: 100
---
# Bug Tracker Index

**Last Updated**: 2026-07-14

## Quick Stats

| Metric | Count |
|--------|-------|
| Open   | 12    |
| Closed | 111   |

## Records

- BUG-527 — deploy parity — Closed
- BUG-528 — marker asymmetry — Open
- BUG-529 — adapter refresh — Open
"""


def _body_after_frontmatter(text: str) -> str:
    """Return everything after the closing frontmatter fence (the DATA body)."""
    lines = text.split("\n")
    assert lines[0].strip() == "---"
    close = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    return "\n".join(lines[close + 1 :])


# --------------------------------------------------------------------------- #
# decide() — the 4 BP-187 cells
# --------------------------------------------------------------------------- #
def test_decide_all_four_cells():
    assert engine.decide(user_edited=False, template_changed=False) == Decision.NO_OP
    assert engine.decide(user_edited=False, template_changed=True) == Decision.REFRESH
    assert engine.decide(user_edited=True, template_changed=False) == Decision.PRESERVE
    assert engine.decide(user_edited=True, template_changed=True) == Decision.CONFLICT


# --------------------------------------------------------------------------- #
# classify() — digest triple -> decision, incl. fail-safe
# --------------------------------------------------------------------------- #
def test_classify_no_op_when_all_equal():
    e = _entry(base="a", deployed="a", new="a")
    assert engine.classify(e) == Decision.NO_OP


def test_classify_refresh_when_only_template_changed():
    e = _entry(base="a", deployed="a", new="b")
    assert engine.classify(e) == Decision.REFRESH


def test_classify_preserve_when_only_user_edited():
    e = _entry(base="a", deployed="b", new="a")
    assert engine.classify(e) == Decision.PRESERVE


def test_classify_conflict_when_both_changed():
    e = _entry(base="a", deployed="b", new="c")
    assert engine.classify(e) == Decision.CONFLICT


def test_classify_empty_base_fails_safe_to_conflict():
    # BP-187 §2.1: no pristine base => cannot prove unedited => never blind-refresh.
    e = _entry(base="", deployed="b", new="c")
    assert engine.classify(e) == Decision.CONFLICT
    # Even when deployed == new (would look like NO_OP), an unknown base is CONFLICT.
    e2 = _entry(base="", deployed="b", new="b")
    assert engine.classify(e2) == Decision.CONFLICT


# --------------------------------------------------------------------------- #
# load_manifest() — frozen P1 schema; reject unknown MAJOR
# --------------------------------------------------------------------------- #
def _write_manifest(path: Path, schema_version: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "generated_at": "2026-07-14T00:00:00Z",
                "generated_by": "install.sh@2.8.3",
                "source_version": "2.8.3",
                "manifest_id": "deadbeef",
                "entries": [
                    {
                        "id": "tracking/decision-log.md",
                        "path": "oversight/tracking/decision-log.md",
                        "classification": "MANAGED_MERGE_REQUIRED",
                        "old_shipped_hash": "aaa",
                        "deployed_hash": "bbb",
                        "new_template_hash": "ccc",
                        "suggested_action": "merge",
                        "rationale": "both changed",
                        "severity": "high",
                        "order": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_load_manifest_parses_frozen_schema(tmp_path):
    m = tmp_path / "pending-updates.json"
    _write_manifest(m, "1.0")
    manifest = engine.load_manifest(m)
    assert manifest.schema_version == "1.0"
    assert manifest.manifest_id == "deadbeef"
    assert len(manifest.entries) == 1
    e = manifest.entries[0]
    assert e.id == "tracking/decision-log.md"
    assert e.old_shipped_hash == "aaa"
    assert e.deployed_hash == "bbb"
    assert e.new_template_hash == "ccc"
    assert e.order == 0


def test_load_manifest_accepts_higher_minor(tmp_path):
    m = tmp_path / "pending-updates.json"
    _write_manifest(m, "1.5")  # additive minor bump -> still supported
    manifest = engine.load_manifest(m)
    assert manifest.schema_version == "1.5"


def test_load_manifest_rejects_unknown_major(tmp_path):
    m = tmp_path / "pending-updates.json"
    _write_manifest(m, "2.0")
    with pytest.raises(engine.UnsupportedSchemaError):
        engine.load_manifest(m)


def test_load_manifest_rejects_garbage_schema(tmp_path):
    m = tmp_path / "pending-updates.json"
    _write_manifest(m, "not-a-version")
    with pytest.raises(engine.UnsupportedSchemaError):
        engine.load_manifest(m)


# --------------------------------------------------------------------------- #
# compute_hash() — installer parity
# --------------------------------------------------------------------------- #
def test_compute_hash_matches_sha256_of_bytes(tmp_path):
    f = tmp_path / "f.md"
    content = b"hello oversight\n"
    f.write_bytes(content)
    assert engine.compute_hash(f) == hashlib.sha256(content).hexdigest()


# --------------------------------------------------------------------------- #
# is_stale() — level-triggered re-check
# --------------------------------------------------------------------------- #
def test_is_stale_false_when_unchanged(tmp_path):
    f = tmp_path / "d.md"
    f.write_bytes(b"deployed\n")
    e = _entry(base="a", deployed=engine.compute_hash(f), new="c")
    assert engine.is_stale(e, deployed_path=f) is False


def test_is_stale_true_when_deployed_mutated(tmp_path):
    f = tmp_path / "d.md"
    f.write_bytes(b"deployed\n")
    e = _entry(base="a", deployed=engine.compute_hash(f), new="c")
    f.write_bytes(b"deployed CHANGED\n")  # moved since manifest
    assert engine.is_stale(e, deployed_path=f) is True


def test_is_stale_true_when_deployed_gone(tmp_path):
    e = _entry(base="a", deployed="whatever", new="c")
    assert engine.is_stale(e, deployed_path=tmp_path / "missing.md") is True


def test_is_stale_true_when_template_moved(tmp_path):
    d = tmp_path / "d.md"
    d.write_bytes(b"deployed\n")
    t = tmp_path / "t.md"
    t.write_bytes(b"template\n")
    e = _entry(base="a", deployed=engine.compute_hash(d), new="STALEHASH")
    assert engine.is_stale(e, deployed_path=d, new_template_path=t) is True


# --------------------------------------------------------------------------- #
# format_version read/write
# --------------------------------------------------------------------------- #
def test_read_format_version_absent_is_zero():
    assert engine.read_format_version("# plain doc\n\nno frontmatter\n") == 0
    assert engine.read_format_version(INDEX_FIXTURE) == 0  # frontmatter, no stamp


def test_write_then_read_format_version_roundtrip():
    stamped = engine.write_format_version(INDEX_FIXTURE, 3)
    assert engine.read_format_version(stamped) == 3
    # Idempotent upsert: re-stamping replaces, never duplicates.
    stamped2 = engine.write_format_version(stamped, 4)
    assert engine.read_format_version(stamped2) == 4
    assert stamped2.count("format_version:") == 1


def test_write_format_version_preserves_body_and_other_frontmatter():
    stamped = engine.write_format_version(INDEX_FIXTURE, 1)
    # Body (DATA) is byte-identical.
    assert _body_after_frontmatter(stamped) == _body_after_frontmatter(INDEX_FIXTURE)
    # Every original frontmatter key survives.
    for key in ("class:", "read_path:", "owns:", "cap_lines:"):
        assert key in stamped


def test_write_format_version_no_frontmatter_raises():
    with pytest.raises(engine.CannotStampError):
        engine.write_format_version("# plain\n\nbody\n", 1)


# --------------------------------------------------------------------------- #
# apply_migrations() — ordered / idempotent / gap / N/A
# --------------------------------------------------------------------------- #
def _synthetic_chain():
    """Two structural migrations that each append a marker line (frontmatter file)."""

    def to_v1(text: str) -> str:
        return text.rstrip("\n") + "\nMARK_V1\n"

    def to_v2(text: str) -> str:
        return text.rstrip("\n") + "\nMARK_V2\n"

    return (
        engine.Migration(0, 1, to_v1, "s0001"),
        engine.Migration(1, 2, to_v2, "s0002"),
    )


def test_apply_migrations_runs_ordered_chain():
    out = engine.apply_migrations(INDEX_FIXTURE, 2, _synthetic_chain())
    assert engine.read_format_version(out) == 2
    # Both structural markers applied, in order.
    v1_pos = out.index("MARK_V1")
    v2_pos = out.index("MARK_V2")
    assert v1_pos < v2_pos
    # Original DATA body still present (zero-loss through the chain).
    assert "BUG-529 — adapter refresh — Open" in out


def test_apply_migrations_is_idempotent():
    once = engine.apply_migrations(INDEX_FIXTURE, 2, _synthetic_chain())
    twice = engine.apply_migrations(once, 2, _synthetic_chain())
    assert once == twice  # already at target -> unchanged


def test_apply_migrations_partial_then_resume():
    partial = engine.apply_migrations(INDEX_FIXTURE, 1, _synthetic_chain())
    assert engine.read_format_version(partial) == 1
    assert "MARK_V1" in partial and "MARK_V2" not in partial
    full = engine.apply_migrations(partial, 2, _synthetic_chain())
    assert engine.read_format_version(full) == 2
    assert full.count("MARK_V1") == 1  # not re-applied


def test_apply_migrations_gap_fails_loud():
    # Only a 1->2 migration exists; a v0 file has no way to reach it.
    only_v1_v2 = (engine.Migration(1, 2, lambda t: t, "s0002"),)
    with pytest.raises(engine.MigrationChainError):
        engine.apply_migrations(INDEX_FIXTURE, 2, only_v1_v2)


def test_apply_migrations_baseline_stamp_on_real_fixture():
    # The shipped MIGRATIONS registry (0001 baseline) on a real frontmatter file.
    out = engine.apply_migrations(
        INDEX_FIXTURE, engine.CURRENT_FORMAT_VERSION, engine.MIGRATIONS
    )
    assert engine.read_format_version(out) == 1
    assert _body_after_frontmatter(out) == _body_after_frontmatter(INDEX_FIXTURE)


def test_apply_migrations_no_frontmatter_is_na_terminal():
    plain = "# plain doc\n\n- data row 1\n- data row 2\n"
    out = engine.apply_migrations(plain, 1, engine.MIGRATIONS)
    # No frontmatter to stamp: baseline transform is identity -> file byte-identical,
    # a clean terminal (data preserved), never a dead-end or error.
    assert out == plain


# --------------------------------------------------------------------------- #
# atomic_write() — crash-safe, backup-first (BP-187 §4)
# --------------------------------------------------------------------------- #
def test_atomic_write_writes_content_and_backs_up(tmp_path):
    f = tmp_path / "sub" / "f.md"
    f.parent.mkdir()
    f.write_text("ORIGINAL\n", encoding="utf-8")
    backup = engine.atomic_write(f, "NEW CONTENT\n")
    assert f.read_text(encoding="utf-8") == "NEW CONTENT\n"
    assert backup == str(f) + ".bak"
    assert Path(backup).read_text(encoding="utf-8") == "ORIGINAL\n"


def test_atomic_write_no_backup_when_target_absent(tmp_path):
    f = tmp_path / "new.md"
    backup = engine.atomic_write(f, "FRESH\n")
    assert backup is None
    assert f.read_text(encoding="utf-8") == "FRESH\n"


def test_atomic_write_accepts_bytes(tmp_path):
    f = tmp_path / "b.md"
    engine.atomic_write(f, b"\x00\x01raw\n")
    assert f.read_bytes() == b"\x00\x01raw\n"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    f = tmp_path / "f.md"
    engine.atomic_write(f, "content\n")
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_atomic_write_cleans_temp_on_crash(tmp_path, monkeypatch):
    f = tmp_path / "f.md"
    f.write_text("SAFE ORIGINAL\n", encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("simulated crash mid-write")

    # Crash at the atomic rename step, after the temp has been written.
    monkeypatch.setattr(engine.os, "replace", boom)
    with pytest.raises(RuntimeError):
        engine.atomic_write(f, "NEW\n")
    # Original intact (atomic: never a truncated hybrid); no temp left behind.
    assert f.read_text(encoding="utf-8") == "SAFE ORIGINAL\n"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


# --------------------------------------------------------------------------- #
# reconcile_entry() — dispatch, staleness, and the ZERO-DATA-LOSS proof
# --------------------------------------------------------------------------- #
def _deploy(project_root: Path, rel: str, content: str) -> Path:
    p = project_root / "oversight" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_reconcile_no_op_makes_no_write(tmp_path):
    dep = _deploy(tmp_path, "tracking/x.md", "same\n")
    e = _entry(base="h", deployed="h", new="h", path="tracking/x.md")
    res = engine.reconcile_entry(e, project_root=tmp_path)
    assert res.decision == Decision.NO_OP
    assert res.action_taken == "no-op"
    assert not (dep.parent / (dep.name + ".bak")).exists()


def test_reconcile_preserve_keeps_deployed(tmp_path):
    dep = _deploy(tmp_path, "tracking/x.md", "user edited\n")
    e = _entry(
        base="base", deployed="edited", new="base", path="tracking/x.md"
    )  # user_edited, template unchanged
    res = engine.reconcile_entry(e, project_root=tmp_path)
    assert res.decision == Decision.PRESERVE
    assert dep.read_text(encoding="utf-8") == "user edited\n"


def test_reconcile_refresh_overwrites_with_template(tmp_path):
    # A raw refresh is only for a NON-data-bearing (fully installer-owned) file.
    # "INSTALLER_OWNED" is a PLACEHOLDER token: P1's classification taxonomy is not
    # yet formally defined (today P1 emits only MANAGED_MERGE_REQUIRED), so this
    # exercises the defense-in-depth safe-refresh extension point, not a live path.
    dep = _deploy(tmp_path, "tracking/x.md", "old deployed\n")
    template = tmp_path / "new_template.md"
    template.write_text("NEW TEMPLATE\n", encoding="utf-8")
    e = _entry(
        base=engine.compute_hash(dep),  # deployed == base -> user NOT edited
        deployed=engine.compute_hash(dep),
        new=engine.compute_hash(template),  # template changed
        path="tracking/x.md",
        classification="INSTALLER_OWNED",  # placeholder overwrite-safe token
    )
    res = engine.reconcile_entry(e, project_root=tmp_path, new_template_path=template)
    assert res.decision == Decision.REFRESH
    assert res.action_taken == "refreshed"
    assert dep.read_text(encoding="utf-8") == "NEW TEMPLATE\n"
    assert Path(res.backup_path).read_text(encoding="utf-8") == "old deployed\n"


def test_reconcile_refresh_data_bearing_migrates_not_overwrites(tmp_path):
    # F1 defense-in-depth: even in the REFRESH quadrant (deployed == base, template
    # changed), a data-bearing/managed file must migrate STRUCTURE forward and
    # preserve every operator DATA row — NOT be raw-overwritten with the new template.
    dep = _deploy(tmp_path, "bugs/INDEX.md", INDEX_FIXTURE)
    template = tmp_path / "new_template.md"
    template.write_text("BRAND NEW EMPTY TEMPLATE\n", encoding="utf-8")
    e = _entry(
        base=engine.compute_hash(dep),  # deployed == base -> user NOT edited
        deployed=engine.compute_hash(dep),
        new=engine.compute_hash(template),  # template changed -> REFRESH quadrant
        path="bugs/INDEX.md",
        classification="MANAGED_MERGE_REQUIRED",  # data-bearing
    )
    assert engine.classify(e) == Decision.REFRESH  # genuinely the REFRESH quadrant

    res = engine.reconcile_entry(e, project_root=tmp_path, new_template_path=template)

    # Routed to the migrate path: template content is NOT written in.
    assert res.decision == Decision.REFRESH
    assert res.action_taken == "migrated"
    after = dep.read_text(encoding="utf-8")
    assert "BRAND NEW EMPTY TEMPLATE" not in after
    # STRUCTURE advanced; every operator DATA row survives byte-for-byte.
    assert engine.read_format_version(after) == 1
    for row in (
        "BUG-527 — deploy parity — Closed",
        "BUG-528 — marker asymmetry — Open",
        "BUG-529 — adapter refresh — Open",
        "| Open   | 12    |",
        "| Closed | 111   |",
    ):
        assert row in after
    # Backup captured the pre-migration original exactly.
    assert Path(res.backup_path).read_text(encoding="utf-8") == INDEX_FIXTURE


def test_reconcile_conflict_migrates_structure_preserves_data(tmp_path):
    # THE ZERO-DATA-LOSS PROOF: a both-changed data-bearing file reconciles by
    # migrating STRUCTURE (frontmatter format_version stamp) forward while every
    # operator DATA row survives byte-for-byte.
    dep = _deploy(tmp_path, "bugs/INDEX.md", INDEX_FIXTURE)
    e = _entry(
        base="last_shipped",  # non-empty base
        deployed=engine.compute_hash(dep),  # != base -> user edited
        new="new_template",  # != base -> template changed  => CONFLICT
        path="bugs/INDEX.md",
    )
    before_body = _body_after_frontmatter(dep.read_text(encoding="utf-8"))

    res = engine.reconcile_entry(e, project_root=tmp_path)

    assert res.decision == Decision.CONFLICT
    assert res.action_taken == "migrated"
    after = dep.read_text(encoding="utf-8")
    # STRUCTURE advanced: format_version stamped.
    assert engine.read_format_version(after) == 1
    # DATA preserved: body byte-identical (ZERO data loss).
    assert _body_after_frontmatter(after) == before_body
    # Every operator data row survives verbatim.
    for row in (
        "BUG-527 — deploy parity — Closed",
        "BUG-528 — marker asymmetry — Open",
        "BUG-529 — adapter refresh — Open",
        "| Open   | 12    |",
        "| Closed | 111   |",
    ):
        assert row in after
    # Backup captured the pre-migration original exactly.
    assert Path(res.backup_path).read_text(encoding="utf-8") == INDEX_FIXTURE


def test_reconcile_conflict_no_frontmatter_preserves_as_terminal(tmp_path):
    # A both-changed file with no frontmatter: baseline stamp is N/A -> data
    # preserved, clean "preserved" terminal (note 2: not a dead-end).
    plain = "# Decision Log\n\n### DEC-1\nbody\n"
    dep = _deploy(tmp_path, "tracking/decision-log.md", plain)
    e = _entry(
        base="base",
        deployed=engine.compute_hash(dep),
        new="new",
        path="tracking/decision-log.md",
    )
    res = engine.reconcile_entry(e, project_root=tmp_path)
    assert res.decision == Decision.CONFLICT
    assert res.action_taken == "preserved"
    assert dep.read_text(encoding="utf-8") == plain  # byte-identical
    assert res.backup_path is None


def test_reconcile_conflict_idempotent_second_run_is_preserved(tmp_path):
    dep = _deploy(tmp_path, "bugs/INDEX.md", INDEX_FIXTURE)
    e1 = _entry(
        base="b", deployed=engine.compute_hash(dep), new="n", path="bugs/INDEX.md"
    )
    first = engine.reconcile_entry(e1, project_root=tmp_path)
    assert first.action_taken == "migrated"
    # Second pass: file now stamped; a fresh manifest reflects the new deployed hash.
    e2 = _entry(
        base="b", deployed=engine.compute_hash(dep), new="n", path="bugs/INDEX.md"
    )
    second = engine.reconcile_entry(e2, project_root=tmp_path)
    assert second.action_taken == "preserved"  # already current, no re-write


def test_reconcile_refuses_stale_manifest(tmp_path):
    dep = _deploy(tmp_path, "bugs/INDEX.md", INDEX_FIXTURE)
    e = _entry(
        base="b",
        deployed="STALE_HASH_FROM_OLD_MANIFEST",  # != current on-disk hash
        new="n",
        path="bugs/INDEX.md",
    )
    with pytest.raises(engine.StaleManifestError):
        engine.reconcile_entry(e, project_root=tmp_path)
    # Refused before any write: file untouched, no backup created.
    assert dep.read_text(encoding="utf-8") == INDEX_FIXTURE
    assert not (dep.parent / (dep.name + ".bak")).exists()


# --------------------------------------------------------------------------- #
# F2 — backup must NOT follow a symlink at <path>.bak (clobbers an unrelated
# file the operator owns). BP-187 §4: backup-before-write is a safety net, never
# a foot-gun that destroys data elsewhere.
# --------------------------------------------------------------------------- #
def test_atomic_write_backup_does_not_follow_symlink(tmp_path):
    victim = tmp_path / "unrelated_precious.txt"
    victim.write_text("PRECIOUS — MUST SURVIVE\n", encoding="utf-8")
    f = tmp_path / "f.md"
    f.write_text("ORIGINAL\n", encoding="utf-8")
    # A pre-existing symlink sits where the backup would be written.
    bak = Path(str(f) + ".bak")
    bak.symlink_to(victim)

    engine.atomic_write(f, "NEW CONTENT\n")

    # The symlink's target (an unrelated file) is untouched — copy2 default
    # follow_symlinks=True would have clobbered it with f.md's old bytes.
    assert victim.read_text(encoding="utf-8") == "PRECIOUS — MUST SURVIVE\n"
    # The write itself still succeeded.
    assert f.read_text(encoding="utf-8") == "NEW CONTENT\n"


# --------------------------------------------------------------------------- #
# F3 — single-slot .bak must not silently clobber (a) an operator's pre-existing
# sibling .bak or (b) an earlier backup on a 2nd write. BP-187 §4.5.
# --------------------------------------------------------------------------- #
def test_atomic_write_does_not_clobber_preexisting_bak(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("V1\n", encoding="utf-8")
    operator_bak = Path(str(f) + ".bak")
    operator_bak.write_text("OPERATOR'S OWN BACKUP — KEEP\n", encoding="utf-8")

    backup = engine.atomic_write(f, "V2\n")

    # The operator's pre-existing .bak survives untouched.
    assert operator_bak.read_text(encoding="utf-8") == "OPERATOR'S OWN BACKUP — KEEP\n"
    # Our backup went to a collision-safe name (not the operator's .bak).
    assert backup != str(operator_bak)
    assert Path(backup).read_text(encoding="utf-8") == "V1\n"


def test_atomic_write_second_write_does_not_selfclobber_backup(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("V1\n", encoding="utf-8")
    b1 = engine.atomic_write(f, "V2\n")  # backs up V1
    b2 = engine.atomic_write(f, "V3\n")  # backs up V2 — must NOT overwrite b1
    assert b1 != b2
    assert Path(b1).read_text(encoding="utf-8") == "V1\n"
    assert Path(b2).read_text(encoding="utf-8") == "V2\n"


# --------------------------------------------------------------------------- #
# F4 — a leading `---…---` markdown thematic break is NOT YAML frontmatter and
# must never get a format_version stamp injected into operator content.
# --------------------------------------------------------------------------- #
def test_write_format_version_thematic_break_is_not_frontmatter():
    # Opens with a thematic break; the block between the rules is prose, not
    # key: value YAML.
    doc = (
        "---\n"
        "A horizontal rule opens this note, not YAML frontmatter.\n"
        "Just prose describing a decision.\n"
        "---\n"
        "Body content.\n"
    )
    with pytest.raises(engine.CannotStampError):
        engine.write_format_version(doc, 1)


def test_read_format_version_thematic_break_is_zero():
    doc = "---\nnarrative prose, no keys here\n---\nbody\n"
    assert engine.read_format_version(doc) == 0


def test_apply_migrations_thematic_break_not_stamped(tmp_path):
    # Through the real registry: a thematic-break doc is an N/A terminal — it
    # comes out byte-identical, never with format_version injected.
    doc = "---\nHorizontal rule, not frontmatter.\n---\n\nOperator body row.\n"
    out = engine.apply_migrations(doc, engine.CURRENT_FORMAT_VERSION, engine.MIGRATIONS)
    assert out == doc


# --------------------------------------------------------------------------- #
# F5 — the inserted stamp line must match the file's dominant newline; a CRLF
# file must not gain a bare-LF line (mixed endings).
# --------------------------------------------------------------------------- #
def test_write_format_version_preserves_crlf_line_endings():
    crlf = INDEX_FIXTURE.replace("\n", "\r\n")
    stamped = engine.write_format_version(crlf, 1)
    assert engine.read_format_version(stamped) == 1
    # The inserted stamp line carries the file's CRLF ending.
    assert "format_version: 1\r\n" in stamped
    # No lone LF anywhere: every newline is a CRLF pair.
    assert "\n" not in stamped.replace("\r\n", "")
    # Re-stamp (the replace branch) must also keep CRLF.
    restamped = engine.write_format_version(stamped, 2)
    assert "\n" not in restamped.replace("\r\n", "")


# --------------------------------------------------------------------------- #
# F6 — load_manifest wraps parse/entry errors in ReconcileError so callers catch
# one uniform type (fail-loud, no write — just a catchable type).
# --------------------------------------------------------------------------- #
def test_load_manifest_wraps_json_decode_error(tmp_path):
    m = tmp_path / "pending-updates.json"
    m.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(engine.ReconcileError):
        engine.load_manifest(m)


def test_load_manifest_wraps_missing_entry_id(tmp_path):
    m = tmp_path / "pending-updates.json"
    m.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "entries": [
                    {  # no "id" key
                        "path": "oversight/tracking/decision-log.md",
                        "old_shipped_hash": "a",
                        "deployed_hash": "b",
                        "new_template_hash": "c",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(engine.ReconcileError):
        engine.load_manifest(m)
