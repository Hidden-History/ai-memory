#!/usr/bin/env python3
"""aim-wiki — shared deterministic helpers.

Project/root resolution, wiki-dir layout, run-state (content-hash + gitHead +
updatedAt), and git evidence. Pure stdlib — no external deps, so the engine runs
under any Python without run-with-env's venv (though it is invoked via
run-with-env.sh per the AI-memory run-with-env convention).

Multi-project scoping: the wiki is written ONLY under <project_root>/wiki/, and
the root is resolved from the current git toplevel (or an explicit --root). No
cross-project bleed — the engine never touches another project's tree.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WIKI_DIRNAME = "wiki"
STATE_FILENAME = ".last-update.json"
PLAN_FILENAME = "_plan.md"
# Files under wiki/ that are transient/metadata and must not count toward the
# content hash (mirrors upstream createOpenWikiContentSnapshot excluding the
# metadata file; _plan.md is the temporary plan the agent deletes before finish).
_HASH_EXCLUDE = {STATE_FILENAME, PLAN_FILENAME}

_GIT_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Root + project scoping
# ---------------------------------------------------------------------------


def resolve_root(override: str | None = None) -> Path:
    """Resolve the project root.

    1. --root override (returned as-is; may not exist).
    2. git toplevel of the current working directory.
    3. Fallback: the current working directory.
    """
    if override is not None:
        return Path(override)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_GIT_TIMEOUT,
        )
        return Path(result.stdout.strip())
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return Path.cwd()


def resolve_project_id(root: Path) -> str | None:
    """Best-effort AI-memory project id (for status display + the deferred
    memory-store seam). Degrades to None when the memory stack is unavailable —
    scoping is guaranteed by the resolved root, not by this id.
    """
    try:
        install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        src = os.path.join(install, "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from memory.project import resolve_project_id as _rpi  # type: ignore

        return _rpi(cwd=str(root), warn=False)
    except Exception:
        return None


def wiki_dir(root: Path) -> Path:
    return root / WIKI_DIRNAME


def state_path(root: Path) -> Path:
    return wiki_dir(root) / STATE_FILENAME


def wiki_has_content(root: Path) -> bool:
    """True when wiki/ holds any authored markdown page (ignoring state + plan)."""
    wd = wiki_dir(root)
    if not wd.is_dir():
        return False
    return any(p.name not in _HASH_EXCLUDE for p in wd.rglob("*.md"))


# ---------------------------------------------------------------------------
# Content hash + run-state
# ---------------------------------------------------------------------------


def content_hash(root: Path) -> str:
    """sha256 over the wiki's authored content: sorted (relpath, bytes), the
    metadata + plan files excluded. Stable across runs when nothing changed —
    this is the no-op detector (an update that changes nothing keeps the hash).
    """
    wd = wiki_dir(root)
    h = hashlib.sha256()
    if not wd.is_dir():
        return h.hexdigest()
    files = sorted(
        (p for p in wd.rglob("*") if p.is_file() and p.name not in _HASH_EXCLUDE),
        key=lambda p: p.relative_to(wd).as_posix(),
    )
    for p in files:
        rel = p.relative_to(wd).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def read_state(root: Path) -> dict | None:
    """Read wiki/.last-update.json, or None when absent/unparseable."""
    sp = state_path(root)
    if not sp.exists():
        return None
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def write_state(root: Path, command: str, git_head: str | None) -> dict:
    """Write run-state after acceptance: updatedAt, command, gitHead, contentHash.

    No `model` field (unlike upstream): Claude Code is the model — there is no
    provider to record in v1.
    """
    wiki_dir(root).mkdir(parents=True, exist_ok=True)
    state = {
        "updatedAt": _now_iso(),
        "command": command,
        "gitHead": git_head,
        "contentHash": content_hash(root),
    }
    state_path(root).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Git evidence
# ---------------------------------------------------------------------------


def _git(root: Path, args: list[str]) -> str | None:
    """Run a git command at root; return stripped stdout, or None on any failure
    (not a git repo, git absent, timeout)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=_GIT_TIMEOUT,
        )
        return result.stdout.strip()
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return None


def git_head(root: Path) -> str | None:
    return _git(root, ["rev-parse", "HEAD"])


def is_git_repo(root: Path) -> bool:
    return _git(root, ["rev-parse", "--is-inside-work-tree"]) == "true"


def git_summary(root: Path, n: int = 20) -> str:
    """Recent-history summary for init grounding: branch + last n commits.
    Empty string when the project is not a git repo."""
    if not is_git_repo(root):
        return "(not a git repository — no git history available)"
    branch = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "(unknown)"
    log = _git(root, ["log", "--oneline", "-n", str(n)]) or "(no commits)"
    return f"branch: {branch}\nrecent commits:\n{log}"


def _is_wiki_managed(path: str) -> bool:
    """True for paths the wiki flow owns — the wiki dir itself and the pointer
    files. These are excluded from the SOURCE-drift signal: editing the docs (or
    the pointer) is not the source changing out from under the docs.

    Known v1 limitation: this excludes the WHOLE top-level CLAUDE.md/AGENTS.md,
    not just the injected `## Project Wiki` pointer section — so unrelated edits to
    those files don't register as source drift. Pointer-section-scoped drift is a
    v2 refinement.
    """
    return (
        path == "CLAUDE.md"
        or path == "AGENTS.md"
        or path.startswith(WIKI_DIRNAME + "/")
    )


def git_changed_files(root: Path, since_head: str | None) -> dict:
    """Source files changed since the recorded gitHead + any uncommitted source
    changes (wiki-managed paths excluded — see _is_wiki_managed).

    Returns {"since": <head or None>, "committed": [...], "uncommitted": [...],
    "resolvable": bool}. `resolvable` is False when since_head is missing or no
    longer resolves (e.g. history rewritten) — the caller then treats the update
    as a full re-review rather than an incremental diff.
    """
    committed: list[str] = []
    resolvable = False
    if (
        since_head
        and _git(root, ["cat-file", "-e", f"{since_head}^{{commit}}"]) is not None
    ):
        resolvable = True
        # `-c core.quotePath=false` keeps non-ASCII paths literal (UTF-8) instead
        # of octal-escaped + double-quoted, so they parse unmangled.
        diff = _git(
            root,
            [
                "-c",
                "core.quotePath=false",
                "diff",
                "--name-only",
                f"{since_head}..HEAD",
            ],
        )
        committed = [
            ln for ln in (diff or "").splitlines() if ln and not _is_wiki_managed(ln)
        ]
    porcelain = (
        _git(root, ["-c", "core.quotePath=false", "status", "--porcelain"]) or ""
    )
    uncommitted = []
    for ln in porcelain.splitlines():
        # Robust parse: the path is the token after the XY status code, regardless
        # of the code's leading-space alignment (which _git's strip() can eat on
        # the first line). Renames are "ORIG -> NEW" — keep NEW.
        parts = ln.split(None, 1)
        if len(parts) < 2:
            continue
        path = parts[1]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not _is_wiki_managed(path):
            uncommitted.append(path)
    return {
        "since": since_head,
        "committed": committed,
        "uncommitted": uncommitted,
        "resolvable": resolvable,
    }
