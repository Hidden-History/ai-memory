"""G5: BP-039 tree-digest determinism + exclude/symlink semantics (TD-675).

Proves the sorted-per-file-SHA-256 hash-of-hashes is byte-identical across
walk-order and after a clone/restore copy, honors gitignore-style excludes on
the relpath, skips symlinks (recording them), and carries the version prefix
that drives R-1 re-baseline.

Run targeted only:
    pytest tests/test_g5_tree_digest.py
"""

import importlib.util
import os
import shutil
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shadow = _load("aim_sot_shadow")


def _populate(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_digest_has_version_prefix(tmp_path):
    _populate(tmp_path, {"a.py": "x", "b/c.py": "y"})
    td = shadow.tree_digest(tmp_path)
    assert td.digest.startswith("v1:")
    assert td.file_count == 2


def test_digest_deterministic_across_creation_order(tmp_path):
    """Same content, different file-creation order → identical digest (the byte
    sort over relpath-keyed lines makes walk-order irrelevant)."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    _populate(a, {"src/z.py": "1", "src/a.py": "2", "docs/m.md": "3"})
    # Create in a different order in b.
    _populate(b, {"docs/m.md": "3", "src/a.py": "2", "src/z.py": "1"})
    assert shadow.tree_digest(a).digest == shadow.tree_digest(b).digest


def test_digest_stable_after_clone_restore_copy(tmp_path):
    """A full copytree (clone/restore) preserves content → identical digest,
    even though inode/mtime differ (content-only hashing)."""
    src = tmp_path / "src"
    _populate(src, {"x.py": "alpha", "pkg/y.py": "beta", "pkg/sub/z.txt": "gamma"})
    before = shadow.tree_digest(src).digest
    dst = tmp_path / "restored"
    shutil.copytree(src, dst)
    # Touch mtimes to prove they are not part of the digest.
    os.utime(dst / "x.py", (0, 0))
    assert shadow.tree_digest(dst).digest == before


def test_digest_changes_on_content_edit(tmp_path):
    _populate(tmp_path, {"a.py": "one"})
    d1 = shadow.tree_digest(tmp_path).digest
    (tmp_path / "a.py").write_text("two", encoding="utf-8")
    assert shadow.tree_digest(tmp_path).digest != d1


def test_digest_changes_on_rename(tmp_path):
    """Path is embedded in each line → a move changes the digest even with
    identical content (correct drift behavior, BP-039)."""
    _populate(tmp_path, {"a.py": "same"})
    d1 = shadow.tree_digest(tmp_path).digest
    (tmp_path / "a.py").rename(tmp_path / "b.py")
    assert shadow.tree_digest(tmp_path).digest != d1


def test_excludes_applied_on_relpath(tmp_path):
    """Excluded paths do not affect the digest; a non-excluded sibling does."""
    _populate(
        tmp_path,
        {
            "keep.py": "k",
            "__pycache__/junk.pyc": "j",
            "build/out.o": "o",
            ".env": "SECRET=1",
        },
    )
    td = shadow.tree_digest(tmp_path)
    # Only keep.py counts.
    assert td.file_count == 1
    # Mutating an excluded file must not change the digest.
    before = td.digest
    (tmp_path / "__pycache__" / "junk.pyc").write_text("changed", encoding="utf-8")
    assert shadow.tree_digest(tmp_path).digest == before


def test_custom_excludes_extend_defaults(tmp_path):
    _populate(tmp_path, {"keep.py": "k", "notes.tmp": "t"})
    base = shadow.tree_digest(tmp_path)
    assert base.file_count == 2
    extended = shadow.tree_digest(tmp_path, (*shadow.DEFAULT_EXCLUDES, "*.tmp"))
    assert extended.file_count == 1


def test_symlinks_skipped_and_recorded(tmp_path):
    _populate(tmp_path, {"real.py": "r"})
    link = tmp_path / "link.py"
    try:
        link.symlink_to(tmp_path / "real.py")
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("symlinks not supported on this platform")
    td = shadow.tree_digest(tmp_path)
    assert "link.py" in td.skipped_symlinks
    assert td.file_count == 1  # only the real file hashed


def test_path_excluded_matcher():
    pats = (".git/", "__pycache__/", "*.pyc", ".env", ".env.*", "build/")
    assert shadow.path_excluded(".git/config", pats)
    assert shadow.path_excluded("pkg/__pycache__/x.pyc", pats)
    assert shadow.path_excluded("a/b/c.pyc", pats)
    assert shadow.path_excluded(".env", pats)
    assert shadow.path_excluded(".env.local", pats)
    assert shadow.path_excluded("build/out", pats)
    assert not shadow.path_excluded("src/app.py", pats)
    assert not shadow.path_excluded("env_config.py", pats)
