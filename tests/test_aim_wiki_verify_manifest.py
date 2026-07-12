"""wiki_verify: citation extraction + dead-path precheck (verifier plumbing)."""

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "_ai-memory"
    / "skills"
    / "aim-wiki"
    / "scripts"
)


def _load(name: str):
    """Load an aim-wiki skill script by bare module name (registered in
    sys.modules) so sibling scripts that `import <name>` resolve correctly —
    without adding scripts/ to sys.path (no sys.path namespace collision)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load("wiki_common")  # wiki_verify imports it by bare name — must land first
build_manifest = _load("wiki_verify").build_manifest


def _page(root: Path, rel: str, text: str) -> None:
    p = root / "wiki" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_live_and_dead_citations(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    _page(
        tmp_path,
        "quickstart.md",
        "The entrypoint is `src/app.py`. Missing: `src/gone.py`.\n"
        "External [docs](https://example.com) ignored.\n"
        "Nav to [arch](architecture/overview.md) ignored.\n",
    )
    _page(tmp_path, "architecture/overview.md", "See `src/app.py:12` for detail.\n")

    m = build_manifest(tmp_path)
    assert m["page_count"] == 2
    dead_refs = {(d["page"], d["ref"]) for d in m["dead_citations"]}
    assert ("wiki/quickstart.md", "src/gone.py") in dead_refs
    assert m["dead_count"] == 1
    # Live citation resolves (and :line suffix is stripped before resolving).
    all_refs = {c["ref"] for p in m["pages"] for c in p["citations"]}
    assert "src/app.py" in all_refs
    # External links and intra-wiki nav are not treated as source citations.
    assert not any(
        c["ref"].startswith(("http://", "https://"))
        for p in m["pages"]
        for c in p["citations"]
    )
    assert not any(
        c["ref"] == "architecture/overview.md"
        for p in m["pages"]
        for c in p["citations"]
    )


def test_page_relative_citation_resolves(tmp_path):
    (tmp_path / "README.md").write_text("# proj\n", encoding="utf-8")
    _page(tmp_path, "quickstart.md", "Root readme: [readme](../README.md)\n")
    m = build_manifest(tmp_path)
    assert m["dead_count"] == 0, "../README.md must resolve page-relative to repo root"
    assert m["citation_count"] == 1


def test_plan_file_skipped(tmp_path):
    _page(tmp_path, "quickstart.md", "ok\n")
    _page(tmp_path, "_plan.md", "cite `src/nope.py`\n")
    m = build_manifest(tmp_path)
    assert m["page_count"] == 1, "_plan.md excluded from the manifest"
    assert m["dead_count"] == 0


def test_prose_dotted_token_not_flagged(tmp_path):
    """F-E: bare dotted prose (`array.map`) is not a source citation; a real
    slash path (`src/gone.py`) still is."""
    _page(
        tmp_path,
        "quickstart.md",
        "Use `array.map` and `response` freely. Missing file `src/gone.py`.\n",
    )
    m = build_manifest(tmp_path)
    refs = {c["ref"] for p in m["pages"] for c in p["citations"]}
    assert "array.map" not in refs, "prose dotted token must not be a citation"
    assert "response" not in refs
    assert "src/gone.py" in refs, "a real slash path is still a citation"
    assert m["dead_count"] == 1


def test_slash_prose_not_flagged(tmp_path):
    """F-E-R2: backtick slash-prose (`TCP/IP`, `CI/CD`, `and/or`, `client/server`)
    is not a source citation; a slash path whose basename has a source extension
    still is (`docs/guide.md` live, `src/gone.py` dead)."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# guide\n", encoding="utf-8")
    _page(
        tmp_path,
        "quickstart.md",
        "Networking uses `TCP/IP`, `CI/CD`, `and/or`, `client/server`.\n"
        "See `docs/guide.md`. Missing file `src/gone.py`.\n",
    )
    m = build_manifest(tmp_path)
    refs = {c["ref"] for p in m["pages"] for c in p["citations"]}
    for prose in ("TCP/IP", "CI/CD", "and/or", "client/server"):
        assert prose not in refs, f"{prose} slash-prose must not be a citation"
    assert "docs/guide.md" in refs, "slash path with source-ext basename is a citation"
    assert "src/gone.py" in refs, "nonexistent slash source path still flagged dead"
    assert m["dead_count"] == 1, "only src/gone.py is dead"


def test_bare_basename_citation_flags_dead(tmp_path):
    """Pins the pre-existing `_resolve` behavior that page-structure.md's
    "citations must be full paths, never a bare filename" guidance documents:
    a bare-basename backtick citation (no path) cannot resolve even when the
    file exists elsewhere in the repo — only root-relative / page-relative
    forms are supported. This behavior predates and is unchanged by that doc
    update; it is not new-code coverage."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "storage.py").write_text("pass\n", encoding="utf-8")
    _page(tmp_path, "quickstart.md", "See `storage.py` for the store.\n")
    m = build_manifest(tmp_path)
    dead_refs = {(d["page"], d["ref"]) for d in m["dead_citations"]}
    assert ("wiki/quickstart.md", "storage.py") in dead_refs
    assert m["dead_count"] == 1


def test_dir_citation_resolves_and_flags(tmp_path):
    """W5: a `/`-terminated backtick citation is checked for directory
    existence — a real directory resolves live, a missing one is dead."""
    (tmp_path / "src" / "handlers").mkdir(parents=True)
    _page(
        tmp_path,
        "quickstart.md",
        "Handlers live in `src/handlers/`. Missing: `src/absent/`.\n",
    )
    m = build_manifest(tmp_path)
    refs = {c["ref"]: c["exists"] for p in m["pages"] for c in p["citations"]}
    assert refs["src/handlers/"] is True
    assert refs["src/absent/"] is False
    assert m["dead_count"] == 1


def test_dir_ref_overmatch_excluded(tmp_path):
    """A `/`-terminated backtick token is only treated as a directory citation
    when it plausibly is one: an absolute-path/API-route shape (`/api/v1/`),
    a sed-style substitution (`s/foo/bar/`), and pure `.`/`..` traversal
    (`../`) must NOT be flagged as dead citations — none of them are real
    repo-relative directory references."""
    _page(
        tmp_path,
        "quickstart.md",
        "Route: `/api/v1/`. Substitution: `s/foo/bar/`. Parent: `../`.\n",
    )
    m = build_manifest(tmp_path)
    refs = {c["ref"] for p in m["pages"] for c in p["citations"]}
    assert "/api/v1/" not in refs
    assert "s/foo/bar/" not in refs
    assert "../" not in refs
    assert m["citation_count"] == 0
    assert m["dead_count"] == 0


def test_empty_wiki(tmp_path):
    (tmp_path / "wiki").mkdir()
    m = build_manifest(tmp_path)
    assert m == {
        "pages": [],
        "dead_citations": [],
        "page_count": 0,
        "citation_count": 0,
        "dead_count": 0,
    }
