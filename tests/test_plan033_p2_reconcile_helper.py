"""Tests for the PLAN-033 P2 session-start reconciliation helper.

The helper lives at
``_ai-memory/pov/skills/aim-content-drift/scripts/reconcile_helper.py`` — a skill
script invoked by path — so it is loaded here via ``importlib.util.spec_from_file_location``
(same pattern as tests/test_plan033_p3_reconcile_engine.py). This file lives under
``tests/`` so CI collects it (TD-812: CI only collects ``tests/``).

Focus (the P2 helper DONE-WHEN): the ledger / hash-move re-nag behavior —
  - effective_pending includes never-disposed entries.
  - applied|dismissed at the SAME new_template_hash suppress re-surfacing.
  - a MOVED new_template_hash re-surfaces a previously-disposed entry.
  - deferred re-surfaces (recorded for audit, not suppressed).
  - the one-line rollup format / silence when nothing is pending.
  - `reconcile --disposition applied` invokes the engine and records action_taken+hash.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_HELPER_PATH = (
    Path(__file__).resolve().parent.parent
    / "_ai-memory"
    / "pov"
    / "skills"
    / "aim-content-drift"
    / "scripts"
    / "reconcile_helper.py"
)
_spec = importlib.util.spec_from_file_location("reconcile_helper", _HELPER_PATH)
helper = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = helper
_spec.loader.exec_module(helper)

engine = helper.engine


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _write_manifest(project_root: Path, entries: list[dict]) -> None:
    state = project_root / ".audit" / "state"
    state.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0",
        "generated_at": "2026-07-14T00:00:00Z",
        "generated_by": "test",
        "source_version": "2.8.3",
        "manifest_id": "test-manifest",
        "entries": entries,
    }
    (state / "pending-updates.json").write_text(json.dumps(manifest), encoding="utf-8")


def _entry(
    id_: str, *, base="B", deployed="D", new="S", severity="high", order=0
) -> dict:
    return {
        "id": id_,
        "path": f"oversight/{id_}",
        "classification": "MANAGED_MERGE_REQUIRED",
        "old_shipped_hash": _sha(base),
        "deployed_hash": _sha(deployed),
        "new_template_hash": _sha(new),
        "suggested_action": "merge",
        "rationale": "local + upstream both changed",
        "severity": severity,
        "order": order,
    }


def _load_manifest(project_root: Path):
    return engine.load_manifest(
        project_root / ".audit" / "state" / "pending-updates.json"
    )


# --------------------------------------------------------------------------- #
# effective_pending — re-nag suppression core
# --------------------------------------------------------------------------- #
def test_never_disposed_entry_is_pending(tmp_path):
    _write_manifest(tmp_path, [_entry("tracking/decision-log.md")])
    manifest = _load_manifest(tmp_path)
    pending = helper.effective_pending(manifest, {"dispositions": {}})
    assert [e.id for e in pending] == ["tracking/decision-log.md"]


def test_applied_at_same_hash_is_suppressed(tmp_path):
    e = _entry("bugs/INDEX.md", new="S")
    _write_manifest(tmp_path, [e])
    manifest = _load_manifest(tmp_path)
    ledger = {
        "dispositions": {
            "bugs/INDEX.md": {"disposition": "applied", "new_template_hash": _sha("S")}
        }
    }
    assert helper.effective_pending(manifest, ledger) == []


def test_dismissed_at_same_hash_is_suppressed(tmp_path):
    e = _entry("bugs/INDEX.md", new="S")
    _write_manifest(tmp_path, [e])
    manifest = _load_manifest(tmp_path)
    ledger = {
        "dispositions": {
            "bugs/INDEX.md": {
                "disposition": "dismissed",
                "new_template_hash": _sha("S"),
            }
        }
    }
    assert helper.effective_pending(manifest, ledger) == []


def test_moved_hash_resurfaces_disposed_entry(tmp_path):
    # Manifest now carries a NEW template hash (S2); the recorded disposition was at S1.
    _write_manifest(tmp_path, [_entry("bugs/INDEX.md", new="S2")])
    manifest = _load_manifest(tmp_path)
    ledger = {
        "dispositions": {
            "bugs/INDEX.md": {"disposition": "applied", "new_template_hash": _sha("S1")}
        }
    }
    pending = helper.effective_pending(manifest, ledger)
    assert [e.id for e in pending] == ["bugs/INDEX.md"]


def test_deferred_resurfaces(tmp_path):
    _write_manifest(tmp_path, [_entry("bugs/INDEX.md", new="S")])
    manifest = _load_manifest(tmp_path)
    ledger = {
        "dispositions": {
            "bugs/INDEX.md": {"disposition": "deferred", "new_template_hash": _sha("S")}
        }
    }
    pending = helper.effective_pending(manifest, ledger)
    assert [e.id for e in pending] == ["bugs/INDEX.md"]


def test_severity_ranking(tmp_path):
    _write_manifest(
        tmp_path,
        [
            _entry("a.md", severity="low", order=0),
            _entry("b.md", severity="high", order=1),
            _entry("c.md", severity="medium", order=2),
        ],
    )
    manifest = _load_manifest(tmp_path)
    pending = helper.effective_pending(manifest, {"dispositions": {}})
    assert [e.id for e in pending] == ["b.md", "c.md", "a.md"]


# --------------------------------------------------------------------------- #
# rollup line
# --------------------------------------------------------------------------- #
def test_rollup_line_high_only(tmp_path):
    _write_manifest(tmp_path, [_entry("a.md"), _entry("b.md", order=1)])
    manifest = _load_manifest(tmp_path)
    pending = helper.effective_pending(manifest, {"dispositions": {}})
    assert helper._rollup_line(pending) == "Pending Updates: 2 pending (2 high)"


def test_rollup_line_mixed_severity(tmp_path):
    _write_manifest(
        tmp_path,
        [_entry("a.md", severity="high"), _entry("b.md", severity="medium", order=1)],
    )
    manifest = _load_manifest(tmp_path)
    pending = helper.effective_pending(manifest, {"dispositions": {}})
    assert (
        helper._rollup_line(pending) == "Pending Updates: 2 pending (1 high, 1 medium)"
    )


def test_rollup_line_empty_is_silent():
    assert helper._rollup_line([]) == ""


# --------------------------------------------------------------------------- #
# CLI: pending --format rollup is silent when manifest absent
# --------------------------------------------------------------------------- #
def test_cli_rollup_silent_when_no_manifest(tmp_path, capsys):
    rc = helper.main(["pending", "--project-root", str(tmp_path), "--format", "rollup"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == ""


def test_cli_rollup_emits_line(tmp_path, capsys):
    _write_manifest(tmp_path, [_entry("a.md")])
    rc = helper.main(["pending", "--project-root", str(tmp_path), "--format", "rollup"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == "Pending Updates: 1 pending (1 high)"


def test_cli_pending_json_lists_entries(tmp_path, capsys):
    _write_manifest(tmp_path, [_entry("a.md")])
    rc = helper.main(["pending", "--project-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["by_severity"] == {"high": 1}
    assert payload["entries"][0]["id"] == "a.md"


# --------------------------------------------------------------------------- #
# CLI: reconcile applied invokes engine + records to ledger
# --------------------------------------------------------------------------- #
def _data_bearing_file(project_root: Path, rel: str, body: str) -> Path:
    # A frontmatter-bearing oversight file (no format_version stamp yet) => the engine
    # migrates it forward to v1 (adds the stamp) while preserving the body.
    target = project_root / "oversight" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    content = f"---\ntitle: Decision Log\n---\n{body}\n"
    target.write_text(content, encoding="utf-8")
    return target


def test_reconcile_applied_migrates_and_records(tmp_path, capsys):
    rel = "tracking/decision-log.md"
    target = _data_bearing_file(tmp_path, rel, "DEC-1: keep my data")
    deployed_hash = engine.compute_hash(target)
    # base != deployed and base != new => CONFLICT (both-changed), the production case.
    entry = {
        "id": rel,
        "path": f"oversight/{rel}",
        "classification": "MANAGED_MERGE_REQUIRED",
        "old_shipped_hash": _sha("pristine-base"),
        "deployed_hash": deployed_hash,
        "new_template_hash": _sha("new-template"),
        "suggested_action": "merge",
        "rationale": "both changed",
        "severity": "high",
        "order": 0,
    }
    _write_manifest(tmp_path, [entry])

    rc = helper.main(
        [
            "reconcile",
            "--project-root",
            str(tmp_path),
            "--id",
            rel,
            "--disposition",
            "applied",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "ok"
    assert payload["decision"] == "conflict"
    assert payload["action_taken"] == "migrated"

    # Body preserved, structure migrated forward (stamp added).
    migrated = target.read_text(encoding="utf-8")
    assert "DEC-1: keep my data" in migrated
    assert "format_version: 1" in migrated

    # Ledger records the disposition at the entry's new_template_hash.
    ledger = json.loads(
        (tmp_path / ".audit" / "state" / "reconcile-dispositions.json").read_text()
    )
    rec = ledger["dispositions"][rel]
    assert rec["disposition"] == "applied"
    assert rec["new_template_hash"] == _sha("new-template")
    assert rec["action_taken"] == "migrated"

    # And now the entry is suppressed at that same hash (re-nag off).
    manifest = _load_manifest(tmp_path)
    assert (
        helper.effective_pending(
            manifest,
            helper.load_ledger(
                tmp_path / ".audit" / "state" / "reconcile-dispositions.json"
            ),
        )
        == []
    )


def test_reconcile_dismiss_records_without_engine(tmp_path, capsys):
    rel = "bugs/INDEX.md"
    _write_manifest(tmp_path, [_entry(rel, new="S")])
    rc = helper.main(
        [
            "reconcile",
            "--project-root",
            str(tmp_path),
            "--id",
            rel,
            "--disposition",
            "dismissed",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["disposition"] == "dismissed"
    ledger = json.loads(
        (tmp_path / ".audit" / "state" / "reconcile-dispositions.json").read_text()
    )
    assert ledger["dispositions"][rel]["disposition"] == "dismissed"
    assert ledger["dispositions"][rel]["new_template_hash"] == _sha("S")


# --------------------------------------------------------------------------- #
# CLI: reconcile resolved — PLAN-035 P1 out-of-band stamp escape hatch
# --------------------------------------------------------------------------- #
def test_reconcile_resolved_stamps_without_engine_no_stale_error(
    tmp_path, capsys, monkeypatch
):
    # The operator hand-conformed the file: its current on-disk content matches
    # neither the manifest's recorded `deployed_hash` snapshot. Routing this through
    # `engine.reconcile_entry` would raise StaleManifestError; `resolved` must never
    # call the engine at all.
    rel = "tracking/decision-log.md"
    target = _data_bearing_file(tmp_path, rel, "DEC-1: hand-conformed by operator")
    entry = {
        "id": rel,
        "path": f"oversight/{rel}",
        "classification": "MANAGED_MERGE_REQUIRED",
        "old_shipped_hash": _sha("pristine-base"),
        "deployed_hash": _sha("stale-snapshot-not-the-real-file"),
        "new_template_hash": _sha("new-template"),
        "suggested_action": "merge",
        "rationale": "both changed",
        "severity": "high",
        "order": 0,
    }
    _write_manifest(tmp_path, [entry])

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("resolved must not call engine.reconcile_entry")

    monkeypatch.setattr(engine, "reconcile_entry", _fail_if_called)

    rc = helper.main(
        [
            "reconcile",
            "--project-root",
            str(tmp_path),
            "--id",
            rel,
            "--disposition",
            "resolved",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "ok"
    assert payload["disposition"] == "resolved"
    assert payload["action_taken"] == "stamped-resolved-out-of-band"
    current_hash = engine.compute_hash(target)
    assert payload["resolved_at_hash"] == current_hash

    ledger = json.loads(
        (tmp_path / ".audit" / "state" / "reconcile-dispositions.json").read_text()
    )
    rec = ledger["dispositions"][rel]
    assert rec["disposition"] == "resolved"
    # Suppression stays keyed to the entry's new_template_hash (unchanged semantics).
    assert rec["new_template_hash"] == _sha("new-template")
    # Audit trail captures the actual deployed hash at resolution time, distinct from
    # both the stale manifest snapshot and the suppression key.
    assert rec["resolved_at_hash"] == current_hash
    assert rec["resolved_at_hash"] != entry["deployed_hash"]

    # The operator's hand-conformed content is untouched.
    assert "DEC-1: hand-conformed by operator" in target.read_text(encoding="utf-8")


def test_resolved_suppresses_at_entry_hash_and_resurfaces_on_hash_move(tmp_path):
    rel = "bugs/INDEX.md"
    _write_manifest(tmp_path, [_entry(rel, new="S")])
    manifest = _load_manifest(tmp_path)
    ledger = {
        "dispositions": {
            rel: {"disposition": "resolved", "new_template_hash": _sha("S")}
        }
    }
    assert helper.effective_pending(manifest, ledger) == []

    # A genuinely new upstream template (hash moved) re-surfaces it.
    _write_manifest(tmp_path, [_entry(rel, new="S2")])
    manifest_moved = _load_manifest(tmp_path)
    pending = helper.effective_pending(manifest_moved, ledger)
    assert [e.id for e in pending] == [rel]


def test_is_disposed_resolved_true_at_entry_hash_false_at_moved_hash(tmp_path):
    rel = "tracking/decision-log.md"
    _data_bearing_file(tmp_path, rel, "DEC-2: hand-conformed")
    entry = {
        "id": rel,
        "path": f"oversight/{rel}",
        "classification": "MANAGED_MERGE_REQUIRED",
        "old_shipped_hash": _sha("pristine-base"),
        "deployed_hash": _sha("stale-snapshot"),
        "new_template_hash": _sha("new-template"),
        "suggested_action": "merge",
        "rationale": "both changed",
        "severity": "high",
        "order": 0,
    }
    _write_manifest(tmp_path, [entry])
    helper.main(
        [
            "reconcile",
            "--project-root",
            str(tmp_path),
            "--id",
            rel,
            "--disposition",
            "resolved",
        ]
    )

    rc_same = helper.main(
        [
            "is-disposed",
            "--project-root",
            str(tmp_path),
            "--id",
            rel,
            "--hash",
            _sha("new-template"),
        ]
    )
    assert rc_same == 0

    rc_moved = helper.main(
        [
            "is-disposed",
            "--project-root",
            str(tmp_path),
            "--id",
            rel,
            "--hash",
            _sha("a-later-shipped-template"),
        ]
    )
    assert rc_moved == 1


def test_reconcile_unknown_id_errors(tmp_path, capsys):
    _write_manifest(tmp_path, [_entry("a.md")])
    rc = helper.main(
        [
            "reconcile",
            "--project-root",
            str(tmp_path),
            "--id",
            "nope.md",
            "--disposition",
            "applied",
        ]
    )
    assert rc == 2


# --------------------------------------------------------------------------- #
# CLI: reconcile applied — engine failure must NOT record a false "applied"
# --------------------------------------------------------------------------- #
def test_reconcile_applied_engine_failure_records_no_ledger_entry(
    tmp_path, capsys, monkeypatch
):
    rel = "tracking/decision-log.md"
    target = _data_bearing_file(tmp_path, rel, "DEC-1: keep my data")
    original_content = target.read_text(encoding="utf-8")
    deployed_hash = engine.compute_hash(target)
    entry = {
        "id": rel,
        "path": f"oversight/{rel}",
        "classification": "MANAGED_MERGE_REQUIRED",
        "old_shipped_hash": _sha("pristine-base"),
        "deployed_hash": deployed_hash,
        "new_template_hash": _sha("new-template"),
        "suggested_action": "merge",
        "rationale": "both changed",
        "severity": "high",
        "order": 0,
    }
    _write_manifest(tmp_path, [entry])

    def _raise_stale(*_args, **_kwargs):
        raise engine.StaleManifestError("forced failure for test")

    monkeypatch.setattr(engine, "reconcile_entry", _raise_stale)

    rc = helper.main(
        [
            "reconcile",
            "--project-root",
            str(tmp_path),
            "--id",
            rel,
            "--disposition",
            "applied",
        ]
    )
    assert rc == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "StaleManifestError"

    # No ledger record was written for this entry — no false "applied".
    ledger_path = tmp_path / ".audit" / "state" / "reconcile-dispositions.json"
    assert not ledger_path.exists()

    # The operator's file is untouched.
    assert target.read_text(encoding="utf-8") == original_content


# --------------------------------------------------------------------------- #
# Fail-safe manifest loading — `pending --format rollup` never errors the
# session-start rollup, regardless of what is on disk at the manifest path.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw_manifest", ["[]", "null", "42"])
def test_pending_rollup_silent_on_non_object_manifest(tmp_path, capsys, raw_manifest):
    state = tmp_path / ".audit" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "pending-updates.json").write_text(raw_manifest, encoding="utf-8")
    rc = helper.main(["pending", "--project-root", str(tmp_path), "--format", "rollup"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == ""


def test_pending_rollup_silent_on_unreadable_manifest(tmp_path, capsys):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("chmod 000 has no effect when running as root")
    state = tmp_path / ".audit" / "state"
    state.mkdir(parents=True, exist_ok=True)
    manifest_path = state / "pending-updates.json"
    manifest_path.write_text(
        json.dumps({"schema_version": "1.0", "entries": []}), encoding="utf-8"
    )
    manifest_path.chmod(0o000)
    try:
        rc = helper.main(
            ["pending", "--project-root", str(tmp_path), "--format", "rollup"]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert out == ""
    finally:
        manifest_path.chmod(0o644)


def test_pending_rollup_silent_on_unreadable_ancestor_dir(tmp_path, capsys):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("chmod 000 has no effect when running as root")
    state = tmp_path / ".audit" / "state"
    state.mkdir(parents=True, exist_ok=True)
    manifest_path = state / "pending-updates.json"
    manifest_path.write_text(
        json.dumps({"schema_version": "1.0", "entries": []}), encoding="utf-8"
    )
    state.chmod(0o000)
    try:
        rc = helper.main(
            ["pending", "--project-root", str(tmp_path), "--format", "rollup"]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert out == ""
    finally:
        state.chmod(0o755)


def test_pending_rollup_silent_on_invalid_utf8_manifest(tmp_path, capsys):
    state = tmp_path / ".audit" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "pending-updates.json").write_bytes(b"\xff\xfe\x00invalid")
    rc = helper.main(["pending", "--project-root", str(tmp_path), "--format", "rollup"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == ""
