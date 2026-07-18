"""Tests for the C2/C4/C5 template-parity CI gates (PLAN-035 P2 Phase B
Wave-2; C4-design.md §3).

Unlike `template_parity_oracle.py` (report-only, per-user-project),
`ci_gates.py` is CI-blocking and source-repo-only. Per gate:
  - a clean-tree pass against the real AI-Memory source tree (exit 0, no
    findings of that gate's verdict);
  - a seeded-violation fixture under
    `tests/fixtures/template_parity/ci_gates/` that fails (exit non-zero).

C4(b)'s combined-run invariant asserts a clean tree (zero findings): the
`oversight/tasks/`, `oversight/reports/`, and `oversight/deferrals/` gaps are
now backed by registered templates (PLAN-035 P2.6), and the `oversight/archive/`
reference was reconciled to a per-area example (§3.5 case no longer applies).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODPATH = REPO / "scripts" / "template_parity" / "ci_gates.py"
FIXTURES = REPO / "tests" / "fixtures" / "template_parity" / "ci_gates"


def _load_module():
    spec = importlib.util.spec_from_file_location("ci_gates", MODPATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["ci_gates"] = mod
    spec.loader.exec_module(mod)
    return mod


gates = _load_module()


def _run_cli(repo_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MODPATH), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
    )


def _run_cli_json(repo_root: Path) -> tuple[subprocess.CompletedProcess, list]:
    result = subprocess.run(
        [
            sys.executable,
            str(MODPATH),
            "--repo-root",
            str(repo_root),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    return result, json.loads(result.stdout)


# ── C2 — template registration + valid `produces` ────────────────────────────


def test_c2_clean_tree_real_repo():
    entries = gates.load_registry(
        REPO / "scripts" / "template_parity" / "oversight-templates.yaml"
    )
    findings = gates.check_c2_registration(REPO / "templates" / "oversight", entries)
    assert findings == []


def test_c2_seeded_fixture_fails():
    result, findings = _run_cli_json(FIXTURES / "c2_seeded")
    assert result.returncode != 0
    paths_by_verdict = {f["verdict"]: f["path"] for f in findings}
    assert (
        paths_by_verdict.get("TEMPLATE_UNREGISTERED")
        == "templates/oversight/unregistered.md"
    )
    assert paths_by_verdict.get("PRODUCES_INVALID") == "templates/oversight/stripped.md"
    # the correctly registered, valid-produces entry must not be flagged
    assert all(f["path"] != "templates/oversight/registered.md" for f in findings)


def test_c2_registration_unregistered_template(tmp_path):
    templates_dir = tmp_path / "templates" / "oversight"
    (templates_dir).mkdir(parents=True)
    (templates_dir / "orphan.md").write_text("# Orphan\n")
    findings = gates.check_c2_registration(templates_dir, [])
    assert len(findings) == 1
    assert findings[0].verdict == gates.TEMPLATE_UNREGISTERED
    assert findings[0].path == "templates/oversight/orphan.md"


def test_c2_registration_missing_produces(tmp_path):
    templates_dir = tmp_path / "templates" / "oversight"
    templates_dir.mkdir(parents=True)
    (templates_dir / "known.md").write_text("# Known\n")
    entries = [
        {"template": "templates/oversight/known.md", "target": "x", "class": "register"}
    ]
    findings = gates.check_c2_registration(templates_dir, entries)
    assert len(findings) == 1
    assert findings[0].verdict == gates.PRODUCES_INVALID


def test_c2_registration_invalid_produces_value(tmp_path):
    templates_dir = tmp_path / "templates" / "oversight"
    templates_dir.mkdir(parents=True)
    (templates_dir / "known.md").write_text("# Known\n")
    entries = [
        {
            "template": "templates/oversight/known.md",
            "produces": "bogus",
            "target": "x",
            "class": "register",
        }
    ]
    findings = gates.check_c2_registration(templates_dir, entries)
    assert len(findings) == 1
    assert findings[0].verdict == gates.PRODUCES_INVALID


def test_c2_registration_excludes_audit_and_dotfiles(tmp_path):
    templates_dir = tmp_path / "templates" / "oversight"
    (templates_dir / ".audit" / "logs").mkdir(parents=True)
    (templates_dir / ".audit" / "logs" / "sanitization-log.jsonl").write_text("{}")
    (templates_dir / ".hidden.md").write_text("# Hidden\n")
    findings = gates.check_c2_registration(templates_dir, [])
    assert findings == []


# ── C4(a) — consumer resolution ───────────────────────────────────────────────


def test_c4a_clean_tree_real_repo():
    entries = gates.load_registry(
        REPO / "scripts" / "template_parity" / "oversight-templates.yaml"
    )
    consumers = gates.load_schema_consumers(
        REPO / "_ai-memory" / "_memory" / "parzival-sidecar" / "oversight-schema.yaml"
    )
    findings = gates.check_c4a_consumer_resolution(entries, consumers)
    assert findings == []


def test_c4a_seeded_fixture_fails():
    result = _run_cli(FIXTURES / "c4_seeded")
    assert result.returncode != 0
    assert "CONSUMER_UNKNOWN" in result.stdout
    assert "ghost-consumer" in result.stdout


def test_c4a_unknown_consumer():
    entries = [
        {
            "template": "templates/oversight/x.md",
            "target": "oversight/x.md",
            "consumed_by": ["nope"],
        }
    ]
    findings = gates.check_c4a_consumer_resolution(entries, {"aim-tracking-rotate"})
    assert len(findings) == 1
    assert findings[0].verdict == gates.CONSUMER_UNKNOWN
    assert "nope" in findings[0].message


def test_c4a_empty_consumed_by_is_legal():
    entries = [
        {
            "template": "templates/oversight/x.md",
            "target": "oversight/x.md",
            "consumed_by": [],
        }
    ]
    assert gates.check_c4a_consumer_resolution(entries, set()) == []


# ── C4(b) — reference resolution + UNBACKED ──────────────────────────────────


def test_c4b_clean_tree_real_repo():
    entries = gates.load_registry(
        REPO / "scripts" / "template_parity" / "oversight-templates.yaml"
    )
    findings = gates.check_c4b_reference_backing(REPO / "_ai-memory" / "pov", entries)
    assert findings == []


def test_c4b_seeded_fixture_fails():
    result, findings = _run_cli_json(FIXTURES / "c4_seeded")
    assert result.returncode != 0
    unbacked = [f for f in findings if f["verdict"] == "UNBACKED"]
    assert {f["path"] for f in unbacked} == {"oversight/newarea/"}


def test_c4b_new_unbacked_reference(tmp_path):
    pov_dir = tmp_path / "pov"
    (pov_dir / "skills" / "s").mkdir(parents=True)
    (pov_dir / "skills" / "s" / "SKILL.md").write_text(
        "see oversight/brandnew/thing.md and oversight/backed.md\n"
    )
    entries = [
        {"template": "templates/oversight/backed.md", "target": "oversight/backed.md"}
    ]
    findings = gates.check_c4b_reference_backing(pov_dir, entries)
    assert len(findings) == 1
    assert findings[0].verdict == gates.UNBACKED
    assert findings[0].path == "oversight/brandnew/"


def test_c4b_directory_reference_without_trailing_slash_resolves_as_directory():
    # "oversight/bugs" (no trailing slash) must resolve like "oversight/bugs/"
    # -- a bare directory name is not a root-level singleton file.
    assert gates._normalize_ref("oversight/bugs") == "oversight/bugs/"


def test_c4b_punctuation_artifacts_are_ignored(tmp_path):
    pov_dir = tmp_path / "pov"
    pov_dir.mkdir()
    (pov_dir / "note.py").write_text(
        'x = "run from the workspace root that contains oversight/."\n'
        'y = "see oversight/ for details"\n'
    )
    edges = gates.extract_pov_references(pov_dir)
    assert edges == {}


def test_c4b_root_singleton_exact_match_required(tmp_path):
    pov_dir = tmp_path / "pov"
    pov_dir.mkdir()
    (pov_dir / "note.md").write_text("see oversight/project-status.md\n")
    entries = [
        {
            "template": "templates/oversight/project-status.md",
            "target": "oversight/project-status.md",
        }
    ]
    findings = gates.check_c4b_reference_backing(pov_dir, entries)
    assert findings == []


# ── C5 — every entry declares a class ────────────────────────────────────────


def test_c5_clean_tree_real_repo():
    entries = gates.load_registry(
        REPO / "scripts" / "template_parity" / "oversight-templates.yaml"
    )
    findings = gates.check_c5_class(entries)
    assert findings == []


def test_c5_seeded_fixture_fails():
    result = _run_cli(FIXTURES / "c5_seeded")
    assert result.returncode != 0
    assert "CLASS_MISSING" in result.stdout


def test_c5_missing_class():
    entries = [{"template": "templates/oversight/x.md", "target": "oversight/x.md"}]
    findings = gates.check_c5_class(entries)
    assert len(findings) == 1
    assert findings[0].verdict == gates.CLASS_MISSING


def test_c5_empty_string_class_is_missing():
    entries = [
        {
            "template": "templates/oversight/x.md",
            "target": "oversight/x.md",
            "class": "",
        }
    ]
    findings = gates.check_c5_class(entries)
    assert len(findings) == 1


# ── Whole-repo combined-run invariant ─────────────────────────────────────────


def test_main_on_real_tree_clean():
    """C2, C4(a), C4(b), and C5 are all clean on today's tree — every shipped
    template is registered, every `oversight/...` reference across the POV
    tree resolves to a backed registry entry, and every entry declares a
    `class` (PLAN-035 P2.6 reconcile closed the tasks/reports/deferrals gaps
    and the archive/ reference)."""
    result, findings = _run_cli_json(REPO)
    assert result.returncode == 0
    assert findings == []
