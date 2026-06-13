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
  T-VF-K1-no-cache                              — no cache baseline → K1 PASS
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


def _run_cmd(args: argparse.Namespace, tmp_path: Path, *, cache: dict | None = None):
    """Run cmd_run with project_id + discover_candidates mocked. Returns verdict dict.

    When cache is not None, _resolve_project_id returns a dummy project id so
    _read_drift_cache is actually reached and returns the supplied cache dict.
    When cache is None, project_id stays None and K1 uses an empty cache (cold-start).
    """
    import io
    from contextlib import redirect_stdout

    _cache = cache if cache is not None else {"components": {}}
    # Only activate the _read_drift_cache path when a cache dict is explicitly supplied.
    _project_id = "test-proj" if cache is not None else None

    buf = io.StringIO()
    with (
        patch.object(vf, "_resolve_project_id", return_value=_project_id),
        patch.object(vf, "_read_drift_cache", return_value=_cache),
        patch.object(vf, "_discover_candidates", return_value=[]),
        redirect_stdout(buf),
    ):
        vf.cmd_run(args)

    return json.loads(buf.getvalue())


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
# T-VF-K1-no-cache — no cache baseline → K1 PASS (cold-start)
# ---------------------------------------------------------------------------


def test_K1_no_cache(tmp_path):
    sot_file = tmp_path / "svc.py"
    sot_file.write_bytes(b"some content")

    empty_cache: dict = {"components": {}}
    entry = {"id": "svc", "sot_location": "svc.py", "status": "active"}

    _, warnings = vf._check_K1([entry], tmp_path, empty_cache)
    assert not [
        w for w in warnings if w["check"] == "K1"
    ], "K1 must not fire when there is no cache baseline"


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


def test_verdict_pass(tmp_path):
    """Registry with one clean entry, CODEOWNERS with owner → PASS."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)
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
    verdict = _run_cmd(args, tmp_path)
    assert (
        verdict["verdict"] == "PASS"
    ), "No CODEOWNERS must not prevent PASS — R4 absent-roster is a silent no-op"
    assert not verdict["warnings"]


# ---------------------------------------------------------------------------
# T-VF-verdict-conditional — 0 failures, ≥1 warning → CONDITIONAL
# ---------------------------------------------------------------------------


def test_verdict_conditional(tmp_path):
    """Roster-present mismatch → R4 warning → CONDITIONAL."""
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
    """Verify pass_count counts distinct check IDs with zero findings, not a subtraction."""
    entry = _good_entry(tmp_path)
    reg = _write_registry(tmp_path, [entry])
    (tmp_path / "CODEOWNERS").write_text("* @team-auth\n", encoding="utf-8")

    args = _make_args(registry=str(reg))
    verdict = _run_cmd(args, tmp_path)
    expected_pass_count = len(
        [
            c
            for c in verdict["checks_run"]
            if not any(
                x["check"] == c for x in verdict["failures"] + verdict["warnings"]
            )
        ]
    )
    assert verdict["pass_count"] == expected_pass_count


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
