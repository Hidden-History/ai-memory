#!/usr/bin/env python3
"""aim-wiki — verification manifest (correctness verifier, deterministic hook).

This is the plumbing for the read-only verifier pass, NOT the verification
itself. It scans the authored wiki pages, extracts every inline source citation
(markdown links to repo files + backtick-wrapped path tokens), and resolves each
against the project tree — a cheap deterministic "does the cited file even
exist" precheck. Dead citations are immediate, unambiguous drift.

The emitted manifest is what the in-session read-only verifier subagent consumes
to do the semantic claims-vs-source check (a page claim grounded in a real file
may still misdescribe it — that judgement is the agent's, not the engine's).
"""

import re
from pathlib import Path

from wiki_common import WIKI_DIRNAME, wiki_dir

# Markdown link target: [text](target). Captured target is trimmed of a #anchor.
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Known source-ish file extensions. A backtick token is treated as a source
# citation only when its basename ends in one of these — otherwise prose like
# `array.map` or `TCP/IP` would masquerade as a dead citation.
_SOURCE_EXTS = {
    "py",
    "js",
    "ts",
    "jsx",
    "tsx",
    "mjs",
    "cjs",
    "go",
    "rs",
    "rb",
    "java",
    "kt",
    "kts",
    "c",
    "h",
    "cpp",
    "hpp",
    "cc",
    "cs",
    "php",
    "swift",
    "scala",
    "sh",
    "bash",
    "zsh",
    "sql",
    "md",
    "rst",
    "txt",
    "json",
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "conf",
    "xml",
    "html",
    "htm",
    "css",
    "scss",
    "less",
    "lock",
    "gradle",
    "proto",
    "graphql",
    "vue",
    "svelte",
    "pl",
    "lua",
}
# Backtick-wrapped path-like token, e.g. `src/app.py` or `pkg/mod.ts:42`. The
# known-extension gate is applied in _looks_like_source, not the regex.
_CODE_PATH_RE = re.compile(r"`([A-Za-z0-9_./-]+(?::\d+(?:-\d+)?)?)`")


def _looks_like_source(ref: str) -> bool:
    """True when a backtick token is a file citation: its basename (the segment
    after the last '/') has a known source extension. Bare dotted prose
    (`array.map`) and slash prose (`TCP/IP`, `CI/CD`, `and/or`) are not."""
    basename = ref.rsplit("/", 1)[-1]
    _, dot, ext = basename.rpartition(".")
    return bool(dot) and ext.lower() in _SOURCE_EXTS


def _looks_like_dir_ref(ref: str) -> bool:
    """True when a backtick token is a directory citation: `/`-terminated and
    more than just the bare root slash (e.g. `src/handlers/`)."""
    return ref.endswith("/") and len(ref) > 1


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def _normalize(target: str) -> str:
    """Strip a #anchor and a :line suffix, yielding a bare repo-relative path."""
    target = target.split("#", 1)[0].strip()
    target = re.sub(r":\d+(-\d+)?$", "", target)
    return target


def _extract_citations(page: Path, wiki_root: Path) -> list[str]:
    text = page.read_text(encoding="utf-8", errors="replace")
    refs: set[str] = set()
    for m in _LINK_RE.finditer(text):
        target = m.group(1).strip()
        if _is_external(target):
            continue
        norm = _normalize(target)
        # Skip intra-wiki links (page-to-page navigation, not source claims).
        if not norm or (norm.endswith(".md") and not _points_into_source(norm)):
            continue
        refs.add(norm)
    for m in _CODE_PATH_RE.finditer(text):
        norm = _normalize(m.group(1))
        if _looks_like_source(norm) or _looks_like_dir_ref(norm):
            refs.add(norm)
    return sorted(refs)


def _points_into_source(norm: str) -> bool:
    # A .md link that escapes the wiki (e.g. ../README.md, docs/x.md) is a real
    # source citation; a sibling wiki page (quickstart.md, architecture/x.md) is
    # navigation. Heuristic: treat links containing '..' or starting outside the
    # wiki dir prefix as source.
    return ".." in norm or norm.startswith((WIKI_DIRNAME + "/",))


def _resolve(root: Path, wiki_root: Path, ref: str, page: Path) -> Path:
    """Resolve a citation to a filesystem path.

    A ref may be repo-root-relative (src/app.py) or relative to the page's own
    directory (../README.md). Try page-relative first, then repo-root-relative.
    """
    page_rel = (page.parent / ref).resolve()
    if page_rel.exists():
        return page_rel
    return (root / ref).resolve()


def build_manifest(root: Path) -> dict:
    """Build the verification manifest for every authored wiki page.

    Returns {"pages": [{page, citations: [{ref, exists, resolved}]}],
             "dead_citations": [...], "page_count", "citation_count",
             "dead_count"}.
    """
    wd = wiki_dir(root)
    pages: list[dict] = []
    dead: list[dict] = []
    citation_count = 0

    md_pages = (
        sorted(
            (p for p in wd.rglob("*.md") if not p.name.startswith("_")),
            key=lambda p: p.relative_to(wd).as_posix(),
        )
        if wd.is_dir()
        else []
    )

    for page in md_pages:
        page_rel = page.relative_to(root).as_posix()
        cites = []
        for ref in _extract_citations(page, wd):
            resolved = _resolve(root, wd, ref, page)
            exists = resolved.exists()
            citation_count += 1
            record = {"ref": ref, "exists": exists}
            cites.append(record)
            if not exists:
                dead.append({"page": page_rel, "ref": ref})
        pages.append({"page": page_rel, "citations": cites})

    return {
        "pages": pages,
        "dead_citations": dead,
        "page_count": len(pages),
        "citation_count": citation_count,
        "dead_count": len(dead),
    }
