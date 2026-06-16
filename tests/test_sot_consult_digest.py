"""
Tests for aim_sot_consult digest subcommand (BP-035 Part-1).

Covers:
  D1  — text mode: per-entry lines rendered in correct format
  D2  — text mode: drift rollup "drift: unverified" — no drift_status in entries
        (file-fallback registry; detect-propose never ran)
  D3  — text mode: drift rollup "drift: N stale" when stale entries present
  D4  — text mode: empty registry → no output, exit 0
  D5  — --json: response has "digest", "count", "drift" (3 keys), "truncated"
  D6  — --json: count matches, truncated=False; drift.unverified correct
  D7  — --json: DIGEST_MAX_LINES+1 entries → truncated=True, digest capped, count=full
  D8  — text mode: DIGEST_MAX_LINES+1 entries → count+pointer emitted, no per-entry lines
  D9  — absent registry, text mode → no-registry message, exit 0
  D10 — absent registry, --json → {"error": "no_registry", ...}, exit 0
  D11 — never-writes static scan on aim_sot_consult module source
  D12 — --registry override resolves to fixture path for digest
  D13 — text mode: explicit drift_status="unverified" entry → "drift: unverified"
  D14 — text mode: drift_status="clean" entries → "drift: clean"
  D15 — text mode: clean+stale → stale wins, "drift: clean" suppressed
  D16 — --json: clean+unverified → correct per-bucket counts
  D17 — text mode: truncated output still emits "drift:" line
  D18 — text mode: drift_status="missing" counts as stale
  D19 — --json: empty registry → count=0, all-zero drift, truncated=False

All tests are hermetic (no network, no filesystem side-effects beyond reads;
all writes are to pytest tmp_path fixtures only).
"""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

_CONSULT_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "_ai-memory"
    / "skills"
    / "aim-sot"
    / "scripts"
    / "aim_sot_consult.py"
)
_spec = importlib.util.spec_from_file_location("aim_sot_consult", _CONSULT_SCRIPT)
consult = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(consult)

# ---------------------------------------------------------------------------
# Helpers + fixtures
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: Path, entries: list[dict]) -> Path:
    """Write a .sot/registry.yaml to tmp_path and return its path."""
    reg_dir = tmp_path / ".sot"
    reg_dir.mkdir(exist_ok=True)
    reg_file = reg_dir / "registry.yaml"
    reg_file.write_text(
        yaml.dump({"schema_version": "1.0", "entries": entries}),
        encoding="utf-8",
    )
    return reg_file


ENTRY_AUTH = {
    "id": "auth-service",
    "kind": "service",
    "boundary_type": "path",
    "sot_location": "src/auth/",
    "owner": "@platform-team",
    "description": "Authentication service",
    "status": "active",
    "drift_check": "test -d src/auth",
}

ENTRY_PAYMENTS = {
    "id": "payments-api",
    "kind": "api",
    "boundary_type": "concern",
    "sot_location": "contracts/payments.openapi.yaml",
    "owner": "@payments-team",
    "description": "Payments API contract",
    "status": "active",
}

ENTRY_STALE = {
    "id": "legacy-svc",
    "kind": "service",
    "boundary_type": "path",
    "sot_location": "src/legacy/",
    "owner": "@core-team",
    "description": "Legacy service",
    "status": "active",
    "drift_status": "drifted",
}

ENTRY_CLEAN = {
    "id": "payments-api",
    "kind": "api",
    "boundary_type": "concern",
    "sot_location": "contracts/payments.openapi.yaml",
    "owner": "@payments-team",
    "description": "Payments API contract",
    "status": "active",
    "drift_status": "clean",
}

ENTRY_UNVERIFIED = {
    "id": "core-lib",
    "kind": "library",
    "boundary_type": "path",
    "sot_location": "src/core/",
    "owner": "@core-team",
    "description": "Core library",
    "status": "active",
    "drift_status": "unverified",
}

ENTRY_MISSING = {
    "id": "missing-svc",
    "kind": "service",
    "boundary_type": "path",
    "sot_location": "src/missing/",
    "owner": "@core-team",
    "description": "Missing service",
    "status": "active",
    "drift_status": "missing",
}

TWO_ENTRIES = [ENTRY_AUTH, ENTRY_PAYMENTS]


@pytest.fixture()
def registry(tmp_path: Path) -> Path:
    """Two-entry registry (no explicit drift_status on either entry)."""
    return _make_registry(tmp_path, TWO_ENTRIES)


@pytest.fixture()
def registry_with_stale(tmp_path: Path) -> Path:
    """Three-entry registry: two without drift_status, one with drift_status=drifted."""
    return _make_registry(tmp_path, [ENTRY_AUTH, ENTRY_PAYMENTS, ENTRY_STALE])


# ---------------------------------------------------------------------------
# D1 — text mode: per-entry line format
# ---------------------------------------------------------------------------


