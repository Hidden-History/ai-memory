"""
Tests for aim_sot_verify — 16-check verification gate (Item 4).

Coverage:
  T-VF-S1-pass / T-VF-S1-fail                  — schema compliance
  T-VF-S2-pass / T-VF-S2-fail                  — ID uniqueness
  T-VF-S3-pass / T-VF-S3-fail                  — YAML parse (format conformance)
  T-VF-S4-pass / T-VF-S4-fail                  — controlled-vocabulary (enums from schema)
  T-VF-R1-pass / T-VF-R1-fail
  T-VF-R1-superseded-exempt                     — superseded entries skip R1
  T-VF-R2-default-no-downgrade                  — URL fields present, no --check-urls → PASS (not CONDITIONAL)
  T-VF-R2-no-urls-pass                          — no URL fields → R2 no-op
  T-VF-R2-checkurls-warn                        — --check-urls + non-resolving URL → warning
  T-VF-R3-pass                                  — cross-ref (always PASS)
  T-VF-R4-no-roster-noop                        — no CODEOWNERS → R4 silent no-op
  T-VF-R4-roster-pass                           — owner in CODEOWNERS → PASS
  T-VF-R4-roster-fail                           — owner not in CODEOWNERS → warning
  T-VF-R4-normalized                            — "alice" vs "@alice" → passes after normalization
  T-VF-C1-pass                                  — no unregistered candidates
  T-VF-C1-unregistered                          — unregistered component → CONDITIONAL (not FAIL)
  T-VF-C2-pass                                  — no orphans (always PASS)
  T-VF-C3-pass                                  — missing path + superseded → C3 PASS
  T-VF-C3-fail                                  — missing path + active → C3 FAIL
  T-VF-C4-na                                    — C4 is N/A (no findings ever)
  T-VF-K1-hash-changed                          — MANDATORY: hash change → K1 CONDITIONAL
  T-VF-K1-no-change                             — hash unchanged → K1 PASS
  T-VF-K1-cold-start                            — no baseline (cold-start) → K1 CONDITIONAL
  T-VF-K1-unverified                            — drift_status=='unverified' → K1 CONDITIONAL
  T-VF-K1-baseline-loss                         — populated cache, lost record → distinct msg
  T-VF-K1-cold-start-cmd_run                    — cold-start end-to-end → verdict CONDITIONAL
  T-VF-K1-resolution-failure                    — project_id None + populated cache → CONDITIONAL + stderr warn
  T-VF-project-id-override                       — --project-id keys the cache directly → K1 ran-pass
  T-VF-verdict-buckets                          — ran-pass / no-op / skipped reported distinctly
  T-VF-K4-proposal-dup-committed                — proposed loc collides with committed loc → K4 FAIL
  T-VF-K3-exec-nonzero / -timeout / -oserror    — --exec-drift-checks outcomes CONDITIONAL, never FAIL
  T-VF-K2-pass                                  — valid past date
  T-VF-K2-fail-future                           — future date
  T-VF-K2-fail-epoch                            — epoch default
  T-VF-K2-yaml-date                             — YAML-native datetime.date → no crash
  T-VF-K3-pass                                  — parseable + binary on PATH
  T-VF-K3-fail-parse                            — shlex syntax error → hard FAIL
  T-VF-K3-fail-notfound                         — binary not on PATH → CONDITIONAL
  T-VF-K4-pass                                  — unique sot_locations
  T-VF-K4-fail                                  — duplicate sot_location → FAIL
  T-VF-K1-via-cmd_run                           — K1 end-to-end through cmd_run (cached sha mismatch)
  T-VF-S2-proposal-dup-existing                 — proposed id collides with committed id → S2 FAIL
  T-VF-S4-schema-sourced                        — novel enum in custom sc accepted (proves schema-driven)
  T-VF-proposal-mode                            — --proposal path exercises proposal entries
  T-VF-audit-mode                               — default standalone audit path
  T-VF-verdict-pass                             — 0 fail / 0 warn → PASS
  T-VF-verdict-pass-no-codeowners               — clean registry, no CODEOWNERS → PASS (R4 no-op)
  T-VF-verdict-conditional                      — 0 fail / ≥1 warn → CONDITIONAL (roster mismatch)
  T-VF-verdict-fail                             — ≥1 fail → FAIL

All tests are hermetic (no network, tmp_path, stores/project_id mocked).
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Module import (importlib pattern — no package install required)
# ---------------------------------------------------------------------------

_VERIFY_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "_ai-memory"
    / "skills"
    / "aim-sot"
    / "scripts"
    / "aim_sot_verify.py"
)
_spec = importlib.util.spec_from_file_location("aim_sot_verify", _VERIFY_SCRIPT)
vf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vf)


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sc():
    """Schema constraints loaded once for all check-function unit tests."""
    return vf._load_schema_constraints()


def _write_registry(tmp_path: Path, entries: list) -> Path:
    sot_dir = tmp_path / ".sot"
    sot_dir.mkdir(exist_ok=True)
    reg = sot_dir / "registry.yaml"
    reg.write_text(
        yaml.dump({"schema_version": "1.0", "entries": entries}), encoding="utf-8"
    )
    return reg


def _good_entry(
    tmp_path: Path,
    entry_id: str = "my-svc",
    *,
    create_file: bool = True,
) -> dict:
    """Return a valid entry; optionally create the sot_location file."""
    filename = f"{entry_id}.md"
    if create_file:
        (tmp_path / filename).write_text(f"content for {entry_id}", encoding="utf-8")
    return {
        "id": entry_id,
        "kind": "service",
        "boundary_type": "path",
        "sot_location": filename,
        "owner": "@team-auth",
        "description": f"A test service: {entry_id}",
        "status": "active",
        "last_verified": "2025-01-01",
    }


def _make_args(**kwargs) -> argparse.Namespace:
    """Build a minimal cmd_run args namespace."""
    defaults = {
        "cmd": "run",
        "registry": None,
        "proposal": None,
        "check_urls": False,
        "exec_drift_checks": False,
        "as_json": True,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _run_cmd(
    args: argparse.Namespace,
    tmp_path: Path,
    *,
    cache: dict | None = None,
    drift_state_populated: bool = False,
    capture_stderr: bool = False,
):
    """Run cmd_run with project_id + discover_candidates mocked. Returns verdict dict.

    When cache is not None, _resolve_project_id returns a dummy project id so
    _read_drift_cache is actually reached and returns the supplied cache dict.
    When cache is None, project_id stays None and K1 uses an empty cache (cold-start).
    drift_state_populated controls the (hermetic) _drift_state_populated() result.
    capture_stderr=True returns (verdict, stderr_text).
    """
    import io
    from contextlib import redirect_stderr, redirect_stdout

    _cache = cache if cache is not None else {"components": {}}
    # Only activate the _read_drift_cache path when a cache dict is explicitly supplied.
    _project_id = "test-proj" if cache is not None else None

    buf = io.StringIO()
    err = io.StringIO()
    with (
        patch.object(vf, "_resolve_project_id", return_value=_project_id),
        patch.object(vf, "_read_drift_cache", return_value=_cache),
        patch.object(vf, "_discover_candidates", return_value=[]),
        patch.object(vf, "_drift_state_populated", return_value=drift_state_populated),
        redirect_stdout(buf),
        redirect_stderr(err),
    ):
        vf.cmd_run(args)

    verdict = json.loads(buf.getvalue())
    if capture_stderr:
        return verdict, err.getvalue()
    return verdict


def _sha256_short(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


# ---------------------------------------------------------------------------
# T-VF-S1-pass — all 6 required fields present
# ---------------------------------------------------------------------------


def test_S1_pass(sc):
    entry = {
        "id": "core",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "src/",
        "owner": "@team",
        "description": "Core service",
    }
    failures, warnings = vf._check_S1([entry], sc)
    assert not failures
    assert not warnings


# ---------------------------------------------------------------------------
# T-VF-S1-fail — missing required field
# ---------------------------------------------------------------------------


def test_S1_fail_missing_owner(sc):
    entry = {
        "id": "core",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "src/",
        "description": "Core service",
        # owner missing
    }
    failures, _ = vf._check_S1([entry], sc)
    assert any(f["check"] == "S1" and "owner" in f["detail"] for f in failures)


# ---------------------------------------------------------------------------
# T-VF-S2-pass — unique IDs
# ---------------------------------------------------------------------------


def test_S2_pass(sc):
    entries = [
        {"id": "svc-a", "kind": "service"},
        {"id": "svc-b", "kind": "library"},
    ]
    failures, _ = vf._check_S2(entries)
    assert not failures


# ---------------------------------------------------------------------------
# T-VF-S2-fail — duplicate ID
# ---------------------------------------------------------------------------


def test_S2_fail_duplicate_id(sc):
    entries = [{"id": "svc-a"}, {"id": "svc-a"}]
    failures, _ = vf._check_S2(entries)
    assert any(f["check"] == "S2" and "svc-a" in f["detail"] for f in failures)


# ---------------------------------------------------------------------------
# T-VF-S3-pass — valid YAML parsed successfully (via cmd_run)
# ---------------------------------------------------------------------------


def test_S3_pass(tmp_path):
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    codeowners = tmp_path / "CODEOWNERS"
    codeowners.write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)
    assert "S3" in verdict["checks_run"]
    assert not any(f["check"] == "S3" for f in verdict["failures"])


# ---------------------------------------------------------------------------
# T-VF-S3-fail — malformed YAML (not a mapping)
# ---------------------------------------------------------------------------


def test_S3_fail(tmp_path):
    sot_dir = tmp_path / ".sot"
    sot_dir.mkdir()
    reg = sot_dir / "registry.yaml"
    reg.write_text("this is not a mapping", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)
    assert verdict["verdict"] == "FAIL"
    assert any(f["check"] == "S3" for f in verdict["failures"])


# ---------------------------------------------------------------------------
# T-VF-S4-pass — valid enum values
# ---------------------------------------------------------------------------


def test_S4_pass(sc):
    entry = {
        "id": "core",
        "kind": "service",
        "boundary_type": "path",
        "status": "active",
    }
    failures, _ = vf._check_S4([entry], sc)
    assert not failures


# ---------------------------------------------------------------------------
# T-VF-S4-fail — invalid kind (asserts enum sourced from schema, not hardcoded)
# ---------------------------------------------------------------------------


def test_S4_fail_invalid_kind(sc):
    entry = {"id": "core", "kind": "invalid_kind_xyz"}
    failures, _ = vf._check_S4([entry], sc)
    assert any(f["check"] == "S4" and "kind" in f["detail"] for f in failures)
    # The allowed list should come from the schema, not hardcoded strings.
    # Assert the failure detail contains schema-sourced enum values.
    detail = next(f["detail"] for f in failures if "kind" in f["detail"])
    assert "service" in detail  # schema-sourced value present in error


# ---------------------------------------------------------------------------
# T-VF-R1-pass — sot_location exists on disk
# ---------------------------------------------------------------------------


def test_R1_pass(tmp_path):
    (tmp_path / "src").mkdir()
    entry = {"id": "core", "sot_location": "src/", "status": "active"}
    failures, _ = vf._check_R1([entry], tmp_path)
    assert not failures


# ---------------------------------------------------------------------------
# T-VF-R1-fail — sot_location does not exist
# ---------------------------------------------------------------------------


def test_R1_fail_missing_path(tmp_path):
    entry = {"id": "core", "sot_location": "nonexistent/", "status": "active"}
    failures, _ = vf._check_R1([entry], tmp_path)
    assert any(f["check"] == "R1" and "nonexistent/" in f["detail"] for f in failures)


# ---------------------------------------------------------------------------
# T-VF-R1-superseded-exempt — missing path + status=superseded → R1 does NOT fail
# ---------------------------------------------------------------------------


def test_R1_superseded_exempt(tmp_path):
    entry = {
        "id": "old-svc",
        "sot_location": "src/old-svc/",  # path does not exist
        "status": "superseded",
    }
    failures, _ = vf._check_R1([entry], tmp_path)
    assert not failures, "superseded entries must be exempt from R1"


# ---------------------------------------------------------------------------
# T-VF-R2-default-no-downgrade — docs_url set, no --check-urls → no R2 warning
# ---------------------------------------------------------------------------


def test_R2_default_no_downgrade(tmp_path):
    """R2 default is a no-op. URL fields must NOT add a warning or downgrade verdict."""
    entry = _good_entry(tmp_path)
    entry["docs_url"] = "https://example.com/docs"
    reg = _write_registry(tmp_path, [entry])
    codeowners = tmp_path / "CODEOWNERS"
    codeowners.write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg), check_urls=False)
    verdict = _run_cmd(args, tmp_path)
    r2_warnings = [w for w in verdict["warnings"] if w["check"] == "R2"]
    assert (
        not r2_warnings
    ), "R2 must not emit warnings in default (no --check-urls) mode"
    # Verdict may still be PASS (R4 passes with CODEOWNERS).
    assert verdict["verdict"] != "FAIL"


# ---------------------------------------------------------------------------
# T-VF-R2-no-urls-pass — no URL fields → R2 produces no warning
# ---------------------------------------------------------------------------


def test_R2_no_urls_pass():
    entry = {
        "id": "svc",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "src/",
        "owner": "@team",
        "description": "No URLs",
        "status": "active",
    }
    _, warnings = vf._check_R2([entry], check_urls=True)
    assert not warnings


# ---------------------------------------------------------------------------
# T-VF-R2-checkurls-warn — --check-urls + non-resolving URL → warning (not fail)
# ---------------------------------------------------------------------------


def test_R2_checkurls_warn():
    """Monkeypatch urlopen to simulate a non-200 response. Expect warning, never fail."""
    entry = {
        "id": "svc",
        "sot_location": "src/",
        "docs_url": "https://broken.example.com/docs",
    }

    mock_resp = MagicMock()
    mock_resp.status = 404
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    def _mock_urlopen(req, timeout=10):
        return mock_resp

    failures, warnings = vf._check_R2([entry], check_urls=True, _urlopen=_mock_urlopen)
    assert not failures, "R2 must never hard-FAIL on network"
    assert any(w["check"] == "R2" for w in warnings)


# ---------------------------------------------------------------------------
# T-VF-R3-pass — cross-ref (always PASS with current schema)
# ---------------------------------------------------------------------------


def test_R3_pass():
    """R3 is a no-op — no _check_R3 function, and 'R3' is in _CHECKS_ALL."""
    assert "R3" in vf._CHECKS_ALL
    # R3 is a no-op comment in _run_all_checks — no dedicated function.
    assert not hasattr(vf, "_check_R3")


# ---------------------------------------------------------------------------
# T-VF-R4-no-roster-noop — no CODEOWNERS → R4 silent no-op (PASS reachable)
# ---------------------------------------------------------------------------


def test_R4_no_roster_noop(tmp_path):
    """No CODEOWNERS → R4 must return ([], []) — no warnings, no failures.

    PASS must be reachable for projects that don't maintain a CODEOWNERS file
    (same rationale as R2 offline no-op: don't penalise absence of optional infra).
    """
    entry = {"id": "svc", "owner": "@team-auth"}
    failures, warnings = vf._check_R4([entry], tmp_path)
    assert not failures
    assert not warnings, "absent CODEOWNERS must be a silent no-op — no R4 warnings"


# ---------------------------------------------------------------------------
# T-VF-R4-roster-pass — owner in CODEOWNERS → R4 PASS
# ---------------------------------------------------------------------------


def test_R4_roster_pass(tmp_path):
    (tmp_path / "CODEOWNERS").write_text("src/ @team-auth\n", encoding="utf-8")
    entry = {"id": "svc", "owner": "@team-auth"}
    _, warnings = vf._check_R4([entry], tmp_path)
    assert not warnings


# ---------------------------------------------------------------------------
# T-VF-R4-roster-fail — owner not in CODEOWNERS → warning
# ---------------------------------------------------------------------------


def test_R4_roster_fail(tmp_path):
    (tmp_path / "CODEOWNERS").write_text("src/ @team-auth\n", encoding="utf-8")
    entry = {"id": "svc", "owner": "@team-unknown"}
    _, warnings = vf._check_R4([entry], tmp_path)
    assert any(w["check"] == "R4" and "team-unknown" in w["detail"] for w in warnings)


# ---------------------------------------------------------------------------
# T-VF-R4-normalized — "alice" vs "@alice" → passes after normalization
# ---------------------------------------------------------------------------


def test_R4_normalized(tmp_path):
    """owner: 'alice' (no @) vs CODEOWNERS '@alice' → normalized match → PASS."""
    (tmp_path / "CODEOWNERS").write_text("* @alice\n", encoding="utf-8")
    entry = {"id": "svc", "owner": "alice"}  # no @ prefix
    _, warnings = vf._check_R4([entry], tmp_path)
    assert (
        not warnings
    ), "owner without @ should match CODEOWNERS @handle after normalization"


# ---------------------------------------------------------------------------
# T-VF-C1-pass — no unregistered candidates
# ---------------------------------------------------------------------------


def test_C1_pass(tmp_path):
    """No manifest files or visible subdirs in tmp_path → no candidates → C1 PASS."""
    entries = [{"id": "svc", "sot_location": "src/"}]
    # _discover_candidates returns [] in a bare tmp_path (no manifests, no dirs).
    discovered: list[dict] = []
    _, warnings = vf._check_C1(entries, discovered)
    assert not warnings


# ---------------------------------------------------------------------------
# T-VF-C1-unregistered — unregistered component → CONDITIONAL (not FAIL)
# ---------------------------------------------------------------------------


def test_C1_unregistered(tmp_path):
    """Unregistered component → warning (CONDITIONAL), not a hard failure."""
    # Simulate discover finding a candidate not in the registry.
    discovered = [
        {
            "id": "myapp",
            "boundary_type": "component",
            "sot_location": "myapp/",
            "confidence": "high",
            "inferred_from": "package.json",
        }
    ]
    entries: list[dict] = []  # nothing registered
    failures, warnings = vf._check_C1(entries, discovered)
    assert (
        not failures
    ), "C1 must NOT hard-fail; unregistered candidates are CONDITIONAL"
    assert any(w["check"] == "C1" for w in warnings)


# ---------------------------------------------------------------------------
# T-VF-C2-pass — no orphan entries (always PASS)
# ---------------------------------------------------------------------------


def test_C2_pass():
    """C2 is a no-op — no _check_C2 function, and 'C2' is in _CHECKS_ALL."""
    assert "C2" in vf._CHECKS_ALL
    assert not hasattr(vf, "_check_C2")


# ---------------------------------------------------------------------------
# T-VF-C3-pass — missing path + status=superseded → C3 PASS
# ---------------------------------------------------------------------------


def test_C3_pass_superseded(tmp_path):
    entry = {
        "id": "old-svc",
        "sot_location": "src/old-svc/",  # does not exist
        "status": "superseded",
    }
    failures, _ = vf._check_C3([entry], tmp_path)
    assert not failures


# ---------------------------------------------------------------------------
# T-VF-C3-fail — missing path + status=active → C3 FAIL
# ---------------------------------------------------------------------------


def test_C3_fail_stale_active(tmp_path):
    entry = {
        "id": "stale-svc",
        "sot_location": "src/stale/",  # does not exist
        "status": "active",
    }
    failures, _ = vf._check_C3([entry], tmp_path)
    assert any(f["check"] == "C3" and "stale/" in f["detail"] for f in failures)


# ---------------------------------------------------------------------------
# T-VF-C4-na — C4 is N/A (no declared-count field → no findings ever)
# ---------------------------------------------------------------------------


def test_C4_na(tmp_path):
    """C4 is a no-op for the current schema — assert it never produces findings."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    codeowners = tmp_path / "CODEOWNERS"
    codeowners.write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)
    c4_findings = [
        x for x in verdict["failures"] + verdict["warnings"] if x["check"] == "C4"
    ]
    assert not c4_findings, "C4 is N/A — must never produce findings"


