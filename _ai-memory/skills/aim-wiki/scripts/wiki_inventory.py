#!/usr/bin/env python3
"""aim-wiki — deterministic repository inventory.

A bounded, heuristic scan that classifies a project's files into the buckets an
init run needs as grounding (existing docs, entrypoints, config, tests, schema).
Deterministic work only — the in-session agent does the reasoning over this
inventory; the engine never authors prose.
"""

import re
from pathlib import Path

# Directories never worth walking (caches, deps, build output, VCS, the wiki
# itself). Matched by directory name at any depth.
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "dist",
    "build",
    "out",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".nuxt",
    ".cache",
    "coverage",
    ".idea",
    ".vscode",
    "vendor",
    "wiki",
}

# Bound the walk so a huge repo can't stall the scan (Stop-hook-safe posture,
# mirrors aim-sot's discovery budgets). Truncation is reported, never silent.
_MAX_FILES = 20000

_ENTRYPOINT_NAMES = {
    "main.py",
    "__main__.py",
    "cli.py",
    "app.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "index.js",
    "index.ts",
    "index.tsx",
    "cli.ts",
    "cli.tsx",
    "server.js",
    "server.ts",
    "main.go",
    "main.rs",
    "main.c",
    "main.cpp",
    "Main.java",
}
_ENTRYPOINT_RE = re.compile(
    r"^(main|index|cli|app|server|entrypoint)\.[a-z0-9]+$", re.I
)

_CONFIG_NAMES = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    "cargo.toml",
    "go.mod",
    "tsconfig.json",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "makefile",
    "pnpm-workspace.yaml",
    "pom.xml",
    "build.gradle",
}
_CONFIG_EXT = {".toml", ".ini", ".cfg"}

_DOC_NAMES = {
    "readme",
    "changelog",
    "contributing",
    "agents",
    "claude",
    "skill",
    "license",
}

_SCHEMA_EXT = {".sql", ".prisma", ".graphql", ".gql"}
_SCHEMA_NAME_RE = re.compile(r"^(schema|openapi|swagger)\b", re.I)

_TEST_PATH_RE = re.compile(r"(^|/)(tests?|spec|__tests__)(/|$)", re.I)
_TEST_FILE_RE = re.compile(
    r"(^test_.*\.py$|.*_test\.(py|go|rb)$|.*\.(test|spec)\.(ts|tsx|js|jsx)$)", re.I
)

_PER_BUCKET_CAP = 60


def _classify(rel: str, name: str) -> str | None:
    """Return the bucket for a file, or None if it isn't inventory-notable.
    First match wins in priority order: config, entrypoint, schema, tests, docs.
    """
    lname = name.lower()
    stem = lname.rsplit(".", 1)[0]
    ext = ("." + lname.rsplit(".", 1)[1]) if "." in lname else ""

    if lname in _CONFIG_NAMES or (ext in _CONFIG_EXT and "/" not in rel):
        return "config"
    if ".github/workflows/" in rel:
        return "config"
    if lname in _ENTRYPOINT_NAMES or _ENTRYPOINT_RE.match(name):
        return "entrypoints"
    if (
        ext in _SCHEMA_EXT
        or _SCHEMA_NAME_RE.match(name)
        or "/migrations/" in ("/" + rel)
    ):
        return "schema"
    if _TEST_PATH_RE.search(rel) or _TEST_FILE_RE.match(name):
        return "tests"
    if stem in _DOC_NAMES or (
        ext == ".md" and (rel.startswith("docs/") or "/docs/" in rel)
    ):
        return "docs"
    if ext == ".md" and "/" not in rel:  # top-level markdown = doc
        return "docs"
    return None


def build_inventory(root: Path) -> dict:
    """Walk the project (bounded, excludes applied) and bucket notable files.

    Returns a dict with per-bucket file lists (capped), top-level directories,
    the total files scanned, and a `truncated` flag when the walk hit the cap.
    """
    buckets: dict[str, list[str]] = {
        "docs": [],
        "entrypoints": [],
        "config": [],
        "tests": [],
        "schema": [],
    }
    top_dirs: list[str] = []
    scanned = 0
    truncated = False

    for child in sorted(root.iterdir() if root.is_dir() else []):
        if child.is_dir() and child.name not in _SKIP_DIRS:
            top_dirs.append(child.name + "/")

    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS:
                    stack.append(entry)
                continue
            scanned += 1
            if scanned > _MAX_FILES:
                truncated = True
                break
            rel = entry.relative_to(root).as_posix()
            bucket = _classify(rel, entry.name)
            if bucket and len(buckets[bucket]) < _PER_BUCKET_CAP:
                buckets[bucket].append(rel)
        if truncated:
            break

    return {
        "root": str(root),
        "top_level_dirs": top_dirs,
        "files_scanned": scanned,
        "truncated": truncated,
        **buckets,
    }
