#!/usr/bin/env python3
"""aim-wiki — engine (deterministic operations only).

The skill runs inside Claude Code: this engine does the DETERMINISTIC work
(project scoping, repo inventory, wiki scaffold, state/content-hash, git-diff,
pointer injection, verification manifest) and hands structured context to the
in-session agent, which does the REASONING (authoring/refreshing pages). The
engine never authors prose and never calls a model or provider.

Subcommands:
    init   [--force]              Prep a fresh wiki: inventory + git summary +
                                  scaffold. Emits the context bundle the agent
                                  authors from. --force overrides existing wiki.
    update                        Prep an incremental refresh: state + git-diff
                                  since last run + no-op (content-hash) check.
    status                        Read-only freshness report. No writes.
    verify                        Emit the verifier manifest (verifier hook):
                                  page citations + dead-path precheck.
    finalize --command init|update
                                  Post-acceptance writes: upsert CLAUDE.md/
                                  AGENTS.md pointer + record run-state.

Common flags: --root PATH (override project root), --json.
Invoked via run-with-env.sh (the AI-memory run-with-env convention).
Exit codes: 0 success (incl. routing messages like wiki-already-exists);
1 usage/system error.
"""

import argparse
import json
import sys
from pathlib import Path

import wiki_common as wc
from wiki_inventory import build_inventory
from wiki_pointer import upsert_pointer
from wiki_verify import build_manifest


def _emit(data: dict, as_json: bool, text_fn) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        text_fn(data)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(root: Path, force: bool, as_json: bool) -> int:
    if wc.wiki_has_content(root) and not force:
        data = {
            "mode": "init",
            "status": "wiki_exists",
            "action": "update",
            "wiki_dir": str(wc.wiki_dir(root)),
            "message": "wiki/ already has content — run `update`, or `init --force` to rebuild.",
        }
        _emit(data, as_json, lambda d: print(d["message"]))
        return 0

    wc.wiki_dir(root).mkdir(parents=True, exist_ok=True)
    data = {
        "mode": "init",
        "status": "ready",
        "root": str(root),
        "project_id": wc.resolve_project_id(root),
        "wiki_dir": str(wc.wiki_dir(root)),
        "state_file": str(wc.state_path(root)),
        "forced": force,
        "inventory": build_inventory(root),
        "git_summary": wc.git_summary(root),
        "next": "Author wiki/quickstart.md first, then section pages, grounding every "
        "claim in the inventory/git evidence. Then run `verify`, then `finalize "
        "--command init`.",
    }

    def _text(d):
        inv = d["inventory"]
        print(f"aim-wiki init — ready ({d['root']})")
        print(f"  project_id : {d['project_id']}")
        print(f"  wiki_dir   : {d['wiki_dir']}")
        print(
            f"  scanned    : {inv['files_scanned']} files"
            + (" (truncated)" if inv["truncated"] else "")
        )
        for bucket in ("docs", "entrypoints", "config", "tests", "schema"):
            print(f"  {bucket:11}: {len(inv[bucket])}")
        print("--- git ---")
        print(d["git_summary"])

    _emit(data, as_json, _text)
    return 0


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def cmd_update(root: Path, as_json: bool) -> int:
    state = wc.read_state(root)
    if state is None:
        data = {
            "mode": "update",
            "status": "no_state" if wc.wiki_has_content(root) else "not_initialized",
            "action": (
                "finalize --command init" if wc.wiki_has_content(root) else "init"
            ),
            "message": (
                "wiki/ exists but has no recorded state — run `finalize --command init` "
                "to establish a baseline."
                if wc.wiki_has_content(root)
                else "no wiki found — run `init` first."
            ),
        }
        _emit(data, as_json, lambda d: print(d["message"]))
        return 0

    changes = wc.git_changed_files(root, state.get("gitHead"))
    current_hash = wc.content_hash(root)
    data = {
        "mode": "update",
        "status": "ready",
        "root": str(root),
        "recorded": {
            "updatedAt": state.get("updatedAt"),
            "gitHead": state.get("gitHead"),
            "contentHash": state.get("contentHash"),
        },
        "current_content_hash": current_hash,
        "wiki_edited_since_record": current_hash != state.get("contentHash"),
        "changes": changes,
        "git_summary": wc.git_summary(root),
        "next": "Build a docs-impact plan (changed source -> page -> edit -> why). Edit "
        "surgically; a no-op is valid if nothing relevant changed. Then run "
        "`verify`, then `finalize --command update`.",
    }

    def _text(d):
        ch = d["changes"]
        print(f"aim-wiki update — ready ({d['root']})")
        print(
            f"  last run : {d['recorded']['updatedAt']}  @ {d['recorded']['gitHead']}"
        )
        if not ch["resolvable"]:
            print("  since    : recorded gitHead unresolvable — full re-review advised")
        print(f"  committed changed files : {len(ch['committed'])}")
        print(f"  uncommitted changes     : {len(ch['uncommitted'])}")
        for f in ch["committed"][:20]:
            print(f"    + {f}")

    _emit(data, as_json, _text)
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def cmd_status(root: Path, as_json: bool) -> int:
    state = wc.read_state(root)
    if state is None:
        data = {
            "mode": "status",
            "status": (
                "not_initialized" if not wc.wiki_has_content(root) else "no_state"
            ),
            "root": str(root),
            "message": (
                "no wiki state recorded — run `init`."
                if not wc.wiki_has_content(root)
                else "wiki/ present but no recorded state — run `finalize --command init`."
            ),
        }
        _emit(data, as_json, lambda d: print(d["message"]))
        return 0

    changes = wc.git_changed_files(root, state.get("gitHead"))
    current_hash = wc.content_hash(root)
    source_drift = len(changes["committed"]) + len(changes["uncommitted"])
    wiki_edited = current_hash != state.get("contentHash")
    resolvable = changes["resolvable"]
    # An unresolvable recorded gitHead (history rewritten / commit gone) means the
    # source-diff could not be computed — never report "current" in that case
    # (mirrors cmd_update's full-re-review advisory).
    if not resolvable:
        status = "unknown"
    elif source_drift or wiki_edited:
        status = "drifted"
    else:
        status = "current"
    data = {
        "mode": "status",
        "status": status,
        "root": str(root),
        "updatedAt": state.get("updatedAt"),
        "gitHead": state.get("gitHead"),
        "resolvable": resolvable,
        "source_changes_since": source_drift,
        "wiki_edited_since_record": wiki_edited,
    }

    def _text(d):
        print(f"aim-wiki status — {d['status']} ({d['root']})")
        print(f"  last run : {d['updatedAt']}  @ {d['gitHead']}")
        if not d["resolvable"]:
            print("  since    : recorded gitHead unresolvable — full re-review advised")
        print(f"  source changes since last run : {d['source_changes_since']}")
        print(f"  wiki edited since last record : {d['wiki_edited_since_record']}")

    _emit(data, as_json, _text)
    return 0


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def cmd_verify(root: Path, as_json: bool) -> int:
    if not wc.wiki_has_content(root):
        data = {
            "mode": "verify",
            "status": "not_initialized",
            "message": "no wiki to verify — run `init` first.",
        }
        _emit(data, as_json, lambda d: print(d["message"]))
        return 0

    manifest = build_manifest(root)
    manifest["mode"] = "verify"
    manifest["status"] = (
        "dead_citations" if manifest["dead_count"] else "citations_resolve"
    )

    def _text(d):
        print(
            f"aim-wiki verify — {d['page_count']} pages, "
            f"{d['citation_count']} source citations, {d['dead_count']} dead"
        )
        for dead in d["dead_citations"]:
            print(f"  DEAD  {dead['page']}  ->  {dead['ref']}")
        print(
            "Now dispatch a read-only verifier subagent with this manifest to check "
            "that each page's CLAIMS match the cited source (grounding, not just "
            "existence). Surface all discrepancies before acceptance."
        )

    _emit(manifest, as_json, _text)
    return 0


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------