# ---------------------------------------------------------------------------
# T-VF-K1-hash-changed — MANDATORY: hash change → K1 CONDITIONAL
# ---------------------------------------------------------------------------


def test_K1_hash_changed(tmp_path):
    """Mandatory test: sha256(artifact) != last_verified_sha → K1 CONDITIONAL warning."""
    sot_file = tmp_path / "my-svc.py"
    original_content = b"original content"
    sot_file.write_bytes(original_content)
    original_sha = _sha256_short(original_content)

    # Modify file → hash changes
    sot_file.write_bytes(b"modified content -- now different")

    cache = {
        "components": {
            "my-svc": {
                "last_verified_sha": original_sha,
                "last_verified_at": "2026-01-01T00:00:00+00:00",
                "drift_status": "clean",
            }
        }
    }

    entry = {
        "id": "my-svc",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "my-svc.py",
        "owner": "@team-auth",
        "description": "Test service",
        "status": "active",
    }

    _, warnings = vf._check_K1([entry], tmp_path, cache)
    k1_warns = [w for w in warnings if w["check"] == "K1"]
    assert k1_warns, "K1 must emit a warning when content hash has changed"
    assert "re-confirmation" in k1_warns[0]["detail"].lower()
    assert original_sha in k1_warns[0]["detail"]