def test_d1_digest_text_line_format(registry: Path, capsys):
    rc = consult.main(["digest", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[auth-service]  service · @platform-team  →  src/auth/" in out
    assert (
        "[payments-api]  api · @payments-team  →  contracts/payments.openapi.yaml"
        in out
    )


# ---------------------------------------------------------------------------
# D2 — text mode: "drift: unverified" — no drift_status in entries (file-fallback)
# ---------------------------------------------------------------------------


def test_d2_digest_text_rollup_unverified_absent(registry: Path, capsys):
    """Entries with no drift_status (detect-propose never ran) → 'drift: unverified'."""
    rc = consult.main(["digest", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "drift: unverified" in out
    assert "drift: clean" not in out


# ---------------------------------------------------------------------------
# D3 — text mode: drift rollup "drift: N stale" when stale entry present
# ---------------------------------------------------------------------------


def test_d3_digest_text_rollup_stale(registry_with_stale: Path, capsys):
    rc = consult.main(["digest", "--registry", str(registry_with_stale)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "drift: 1 stale" in out


# ---------------------------------------------------------------------------
# D4 — text mode: empty registry → no output, exit 0
# ---------------------------------------------------------------------------


def test_d4_digest_text_empty_registry(tmp_path: Path, capsys):
    reg = _make_registry(tmp_path, [])
    rc = consult.main(["digest", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == ""


# ---------------------------------------------------------------------------
# D5 — --json: response shape has all three drift buckets
# ---------------------------------------------------------------------------


def test_d5_digest_json_keys_present(registry: Path, capsys):
    rc = consult.main(["digest", "--json", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "digest" in data
    assert "count" in data
    assert "drift" in data
    assert "truncated" in data
    # Three-bucket drift object (C1 ruling)
    assert "clean" in data["drift"]
    assert "stale" in data["drift"]
    assert "unverified" in data["drift"]


# ---------------------------------------------------------------------------
# D6 — --json: count correct, truncated=False, drift buckets accurate
# ---------------------------------------------------------------------------


def test_d6_digest_json_count_and_truncated(registry: Path, capsys):
    """TWO_ENTRIES: no drift_status → both land in unverified bucket."""
    rc = consult.main(["digest", "--json", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["count"] == 2
    assert data["truncated"] is False
    assert len(data["digest"]) == 2
    assert data["drift"]["clean"] == 0
    assert data["drift"]["stale"] == 0
    assert data["drift"]["unverified"] == 2


# ---------------------------------------------------------------------------
# D7 — --json: DIGEST_MAX_LINES+1 entries → truncated=True, digest capped
# ---------------------------------------------------------------------------


def test_d7_digest_json_truncation(tmp_path: Path, capsys):
    over = consult.DIGEST_MAX_LINES + 1
    entries = [
        {
            "id": f"svc-{i}",
            "kind": "service",
            "sot_location": f"src/svc{i}/",
            "owner": f"@team-{i}",
        }
        for i in range(over)
    ]
    reg = _make_registry(tmp_path, entries)
    rc = consult.main(["digest", "--json", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["truncated"] is True
    assert data["count"] == over
    assert len(data["digest"]) == consult.DIGEST_MAX_LINES


# ---------------------------------------------------------------------------
# D8 — text mode: truncation → count+pointer, no per-entry lines
# ---------------------------------------------------------------------------


def test_d8_digest_text_truncation_pointer(tmp_path: Path, capsys):
    over = consult.DIGEST_MAX_LINES + 1
    entries = [
        {
            "id": f"svc-{i}",
            "kind": "service",
            "sot_location": f"src/svc{i}/",
            "owner": f"@team-{i}",
        }
        for i in range(over)
    ]
    reg = _make_registry(tmp_path, entries)
    rc = consult.main(["digest", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Run 'aim-sot consult list' for the full set." in out
    # No individual per-entry lines in truncated text output.
    assert "[svc-0]" not in out


# ---------------------------------------------------------------------------
# D9 — absent registry, text mode → no-registry message, exit 0
# ---------------------------------------------------------------------------


def test_d9_digest_absent_registry_text(tmp_path: Path, capsys):
    absent = tmp_path / "no" / "registry.yaml"
    rc = consult.main(["digest", "--registry", str(absent)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no registry found" in out.lower()


# ---------------------------------------------------------------------------
# D10 — absent registry, --json → {"error": "no_registry", ...}, exit 0
# ---------------------------------------------------------------------------


def test_d10_digest_absent_registry_json(tmp_path: Path, capsys):
    absent = tmp_path / "no" / "registry.yaml"
    rc = consult.main(["digest", "--json", "--registry", str(absent)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["error"] == "no_registry"
    assert "message" in data


# ---------------------------------------------------------------------------
# D11 — never-writes static scan (mirrors T-DP12 from test_sot_detect_propose.py)
# ---------------------------------------------------------------------------


def test_d11_consult_never_writes_registry_static():
    """Static source scan: no write-mode file open or write method touches registry."""
    import inspect

    src = inspect.getsource(consult)
    violations = []
    for i, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        has_registry = "registry" in line.lower()
        write_modes = ('"w"', "'w'", '"wb"', "'wb'", '"a"', "'a'", '"x"', "'x'")
        has_write_open = any(m in line for m in write_modes)
        has_write_method = ".write_text(" in line or ".write_bytes(" in line
        if has_registry and (has_write_open or has_write_method):
            violations.append((i, line.rstrip()))
    assert violations == [], "consult opens registry in write mode:\n" + "\n".join(
        f"  line {lineno}: {code}" for lineno, code in violations
    )


# ---------------------------------------------------------------------------
# D12 — --registry override resolves to fixture path for digest
# ---------------------------------------------------------------------------


def test_d12_digest_registry_override(tmp_path: Path, capsys):
    """--registry PATH override directs digest to the specified fixture."""
    reg = _make_registry(tmp_path, [ENTRY_AUTH])
    rc = consult.main(["digest", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "auth-service" in out
    assert "src/auth/" in out


# ---------------------------------------------------------------------------
# D13 — text mode: explicit drift_status="unverified" → "drift: unverified"
# ---------------------------------------------------------------------------


def test_d13_digest_text_rollup_explicit_unverified(tmp_path: Path, capsys):
    """Explicit drift_status='unverified' (engine ran, not yet confirmed clean)
    lands in the unverified bucket — same rollup as absent drift_status."""
    reg = _make_registry(tmp_path, [ENTRY_UNVERIFIED])
    rc = consult.main(["digest", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "drift: unverified" in out
    assert "drift: clean" not in out


# ---------------------------------------------------------------------------
# D14 — text mode: drift_status="clean" entries → "drift: clean"
# ---------------------------------------------------------------------------


def test_d14_digest_text_rollup_clean(tmp_path: Path, capsys):
    """Entries with drift_status='clean' (engine confirmed, zero stale) →
    'drift: clean'. Must NOT print 'drift: clean' when nothing is actually clean."""
    reg = _make_registry(tmp_path, [ENTRY_CLEAN])
    rc = consult.main(["digest", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "drift: clean" in out
    assert "drift: unverified" not in out


# ---------------------------------------------------------------------------
# D15 — text mode: clean+stale → stale wins, "drift: clean" suppressed
# ---------------------------------------------------------------------------


def test_d15_digest_text_clean_and_stale_stale_wins(tmp_path: Path, capsys):
    """One clean + one drifted → stale takes priority; 'drift: clean' must not appear."""
    reg = _make_registry(tmp_path, [ENTRY_CLEAN, ENTRY_STALE])
    rc = consult.main(["digest", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "drift: 1 stale" in out
    assert "drift: clean" not in out


# ---------------------------------------------------------------------------
# D16 — --json: clean+unverified → correct per-bucket counts
# ---------------------------------------------------------------------------


def test_d16_digest_json_clean_and_unverified(tmp_path: Path, capsys):
    """One clean + one no-drift_status → unverified=1, clean=1, stale=0."""
    reg = _make_registry(tmp_path, [ENTRY_CLEAN, ENTRY_AUTH])
    rc = consult.main(["digest", "--json", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["drift"] == {"clean": 1, "stale": 0, "unverified": 1}


# ---------------------------------------------------------------------------
# D17 — text mode: truncated output still emits "drift:" line
# ---------------------------------------------------------------------------


def test_d17_digest_text_truncated_drift_line_present(tmp_path: Path, capsys):
    """Truncated text output must still include the 'drift:' line."""
    over = consult.DIGEST_MAX_LINES + 1
    entries = [
        {
            "id": f"svc-{i}",
            "kind": "service",
            "sot_location": f"src/svc{i}/",
            "owner": f"@team-{i}",
        }
        for i in range(over)
    ]
    reg = _make_registry(tmp_path, entries)
    rc = consult.main(["digest", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "drift:" in out


# ---------------------------------------------------------------------------
# D18 — text mode: drift_status="missing" counts as stale
# ---------------------------------------------------------------------------


def test_d18_digest_text_rollup_missing_counts_as_stale(tmp_path: Path, capsys):
    """drift_status='missing' must land in the stale bucket → 'drift: 1 stale'."""
    reg = _make_registry(tmp_path, [ENTRY_MISSING])
    rc = consult.main(["digest", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "drift: 1 stale" in out


# ---------------------------------------------------------------------------
# D19 — --json: empty registry → count=0, all-zero drift, truncated=False
# ---------------------------------------------------------------------------


def test_d19_digest_json_empty_registry(tmp_path: Path, capsys):
    """Empty registry with --json → parseable output, zero counts, not truncated."""
    reg = _make_registry(tmp_path, [])
    rc = consult.main(["digest", "--json", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["count"] == 0
    assert data["drift"] == {"clean": 0, "stale": 0, "unverified": 0}
    assert data["truncated"] is False
