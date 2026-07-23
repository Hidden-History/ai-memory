"""Tests for the PLAN-035 P3 template-parity conform engine (Axis B — BP-190 + §3b).

The engine lives at
``_ai-memory/pov/skills/aim-content-drift/scripts/conform_engine.py`` (a skill script
invoked by path), so it is loaded via ``importlib.util.spec_from_file_location`` — the
established repo pattern (mirrors ``test_plan033_p3_reconcile_engine.py``). This file
lives under ``tests/`` so CI collects it (TD-812).

Every fixture is built from the SHIPPED registry + templates
(``scripts/template_parity/`` + ``templates/oversight/``) so the suite is portable —
never keyed to maintainer-specific tree contents (P3 binding note 4). The real oracle
is driven end-to-end (full-capture JSON), exactly as the engine does in production.

DONE-WHEN coverage (1:1 to the P3 brief):
  ① Kind-A/B on a MANAGED_MERGE_REQUIRED fixture -> oracle 0 STRUCT + zero line loss.
  ② Kind-C fixture -> flagged-and-restored, NOT auto-applied (bytes unchanged).
  ③ Data-safety gate restore-on-fail (drive the real gate; backup restored).
  ④ OVER_CAP never acted on by the conform loop.
  ⑤ No [TODO]/placeholder token written into a conformed live file.
  ⑥ Apply-once: a second conform run is a no-op (oracle-measured).
  ⑦ HIL / Needs-attention -> resolved-stamp loop; runbook is live-measured.
  ⑧ UPDATE-RUNBOOK renders Pending / Applied / Needs-attention.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ENGINE_PATH = (
    _REPO
    / "_ai-memory"
    / "pov"
    / "skills"
    / "aim-content-drift"
    / "scripts"
    / "conform_engine.py"
)
_spec = importlib.util.spec_from_file_location("conform_engine", _ENGINE_PATH)
ce = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ce
_spec.loader.exec_module(ce)

_ORACLE = _REPO / "scripts" / "template_parity" / "template_parity_oracle.py"
_REGISTRY = _REPO / "scripts" / "template_parity" / "oversight-templates.yaml"
_TEMPLATES = _REPO / "templates" / "oversight"


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def _cfg(project_root: Path) -> ce.ConformConfig:
    return ce.ConformConfig(
        project_root=project_root.resolve(),
        oracle_path=_ORACLE,
        registry_path=_REGISTRY,
        templates_root=_TEMPLATES,
    )


def _write(project_root: Path, rel: str, text: str) -> Path:
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _struct_for(cfg, rel: str) -> list[dict]:
    return [
        f
        for f in ce.run_oracle(cfg)
        if f.get("verdict") == "STRUCT_NONCONFORMANT" and f.get("path") == rel
    ]


# A SESSION_WORK_INDEX.md missing exactly 2 of its 4 required sections (50% -> Kind A,
# not coverage-C). Frontmatter constants + required fields present, so the ONLY gap is
# two sections -> a clean deterministic Kind-A add-only case. Under cap (80 lines/12KB).
SWI_KIND_A = """\
---
class: live-index
cap_lines: 80
cap_kb: 12
---
# Session Work Index

## Current Sprint

**Sprint**: S1
**Goal**: ship PLAN-035 P3
**Status**: active

## Active Task

| task | owner |
| ---- | ----- |
| build conform engine | amelia |
"""

# Same singleton, but 3 of 4 sections missing (75% -> coverage trigger) with a non-stub
# body written under the file's OWN heading -> Kind C (a blind add-only would orphan it).
SWI_KIND_C = """\
---
class: live-index
cap_lines: 80
cap_kb: 12
---
# Session Work Index

## Current Sprint

**Sprint**: S1
**Goal**: g
**Status**: active

## My Own Running Notes

custom narrative line one
custom narrative line two
custom narrative line three
custom narrative line four
custom narrative line five
custom narrative line six
"""


def _swi_conformant(n_rows: int = 4) -> str:
    rows = "\n".join(f"| item {i} | owner {i} |" for i in range(n_rows))
    return f"""\
---
class: live-index
cap_lines: 80
cap_kb: 12
---
# Session Work Index

## Current Sprint

**Sprint**: S1
**Goal**: g
**Status**: active

## Active Task

| task | owner |
| ---- | ----- |
{rows}

## Active Blockers

none

## High Priority Risks

