#!/usr/bin/env python3
"""Session-start reconciliation helper (PLAN-033 P2 — the consumer seam).

Thin orchestration wrapper the Parzival session-start step-files invoke BY PATH,
keeping those step-files as thin prose (W-07 skills-with-scripts, mirrors how the
sibling ``reconcile_engine.py`` is invoked). It owns the two mechanics the step-files
must NOT re-implement in markdown:

1. **Effective-pending filtering with hash-move re-nag suppression.** Reads the frozen
   ``pending-updates.json`` manifest (P1 producer) and the disposition ledger, and
   returns only entries the operator still needs to see — an entry with a *terminal*
   disposition (``applied`` / ``dismissed``) recorded at the SAME ``new_template_hash``
   is suppressed; it re-surfaces only when that hash MOVES (a genuinely new upstream
   template), never on a "shown-before" flag. A ``deferred`` entry is recorded for
   audit but re-surfaces next session (defer == "ask me later", not "stop asking").

2. **Apply-and-record.** For an approved entry it invokes the data-safety-critical
   ``reconcile_engine.reconcile_entry`` and records the disposition + the engine's
   ``action_taken`` / ``backup_path`` to the ledger atomically — so a disposition is
   never recorded for a reconcile that did not actually complete.

This module does NOT change ``reconcile_engine.py`` (P3) or the manifest producer (P1);
it composes them. It is fail-safe for the ambient surface: a missing or unparseable
manifest yields an empty result (a silent rollup), never a session-start error.

Ledger: ``<project-root>/.audit/state/reconcile-dispositions.json`` (sibling to the
manifest). Manifest: ``<project-root>/.audit/state/pending-updates.json``.
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import sys
from pathlib import Path

# Load the sibling engine by file location (skill scripts are invoked by path, not
# importable as a package — mirrors tests/test_plan033_p3_reconcile_engine.py).
_ENGINE_PATH = Path(__file__).resolve().parent / "reconcile_engine.py"
_spec = importlib.util.spec_from_file_location("reconcile_engine", _ENGINE_PATH)
engine = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = engine
_spec.loader.exec_module(engine)

LEDGER_SCHEMA_VERSION = "1.0"

# Terminal dispositions suppress re-surfacing until new_template_hash moves. A
# "deferred" entry re-surfaces next session (it is recorded only for audit history).
_TERMINAL_DISPOSITIONS = frozenset({"applied", "dismissed"})
_VALID_DISPOSITIONS = frozenset({"applied", "deferred", "dismissed"})

# Severity rank for presentation ordering (lower = surfaced first). Unknown severities
# sort last but are still shown — never silently dropped.
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_UNKNOWN_SEVERITY_RANK = 99


def _manifest_path(project_root: Path) -> Path:
    return project_root / ".audit" / "state" / "pending-updates.json"


def _ledger_path(project_root: Path) -> Path:
    return project_root / ".audit" / "state" / "reconcile-dispositions.json"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Ledger read/write.
# --------------------------------------------------------------------------- #
def load_ledger(path: Path) -> dict:
    """Read the disposition ledger, returning an empty structure if absent/corrupt.

    Fail-safe: a corrupt ledger must not brick the ambient surface. An unreadable
    ledger is treated as "no dispositions recorded" (every entry re-surfaces) — the
    conservative direction (show, never silently suppress).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    dispositions = data.get("dispositions")
    if not isinstance(dispositions, dict):
        dispositions = {}
    data["dispositions"] = dispositions
    return data


def write_ledger(path: Path, ledger: dict) -> None:
    """Persist the ledger crash-atomically (temp -> fsync -> same-dir rename, no .bak).

    Reuses the engine's proven ``atomic_write`` with ``backup=False`` — a state file
    does not want a ``.bak`` sibling on every write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    engine.atomic_write(path, payload, backup=False)


def _is_suppressed(entry, ledger: dict) -> bool:
    """True if a terminal disposition was recorded at the entry's current hash."""
    record = ledger.get("dispositions", {}).get(entry.id)
    if not isinstance(record, dict):
        return False
    if record.get("disposition") not in _TERMINAL_DISPOSITIONS:
        return False
    return record.get("new_template_hash") == entry.new_template_hash


def _severity_sort_key(entry):
    return (_SEVERITY_RANK.get(entry.severity, _UNKNOWN_SEVERITY_RANK), entry.order)


def effective_pending(manifest, ledger: dict) -> list:
    """Manifest entries the operator still needs to see, severity-ranked.

    Drops entries with a terminal disposition recorded at the same hash (re-nag
    suppression); keeps everything else (never-disposed, deferred, or hash-moved).
    """
    pending = [e for e in manifest.entries if not _is_suppressed(e, ledger)]
    return sorted(pending, key=_severity_sort_key)


def _load_manifest_safe(path: Path):
    """Load the manifest, returning None if absent or unparseable (silent rollup)."""
    try:
        if not path.exists():
            return None
        return engine.load_manifest(path)
    except (
        engine.ReconcileError,
        AttributeError,
        TypeError,
        OSError,
        UnicodeDecodeError,
    ) as exc:
        sys.stderr.write(
            f"pending-updates: manifest unreadable, treating as empty: {exc}\n"
        )
        return None


