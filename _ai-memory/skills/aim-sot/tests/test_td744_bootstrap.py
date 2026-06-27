"""TD-744: SOT auto-bootstrap — propose-and-approve staging proposal.

Covers the `--write-proposal` affordance on the cold-start `run` path:
    (a) no-registry + --write-proposal → staging file written with blank
        TODO(human) semantics + filled structural values;
    (b) second run skips an existing staging file unless --force;
    (c) committed registry present → additive candidates only, the staging
        bootstrap does NOT fire and the committed file is never written;
    (d) non-git project degrades — no owner-hint block;
    (e) `low` confidence tier emitted for weak (nested-source) signals.

BP-030 invariant: no code path writes/overwrites the committed
`.sot/registry.yaml`; the only writable artifact is `.sot/registry.proposed.yaml`.

Run targeted only:
    pytest tests/test_td744_bootstrap.py
"""

import importlib.util
import json
import os
import stat
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = _load("aim_sot_detect_propose")


def _fake_memory_stack(monkeypatch, project_id):
    """Stub memory.project.resolve_project_id so no real install is needed."""
    fake_memory = types.ModuleType("memory")
    fake_project = types.ModuleType("memory.project")
    fake_project.resolve_project_id = lambda cwd=None, warn=True: project_id
    fake_memory.project = fake_project
    monkeypatch.setitem(sys.modules, "memory", fake_memory)
    monkeypatch.setitem(sys.modules, "memory.project", fake_project)


def _cold_start_args(root: Path, **overrides):
    """Args routing cmd_run to cold-start: a non-existent registry path under root."""
    args = SimpleNamespace(
        registry=str(root / ".sot" / "registry.yaml"),
        as_json=True,
        limit=20,
        all=False,
        write_proposal=False,
        force=False,
        shadow=False,
    )
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


