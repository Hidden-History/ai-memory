"""wiki_pointer: placement rule, idempotency, surrounding-content preservation."""

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


_wiki_pointer = _load("wiki_pointer")
POINTER_HEADING = _wiki_pointer.POINTER_HEADING
upsert_pointer = _wiki_pointer.upsert_pointer
upsert_section = _wiki_pointer.upsert_section


def test_creates_agents_when_neither_exists(tmp_path):
    changed = upsert_pointer(tmp_path)
    assert changed == ["AGENTS.md"]
    assert not (tmp_path / "CLAUDE.md").exists()
    assert POINTER_HEADING in (tmp_path / "AGENTS.md").read_text()


def test_updates_claude_when_present(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# House rules\n\nBe surgical.\n", encoding="utf-8"
    )
    changed = upsert_pointer(tmp_path)
    assert changed == ["CLAUDE.md"]
    text = (tmp_path / "CLAUDE.md").read_text()
    assert "Be surgical." in text, "surrounding content preserved"
    assert POINTER_HEADING in text
    assert not (
        tmp_path / "AGENTS.md"
    ).exists(), "AGENTS.md not created when CLAUDE.md exists"


def test_updates_both_when_both_present(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# c\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# a\n", encoding="utf-8")
    changed = upsert_pointer(tmp_path)
    assert set(changed) == {"CLAUDE.md", "AGENTS.md"}


def test_idempotent_second_run_no_change(tmp_path):
    upsert_pointer(tmp_path)  # creates AGENTS.md
    changed = upsert_pointer(tmp_path)  # second run
    assert changed == [], "re-running with an identical section must be a no-op"


def test_replaces_existing_section_no_duplicate(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    claude.write_text(
        "# top\n\n## Project Wiki\n\nOLD stale pointer text.\n\n## Other\n\nkeep me.\n",
        encoding="utf-8",
    )
    upsert_pointer(tmp_path)
    text = claude.read_text()
    assert text.count(POINTER_HEADING) == 1, "must replace, not duplicate"
    assert "OLD stale pointer text." not in text
    assert "## Other" in text and "keep me." in text, "later section preserved"
    assert "wiki/quickstart.md" in text


def test_replace_preserves_following_h1(tmp_path):
    """F-A: replacing the section must NOT swallow a following `# H1` heading.

    The old terminator stopped only at `## ` H2 / EOF, so a `# Appendix` after the
    Project Wiki section was consumed and deleted on replace (data-loss)."""
    claude = tmp_path / "CLAUDE.md"
    claude.write_text(
        "# Top\n\n## Project Wiki\n\nOLD pointer text.\n\n# Appendix\n\nkeep me.\n",
        encoding="utf-8",
    )
    upsert_pointer(tmp_path)
    text = claude.read_text()
    assert text.count(POINTER_HEADING) == 1, "must replace, not duplicate"
    assert "OLD pointer text." not in text
    assert "# Appendix" in text and "keep me." in text, "following H1 preserved"


def test_upsert_section_appends_with_separation():
    out = upsert_section("# title\n\nbody\n")
    assert "body" in out
    assert out.rstrip().endswith("run an update when your changes make a page stale.")
    assert "\n\n## Project Wiki" in out