none
"""


# --------------------------------------------------------------------------- #
# ① Kind-A auto-conform -> oracle 0 STRUCT + zero line loss
# --------------------------------------------------------------------------- #
def test_kind_a_reaches_zero_struct_no_line_loss(tmp_path):
    cfg = _cfg(tmp_path)
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A)
    original_nonblank = [ln for ln in SWI_KIND_A.splitlines() if ln.strip()]

    # Precondition: nonconformant (the 2 missing sections).
    assert _struct_for(cfg, "oversight/SESSION_WORK_INDEX.md")

    out = ce.conform(cfg, kinds="A")

    assert "oversight/SESSION_WORK_INDEX.md" in out["a_fixed"]
    assert not out["a_failed"]
    # Oracle now clean for the file (the done-gate: 0 STRUCT_NONCONFORMANT).
    assert _struct_for(cfg, "oversight/SESSION_WORK_INDEX.md") == []
    new_text = p.read_text(encoding="utf-8")
    assert "## Active Blockers" in new_text and "## High Priority Risks" in new_text
    # Zero line loss: every original non-empty line survives.
    new_nonblank = [ln for ln in new_text.splitlines() if ln.strip()]
    for line in original_nonblank:
        assert line in new_nonblank


# --------------------------------------------------------------------------- #
# ①b CRITICAL byte-safety — a non-UTF-8 byte survives conform unchanged
# --------------------------------------------------------------------------- #
def test_kind_a_preserves_non_utf8_bytes(tmp_path):
    """A structurally-nonconformant Kind-A file carrying a raw non-UTF-8 byte (0xE9 —
    a real field artifact) must be conformed WITHOUT corrupting that byte. The pre-fix
    engine read every live file with ``errors="replace"`` and wrote the lossy text back,
    turning 0xE9 into 0xEF 0xBF 0xBD (U+FFFD) — permanent corruption reported as success.
    This is the reviewer's exact repro: it fails on the pre-fix engine, passes after."""
    cfg = _cfg(tmp_path)
    p = tmp_path / "oversight" / "SESSION_WORK_INDEX.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = SWI_KIND_A.encode("utf-8")
    marker = b"**Goal**: ship PLAN-035 P3"
    nonutf8 = raw.replace(marker, marker + b" (caf\xe9)")  # lone 0xE9 = invalid UTF-8
    assert b"\xe9" in nonutf8 and b"\xef\xbf\xbd" not in nonutf8
    p.write_bytes(nonutf8)

    # Precondition: nonconformant (2 missing sections); the oracle tolerates the bad byte.
    assert _struct_for(cfg, "oversight/SESSION_WORK_INDEX.md")

    out = ce.conform(cfg, kinds="A")

    # Success reported AND the two sections were added...
    assert "oversight/SESSION_WORK_INDEX.md" in out["a_fixed"]
    assert not out["a_failed"]
    result = p.read_bytes()
    assert b"## Active Blockers" in result and b"## High Priority Risks" in result
    # ...and the original invalid byte is preserved EXACTLY — never replaced by U+FFFD.
    assert b"\xe9" in result, "original non-UTF-8 byte was corrupted"
    assert b"\xef\xbf\xbd" not in result, "byte was lossily replaced with U+FFFD"
    # Full byte-level insert-only preservation (the safety-net gate).
    assert ce._bytes_preserved(nonutf8, result)


# --------------------------------------------------------------------------- #
# ①c EOF newline-glue — a file with no trailing newline conforms cleanly
# --------------------------------------------------------------------------- #
def test_kind_a_no_trailing_newline_conforms_cleanly(tmp_path):
    """An end-anchored section insert onto a body whose last line lacks a trailing
    newline must not glue the new heading onto that line (which would trip the
    line-preservation precheck and leave the file permanently non-conformable)."""
    cfg = _cfg(tmp_path)
    no_eol = SWI_KIND_A.rstrip("\n")
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", no_eol)
    assert not p.read_bytes().endswith(b"\n")  # precondition: no trailing newline

    out = ce.conform(cfg, kinds="A")

    assert "oversight/SESSION_WORK_INDEX.md" in out["a_fixed"]
    assert not out["a_failed"]
    assert _struct_for(cfg, "oversight/SESSION_WORK_INDEX.md") == []
    new_lines = p.read_text(encoding="utf-8").splitlines()
    assert "## Active Blockers" in new_lines and "## High Priority Risks" in new_lines
    # The original last line survives intact, not glued to the new heading.
    assert "| build conform engine | amelia |" in new_lines


