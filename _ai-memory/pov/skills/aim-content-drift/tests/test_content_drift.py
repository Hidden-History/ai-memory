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


# --- HIGH-1 regression: a {placeholder} ORPHAN must not absorb operator prose ----

# Each affected placeholder-bearing unit (BP-173 §3): the reference framing is kept
# verbatim and only the {placeholder} token is resolved — once with a bare value
# (genuinely pristine → still ORPHAN), once with a value PLUS operator-authored prose
# (CUSTOMIZED → must never be recommended for removal). On b444740 the prose case was
# absorbed by the placeholder's ``.+?`` under ``fullmatch`` → false ORPHAN/REMOVE.
_PLACEHOLDER_ORPHAN_CASES = [
    (
        "BOND-template.md",
        "BOND.md",
        "owner",
        {"{user_name}": "Alice"},
        {
            "{user_name}": "Alice — principal eng; told me NEVER auto-merge, do not delete"
        },
    ),
    (
        "CREED-template.md",
        "CREED.md",
        "standing-orders",
        {"{communication_language}": "English"},
        {"{communication_language}": "English, but always be terse and never hedge"},
    ),
    (
        "PERSONA-template.md",
        "PERSONA.md",
        "identity",
        {"{birth_date}": "2026-05-30"},
        {"{birth_date}": "2026-05-30 (the day First Breath ran; never forget this)"},
    ),
    (
        "PERSONA-template.md",
        "PERSONA.md",
        "evolution-log",
        {"{birth_date}": "2026-05-30", "{user_name}": "Alice"},
        {
            "{birth_date}": "2026-05-30",
            "{user_name}": "Alice the operator who keeps editing this log herself",
        },
    ),
]


def _fill(template_text: str, repl: dict) -> str:
    out = template_text
    for ph, val in repl.items():
        out = out.replace(ph, val)
    return out


def _detect_orphan_case(tmp_path, template_name, op_name, unit_id, repl):
    """Scaffold the operator file with the unit's placeholder(s) resolved per ``repl``,
    mark that unit ORPHAN in the sidecar, and run detect (read-only). Returns stdout."""
    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    sanctum.mkdir(parents=True, exist_ok=True)
    (sanctum / op_name).write_text(
        _fill(_real_template(template_name), repl), encoding="utf-8"
    )
    fp = _copy_sidecars(tmp_path / "fp")
    sc_name = Path(template_name).stem + ".fingerprints.json"
    sidecar = _load_sidecar(fp, sc_name)
    _unit(sidecar, unit_id)["status"] = "orphan"
    _write_sidecar(fp, sc_name, sidecar)
    r = _run(str(sanctum), "--fingerprints-dir", str(fp))
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_HIGH1_placeholder_orphan_unit_level():
    """is_pristine_remnant: a value-only fill is pristine (True); a value + added
    operator prose is CUSTOMIZED (False). FAILS on b444740 (prose absorbed → True)."""
    sys.path.insert(0, str(SCRIPT.parent))
    import content_drift as cd

    for (
        template_name,
        _op,
        unit_id,
        value_only,
        customized,
    ) in _PLACEHOLDER_ORPHAN_CASES:
        sidecar = _load_sidecar(
            REAL_ASSETS, Path(template_name).stem + ".fingerprints.json"
        )
        guidance = _unit(sidecar, unit_id)["guidance"]
        pristine_body = cd.canonical_text([_fill(guidance, value_only)])
        custom_body = cd.canonical_text([_fill(guidance, customized)])
        assert (
            cd.is_pristine_remnant(guidance, pristine_body) is True
        ), f"{template_name}::{unit_id} value-only fill should be pristine (control)"
        assert (
            cd.is_pristine_remnant(guidance, custom_body) is False
        ), f"{template_name}::{unit_id} value+prose fill must be CUSTOMIZED, not pristine"


def test_HIGH1_placeholder_orphan_with_operator_prose_not_removed(tmp_path):
    """detect: an ORPHAN placeholder unit whose operator filled the value AND added
    prose is CUSTOMIZED — never recommended for removal (the cardinal guarantee)."""
    for (
        template_name,
        op_name,
        unit_id,
        _value_only,
        customized,
    ) in _PLACEHOLDER_ORPHAN_CASES:
        case_dir = tmp_path / unit_id
        out = _detect_orphan_case(case_dir, template_name, op_name, unit_id, customized)
        assert (
            "ORPHAN" not in out
        ), f"{op_name}::{unit_id} wrongly flagged ORPHAN\n{out}"
        assert (
            "REMOVE" not in out
        ), f"{op_name}::{unit_id} wrongly recommends REMOVE\n{out}"
        assert (
            f"{op_name}::{unit_id}" not in out
        ), f"{op_name}::{unit_id} surfaced\n{out}"


def test_HIGH1_placeholder_orphan_value_only_still_orphan(tmp_path):
    """Control (not over-broad): a genuinely-pristine remnant — placeholder resolved to
    a bare value, no operator content added — still classifies ORPHAN."""
    for (
        template_name,
        op_name,
        unit_id,
        value_only,
        _customized,
    ) in _PLACEHOLDER_ORPHAN_CASES:
        case_dir = tmp_path / unit_id
        out = _detect_orphan_case(case_dir, template_name, op_name, unit_id, value_only)
        assert (
            "ORPHAN" in out
        ), f"{op_name}::{unit_id} value-only should be ORPHAN\n{out}"
        assert f"{op_name}::{unit_id}" in out, f"{op_name}::{unit_id} missing\n{out}"


# --- MEDIUM-1 regression: a {placeholder} fill cannot carry punctuation-joined prose -

