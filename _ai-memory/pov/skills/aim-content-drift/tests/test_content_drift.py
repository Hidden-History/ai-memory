"""Tests for content_drift.py (BP-173 — content-drift detect/recommend/ack).

Covers the build-spec §10 + DONE WHEN scenarios:
  T1 — detect (DEFAULT) mutates nothing (sha256 unchanged, no ack/.bak written)
  T2 — MISSING / SUPERSEDED / ORPHAN classified correctly against a real template
  T3 — CUSTOMIZED content is NEVER recommended-for-removal (the cardinal guarantee)
  T4 — ACK suppresses; a reference-fingerprint change re-surfaces
  T5 — --prune-ack drops entries whose unit no longer drifts
  T7 — project-scoped (≥2 group_ids, no cross-project leak); real resolver via env
  + a realistic-size fixture: a fresh scaffold of all 8 real sanctum templates is clean
  + --emit-fingerprints leaves the templates byte-unchanged

Every test runs the script via subprocess against tmp_path fixtures built from the
REAL shipped templates/sidecars (no mocks; the real classify path is exercised).
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "content_drift.py"
REAL_ASSETS = SKILL_ROOT.parent / "aim-agent-sanctum-init" / "assets"

SANCTUM_FILES = {
    "BOND.md": "BOND-template.md",
    "CAPABILITIES.md": "CAPABILITIES-template.md",
    "CREED.md": "CREED-template.md",
    "INDEX.md": "INDEX-template.md",
    "LORE.md": "LORE-template.md",
    "MEMORY.md": "MEMORY-template.md",
    "PERSONA.md": "PERSONA-template.md",
    "PULSE.md": "PULSE-template.md",
}


def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _real_template(name: str) -> str:
    return (REAL_ASSETS / name).read_text(encoding="utf-8")


def _scaffold_lore(sanctum: Path) -> Path:
    """Write a fresh-scaffold LORE.md (a verbatim copy of the real template)."""
    sanctum.mkdir(parents=True, exist_ok=True)
    lore = sanctum / "LORE.md"
    lore.write_text(_real_template("LORE-template.md"), encoding="utf-8")
    return lore


def _copy_sidecars(dst: Path) -> Path:
    """Copy the real fingerprint sidecars to a writable tmp dir (for SUPERSEDED/ORPHAN
    construction)."""
    dst.mkdir(parents=True, exist_ok=True)
    for sc in REAL_ASSETS.glob("*.fingerprints.json"):
        shutil.copy(sc, dst / sc.name)
    return dst


def _load_sidecar(fp_dir: Path, name: str) -> dict:
    return json.loads((fp_dir / name).read_text(encoding="utf-8"))


def _write_sidecar(fp_dir: Path, name: str, data: dict) -> None:
    (fp_dir / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _unit(sidecar: dict, unit_id: str) -> dict:
    return next(u for u in sidecar["units"] if u["id"] == unit_id)


def _drop_section(lore_text: str, heading: str) -> str:
    """Remove a whole ``## heading`` section from a sanctum file (creates a MISSING)."""
    lines = lore_text.splitlines(keepends=True)
    out, skip = [], False
    for line in lines:
        s = line.strip()
        if s.startswith("## "):
            skip = s == heading
        elif s.startswith("# ") or s == "#":
            skip = False
        if not skip:
            out.append(line)
    return "".join(out)


# --- T1: detect is read-only --------------------------------------------------


