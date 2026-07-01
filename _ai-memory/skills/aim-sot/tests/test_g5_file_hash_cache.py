"""BP-048: incremental per-file hash cache inside ``tree_digest`` (R2 + fixes).

The load-bearing gate: a warm run (populated cache) yields a digest that is
BYTE-IDENTICAL to a cold run (empty cache) and to a cache-free run — the cache
is a pure accelerator, never the digest authority.

Also covers the review-round fixes:
  FIX-S1 — store-side freshness guard (a racy same-second overwrite never serves
           a stale hash);
  FIX-S2 — stdlib ``fcntl`` lock (no ``filelock`` third-party dep);
  FIX-S3 — a truncated walk persists its partial entries so large/slow trees
           bootstrap the cache incrementally;
  FIX-S4 — the project_id-keyed, scope-isolated standalone cache API.

Run targeted only:
    pytest tests/test_g5_file_hash_cache.py
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

_EPOCH = shadow.exclude_epoch(shadow.DEFAULT_EXCLUDES)


def _populate(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _age(root: Path, seconds: int = 10) -> None:
    """Push every file's mtime into the past so it clears the 2s freshness
    horizon and a cached hit is stored/trusted."""
    past = time.time() - seconds
    for p in root.rglob("*"):
        if p.is_file():
            os.utime(p, (past, past))


def _empty_cache() -> dict:
    return {"v": shadow.FILE_HASH_CACHE_VERSION, "epoch": _EPOCH, "files": {}}


class _FakeTime:
    """Controllable stand-in for the ``time`` module: ``time_ns`` returns the
    settable ``now_ns``; ``monotonic`` is a constant so the digest never
    truncates during a clock-controlled test."""

    def __init__(self, now_ns: int = 0) -> None:
        self.now_ns = now_ns

    def time_ns(self) -> int:
        return self.now_ns

    def monotonic(self) -> float:
        return 0.0


# --------------------------------------------------------------------------- #
# Load-bearing gate: cold == warm == cache-free (byte-identical)
# --------------------------------------------------------------------------- #


def test_warm_run_after_reload_is_byte_identical(tmp_path, monkeypatch):
    """Cold → persist → reload → warm produces the identical digest, and it
    equals a cache-free authority run. This is the core BP-048 correctness gate."""
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "drift")
    proj = tmp_path / "p"
    _populate(proj, {"a.py": "1", "d/b.py": "2", "d/sub/c.txt": "three"})
    _age(proj)

    c1 = shadow.load_file_hash_cache("proj-x")
    cold = shadow.tree_digest(proj, cache=c1).digest
    shadow.save_file_hash_cache("proj-x", c1)

    c2 = shadow.load_file_hash_cache("proj-x")
    warm = shadow.tree_digest(proj, cache=c2).digest

    assert warm == cold
    assert warm == shadow.tree_digest(proj).digest  # cache-free authority


def test_warm_run_serves_every_file_from_cache(tmp_path, monkeypatch):
    """A warm run over an unchanged, aged tree reads zero files — every hash is
    served from the cache."""
    proj = tmp_path / "p"
    _populate(proj, {"a.py": "1", "pkg/b.py": "2"})
    _age(proj)
    cache = _empty_cache()
    cold = shadow.tree_digest(proj, cache=cache).digest

    reads: list = []
    real = shadow.file_sha256
    monkeypatch.setattr(
        shadow, "file_sha256", lambda p, **k: (reads.append(p), real(p, **k))[1]
    )
    warm = shadow.tree_digest(proj, cache=cache).digest

    assert warm == cold
    assert reads == []  # no file re-read on the warm path


def test_digest_changes_after_mutation_with_cache(tmp_path):
    """Mutating one file changes the warm digest and it matches the cache-free
    digest of the mutated tree (accelerator never masks a real change)."""
    proj = tmp_path / "p"
    _populate(proj, {"a.py": "one", "b.py": "two"})
    _age(proj)
    cache = _empty_cache()
    d1 = shadow.tree_digest(proj, cache=cache).digest

    (proj / "a.py").write_text("one-CHANGED", encoding="utf-8")
    d2 = shadow.tree_digest(proj, cache=cache).digest

    assert d2 != d1
    assert d2 == shadow.tree_digest(proj).digest


# --------------------------------------------------------------------------- #
# FIX-S1 — store-side freshness guard (racy same-second overwrite)
# --------------------------------------------------------------------------- #


def test_store_guard_skips_fresh_file(tmp_path):
    """A file within the freshness horizon is NEVER persisted, so it can never
    poison a later read (the returned hash is still the true content hash)."""
    _populate(tmp_path, {"a.py": "AAAA"})
    p = tmp_path / "a.py"  # just written → fresh
    cache = _empty_cache()
    got = shadow.get_file_hash("a.py", p, cache)
    assert got == shadow.file_sha256(p)
    assert "a.py" not in cache["files"]  # store guard skipped it


def test_racy_same_second_overwrite_never_serves_stale(tmp_path, monkeypatch):
    """FIX-S1: hash AAAA while fresh (not stored), overwrite BBBB keeping the same
    mtime+size, then read while aged → must return sha(BBBB), never a stale
    sha(AAAA). Byte-identical to the cache-free digest of the mutated tree."""
    proj = tmp_path / "p"
    _populate(proj, {"a.py": "AAAA"})
    p = proj / "a.py"
    os.utime(p, (1000.0, 1000.0))  # fixed mtime
    m_ns = os.stat(p).st_mtime_ns

    ft = _FakeTime()
    monkeypatch.setattr(shadow, "time", ft)
    cache = _empty_cache()

    # STORE phase: "now" is within the horizon of M → too fresh → not cached.
    ft.now_ns = m_ns + 500_000_000  # +0.5s
    cold_aaaa = shadow.tree_digest(proj, cache=cache).digest
    assert "a.py" not in cache["files"]

    # Same-second overwrite: same size (4 bytes), mtime restored to M.
    p.write_text("BBBB", encoding="utf-8")
    os.utime(p, (1000.0, 1000.0))

    # READ phase: "now" is well past the horizon → aged, (mtime,size) match the
    # (never-stored) entry. A pre-fix cache would return sha(AAAA); we must not.
    ft.now_ns = m_ns + 10_000_000_000  # +10s
    warm = shadow.tree_digest(proj, cache=cache).digest
    cold_bbbb = shadow.tree_digest(proj).digest  # cache-free authority (BBBB)

    assert warm == cold_bbbb
    assert warm != cold_aaaa


# --------------------------------------------------------------------------- #
# get_file_hash: retrieval guard + (mtime, size) key
# --------------------------------------------------------------------------- #


def test_freshness_horizon_recomputes_recent_file(tmp_path):
    """A file modified within the horizon is re-hashed even when a cache entry's
    (mtime, size) matches — the racy-clean guard rejects the poisoned hit."""
    _populate(tmp_path, {"a.py": "aaa"})
    p = tmp_path / "a.py"  # just written → mtime is "now" (< 2s)
    st = os.stat(p)
    cache = {
        "v": "1",
        "epoch": _EPOCH,
        "files": {
            "a.py": {
                "v": "1",
                "mtime": st.st_mtime_ns,
                "size": st.st_size,
                "sha256": "deadbeef",
            }
        },
    }
    got = shadow.get_file_hash("a.py", p, cache)
    assert got == shadow.file_sha256(p)
    assert got != "deadbeef"


def test_aged_cache_hit_is_trusted(tmp_path):
    """An aged file whose (mtime, size) matches the entry is served straight from
    the cache (proven by returning a sentinel hash the file does not have)."""
    _populate(tmp_path, {"a.py": "aaa"})
    p = tmp_path / "a.py"
    _age(tmp_path)
    st = os.stat(p)
    cache = {
        "v": "1",
        "epoch": _EPOCH,
        "files": {
            "a.py": {
                "v": "1",
                "mtime": st.st_mtime_ns,
                "size": st.st_size,
                "sha256": "cafef00d",
            }
        },
    }
    assert shadow.get_file_hash("a.py", p, cache) == "cafef00d"


def test_size_change_invalidates_even_when_aged(tmp_path):
    """A size mismatch is always a miss regardless of the freshness horizon."""
    _populate(tmp_path, {"a.py": "aaa"})
    p = tmp_path / "a.py"
    _age(tmp_path)
    st = os.stat(p)
    cache = {
        "v": "1",
        "epoch": _EPOCH,
        "files": {
            "a.py": {
                "v": "1",
                "mtime": st.st_mtime_ns,
                "size": st.st_size + 1,  # stale size
                "sha256": "cafef00d",
            }
        },
    }
    assert shadow.get_file_hash("a.py", p, cache) == shadow.file_sha256(p)


def test_entry_version_mismatch_is_a_miss(tmp_path):
    _populate(tmp_path, {"a.py": "aaa"})
    p = tmp_path / "a.py"
    _age(tmp_path)
    st = os.stat(p)
    cache = {
        "v": "1",
        "epoch": _EPOCH,
        "files": {
            "a.py": {
                "v": "0",  # old algorithm version
                "mtime": st.st_mtime_ns,
                "size": st.st_size,
                "sha256": "cafef00d",
            }
        },
    }
    assert shadow.get_file_hash("a.py", p, cache) == shadow.file_sha256(p)


# --------------------------------------------------------------------------- #
# Pruning + FIX-S3 partial-persist on truncation
# --------------------------------------------------------------------------- #


def test_prune_drops_deleted_entries_on_complete_walk(tmp_path):
    _populate(tmp_path, {"a.py": "a", "b.py": "b"})
    _age(tmp_path)
    cache = _empty_cache()
    shadow.tree_digest(tmp_path, cache=cache)
    assert set(cache["files"]) == {"a.py", "b.py"}

    (tmp_path / "b.py").unlink()
    shadow.tree_digest(tmp_path, cache=cache)
    assert set(cache["files"]) == {"a.py"}


def test_truncated_walk_does_not_prune(tmp_path):
    """A truncated walk holds an incomplete file set → it must not drop live
    entries (would corrupt the cache into a permanent under-count)."""
    _populate(tmp_path, {f"f{i}.txt": str(i) for i in range(10)})
    _age(tmp_path)
    cache = _empty_cache()
    shadow.tree_digest(tmp_path, cache=cache)
    assert len(cache["files"]) == 10

    td = shadow.tree_digest(tmp_path, cache=cache, max_files=3)
    assert td.truncated is True
    assert len(cache["files"]) == 10  # untouched


def test_truncated_walk_persists_partial_entries(tmp_path):
    """FIX-S3 (tree_digest level): a truncated walk still stored valid per-file
    entries for the files it reached — the accelerator can warm incrementally."""
    _populate(tmp_path, {f"f{i}.txt": str(i) for i in range(8)})
    _age(tmp_path)
    cache = _empty_cache()
    td = shadow.tree_digest(tmp_path, cache=cache, max_files=3)
    assert td.truncated is True
    assert 0 < len(cache["files"]) <= 3


# --------------------------------------------------------------------------- #
# FIX-S2 — stdlib fcntl lock (no filelock third-party dependency)
# --------------------------------------------------------------------------- #


def test_no_filelock_dependency():
    assert not hasattr(shadow, "FileLock")  # filelock import removed
    assert hasattr(shadow, "fcntl")  # stdlib lock in use


def test_save_creates_lock_file_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "d")
    cache = {
        "v": "1",
        "epoch": _EPOCH,
        "files": {"a.py": {"v": "1", "mtime": 1, "size": 2, "sha256": "z"}},
    }
    shadow.save_file_hash_cache("proj-l", cache)
    cf = shadow.file_hash_cache_path("proj-l")
    assert cf.exists()
    assert Path(str(cf) + ".lock").exists()  # fcntl lock path exercised
    assert shadow.load_file_hash_cache("proj-l")["files"] == cache["files"]


# --------------------------------------------------------------------------- #
# FIX-S4 — project_id-keyed, scope-isolated standalone cache API
# --------------------------------------------------------------------------- #


def test_cache_path_and_epoch_helpers(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path)
    p = shadow.file_hash_cache_path("proj/x")
    assert p.parent == tmp_path
    assert p.name.startswith("sot_file_hash_proj__x__")  # human-readable stem
    assert p.suffix == ".json"
    assert "__whole_tree__" in p.name  # default scope is the reserved token
    assert shadow.exclude_epoch(("a", "b")) == shadow.exclude_epoch(("b", "a"))
    assert shadow.exclude_epoch(("a", "c")) != shadow.exclude_epoch(("a", "b"))


def test_whole_tree_scope_reserved_from_entry_named_tree(tmp_path, monkeypatch):
    """LOW-1: the whole-project cache uses a reserved token, so an entry literally
    named 'tree' gets a distinct cache file and cannot prune the project cache."""
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path)
    assert shadow.file_hash_cache_path("p") != shadow.file_hash_cache_path(
        "p", scope="tree"
    )


def test_cache_path_boundary_is_unambiguous(tmp_path, monkeypatch):
    """LOW-1: ('a/b','c') and ('a','b/c') share the flattened stem 'a__b__c' but
    must map to distinct cache files (the NUL-delimited tag disambiguates)."""
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path)
    assert shadow.file_hash_cache_path("a/b", scope="c") != shadow.file_hash_cache_path(
        "a", scope="b/c"
    )


def test_scope_isolation_prevents_cross_prune(tmp_path, monkeypatch):
    """Two distinct roots under one project must not prune each other — each uses
    its own scope, hence its own cache file (the FIX-S4 correctness guarantee)."""
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "d")
    a = tmp_path / "A"
    b = tmp_path / "B"
    _populate(a, {"x.py": "1"})
    _populate(b, {"y.py": "2"})
    _age(tmp_path)

    ca = shadow.load_file_hash_cache("proj", scope="A")
    shadow.tree_digest(a, cache=ca)
    shadow.save_file_hash_cache("proj", ca, scope="A")

    cb = shadow.load_file_hash_cache("proj", scope="B")
    shadow.tree_digest(b, cache=cb)
    shadow.save_file_hash_cache("proj", cb, scope="B")

    assert set(shadow.load_file_hash_cache("proj", scope="A")["files"]) == {"x.py"}
    assert set(shadow.load_file_hash_cache("proj", scope="B")["files"]) == {"y.py"}
    assert shadow.file_hash_cache_path("proj", "A") != shadow.file_hash_cache_path(
        "proj", "B"
    )


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "drift")
    cache = {
        "v": "1",
        "epoch": _EPOCH,
        "files": {"a.py": {"v": "1", "mtime": 1, "size": 2, "sha256": "z"}},
    }
    shadow.save_file_hash_cache("proj-r", cache)
    assert shadow.file_hash_cache_path("proj-r").exists()
    assert shadow.load_file_hash_cache("proj-r") == cache


def test_epoch_change_invalidates_whole_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "d")
    ex1 = ("a", "b")
    ex2 = ("a", "c")
    cache = shadow.load_file_hash_cache("p", ex1)
    cache["files"]["x.py"] = {"v": "1", "mtime": 1, "size": 2, "sha256": "z"}
    shadow.save_file_hash_cache("p", cache)
    assert shadow.load_file_hash_cache("p", ex1)["files"]  # same excludes → kept
    assert shadow.load_file_hash_cache("p", ex2)["files"] == {}  # changed → empty


def test_cache_version_mismatch_invalidates(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "d")
    p = shadow.file_hash_cache_path("proj")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"v": "0", "epoch": _EPOCH, "files": {"a.py": 1}}), encoding="utf-8"
    )
    assert shadow.load_file_hash_cache("proj")["files"] == {}


def test_corrupt_cache_fails_open(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "d")
    p = shadow.file_hash_cache_path("proj")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    assert shadow.load_file_hash_cache("proj") == {
        "v": "1",
        "epoch": _EPOCH,
        "files": {},
    }


def test_missing_cache_fails_open(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "d")
    assert shadow.load_file_hash_cache("absent-proj") == {
        "v": "1",
        "epoch": _EPOCH,
        "files": {},
    }


# --------------------------------------------------------------------------- #
# run_shadow_pass wiring
# --------------------------------------------------------------------------- #


def test_run_shadow_pass_populates_file_hash_cache(tmp_path, monkeypatch):
    if not shadow.git_available():
        pytest.skip("git not available")
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "drift-state")
    proj = tmp_path / "proj"
    _populate(proj, {"a.py": "x", "pkg/b.py": "y"})
    _age(proj)

    shadow.run_shadow_pass("proj-cache", proj, {})

    cache_path = shadow.file_hash_cache_path("proj-cache")
    assert cache_path.exists()
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert set(data["files"]) == {"a.py", "pkg/b.py"}
    assert data["epoch"] == shadow.exclude_epoch(shadow.DEFAULT_EXCLUDES)


def test_run_shadow_pass_partial_persist_then_bootstrap(tmp_path, monkeypatch):
    """FIX-S3 (run_shadow_pass level): a truncated first run persists partial
    entries; the next run reuses them and completes without truncation."""
    if not shadow.git_available():
        pytest.skip("git not available")
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.setattr(shadow, "_DRIFT_STATE_DIR", tmp_path / "drift-state")
    proj = tmp_path / "proj"
    _populate(proj, {f"f{i}.py": f"V{i}" for i in range(8)})
    _age(proj)

    monkeypatch.setattr(shadow, "_DIGEST_MAX_FILES", 3)
    s1 = shadow.run_shadow_pass("proj-b", proj, {})
    assert s1["digest_truncated"] is True
    cf = shadow.file_hash_cache_path("proj-b")
    d1 = json.loads(cf.read_text(encoding="utf-8"))
    assert 0 < len(d1["files"]) <= 3  # partial entries persisted

    monkeypatch.setattr(shadow, "_DIGEST_MAX_FILES", 20000)
    s2 = shadow.run_shadow_pass("proj-b", proj, {})
    assert s2["digest_truncated"] is False
    d2 = json.loads(cf.read_text(encoding="utf-8"))
    assert len(d2["files"]) == 8
