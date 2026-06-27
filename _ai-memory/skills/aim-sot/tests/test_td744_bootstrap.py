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
import sys
import types
from pathlib import Path
from types import SimpleNamespace

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