def test_T1_detect_mutates_nothing(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    # Introduce real drift so there ARE findings — proving nothing is written even then.
    lore.write_text(
        _drop_section(lore.read_text(), "## Key Design Decisions"), encoding="utf-8"
    )
    before = _sha(lore)

    r = _run(str(sanctum), "--fingerprints-dir", str(REAL_ASSETS))
    assert r.returncode == 0, r.stderr
    assert "DETECT" in r.stdout and "read-only" in r.stdout
    assert "MISSING" in r.stdout  # the drift is reported

    assert _sha(lore) == before, "detect modified a sanctum file"
    assert not list(sanctum.glob("*.bak")), "detect wrote a backup"
    project_root = tmp_path / "_ai-memory"
    assert not (project_root / "content-drift-ack.json").exists(), "detect wrote an ack"


# --- T2: classification correctness against a real template -------------------


def test_T2_missing_classified(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    lore.write_text(
        _drop_section(lore.read_text(), "## Key Design Decisions"), encoding="utf-8"
    )

    r = _run(str(sanctum), "--fingerprints-dir", str(REAL_ASSETS))
    assert r.returncode == 0, r.stderr
    assert "MISSING" in r.stdout
    assert "LORE.md::key-design-decisions" in r.stdout


def test_T2_superseded_classified(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    _scaffold_lore(sanctum)  # operator keeps the CURRENT (soon-to-be-prior) framing
    fp = _copy_sidecars(tmp_path / "fp")
    sidecar = _load_sidecar(fp, "LORE-template.fingerprints.json")
    unit = _unit(sidecar, "system-architecture")
    # Simulate the reference evolving: the operator's current framing becomes a PRIOR,
    # and the reference adopts new framing the operator does not have.
    unit["prior"] = {unit["fingerprint"]: unit["guidance"]}
    unit["guidance"] = "_A brand-new architecture framing the reference now ships._"
    unit["fingerprint"] = "sha256:newfingerprint"
    _write_sidecar(fp, "LORE-template.fingerprints.json", sidecar)

    r = _run(str(sanctum), "--fingerprints-dir", str(fp), "--show-diff")
    assert r.returncode == 0, r.stderr
    assert "SUPERSEDED" in r.stdout
    assert "LORE.md::system-architecture" in r.stdout


def test_T2_orphan_classified(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    _scaffold_lore(sanctum)  # the section is a pristine, uncustomized remnant
    fp = _copy_sidecars(tmp_path / "fp")
    sidecar = _load_sidecar(fp, "LORE-template.fingerprints.json")
    _unit(sidecar, "patterns-conventions")["status"] = "orphan"
    _write_sidecar(fp, "LORE-template.fingerprints.json", sidecar)

    r = _run(str(sanctum), "--fingerprints-dir", str(fp))
    assert r.returncode == 0, r.stderr
    assert "ORPHAN" in r.stdout
    assert "LORE.md::patterns-conventions" in r.stdout


# --- T3: CUSTOMIZED is NEVER recommended-for-removal (cardinal) ---------------


def test_T3_operator_authored_section_never_flagged(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    # An entirely operator-authored section (no reference id) plus operator content
    # added under a reference section.
    lore.write_text(
        lore.read_text()
        + "\n## My Own Section\n\n- a deeply personal operator note worth keeping.\n",
        encoding="utf-8",
    )

    r = _run(str(sanctum), "--fingerprints-dir", str(REAL_ASSETS))
    assert r.returncode == 0, r.stderr
    # The operator's own section is invisible to the remove path.
    assert "my-own-section" not in r.stdout
    assert "ORPHAN" not in r.stdout
    assert "REMOVE" not in r.stdout
    # A fresh scaffold + an added custom section still has nothing recommended.
    assert "0 recommendation" in r.stdout


def test_T3_customized_orphan_section_is_kept_not_removed(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    # Operator has ADDED content under a section that the reference later orphans.
    lore.write_text(
        lore.read_text().replace(
            "## Patterns & Conventions\n",
            "## Patterns & Conventions\n\n- our house naming rule the operator wrote.\n",
        ),
        encoding="utf-8",
    )
    fp = _copy_sidecars(tmp_path / "fp")
    sidecar = _load_sidecar(fp, "LORE-template.fingerprints.json")
    _unit(sidecar, "patterns-conventions")["status"] = "orphan"
    _write_sidecar(fp, "LORE-template.fingerprints.json", sidecar)

    r = _run(str(sanctum), "--fingerprints-dir", str(fp))
    assert r.returncode == 0, r.stderr
    # The orphaned section now carries operator content → CUSTOMIZED, never removed.
    assert "ORPHAN" not in r.stdout
    assert "patterns-conventions" not in r.stdout


# --- T4: ACK suppresses; reference-fingerprint change re-surfaces -------------


def test_T4_ack_suppresses_then_resurfaces(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    lore.write_text(
        _drop_section(lore.read_text(), "## Key Design Decisions"), encoding="utf-8"
    )
    fp = _copy_sidecars(tmp_path / "fp")
    ack_file = tmp_path / "ack.json"
    key = "LORE.md::key-design-decisions"

    # Before ack: the recommendation is active.
    r0 = _run(str(sanctum), "--fingerprints-dir", str(fp), "--group-id", "proj")
    assert "MISSING" in r0.stdout

    # Ack it (writes the ack sidecar only).
    r1 = _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--group-id",
        "proj",
        "--ack-file",
        str(ack_file),
        "--ack",
        key,
    )
    assert r1.returncode == 0, r1.stderr
    assert ack_file.is_file()
    assert json.loads(ack_file.read_text())["acks"].get(key)

    # After ack: suppressed.
    r2 = _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--group-id",
        "proj",
        "--ack-file",
        str(ack_file),
    )
    assert "0 recommendation" in r2.stdout
    assert "acknowledged" in r2.stdout

    # The reference unit changes → re-surfaces (conservative re-surface rule).
    sidecar = _load_sidecar(fp, "LORE-template.fingerprints.json")
    _unit(sidecar, "key-design-decisions")["fingerprint"] = "sha256:changedref"
    _write_sidecar(fp, "LORE-template.fingerprints.json", sidecar)
    r3 = _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--group-id",
        "proj",
        "--ack-file",
        str(ack_file),
    )
    assert "MISSING" in r3.stdout
    assert "1 recommendation" in r3.stdout


# --- T5: --prune-ack drops entries whose unit no longer drifts ----------------


def test_T5_prune_ack_drops_resolved(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    full = lore.read_text()
    lore.write_text(_drop_section(full, "## Key Design Decisions"), encoding="utf-8")
    fp = _copy_sidecars(tmp_path / "fp")
    ack_file = tmp_path / "ack.json"
    key = "LORE.md::key-design-decisions"

    _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--group-id",
        "proj",
        "--ack-file",
        str(ack_file),
        "--ack",
        key,
    )
    assert key in json.loads(ack_file.read_text())["acks"]

    # The operator resolves the drift (restores the section) → the ack is now stale.
    lore.write_text(full, encoding="utf-8")
    r = _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--group-id",
        "proj",
        "--ack-file",
        str(ack_file),
        "--prune-ack",
    )
    assert r.returncode == 0, r.stderr
    assert "pruned stale ack" in r.stdout
    assert key not in json.loads(ack_file.read_text())["acks"]


# --- T7: project scope (≥2 group_ids, no leak) + the real resolver ------------


def test_T7_ack_file_scoped_to_other_project_is_ignored(tmp_path):
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    lore.write_text(
        _drop_section(lore.read_text(), "## Key Design Decisions"), encoding="utf-8"
    )
    fp = _copy_sidecars(tmp_path / "fp")
    key = "LORE.md::key-design-decisions"

    # Ack under project A.
    ack_a = tmp_path / "ack_a.json"
    _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--group-id",
        "projA",
        "--ack-file",
        str(ack_a),
        "--ack",
        key,
    )
    assert json.loads(ack_a.read_text())["project_id"] == "projA"

    # Project B detecting against project A's ack file: the ack must NOT leak.
    r = _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--group-id",
        "projB",
        "--ack-file",
        str(ack_a),
    )
    assert r.returncode == 0, r.stderr
    assert "no cross-project leak" in r.stdout
    assert "MISSING" in r.stdout  # the recommendation is active for project B

    # And project B refuses to overwrite project A's ack file.
    r2 = _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--group-id",
        "projB",
        "--ack-file",
        str(ack_a),
        "--ack",
        key,
    )
    assert r2.returncode != 0
    assert "refusing to overwrite" in (r2.stdout + r2.stderr)


