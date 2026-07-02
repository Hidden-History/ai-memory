"""wiki_pointer: placement rule, marker-keyed idempotency, user-content safety.

Idempotency keys on the managed marker pair (BP-171 OQ-3), never on the
`## Project Wiki` heading — a user's own same-named section is never clobbered.
Writes are backup-copy-first + atomic (tempfile + os.replace).
"""

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
POINTER_SECTION = _wiki_pointer.POINTER_SECTION
BEGIN_MARKER = _wiki_pointer.BEGIN_MARKER
END_MARKER = _wiki_pointer.END_MARKER
upsert_pointer = _wiki_pointer.upsert_pointer
splice_block = _wiki_pointer.splice_block


def test_creates_agents_when_neither_exists(tmp_path):
    changed = upsert_pointer(tmp_path)
    assert changed == ["AGENTS.md"]
    assert not (tmp_path / "CLAUDE.md").exists()
    text = (tmp_path / "AGENTS.md").read_text()
    assert POINTER_HEADING in text
    assert BEGIN_MARKER in text and END_MARKER in text


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
    assert changed == [], "re-running with an identical managed block must be a no-op"


# --- W1: managed-marker fences — user content is never clobbered ---


def test_user_markerless_section_preserved(tmp_path):
    """W1(a): a user-authored markerless `## Project Wiki` is NOT clobbered.

    Its body differs from the aim-wiki template, so it is user content: left
    untouched, and the managed block is added separately.
    """
    claude = tmp_path / "CLAUDE.md"
    user = "# top\n\n## Project Wiki\n\nMy own notes about our internal wiki.\n"
    claude.write_text(user, encoding="utf-8")
    upsert_pointer(tmp_path)
    text = claude.read_text()
    assert "My own notes about our internal wiki." in text, "user section preserved"
    assert BEGIN_MARKER in text and END_MARKER in text, "managed block added"
    assert text.count(POINTER_HEADING) == 2, "user heading + managed heading"


def test_replace_in_place_between_markers(tmp_path):
    """W1(b): a stale managed block is replaced in place; bytes outside the
    markers are preserved, and no duplicate markers appear."""
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        f"# a\n\nkeep before.\n\n{BEGIN_MARKER}\nstale managed body\n{END_MARKER}\n"
        f"\nkeep after.\n",
        encoding="utf-8",
    )
    changed = upsert_pointer(tmp_path)
    assert changed == ["AGENTS.md"]
    text = agents.read_text()
    assert text.count(BEGIN_MARKER) == 1 and text.count(END_MARKER) == 1
    assert "stale managed body" not in text, "managed body replaced"
    assert POINTER_HEADING in text and "wiki/quickstart.md" in text
    assert "keep before." in text and "keep after." in text, "outside bytes kept"


def test_no_duplicate_across_reruns(tmp_path):
    """W1(b): re-running many times never duplicates the managed block."""
    upsert_pointer(tmp_path)  # create AGENTS.md with block
    upsert_pointer(tmp_path)
    upsert_pointer(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text()
    assert text.count(BEGIN_MARKER) == 1
    assert text.count(END_MARKER) == 1
    assert text.count(POINTER_HEADING) == 1


def test_legacy_markerless_migrates_once(tmp_path):
    """W1(c): a legacy markerless section whose body matches the template is
    migrated once to the marked form (no duplicate); a following H1 survives."""
    claude = tmp_path / "CLAUDE.md"
    legacy = "# Top\n\n" + POINTER_SECTION.rstrip("\n") + "\n\n# Appendix\n\nkeep me.\n"
    claude.write_text(legacy, encoding="utf-8")
    upsert_pointer(tmp_path)
    text = claude.read_text()
    assert BEGIN_MARKER in text and END_MARKER in text, "migrated to marked form"
    assert text.count(POINTER_HEADING) == 1, "migrated in place, not appended"
    assert "# Appendix" in text and "keep me." in text, "following H1 preserved"
    # markers now present → subsequent run is a true no-op
    assert upsert_pointer(tmp_path) == []


def test_non_matching_section_not_migrated(tmp_path):
    """W1(c): a markerless section whose body differs from the template is user
    content — NOT migrated; the managed block is appended separately."""
    claude = tmp_path / "CLAUDE.md"
    claude.write_text(
        "# Top\n\n## Project Wiki\n\nUser's own different wiki text.\n",
        encoding="utf-8",
    )
    upsert_pointer(tmp_path)
    text = claude.read_text()
    assert "User's own different wiki text." in text, "user body preserved"
    assert BEGIN_MARKER in text, "managed block appended separately"
    assert text.count(POINTER_HEADING) == 2


def test_malformed_markers_left_unchanged(tmp_path):
    """W1: an ambiguous marker state (stray BEGIN) is refused — file unchanged,
    no write, empty return list."""
    agents = tmp_path / "AGENTS.md"
    original = f"# a\n\n{BEGIN_MARKER}\ndangling — no end marker\n"
    agents.write_text(original, encoding="utf-8")
    changed = upsert_pointer(tmp_path)
    assert changed == [], "malformed markers → no change"
    assert agents.read_text() == original, "file left byte-for-byte unchanged"


# --- W2: atomic write + timestamped backup ---


def test_backup_created_on_change_not_on_noop(tmp_path):
    """W2(d): a timestamped backup is produced on change, but NOT on a no-op."""
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# rules\n", encoding="utf-8")
    upsert_pointer(tmp_path)  # change → one backup
    assert len(list(tmp_path.glob("CLAUDE.md.backup.*"))) == 1, "backup on change"
    upsert_pointer(tmp_path)  # no-op → no new backup
    assert len(list(tmp_path.glob("CLAUDE.md.backup.*"))) == 1, "no backup on no-op"


def test_no_backup_when_creating_new_file(tmp_path):
    """W2: creating a brand-new AGENTS.md backs up nothing (nothing existed)."""
    upsert_pointer(tmp_path)
    assert list(tmp_path.glob("AGENTS.md.backup.*")) == []


def test_write_is_atomic_via_os_replace(tmp_path, monkeypatch):
    """W2(e): the write is routed through os.replace (atomic) and leaves no
    temp files behind."""
    calls = []
    real_replace = _wiki_pointer.os.replace

    def spy(src, dst):
        calls.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(_wiki_pointer.os, "replace", spy)
    upsert_pointer(tmp_path)  # creates AGENTS.md
    assert calls, "write routed through os.replace"
    assert any(str(dst).endswith("AGENTS.md") for _src, dst in calls)
    assert list(tmp_path.glob(".AGENTS.md_*.tmp")) == [], "no leftover temp files"


# --- pure splice_block behavior ---


def test_splice_block_appends_with_separation():
    out = splice_block("# title\n\nbody\n")
    assert "body" in out
    assert "\n\n" + BEGIN_MARKER in out, "blank line separates existing content"
    assert out.endswith(END_MARKER + "\n")
    assert POINTER_HEADING in out