# ---------------------------------------------------------------------------
# T-VF-K1-no-change — hash unchanged → K1 PASS
# ---------------------------------------------------------------------------


def test_K1_no_change(tmp_path):
    sot_file = tmp_path / "svc.py"
    content = b"stable content"
    sot_file.write_bytes(content)
    current_sha = _sha256_short(content)

    cache = {"components": {"svc": {"last_verified_sha": current_sha}}}
    entry = {"id": "svc", "sot_location": "svc.py", "status": "active"}

    _, warnings = vf._check_K1([entry], tmp_path, cache)
    assert not [w for w in warnings if w["check"] == "K1"]


# ---------------------------------------------------------------------------
# T-VF-K1-cold-start — no baseline (cold-start) → K1 CONDITIONAL, not silent PASS
# ---------------------------------------------------------------------------


def test_K1_cold_start_conditional(tmp_path):
    """Cold-start (no cache record) must surface CONDITIONAL — a missing baseline
    means content was never machine-confirmed; silent PASS would mask that (H3-c)."""
    sot_file = tmp_path / "svc.py"
    sot_file.write_bytes(b"some content")

    empty_cache: dict = {"components": {}}
    entry = {"id": "svc", "sot_location": "svc.py", "status": "active"}

    _, warnings = vf._check_K1(
        [entry], tmp_path, empty_cache, project_id_resolved=True, cache_populated=False
    )
    k1 = [w for w in warnings if w["check"] == "K1"]
    assert k1, "cold-start (no baseline) must emit a K1 CONDITIONAL warning"
    assert k1[0].get("kind") == "skipped_no_baseline"
    assert "cold-start" in k1[0]["detail"]
    assert "human confirmation" in k1[0]["detail"].lower()


