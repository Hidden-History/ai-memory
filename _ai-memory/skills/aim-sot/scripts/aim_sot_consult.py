#!/usr/bin/env python3
"""
aim-sot consult — read-only query engine over .sot/registry.yaml.

Invoked via run-with-env.sh (Pattern B, BP-013): pyyaml is a venv dep.

Subcommands:
    list                     List all entries (id, kind, owner, sot_location, status)
    get   <id>               Full entry dump
    where <id>               sot_location for the entry
    who   <id>               owner for the entry
    drift <id>               drift_check for the entry
    digest                   Compact ambient summary of all entries + drift rollup

Flags (all subcommands):
    --registry PATH          Override registry path (skip git-root walk)
    --json                   Machine-readable JSON output

Exit codes: 0 = success (incl. no_registry, not-found); 1 = YAML error / system error.
Read-only invariant: this script never opens any file in write mode.

5b-cache seam: _load_entries() is the single insertion point for the
derived memory cache (Item 3). Item 3 inserts a cache lookup before the
file fallback — the function signature must not change.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Sibling import — reuse detect_propose's registry-SHA + 5a drift-cache helpers
# so consult's freshness gate (Item 3) binds to the EXACT definitions the engine
# writes; if the SHA algorithm or 5a cache layout changes, consult tracks it.
# ---------------------------------------------------------------------------

try:
    _DP_SCRIPT = Path(__file__).resolve().parent / "aim_sot_detect_propose.py"
    _dp_spec = importlib.util.spec_from_file_location(
        "aim_sot_detect_propose", _DP_SCRIPT
    )
    _dp = importlib.util.module_from_spec(_dp_spec)
    _dp_spec.loader.exec_module(_dp)

    _registry_sha = _dp._registry_sha
    _read_drift_cache = _dp._read_drift_cache
except Exception:
    # detect_propose absent or broken: degrade gracefully rather than die. consult
    # runs in the default-on SessionStart digest hook, so it must keep serving the
    # committed registry file. With the freshness helpers unavailable, _cache_is_fresh
    # treats the cache as NOT fresh → consult falls back to the committed file.
    _dp = None
    _registry_sha = None
    _read_drift_cache = None

DIGEST_MAX_LINES = 200

# ---------------------------------------------------------------------------
# Registry resolution
# ---------------------------------------------------------------------------


def _find_registry(override: str | None = None) -> Path | None:
    """Locate the .sot/registry.yaml file.

    Resolution order:
    1. --registry PATH override (returned as-is; may not exist).
    2. git root of the current working directory + '.sot/registry.yaml'.
    3. Parent-directory walk from cwd upward (when git is unavailable).

    Returns the resolved Path, or None if the registry cannot be located at all.
    """
    if override is not None:
        return Path(override)

    # Try git root first — the definitive project root.
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_root = Path(result.stdout.strip())
        return git_root / ".sot" / "registry.yaml"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback: walk parent directories when git is unavailable.
    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / ".sot" / "registry.yaml"
        if candidate.exists():
            return candidate

    return None


# ---------------------------------------------------------------------------
# Loading (light structural validation — consult is resilient, not strict)
# ---------------------------------------------------------------------------


def _load_from_file(registry_path: Path) -> list[dict]:
    """Read the registry file with light structural validation.

    Consult is resilient: individual malformed entries are included as-is
    (best-effort orientation). Only two hard failures:
    - Unparseable YAML        → raises yaml.YAMLError
    - 'entries' is not a list → raises ValueError

    Full 16-check schema validation is Item 4's verify mode (spec §5).
    jsonschema is intentionally NOT imported here.
    """
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Registry YAML must be a mapping at the top level")
    entries = raw.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Registry 'entries' key must be a list")
    # Best-effort: silently skip any non-dict items (defensive only).
    return [e for e in entries if isinstance(e, dict)]


def _resolve_project_id_for_cache(registry_path: Path) -> str | None:
    """Resolve project_id for the 5a/5b cache lookup.

    Returns None when the memory stack is unavailable (no install, import
    failure) so the caller falls back to the committed registry file silently.
    """
    try:
        _install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        _src = os.path.join(_install, "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)

        from memory.project import resolve_project_id

        return resolve_project_id(cwd=str(registry_path.parent.parent), warn=False)
    except Exception:
        return None


def _cache_is_fresh(registry_path: Path, project_id: str) -> bool:
    """True iff the 5b cache provably reflects the committed registry.

    The 5a drift cache records the ``registry_sha`` it was last rebuilt from, and
    that field advances only on a successful reindex (detect_propose ``cmd_run``).
    The 5b cache is rebuilt in the same reindex, so a 5a ``registry_sha`` equal to
    the committed registry's SHA is the binding proof the 5b rows are current.

    A mismatch (registry edited since the last reindex) or an absent/unreadable 5a
    cache means the 5b rows may be stale or cross-state — the caller must bypass
    the cache and read the committed file (Item 3 / A1 invariant: consult never
    returns entries that don't match the committed registry).

    When the detect_propose sibling helpers are unavailable (import failed), the
    cache cannot be proven fresh → return False so the caller serves the file.
    """
    if _registry_sha is None or _read_drift_cache is None:
        return False
    committed_sha = _registry_sha(registry_path)
    if not committed_sha:
        return False
    cached_sha = _read_drift_cache(project_id).get("registry_sha", "")
    return bool(cached_sha) and cached_sha == committed_sha


def _try_memory_cache(registry_path: Path, project_id: str) -> list[dict] | None:
    """Try to load registry entries from the 5b derived memory cache.

    Returns a list of entry dicts on success, or None if the store is
    unreachable or the cache is empty. The caller falls back to the committed
    registry file silently. ``project_id`` is resolved by the caller (and the
    freshness gate applied) before this is invoked.
    """
    try:
        _install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        _src = os.path.join(_install, "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        from memory.config import COLLECTION_CONVENTIONS, get_config
        from memory.qdrant_client import get_qdrant_client

        config = get_config()
        client = get_qdrant_client(config)

        entries: list[dict] = []
        offset = None
        while True:
            points, next_offset = client.scroll(
                collection_name=COLLECTION_CONVENTIONS,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="group_id", match=MatchValue(value=project_id)
                        ),
                        FieldCondition(key="type", match=MatchValue(value="sot_entry")),
                    ]
                ),
                limit=100,
                offset=offset,
                with_payload=True,
            )
            for pt in points:
                if pt.payload:
                    try:
                        parsed = json.loads(pt.payload.get("content", "{}"))
                        if isinstance(parsed, dict):
                            entries.append(parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass
            if next_offset is None:
                break
            offset = next_offset

        return entries if entries else None
    except Exception:
        return None


def _load_entries(registry_path: Path) -> list[dict]:
    """Load registry entries for query.

    Use the 5b derived memory cache (fast, agent-searchable, carries enriched
    fields like ``drift_status``) ONLY when it provably reflects the committed
    registry — i.e. the 5a cache's ``registry_sha`` matches the committed file's
    SHA (A1 freshness gate). Otherwise fall back to the committed registry file
    so consult never returns stale or cross-state entries (the cache-first read
    previously shadowed the file after any registry edit).
    Signature must not change (spec §4, Item 3 seam).
    """
    project_id = _resolve_project_id_for_cache(registry_path)
    if project_id and _cache_is_fresh(registry_path, project_id):
        cached = _try_memory_cache(registry_path, project_id)
        if cached is not None:
            return cached
    # --- fallback: committed registry (cache stale, empty, or unavailable) ---
    return _load_from_file(registry_path)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _emit_json(data: dict) -> None:
    print(json.dumps(data))


def _no_registry(path: Path | None, as_json: bool) -> int:
    """Emit no-registry message, return exit code 0."""
    loc = f" at {path}" if path is not None else ""
    msg = f"No registry found{loc}. Run aim-sot detect-propose to create one."
    if as_json:
        _emit_json({"error": "no_registry", "message": msg})
    else:
        print(msg)
    return 0


def _bad_yaml(err: str, as_json: bool) -> int:
    """Emit YAML parse error, return exit code 1."""
    msg = f"Registry is not valid YAML: {err}"
    if as_json:
        _emit_json({"error": "invalid_registry", "message": msg, "details": err})
    else:
        print(msg, file=sys.stderr)
    return 1


def _not_found(entry_id: str, as_json: bool) -> None:
    """Print a not-found result. Consistent across all subcommands."""
    if as_json:
        _emit_json({"found": False, "id": entry_id})
    else:
        print(f"not found: {entry_id}")


# ---------------------------------------------------------------------------
# Entry lookup
# ---------------------------------------------------------------------------


def _lookup(entries: list[dict], entry_id: str) -> dict | None:
    """Return the first entry whose 'id' matches, or None."""
    for e in entries:
        if e.get("id") == entry_id:
            return e
    return None


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_list(entries: list[dict], as_json: bool) -> int:
    if as_json:
        summary = [
            {
                "id": e.get("id"),
                "kind": e.get("kind"),
                "owner": e.get("owner"),
                "sot_location": e.get("sot_location"),
                "status": e.get("status"),
            }
            for e in entries
        ]
        _emit_json({"entries": summary, "count": len(summary)})
    else:
        if not entries:
            print("(no entries)")
        for e in entries:
            eid = e.get("id", "(no id)")
            kind = e.get("kind", "?")
            owner = e.get("owner", "?")
            loc = e.get("sot_location", "?")
            print(f"[{eid}]  {kind} · {owner}  →  {loc}")
    return 0


def cmd_get(entries: list[dict], entry_id: str, as_json: bool) -> int:
    entry = _lookup(entries, entry_id)
    if entry is None:
        _not_found(entry_id, as_json)
        return 0
    if as_json:
        _emit_json({"found": True, "entry": entry})
    else:
        for k, v in entry.items():
            print(f"{k}: {v}")
    return 0


def cmd_digest(entries: list[dict], as_json: bool) -> int:
    # Drift rollup — pure dict inspection, no engine calls.
    # drift_status enum (detect_propose.py): clean | drifted | missing | unverified.
    # Absent drift_status (file-only registry, engine never ran) = indeterminate,
    # counted in the unverified bucket alongside the explicit "unverified" value.
    stale = sum(1 for e in entries if e.get("drift_status") in ("drifted", "missing"))
    clean = sum(1 for e in entries if e.get("drift_status") == "clean")
    unverified = len(entries) - clean - stale

    if stale > 0:
        drift_label = f"{stale} stale"
    elif clean > 0:
        drift_label = "clean"
    else:
        drift_label = "unverified"

    lines = [
        f"[{e.get('id', '(no id)')}]  {e.get('kind', '?')} · {e.get('owner', '?')}  →  {e.get('sot_location', '?')}"
        for e in entries
    ]
    truncated = len(lines) > DIGEST_MAX_LINES

    if as_json:
        _emit_json(
            {
                "digest": lines[:DIGEST_MAX_LINES] if truncated else lines,
                "count": len(entries),
                "drift": {"clean": clean, "stale": stale, "unverified": unverified},
                "truncated": truncated,
            }
        )
        return 0

    # Text mode — emit nothing for empty registry (no-noise per BP-035).
    if not entries:
        return 0

    if truncated:
        print(
            f"SOT registry: {len(entries)} components"
            f" (digest truncated — exceeds {DIGEST_MAX_LINES} lines)"
        )
        print(f"drift: {drift_label}")
        print("Run 'aim-sot consult list' for the full set.")
    else:
        for line in lines:
            print(line)
        print(f"drift: {drift_label}")

    return 0


def cmd_field(entries: list[dict], entry_id: str, field: str, as_json: bool) -> int:
    """Shared handler for where / who / drift — single-field lookup."""
    entry = _lookup(entries, entry_id)
    if entry is None:
        _not_found(entry_id, as_json)
        return 0
    value = entry.get(field)
    if as_json:
        _emit_json({"id": entry_id, "found": True, "field": field, "value": value})
    else:
        if value is None:
            display = "(none configured)" if field == "drift_check" else "(not set)"
        else:
            display = str(value)
        print(f"{entry_id} → {display}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    # Shared options live on the subcommands (post-subcommand ordering),
    # consistent with detect-propose/verify and the SKILL.md example.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--registry",
        metavar="PATH",
        help="Explicit path to registry.yaml (skips git-root walk)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Machine-readable JSON output",
    )

    parser = argparse.ArgumentParser(
        prog="aim_sot_consult",
        description="Read-only query engine over .sot/registry.yaml",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all entries", parents=[common])
    for name in ("get", "where", "who", "drift"):
        p = sub.add_parser(name, parents=[common])
        p.add_argument("id", help="Entry id")
    sub.add_parser(
        "digest", help="Compact ambient summary + drift rollup", parents=[common]
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    as_json: bool = args.as_json

    # --- Resolve registry ---
    registry_path = _find_registry(args.registry)

    if registry_path is None:
        return _no_registry(None, as_json)

    if not registry_path.exists():
        return _no_registry(registry_path, as_json)

    # --- Load ---
    try:
        entries = _load_entries(registry_path)
    except yaml.YAMLError as exc:
        return _bad_yaml(str(exc), as_json)
    except ValueError as exc:
        return _bad_yaml(str(exc), as_json)

    # --- Dispatch ---
    cmd = args.cmd
    if cmd == "list":
        return cmd_list(entries, as_json)
    if cmd == "get":
        return cmd_get(entries, args.id, as_json)
    if cmd == "where":
        return cmd_field(entries, args.id, "sot_location", as_json)
    if cmd == "who":
        return cmd_field(entries, args.id, "owner", as_json)
    if cmd == "drift":
        return cmd_field(entries, args.id, "drift_check", as_json)
    if cmd == "digest":
        return cmd_digest(entries, as_json)

    return 0  # unreachable


if __name__ == "__main__":
    sys.exit(main())
