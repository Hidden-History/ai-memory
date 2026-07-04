"""TD-730: scoped shadow-git ``git add`` (accelerate the Stop-hook snapshot).

Proves the scoped-pathspec add that replaces the whole-tree ``git add -A`` walk on
a large ``path``-type SOT boundary:

  * ``tree_digest`` reports ``changed_rels`` (new/modified, cache-gated) and
    ``present_rels`` (every non-excluded regular file on disk, cache-independent).
  * ``shadow_commit(pathspec=...)`` stages exactly those paths (add/modify/delete),
    an empty pathspec skips the add, and ``pathspec=None`` keeps the whole-tree add.
  * ``run_shadow_pass`` builds the scoped pathspec = changed_rels + all present
    symlinks + deletions (tracked paths from ``git ls-files`` no longer on disk),
    only on a warm cache; else it falls back to the full add (cold/empty cache,
    prior commit raised, or changed-set over the cap).
  * The scoped snapshot is byte-identical to what a full ``add -A`` would commit —
    including symlink retargets and deletions of committed-but-uncached files.
  * #258's stale-lock clear + inner-add cap are still exercised on the scoped path.
  * Perf: a warm steady-state run over a large tree uses the scoped add.

Hermetic: all machine-local roots redirect into ``tmp_path``; requires the ``git``
binary (a stated required tool).

Run targeted only:
    pytest tests/test_sot_shadow_scoped_add.py
"""

import importlib.util
import os
import time
from pathlib import Path

import pytest

_SHADOW_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "_ai-memory"
    / "skills"
    / "aim-sot"
    / "scripts"
    / "aim_sot_shadow.py"
)
_spec = importlib.util.spec_from_file_location("aim_sot_shadow", _SHADOW_SCRIPT)
shadow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shadow)