# ---------------------------------------------------------------------------
# T-VF-K1-unverified — drift_status=='unverified' baseline → K1 CONDITIONAL
# ---------------------------------------------------------------------------


def test_K1_unverified_conditional(tmp_path):
    """An entry the engine recorded as drift_status=='unverified' (cold-start per
    the 5a contract) has no confirmed baseline → K1 CONDITIONAL, not PASS."""
    sot_file = tmp_path / "svc.py"
    content = b"some content"
    sot_file.write_bytes(content)

    cache = {
        "components": {
            "svc": {
                "last_verified_sha": _sha256_short(content),
                "drift_status": "unverified",
            }
        }
    }
    entry = {"id": "svc", "sot_location": "svc.py", "status": "active"}

    _, warnings = vf._check_K1([entry], tmp_path, cache, project_id_resolved=True)
    k1 = [w for w in warnings if w["check"] == "K1"]
    assert k1, "drift_status=='unverified' must emit a K1 CONDITIONAL warning"
    assert k1[0].get("kind") == "skipped_no_baseline"
    assert "unverified" in k1[0]["detail"]


# ---------------------------------------------------------------------------
# T-VF-K1-baseline-loss — populated cache but entry record lost → distinct message
# ---------------------------------------------------------------------------


def test_K1_baseline_loss_message(tmp_path):
    """No record for THIS entry while the project cache has other entries → baseline-loss
    message (distinct from genuine cold-start).

    After V-LOW-1 the project-scoped cache (bool(components)) determines the label, not
    the global cache_populated flag. A project with other cached entries but no record
    for this specific entry is 'baseline-loss' — not 'cold-start'.
    """
    sot_file = tmp_path / "svc.py"
    sot_file.write_bytes(b"some content")

    entry = {"id": "svc", "sot_location": "svc.py", "status": "active"}
    # Project cache has another component — 'svc' is absent (baseline-loss, not cold-start)
    _, warnings = vf._check_K1(
        [entry],
        tmp_path,
        {
            "components": {
                "other-svc": {"last_verified_sha": "abcd1234", "drift_status": "clean"}
            }
        },
        project_id_resolved=True,
        cache_populated=False,  # global is irrelevant when project_id_resolved=True (V-LOW-1)
    )
    k1 = [w for w in warnings if w["check"] == "K1"]
    assert k1
    assert "baseline-loss" in k1[0]["detail"]
    assert "cold-start" not in k1[0]["detail"]


# ---------------------------------------------------------------------------
# T-VF-K2-pass — valid past date
# ---------------------------------------------------------------------------


def test_K2_pass():
    entry = {"id": "svc", "last_verified": "2025-01-01"}
    failures, _ = vf._check_K2([entry])
    assert not failures


# ---------------------------------------------------------------------------
# T-VF-K2-fail-future — date in the future
# ---------------------------------------------------------------------------


def test_K2_fail_future():
    future = (
        (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10))
        .date()
        .isoformat()
    )
    entry = {"id": "svc", "last_verified": future}
    failures, _ = vf._check_K2([entry])
    assert any(f["check"] == "K2" and "future" in f["detail"] for f in failures)


# ---------------------------------------------------------------------------
# T-VF-K2-fail-epoch — epoch default date
# ---------------------------------------------------------------------------


def test_K2_fail_epoch():
    entry = {"id": "svc", "last_verified": "1970-01-01"}
    failures, _ = vf._check_K2([entry])
    assert any(f["check"] == "K2" and "epoch" in f["detail"] for f in failures)


# ---------------------------------------------------------------------------
# T-VF-K2-yaml-date — YAML-native datetime.date → no crash
# ---------------------------------------------------------------------------


def test_K2_yaml_date():
    """Unquoted 'last_verified: 2025-06-01' parses as datetime.date in YAML.
    K2 must handle this without raising TypeError (str(raw).strip() guard)."""
    yaml_date = datetime.date(2025, 6, 1)  # simulate what yaml.safe_load produces
    entry = {"id": "svc", "last_verified": yaml_date}
    failures, _ = vf._check_K2([entry])
    assert (
        not failures
    ), "YAML-native datetime.date must be handled without crash or false failure"


# ---------------------------------------------------------------------------
# T-VF-K3-pass — parseable command with binary on PATH
# ---------------------------------------------------------------------------


def test_K3_pass():
    entry = {"id": "svc", "drift_check": "echo ok"}
    failures, warnings = vf._check_K3([entry], exec_drift_checks=False)
    assert not failures
    assert not warnings


# ---------------------------------------------------------------------------
# T-VF-K3-fail-parse — malformed shlex string → hard FAIL
# ---------------------------------------------------------------------------


def test_K3_fail_parse():
    entry = {"id": "svc", "drift_check": "echo 'unclosed string"}
    failures, warnings = vf._check_K3([entry], exec_drift_checks=False)
    assert any(f["check"] == "K3" and "syntax" in f["detail"].lower() for f in failures)
    assert not warnings


# ---------------------------------------------------------------------------
# T-VF-K3-fail-notfound — binary not on PATH → CONDITIONAL (not FAIL)
# ---------------------------------------------------------------------------


def test_K3_fail_notfound():
    entry = {
        "id": "svc",
        "drift_check": "definitely_not_a_real_binary_xyz_abc_999 --arg",
    }
    failures, warnings = vf._check_K3([entry], exec_drift_checks=False)
    assert (
        not failures
    ), "binary-not-on-PATH must be a warning (CONDITIONAL), not a hard FAIL"
    assert any(
        w["check"] == "K3" and "not found" in w["detail"].lower() for w in warnings
    )


# ---------------------------------------------------------------------------
# T-VF-K4-pass — unique sot_locations
# ---------------------------------------------------------------------------


def test_K4_pass():
    entries = [
        {"id": "svc-a", "sot_location": "src/a/"},
        {"id": "svc-b", "sot_location": "src/b/"},
    ]
    failures, _ = vf._check_K4(entries)
    assert not failures


# ---------------------------------------------------------------------------
# T-VF-K4-fail — duplicate sot_location → hard FAIL
# ---------------------------------------------------------------------------


def test_K4_fail_collision():
    entries = [
        {"id": "svc-a", "sot_location": "src/shared/"},
        {"id": "svc-b", "sot_location": "src/shared/"},
    ]
    failures, _ = vf._check_K4(entries)
    assert any(f["check"] == "K4" and "src/shared/" in f["detail"] for f in failures)


# ---------------------------------------------------------------------------
# T-VF-audit-mode — default standalone audit exercises the committed registry
# ---------------------------------------------------------------------------


