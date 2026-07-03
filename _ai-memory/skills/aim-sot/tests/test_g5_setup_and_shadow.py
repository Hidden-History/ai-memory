"""G5: BP-041 setup sentinel + BP-040 shadow-git substrate (TD-675).

Proves: bare two-pointer shadow git with ZERO user-tree footprint, skip-if-clean
commits, gc; idempotent run-once setup with a sentinel written LAST and the full
invalidation ladder (absent / corrupt / schema / setup_version / reconfigure).

Requires the ``git`` binary (a stated required tool).  All machine-local roots
are redirected to ``tmp_path`` so the real ``~/.ai-memory`` is never touched.

Run targeted only:
    pytest tests/test_g5_setup_and_shadow.py
"""

import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shadow = _load("aim_sot_shadow")

pytestmark = pytest.mark.skipif(
    not shadow.git_available(), reason="git binary not available"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Redirect all machine-local roots into tmp_path and build a project tree."""
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.delenv("AIM_SOT_RECONFIGURE", raising=False)
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    return SimpleEnv(project)


class SimpleEnv:
    def __init__(self, project):
        self.project = project
        self.pid = "proj-shadow"


# --------------------------------------------------------------------------- #
# Shadow git — bare two-pointer, zero footprint
# --------------------------------------------------------------------------- #


def test_ensure_shadow_git_is_bare_and_configured(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    sdir = shadow.shadow_git_dir(env.pid)
    assert (sdir / "HEAD").exists()  # bare repo layout
    assert not (sdir / ".git").exists()
    assert (sdir / "info" / "exclude").exists()
    excl = (sdir / "info" / "exclude").read_text()
    assert ".git" in excl and ".sot/" in excl and ".env" in excl


def test_commit_leaves_zero_user_tree_footprint(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    sha = shadow.shadow_commit(env.pid, env.project, "snapshot")
    assert sha  # a non-empty commit happened
    # The cardinal non-invasive invariant: NOTHING written into the user's tree.
    assert not (env.project / ".git").exists()
    assert not (env.project / ".gitignore").exists()
    # Only the files we created remain in the work-tree.
    names = {p.name for p in env.project.rglob("*") if p.is_file()}
    assert names == {"app.py"}


def test_commit_skips_when_clean(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    first = shadow.shadow_commit(env.pid, env.project, "first")
    assert first
    # No changes since → skip (no empty snapshot).
    assert shadow.shadow_commit(env.pid, env.project, "second") is None
    # A change → commits again.
    (env.project / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    third = shadow.shadow_commit(env.pid, env.project, "third")
    assert third and third != first


def test_diff_name_status_over_shadow_history(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    base = shadow.shadow_commit(env.pid, env.project, "base")
    (env.project / "src" / "new.py").write_text("x\n", encoding="utf-8")
    (env.project / "src" / "app.py").write_text("y\n", encoding="utf-8")
    head = shadow.shadow_commit(env.pid, env.project, "next")
    changes = shadow.get_change_set(env.pid, env.project, base, head)
    by_path = {c.path: c.status for c in changes}
    assert by_path.get("src/new.py") == "A"
    assert by_path.get("src/app.py") == "M"


def test_gc_and_cap_rotate_do_not_error(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    shadow.shadow_commit(env.pid, env.project, "c1")
    shadow.shadow_gc(env.pid, env.project)  # must not raise
    assert shadow.cap_and_rotate(env.pid, env.project) is False  # under the caps


# --------------------------------------------------------------------------- #
# S3-F1 — project .gitignore folded into the shadow's info/exclude
# --------------------------------------------------------------------------- #


def test_gitignore_folded_into_exclude(env):
    (env.project / ".gitignore").write_text("build-output/\n", encoding="utf-8")
    shadow.ensure_shadow_git(env.pid, env.project)
    excl = (shadow.shadow_git_dir(env.pid) / "info" / "exclude").read_text()
    assert "build-output/" in excl
    # Additive: the mandatory hardcoded list is still present.
    assert ".git" in excl and ".sot/" in excl and ".env" in excl


def test_no_gitignore_no_error(env):
    assert not (env.project / ".gitignore").exists()
    shadow.ensure_shadow_git(env.pid, env.project)  # must not raise
    excl = (shadow.shadow_git_dir(env.pid) / "info" / "exclude").read_text()
    assert ".git" in excl  # mandatory list still written, no crash on absent file


def test_non_utf8_gitignore_no_error(env):
    """A .gitignore with a stray non-UTF-8 byte (e.g. Windows-authored repo)
    must not raise UnicodeDecodeError — the function's own contract is
    "absent/unreadable → no lines, no error" (fix-round finding)."""
    (env.project / ".gitignore").write_bytes(b"build-output/\n\xffbroken\n")
    assert shadow._project_gitignore_lines(env.project) == ()
    shadow.ensure_shadow_git(env.pid, env.project)  # must not raise
    excl = (shadow.shadow_git_dir(env.pid) / "info" / "exclude").read_text()
    assert ".git" in excl  # mandatory list still written, setup still succeeds


def test_setup_version_bump_regenerates_exclude_from_gitignore(env):
    """An already-'valid' sentinel from a prior setup_version is stale (S3-F1
    bumped SETUP_VERSION) so an already-set-up install regenerates info/exclude
    with the folded-in .gitignore on the next `ensure_setup`, instead of
    staying stuck on the old hardcoded-only list."""
    shadow.run_setup(env.pid, env.project)
    p = shadow.sentinel_path(env.pid)
    data = json.loads(p.read_text())
    data["setup_version"] = "0.0.0"  # simulate a pre-S3-F1 install
    p.write_text(json.dumps(data), encoding="utf-8")
    assert shadow.is_setup_valid(env.pid) is False

    (env.project / ".gitignore").write_text("legacy-nested-clone/\n", encoding="utf-8")
    assert shadow.ensure_setup(env.pid, env.project) is True
    excl = (shadow.shadow_git_dir(env.pid) / "info" / "exclude").read_text()
    assert "legacy-nested-clone/" in excl


# --------------------------------------------------------------------------- #
# S3-F2 — stale index.lock self-recovery
# --------------------------------------------------------------------------- #


def test_stale_index_lock_is_cleared_and_add_succeeds(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    lock_path = shadow.shadow_git_dir(env.pid) / "index.lock"
    lock_path.write_bytes(b"")  # 0-byte lock, as left by a SIGKILLed `git add`
    stale_mtime = time.time() - shadow._SHADOW_LOCK_STALE_SECONDS - 1
    os.utime(lock_path, (stale_mtime, stale_mtime))

    sha = shadow.shadow_commit(env.pid, env.project, "recovers")
    assert sha  # committed normally — no permanent wedge
    assert not lock_path.exists()


def test_fresh_index_lock_is_not_cleared(env):
    """A lock younger than the staleness threshold could be a live holder —
    must NOT be swept (sweeping it could corrupt an in-flight write)."""
    shadow.ensure_shadow_git(env.pid, env.project)
    lock_path = shadow.shadow_git_dir(env.pid) / "index.lock"
    lock_path.write_bytes(b"")  # fresh — mtime defaults to now
    shadow._clear_stale_index_lock(env.pid)
    assert lock_path.exists()  # untouched — not stale yet


def test_shadow_add_timeout_matches_coordinated_cap():
    """Locks in the cross-lane coordinated number (inner-add 15s < hook
    inner-subprocess 20s < hook outer SIGALRM 25s) so an accidental edit here
    is caught rather than silently drifting out of the safe ordering."""
    assert shadow._SHADOW_ADD_TIMEOUT_SECONDS == 15


# --------------------------------------------------------------------------- #
# Setup sentinel — idempotent run-once + invalidation ladder
# --------------------------------------------------------------------------- #


def test_setup_valid_only_after_run(env):
    assert shadow.is_setup_valid(env.pid) is False  # absent
    assert shadow.run_setup(env.pid, env.project) is True
    assert shadow.is_setup_valid(env.pid) is True  # present + current


def test_sentinel_written_last_on_success(env):
    shadow.run_setup(env.pid, env.project)
    data = json.loads(shadow.sentinel_path(env.pid).read_text())
    assert data["schema_version"] == shadow.SETUP_SCHEMA_VERSION
    assert data["setup_version"] == shadow.SETUP_VERSION
    assert data["artifacts"]["shadow_git"]["path"]


def test_partial_failure_leaves_no_sentinel(env, monkeypatch):
    """If an artifact step fails, the sentinel must NOT be written (proof-of-
    completion, BP-041 Q4) → next session re-runs."""

    def boom(*a, **k):
        raise RuntimeError("init failed")

    monkeypatch.setattr(shadow, "ensure_shadow_git", boom)
    with pytest.raises(RuntimeError):
        shadow.run_setup(env.pid, env.project)
    assert not shadow.sentinel_path(env.pid).exists()
    assert shadow.is_setup_valid(env.pid) is False


def test_git_init_is_rerun_safe(env):
    shadow.ensure_shadow_git(env.pid, env.project)
    shadow.shadow_commit(env.pid, env.project, "c1")
    head_before = shadow.shadow_head(env.pid, env.project)
    # Re-running setup must not destroy history (git init --bare is idempotent).
    shadow.ensure_shadow_git(env.pid, env.project)
    assert shadow.shadow_head(env.pid, env.project) == head_before


def test_invalidation_corrupt_sentinel(env):
    shadow.run_setup(env.pid, env.project)
    shadow.sentinel_path(env.pid).write_text("{not json", encoding="utf-8")
    assert shadow.is_setup_valid(env.pid) is False


def test_invalidation_schema_version_mismatch(env):
    shadow.run_setup(env.pid, env.project)
    p = shadow.sentinel_path(env.pid)
    data = json.loads(p.read_text())
    data["schema_version"] = "999"
    p.write_text(json.dumps(data), encoding="utf-8")
    assert shadow.is_setup_valid(env.pid) is False


def test_invalidation_setup_version_mismatch(env):
    shadow.run_setup(env.pid, env.project)
    p = shadow.sentinel_path(env.pid)
    data = json.loads(p.read_text())
    data["setup_version"] = "0.0.0"
    p.write_text(json.dumps(data), encoding="utf-8")
    assert shadow.is_setup_valid(env.pid) is False


def test_invalidation_reconfigure_env(env, monkeypatch):
    shadow.run_setup(env.pid, env.project)
    assert shadow.is_setup_valid(env.pid) is True
    monkeypatch.setenv("AIM_SOT_RECONFIGURE", "1")
    assert shadow.is_setup_valid(env.pid) is False


def test_ensure_setup_fast_path_and_teardown(env):
    assert shadow.ensure_setup(env.pid, env.project) is True
    # Fast path: already valid → still True, no rebuild needed.
    assert shadow.ensure_setup(env.pid, env.project) is True
    shadow.teardown(env.pid)
    assert not shadow.shadow_git_dir(env.pid).exists()