pytestmark = pytest.mark.skipif(
    not shadow.git_available(), reason="git binary not available"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Redirect every machine-local root into tmp_path and build a project tree."""
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "drift-state")
    monkeypatch.delenv("AIM_SOT_RECONFIGURE", raising=False)
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "src" / "util.py").write_text("x = 1\n", encoding="utf-8")
    return _Env(project)


class _Env:
    def __init__(self, project):
        self.project = project
        self.pid = "proj-scoped"


def _cache(env):
    return shadow.load_file_hash_cache(env.pid, shadow.DEFAULT_EXCLUDES)


def _age(root):
    """Back-date every file well past the per-file cache freshness horizon so a
    digest run actually stores its hashes (the cache only stores AGED files, so a
    just-written file is never cached — this reproduces real steady-state where
    files predate the session's Stop by more than the horizon)."""
    old = time.time() - (shadow._FRESHNESS_HORIZON_NS / 1e9) - 5
    for p in root.rglob("*"):
        if p.is_file():
            os.utime(p, (old, old))


def _spy_pathspec(monkeypatch):
    """Wrap shadow_commit to record the pathspec each call received."""
    calls = []
    real = shadow.shadow_commit

    def _wrapper(project_id, project_dir, message, pathspec=None):
        calls.append(pathspec)
        return real(project_id, project_dir, message, pathspec=pathspec)

    monkeypatch.setattr(shadow, "shadow_commit", _wrapper)
    return calls


# --------------------------------------------------------------------------- #
# tree_digest — changed / present reporting
# --------------------------------------------------------------------------- #


def test_tree_digest_reports_changed_and_present(env):
    cache = _cache(env)
    # Warm the cache with a first complete walk (files aged so hashes are stored).
    _age(env.project)
    first = shadow.tree_digest(env.project, cache=cache)
    assert set(first.changed_rels) == {"src/app.py", "src/util.py"}
    assert set(first.present_rels) == {"src/app.py", "src/util.py"}

    # Modify one, add one, delete one.
    (env.project / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (env.project / "src" / "new.py").write_text("y = 2\n", encoding="utf-8")
    (env.project / "src" / "util.py").unlink()

    second = shadow.tree_digest(env.project, cache=cache)
    assert set(second.changed_rels) == {"src/app.py", "src/new.py"}
    # present_rels is the on-disk set: the deleted file is gone; deletion detection
    # itself is the caller's job (git ls-files minus present), not tree_digest's.
    assert set(second.present_rels) == {"src/app.py", "src/new.py"}


def test_tree_digest_present_populated_without_cache(env):
    # present_rels is cache-independent; changed_rels needs a cache.
    td = shadow.tree_digest(env.project)  # no cache → no changed-set source
    assert td.changed_rels == []
    assert set(td.present_rels) == {"src/app.py", "src/util.py"}


# --------------------------------------------------------------------------- #
# shadow_commit — scoped staging
# --------------------------------------------------------------------------- #


def test_scoped_add_stages_only_pathspec(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    base = shadow.shadow_commit(env.pid, env.project, "base")
    assert base
    # Modify BOTH files but scope the add to only one.
    (env.project / "src" / "app.py").write_text("print('a2')\n", encoding="utf-8")
    (env.project / "src" / "util.py").write_text("x = 2\n", encoding="utf-8")
    head = shadow.shadow_commit(env.pid, env.project, "scoped", pathspec=["src/app.py"])
    assert head and head != base
    changed = {c.path for c in shadow.get_change_set(env.pid, env.project, base, head)}
    assert changed == {"src/app.py"}  # util.py's change was NOT staged


def test_scoped_add_stages_deletion(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    base = shadow.shadow_commit(env.pid, env.project, "base")
    (env.project / "src" / "util.py").unlink()
    head = shadow.shadow_commit(env.pid, env.project, "del", pathspec=["src/util.py"])
    assert head and head != base
    changes = {
        c.path: c.status
        for c in shadow.get_change_set(env.pid, env.project, base, head)
    }
    assert changes.get("src/util.py") == "D"


def test_empty_pathspec_skips_add_and_commit(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    base = shadow.shadow_commit(env.pid, env.project, "base")
    # Dirty the tree but pass an empty pathspec → add is skipped → nothing staged.
    (env.project / "src" / "app.py").write_text("print('dirty')\n", encoding="utf-8")
    assert shadow.shadow_commit(env.pid, env.project, "noop", pathspec=[]) is None
    assert shadow.shadow_head(env.pid, env.project) == base


def test_scoped_run_honors_exclude(env):
    # #258 scoped-exclude net preserved through the scoped path: an excluded file
    # (matched by info/exclude) never enters tree_digest.changed_rels, so the scoped
    # add never stages it.  Exercised end-to-end through run_shadow_pass.
    drift_state = {}
    _age(env.project)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)  # warm + baseline
    base = shadow.shadow_head(env.pid, env.project)
    (env.project / "debug.log").write_text(
        "noise\n", encoding="utf-8"
    )  # *.log excluded
    (env.project / "src" / "app.py").write_text("print('a2')\n", encoding="utf-8")
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    head = shadow.shadow_head(env.pid, env.project)
    changed = {c.path for c in shadow.get_change_set(env.pid, env.project, base, head)}
    assert changed == {"src/app.py"}  # debug.log excluded, never staged


# --------------------------------------------------------------------------- #
# run_shadow_pass — pathspec selection + fallbacks
# --------------------------------------------------------------------------- #


def test_cold_cache_uses_full_add(env, monkeypatch):
    calls = _spy_pathspec(monkeypatch)
    drift_state = {}
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    assert calls == [None]  # cold cache → whole-tree add -A
    assert drift_state.get("shadow_commit_dirty") is False


def test_warm_cache_uses_scoped_add(env, monkeypatch):
    drift_state = {}
    _age(env.project)
    # First run warms the per-file cache and commits the baseline (full add).
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    # Change exactly one file, then run again.
    (env.project / "src" / "app.py").write_text("print('warm')\n", encoding="utf-8")
    calls = _spy_pathspec(monkeypatch)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    assert len(calls) == 1
    assert calls[0] == ["src/app.py"]  # scoped to the single changed file


def test_many_changed_falls_back_to_full_add(env, monkeypatch):
    monkeypatch.setattr(shadow, "_SCOPED_ADD_MAX_PATHS", 1)
    drift_state = {}
    _age(env.project)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)  # warm + baseline
    # Change both files → 2 > cap(1) → full add.
    (env.project / "src" / "app.py").write_text("print('a2')\n", encoding="utf-8")
    (env.project / "src" / "util.py").write_text("x = 9\n", encoding="utf-8")
    calls = _spy_pathspec(monkeypatch)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    assert calls == [None]


def test_prior_commit_dirty_forces_full_add(env, monkeypatch):
    drift_state = {}
    _age(env.project)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)  # warm + baseline
    (env.project / "src" / "app.py").write_text("print('a2')\n", encoding="utf-8")
    drift_state["shadow_commit_dirty"] = True  # simulate a prior commit that raised
    calls = _spy_pathspec(monkeypatch)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    assert calls == [None]  # resync via full add
    assert drift_state.get("shadow_commit_dirty") is False  # cleared after clean commit


def test_commit_failure_sets_dirty_flag(env, monkeypatch):
    drift_state = {}
    _age(env.project)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)  # warm + baseline
    (env.project / "src" / "app.py").write_text("print('a2')\n", encoding="utf-8")

    def _boom(*a, **k):
        raise shadow.ShadowGitError("simulated add failure")

    monkeypatch.setattr(shadow, "shadow_commit", _boom)
    summary = shadow.run_shadow_pass(env.pid, env.project, drift_state)
    assert drift_state.get("shadow_commit_dirty") is True  # forces full add next run
    assert any(f.get("finding_type") == "ERROR" for f in summary["findings"])


# --------------------------------------------------------------------------- #
# Correctness: scoped snapshot == full add -A snapshot (no missed file)
# --------------------------------------------------------------------------- #


def _head_tree(pid, project):
    res = shadow.run_git(pid, project, "rev-parse", "HEAD^{tree}")
    return res.stdout.strip()


def test_scoped_snapshot_matches_full_add_tree(tmp_path, monkeypatch):
    """A scoped-add run and a full-add run over identical mutations must produce
    the same committed tree — proving the scoped path stages exactly the same set."""
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "drift-state")

    def _build(root):
        (root / "a").mkdir(parents=True)
        (root / "a" / "one.py").write_text("1\n", encoding="utf-8")
        (root / "a" / "two.py").write_text("2\n", encoding="utf-8")
        (root / "b.txt").write_text("b\n", encoding="utf-8")

    def _mutate(root):
        (root / "a" / "one.py").write_text("1-changed\n", encoding="utf-8")  # M
        (root / "a" / "three.py").write_text("3\n", encoding="utf-8")  # A
        (root / "b.txt").unlink()  # D

    scoped_proj = tmp_path / "scoped"
    full_proj = tmp_path / "full"
    _build(scoped_proj)
    _build(full_proj)

    # Scoped project: real run_shadow_pass (warm → scoped add on the mutation run).
    ds_scoped = {}
    _age(scoped_proj)  # warm the cache so the mutation run takes the scoped path
    shadow.run_shadow_pass("scoped", scoped_proj, ds_scoped)
    _mutate(scoped_proj)
    shadow.run_shadow_pass("scoped", scoped_proj, ds_scoped)

    # Full project: force the whole-tree add every time.
    shadow.ensure_setup("full", full_proj)
    shadow.shadow_commit("full", full_proj, "base", pathspec=None)
    _mutate(full_proj)
    shadow.shadow_commit("full", full_proj, "next", pathspec=None)

    assert _head_tree("scoped", scoped_proj) == _head_tree("full", full_proj)


# --------------------------------------------------------------------------- #
# Soundness: the scoped pathspec == git's full stage-set (symlinks + deletions
# the digest / 2s cache can't see).  Regression for the review's HIGH + MEDIUM.
# --------------------------------------------------------------------------- #


def test_uncached_regular_file_deletion_staged(env):
    """A committed file that stayed under the 2s freshness horizon is tracked but
    never cached; the scoped run must still stage its deletion (sourced from the
    shadow index, not the cache) — else a ghost is left in the shadow tree."""
    drift_state = {}
    _age(env.project)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)  # warm baseline
    # Fresh (< horizon) file: committed via changed_rels but NOT stored in the cache.
    (env.project / "src" / "transient.py").write_text("t = 1\n", encoding="utf-8")
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    mid = shadow.shadow_head(env.pid, env.project)
    cache = shadow.load_file_hash_cache(env.pid, shadow.DEFAULT_EXCLUDES)
    assert "src/transient.py" not in cache["files"]  # uncached (too fresh)
    assert (
        "src/transient.py" in shadow.run_git(env.pid, env.project, "ls-files").stdout
    )  # but tracked

    (env.project / "src" / "transient.py").unlink()
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    head = shadow.shadow_head(env.pid, env.project)
    changes = {
        c.path: c.status for c in shadow.get_change_set(env.pid, env.project, mid, head)
    }
    assert changes.get("src/transient.py") == "D"
    assert (
        "src/transient.py"
        not in shadow.run_git(env.pid, env.project, "ls-files").stdout
    )


