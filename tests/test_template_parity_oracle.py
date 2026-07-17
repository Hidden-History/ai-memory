"""Regression tests for the template-parity oracle (PLAN-035 P2 Phase B keystone).

One test per §5 Done-When criterion (PLAN-035-pov-template-update-correctness.md):
  1. Oracle-truth — reproduces PM #407's hand-verified result against the real,
     frozen 40-entry registry.
  2. A PRESERVE-class file missing a required section/key is flagged.
  3. Instance-family / match_frontmatter routing — a reverted plan_role flags
     exactly that file.
  4. C6 order — an out-of-newest-first entry is named; C1 still passes.
  5. C6 cap — over cap_lines/cap_kb is flagged; within-cap is not.
  6. Cross-project — a non-conformant fixture is flagged, a conformant one passes.
  7. Product/user boundary — arbitrary dirs under oversight/ outside owned
     roots produce zero findings.
  8. Fresh-install — all declared targets present + conformant -> zero findings.

Any other result than what each test asserts means the oracle is wrong.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODPATH = REPO / "scripts" / "template_parity" / "template_parity_oracle.py"
FROZEN_REGISTRY = (
    REPO / "tests" / "fixtures" / "template_parity" / "oversight-templates.yaml"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("template_parity_oracle", MODPATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["template_parity_oracle"] = mod
    spec.loader.exec_module(mod)
    return mod


oracle = _load_module()


def _write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _run(entries: list[dict], project_root: Path) -> list:
    return oracle.run_checks(entries, project_root)


def _findings_for(findings: list, path: str) -> list:
    return [f for f in findings if f.path == path]


# ── Verbatim registry fragments (drawn from the frozen registry) ────────────

DECISION_LOG_ENTRY = {
    "template": "templates/oversight/tracking/decision-log.md",
    "produces": "singleton",
    "target": "oversight/tracking/decision-log.md",
    "class": "append-only-log",
    "required_skeleton": {
        "required_sections": ["## Decisions"],
        "required_frontmatter_keys": ["class", "cap_lines", "cap_kb"],
    },
    "conventions": {
        "entry_pattern": r"^### DEC-[A-Z0-9-]+-D\d",
        "order": "newest_first",
        "cap_lines": 150,
        "cap_kb": 50,
    },
}

RISK_REGISTER_ENTRY = {
    "template": "templates/oversight/tracking/risk-register.md",
    "produces": "singleton",
    "target": "oversight/tracking/risk-register.md",
    "class": "register",
    "required_skeleton": {
        "required_sections": ["## Active Risks", "## Resolved Risks"],
        "required_frontmatter_keys": ["class", "cap_lines", "cap_kb"],
    },
    "conventions": {"cap_lines": 120, "cap_kb": 12},
}

SESSION_WORK_INDEX_ENTRY = {
    "template": "templates/oversight/SESSION_WORK_INDEX.md",
    "produces": "singleton",
    "target": "oversight/SESSION_WORK_INDEX.md",
    "class": "live-index",
    "required_skeleton": {
        "required_sections": [
            "## Current Sprint",
            "## Active Task",
            "## Active Blockers",
            "## High Priority Risks",
        ],
        "required_frontmatter_keys": ["class", "cap_lines", "cap_kb"],
    },
    "conventions": {"entry_pattern": r"^\| ", "cap_lines": 80, "cap_kb": 12},
}

MASTER_PLAN_ENTRY = {
    "template": "templates/oversight/plans/MASTER_PLAN_TEMPLATE.md",
    "produces": "family",
    "glob": "oversight/plans/*.md",
    "match_frontmatter": {"plan_role": "master"},
    "class": "detail-record",
    "required_skeleton": {
        "required_frontmatter_keys": ["plan_id", "plan_role", "type", "status"],
        "required_sections": ["## Master spine*", "## Continuity Log"],
        "ordered": False,
        "match_case": False,
    },
}

STANDALONE_PLAN_ENTRY = {
    "template": "templates/oversight/plans/PLAN_TEMPLATE.md",
    "produces": "family",
    "glob": "oversight/plans/*.md",
    "match_frontmatter": {"plan_role": "standalone"},
    "class": "detail-record",
    "required_skeleton": {
        "required_frontmatter_keys": ["plan_id", "type", "status"],
        "required_sections": ["## 1. Goal", "## 7. Continuity Log"],
        "ordered": False,
        "match_case": False,
    },
}

PROJECT_STATUS_ENTRY = {
    "template": "templates/oversight/project-status.md",
    "produces": "singleton",
    "target": "oversight/project-status.md",
    "class": "heartbeat",
    "required_skeleton": {
        "required_frontmatter_keys": ["class", "cap_lines", "cap_kb"],
        "required_yaml_body_keys": [
            "current_phase",
            "active_task",
            "phases_complete",
            "key_files",
            "live_record",
            "open_issues",
        ],
    },
    "conventions": {"cap_lines": 60, "cap_kb": 6},
}

PROJECT_STANDARDS_ENTRY = {
    "template": "templates/oversight/PROJECT_STANDARDS.yaml",
    "produces": "singleton",
    "target": "oversight/PROJECT_STANDARDS.yaml",
    "class": "live-index",
    "required_skeleton": {
        "kind": "yaml",
        "required_yaml_keys": ["schema_version", "global", "project", "topic_index"],
    },
}


# ── Fixture content builders ─────────────────────────────────────────────────

_DECISION_LOG_FRONTMATTER = (
    "---\nclass: append-only-log\ncap_lines: 150\ncap_kb: 50\n---\n"
)


def _conformant_decision_log(entry_ids: list[str]) -> str:
    body = _DECISION_LOG_FRONTMATTER + "# Decision Log\n\n## Decisions\n\n"
    for entry_id in entry_ids:
        body += f"### {entry_id}: example\n- **Date**: 2026-01-01\n\n"
    return body


def _oversized_decision_log() -> str:
    text = _DECISION_LOG_FRONTMATTER + "# Decision Log\n\n## Decisions\n\n"
    n = 0
    while len(text.splitlines()) < 210 or len(text.encode()) < 56 * 1024:
        n += 1
        text += (
            f"### DEC-PM{999 - n:03d}-D1: filler decision entry padded for size {n}\n"
            "- **Date**: 2026-01-01\n"
            "- **Context**: filler filler filler filler filler filler filler filler\n"
            "- **Decision**: filler filler filler filler filler filler filler filler\n\n"
        )
    return text


PROJECT_STATUS_CONFORMANT = """\
---
class: heartbeat
cap_lines: 60
cap_kb: 6
---
# project-status.md