def test_audit_mode(tmp_path):
    """No --proposal: verify reads from the committed .sot/registry.yaml."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)
    # All 16 checks appear in checks_run
    assert set(vf._CHECKS_ALL).issubset(set(verdict["checks_run"]))


# ---------------------------------------------------------------------------
# T-VF-proposal-mode — --proposal path gates proposal entries (S1 + R1 checked)
# ---------------------------------------------------------------------------


def test_proposal_mode(tmp_path):
    """--proposal accepts a JSON file with 'entries' key; S1 + R1 run against them."""
    # Create the sot_location target
    (tmp_path / "api.yaml").write_text("openapi: 3.0\n", encoding="utf-8")

    proposal_entry = {
        "id": "api-svc",
        "kind": "api",
        "boundary_type": "component",
        "sot_location": "api.yaml",
        "owner": "@team-auth",
        "description": "API service proposal",
        "status": "proposed",
    }
    proposal_file = tmp_path / "proposal.json"
    proposal_file.write_text(
        json.dumps({"entries": [proposal_entry]}), encoding="utf-8"
    )

    # Need a real registry.yaml too (for project_root resolution)
    reg = _write_registry(tmp_path, [])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg), proposal=str(proposal_file))
    verdict = _run_cmd(args, tmp_path)

    # S1 and R1 were checked against proposal entries
    assert set(vf._CHECKS_ALL).issubset(set(verdict["checks_run"]))
    # The proposal entry is valid — expect PASS or CONDITIONAL (R4 may warn)
    assert verdict["verdict"] != "FAIL"
    r1_failures = [f for f in verdict["failures"] if f["check"] == "R1"]
    s1_failures = [f for f in verdict["failures"] if f["check"] == "S1"]
    assert not r1_failures, "sot_location exists — R1 should not fail"
    assert not s1_failures, "all required fields present — S1 should not fail"


# ---------------------------------------------------------------------------
# T-VF-verdict-pass — 0 failures, 0 warnings → PASS
# ---------------------------------------------------------------------------


def _clean_baseline_cache(tmp_path: Path, entry: dict) -> dict:
    """5a cache with a clean, matching baseline for entry so K1 ran-passes."""
    sha = _sha256_short((tmp_path / entry["sot_location"]).read_bytes())
    return {
        "components": {entry["id"]: {"last_verified_sha": sha, "drift_status": "clean"}}
    }


def test_verdict_pass(tmp_path):
    """Registry with one clean entry + matching baseline, CODEOWNERS → PASS."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path, cache=_clean_baseline_cache(tmp_path, entry))
    assert verdict["verdict"] == "PASS"
    assert verdict["fail_count"] == 0
    assert not verdict["warnings"]


# ---------------------------------------------------------------------------
# T-VF-verdict-pass-no-codeowners — clean registry with NO CODEOWNERS → PASS
# ---------------------------------------------------------------------------


def test_verdict_pass_no_codeowners(tmp_path):
    """Regression guard: absent CODEOWNERS must not block PASS.

    R4 is a no-op when CODEOWNERS is absent; a clean registry must reach PASS.
    """
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    # Intentionally no CODEOWNERS written

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path, cache=_clean_baseline_cache(tmp_path, entry))
    assert (
        verdict["verdict"] == "PASS"
    ), "No CODEOWNERS must not prevent PASS — R4 absent-roster is a silent no-op"
    assert not verdict["warnings"]


# ---------------------------------------------------------------------------
# T-VF-verdict-conditional — 0 failures, ≥1 warning → CONDITIONAL
# ---------------------------------------------------------------------------


def test_verdict_conditional(tmp_path):
    """Roster-present mismatch → R4 warning → CONDITIONAL.

    K1 is also CONDITIONAL here (no cache supplied → cold-start skipped_no_baseline).
    """
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    # CODEOWNERS present but does NOT include @team-auth → R4 mismatch warning
    (tmp_path / "CODEOWNERS").write_text("* @team-other\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)
    assert verdict["verdict"] == "CONDITIONAL"
    assert verdict["fail_count"] == 0
    assert any(w["check"] == "R4" for w in verdict["warnings"])


# ---------------------------------------------------------------------------
# T-VF-verdict-fail — ≥1 failure → FAIL
# ---------------------------------------------------------------------------


def test_verdict_fail(tmp_path):
    """Entry with missing sot_location (active) → R1 + C3 FAIL."""
    entry = {
        "id": "broken-svc",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "src/does-not-exist/",  # does not exist
        "owner": "@team-auth",
        "description": "Broken service",
        "status": "active",
        "last_verified": "2025-01-01",
    }
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)
    assert verdict["verdict"] == "FAIL"
    assert verdict["fail_count"] > 0


# ---------------------------------------------------------------------------
# T-VF-pass-count — pass_count = distinct check IDs with zero findings
# ---------------------------------------------------------------------------


def test_pass_count_correct(tmp_path):
    """pass_count counts ONLY ran-pass checks — no-op (R3/C2/C4) and skipped checks
    are excluded so a flat count can't masquerade as full content verification."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path, cache=_clean_baseline_cache(tmp_path, entry))

    # pass_count == number of ran-pass checks (not a flat zero-findings subtraction)
    assert verdict["pass_count"] == len(verdict["ran_pass"])
    # The inert checks are reported as no-op, never as ran-pass.
    assert set(verdict["no_op"]) == {"R3", "C2", "C4"}
    assert not (set(verdict["ran_pass"]) & set(verdict["no_op"]))


# ---------------------------------------------------------------------------
# T-VF-S2-proposal-dup-existing — proposed id collides with committed id → S2 FAIL
# ---------------------------------------------------------------------------


def test_S2_proposal_dup_existing(tmp_path):
    """In --proposal mode, _check_S2 must seed with committed registry IDs (BP-024 S2).

    A proposal whose entry id matches an existing committed entry id must FAIL S2,
    not pass silently.
    """
    committed = _good_entry(tmp_path, entry_id="svc-a")
    reg = _write_registry(tmp_path, [committed])

    proposal_entry = {
        "id": "svc-a",  # same id as committed entry → collision
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "svc-a-v2.md",
        "owner": "@team-auth",
        "description": "Proposed replacement for svc-a",
        "status": "proposed",
    }
    proposal_file = tmp_path / "proposal.json"
    proposal_file.write_text(
        json.dumps({"entries": [proposal_entry]}), encoding="utf-8"
    )

    args = _make_args(registry=str(reg), proposal=str(proposal_file))
    verdict = _run_cmd(args, tmp_path)

    s2_failures = [f for f in verdict["failures"] if f["check"] == "S2"]
    assert s2_failures, "Proposed id colliding with a committed id must be an S2 FAIL"
    assert verdict["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# T-VF-S4-schema-sourced — novel enum in custom sc dict accepted (schema-driven proof)
# ---------------------------------------------------------------------------


def test_S4_schema_sourced():
    """S4 enums are data-driven from the sc object, not hardcoded in the function.

    Build a custom sc dict with a novel 'kind' enum value ('novel_kind_zzz').
    An entry using that value must NOT fail S4, proving the check reads from sc
    and not from a hardcoded list inside the function body.
    """
    custom_sc = {
        "entry_required": [],
        "entry_enums": {"kind": ["service", "novel_kind_zzz"]},
        "entry_str_fields": set(),
    }
    entry = {"id": "svc", "kind": "novel_kind_zzz"}
    failures, _ = vf._check_S4([entry], custom_sc)
    assert not failures, (
        "kind='novel_kind_zzz' is in the custom sc dict — S4 must not reject it, "
        "proving enums are read from sc and not hardcoded"
    )


# ---------------------------------------------------------------------------
# T-VF-K1-via-cmd_run — K1 end-to-end through cmd_run (cached sha mismatch)
# ---------------------------------------------------------------------------


def test_K1_via_cmd_run(tmp_path):
    """K1 fires end-to-end via cmd_run when the cached sha differs from current sha.

    Exercises the full path: _resolve_project_id → _read_drift_cache → _check_K1.
    """
    content = b"initial stable content"
    sot_file = tmp_path / "svc.md"
    sot_file.write_bytes(content)

    # Use a separate file for K1 trigger — create entry pointing to sot_file
    k1_entry = {
        "id": "k1-svc",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "svc.md",
        "owner": "@team-auth",
        "description": "K1 test service",
        "status": "active",
        "last_verified": "2025-01-01",
    }
    reg = _write_registry(tmp_path, [k1_entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    stale_sha = "00000000"  # intentionally differs from actual sha of svc.md
    cache = {"components": {"k1-svc": {"last_verified_sha": stale_sha}}}

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path, cache=cache)

    k1_warnings = [w for w in verdict["warnings"] if w["check"] == "K1"]
    assert (
        k1_warnings
    ), "K1 must fire end-to-end when cached sha differs from current sha"
    assert verdict["verdict"] == "CONDITIONAL"
    assert verdict["fail_count"] == 0


# ---------------------------------------------------------------------------
# T-VF-K1-cold-start-cmd_run — cold-start via cmd_run → verdict CONDITIONAL
# ---------------------------------------------------------------------------


def test_K1_cold_start_via_cmd_run(tmp_path):
    """End-to-end: no drift cache at all + a file-typed entry → K1 skipped-no-baseline
    → verdict CONDITIONAL (not the old silent PASS)."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path, drift_state_populated=False)

    assert verdict["verdict"] == "CONDITIONAL"
    assert verdict["fail_count"] == 0
    assert "K1" in verdict["skipped"]
    assert "K1" not in verdict["ran_pass"]
    k1 = [w for w in verdict["warnings"] if w["check"] == "K1"]
    assert k1 and "cold-start" in k1[0]["detail"]