def test_symlink_retarget_staged(env):
    """A symlink retarget is the sole change.  The digest skips symlink content, so
    it's absent from changed_rels; folding skipped_symlinks into the pathspec is
    what stops the change being silently dropped (the review's HIGH)."""
    (env.project / "target1.txt").write_text("one\n", encoding="utf-8")
    (env.project / "target2.txt").write_text("two\n", encoding="utf-8")
    os.symlink("target1.txt", env.project / "link.txt")
    drift_state = {}
    _age(env.project)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)  # baseline commits link
    base = shadow.shadow_head(env.pid, env.project)

    (env.project / "link.txt").unlink()
    os.symlink("target2.txt", env.project / "link.txt")  # retarget = sole change
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    head = shadow.shadow_head(env.pid, env.project)
    assert head and head != base  # NOT silently dropped
    changed = {c.path for c in shadow.get_change_set(env.pid, env.project, base, head)}
    assert "link.txt" in changed


def test_symlink_deletion_staged(env):
    """A deleted symlink is tracked but absent from present (present = regular +
    symlink), and lexists is False so the scoped run stages its removal."""
    (env.project / "target.txt").write_text("x\n", encoding="utf-8")
    os.symlink("target.txt", env.project / "link.txt")
    drift_state = {}
    _age(env.project)
    shadow.run_shadow_pass(env.pid, env.project, drift_state)  # baseline
    base = shadow.shadow_head(env.pid, env.project)

    (env.project / "link.txt").unlink()
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    head = shadow.shadow_head(env.pid, env.project)
    changes = {
        c.path: c.status
        for c in shadow.get_change_set(env.pid, env.project, base, head)
    }
    assert changes.get("link.txt") == "D"