def cmd_finalize(root: Path, command: str, as_json: bool) -> int:
    if not wc.wiki_has_content(root):
        data = {
            "mode": "finalize",
            "status": "not_initialized",
            "command": command,
            "root": str(root),
            "message": "no wiki content to finalize — author wiki/ pages first "
            "(run `init`). Pointer + state not written.",
        }
        _emit(data, as_json, lambda d: print(d["message"]))
        return 0
    pointer_changed = upsert_pointer(root)
    head = wc.git_head(root)
    state = wc.write_state(root, command, head)
    data = {
        "mode": "finalize",
        "status": "recorded",
        "command": command,
        "root": str(root),
        "pointer_files_changed": pointer_changed,
        "state": state,
    }

    def _text(d):
        print(f"aim-wiki finalize — recorded ({d['command']})")
        print(f"  gitHead     : {d['state']['gitHead']}")
        print(f"  contentHash : {d['state']['contentHash']}")
        print(f"  updatedAt   : {d['state']['updatedAt']}")
        pc = d["pointer_files_changed"]
        print(f"  pointer     : {', '.join(pc) if pc else 'already current'}")

    _emit(data, as_json, _text)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        metavar="PATH",
        help="Project root override (default: git toplevel, else cwd)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Machine-readable JSON output",
    )

    parser = argparse.ArgumentParser(
        prog="aim_wiki", description="aim-wiki engine (deterministic operations)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", parents=[common], help="Prep a fresh wiki")
    p_init.add_argument(
        "--force", action="store_true", help="Rebuild even if wiki/ already has content"
    )
    sub.add_parser("update", parents=[common], help="Prep an incremental refresh")
    sub.add_parser("status", parents=[common], help="Read-only freshness report")
    sub.add_parser("verify", parents=[common], help="Emit the verifier manifest")
    p_fin = sub.add_parser(
        "finalize", parents=[common], help="Upsert pointer + record run-state"
    )
    p_fin.add_argument(
        "--command",
        choices=("init", "update"),
        required=True,
        help="Which run is being finalized",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = wc.resolve_root(args.root)
    as_json = args.as_json

    if args.cmd == "init":
        return cmd_init(root, args.force, as_json)
    if args.cmd == "update":
        return cmd_update(root, as_json)
    if args.cmd == "status":
        return cmd_status(root, as_json)
    if args.cmd == "verify":
        return cmd_verify(root, as_json)
    if args.cmd == "finalize":
        return cmd_finalize(root, args.command, as_json)
    return 1  # unreachable (subparser required)


if __name__ == "__main__":
    sys.exit(main())