# c5b6a07 closed the space-separated-prose hole but left a narrower bypass: the value
# matcher treated an apostrophe/hyphen-joined run as a SINGLE token, so an unbounded
# "a-b-c-…" chain (or "a'b'c'…" run) read as one value and stayed within the word cap →
# operator prose absorbed → false ORPHAN/REMOVE. The bound now counts every sub-token,
# so a long punctuation-joined run exceeds the cap and classifies CUSTOMIZED (keep).

# A minimal reference framing with one placeholder (the BOND::owner shape).
_MED1_GUIDANCE = "**Name:** {user_name} _Filled during First Breath: who they are._"

# Punctuation-joined operator prose that MUST NOT read as a pristine fill (→ keep).
_MED1_PROSE_FILLS = [
    "Alice-principal-eng-NEVER-auto-merge-do-not-delete-my-files",  # hyphen chain
    "Alice'is'telling'you'never'to'merge",  # apostrophe-joined run
]
# Legitimate short value fills that MUST stay pristine (→ control ORPHAN still fires).
_MED1_LEGIT_FILLS = ["Mary-Jane", "O'Brien", "Alice Chen", "2026-05-30", "English"]


def test_MEDIUM1_punctuation_joined_prose_is_not_pristine():
    """is_pristine_remnant: an apostrophe/hyphen-joined operator-prose fill is
    CUSTOMIZED (False); a legit short value fill stays pristine (True). FAILS on
    c5b6a07 (the joined run collapsed to one token → absorbed → True)."""
    sys.path.insert(0, str(SCRIPT.parent))
    import content_drift as cd

    guidance = cd.canonical_text([_MED1_GUIDANCE])
    for prose in _MED1_PROSE_FILLS:
        body = cd.canonical_text([_MED1_GUIDANCE.replace("{user_name}", prose)])
        assert (
            cd.is_pristine_remnant(guidance, body) is False
        ), f"punctuation-joined prose {prose!r} must be CUSTOMIZED, not pristine"
    for legit in _MED1_LEGIT_FILLS:
        body = cd.canonical_text([_MED1_GUIDANCE.replace("{user_name}", legit)])
        assert (
            cd.is_pristine_remnant(guidance, body) is True
        ), f"legit short fill {legit!r} must stay pristine (control — ORPHAN must still fire)"


def test_MEDIUM1_punctuation_prose_orphan_not_removed(tmp_path):
    """detect: a BOND::owner ORPHAN whose operator filled the value with a hyphen-joined
    prose run is CUSTOMIZED — never recommended for removal (the cardinal guarantee)."""
    prose = {"{user_name}": "Alice-principal-eng-NEVER-auto-merge-do-not-delete"}
    out = _detect_orphan_case(
        tmp_path / "prose", "BOND-template.md", "BOND.md", "owner", prose
    )
    assert "ORPHAN" not in out, f"hyphen-joined prose wrongly flagged ORPHAN\n{out}"
    assert "REMOVE" not in out, f"hyphen-joined prose wrongly recommends REMOVE\n{out}"
    assert "BOND.md::owner" not in out, f"BOND.md::owner surfaced\n{out}"


def test_MEDIUM1_legit_short_fill_still_orphan(tmp_path):
    """Control (not over-broad): a BOND::owner ORPHAN whose operator left a hyphenated
    short name (Mary-Jane) as the only fill is a genuine pristine remnant → still
    ORPHAN. Proves the bound did not kill the matcher."""
    out = _detect_orphan_case(
        tmp_path / "legit",
        "BOND-template.md",
        "BOND.md",
        "owner",
        {"{user_name}": "Mary-Jane"},
    )
    assert "ORPHAN" in out, f"legit short fill should still be ORPHAN\n{out}"
    assert "BOND.md::owner" in out, f"BOND.md::owner missing\n{out}"


# --- LOW #3: an unresolved scope refuses a project-stamped ack (no cross-project leak)


def test_LOW3_offline_ignores_project_stamped_ack(tmp_path):
    """When the project scope is unresolvable, a project-stamped ack file is ignored
    (it could belong to another project) → findings are shown, not suppressed."""
    import os

    sanctum = tmp_path / "_ai-memory" / "sanctum" / "parzival"
    lore = _scaffold_lore(sanctum)
    lore.write_text(
        _drop_section(lore.read_text(), "## Key Design Decisions"), encoding="utf-8"
    )
    fp = _copy_sidecars(tmp_path / "fp")
    key = "LORE.md::key-design-decisions"
    ref_fp = _unit(
        _load_sidecar(fp, "LORE-template.fingerprints.json"), "key-design-decisions"
    )["fingerprint"]
    # A foreign, project-stamped ack that WOULD suppress the finding if applied.
    ack = tmp_path / "ack.json"
    ack.write_text(
        json.dumps(
            {
                "schema": 1,
                "project_id": "some-other-project",
                "acks": {key: {"reference_fingerprint": ref_fp, "class": "MISSING"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k != "AI_MEMORY_PROJECT_ID"}
    r = _run(
        str(sanctum), "--fingerprints-dir", str(fp), "--ack-file", str(ack), env=env
    )
    assert r.returncode == 0, r.stderr
    assert "project scope is unresolved" in r.stdout
    assert "MISSING" in r.stdout  # not suppressed by the foreign ack


# --- LOW #4: resolve_scope locates src by walking up (not a hard-coded depth) ------


def test_LOW4_resolve_scope_locates_src(monkeypatch):
    """resolve_scope finds the repo's src/memory by walking up from the script's real
    location (no hard-coded parents[N]) and delegates to the canonical resolver."""
    sys.path.insert(0, str(SCRIPT.parent))
    import content_drift as cd

    monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "scope-via-walkup")
    assert cd.resolve_scope(None, None) == "scope-via-walkup"


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