def test_T7_scope_resolved_via_canonical_resolver(tmp_path, monkeypatch):
    """No --group-id: the project scope is resolved through the canonical
    resolve_project_id() (env tier), and the ack file is stamped with it."""
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    lore.write_text(
        _drop_section(lore.read_text(), "## Key Design Decisions"), encoding="utf-8"
    )
    fp = _copy_sidecars(tmp_path / "fp")
    ack_file = tmp_path / "ack.json"
    key = "LORE.md::key-design-decisions"

    import os

    env = dict(os.environ)
    env["AI_MEMORY_PROJECT_ID"] = "resolved-via-env"
    r = _run(
        str(sanctum),
        "--fingerprints-dir",
        str(fp),
        "--ack-file",
        str(ack_file),
        "--ack",
        key,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(ack_file.read_text())["project_id"] == "resolved-via-env"


# --- Realistic-size fixture: a fresh scaffold of all 8 real templates is clean -


def test_realistic_fresh_scaffold_all_eight_is_clean(tmp_path):
    """feedback_realistic_size_production_artifact_tests — every one of the 8 real
    sanctum templates, scaffolded verbatim, classifies as MATCH (zero drift) against
    the committed sidecars. Exercises the real classify path end to end, no mocks."""
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True)
    for op_name, template_name in SANCTUM_FILES.items():
        (sanctum / op_name).write_text(_real_template(template_name), encoding="utf-8")

    r = _run(str(sanctum), "--fingerprints-dir", str(REAL_ASSETS))
    assert r.returncode == 0, r.stderr
    assert "0 recommendation" in r.stdout, r.stdout
    assert "your sanctum is current" in r.stdout


# --- --emit-fingerprints leaves the templates byte-unchanged ------------------


def test_emit_fingerprints_does_not_touch_templates(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    before = {}
    for tpl in REAL_ASSETS.glob("*-template.md"):
        shutil.copy(tpl, assets / tpl.name)
        before[tpl.name] = _sha(assets / tpl.name)

    r = _run(str(assets), "--emit-fingerprints")
    assert r.returncode == 0, r.stderr

    for name, sha in before.items():
        assert _sha(assets / name) == sha, f"{name} was modified by --emit-fingerprints"
        assert (assets / (Path(name).stem + ".fingerprints.json")).is_file()