# (a) -------------------------------------------------------------------------
def test_write_proposal_writes_staging_file_with_todo_semantics(monkeypatch, tmp_path):
    _fake_memory_stack(monkeypatch, "td744-a")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    args = _cold_start_args(tmp_path, write_proposal=True)
    rc = dp.cmd_run(args)
    assert rc == 0

    proposed = tmp_path / ".sot" / "registry.proposed.yaml"
    committed = tmp_path / ".sot" / "registry.yaml"
    assert proposed.exists(), "staging proposal not written"
    assert not committed.exists(), "BP-030 violated: committed registry was written"

    data = yaml.safe_load(proposed.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert data["entries"], "no entries in staging proposal"
    entry = next(e for e in data["entries"] if e["sot_location"] == "./")

    # Structural fields filled with real values.
    assert entry["boundary_type"] == "component"
    assert entry["sot_location"] == "./"
    assert entry["status"] == "proposed"
    assert entry["added_by"] == "aim-sot bootstrap"

    # Every human-owned semantic field is a TODO(human) placeholder (BP-029).
    for field in ("kind", "owner", "description", "last_verified", "provenance_note"):
        assert entry[field].startswith(
            "TODO(human):"
        ), f"{field} not a TODO placeholder"

    # confidence + inferred_from ride as comments only — they are not registry
    # schema fields (additionalProperties:false) and must never leak into the
    # parsed entry body.
    for field in ("confidence", "inferred_from"):
        assert field not in entry, f"{field} leaked into entry body"


def test_write_proposal_staging_file_is_owner_only(monkeypatch, tmp_path):
    """Staging draft is created owner-only (0o600), never world/group readable
    (CodeQL py/overly-permissive-file-permissions)."""
    _fake_memory_stack(monkeypatch, "td744-perms")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    # Pin umask so the == 0o600 assertion can't be umask-flaky.
    old_umask = os.umask(0o022)
    try:
        rc = dp.cmd_run(_cold_start_args(tmp_path, write_proposal=True))
    finally:
        os.umask(old_umask)
    assert rc == 0

    proposed = tmp_path / ".sot" / "registry.proposed.yaml"
    assert proposed.exists(), "staging proposal not written"
    assert stat.S_IMODE(os.stat(proposed).st_mode) == 0o600


def test_write_proposal_force_overwrite_resets_stale_perms(tmp_path):
    """A stale world-readable (0o644) staging file overwritten with --force must
    come back owner-only: O_TRUNC reuses the inode without resetting mode, so the
    fchmod is what forces 0o600 on the overwrite path."""
    sot_dir = tmp_path / ".sot"
    sot_dir.mkdir(parents=True)
    proposed = sot_dir / dp._PROPOSED_FILENAME
    proposed.write_text("stale\n", encoding="utf-8")
    os.chmod(proposed, 0o644)
    assert stat.S_IMODE(os.stat(proposed).st_mode) == 0o644

    written, _ = dp._write_proposal_file(
        proposed, [], {}, scan_root=tmp_path, force=True
    )
    assert written
    assert stat.S_IMODE(os.stat(proposed).st_mode) == 0o600


# (b) -------------------------------------------------------------------------
def test_second_run_skips_existing_unless_force(monkeypatch, tmp_path):
    _fake_memory_stack(monkeypatch, "td744-b")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    proposed = tmp_path / ".sot" / "registry.proposed.yaml"

    # First write.
    assert dp.cmd_run(_cold_start_args(tmp_path, write_proposal=True)) == 0
    assert proposed.exists()

    # Mutate the draft to simulate in-progress human edits.
    sentinel = proposed.read_text(encoding="utf-8") + "\n# HUMAN EDIT SENTINEL\n"
    proposed.write_text(sentinel, encoding="utf-8")

    # Second run WITHOUT --force → skip, edits preserved.
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert dp.cmd_run(_cold_start_args(tmp_path, write_proposal=True)) == 0
    assert "# HUMAN EDIT SENTINEL" in proposed.read_text(encoding="utf-8")
    payload = json.loads(buf.getvalue())
    assert payload["proposal_written"] is False

    # Third run WITH --force → overwrite, sentinel gone.
    assert dp.cmd_run(_cold_start_args(tmp_path, write_proposal=True, force=True)) == 0
    assert "# HUMAN EDIT SENTINEL" not in proposed.read_text(encoding="utf-8")


# (c) -------------------------------------------------------------------------
def test_committed_registry_present_bootstrap_does_not_fire(monkeypatch, tmp_path):
    project_id = "td744-c"
    _fake_memory_stack(monkeypatch, project_id)

    # A committed registry exists → registry-present path takes over.
    sot_dir = tmp_path / ".sot"
    sot_dir.mkdir(parents=True)
    committed = sot_dir / "registry.yaml"
    committed.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "id": "core",
                        "kind": "library",
                        "boundary_type": "path",
                        "sot_location": "core/",
                        "owner": "@team",
                        "description": "core lib",
                        "status": "active",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    committed_before = committed.read_text(encoding="utf-8")

    # Seed the 5a cache with the current sha so reg_changed is False (no reindex,
    # which would need the memory stack).
    cache_dir = tmp_path / "drift-state"
    monkeypatch.setattr(dp, "_DRIFT_CACHE_DIR", cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"sot_drift_{project_id}.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "project_id": project_id,
                "generated_at": "",
                "registry_sha": dp._registry_sha(committed),
                "components": {},
            }
        ),
        encoding="utf-8",
    )

    # --write-proposal is passed, but the registry-present path must ignore it.
    args = SimpleNamespace(
        registry=str(committed),
        as_json=True,
        limit=20,
        all=False,
        write_proposal=True,
        force=False,
        shadow=False,
    )
    rc = dp.cmd_run(args)
    assert rc == 0

    assert not (
        sot_dir / "registry.proposed.yaml"
    ).exists(), "bootstrap fired with a committed registry"
    assert (
        committed.read_text(encoding="utf-8") == committed_before
    ), "committed registry mutated"


# (d) -------------------------------------------------------------------------
def test_non_git_project_degrades_no_owner_hints(monkeypatch, tmp_path):
    _fake_memory_stack(monkeypatch, "td744-d")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    # Force the non-git degrade path deterministically (independent of where the
    # pytest tmp dir lives): git rev-parse reports "not a work tree".
    monkeypatch.setattr(dp, "_git_owner_candidates", lambda root, locs, top_n=3: {})

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert dp.cmd_run(_cold_start_args(tmp_path, write_proposal=True)) == 0
    payload = json.loads(buf.getvalue())
    assert payload["owner_candidates"] == {}

    text = (tmp_path / ".sot" / "registry.proposed.yaml").read_text(encoding="utf-8")
    assert (
        "owner_candidates" not in text
    ), "owner-hint block present on a non-git degrade"


