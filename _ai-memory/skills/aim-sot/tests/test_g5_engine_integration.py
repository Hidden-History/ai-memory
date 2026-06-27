"""G5: engine integration — [CL] --shadow pass, verify S4 mutation gate, and the
[ST] consult rollup surface (TD-675).

- ``detect-propose run --shadow`` emits the structured ``findings`` pipe and the
  live ``drift_rollup`` in its JSON, and writes ONLY machine-local state (never
  an oversight register).
- verify S4 (schema-driven) REJECTS a non-enum ``drift_strategy`` — proving the
  value is validated, never executed (no arbitrary code execution).
- consult ``digest`` surfaces the live rollup for the [ST] ambient channel.

Run targeted only:
    pytest tests/test_g5_engine_integration.py
"""

import importlib.util
import io
import json
import sys
import types
from contextlib import redirect_stdout
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
shadow = _load("aim_sot_shadow")
verify = _load("aim_sot_verify")
consult = _load("aim_sot_consult")


# --------------------------------------------------------------------------- #
# verify S4 mutation gate — non-enum drift_strategy rejected, never executed
# --------------------------------------------------------------------------- #


def test_verify_s4_rejects_non_enum_drift_strategy():
    sc = verify._load_schema_constraints()
    assert "drift_strategy" in sc["entry_enums"]  # schema-driven, auto-validated
    bad = [{"id": "X", "drift_strategy": "rm -rf /"}]
    failures, _ = verify._check_S4(bad, sc)
    assert any(f["check"] == "S4" for f in failures)
    assert any("drift_strategy" in f["detail"] for f in failures)


def test_verify_s4_accepts_enum_drift_strategy():
    sc = verify._load_schema_constraints()
    good = [{"id": "X", "drift_strategy": "tree-digest"}]
    failures, _ = verify._check_S4(good, sc)
    assert not any(f["check"] == "S4" for f in failures)


# --------------------------------------------------------------------------- #
# consult digest — [ST] rollup surface
# --------------------------------------------------------------------------- #


def test_consult_digest_surfaces_rollup():
    entries = [
        {"id": "A", "kind": "library", "owner": "@t", "sot_location": "a/"},
    ]
    rollup = {"clean": 1, "changed": 2, "docs_stale": 3}
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = consult.cmd_digest(entries, True, rollup)
    assert rc == 0
    out = json.loads(buf.getvalue())
    assert out["drift_rollup"] == rollup

    # Text mode surfaces "changed" / "docs-stale".
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        consult.cmd_digest(entries, False, rollup)
    text = buf2.getvalue()
    assert "2 changed" in text and "3 docs-stale" in text


# --------------------------------------------------------------------------- #
# [CL] --shadow pass through cmd_run
# --------------------------------------------------------------------------- #


def _fake_memory(monkeypatch, project_id):
    fake_memory = types.ModuleType("memory")
    fake_project = types.ModuleType("memory.project")
    fake_project.resolve_project_id = lambda cwd=None, warn=True: project_id
    fake_memory.project = fake_project
    monkeypatch.setitem(sys.modules, "memory", fake_memory)
    monkeypatch.setitem(sys.modules, "memory.project", fake_project)


@pytest.mark.skipif(not shadow.git_available(), reason="git not available")
def test_cmd_run_shadow_emits_findings_and_rollup(tmp_path, monkeypatch):
    # Redirect ALL machine-local roots into tmp_path (never touch ~/.ai-memory).
    # The engine calls its OWN imported shadow instance (dp.shadow), so patch
    # that one's roots (a separate importlib load from the test's `shadow`).
    monkeypatch.setattr(dp, "_DRIFT_CACHE_DIR", tmp_path / "drift-state")
    monkeypatch.setattr(dp.shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(dp.shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.delenv("AIM_SOT_RECONFIGURE", raising=False)
    monkeypatch.setattr(
        dp, "_reindex_sot_entries", lambda *a, **k: dp.ReindexResult(True, 0)
    )
    project_id = "proj-clpass"
    _fake_memory(monkeypatch, project_id)

    # Conforming project root: <root>/.sot/registry.yaml.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
    sot = tmp_path / ".sot"
    sot.mkdir()
    (sot / "registry.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "entries": [
                    {
                        "id": "APP",
                        "kind": "application",
                        "boundary_type": "path",
                        "sot_location": "src/",
                        "owner": "@team",
                        "description": "the app",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = sot / "registry.yaml"

    args = SimpleNamespace(
        registry=str(registry), as_json=True, limit=20, all=False, shadow=True
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = dp.cmd_run(args)
    assert rc == 0
    out = json.loads(buf.getvalue())
    # The findings pipe + live rollup are present in the JSON output.
    assert "findings" in out and isinstance(out["findings"], list)
    assert "drift_rollup" in out
    assert {"clean", "changed", "docs_stale"} <= set(out["drift_rollup"])

    # The shadow baseline commit happened (machine-local), and the user tree is
    # untouched — no .git / .gitignore written into the project.
    assert dp.shadow.shadow_head(project_id, tmp_path) is not None
    assert not (tmp_path / ".git").exists()
    assert not (tmp_path / ".gitignore").exists()

    # The engine wrote ONLY the machine-local drift-state cache — no oversight
    # register file anywhere under the project tree.
    assert (tmp_path / "drift-state").exists()
    for name in ("INDEX.md", "CLOSED.md", "findings.md", "bugs.md"):
        assert not list(tmp_path.rglob(name))


def test_cmd_run_default_has_empty_findings_no_shadow(tmp_path, monkeypatch):
    """Behavior-preserving: the default `run` (no --shadow) does NOT invoke the
    shadow pass — findings is empty and no shadow repo is created."""
    monkeypatch.setattr(dp, "_DRIFT_CACHE_DIR", tmp_path / "drift-state")
    monkeypatch.setattr(dp.shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(
        dp, "_reindex_sot_entries", lambda *a, **k: dp.ReindexResult(True, 0)
    )
    _fake_memory(monkeypatch, "proj-noshadow")
    sot = tmp_path / ".sot"
    sot.mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x\n", encoding="utf-8")
    (sot / "registry.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "entries": [
                    {
                        "id": "APP",
                        "kind": "application",
                        "boundary_type": "path",
                        "sot_location": "src/",
                        "owner": "@team",
                        "description": "the app",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        registry=str(sot / "registry.yaml"),
        as_json=True,
        limit=20,
        all=False,
        shadow=False,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert dp.cmd_run(args) == 0
    out = json.loads(buf.getvalue())
    assert out["findings"] == []
    assert not (tmp_path / "sot-git").exists()  # no shadow repo created
