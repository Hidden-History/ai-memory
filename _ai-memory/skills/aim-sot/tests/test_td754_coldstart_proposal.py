"""TD-754: `verify --proposal <draft>` must work at cold-start — with NO
committed registry.

The registry-existence gate previously ran before the proposal load, so a
freshly-scaffolded ``.sot/registry.proposed.yaml`` (the only registry that
exists at cold-start) could not be verified — it hit the ``No registry found``
bail. The gate is now hoisted-and-branched so a proposal is gated without a
committed registry, while:
  - standalone ``verify`` (no --proposal) still requires a registry,
  - the TD-749 sentinel FAIL still fires at cold-start,
  - an arbitrary (non-``.sot/``) proposal path does not trigger an unbounded
    discovery scan.

Run targeted only:
    pytest tests/test_td754_coldstart_proposal.py
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


verify = _load("aim_sot_verify")
dp = _load("aim_sot_detect_propose")


def _fake_memory_stack(monkeypatch, project_id):
    fake_memory = types.ModuleType("memory")
    fake_project = types.ModuleType("memory.project")
    fake_project.resolve_project_id = lambda cwd=None, warn=True: project_id
    fake_memory.project = fake_project
    monkeypatch.setitem(sys.modules, "memory", fake_memory)
    monkeypatch.setitem(sys.modules, "memory.project", fake_project)


def _verify_args(**overrides):
    args = SimpleNamespace(
        registry=None,
        proposal=None,
        project_id=None,
        check_urls=False,
        exec_drift_checks=False,
        strict=False,
        as_json=True,
    )
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _write_cold_start_proposal(monkeypatch, tmp_path, capsys):
    """Produce a real registry.proposed.yaml via detect-propose (has sentinels)."""
    _fake_memory_stack(monkeypatch, "td754")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    dp_args = SimpleNamespace(
        registry=str(tmp_path / ".sot" / "registry.yaml"),
        as_json=True,
        limit=20,
        all=False,
        write_proposal=True,
        force=False,
        shadow=False,
    )
    assert dp.cmd_run(dp_args) == 0
    proposed = tmp_path / ".sot" / "registry.proposed.yaml"
    assert proposed.exists()
    assert not (tmp_path / ".sot" / "registry.yaml").exists()
    capsys.readouterr()  # drain detect-propose's own stdout before the verify run
    return proposed


def test_coldstart_proposal_returns_real_verdict_not_no_registry_bail(
    monkeypatch, tmp_path, capsys
):
    """A registry-less `verify --proposal` emits a verdict, not the bail."""
    monkeypatch.setattr(verify, "_resolve_project_id", lambda p: None)
    proposed = _write_cold_start_proposal(monkeypatch, tmp_path, capsys)

    rc = verify.cmd_run(_verify_args(proposal=str(proposed)))
    out = capsys.readouterr().out
    assert (
        "No registry found" not in out
    ), "cold-start proposal hit the no-registry bail"
    v = json.loads(out)
    assert v["verdict"] in {"PASS", "CONDITIONAL", "FAIL"}
    assert rc == 0  # non-strict always exits 0


def test_coldstart_proposal_sentinels_still_fail(monkeypatch, tmp_path, capsys):
    """TD-749 coupling: the producer's leftover sentinels FAIL at cold-start."""
    monkeypatch.setattr(verify, "_resolve_project_id", lambda p: None)
    proposed = _write_cold_start_proposal(monkeypatch, tmp_path, capsys)

    verify.cmd_run(_verify_args(proposal=str(proposed)))
    v = json.loads(capsys.readouterr().out)
    assert v["verdict"] == "FAIL"
    s1_fields = {f["detail"].split("'")[1] for f in v["failures"] if f["check"] == "S1"}
    assert {"owner", "description"} <= s1_fields


def test_coldstart_filled_proposal_no_sentinel_failure(monkeypatch, tmp_path, capsys):
    """A fully-filled cold-start proposal does NOT fail on the sentinel check."""
    monkeypatch.setattr(verify, "_resolve_project_id", lambda p: None)
    proposed = _write_cold_start_proposal(monkeypatch, tmp_path, capsys)

    data = yaml.safe_load(proposed.read_text(encoding="utf-8"))
    for e in data["entries"]:
        e["kind"] = "library"
        e["owner"] = "platform-team"
        e["description"] = "A real component."
        e["last_verified"] = "2026-07-01"
        e["provenance_note"] = "Bootstrapped and reviewed."
    proposed.write_text(yaml.safe_dump(data), encoding="utf-8")

    verify.cmd_run(_verify_args(proposal=str(proposed)))
    v = json.loads(capsys.readouterr().out)
    sentinel_fails = [f for f in v["failures"] if "TODO(human):" in f["detail"]]
    assert (
        sentinel_fails == []
    ), f"filled proposal still had sentinel fails: {sentinel_fails}"


def test_standalone_verify_no_registry_still_bails(monkeypatch, tmp_path, capsys):
    """No --proposal + no registry → unchanged `No registry found` bail."""
    monkeypatch.setattr(verify, "_resolve_project_id", lambda p: None)
    rc = verify.cmd_run(_verify_args(registry=str(tmp_path / ".sot" / "registry.yaml")))
    out = capsys.readouterr().out
    assert "No registry found" in out
    assert rc == 0  # non-strict


def test_standalone_verify_no_registry_strict_exits_1(monkeypatch, tmp_path):
    monkeypatch.setattr(verify, "_resolve_project_id", lambda p: None)
    rc = verify.cmd_run(
        _verify_args(registry=str(tmp_path / ".sot" / "registry.yaml"), strict=True)
    )
    assert rc == 1  # fail-closed: no verdict = exit 1


def test_arbitrary_proposal_path_no_unbounded_scan(monkeypatch, tmp_path, capsys):
    """A proposal NOT under a `.sot/` dir yields no derivable root → discovery is
    skipped (no unbounded scan), but declared paths still resolve and a verdict
    is emitted (robustness requirement)."""
    monkeypatch.setattr(verify, "_resolve_project_id", lambda p: None)

    # Sentinel that would explode if discovery ran against a bogus root.
    def _boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("discovery ran against a non-conforming proposal root")

    monkeypatch.setattr(verify, "_discover_candidates", _boom)

    prop = tmp_path / "loose_proposal.yaml"
    prop.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "id": "a",
                        "kind": "service",
                        "boundary_type": "component",
                        "sot_location": "a/",
                        "owner": "team",
                        "description": "desc",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rc = verify.cmd_run(_verify_args(proposal=str(prop)))
    v = json.loads(capsys.readouterr().out)
    assert v["verdict"] in {"PASS", "CONDITIONAL", "FAIL"}
    assert rc == 0
