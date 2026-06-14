"""Tests for aim_sot_consult.py (SOT Wave-1 Item 2).

Covers:
  C1  — get by known id returns full entry dict
  C2  — get unknown id → not-found (human + json)
  C3  — where known id → correct sot_location
  C4  — who known id → correct owner
  C5  — drift known id with drift_check → value returned
  C6  — drift known id without drift_check → "(none configured)"
  C7  — list returns all entries, count matches
  C8  — --json on list → valid JSON, correct shape
  C9  — --json on get → {"found": true, "entry": {...}}
  C10 — --json on not-found → {"found": false, "id": "..."}
  C11 — registry file absent → exit 0, no-registry human message
  C12 — --json + absent → {"error": "no_registry", ...}, exit 0
  C13 — malformed YAML → exit 1, error message
  C14 — consult answers valid query against registry with malformed sibling entry
  C15 — --registry PATH override beats git-root discovery (decoy test)
  C16 — _load_entries never creates or modifies any file (read-only guarantee)
  C17 — where on unknown id → not-found shape (same as get)
  C18 — who on unknown id → not-found shape
  C19 — drift on unknown id → not-found shape
  C20 — --json + where/who/drift not-found → {"found": false, "id": "..."}
  C21 — registry found via git-root resolution from a subdirectory
  C22 — registry found by parent-dir walk when git is unavailable
  C23 — full main() call never writes any file (read-only at full call-path)

All tests are hermetic (no network, no filesystem side-effects beyond reads;
all writes are to pytest tmp_path fixtures only).
"""

import importlib.util
import json
import subprocess
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
# Fixtures
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: Path, entries: list[dict]) -> Path:
    """Write a .sot/registry.yaml to tmp_path and return its path."""
    reg_dir = tmp_path / ".sot"
    reg_dir.mkdir()
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
    # no drift_check
}

TWO_ENTRIES = [ENTRY_AUTH, ENTRY_PAYMENTS]


@pytest.fixture()
def registry(tmp_path: Path) -> Path:
    """Two-entry registry at tmp_path/.sot/registry.yaml."""
    return _make_registry(tmp_path, TWO_ENTRIES)


# ---------------------------------------------------------------------------
# C1 — get found
# ---------------------------------------------------------------------------


