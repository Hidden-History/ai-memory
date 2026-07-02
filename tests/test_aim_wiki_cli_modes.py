"""aim_wiki CLI: init / update / status / verify / finalize via main(), JSON path.

Drives the real argv dispatch (--root override, --json) end-to-end on a tmp git
repo so the mode wiring, guards, and state lifecycle are exercised together.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


wc = _load("wiki_common")
_load("wiki_inventory")
wp = _load("wiki_pointer")
_load("wiki_verify")
aim_wiki = _load("aim_wiki")


@pytest.fixture(autouse=True)
def _stub_project_id(monkeypatch):
    """Keep CLI-mode tests off the real memory stack: resolve_project_id would
    import ~/.ai-memory and can touch machine state outside tmp_path. Scoping is
    guaranteed by the resolved root, not this id, so a stub is faithful."""
    monkeypatch.setattr(wc, "resolve_project_id", lambda root, **_: "test-project")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path):
    """A tmp git repo with one initial commit. Returns (root, commit_fn)."""
    root = tmp_path
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# Proj\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")

    def commit(relpath: str, content: str, msg: str = "change") -> str:
        p = root / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", msg)
        return _git(root, "rev-parse", "HEAD")

    return root, commit


def _run(capsys, argv):
    capsys.readouterr()  # drain any prior (un-measured) main() output
    rc = aim_wiki.main(argv)
    out = capsys.readouterr().out
    return rc, out


def _json(capsys, argv):
    rc, out = _run(capsys, argv)
    return rc, json.loads(out)


def test_init_ready_then_guard_then_force(capsys, git_repo):
    root, _ = git_repo
    r = str(root)

    rc, data = _json(capsys, ["init", "--root", r, "--json"])
    assert rc == 0 and data["status"] == "ready"
    assert wc.wiki_dir(root).is_dir()
    assert "inventory" in data and "git_summary" in data

    # Author a page → wiki now has content.
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")

    # Bare init now routes to update (guard).
    rc, data = _json(capsys, ["init", "--root", r, "--json"])
    assert rc == 0 and data["status"] == "wiki_exists" and data["action"] == "update"

    # --force overrides the guard.
    rc, data = _json(capsys, ["init", "--root", r, "--force", "--json"])
    assert rc == 0 and data["status"] == "ready" and data["forced"] is True


def test_update_requires_state_then_ready(capsys, git_repo):
    root, commit = git_repo
    r = str(root)
    aim_wiki.main(["init", "--root", r])
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")

    # No state yet → routed to finalize-init to establish a baseline.
    rc, data = _json(capsys, ["update", "--root", r, "--json"])
    assert rc == 0 and data["status"] == "no_state"

    # Establish baseline, then change source → update reports the diff.
    aim_wiki.main(["finalize", "--root", r, "--command", "init"])
    commit("src/new.py", "x = 1\n", "add source")
    rc, data = _json(capsys, ["update", "--root", r, "--json"])
    assert rc == 0 and data["status"] == "ready"
    assert "src/new.py" in data["changes"]["committed"]


def test_status_lifecycle(capsys, git_repo):
    root, commit = git_repo
    r = str(root)

    # Not initialized.
    rc, data = _json(capsys, ["status", "--root", r, "--json"])
    assert rc == 0 and data["status"] == "not_initialized"

    # Init + author + finalize → current.
    aim_wiki.main(["init", "--root", r])
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")
    aim_wiki.main(["finalize", "--root", r, "--command", "init"])
    rc, data = _json(capsys, ["status", "--root", r, "--json"])
    assert rc == 0 and data["status"] == "current"

    # Source change → drifted.
    commit("src/x.py", "1\n", "change")
    rc, data = _json(capsys, ["status", "--root", r, "--json"])
    assert data["status"] == "drifted" and data["source_changes_since"] >= 1


def test_status_unresolvable_githead_not_current(capsys, git_repo):
    """F-B: an unresolvable recorded gitHead must not report 'current'."""
    root, _ = git_repo
    r = str(root)
    aim_wiki.main(["init", "--root", r])
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")
    aim_wiki.main(["finalize", "--root", r, "--command", "init"])

    # Corrupt the recorded gitHead to a commit that no longer resolves.
    sp = wc.state_path(root)
    state = json.loads(sp.read_text())
    state["gitHead"] = "0" * 40
    sp.write_text(json.dumps(state), encoding="utf-8")

    rc, data = _json(capsys, ["status", "--root", r, "--json"])
    assert rc == 0
    assert data["resolvable"] is False
    assert data["status"] != "current", "unresolvable gitHead must not read as fresh"


def test_finalize_guards_empty_wiki(capsys, git_repo):
    """F-C: finalize on an empty wiki is guarded — no pointer, no state written."""
    root, _ = git_repo
    r = str(root)
    aim_wiki.main(["init", "--root", r])  # scaffolds empty wiki/, authors nothing

    rc, data = _json(capsys, ["finalize", "--root", r, "--command", "init", "--json"])
    assert rc == 0 and data["status"] == "not_initialized"
    assert not (root / "AGENTS.md").exists() and not (root / "CLAUDE.md").exists()
    assert wc.read_state(root) is None, "no baseline state recorded on empty wiki"


def test_finalize_writes_pointer_and_state(capsys, git_repo):
    root, _ = git_repo
    r = str(root)
    aim_wiki.main(["init", "--root", r])
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")

    rc, data = _json(capsys, ["finalize", "--root", r, "--command", "init", "--json"])
    assert rc == 0 and data["status"] == "recorded"
    # Pointer landed in CLAUDE.md (README exists but CLAUDE/AGENTS do not → AGENTS.md).
    assert data["pointer_files_changed"] == ["AGENTS.md"]
    assert "## Project Wiki" in (root / "AGENTS.md").read_text()
    # State persisted with a real gitHead + matching content hash.
    state = wc.read_state(root)
    assert state["command"] == "init"
    assert state["gitHead"] == wc.git_head(root)
    assert state["contentHash"] == wc.content_hash(root)


def test_finalize_refuses_malformed_pointer_markers(capsys, git_repo):
    """Refusal observability: `finalize` against a CLAUDE.md with malformed
    AI-memory markers surfaces the refusal distinctly from a no-op — a populated
    `pointer_files_refused` (empty `pointer_files_changed`) in --json, a human
    REFUSED line in text, exit 2, and the file left byte-for-byte unchanged."""
    root, _ = git_repo
    r = str(root)
    aim_wiki.main(["init", "--root", r])
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")

    # Malformed: a stray BEGIN with no matching END.
    claude = root / "CLAUDE.md"
    original = f"# rules\n\n{wp.BEGIN_MARKER}\ndangling — no end marker\n"
    claude.write_text(original, encoding="utf-8")

    rc, data = _json(capsys, ["finalize", "--root", r, "--command", "init", "--json"])
    assert rc == 2, "refused pointer write exits non-zero"
    assert data["pointer_files_refused"] == ["CLAUDE.md"]
    assert data["pointer_files_changed"] == [], "refusal is not a change"
    assert data["status"] == "recorded", "wiki run-state is still recorded"
    assert claude.read_text() == original, "malformed file left byte-for-byte unchanged"
    assert list(root.glob("CLAUDE.md.backup.*")) == [], "no backup on refusal"

    # Text path renders a REFUSED line, not 'already current'.
    rc, out = _run(capsys, ["finalize", "--root", r, "--command", "init"])
    assert rc == 2
    assert "REFUSED" in out and "CLAUDE.md" in out
    assert "already current" not in out


def test_finalize_noop_reports_already_current(capsys, git_repo):
    """No-op companion: once the pointer is present and identical, a re-finalize
    is a true no-op — exit 0, empty changed/refused, and the text path still
    reports `already current` (no false-refused regression)."""
    root, _ = git_repo
    r = str(root)
    aim_wiki.main(["init", "--root", r])
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")
    aim_wiki.main(["finalize", "--root", r, "--command", "init"])  # writes pointer

    rc, data = _json(capsys, ["finalize", "--root", r, "--command", "init", "--json"])
    assert rc == 0
    assert data["pointer_files_changed"] == [] and data["pointer_files_refused"] == []

    rc, out = _run(capsys, ["finalize", "--root", r, "--command", "init"])
    assert rc == 0
    assert "already current" in out
    assert "REFUSED" not in out


def test_finalize_mixed_changed_and_refused(capsys, git_repo):
    """Per-file accumulation: with one valid target (needs the pointer) and one
    carrying malformed markers, `finalize` writes the valid file
    (`pointer_files_changed`), refuses the malformed one (`pointer_files_refused`),
    exits 2, and in text mode renders BOTH the changed line and the REFUSED line."""
    root, _ = git_repo
    r = str(root)
    aim_wiki.main(["init", "--root", r])
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")

    # CLAUDE.md valid (no markers → pointer appended); AGENTS.md malformed
    # (a stray BEGIN with no matching END).
    claude = root / "CLAUDE.md"
    agents = root / "AGENTS.md"
    claude_original = "# rules\n"
    agents_original = f"# agents\n\n{wp.BEGIN_MARKER}\ndangling — no end marker\n"
    claude.write_text(claude_original, encoding="utf-8")
    agents.write_text(agents_original, encoding="utf-8")

    rc, data = _json(capsys, ["finalize", "--root", r, "--command", "init", "--json"])
    assert rc == 2, "any refused file makes finalize exit non-zero"
    assert data["pointer_files_changed"] == ["CLAUDE.md"], "valid target written"
    assert data["pointer_files_refused"] == ["AGENTS.md"], "malformed target refused"
    assert data["status"] == "recorded", "wiki run-state still recorded"
    assert "## Project Wiki" in claude.read_text(), "pointer landed in the valid file"
    assert agents.read_text() == agents_original, "malformed file left unchanged"
    assert list(root.glob("AGENTS.md.backup.*")) == [], "no backup on the refused file"

    # Text mode renders BOTH the changed line and the REFUSED line. Reset the valid
    # file so this run re-exercises the mixed changed+refused render (the prior run
    # already made CLAUDE.md a no-op).
    claude.write_text(claude_original, encoding="utf-8")
    rc, out = _run(capsys, ["finalize", "--root", r, "--command", "init"])
    assert rc == 2
    assert "CLAUDE.md" in out, "changed line names the valid file"
    assert (
        "REFUSED" in out and "AGENTS.md" in out
    ), "REFUSED line names the malformed file"


def test_verify_reports_dead_citation(capsys, git_repo):
    root, _ = git_repo
    r = str(root)
    aim_wiki.main(["init", "--root", r])
    (wc.wiki_dir(root) / "quickstart.md").write_text(
        "Entry `src/ghost.py` does not exist.\n", encoding="utf-8"
    )

    rc, data = _json(capsys, ["verify", "--root", r, "--json"])
    assert rc == 0 and data["status"] == "dead_citations"
    assert data["dead_count"] == 1
    assert data["dead_citations"][0]["ref"] == "src/ghost.py"


def test_verify_not_initialized(capsys, tmp_path):
    rc, data = _json(capsys, ["verify", "--root", str(tmp_path), "--json"])
    assert rc == 0 and data["status"] == "not_initialized"


def test_text_output_smoke(capsys, git_repo):
    """Text (non-JSON) path renders without error for every mode."""
    root, _ = git_repo
    r = str(root)
    assert aim_wiki.main(["init", "--root", r]) == 0
    (wc.wiki_dir(root) / "quickstart.md").write_text("# hi\n", encoding="utf-8")
    assert aim_wiki.main(["finalize", "--root", r, "--command", "init"]) == 0
    assert aim_wiki.main(["status", "--root", r]) == 0
    assert aim_wiki.main(["update", "--root", r]) == 0
    assert aim_wiki.main(["verify", "--root", r]) == 0
    out = capsys.readouterr().out
    assert "aim-wiki" in out