```yaml
current_phase: execution
active_task: oversight/plans/PLAN-001.md
phases_complete:
  discovery: true
key_files:
  prd: null
live_record: oversight/SESSION_WORK_INDEX.md
open_issues: 0
```
"""

PROJECT_STANDARDS_CONFORMANT = """\
schema_version: "1.0"
project: "demo"
global: []
project_list: []
topic_index: {}
"""
# note: registry key is `project`, present above; `project_list` is incidental extra content
# (BP-189 extras-out-of-scope) exercising that C1 ignores it.


# ── 1. Oracle-truth ───────────────────────────────────────────────────────────


def test_oracle_truth_reproduces_pm407_hand_verified_result(tmp_path):
    entries = oracle.load_registry(FROZEN_REGISTRY)

    _write(
        tmp_path,
        "oversight/SESSION_WORK_INDEX.md",
        "---\nclass: live-index\ncap_lines: 80\ncap_kb: 12\n---\n"
        "# Session Work Index\n\n## Current State\n\nsome content\n",
    )
    _write(
        tmp_path,
        "oversight/session-index/INDEX.md",
        "---\nclass: live-index\ncap_lines: 120\ncap_kb: 10\n---\n"
        "# Session Index\n\n## How This Works\n\n## Archive\n\nstuff\n",
    )
    _write(
        tmp_path,
        "oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-PM002-D1", "DEC-PM001-D1"]),
    )

    findings = _run(entries, tmp_path)

    swi = _findings_for(findings, "oversight/SESSION_WORK_INDEX.md")
    assert len(swi) == 1
    assert swi[0].verdict == oracle.STRUCT_NONCONFORMANT
    for section in [
        "## Current Sprint",
        "## Active Task",
        "## Active Blockers",
        "## High Priority Risks",
    ]:
        assert section in swi[0].message

    session_index = _findings_for(findings, "oversight/session-index/INDEX.md")
    assert len(session_index) == 1
    assert session_index[0].verdict == oracle.STRUCT_NONCONFORMANT
    assert "## Current Year" in session_index[0].message

    decision_log = _findings_for(findings, "oversight/tracking/decision-log.md")
    assert decision_log == []  # CONFORMANT — any finding here is a wrong oracle


# ── 2. PRESERVE-class file missing a required section/key ───────────────────


def test_preserve_class_file_missing_section_is_flagged(tmp_path):
    _write(
        tmp_path,
        "oversight/tracking/risk-register.md",
        "---\nclass: register\ncap_lines: 120\ncap_kb: 12\n---\n"
        "# Risk Register\n\n## Active Risks\n\nnone yet\n",
    )
    findings = _run([RISK_REGISTER_ENTRY], tmp_path)
    matches = _findings_for(findings, "oversight/tracking/risk-register.md")
    assert len(matches) == 1
    assert matches[0].verdict == oracle.STRUCT_NONCONFORMANT
    assert "## Resolved Risks" in matches[0].message


# ── 3. Instance-family / match_frontmatter routing ───────────────────────────


def test_reverted_plan_role_flags_exactly_that_file(tmp_path):
    _write(
        tmp_path,
        "oversight/plans/PLAN-001-standalone.md",
        "---\nplan_id: PLAN-001\nplan_role: standalone\ntype: build\nstatus: active\n---\n"
        "# PLAN-001\n\n## 1. Goal\n\ngoal text\n\n## 7. Continuity Log\n\nlog\n",
    )
    # Reverted: content is standalone-shaped but plan_role now claims "master" —
    # the 54-plan-family failure this test guards against.
    _write(
        tmp_path,
        "oversight/plans/PLAN-002-reverted.md",
        "---\nplan_id: PLAN-002\nplan_role: master\ntype: build\nstatus: active\n---\n"
        "# PLAN-002\n\n## 1. Goal\n\ngoal text\n\n## 7. Continuity Log\n\nlog\n",
    )

    entries = [MASTER_PLAN_ENTRY, STANDALONE_PLAN_ENTRY]
    findings = _run(entries, tmp_path)

    assert _findings_for(findings, "oversight/plans/PLAN-001-standalone.md") == []
    reverted = _findings_for(findings, "oversight/plans/PLAN-002-reverted.md")
    assert len(reverted) == 1
    assert reverted[0].verdict == oracle.STRUCT_NONCONFORMANT
    assert reverted[0].template == MASTER_PLAN_ENTRY["template"]


# ── 4. C6 order ───────────────────────────────────────────────────────────────


def test_c6_order_violation_named_c1_still_passes(tmp_path):
    ordered = _write(
        tmp_path,
        "ordered/oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-PM003-D1", "DEC-PM002-D1", "DEC-PM001-D1"]),
    )
    violated = _write(
        tmp_path,
        "violated/oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-PM003-D1", "DEC-PM001-D1", "DEC-PM002-D1"]),
    )

    ordered_findings = _run([DECISION_LOG_ENTRY], ordered.parents[2])
    violated_findings = _run([DECISION_LOG_ENTRY], violated.parents[2])

    rel = "oversight/tracking/decision-log.md"
    assert [
        f for f in ordered_findings if f.verdict == oracle.CONVENTION_VIOLATION
    ] == []
    assert [
        f for f in ordered_findings if f.verdict == oracle.STRUCT_NONCONFORMANT
    ] == []

    violations = [
        f for f in violated_findings if f.verdict == oracle.CONVENTION_VIOLATION
    ]
    assert len(violations) == 1
    assert "DEC-PM002-D1" in violations[0].message
    # same file still structurally conformant — C6 catches what C1 cannot
    assert [
        f
        for f in violated_findings
        if f.path == rel and f.verdict == oracle.STRUCT_NONCONFORMANT
    ] == []


# ── 5. C6 cap ─────────────────────────────────────────────────────────────────


def test_c6_over_cap_flagged_within_cap_is_not(tmp_path):
    small = _write(
        tmp_path,
        "small/oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-PM001-D1"]),
    )
    big_text = _oversized_decision_log()
    assert len(big_text.splitlines()) >= 210
    assert len(big_text.encode()) >= 56 * 1024
    big = _write(tmp_path, "big/oversight/tracking/decision-log.md", big_text)

    small_findings = _run([DECISION_LOG_ENTRY], small.parents[2])
    big_findings = _run([DECISION_LOG_ENTRY], big.parents[2])

    assert [f for f in small_findings if f.verdict == oracle.OVER_CAP] == []

    over_cap = [f for f in big_findings if f.verdict == oracle.OVER_CAP]
    assert len(over_cap) == 1
    assert "cap_lines" in over_cap[0].message
    assert "cap_kb" in over_cap[0].message


# ── 6. Cross-project ──────────────────────────────────────────────────────────


def test_cross_project_lsp_app_like_flagged_document_pipeline_like_passes(tmp_path):
    entries = [SESSION_WORK_INDEX_ENTRY, DECISION_LOG_ENTRY]

    lsp_app = tmp_path / "lsp_app"
    _write(
        lsp_app,
        "oversight/SESSION_WORK_INDEX.md",
        "---\nclass: live-index\ncap_lines: 80\ncap_kb: 12\n---\n"
        "# Session Work Index\n\n## Recent Activity\n\nreconciled 8 managed-merges\n",
    )
    _write(
        lsp_app,
        "oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-L1-D1"]),
    )

    document_pipeline = tmp_path / "document_pipeline"
    _write(
        document_pipeline,
        "oversight/SESSION_WORK_INDEX.md",
        "---\nclass: live-index\ncap_lines: 80\ncap_kb: 12\n---\n"
        "# Session Work Index\n\n"
        "## Current Sprint\n\ns\n\n## Active Task\n\na\n\n"
        "## Active Blockers\n\nnone\n\n## High Priority Risks\n\nnone\n",
    )
    _write(
        document_pipeline,
        "oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-D1-D1"]),
    )

    lsp_findings = _run(entries, lsp_app)
    doc_findings = _run(entries, document_pipeline)

    assert any(f.verdict == oracle.STRUCT_NONCONFORMANT for f in lsp_findings)
    assert doc_findings == []


# ── 7. Product/user boundary ─────────────────────────────────────────────────


def test_arbitrary_user_dirs_under_oversight_outside_owned_roots_are_silent(tmp_path):
    _write(
        tmp_path,
        "oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-PM001-D1"]),
    )
    # Arbitrary, AI-Memory-unaware directories directly under oversight/ — the
    # exact PM #407 scenario (oversight/tasks/** scratch dirs, never shipped).
    _write(tmp_path, "oversight/tasks/pm999-scratch/notes.md", "scratch notes\n")
    _write(tmp_path, "oversight/my-own-notes/whatever.txt", "user content\n")

    findings = _run([DECISION_LOG_ENTRY], tmp_path)

    boundary_findings = [
        f
        for f in findings
        if f.path.startswith("oversight/tasks/")
        or f.path.startswith("oversight/my-own-notes/")
    ]
    assert boundary_findings == []


# ── 8. Fresh-install ──────────────────────────────────────────────────────────


def test_fresh_install_all_targets_present_conformant_zero_findings(tmp_path):
    entries = [
        DECISION_LOG_ENTRY,
        STANDALONE_PLAN_ENTRY,
        PROJECT_STATUS_ENTRY,
        PROJECT_STANDARDS_ENTRY,
    ]

    _write(
        tmp_path,
        "oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-PM001-D1"]),
    )
    _write(
        tmp_path,
        "oversight/plans/PLAN-001.md",
        "---\nplan_id: PLAN-001\nplan_role: standalone\ntype: build\nstatus: active\n---\n"
        "# PLAN-001\n\n## 1. Goal\n\ngoal\n\n## 7. Continuity Log\n\nlog\n",
    )
    _write(tmp_path, "oversight/project-status.md", PROJECT_STATUS_CONFORMANT)
    _write(tmp_path, "oversight/PROJECT_STANDARDS.yaml", PROJECT_STANDARDS_CONFORMANT)

    findings = _run(entries, tmp_path)
    assert findings == []


# ── FIX 1: malformed/absent plan_role discriminant is not invisible ─────────


def test_malformed_or_absent_plan_role_flags_orphan_plan(tmp_path):
    _write(
        tmp_path,
        "oversight/plans/PLAN-003-typo.md",
        "---\nplan_id: PLAN-003\nplan_role: standalon\ntype: build\nstatus: active\n---\n"
        "# PLAN-003\n\n## 1. Goal\n\ngoal\n\n## 7. Continuity Log\n\nlog\n",
    )
    _write(
        tmp_path,
        "oversight/plans/PLAN-004-absent.md",
        "---\nplan_id: PLAN-004\ntype: build\nstatus: active\n---\n"
        "# PLAN-004\n\n## 1. Goal\n\ngoal\n\n## 7. Continuity Log\n\nlog\n",
    )

    entries = [MASTER_PLAN_ENTRY, STANDALONE_PLAN_ENTRY]
    findings = _run(entries, tmp_path)

    typo = _findings_for(findings, "oversight/plans/PLAN-003-typo.md")
    absent = _findings_for(findings, "oversight/plans/PLAN-004-absent.md")
    assert len(typo) == 1
    assert typo[0].verdict == oracle.STRUCT_NONCONFORMANT
    assert "plan_role" in typo[0].message
    assert len(absent) == 1
    assert absent[0].verdict == oracle.STRUCT_NONCONFORMANT
    assert "plan_role" in absent[0].message


# ── FIX 2: glob_exclude is honored ───────────────────────────────────────────

EXCLUDE_ENTRY = {
    "template": "templates/oversight/standards/_global/_TEMPLATE.md",
    "produces": "family",
    "glob": "oversight/standards/_global/*.md",
    "glob_exclude": ["_TEMPLATE.md"],
    "class": "detail-record",
    "required_skeleton": {"required_sections": ["## Rules"]},
}


def test_glob_exclude_drops_excluded_file_from_family(tmp_path):
    _write(tmp_path, "oversight/standards/_global/_TEMPLATE.md", "# stub, no Rules\n")
    _write(
        tmp_path,
        "oversight/standards/_global/G001-real.md",
        "# Real\n\n## Rules\n\nstuff\n",
    )
    findings = _run([EXCLUDE_ENTRY], tmp_path)

    # excluded file is neither checked (would fail C1 — missing "## Rules")
    # nor counted as a real family member
    assert _findings_for(findings, "oversight/standards/_global/_TEMPLATE.md") == []
    # non-excluded member still resolves and is checked normally (conformant)
    assert _findings_for(findings, "oversight/standards/_global/G001-real.md") == []


# ── FIX 3: MISSING_TARGET only for produces:singleton ────────────────────────


def test_missing_target_only_for_singleton_not_empty_family(tmp_path):
    # empty family glob (fresh project, zero plans yet) -> legitimate, no finding
    findings = _run([STANDALONE_PLAN_ENTRY], tmp_path)
    assert [f for f in findings if f.verdict == oracle.MISSING_TARGET] == []

    # missing singleton target -> MISSING_TARGET
    findings2 = _run([RISK_REGISTER_ENTRY], tmp_path)
    missing = [f for f in findings2 if f.verdict == oracle.MISSING_TARGET]
    assert len(missing) == 1


# ── FIX 4: C6 order — sound, conservative sort key ───────────────────────────


def test_c6_order_older_before_newer_flags_offender(tmp_path):
    # the real PM #407 "appended to bottom" shape: an older session-block
    # (DEC-PM407) sits above a newer one (DEC-PM408) that landed below it
    _write(
        tmp_path,
        "oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-PM407-D1", "DEC-PM408-D1"]),
    )
    findings = _run([DECISION_LOG_ENTRY], tmp_path)
    violations = [f for f in findings if f.verdict == oracle.CONVENTION_VIOLATION]
    assert len(violations) == 1
    assert "DEC-PM408-D1" in violations[0].message


def test_c6_order_numberless_prefix_same_session_no_finding(tmp_path):
    _write(
        tmp_path,
        "oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-HOTFIX-D1", "DEC-HOTFIX-D2", "DEC-HOTFIX-D3"]),
    )
    findings = _run([DECISION_LOG_ENTRY], tmp_path)
    assert [f for f in findings if f.verdict == oracle.CONVENTION_VIOLATION] == []


def test_c6_order_real_pm409_over_pm408_shape_no_finding(tmp_path):
    ids = [
        "DEC-PM409-D1",
        "DEC-PM409-D2",
        "DEC-PM409-D3",
        "DEC-PM408-D1",
        "DEC-PM408-D2",
        "DEC-PM408-D3",
        "DEC-PM408-D4",
        "DEC-PM408-D5",
    ]
    _write(
        tmp_path, "oversight/tracking/decision-log.md", _conformant_decision_log(ids)
    )
    findings = _run([DECISION_LOG_ENTRY], tmp_path)
    assert [f for f in findings if f.verdict == oracle.CONVENTION_VIOLATION] == []


# ── FIX 5: report discloses unchecked convention dimensions ─────────────────


def test_report_discloses_unchecked_convention_dimensions(tmp_path):
    entry = dict(
        RISK_REGISTER_ENTRY,
        conventions={"cap_lines": 120, "cap_kb": 12, "plan_role_value": "master"},
    )
    entries = [entry]
    _write(
        tmp_path,
        "oversight/tracking/risk-register.md",
        "---\nclass: register\ncap_lines: 120\ncap_kb: 12\n---\n"
        "# Risk Register\n\n## Active Risks\n\nnone yet\n\n## Resolved Risks\n\nnone\n",
    )
    findings = _run(entries, tmp_path)
    unchecked = oracle.unchecked_convention_dimensions(entries)
    assert "plan_role_value" in unchecked
    assert "entry_pattern" not in unchecked  # a checked key never appears

    text = oracle.render_text(findings, tmp_path, unchecked)
    note = [line for line in text.splitlines() if line.startswith("note:")]
    assert len(note) == 1
    assert "plan_role_value" in note[0]

    # no unchecked dimensions declared -> no disclosure line at all
    text_none = oracle.render_text(findings, tmp_path, [])
    assert not any(line.startswith("note:") for line in text_none.splitlines())


# ── FIX 6: UNMANAGED scan stays non-recursive by design ──────────────────────


def test_find_unmanaged_is_non_recursive_by_design(tmp_path):
    _write(
        tmp_path,
        "oversight/tracking/decision-log.md",
        _conformant_decision_log(["DEC-PM001-D1"]),
    )
    # nested debris under the owned root oversight/tracking/ — direct-children
    # -only scan must never descend into it (PLAN-035 §3a boundary)
    _write(tmp_path, "oversight/tracking/.audit/logs/scratch.jsonl", "debris\n")
    findings = _run([DECISION_LOG_ENTRY], tmp_path)
    assert [f for f in findings if f.verdict == oracle.UNMANAGED] == []


# ── FIX 7: unchecked convention dimensions computed per-entry (cycle-2) ──────


def test_entry_pattern_without_order_on_same_entry_surfaces_as_unchecked(tmp_path):
    # SESSION_WORK_INDEX_ENTRY declares entry_pattern with NO order — its own
    # ordering is never asserted by check_c6_conventions, even though
    # DECISION_LOG_ENTRY (a different entry) pairs entry_pattern with order.
    entries = [SESSION_WORK_INDEX_ENTRY, DECISION_LOG_ENTRY]
    unchecked = oracle.unchecked_convention_dimensions(entries)
    assert "entry_pattern" in unchecked


def test_entry_pattern_paired_with_order_everywhere_not_unchecked(tmp_path):
    # every entry declaring entry_pattern also declares order: newest_first
    # -> entry_pattern is actually checked, must never appear as unchecked
    entries = [DECISION_LOG_ENTRY]
    unchecked = oracle.unchecked_convention_dimensions(entries)
    assert "entry_pattern" not in unchecked


def test_real_frozen_registry_discloses_entry_pattern_unchecked():
    # SESSION_WORK_INDEX.md and session-index/INDEX.md declare entry_pattern
    # with no order in the real registry — the disclosure must name
    # entry_pattern despite decision-log.md pairing it with order elsewhere.
    entries = oracle.load_registry(FROZEN_REGISTRY)
    unchecked = oracle.unchecked_convention_dimensions(entries)
    assert "entry_pattern" in unchecked


# ── FIX 8: discriminant-orphan guard — catch-all sibling covers the group ────

CATCHALL_PLAN_ENTRY = {
    "template": "templates/oversight/plans/PLAN_CATCHALL_TEMPLATE.md",
    "produces": "family",
    "glob": "oversight/plans/*.md",
    "class": "detail-record",
    "required_skeleton": {"required_sections": ["## Notes"]},
}


def test_discriminant_orphan_not_flagged_when_catchall_sibling_shares_glob(tmp_path):
    # plan_role matches neither MASTER_PLAN_ENTRY's discriminant nor any
    # other specific one, but CATCHALL_PLAN_ENTRY (no match_frontmatter)
    # shares the same raw glob and legitimately covers every member.
    _write(
        tmp_path,
        "oversight/plans/PLAN-005-weird-role.md",
        "---\nplan_id: PLAN-005\nplan_role: nonsense\ntype: build\nstatus: active\n---\n"
        "# PLAN-005\n\n## Notes\n\nstuff\n",
    )
    entries = [MASTER_PLAN_ENTRY, CATCHALL_PLAN_ENTRY]
    findings = _run(entries, tmp_path)
    orphans = [
        f
        for f in findings
        if f.verdict == oracle.STRUCT_NONCONFORMANT and f.template is None
    ]
    assert orphans == []


def test_discriminant_orphan_still_flagged_when_all_siblings_declare_discriminant(
    tmp_path,
):
    # no catch-all in the group (both siblings declare match_frontmatter) ->
    # the FIX 1 blocker-fix behavior must still hold.
    _write(
        tmp_path,
        "oversight/plans/PLAN-006-typo.md",
        "---\nplan_id: PLAN-006\nplan_role: standalon\ntype: build\nstatus: active\n---\n"
        "# PLAN-006\n\n## 1. Goal\n\ngoal\n\n## 7. Continuity Log\n\nlog\n",
    )
    entries = [MASTER_PLAN_ENTRY, STANDALONE_PLAN_ENTRY]
    findings = _run(entries, tmp_path)
    orphans = _findings_for(findings, "oversight/plans/PLAN-006-typo.md")
    assert len(orphans) == 1
    assert orphans[0].verdict == oracle.STRUCT_NONCONFORMANT


# ── CLI invariant: report-only, always exit 0 ────────────────────────────────


def test_cli_always_exits_zero_even_with_findings(tmp_path):
    registry = tmp_path / "registry.yaml"
    import yaml

    registry.write_text(yaml.safe_dump({"templates": [RISK_REGISTER_ENTRY]}))
    # deliberately non-conformant: target missing entirely -> MISSING_TARGET
    result = subprocess.run(
        [
            sys.executable,
            str(MODPATH),
            "--registry",
            str(registry),
            "--project-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "MISSING_TARGET" in result.stdout