def test_c1_get_known_id(registry: Path, capsys):
    rc = consult.main(["get", "auth-service", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "auth-service" in out
    assert "src/auth/" in out
    assert "@platform-team" in out


# ---------------------------------------------------------------------------
# C2 — get not-found (human)
# ---------------------------------------------------------------------------


def test_c2_get_unknown_id_human(registry: Path, capsys):
    rc = consult.main(["get", "nonexistent", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "not found" in out.lower()
    assert "nonexistent" in out


# ---------------------------------------------------------------------------
# C3 — where
# ---------------------------------------------------------------------------


def test_c3_where_known_id(registry: Path, capsys):
    rc = consult.main(["where", "auth-service", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "src/auth/" in out


# ---------------------------------------------------------------------------
# C4 — who
# ---------------------------------------------------------------------------


def test_c4_who_known_id(registry: Path, capsys):
    rc = consult.main(["who", "auth-service", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "@platform-team" in out


# ---------------------------------------------------------------------------
# C5 — drift with drift_check present
# ---------------------------------------------------------------------------


def test_c5_drift_with_check(registry: Path, capsys):
    rc = consult.main(["drift", "auth-service", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "test -d src/auth" in out


# ---------------------------------------------------------------------------
# C6 — drift with no drift_check
# ---------------------------------------------------------------------------


def test_c6_drift_absent_check(registry: Path, capsys):
    rc = consult.main(["drift", "payments-api", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "(none configured)" in out


# ---------------------------------------------------------------------------
# C7 — list (human)
# ---------------------------------------------------------------------------


def test_c7_list_human(registry: Path, capsys):
    rc = consult.main(["list", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "auth-service" in out
    assert "payments-api" in out


# ---------------------------------------------------------------------------
# C8 — --json list
# ---------------------------------------------------------------------------


def test_c8_list_json(registry: Path, capsys):
    rc = consult.main(["list", "--json", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "entries" in data
    assert "count" in data
    assert data["count"] == 2
    ids = [e["id"] for e in data["entries"]]
    assert "auth-service" in ids
    assert "payments-api" in ids


# ---------------------------------------------------------------------------
# C9 — --json get found
# ---------------------------------------------------------------------------


def test_c9_get_json_found(registry: Path, capsys):
    rc = consult.main(["get", "auth-service", "--json", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["found"] is True
    assert data["entry"]["id"] == "auth-service"
    assert data["entry"]["sot_location"] == "src/auth/"


# ---------------------------------------------------------------------------
# C10 — --json get not-found
# ---------------------------------------------------------------------------


def test_c10_get_json_not_found(registry: Path, capsys):
    rc = consult.main(["get", "nonexistent", "--json", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["found"] is False
    assert data["id"] == "nonexistent"


# ---------------------------------------------------------------------------
# C11 — absent registry, human
# ---------------------------------------------------------------------------


def test_c11_absent_registry_human(tmp_path: Path, capsys):
    absent = tmp_path / "no" / "registry.yaml"
    rc = consult.main(["list", "--registry", str(absent)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no registry found" in out.lower()


# ---------------------------------------------------------------------------
# C12 — absent registry, --json
# ---------------------------------------------------------------------------


def test_c12_absent_registry_json(tmp_path: Path, capsys):
    absent = tmp_path / "no" / "registry.yaml"
    rc = consult.main(["list", "--json", "--registry", str(absent)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["error"] == "no_registry"
    assert "message" in data


# ---------------------------------------------------------------------------
# C13 — malformed YAML
# ---------------------------------------------------------------------------


def test_c13_malformed_yaml(tmp_path: Path, capsys):
    bad = tmp_path / "registry.yaml"
    bad.write_text(": invalid: yaml: {{{", encoding="utf-8")
    rc = consult.main(["list", "--registry", str(bad)])
    assert rc == 1
    # Error goes to stderr for human mode
    captured = capsys.readouterr()
    assert "yaml" in (captured.err + captured.out).lower()


# ---------------------------------------------------------------------------
# C14 — malformed sibling does not break valid query (resilience)
# ---------------------------------------------------------------------------


def test_c14_malformed_sibling_resilience(tmp_path: Path, capsys):
    """A malformed entry in the registry must not block queries on valid entries."""
    malformed_entry = {
        "id": "broken",
        # missing kind, boundary_type, sot_location, owner, description
        "status": "proposed",
    }
    reg = _make_registry(tmp_path, [ENTRY_AUTH, malformed_entry])
    # Query the valid entry — must succeed despite malformed sibling.
    rc = consult.main(["get", "auth-service", "--registry", str(reg)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "auth-service" in out
    assert "src/auth/" in out


# ---------------------------------------------------------------------------
# C15 — --registry override beats git-root discovery (decoy test)
# ---------------------------------------------------------------------------


def test_c15_registry_override_decoy(tmp_path: Path, capsys, monkeypatch):
    """--registry PATH wins over git-root resolution (decoy proves precedence)."""
    # Decoy: what git-root discovery would return
    decoy_sot = tmp_path / ".sot"
    decoy_sot.mkdir()
    decoy_reg = decoy_sot / "registry.yaml"
    decoy_reg.write_text(
        yaml.dump(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "id": "decoy-entry",
                        "kind": "service",
                        "boundary_type": "path",
                        "sot_location": "src/decoy/",
                        "owner": "@decoy-team",
                        "description": "Decoy",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # Override: different file, different content
    alt_reg = tmp_path / "override" / "registry.yaml"
    alt_reg.parent.mkdir()
    alt_reg.write_text(
        yaml.dump(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "id": "alt-entry",
                        "kind": "library",
                        "boundary_type": "path",
                        "sot_location": "src/alt/",
                        "owner": "@alt-team",
                        "description": "Alt entry",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # Mock git to return tmp_path as root so the decoy is discoverable.
    def fake_git(cmd, **kwargs):
        if isinstance(cmd, list) and len(cmd) >= 2 and cmd[1] == "rev-parse":
            return subprocess.CompletedProcess(cmd, 0, str(tmp_path) + "\n", "")
        return subprocess.run(cmd, **kwargs)

    monkeypatch.setattr(consult.subprocess, "run", fake_git)

    # Without --registry: git-root resolution finds the decoy.
    rc1 = consult.main(["get", "decoy-entry"])
    out1 = capsys.readouterr().out
    assert rc1 == 0
    assert "decoy-entry" in out1

    # With --registry: override wins — alt-entry returned, decoy-entry absent.
    rc2 = consult.main(["get", "alt-entry", "--registry", str(alt_reg)])
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert "alt-entry" in out2
    assert "src/alt/" in out2

    rc3 = consult.main(["get", "decoy-entry", "--registry", str(alt_reg)])
    out3 = capsys.readouterr().out
    assert rc3 == 0
    assert "not found" in out3.lower()


# ---------------------------------------------------------------------------
# C16 — read-only guarantee
# ---------------------------------------------------------------------------


def test_c16_read_only_guarantee(tmp_path: Path):
    """_load_entries must not create or modify any file."""
    reg = _make_registry(tmp_path, TWO_ENTRIES)
    files_before = {p: p.stat().st_mtime for p in tmp_path.rglob("*") if p.is_file()}
    consult._load_entries(reg)
    files_after = {p: p.stat().st_mtime for p in tmp_path.rglob("*") if p.is_file()}
    assert files_before == files_after, "consult wrote or modified a file"
    # No new files created.
    assert set(files_before) == set(files_after)


# ---------------------------------------------------------------------------
# C17-C19 -- where/who/drift not-found (human) -- refinement #2
# ---------------------------------------------------------------------------


def test_c17_where_not_found_human(registry: Path, capsys):
    rc = consult.main(["where", "ghost", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "not found" in out.lower()
    assert "ghost" in out


def test_c18_who_not_found_human(registry: Path, capsys):
    rc = consult.main(["who", "ghost", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "not found" in out.lower()
    assert "ghost" in out


def test_c19_drift_not_found_human(registry: Path, capsys):
    rc = consult.main(["drift", "ghost", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "not found" in out.lower()
    assert "ghost" in out


# ---------------------------------------------------------------------------
# C20 — where/who/drift not-found JSON shape (refinement #2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subcmd", ["where", "who", "drift"])
def test_c20_field_not_found_json(registry: Path, capsys, subcmd: str):
    rc = consult.main([subcmd, "ghost", "--json", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["found"] is False
    assert data["id"] == "ghost"


# ---------------------------------------------------------------------------
# C21 — registry found via git-root resolution
# ---------------------------------------------------------------------------


def test_c21_registry_resolution_git_root(tmp_path: Path, capsys, monkeypatch):
    """Registry at git-root/.sot/registry.yaml is found from a subdirectory."""
    # Init a real git repo so git rev-parse --show-toplevel returns tmp_path.
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)

    # Place the registry at the git root.
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text(
        yaml.dump({"schema_version": "1.0", "entries": [ENTRY_AUTH]}),
        encoding="utf-8",
    )

    # Query from a subdirectory inside the repo.
    subdir = tmp_path / "src" / "auth"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)

    rc = consult.main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "auth-service" in out


# ---------------------------------------------------------------------------
# C22 — registry found by parent-dir walk (no git)
# ---------------------------------------------------------------------------


def test_c22_registry_resolution_parent_walk(tmp_path: Path, capsys, monkeypatch):
    """Registry found by walking parent dirs when git is unavailable."""
    # Place the registry at tmp_path (no git init).
    (tmp_path / ".sot").mkdir()
    (tmp_path / ".sot" / "registry.yaml").write_text(
        yaml.dump({"schema_version": "1.0", "entries": [ENTRY_AUTH]}),
        encoding="utf-8",
    )

    # CWD is a nested child — no .sot there.
    child = tmp_path / "nested" / "child"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)

    # Make git fail so the parent-walk fallback is exercised.
    def git_fail(cmd, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "git":
            raise subprocess.CalledProcessError(128, cmd)
        return subprocess.run(cmd, **kwargs)

    monkeypatch.setattr(consult.subprocess, "run", git_fail)

    rc = consult.main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "auth-service" in out


# ---------------------------------------------------------------------------
# C23 — full main() call is read-only (gate at full call-path)
# ---------------------------------------------------------------------------


def test_c23_main_level_read_only(tmp_path: Path, capsys):
    """Running a complete main() query must not write or modify any file."""
    reg = _make_registry(tmp_path, TWO_ENTRIES)
    files_before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    consult.main(["list", "--json", "--registry", str(reg)])
    capsys.readouterr()  # discard output

    files_after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert files_before == files_after, "main() wrote or modified a file"


# ---------------------------------------------------------------------------
# C24-C26 — DEFECT-1: --json / --registry accepted POST-subcommand
# (consistent with detect-propose/verify and the SKILL.md example).
# These FAIL on pre-fix code (flags were on the top-level parser) with
# `SystemExit(2): unrecognized arguments`.
# ---------------------------------------------------------------------------


def test_c24_json_post_subcommand_list(registry: Path, capsys):
    """`list --json` (flag AFTER subcommand) parses and emits valid JSON."""
    rc = consult.main(["list", "--json", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["count"] == 2


def test_c25_json_post_subcommand_get(registry: Path, capsys):
    """`get <id> --json` (flag AFTER subcommand) parses and emits JSON."""
    rc = consult.main(["get", "auth-service", "--json", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["found"] is True
    assert data["entry"]["id"] == "auth-service"


def test_c26_registry_post_subcommand(registry: Path, capsys):
    """`list --registry PATH` (flag AFTER subcommand) resolves the registry."""
    rc = consult.main(["list", "--registry", str(registry)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "auth-service" in out
    assert "payments-api" in out


@pytest.mark.parametrize(
    "argv",
    [["--json", "list"], ["--registry", "X", "list"]],
)
def test_c27_pre_subcommand_ordering_rejected(argv: list[str]):
    """Flags BEFORE the subcommand are no longer accepted (argparse exits 2)."""
    with pytest.raises(SystemExit) as exc:
        consult.main(argv)
    assert exc.value.code == 2