# --------------------------------------------------------------------------- #
# ②a Required field with no template host section -> HIL, never a broken Kind-A
# --------------------------------------------------------------------------- #
def test_required_field_with_no_host_section_routes_to_hil(tmp_path):
    """A required_field the shipped template places under NO required section is
    unhostable: a blind add-only would drop it and the gate would fail forever. Such a
    file routes to HIL rather than a perpetually-failing Kind-A. (Finding 4.)"""
    templates_root = tmp_path / "templates" / "oversight"
    templates_root.mkdir(parents=True)
    # `**Orphan Field**:` sits ABOVE the only required section -> host resolves to None.
    (templates_root / "widget.md").write_text(
        "---\nclass: widget\n---\n# Widget\n\n**Orphan Field**:\n\n## Real Section\n\nbody\n",
        encoding="utf-8",
    )
    cfg = ce.ConformConfig(
        project_root=tmp_path,
        oracle_path=_ORACLE,
        registry_path=_REGISTRY,
        templates_root=templates_root,
    )
    entry = {
        "template": "widget.md",
        "required_skeleton": {
            "required_sections": ["## Real Section"],
            "required_fields": ["Orphan Field"],
            "match_case": True,
        },
    }
    live = _write(
        tmp_path,
        "oversight/w.md",
        "---\nclass: widget\n---\n# Widget\n\n## Real Section\n\nbody\n",
    )
    decision = ce.classify_file(cfg, entry, live, ["Orphan Field"])
    assert decision.kind == "HIL"
    assert "no template host" in (decision.reason or "")


# --------------------------------------------------------------------------- #
# ③b Mid-run OSError preserves already-succeeded ledger rows (no whole-pass abort)
# --------------------------------------------------------------------------- #
def test_midrun_oserror_preserves_succeeded_ledger_rows(tmp_path, monkeypatch):
    """A mid-run OSError from one file's write must NOT abort the whole pass or drop the
    audit rows of files that already conformed this run. (Finding 3.)"""
    cfg = _cfg(tmp_path)
    _write(tmp_path, "oversight/plans/PLAN-a.md", _PLAN_NO_ROLE)
    _write(tmp_path, "oversight/plans/PLAN-b.md", _PLAN_NO_ROLE)

    real_atomic = ce.atomic_write

    def flaky(path, data, **kw):
        if "PLAN-b" in str(path):
            raise OSError("simulated disk failure")
        return real_atomic(path, data, **kw)

    monkeypatch.setattr(ce, "atomic_write", flaky)

    out = ce.conform(cfg, kinds="B")

    assert "oversight/plans/PLAN-a.md" in out["b_fixed"]
    assert any(f["path"] == "oversight/plans/PLAN-b.md" for f in out["b_failed"])
    # Ledger persisted despite the mid-run OSError, WITH the succeeded row.
    ledger = ce.load_conform_ledger(cfg.ledger_path())
    assert "oversight/plans/PLAN-a.md" in ledger.get("conformed", {})


# --------------------------------------------------------------------------- #
# ② Kind-C -> flagged-and-restored, NOT auto-applied
# --------------------------------------------------------------------------- #
def test_kind_c_flagged_not_applied(tmp_path):
    cfg = _cfg(tmp_path)
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_C)
    before = p.read_bytes()

    out = ce.conform(cfg, kinds="AB")

    assert "oversight/SESSION_WORK_INDEX.md" in out["c_skipped"]
    assert "oversight/SESSION_WORK_INDEX.md" not in out["a_fixed"]
    # Never written — bytes identical.
    assert p.read_bytes() == before
    # No stray backup left behind.
    assert not (tmp_path / "oversight" / "SESSION_WORK_INDEX.md.bak").exists()


# --------------------------------------------------------------------------- #
# ③ Data-safety gate — restore-the-backup on a failing re-verify
# --------------------------------------------------------------------------- #
def test_gate_restores_backup_on_failed_reverify(tmp_path):
    cfg = _cfg(tmp_path)
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A)
    before = p.read_bytes()

    # Feed the gate a "new" text that does NOT fix the findings (identical content):
    # the oracle re-verify still reports the 2 missing sections -> gate must restore.
    res = ce.apply_with_gate(cfg, p, SWI_KIND_A, ce.gate_kind_a)

    assert res["status"] == "failed"
    assert res.get("restored") is True
    assert p.read_bytes() == before  # original intact, no partial write
    assert not (tmp_path / "oversight" / "SESSION_WORK_INDEX.md.bak").exists()


def test_gate_aborts_on_line_loss_before_write(tmp_path):
    cfg = _cfg(tmp_path)
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A)
    before = p.read_bytes()

    # A candidate that DROPS an original line -> multiset precheck aborts before writing.
    truncated = "\n".join(SWI_KIND_A.splitlines()[:-3]) + "\n"
    res = ce.apply_with_gate(cfg, p, truncated, ce.gate_kind_a)

    assert res["status"] == "failed"
    assert "line-loss" in res["reason"]
    assert p.read_bytes() == before