def test_dangling_symlink_not_flagged_deleted(env):
    """A present-but-dangling symlink (target missing) must NOT be staged as a
    deletion — lexists (not exists) keeps it in the present-set."""
    (env.project / "gone.txt").write_text("bye\n", encoding="utf-8")
    os.symlink("gone.txt", env.project / "link.txt")
    drift_state = {}
    _age(env.project)
    shadow.run_shadow_pass(
        env.pid, env.project, drift_state
    )  # baseline (link + target)
    base = shadow.shadow_head(env.pid, env.project)

    (env.project / "gone.txt").unlink()  # link.txt now dangles but still exists
    shadow.run_shadow_pass(env.pid, env.project, drift_state)
    head = shadow.shadow_head(env.pid, env.project)
    changes = {
        c.path: c.status
        for c in shadow.get_change_set(env.pid, env.project, base, head)
    }
    assert changes.get("gone.txt") == "D"  # the real deletion is staged
    assert "link.txt" not in changes  # the dangling symlink is NOT staged as deleted


def test_scoped_matches_full_add_symlinks_and_deletions(tmp_path, monkeypatch):
    """Byte-identical committed tree for the hard cases together: a symlink retarget,
    an uncached-fresh-file deletion, and a cached-file deletion — scoped == full."""
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "drift-state")

    def _build(root):
        root.mkdir(parents=True)
        (root / "t1.txt").write_text("1\n", encoding="utf-8")
        (root / "t2.txt").write_text("2\n", encoding="utf-8")
        (root / "keep.py").write_text("keep\n", encoding="utf-8")
        (root / "cached_del.py").write_text("x\n", encoding="utf-8")
        os.symlink("t1.txt", root / "link.txt")

    def _mutate(root):
        (root / "link.txt").unlink()
        os.symlink("t2.txt", root / "link.txt")  # symlink retarget
        (root / "cached_del.py").unlink()  # cached-file deletion
        (root / "fresh.py").write_text("f\n", encoding="utf-8")  # fresh, then delete

    scoped, full = tmp_path / "s", tmp_path / "f"
    _build(scoped)
    _build(full)

    ds = {}
    _age(scoped)
    shadow.run_shadow_pass("s", scoped, ds)  # warm baseline
    _mutate(scoped)
    (scoped / "fresh.py").unlink()  # delete the just-created uncached file
    shadow.run_shadow_pass("s", scoped, ds)

    shadow.ensure_setup("f", full)
    shadow.shadow_commit("f", full, "base", pathspec=None)
    _mutate(full)
    (full / "fresh.py").unlink()
    shadow.shadow_commit("f", full, "next", pathspec=None)

    assert _head_tree("s", scoped) == _head_tree("f", full)


# --------------------------------------------------------------------------- #
# Perf: warm steady-state over a large tree uses the scoped add
# --------------------------------------------------------------------------- #


def test_large_tree_warm_run_is_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "drift-state")
    project = tmp_path / "big"
    for i in range(1500):
        d = project / f"pkg{i // 100:02d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"mod{i:04d}.py").write_text(f"X = {i}\n", encoding="utf-8")

    drift_state = {}
    _age(project)  # files predate the session → cache warms on the baseline run
    shadow.run_shadow_pass("big", project, drift_state)  # cold baseline (full add)

    # Steady state: touch 3 files.
    for i in (7, 800, 1490):
        (project / f"pkg{i // 100:02d}" / f"mod{i:04d}.py").write_text(
            f"X = {i}  # edit\n", encoding="utf-8"
        )
    calls = _spy_pathspec(monkeypatch)
    t0 = time.monotonic()
    summary = shadow.run_shadow_pass("big", project, drift_state)
    elapsed = time.monotonic() - t0

    assert len(calls) == 1
    assert calls[0] is not None and set(calls[0]) == {
        "pkg00/mod0007.py",
        "pkg08/mod0800.py",
        "pkg14/mod1490.py",
    }
    assert summary["committed"] is True
    # Generous ceiling; the real WSL2/9p <20s target is measured by the harness.
    assert elapsed < 20.0