# ---------------------------------------------------------------------------
# T-VF-K1-resolution-failure — project_id None + populated cache → CONDITIONAL + warn
# ---------------------------------------------------------------------------


def test_K1_resolution_failure_warns(tmp_path):
    """project_id unresolved while a drift cache exists → K1 CONDITIONAL + a stderr
    WARNING; a resolution failure must not silently zero a mandatory check (H3-c)."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict, stderr = _run_cmd(
        args, tmp_path, drift_state_populated=True, capture_stderr=True
    )

    assert verdict["verdict"] == "CONDITIONAL"
    assert "K1" in verdict["skipped"]
    k1 = [w for w in verdict["warnings"] if w["check"] == "K1"]
    assert k1 and k1[0].get("kind") == "skipped_no_baseline"
    assert "baseline-loss" in k1[0]["detail"]
    assert "project_id could not be resolved" in stderr


# ---------------------------------------------------------------------------
# T-VF-project-id-override — --project-id supplies the cache key explicitly
# ---------------------------------------------------------------------------


def test_project_id_override_resolves(tmp_path):
    """--project-id skips auto-resolution and keys into the drift cache directly,
    so K1 ran-passes against a matching baseline even when _resolve_project_id fails."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    sha = _sha256_short((tmp_path / entry["sot_location"]).read_bytes())
    cache = {
        "components": {entry["id"]: {"last_verified_sha": sha, "drift_status": "clean"}}
    }

    import io
    from contextlib import redirect_stdout

    args = _make_args(registry=str(reg), project_id="explicit-proj")
    resolve_mock = MagicMock(return_value=None)
    read_mock = MagicMock(return_value=cache)

    buf = io.StringIO()
    with (
        patch.object(vf, "_resolve_project_id", resolve_mock),
        patch.object(vf, "_read_drift_cache", read_mock),
        patch.object(vf, "_discover_candidates", return_value=[]),
        patch.object(vf, "_drift_state_populated", return_value=False),
        redirect_stdout(buf),
    ):
        vf.cmd_run(args)
    verdict = json.loads(buf.getvalue())

    resolve_mock.assert_not_called()  # override bypasses auto-resolution
    read_mock.assert_called_once_with("explicit-proj")
    assert verdict["verdict"] == "PASS"
    assert "K1" in verdict["ran_pass"]
    assert "K1" not in verdict["skipped"]


# ---------------------------------------------------------------------------
# T-VF-verdict-buckets — ran-pass / no-op / skipped reported distinctly
# ---------------------------------------------------------------------------