# --------------------------------------------------------------------------- #
# ④ OVER_CAP is never acted on by the conform loop
# --------------------------------------------------------------------------- #
def test_over_cap_never_conformed(tmp_path):
    cfg = _cfg(tmp_path)
    # Conformant structure but > cap_lines (80) -> OVER_CAP only.
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", _swi_conformant(n_rows=90))
    before = p.read_bytes()

    findings = ce.run_oracle(cfg)
    over = [
        f
        for f in findings
        if f["verdict"] == "OVER_CAP" and f["path"] == "oversight/SESSION_WORK_INDEX.md"
    ]
    assert over, "fixture should be over cap_lines"
    assert (
        _struct_for(cfg, "oversight/SESSION_WORK_INDEX.md") == []
    )  # structurally conformant

    out = ce.conform(cfg, kinds="AB")

    assert "oversight/SESSION_WORK_INDEX.md" in out["over_cap"]
    assert "oversight/SESSION_WORK_INDEX.md" not in out["a_fixed"]
    assert p.read_bytes() == before  # rotation's domain, never touched here


# --------------------------------------------------------------------------- #
# ⑤ No [TODO]/placeholder written into a conformed live file
# --------------------------------------------------------------------------- #
def test_no_placeholder_token_written(tmp_path):
    cfg = _cfg(tmp_path)
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A)
    ce.conform(cfg, kinds="A")
    text = p.read_text(encoding="utf-8")
    assert "[TODO]" not in text
    assert "TODO" not in text
    assert "placeholder" not in text.lower()


# --------------------------------------------------------------------------- #
# ⑥ Apply-once — a second conform run is a no-op (oracle-measured)
# --------------------------------------------------------------------------- #
def test_apply_once_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A)

    first = ce.conform(cfg, kinds="A")
    assert "oversight/SESSION_WORK_INDEX.md" in first["a_fixed"]
    after_first = p.read_bytes()

    second = ce.conform(cfg, kinds="A")
    assert second["a_fixed"] == []  # already conformant -> not pending -> no write
    assert p.read_bytes() == after_first


# --------------------------------------------------------------------------- #
# Kind-B — deterministic plan_role discriminant fix + master flag-not-guess
# --------------------------------------------------------------------------- #
_PLAN_NO_ROLE = """\
---
plan_id: PLAN-TEST
type: build
status: active
---
# Test Plan

Some plan body content that must survive verbatim.
"""


def test_kind_b_sets_standalone_when_unambiguous(tmp_path):
    cfg = _cfg(tmp_path)
    p = _write(tmp_path, "oversight/plans/PLAN-test.md", _PLAN_NO_ROLE)

    # Precondition: the oracle flags a plan-family discriminant orphan.
    orphan = [
        f
        for f in ce.run_oracle(cfg)
        if f["verdict"] == "STRUCT_NONCONFORMANT"
        and not f.get("template")
        and "discriminant" in f.get("message", "")
        and f["path"] == "oversight/plans/PLAN-test.md"
    ]
    assert orphan, "fixture should be a discriminant orphan"

    out = ce.conform(cfg, kinds="B")

    assert "oversight/plans/PLAN-test.md" in out["b_fixed"]
    text = p.read_text(encoding="utf-8")
    assert "plan_role: standalone" in text
    assert "Some plan body content that must survive verbatim." in text
    # Discriminant orphan cleared.
    assert not [
        f
        for f in ce.run_oracle(cfg)
        if not f.get("template")
        and "discriminant" in f.get("message", "")
        and f["path"] == "oversight/plans/PLAN-test.md"
    ]


def test_kind_b_flags_master_never_guesses(tmp_path):
    cfg = _cfg(tmp_path)
    p = _write(tmp_path, "oversight/plans/MASTER_PLAN-x.md", _PLAN_NO_ROLE)
    before = p.read_bytes()

    out = ce.conform(cfg, kinds="B")

    flagged = [b["path"] for b in out["b_flagged"]]
    assert "oversight/plans/MASTER_PLAN-x.md" in flagged
    assert "oversight/plans/MASTER_PLAN-x.md" not in out["b_fixed"]
    assert p.read_bytes() == before  # ambiguous -> never written


