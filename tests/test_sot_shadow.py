"""
Tests for aim_sot_shadow.py — TD-675 dual-review fixes.

Coverage:
  T-SHD01 — F-M1: path_excluded glob-dir: *.egg-info/ matches nested file
  T-SHD02 — F-M1: path_excluded glob-dir: vendor*/ user pattern matches
  T-SHD03 — F-M1: path_excluded literal dir: __pycache__/ still excluded
  T-SHD04 — F-M1: path_excluded: src/app.py not excluded
  T-SHD05 — F-M1: path_excluded glob-dir: *.egg-info/ matches dir with trailing slash
  T-SHD06 — F-M2: shadow_commit raises ShadowGitError on git-add failure
  T-SHD07 — F-M2: shadow_commit raises ShadowGitError on git-commit failure
  T-SHD08 — F-M2: shadow_commit returns None on clean tree (no error)
  T-SHD09 — F-M2: run_shadow_pass emits ERROR finding on ShadowGitError (not silent)
  T-SHD10 — F-L1: select_strategy git-ahead-behind + findings list → FRICTION appended
  T-SHD11 — F-L1: select_strategy git-ahead-behind + no findings list → no error
  T-SHD12 — F-L1: select_strategy content-digest → no FRICTION
  T-SHD13 — F-L2: correlate_doc_drift rename-away (old_path watched) → finding emitted
  T-SHD14 — F-L2: correlate_doc_drift rename-into (old_path unwatched) → also found via new_path
  T-SHD15 — F-L2: correlate_doc_drift all-M (normal modify) still fires (no false guard)

All tests are hermetic (no network, no disk I/O except tmp, subprocess mocked where needed).

Note: F-M3 (reformat-only guard) is DESCOPED — git --name-status has no line-content
visibility, so all-M is indistinguishable from a normal modify commit. The three
implemented guards (test-only, doc-only, internal-only) remain.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module import (importlib pattern — no package install required)
# ---------------------------------------------------------------------------

_SHADOW_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "_ai-memory"
    / "skills"
    / "aim-sot"
    / "scripts"
    / "aim_sot_shadow.py"
)
_spec = importlib.util.spec_from_file_location("aim_sot_shadow", _SHADOW_SCRIPT)
shadow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shadow)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOCOWNERS = [("docs/api.md", ["src/api/**"])]


def _make_change(status, old_path, new_path=None, similarity=None):
    return shadow.FileChange(
        status=status,
        similarity=similarity,
        old_path=old_path,
        new_path=new_path,
    )


# ---------------------------------------------------------------------------
# T-SHD01 — F-M1: *.egg-info/ matches a file nested inside the dir
# ---------------------------------------------------------------------------


def test_path_excluded_egg_info_nested_file():
    """*.egg-info/ must exclude any file inside a matching dir at any depth."""
    assert shadow.path_excluded(
        "src/foo.egg-info/PKG-INFO", shadow.DEFAULT_EXCLUDES
    ), "src/foo.egg-info/PKG-INFO should be excluded by *.egg-info/"


# ---------------------------------------------------------------------------
# T-SHD02 — F-M1: user vendor*/ pattern excludes files inside vendor dirs
# ---------------------------------------------------------------------------


def test_path_excluded_user_vendor_glob():
    """A user-supplied vendor*/ exclude must fnmatch dir segments."""
    patterns = [*shadow.DEFAULT_EXCLUDES, "vendor*/"]
    assert shadow.path_excluded(
        "vendor-foo/package.json", patterns
    ), "vendor-foo/package.json should match vendor*/"
    assert shadow.path_excluded(
        "vendor-bar/sub/file.js", patterns
    ), "vendor-bar/sub/file.js should match vendor*/"


# ---------------------------------------------------------------------------
# T-SHD03 — F-M1: literal __pycache__/ still excluded (no regression)
# ---------------------------------------------------------------------------


def test_path_excluded_literal_pycache():
    """Literal dir patterns (no glob chars) must still be excluded."""
    assert shadow.path_excluded(
        "src/__pycache__/foo.pyc", shadow.DEFAULT_EXCLUDES
    ), "src/__pycache__/foo.pyc should be excluded by __pycache__/"


# ---------------------------------------------------------------------------
# T-SHD04 — F-M1: a non-matching path is not excluded
# ---------------------------------------------------------------------------


def test_path_excluded_non_match():
    """src/app.py must not be excluded by any default exclude."""
    assert not shadow.path_excluded(
        "src/app.py", shadow.DEFAULT_EXCLUDES
    ), "src/app.py should not be excluded"


# ---------------------------------------------------------------------------
# T-SHD05 — F-M1: *.egg-info/ with trailing slash (as used in tree_digest dir pruning)
# ---------------------------------------------------------------------------


def test_path_excluded_egg_info_dir_trailing_slash():
    """path_excluded called with trailing slash (tree_digest dir pruning path)."""
    assert shadow.path_excluded(
        "src/foo.egg-info/", shadow.DEFAULT_EXCLUDES
    ), "src/foo.egg-info/ (dir with trailing slash) should be excluded by *.egg-info/"


# ---------------------------------------------------------------------------
# T-SHD06 — F-M2: shadow_commit raises ShadowGitError on git-add failure
# ---------------------------------------------------------------------------


def test_shadow_commit_raises_on_add_failure(tmp_path):
    """git add returncode != 0 → ShadowGitError raised (not silent None)."""
    fail_add = MagicMock(
        returncode=1, stderr="fatal: unable to write new_object_file", stdout=""
    )
    ok_staged = MagicMock(returncode=1, stdout="", stderr="")  # staged (irrelevant)

    with (
        patch.object(shadow, "run_git", side_effect=[fail_add, ok_staged]),
        pytest.raises(shadow.ShadowGitError, match="git add failed"),
    ):
        shadow.shadow_commit("test-project", tmp_path, "test commit")


# ---------------------------------------------------------------------------
# T-SHD07 — F-M2: shadow_commit raises ShadowGitError on git-commit failure
# ---------------------------------------------------------------------------


def test_shadow_commit_raises_on_commit_failure(tmp_path):
    """git commit returncode != 0 → ShadowGitError raised (not silent None)."""
    ok_add = MagicMock(returncode=0, stderr="", stdout="")
    staged = MagicMock(returncode=1, stdout="", stderr="")  # index dirty
    fail_commit = MagicMock(
        returncode=1, stderr="error: pathspec '.' did not match", stdout=""
    )

    with (
        patch.object(shadow, "run_git", side_effect=[ok_add, staged, fail_commit]),
        pytest.raises(shadow.ShadowGitError, match="git commit failed"),
    ):
        shadow.shadow_commit("test-project", tmp_path, "test commit")


# ---------------------------------------------------------------------------
# T-SHD08 — F-M2: shadow_commit returns None on clean tree (no error, no raise)
# ---------------------------------------------------------------------------


def test_shadow_commit_clean_tree_returns_none(tmp_path):
    """Clean tree (git diff --cached exits 0) → None returned, no error."""
    ok_add = MagicMock(returncode=0, stderr="", stdout="")
    clean_staged = MagicMock(returncode=0, stdout="", stderr="")  # nothing staged

    with patch.object(shadow, "run_git", side_effect=[ok_add, clean_staged]):
        result = shadow.shadow_commit("test-project", tmp_path, "test commit")

    assert result is None


# ---------------------------------------------------------------------------
# T-SHD09 — F-M2: run_shadow_pass emits ERROR finding on git failure (not silent)
# ---------------------------------------------------------------------------


def test_run_shadow_pass_emits_error_finding_on_git_failure(tmp_path):
    """ShadowGitError from shadow_commit → ERROR finding in summary (not silent)."""
    drift_state: dict = {}

    with (
        patch.object(shadow, "git_available", return_value=True),
        patch.object(shadow, "ensure_setup", return_value=True),
        patch.object(
            shadow,
            "tree_digest",
            return_value=MagicMock(
                digest="v1:abc", skipped_symlinks=[], file_count=3, truncated=False
            ),
        ),
        patch.object(
            shadow,
            "shadow_commit",
            side_effect=shadow.ShadowGitError(
                "git add failed (rc=128): fatal: write error"
            ),
        ),
    ):
        summary = shadow.run_shadow_pass("proj", tmp_path, drift_state)

    findings = summary["findings"]
    assert any(
        f["finding_type"] == "ERROR" for f in findings
    ), f"Expected ERROR finding on git failure; got: {findings}"
    error_msgs = [
        f["recommended_action"] for f in findings if f["finding_type"] == "ERROR"
    ]
    assert any(
        "git add failed" in m for m in error_msgs
    ), f"ERROR finding message should contain failure reason; got: {error_msgs}"


# ---------------------------------------------------------------------------
# T-SHD10 — F-L1: select_strategy git-ahead-behind + findings list → FRICTION
# ---------------------------------------------------------------------------


def test_select_strategy_git_ahead_behind_emits_friction():
    """Selecting git-ahead-behind with a findings list appends a FRICTION finding."""
    entry = {"id": "comp-1", "entry_id": "comp-1", "drift_strategy": "git-ahead-behind"}
    findings: list = []
    strategy = shadow.select_strategy(entry, None, findings)

    assert strategy == "git-ahead-behind", "Strategy should still be returned as-is"
    assert len(findings) == 1, f"Expected 1 FRICTION finding; got {len(findings)}"
    assert (
        findings[0]["finding_type"] == "FRICTION"
    ), f"Expected FRICTION; got {findings[0]}"
    assert "git-ahead-behind" in findings[0]["recommended_action"]


# ---------------------------------------------------------------------------
# T-SHD11 — F-L1: select_strategy git-ahead-behind without findings list → no error
# ---------------------------------------------------------------------------


def test_select_strategy_git_ahead_behind_no_findings_list():
    """Selecting git-ahead-behind without a findings list → no error, strategy returned."""
    entry = {"id": "comp-1", "drift_strategy": "git-ahead-behind"}
    strategy = shadow.select_strategy(entry, None)  # no findings param

    assert strategy == "git-ahead-behind"


# ---------------------------------------------------------------------------
# T-SHD12 — F-L1: content-digest → no FRICTION appended
# ---------------------------------------------------------------------------


def test_select_strategy_content_digest_no_friction():
    """Normal strategies (content-digest, tree-digest) do not emit FRICTION."""
    findings: list = []
    entry = {"id": "comp-1", "drift_strategy": "content-digest"}
    shadow.select_strategy(entry, None, findings)

    assert not findings, f"Expected no findings for content-digest; got {findings}"


# ---------------------------------------------------------------------------
# T-SHD13 — F-L2: rename-away from watched area → finding emitted via old_path
# ---------------------------------------------------------------------------


def test_correlate_doc_drift_rename_away_matched(tmp_path):
    """A file renamed OUT of a watched area must correlate via old_path."""
    # Rename from src/api/users.py (watched) → lib/users.py (unwatched)
    changes = [_make_change("R", "src/api/users.py", "lib/users.py", similarity=95)]
    findings = shadow.correlate_doc_drift(changes, _DOCOWNERS, tmp_path)
    assert len(findings) > 0, (
        "Rename-away from watched src/api/** should produce a DOC_DRIFT finding "
        f"via old_path; got: {findings}"
    )


# ---------------------------------------------------------------------------
# T-SHD14 — F-L2: rename-into watched area → finding via new_path (no regression)
# ---------------------------------------------------------------------------


def test_correlate_doc_drift_rename_into_watched(tmp_path):
    """A file renamed INTO a watched area is still found via new_path (cpath)."""
    # Rename from lib/helper.py (unwatched) → src/api/helper.py (watched)
    changes = [_make_change("R", "lib/helper.py", "src/api/helper.py", similarity=90)]
    findings = shadow.correlate_doc_drift(changes, _DOCOWNERS, tmp_path)
    assert len(findings) > 0, (
        "Rename into watched src/api/** should produce a DOC_DRIFT finding; "
        f"got: {findings}"
    )


# ---------------------------------------------------------------------------
# T-SHD15 — F-M3 descope guard: all-M (normal modify) still fires doc-drift
# ---------------------------------------------------------------------------


def test_correlate_doc_drift_all_m_still_fires(tmp_path):
    """All-M commit on a watched path MUST still emit a finding (no reformat guard).

    Regression guard for the descoped F-M3: git --name-status cannot distinguish a
    reformat from a real change, so the guard was removed. A plain modify commit
    touching a watched code path must always produce a DOC_DRIFT finding.
    """
    changes = [_make_change("M", "src/api/users.py")]
    findings = shadow.correlate_doc_drift(changes, _DOCOWNERS, tmp_path)
    assert len(findings) > 0, (
        "An all-M commit on a watched path must still produce a DOC_DRIFT finding; "
        f"got: {findings}"
    )