def test_verdict_buckets_distinct(tmp_path):
    """The verdict separates ran-pass from inert no-ops (R3/C2/C4) and skipped-K1
    so a human is not misled by a flat pass count (DD-D / M3)."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    # Cold-start: K1 skipped, R3/C2/C4 no-op, the rest ran-pass.
    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path, drift_state_populated=False)

    assert set(verdict["no_op"]) == {"R3", "C2", "C4"}
    assert verdict["skipped"] == ["K1"]
    assert "K1" not in verdict["ran_pass"]
    for noop in ("R3", "C2", "C4"):
        assert noop not in verdict["ran_pass"]
    # The three buckets + findings partition checks_run with no double-counting.
    finding_checks = {x["check"] for x in verdict["failures"] + verdict["warnings"]}
    classified = set(verdict["ran_pass"]) | set(verdict["no_op"]) | finding_checks
    assert classified == set(verdict["checks_run"])


# ---------------------------------------------------------------------------
# T-VF-K4-proposal-dup-committed — proposed loc collides with committed loc → FAIL
# ---------------------------------------------------------------------------


def test_K4_seed_committed_locations():
    """Unit: _check_K4 seeded with committed locations fails a colliding proposal."""
    proposal = [{"id": "svc-b", "sot_location": "svc-a.md"}]
    failures, _ = vf._check_K4(proposal, existing_locs={"svc-a.md": "svc-a"})
    assert any(
        f["check"] == "K4" and "svc-a.md" in f["detail"] and "svc-a" in f["detail"]
        for f in failures
    )


def test_K4_proposal_dup_committed_sot_location(tmp_path):
    """End-to-end: a proposed entry claiming a committed entry's sot_location must
    FAIL K4 in --proposal mode (symmetric with S2 id-collision seeding) (H4)."""
    committed = _good_entry(tmp_path, entry_id="svc-a")  # sot_location svc-a.md
    reg = _write_registry(tmp_path, [committed])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    proposal_entry = {
        "id": "svc-b",  # distinct id (so S2 does not fire) ...
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "svc-a.md",  # ... but collides with committed svc-a's loc
        "owner": "@team-auth",
        "description": "Proposed entry colliding on location",
        "status": "proposed",
    }
    proposal_file = tmp_path / "proposal.json"
    proposal_file.write_text(
        json.dumps({"entries": [proposal_entry]}), encoding="utf-8"
    )

    args = _make_args(registry=str(reg), proposal=str(proposal_file))
    verdict = _run_cmd(args, tmp_path)

    k4_failures = [f for f in verdict["failures"] if f["check"] == "K4"]
    assert k4_failures, "proposed loc colliding with a committed loc must FAIL K4"
    assert any("svc-a" in f["detail"] for f in k4_failures)
    assert verdict["verdict"] == "FAIL"
    s2_failures = [f for f in verdict["failures"] if f["check"] == "S2"]
    assert not s2_failures, "distinct ids → S2 must not fire (K4 is the gate here)"


# ---------------------------------------------------------------------------
# T-VF-K3-exec-* — --exec-drift-checks outcomes are CONDITIONAL, never FAIL (F-B-3)
# ---------------------------------------------------------------------------


def test_K3_exec_nonzero_conditional():
    """A non-zero drift_check exit is CONDITIONAL — K3 verifies executability, not
    the drift outcome; the exit code must never hard-FAIL the registry."""
    entry = {"id": "svc", "drift_check": "mycmd --check"}
    mock_result = MagicMock(returncode=2)
    with (
        patch.object(vf.shutil, "which", return_value="/usr/bin/mycmd"),
        patch.object(vf.subprocess, "run", return_value=mock_result),
    ):
        failures, warnings = vf._check_K3([entry], exec_drift_checks=True)
    assert not failures, "non-zero exit must be CONDITIONAL, never FAIL"
    assert any(w["check"] == "K3" and "exited 2" in w["detail"] for w in warnings)


def test_K3_exec_timeout_conditional():
    entry = {"id": "svc", "drift_check": "slowcmd"}
    with (
        patch.object(vf.shutil, "which", return_value="/usr/bin/slowcmd"),
        patch.object(
            vf.subprocess,
            "run",
            side_effect=vf.subprocess.TimeoutExpired(cmd="slowcmd", timeout=10),
        ),
    ):
        failures, warnings = vf._check_K3([entry], exec_drift_checks=True)
    assert not failures
    assert any(w["check"] == "K3" and "timed out" in w["detail"] for w in warnings)


def test_K3_exec_oserror_conditional():
    entry = {"id": "svc", "drift_check": "badcmd"}
    with (
        patch.object(vf.shutil, "which", return_value="/usr/bin/badcmd"),
        patch.object(vf.subprocess, "run", side_effect=OSError("exec failed")),
    ):
        failures, warnings = vf._check_K3([entry], exec_drift_checks=True)
    assert not failures
    assert any(
        w["check"] == "K3" and "execution error" in w["detail"] for w in warnings
    )


# ---------------------------------------------------------------------------
# test_K1_mixed_baseline_cond_takes_precedence — FV-1 regression guard
# ---------------------------------------------------------------------------


def test_K1_mixed_baseline_cond_takes_precedence(tmp_path):
    """FV-1: in a mixed-baseline registry (one entry has a real hash-drift K1,
    another has an unverified-baseline K1), K1 must land in cond — not skipped.

    The real drift warning (no kind) takes precedence over the skipped_no_baseline
    marker from the unverified entry. FAILs on old bucket logic where cond_checks
    was built as all-warnings minus skipped_checks (defeating DD-D).
    """
    # entry-drift: clean baseline, sha now changed → real hash-drift K1 (no kind)
    drift_file = tmp_path / "svc-drift.py"
    original_content = b"original content"
    drift_file.write_bytes(original_content)
    stale_sha = _sha256_short(original_content)
    drift_file.write_bytes(b"modified content -- now different")

    # entry-unverified: drift_status='unverified' → skipped_no_baseline K1
    unverified_file = tmp_path / "svc-unverified.py"
    unverified_file.write_bytes(b"stable content")

    cache = {
        "components": {
            "entry-drift": {
                "last_verified_sha": stale_sha,
                "drift_status": "clean",
            },
            "entry-unverified": {
                "last_verified_sha": _sha256_short(b"stable content"),
                "drift_status": "unverified",
            },
        }
    }
    entries = [
        {"id": "entry-drift", "sot_location": "svc-drift.py"},
        {"id": "entry-unverified", "sot_location": "svc-unverified.py"},
    ]

    _, warnings = vf._check_K1(entries, tmp_path, cache, project_id_resolved=True)
    verdict = vf._build_verdict([], warnings, ["K1"])

    # K1 must be in cond (real drift present), never in skipped — FV-1
    assert "K1" not in verdict["skipped"], (
        "K1 must not be in skipped when a real hash-drift warning exists "
        "(mixed-baseline registry — FV-1 precedence: cond > skipped)"
    )
    assert verdict["verdict"] == "CONDITIONAL"
    drift_warns = [
        w
        for w in warnings
        if w["check"] == "K1" and w.get("kind") != "skipped_no_baseline"
    ]
    assert drift_warns, "real hash-drift K1 warning (no kind) must be present"


# ---------------------------------------------------------------------------
# test_K1_cold_start_message_project_scoped — V-LOW-1 regression guard
# ---------------------------------------------------------------------------


def test_K1_cold_start_message_project_scoped(tmp_path):
    """V-LOW-1: cold-start vs baseline-loss label must use THIS project's cache,
    not the global dir-wide _drift_state_populated() glob.

    A new project with empty components but global cache_populated=True must be
    labeled 'cold-start' (correct), not 'baseline-loss' (mislabel). Fails on old
    code that checked cache_populated instead of bool(components).
    """
    sot_file = tmp_path / "svc.py"
    sot_file.write_bytes(b"some content")

    entry = {"id": "svc", "sot_location": "svc.py"}
    # This project's cache has no components (genuinely new project)
    cache: dict = {"components": {}}

    _, warnings = vf._check_K1(
        [entry],
        tmp_path,
        cache,
        project_id_resolved=True,
        cache_populated=True,  # global glob says some other project has a cache
    )
    k1 = [w for w in warnings if w["check"] == "K1"]
    assert k1
    assert "cold-start" in k1[0]["detail"], (
        "empty project-cache must yield 'cold-start', not 'baseline-loss', "
        "regardless of the global cache_populated flag (V-LOW-1)"
    )
    assert "baseline-loss" not in k1[0]["detail"]


# ---------------------------------------------------------------------------
# test_K1_unreadable_file_conditional — V-LOW-2 regression guard
# ---------------------------------------------------------------------------


def test_K1_unreadable_file_conditional(tmp_path):
    """V-LOW-2: _sha256_short returns None (file exists but unreadable mid-check)
    → K1 CONDITIONAL ('artifact unreadable'), not silent ran-pass.

    Fails on old code where `if current_sha and ...` silently skipped the None case.
    """
    sot_file = tmp_path / "svc.py"
    sot_file.write_bytes(b"some content")

    cache = {
        "components": {
            "svc": {"last_verified_sha": "aabbccdd", "drift_status": "clean"}
        }
    }
    entry = {"id": "svc", "sot_location": "svc.py"}

    with patch.object(vf, "_sha256_short", return_value=None):
        _, warnings = vf._check_K1([entry], tmp_path, cache, project_id_resolved=True)

    k1 = [w for w in warnings if w["check"] == "K1"]
    assert k1, "unreadable file must emit a K1 CONDITIONAL warning (V-LOW-2)"
    assert "unreadable" in k1[0]["detail"]
    # Must be a plain CONDITIONAL (in cond bucket), not skipped_no_baseline
    assert k1[0].get("kind") != "skipped_no_baseline"


# ---------------------------------------------------------------------------
# test_K1_empty_sha_conditional — FV-2 (companion test for existing behavior)
# ---------------------------------------------------------------------------


def test_K1_empty_sha_conditional(tmp_path):
    """FV-2: comp present, drift_status='clean', last_verified_sha='' →
    K1 CONDITIONAL with 'no recorded content hash' detail.

    A component record exists but the hash was never captured; the entry cannot
    be declared clean without a recorded hash to compare against.
    """
    sot_file = tmp_path / "svc.py"
    sot_file.write_bytes(b"some content")

    cache = {
        "components": {
            "svc": {
                "last_verified_sha": "",  # no hash recorded
                "drift_status": "clean",
            }
        }
    }
    entry = {"id": "svc", "sot_location": "svc.py"}

    _, warnings = vf._check_K1([entry], tmp_path, cache, project_id_resolved=True)
    k1 = [w for w in warnings if w["check"] == "K1"]
    assert k1, "empty last_verified_sha must emit a K1 CONDITIONAL warning (FV-2)"
    assert "no recorded content hash" in k1[0]["detail"]
    assert k1[0].get("kind") == "skipped_no_baseline"


# ---------------------------------------------------------------------------
# test_flat_registry_override_emits_verdict — DEFECT-3
# ---------------------------------------------------------------------------


def test_flat_registry_override_emits_verdict(tmp_path):
    """DEFECT-3: a non-conforming --registry path must emit a verdict, not crash.

    A flat --registry override (not under <root>/.sot/) makes
    _project_root_from_registry return None. Pre-fix that None reached the path
    checks (R1/R4/C3/discovery/K1) unguarded and raised TypeError; a validation
    gate must never traceback. cmd_run now resolves declared locations relative
    to the registry's own directory and emits a structured FAIL.
    """
    # Flat registry: parent dir is not '.sot' → project root resolves to None.
    reg = tmp_path / "registry.yaml"
    entry = _good_entry(tmp_path, create_file=False)  # file absent → R1 FAIL
    reg.write_text(
        yaml.dump({"schema_version": "1.0", "entries": [entry]}), encoding="utf-8"
    )
    assert vf._project_root_from_registry(reg) is None

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)  # must not raise TypeError

    assert verdict["verdict"] in {"PASS", "CONDITIONAL", "FAIL"}
    r1 = [f for f in verdict["failures"] if f["check"] == "R1"]
    assert r1, "R1 must resolve against the registry dir and FAIL on the absent file"


# ---------------------------------------------------------------------------
# test_flat_registry_override_skips_discovery — DEFECT-3 MINOR-1
# test_conforming_registry_still_discovers_C1 — DEFECT-3 MINOR-1 no-regression
# ---------------------------------------------------------------------------


def _run_cmd_with_discovery(args, candidates):
    """Run cmd_run with _discover_candidates returning the given candidates.

    Unlike _run_cmd (which mocks discovery → []), this lets discovery surface a
    candidate so C1 can be exercised end-to-end. Returns the verdict dict.
    """
    import io
    from contextlib import redirect_stderr, redirect_stdout

    buf = io.StringIO()
    err = io.StringIO()
    with (
        patch.object(vf, "_resolve_project_id", return_value=None),
        patch.object(vf, "_read_drift_cache", return_value={"components": {}}),
        patch.object(vf, "_discover_candidates", return_value=candidates),
        patch.object(vf, "_drift_state_populated", return_value=False),
        redirect_stdout(buf),
        redirect_stderr(err),
    ):
        vf.cmd_run(args)
    return json.loads(buf.getvalue())


def test_flat_registry_override_skips_discovery(tmp_path):
    """DEFECT-3 MINOR-1: a flat --registry override must NOT emit spurious C1.

    For a non-conforming --registry path _project_root_from_registry returns
    None, so verify must skip auto-discovery (matching detect-propose's M5
    skip-discovery contract) — otherwise it would scan registry.parent and fire
    spurious "discovered component(s) not registered" C1 warnings.

    Pre-fix: discovery ran unconditionally against resolve_root (= registry.parent,
    non-None), so the surfaced candidate produced a C1 warning and this assertion
    FAILED. Post-fix: discovery is gated off (discover=False) → no C1.
    """
    reg = tmp_path / "registry.yaml"
    entry = _good_entry(tmp_path)  # file present → no R1/C3 failure
    reg.write_text(
        yaml.dump({"schema_version": "1.0", "entries": [entry]}), encoding="utf-8"
    )
    assert vf._project_root_from_registry(reg) is None

    candidate = {
        "id": "discovered-comp",
        "boundary_type": "component",
        "sot_location": "discovered-comp/",
        "confidence": "high",
        "inferred_from": "package.json",
    }
    args = _make_args(registry=str(reg))
    verdict = _run_cmd_with_discovery(args, [candidate])

    c1 = [w for w in verdict["warnings"] if w["check"] == "C1"]
    assert not c1, (
        "flat --registry must skip discovery; no spurious C1 warning expected "
        f"(got: {c1})"
    )


def test_conforming_registry_still_discovers_C1(tmp_path):
    """DEFECT-3 MINOR-1 no-regression: a conforming .sot/ registry STILL runs C1.

    project_root is non-None for <root>/.sot/registry.yaml, so discovery runs and
    an unregistered candidate produces a C1 warning. Passes pre- AND post-fix.
    """
    reg = _write_registry(tmp_path, [_good_entry(tmp_path)])
    assert vf._project_root_from_registry(reg) == tmp_path

    candidate = {
        "id": "discovered-comp",
        "boundary_type": "component",
        "sot_location": "discovered-comp/",
        "confidence": "high",
        "inferred_from": "package.json",
    }
    args = _make_args(registry=str(reg))
    verdict = _run_cmd_with_discovery(args, [candidate])

    c1 = [w for w in verdict["warnings"] if w["check"] == "C1"]
    assert c1, "conforming registry must still run discovery and surface C1"


# ---------------------------------------------------------------------------
# CI guards for TASK-096 Lane D fixes (RISK-023): the field-level tests live in
# the skill-local suite (correct home) which CI `pytest tests/` never collects,
# so these mirror the load-bearing behaviors into the CI-covered top-level suite.
# One focused guard per fix; each fails if the fix is reverted.
# ---------------------------------------------------------------------------


# T-VF-TD749 — verify FAILs an entry with an unfilled TODO(human): sentinel,
# including the OPTIONAL provenance_note (not in the required set).
def test_TD749_sentinel_free_text_fails_S1(sc):
    marker = vf._SENTINEL_MARKER
    entry = {
        "id": "svc",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "src/",
        "owner": f"{marker} <owning team or person>",
        "description": "A real description.",
        "provenance_note": f"{marker} <how/why this entry was added>",
    }
    failures, _ = vf._check_S1([entry], sc)
    failed_fields = {f["detail"].split("'")[1] for f in failures}
    assert "owner" in failed_fields
    assert "provenance_note" in failed_fields  # optional field caught too
    assert all(f["check"] == "S1" for f in failures)


def test_TD749_filled_entry_passes_S1(sc):
    entry = {
        "id": "svc",
        "kind": "service",
        "boundary_type": "path",
        "sot_location": "src/",
        "owner": "@team",
        "description": "A real description.",
        "provenance_note": "Added during bootstrap.",
    }
    failures, _ = vf._check_S1([entry], sc)
    assert not failures


# T-VF-TD754 — verify --proposal returns a real verdict at cold-start (no
# committed registry) and still FAILs a leftover sentinel (TD-749 coupling).
def test_TD754_coldstart_proposal_returns_real_verdict(tmp_path):
    sot = tmp_path / ".sot"
    sot.mkdir()
    proposal = sot / "registry.proposed.yaml"
    proposal.write_text(
        yaml.dump(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "id": "svc",
                        "kind": "service",
                        "boundary_type": "path",
                        "sot_location": "svc.md",
                        "owner": f"{vf._SENTINEL_MARKER} <owning team>",
                        "description": "desc",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # No committed registry.yaml exists under tmp_path/.sot.
    args = _make_args(registry=str(sot / "registry.yaml"), proposal=str(proposal))
    verdict = _run_cmd(args, tmp_path)
    assert verdict["verdict"] == "FAIL"  # a real verdict, not the no-registry bail
    s1_fields = {
        f["detail"].split("'")[1] for f in verdict["failures"] if f["check"] == "S1"
    }
    assert "owner" in s1_fields  # leftover sentinel FAILed at cold-start


# T-VF-TD756 — K3 no longer false-flags a valid compound drift_check, but a
# genuinely-missing binary in a compound command still WARNs.
def test_TD756_compound_drift_check_not_false_flagged():
    import shutil

    real = "sh" if shutil.which("sh") else "python3"
    _, warnings = vf._check_K3(
        [{"id": "e", "drift_check": f"cd website && {real} -c 'true'"}],
        exec_drift_checks=False,
    )
    assert warnings == []


def test_TD756_missing_binary_in_compound_still_warns():
    _, warnings = vf._check_K3(
        [{"id": "e", "drift_check": "cd website && definitely-not-real-xyz build"}],
        exec_drift_checks=False,
    )
    assert len(warnings) == 1
    assert "definitely-not-real-xyz" in warnings[0]["detail"]