# --------------------------------------------------------------------------- #
# `pending` — effective-pending summary + list (step-02 rollup / step-03 list).
# --------------------------------------------------------------------------- #
def _severity_tally(entries) -> dict:
    tally: dict[str, int] = {}
    for e in entries:
        tally[e.severity] = tally.get(e.severity, 0) + 1
    return tally


def _rollup_line(entries) -> str:
    """One-line ambient rollup, or "" when nothing is pending (=> silent)."""
    if not entries:
        return ""
    tally = _severity_tally(entries)
    ordered = sorted(
        tally.items(),
        key=lambda kv: (_SEVERITY_RANK.get(kv[0], _UNKNOWN_SEVERITY_RANK), kv[0]),
    )
    parts = ", ".join(f"{n} {sev}" for sev, n in ordered)
    return f"Pending Updates: {len(entries)} pending ({parts})"


def cmd_pending(args) -> int:
    project_root = Path(args.project_root)
    manifest = _load_manifest_safe(_manifest_path(project_root))
    ledger = load_ledger(_ledger_path(project_root))
    entries = effective_pending(manifest, ledger) if manifest else []

    if args.format == "rollup":
        line = _rollup_line(entries)
        if line:
            print(line)
        return 0

    result = {
        "summary": {
            "total": len(entries),
            "by_severity": _severity_tally(entries),
            "manifest_id": manifest.manifest_id if manifest else None,
        },
        "entries": [
            {
                "id": e.id,
                "path": e.path,
                "severity": e.severity,
                "classification": e.classification,
                "suggested_action": e.suggested_action,
                "rationale": e.rationale,
                "new_template_hash": e.new_template_hash,
                "order": e.order,
            }
            for e in entries
        ],
    }
    print(json.dumps(result, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# `reconcile` — apply/defer/dismiss one entry, record atomically.
# --------------------------------------------------------------------------- #
def _record_disposition(
    ledger: dict,
    entry,
    disposition: str,
    *,
    action_taken=None,
    decision=None,
    backup_path=None,
) -> None:
    ledger.setdefault("dispositions", {})[entry.id] = {
        "disposition": disposition,
        "new_template_hash": entry.new_template_hash,
        "decision": decision,
        "action_taken": action_taken,
        "backup_path": backup_path,
        "recorded_at": _now(),
    }
    ledger["schema_version"] = LEDGER_SCHEMA_VERSION
    ledger["updated_at"] = _now()


def cmd_reconcile(args) -> int:
    project_root = Path(args.project_root)
    disposition = args.disposition
    if disposition not in _VALID_DISPOSITIONS:
        print(
            json.dumps(
                {"status": "error", "message": f"invalid disposition: {disposition}"}
            ),
            file=sys.stderr,
        )
        return 2

    manifest = _load_manifest_safe(_manifest_path(project_root))
    if manifest is None:
        print(
            json.dumps({"status": "error", "message": "no manifest to reconcile"}),
            file=sys.stderr,
        )
        return 2

    entry = next((e for e in manifest.entries if e.id == args.id), None)
    if entry is None:
        print(
            json.dumps({"status": "error", "message": f"entry not found: {args.id}"}),
            file=sys.stderr,
        )
        return 2

    ledger_path = _ledger_path(project_root)
    ledger = load_ledger(ledger_path)

    if disposition != "applied":
        # defer / dismiss: no engine write; record disposition only.
        _record_disposition(ledger, entry, disposition)
        write_ledger(ledger_path, ledger)
        print(
            json.dumps(
                {"status": "ok", "id": entry.id, "disposition": disposition}, indent=2
            )
        )
        return 0

    # applied: run the engine, then record atomically (record only on success).
    try:
        result = engine.reconcile_entry(entry, project_root=project_root)
    except engine.ReconcileError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "id": entry.id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    _record_disposition(
        ledger,
        entry,
        "applied",
        action_taken=result.action_taken,
        decision=result.decision.value,
        backup_path=result.backup_path,
    )
    write_ledger(ledger_path, ledger)
    print(
        json.dumps(
            {
                "status": "ok",
                "id": entry.id,
                "disposition": "applied",
                "decision": result.decision.value,
                "action_taken": result.action_taken,
                "backup_path": result.backup_path,
            },
            indent=2,
        )
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="PLAN-033 P2 session-start reconciliation helper (manifest + ledger)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_pending = sub.add_parser("pending", help="list effective-pending entries")
    p_pending.add_argument("--project-root", required=True)
    p_pending.add_argument("--format", choices=["json", "rollup"], default="json")
    p_pending.set_defaults(func=cmd_pending)

    p_reconcile = sub.add_parser("reconcile", help="apply/defer/dismiss one entry")
    p_reconcile.add_argument("--project-root", required=True)
    p_reconcile.add_argument("--id", required=True)
    p_reconcile.add_argument(
        "--disposition", required=True, choices=sorted(_VALID_DISPOSITIONS)
    )
    p_reconcile.set_defaults(func=cmd_reconcile)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
