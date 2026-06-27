"""G5: BP-042 doc-drift correlation + the structured findings pipe (TD-675).

Proves: name-status parsing → typed FileChange; DOCOWNERS (.sot/DOCOWNERS,
Pattern A) correlation fires; the false-positive guards skip test-only / doc-only
/ internal-only commits; the single findings emitter produces the structured dict
for DOC_DRIFT / ERROR / FRICTION; and the end-to-end Stop pass surfaces doc-drift
without writing any oversight register file.

Run targeted only:
    pytest tests/test_g5_doc_drift_findings.py
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shadow = _load("aim_sot_shadow")


# --------------------------------------------------------------------------- #
# name-status parsing → FileChange
# --------------------------------------------------------------------------- #


def test_parse_name_status_all_shapes():
    text = (
        "A\tsrc/api/users.py\n"
        "M\tsrc/auth/provider.py\n"
        "D\tsrc/legacy/old.py\n"
        "R095\tsrc/utils/foo.py\tsrc/lib/foo.py\n"
    )
    changes = shadow.parse_name_status(text)
    assert [c.status for c in changes] == ["A", "M", "D", "R"]
    rename = changes[-1]
    assert rename.similarity == 95
    assert rename.old_path == "src/utils/foo.py"
    assert rename.new_path == "src/lib/foo.py"
    assert rename.path == "src/lib/foo.py"  # effective current path


# --------------------------------------------------------------------------- #
# DOCOWNERS loading + correlation
# --------------------------------------------------------------------------- #


def _docowners(project: Path, body: str) -> None:
    sot = project / ".sot"
    sot.mkdir(parents=True, exist_ok=True)
    (sot / "DOCOWNERS").write_text(body, encoding="utf-8")


def test_load_docowners_from_sot_dir(tmp_path):
    _docowners(
        tmp_path,
        "# comment\ndocs/api/*.md  src/api/**\ndocs/auth.md  src/auth/**\n\n",
    )
    rules = shadow.load_docowners(tmp_path)
    assert rules == [
        ("docs/api/*.md", ["src/api/**"]),
        ("docs/auth.md", ["src/auth/**"]),
    ]


def test_correlate_fires_on_matching_code_change(tmp_path):
    _docowners(tmp_path, "docs/api/*.md  src/api/**\n")
    (tmp_path / "docs" / "api").mkdir(parents=True)
    (tmp_path / "docs" / "api" / "users.md").write_text("doc", encoding="utf-8")
    changes = [shadow.FileChange("M", None, "src/api/users.py", None)]
    findings = shadow.correlate_doc_drift(
        changes, shadow.load_docowners(tmp_path), tmp_path
    )
    assert len(findings) == 1
    f = findings[0]
    assert f["finding_type"] == "DOC_DRIFT"
    assert f["doc_file"] == "docs/api/users.md"  # glob resolved to the real file
    assert f["anchor_type"] == "DOCOWNERS_MAP"
    assert f["severity"] == "MEDIUM"


def test_deletion_is_high_severity(tmp_path):
    _docowners(tmp_path, "docs/api.md  src/api/**\n")
    changes = [shadow.FileChange("D", None, "src/api/users.py", None)]
    findings = shadow.correlate_doc_drift(
        changes, shadow.load_docowners(tmp_path), tmp_path
    )
    assert findings and findings[0]["severity"] == "HIGH"


def test_no_findings_without_docowners(tmp_path):
    changes = [shadow.FileChange("M", None, "src/api/users.py", None)]
    assert shadow.correlate_doc_drift(changes, [], tmp_path) == []


# --------------------------------------------------------------------------- #
# False-positive guards (BP-042 Q3)
# --------------------------------------------------------------------------- #


def test_guard_test_only_commit(tmp_path):
    _docowners(tmp_path, "docs/api.md  src/api/**\n")
    changes = [
        shadow.FileChange("M", None, "tests/test_users.py", None),
        shadow.FileChange("A", None, "src/api/__tests__/x.py", None),
    ]
    assert (
        shadow.correlate_doc_drift(changes, shadow.load_docowners(tmp_path), tmp_path)
        == []
    )


def test_guard_doc_only_commit(tmp_path):
    _docowners(tmp_path, "docs/api.md  docs/**\n")
    changes = [shadow.FileChange("M", None, "docs/api.md", None)]
    assert (
        shadow.correlate_doc_drift(changes, shadow.load_docowners(tmp_path), tmp_path)
        == []
    )


def test_guard_internal_only_commit(tmp_path):
    _docowners(tmp_path, "docs/api.md  src/**\n")
    changes = [shadow.FileChange("M", None, "src/internal/cache.py", None)]
    assert (
        shadow.correlate_doc_drift(changes, shadow.load_docowners(tmp_path), tmp_path)
        == []
    )


def test_mixed_commit_still_flags_the_real_code_path(tmp_path):
    """A commit mixing a test file with a real code change still flags the doc
    for the real change (the guard only suppresses *entirely* noise commits)."""
    _docowners(tmp_path, "docs/api.md  src/api/**\n")
    changes = [
        shadow.FileChange("M", None, "tests/test_users.py", None),
        shadow.FileChange("M", None, "src/api/users.py", None),
    ]
    findings = shadow.correlate_doc_drift(
        changes, shadow.load_docowners(tmp_path), tmp_path
    )
    assert len(findings) == 1
    assert findings[0]["trigger_path"].startswith("src/api/users.py")


# --------------------------------------------------------------------------- #
# Findings pipe — one emitter for ALL finding classes
# --------------------------------------------------------------------------- #


def test_emit_finding_shape():
    f = shadow.emit_finding(
        finding_type="DOC_DRIFT",
        severity="HIGH",
        doc_file="docs/x.md",
        trigger_path="src/x.py",
        trigger_commit={"sha": "abc", "subject": "s"},
        anchor_type="DOCOWNERS_MAP",
        recommended_action="review",
    )
    assert set(f) == {
        "bp_id",
        "finding_type",
        "severity",
        "detected_at",
        "doc_file",
        "trigger_path",
        "trigger_commit",
        "anchor_type",
        "recommended_action",
    }


def test_error_and_friction_findings_flow_through_same_pipe():
    err = shadow.error_finding("git diff failed", "doc-drift")
    fric = shadow.friction_finding("resolved ambiguity X by choosing Y", "setup")
    assert err["finding_type"] == "ERROR" and err["severity"] == "HIGH"
    assert fric["finding_type"] == "FRICTION" and fric["severity"] == "MEDIUM"
    # Same structured shape as a DOC_DRIFT finding (single pipe).
    assert set(err) == set(fric)


# --------------------------------------------------------------------------- #
# End-to-end Stop pass — doc-drift surfaces; no register file written
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not shadow.git_available(), reason="git not available")
def test_run_shadow_pass_surfaces_doc_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "_SHADOW_GIT_ROOT", tmp_path / "sot-git")
    monkeypatch.setattr(shadow, "_SETUP_DIR", tmp_path / "sot-setup")
    monkeypatch.delenv("AIM_SOT_RECONFIGURE", raising=False)
    project = tmp_path / "project"
    (project / "src" / "api").mkdir(parents=True)
    (project / "src" / "api" / "users.py").write_text(
        "def u(): ...\n", encoding="utf-8"
    )
    (project / "docs" / "api").mkdir(parents=True)
    (project / "docs" / "api" / "users.md").write_text("# Users\n", encoding="utf-8")
    _docowners(project, "docs/api/*.md  src/api/**\n")
    pid = "proj-docdrift"

    state: dict = {}
    # First pass — establishes the baseline commit (nothing to diff yet).
    first = shadow.run_shadow_pass(pid, project, state)
    assert first["committed"] is True
    assert first["docs_stale"] == 0
    assert "last_verified_sha" in state

    # A real code change to a watched path.
    (project / "src" / "api" / "users.py").write_text(
        "def u(x): ...\n", encoding="utf-8"
    )
    second = shadow.run_shadow_pass(pid, project, state)
    doc_findings = [f for f in second["findings"] if f["finding_type"] == "DOC_DRIFT"]
    assert len(doc_findings) == 1
    assert doc_findings[0]["doc_file"] == "docs/api/users.md"
    assert second["docs_stale"] == 1

    # Non-invasive: still zero footprint in the user's tree.
    assert not (project / ".git").exists()
    assert not (project / ".gitignore").exists()