def test_git_owner_candidates_returns_empty_on_non_git(tmp_path):
    """Direct unit check: the helper degrades silently outside a git repo."""
    # A bare temp dir is not inside a work tree (git rev-parse → non-true/error).
    assert dp._git_owner_candidates(tmp_path, ["./"]) == {}


# (e) -------------------------------------------------------------------------
def test_low_confidence_tier_for_nested_source_dir(monkeypatch, tmp_path):
    _fake_memory_stack(monkeypatch, "td744-e")
    # Nested source dir (depth >= 2), no co-located manifest → low confidence.
    nested = tmp_path / "backend" / "src"
    nested.mkdir(parents=True)
    (nested / "module.py").write_text("x = 1\n", encoding="utf-8")

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert dp.cmd_run(_cold_start_args(tmp_path)) == 0
    payload = json.loads(buf.getvalue())

    low = [c for c in payload["candidate_proposals"] if c.get("confidence") == "low"]
    assert low, "no low-confidence candidate emitted for a nested source dir"
    assert any(
        c["sot_location"] == "backend/src/"
        and c["inferred_from"] == "nested_source_directory"
        for c in low
    )


# (f) BP-030 hardening ---------------------------------------------------------
def test_dangling_symlink_does_not_create_committed_registry(monkeypatch, tmp_path):
    """A pre-existing dangling ``registry.proposed.yaml -> registry.yaml`` symlink
    must NOT be followed by cold-start --write-proposal — the committed registry
    is never created through the link (BP-030)."""
    _fake_memory_stack(monkeypatch, "td744-sym")
    (tmp_path / "package.json").write_text('{"name":"x"}\n', encoding="utf-8")
    sot_dir = tmp_path / ".sot"
    sot_dir.mkdir(parents=True)
    proposed = sot_dir / "registry.proposed.yaml"
    committed = sot_dir / "registry.yaml"
    # Planted dangling symlink (BP-030 bypass attempt).
    proposed.symlink_to("registry.yaml")

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = dp.cmd_run(_cold_start_args(tmp_path, write_proposal=True))
    assert rc == 0
    # Mirrors the repro invariant `test -f X && ! test -L X`: no regular committed
    # registry.yaml was created by following the link.
    assert not (
        committed.exists() and not committed.is_symlink()
    ), "BP-030 violated: writing through the symlink created committed registry.yaml"
    # The planted symlink is refused, not written through.
    assert proposed.is_symlink()


def test_write_proposal_file_rejects_traversal_and_symlink(tmp_path):
    """`_write_proposal_file` rejects a target resolving outside <scan_root>/.sot/
    and a symlinked target — basename match alone is insufficient (BP-030)."""
    sot_dir = tmp_path / ".sot"
    sot_dir.mkdir(parents=True)

    # Traversal: passes the basename check but resolves outside <scan_root>/.sot/.
    traversal = sot_dir / ".." / dp._PROPOSED_FILENAME
    with pytest.raises(ValueError):
        dp._write_proposal_file(traversal, [], {}, scan_root=tmp_path, force=True)

    # Symlinked target: refused even with --force (never followed).
    link = sot_dir / dp._PROPOSED_FILENAME
    link.symlink_to("registry.yaml")
    with pytest.raises(ValueError):
        dp._write_proposal_file(link, [], {}, scan_root=tmp_path, force=True)


# (g) FIX 1 — adversarial candidate names yield a parseable draft -------------
_HOSTILE_NAMES = ["foo: bar", "@weird", "[bracket", 'foo"bar']


