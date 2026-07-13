"""Regression tests for the managed-file deploy-parity gate (BP-186, PLAN-032 P2).

Covers:
  * BUG-527 — the source-side structural gate flags a refresh-class deploy `cp`
    dominated by the hook-config force-gate, and passes once decoupled.
  * BUG-528 — the structural gate flags a set/dir class with no prune path, and
    passes once a prune loop exists.
  * BUG-526 — every fixed adapter entrypoint resolves to a file that exists, and
    no template still cites a broken path.
  * TD-815-1 — the deployed story-complete.md hash is registered for self-heal.
  * Runtime deployed-vs-source: stale/orphan deployments FAIL; a fresh deployment
    PASSES; user-owned preserve files are never flagged (F7).
  * `--check` blocks on ERROR; `--report` never blocks.

These tests live under tests/ (CI-collected), never src/memory/adapters/tests/
(CI-orphaned — TECH-DEBT-812).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODPATH = REPO / "scripts" / "deploy_parity" / "deploy_parity.py"
REGISTRY = REPO / "scripts" / "deploy_parity" / "managed-files.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("deploy_parity", MODPATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["deploy_parity"] = mod  # needed for dataclass __module__ resolution
    spec.loader.exec_module(mod)
    return mod


dp = _load_module()


# ── Synthetic install.sh fixtures for the structural gate ───────────────────

_FORCE_GATED = """\
write_gemini_config() {
    local force="${4:-false}"
    if [[ -f "$config_file" ]] && grep -q "AI_MEMORY_INSTALL_DIR" "$config_file"; then
        if [[ "$force" != "true" ]]; then
            return 0
        fi
    fi
    mkdir -p "$project_path/.gemini/commands"
    cp "$install_dir/src/memory/adapters/templates/gemini/"*.toml "$project_path/.gemini/commands/"
}

deploy_parzival_shims() {
    cp -r "$src_commands/"* "$PROJECT_PATH/.claude/commands/pov/"
}
"""

_DECOUPLED = """\
write_gemini_config() {
    local force="${4:-false}"
    mkdir -p "$project_path/.gemini/commands"
    cp "$install_dir/src/memory/adapters/templates/gemini/"*.toml "$project_path/.gemini/commands/"
    if [[ -f "$config_file" ]] && grep -q "AI_MEMORY_INSTALL_DIR" "$config_file"; then
        if [[ "$force" != "true" ]]; then
            return 0
        fi
    fi
}