# --------------------------------------------------------------------------- #
# HIL routing — a missing semantic frontmatter key is never auto-filled
# --------------------------------------------------------------------------- #
def test_missing_semantic_frontmatter_key_routes_to_hil(tmp_path):
    cfg = _cfg(tmp_path)
    # A standalone plan missing `status` (a per-instance semantic key) but otherwise
    # section-complete would be Kind-A except for the unfillable key -> HIL.
    registry = ce.load_registry(cfg)
    # Find the standalone-plan entry to build a matching, section-complete fixture.
    entry = next(
        e
        for e in registry.values()
        if e.get("match_frontmatter", {}).get("plan_role") == "standalone"
    )
    sections = entry.get("required_skeleton", {}).get("required_sections", [])
    body = "\n\n".join(f"{s}\n\ncontent for {s}" for s in sections)
    plan = f"---\nplan_id: PLAN-Z\ntype: build\nplan_role: standalone\n---\n# Z\n\n{body}\n"
    _write(tmp_path, "oversight/plans/PLAN-z.md", plan)

    out = ce.conform(cfg, kinds="A")
    # `status` (required frontmatter key, no registry-declared value) -> HIL, not [TODO].
    assert "oversight/plans/PLAN-z.md" in out["hil"]
    assert "oversight/plans/PLAN-z.md" not in out["a_fixed"]
    assert "[TODO]" not in (tmp_path / "oversight/plans/PLAN-z.md").read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# ⑧ UPDATE-RUNBOOK renders Pending / Applied / Needs-attention  (+ ⑦ live-measured)
# --------------------------------------------------------------------------- #
def test_runbook_renders_three_sections(tmp_path):
    cfg = _cfg(tmp_path)
    _write(
        tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A
    )  # -> Pending (Kind A)
    runbook = ce.render_runbook(cfg)
    assert "## Pending" in runbook
    assert "## Applied" in runbook
    assert "## Needs-attention" in runbook
    # The Kind-A file is listed as pending with the conform command.
    pending = runbook[runbook.index("## Pending") : runbook.index("## Applied")]
    assert "oversight/SESSION_WORK_INDEX.md" in pending
    assert "conform --project-root" in pending


def test_runbook_applied_and_needs_attention_are_live(tmp_path):
    cfg = _cfg(tmp_path)
    # Kind-C file -> Needs-attention.
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_C)
    rb1 = ce.render_runbook(cfg)
    na_index = rb1.index("## Needs-attention")
    assert "oversight/SESSION_WORK_INDEX.md" in rb1[na_index:]

    # Operator hand-conforms it -> live re-render drops it from Needs-attention (⑦).
    p.write_text(_swi_conformant(), encoding="utf-8")
    rb2 = ce.render_runbook(cfg)
    na_index2 = rb2.index("## Needs-attention")
    assert "oversight/SESSION_WORK_INDEX.md" not in rb2[na_index2:]


def test_runbook_applied_reads_ledger(tmp_path):
    cfg = _cfg(tmp_path)
    _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A)
    ce.conform(cfg, kinds="A")  # writes an Applied ledger row
    runbook = ce.render_runbook(cfg)
    applied = runbook[runbook.index("## Applied") : runbook.index("## Needs-attention")]
    assert "oversight/SESSION_WORK_INDEX.md" in applied
    assert "conformed-kind-a" in applied


# --------------------------------------------------------------------------- #
# Helper CLI wiring — `conform` and `runbook` subcommands route into the engine
# --------------------------------------------------------------------------- #
_HELPER_PATH = (
    _REPO
    / "_ai-memory"
    / "pov"
    / "skills"
    / "aim-content-drift"
    / "scripts"
    / "reconcile_helper.py"
)
_hspec = importlib.util.spec_from_file_location("reconcile_helper", _HELPER_PATH)
helper = importlib.util.module_from_spec(_hspec)
sys.modules[_hspec.name] = helper
_hspec.loader.exec_module(helper)


def test_helper_conform_subcommand(tmp_path, capsys):
    p = _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A)
    rc = helper.main(["conform", "--project-root", str(tmp_path), "--kinds", "A"])
    assert rc == 0
    assert "## Active Blockers" in p.read_text(encoding="utf-8")


def test_helper_runbook_subcommand(tmp_path):
    _write(tmp_path, "oversight/SESSION_WORK_INDEX.md", SWI_KIND_A)
    rc = helper.main(["runbook", "--project-root", str(tmp_path)])
    assert rc == 0
    runbook = (tmp_path / "UPDATE-RUNBOOK.md").read_text(encoding="utf-8")
    assert (
        "## Pending" in runbook
        and "## Applied" in runbook
        and "## Needs-attention" in runbook
    )