def test_format_proposal_yaml_escapes_adversarial_names():
    """Candidate id / sot_location values straight from directory names may carry
    YAML metacharacters; rendering via yaml.safe_dump must keep the draft
    round-trippable through yaml.safe_load with structural values intact and
    semantics still TODO(human)."""
    candidates = [
        {
            "id": name,
            "boundary_type": "path",
            "sot_location": name + "/",
            "confidence": "medium",
            "inferred_from": "top_level_directory",
        }
        for name in _HOSTILE_NAMES
    ]
    body = dp._format_proposal_yaml(candidates, {})

    data = yaml.safe_load(body)  # must not raise
    by_loc = {e["sot_location"]: e for e in data["entries"]}
    for name in _HOSTILE_NAMES:
        entry = by_loc[name + "/"]
        # Structural values intact through the escape round-trip.
        assert entry["id"] == name
        assert entry["boundary_type"] == "path"
        assert entry["status"] == "proposed"
        assert entry["added_by"] == "aim-sot bootstrap"
        # Semantics still human-owned placeholders.
        for field in (
            "kind",
            "owner",
            "description",
            "last_verified",
            "provenance_note",
        ):
            assert entry[field].startswith("TODO(human):")
        # confidence / inferred_from never leak into the entry body.
        for field in ("confidence", "inferred_from"):
            assert field not in entry
    # confidence/inferred_from ride as comments only.
    assert "# confidence:" in body


def test_owner_candidate_with_embedded_newline_keeps_draft_parseable():
    """An owner_candidates location (dir-derived) or git hint carrying an embedded
    newline must not split its advisory ``#`` comment line into uncommented YAML;
    control-char sanitization keeps the draft round-trippable via yaml.safe_load."""
    candidates = [
        {
            "id": "svc",
            "boundary_type": "path",
            "sot_location": "svc/",
            "confidence": "medium",
            "inferred_from": "top_level_directory",
        }
    ]
    owner_candidates = {"ev\nil": [{"name": "a\nb", "commits": 3}]}
    body = dp._format_proposal_yaml(candidates, owner_candidates)

    yaml.safe_load(body)  # must not raise (ScannerError before sanitization)
    # Newline collapsed to a space; the hint stays on one commented line.
    assert "#   ev il: a b (3)" in body


def test_adversarial_candidate_dirs_produce_parseable_draft(monkeypatch, tmp_path):
    """End-to-end: directories with adversarial names flow through discovery +
    --write-proposal into a draft that yaml.safe_load parses cleanly (FIX 1)."""
    _fake_memory_stack(monkeypatch, "td744-hostile")
    # Deterministic non-git degrade for the owner-hint helper.
    monkeypatch.setattr(dp, "_git_owner_candidates", lambda root, locs, top_n=3: {})
    for name in _HOSTILE_NAMES:
        (tmp_path / name).mkdir()

    assert dp.cmd_run(_cold_start_args(tmp_path, write_proposal=True)) == 0

    draft = (tmp_path / ".sot" / "registry.proposed.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(draft)  # must not raise
    by_loc = {e["sot_location"]: e for e in data["entries"]}
    for name in _HOSTILE_NAMES:
        entry = by_loc[name + "/"]
        assert entry["id"] == name
        assert entry["status"] == "proposed"
        for field in (
            "kind",
            "owner",
            "description",
            "last_verified",
            "provenance_note",
        ):
            assert entry[field].startswith("TODO(human):")
        for field in ("confidence", "inferred_from"):
            assert field not in entry


# (h) FIX 5 — a symlinked .sot directory is itself rejected -------------------
def test_write_proposal_file_rejects_symlinked_sot_dir(tmp_path):
    """When ``.sot`` is itself a pre-existing symlink to an external dir, the
    resolved-parent comparison would pass (both sides resolve through the link).
    Guard 2 must reject the symlinked ``.sot`` so the draft never lands outside
    the project (defense-in-depth)."""
    external = tmp_path / "external"
    external.mkdir()
    sot_link = tmp_path / ".sot"
    sot_link.symlink_to(external, target_is_directory=True)

    target = sot_link / dp._PROPOSED_FILENAME
    with pytest.raises(ValueError):
        dp._write_proposal_file(target, [], {}, scan_root=tmp_path, force=True)
    # Nothing was written through the link.
    assert not (external / dp._PROPOSED_FILENAME).exists()
