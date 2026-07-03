"""wiki_common: root resolution, content-hash (no-op detection), state roundtrip,
and git-diff-since-last-run."""

import importlib.util
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


def _page(root: Path, rel: str, text: str) -> None:
    p = wc.wiki_dir(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_resolve_root_override(tmp_path):
    assert wc.resolve_root(str(tmp_path)) == tmp_path


def test_wiki_has_content(tmp_path):
    assert wc.wiki_has_content(tmp_path) is False
    _page(tmp_path, "quickstart.md", "# hi\n")
    assert wc.wiki_has_content(tmp_path) is True


def test_content_hash_stable_and_sensitive(tmp_path):
    _page(tmp_path, "quickstart.md", "# hi\n")
    _page(tmp_path, "arch/overview.md", "body\n")
    h1 = wc.content_hash(tmp_path)
    assert h1 == wc.content_hash(tmp_path), "hash must be stable when nothing changes"
    _page(tmp_path, "arch/overview.md", "body changed\n")
    assert wc.content_hash(tmp_path) != h1, "hash must change when a page changes"


def test_content_hash_excludes_state_and_plan(tmp_path):
    _page(tmp_path, "quickstart.md", "# hi\n")
    h1 = wc.content_hash(tmp_path)
    # Writing the state file and a plan file must NOT change the content hash.
    wc.state_path(tmp_path).write_text('{"x":1}', encoding="utf-8")
    _page(tmp_path, wc.PLAN_FILENAME, "scratch\n")
    assert wc.content_hash(tmp_path) == h1


def test_state_roundtrip(tmp_path):
    _page(tmp_path, "quickstart.md", "# hi\n")
    assert wc.read_state(tmp_path) is None
    state = wc.write_state(tmp_path, "init", "abc123")
    assert state["command"] == "init"
    assert state["gitHead"] == "abc123"
    assert state["contentHash"] == wc.content_hash(tmp_path)
    assert state["updatedAt"].endswith("Z")
    read = wc.read_state(tmp_path)
    assert read == state


def test_read_state_none_on_bad_json(tmp_path):
    wc.wiki_dir(tmp_path).mkdir(parents=True)
    wc.state_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert wc.read_state(tmp_path) is None


def test_git_changed_files(git_repo):
    root, commit = git_repo
    head0 = wc.git_head(root)
    assert head0
    commit("src/app.py", "print(1)\n", "add app")
    commit("src/util.py", "x = 1\n", "add util")
    changes = wc.git_changed_files(root, head0)
    assert changes["resolvable"] is True
    assert set(changes["committed"]) == {"src/app.py", "src/util.py"}
    # Uncommitted edit shows up too.
    (root / "src" / "app.py").write_text("print(2)\n", encoding="utf-8")
    changes2 = wc.git_changed_files(root, head0)
    assert "src/app.py" in changes2["uncommitted"]


def test_git_changed_files_excludes_wiki_managed(git_repo):
    """The wiki dir + pointer files must not register as SOURCE drift."""
    root, commit = git_repo
    head0 = wc.git_head(root)
    commit("src/real.py", "x=1\n", "add source")  # committed source change
    # Uncommitted wiki output + pointer must NOT count as source drift.
    (root / "wiki").mkdir()
    (root / "wiki" / "quickstart.md").write_text("# q\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("## Project Wiki\n", encoding="utf-8")
    changes = wc.git_changed_files(root, head0)
    assert "src/real.py" in changes["committed"]
    both = changes["committed"] + changes["uncommitted"]
    assert not any(p.startswith("wiki") for p in both)
    assert "AGENTS.md" not in both


def test_git_changed_files_non_ascii_unmangled(git_repo):
    """F-D: non-ASCII paths must come back literal, not octal-quoted by git's
    default core.quotePath (covers both the diff and status --porcelain parses)."""
    root, commit = git_repo
    base = wc.git_head(root)
    commit("café.py", "x = 1\n", "add committed non-ascii")  # committed -> diff path
    (root / "naïve.py").write_text("y = 2\n", encoding="utf-8")  # uncommitted -> status
    changes = wc.git_changed_files(root, base)
    assert "café.py" in changes["committed"]
    assert "naïve.py" in changes["uncommitted"]


def test_git_changed_files_unresolvable_head(git_repo):
    root, _ = git_repo
    changes = wc.git_changed_files(root, "deadbeef" * 5)
    assert changes["resolvable"] is False
    assert changes["committed"] == []


def test_git_summary_non_repo(tmp_path):
    assert "not a git repository" in wc.git_summary(tmp_path)