deploy_parzival_shims() {
    prune_pov_shims "$PROJECT_PATH/.claude/commands/pov" "$src_commands"
    cp -r "$src_commands/"* "$PROJECT_PATH/.claude/commands/pov/"
}
"""

_MIN_CLASSES = [
    {
        "id": "gemini_commands",
        "class": "MANAGED_REFRESH_SET",
        "deploy_fn": "write_gemini_config",
        "ownership": {"kind": "glob", "pattern": "*.toml"},
        "source_glob": "{INSTALL_DIR}/src/memory/adapters/templates/gemini/*.toml",
        "target_dir": "{PROJECT}/.gemini/commands",
        "refresh": "unconditional",
    },
    {
        "id": "pov_command_shims",
        "class": "MANAGED_REFRESH_SET",
        "deploy_fn": "deploy_parzival_shims",
        "ownership": {"kind": "directory"},
        "source_dir": "{INSTALL_DIR}/.claude/commands/pov",
        "target_dir": "{PROJECT}/.claude/commands/pov",
        "prune": "required",
    },
]


def _write_repo(tmp_path: Path, install_sh: str) -> Path:
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "install.sh").write_text(install_sh)
    return tmp_path


# ── Structural gate (BUG-527 / BUG-528) ─────────────────────────────────────


def test_structural_flags_forcegated_refresh_and_missing_prune(tmp_path):
    repo = _write_repo(tmp_path, _FORCE_GATED)
    verdicts = {f.verdict for f in dp.source_side_findings(repo, _MIN_CLASSES)}
    assert "REFRESH_FORCE_GATED" in verdicts  # BUG-527
    assert "PRUNE_MISSING" in verdicts  # BUG-528


def test_structural_passes_when_decoupled_and_pruned(tmp_path):
    repo = _write_repo(tmp_path, _DECOUPLED)
    findings = dp.source_side_findings(repo, _MIN_CLASSES)
    verdicts = {f.verdict for f in findings}
    assert "REFRESH_FORCE_GATED" not in verdicts
    assert "PRUNE_MISSING" not in verdicts
    assert [f for f in findings if f.severity == dp.ERROR] == []


def test_structural_gate_clean_on_real_repo():
    """The shipped install.sh + registry must have zero structural ERRORs."""
    classes = dp.load_registry(REGISTRY)
    errors = [
        f for f in dp.source_side_findings(REPO, classes) if f.severity == dp.ERROR
    ]
    assert errors == [], [f.render() for f in errors]


# ── BUG-526: adapter entrypoints resolve to real files ──────────────────────

_FIXED_ENTRYPOINTS = {
    "gemini/memory-status.toml": [
        "scripts/memory/run-with-env.sh",
        "scripts/memory/aim_status.py",
    ],
    "gemini/save-memory.toml": [".claude/hooks/scripts/manual_save_memory.py"],
    "cursor/memory-status/SKILL.md": [
        "scripts/memory/run-with-env.sh",
        "scripts/memory/aim_status.py",
    ],
    "cursor/save-memory/SKILL.md": [".claude/hooks/scripts/manual_save_memory.py"],
    "codex/memory-status/SKILL.md": [
        "scripts/memory/run-with-env.sh",
        "scripts/memory/aim_status.py",
    ],
}

_BROKEN_PATHS = [
    "src/memory/status_cli.py",
    "src/memory/save_cli.py",
    "src/memory/cli/status.py",
    "adapters/claude/manual_save_memory.py",
]


@pytest.mark.parametrize("rel,scripts", _FIXED_ENTRYPOINTS.items())
def test_adapter_entrypoints_exist_and_no_broken_paths(rel, scripts):
    content = (REPO / "src/memory/adapters/templates" / rel).read_text()
    for script in scripts:
        assert script in content, f"{rel} no longer references {script}"
        assert (
            REPO / script
        ).exists(), f"{rel} entrypoint {script} does not exist in repo"
    for broken in _BROKEN_PATHS:
        assert broken not in content, f"{rel} still cites broken path {broken}"


def test_codex_has_no_save_memory_template():
    """Intentional installer loop gap (BP-172) — must stay absent (out of scope)."""
    assert not (REPO / "src/memory/adapters/templates/codex/save-memory").exists()


# ── TD-815-1: deployed story-complete.md hash registered ────────────────────


def test_story_complete_deployed_hash_registered():
    registry = (REPO / "templates/known-oversight-template-versions.txt").read_text()
    line = (
        "verification/checklists/story-complete.md\t"
        "cdae71deb346748bb0849c3daf5b56e12eaa81e1f9dbf76cbf063e3362e54ef1"
    )
    assert line in registry


# ── Runtime deployed-vs-source gate ─────────────────────────────────────────


def _runtime_classes():
    return [
        {
            "id": "gemini_commands",
            "class": "MANAGED_REFRESH_SET",
            "deploy_fn": "write_gemini_config",
            "ownership": {"kind": "glob", "pattern": "*.toml"},
            "source_glob": "{INSTALL_DIR}/src/memory/adapters/templates/gemini/*.toml",
            "target_dir": "{PROJECT}/.gemini/commands",
            "refresh": "unconditional",
        },
        {
            "id": "pov_command_shims",
            "class": "MANAGED_REFRESH_SET",
            "deploy_fn": "deploy_parzival_shims",
            "ownership": {"kind": "directory"},
            "source_dir": "{INSTALL_DIR}/.claude/commands/pov",
            "target_dir": "{PROJECT}/.claude/commands/pov",
            "prune": "required",
        },
        {
            "id": "gemini_settings",
            "class": "USER_OWNED_PRESERVE",
            "ownership": {"kind": "user"},
            "target": "{PROJECT}/.gemini/settings.json",
        },
    ]


def _seed_deploy(tmp_path: Path, *, toml_body: str, pov_extra: str | None):
    install = tmp_path / "install"
    project = tmp_path / "project"
    # Source templates.
    gemini_src = install / "src/memory/adapters/templates/gemini"
    gemini_src.mkdir(parents=True)
    (gemini_src / "search-memory.toml").write_text('description = "canonical"\n')
    pov_src = install / ".claude/commands/pov"
    pov_src.mkdir(parents=True)
    (pov_src / "parzival.md").write_text("# parzival\n")
    # Deployed project.
    gemini_dep = project / ".gemini/commands"
    gemini_dep.mkdir(parents=True)
    (gemini_dep / "search-memory.toml").write_text(toml_body)
    pov_dep = project / ".claude/commands/pov"
    pov_dep.mkdir(parents=True)
    (pov_dep / "parzival.md").write_text("# parzival\n")
    if pov_extra:
        (pov_dep / pov_extra).write_text("# retired shim\n")
    # User-owned preserve file with hand edits.
    (project / ".gemini").mkdir(exist_ok=True)
    (project / ".gemini/settings.json").write_text('{"user":"do not touch"}\n')
    return str(install), str(project)


def test_runtime_fresh_deploy_is_clean(tmp_path):
    install, project = _seed_deploy(
        tmp_path, toml_body='description = "canonical"\n', pov_extra=None
    )
    findings = dp.runtime_findings(install, project, _runtime_classes())
    assert [f for f in findings if f.severity == dp.ERROR] == [], [
        f.render() for f in findings
    ]


def test_runtime_stale_and_orphan_fail(tmp_path):
    install, project = _seed_deploy(
        tmp_path,
        toml_body='description = "STALE broken form"\n',
        pov_extra="parzival-team.md",
    )
    findings = dp.runtime_findings(install, project, _runtime_classes())
    verdicts = {f.verdict for f in findings if f.severity == dp.ERROR}
    assert "STALE_DRIFT" in verdicts  # F1: adapter drift
    assert "ORPHAN_RETIRED" in verdicts  # F3: un-pruned retired pov shim


def test_runtime_preserve_file_never_flagged(tmp_path):
    """F7: a user-owned preserve file is never reported (and never compared)."""
    install, project = _seed_deploy(
        tmp_path, toml_body='description = "canonical"\n', pov_extra=None
    )
    findings = dp.runtime_findings(install, project, _runtime_classes())
    assert all(f.class_id != "gemini_settings" for f in findings)


# ── CLI contract: --check blocks, --report does not ─────────────────────────


def _min_registry(tmp_path: Path) -> Path:
    import yaml

    reg = tmp_path / "managed-files.yaml"
    reg.write_text(yaml.safe_dump({"classes": _MIN_CLASSES}))
    return reg


def test_cli_check_blocks_on_error(tmp_path, capsys):
    repo = _write_repo(tmp_path, _FORCE_GATED)
    rc = dp.main(
        ["--check", "--repo", str(repo), "--registry", str(_min_registry(tmp_path))]
    )
    assert rc == 1


def test_cli_report_never_blocks(tmp_path, capsys):
    repo = _write_repo(tmp_path, _FORCE_GATED)
    rc = dp.main(
        ["--report", "--repo", str(repo), "--registry", str(_min_registry(tmp_path))]
    )
    assert rc == 0


def test_cli_check_passes_when_clean(tmp_path, capsys):
    repo = _write_repo(tmp_path, _DECOUPLED)
    rc = dp.main(
        ["--check", "--repo", str(repo), "--registry", str(_min_registry(tmp_path))]
    )
    assert rc == 0
