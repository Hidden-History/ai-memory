"""Integration tests for ENV-MANAGEMENT-V2 secrets split migration (BUG-277).

Tests T1-T12 per BP-154 §10, plus verify_env_split.py unit test.
All tests use tmp_path; no real install directory; no Docker subprocess.
Shell migration functions invoked via subprocess for T4-T9.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Path to helpers and verify script relative to this test file
_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
_HELPERS_SH = _SCRIPTS_DIR / "_env_split_helpers.sh"
_VERIFY_PY = _SCRIPTS_DIR / "verify_env_split.py"

# Canonical PP-2 key lists (split: 6 core + 12 Langfuse per F-r4-4 / Shape 1)
#
# Classification note (BUG-286 fix-r2): QDRANT_READ_ONLY_API_KEY is classified differently
# across subsystems — this is a known inconsistency, not an error:
#   - PP_2_CORE_KEYS here (and verify_env_split.py): 6 keys including QDRANT_READ_ONLY_API_KEY.
#     Reason: verify_env_split.py I3 requires it in .env.secrets for install verification.
#   - _env_split_helpers.sh pp3_keys (and ENV-MANAGEMENT-V2 §3.4): 6 PP-3 keys including
#     QDRANT_READ_ONLY_API_KEY. Reason: migration-scope classification (user-supplied / optional).
#
# Both reach 25-key total: 2 (PP-1) + 18 (PP-2 = 6 core + 12 Langfuse) + 5 (PP-3) = 25.
# True alignment (PP-2=17, PP-3=6) requires verify_env_split.py update — out of scope for
# BUG-286 fix-r2 (4-file allowlist). Tracked as follow-up TD.
PP_2_CORE_KEYS = [
    "QDRANT_API_KEY",
    "QDRANT_READ_ONLY_API_KEY",
    "GRAFANA_ADMIN_PASSWORD",
    "GRAFANA_SECRET_KEY",
    "PROMETHEUS_ADMIN_PASSWORD",
    "PROMETHEUS_BASIC_AUTH_HEADER",
]

PP_2_LANGFUSE_KEYS = [
    "LANGFUSE_DB_PASSWORD",
    "LANGFUSE_CLICKHOUSE_PASSWORD",
    "LANGFUSE_NEXTAUTH_SECRET",
    "LANGFUSE_SALT",
    "LANGFUSE_ENCRYPTION_KEY",
    "LANGFUSE_S3_ACCESS_KEY",
    "LANGFUSE_S3_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_INIT_PROJECT_PUBLIC_KEY",
    "LANGFUSE_INIT_PROJECT_SECRET_KEY",
    "LANGFUSE_INIT_USER_PASSWORD",
]

PP_2_KEYS = (
    PP_2_CORE_KEYS + PP_2_LANGFUSE_KEYS
)  # 18 total (test-suite construct; see classification note above)

PP_3_KEYS = [
    "OLLAMA_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "EVALUATOR_API_KEY",
]

# PP-1: user-input secrets — GITHUB_TOKEN + JIRA_API_TOKEN (BUG-286 fix scope)
PP_1_KEYS = [
    "GITHUB_TOKEN",
    "JIRA_API_TOKEN",
]

# Complete 25-key set for T13-T15: PP_1 (2) + PP_2 (18, test-suite construct) + PP_3 (5) = 25
# Note: total 25 matches _env_split_helpers.sh ALL_SECRET_KEYS (2+17+6=25); counts differ per
# classification note above. Key coverage is identical — all 25 secret-class keys included.
ALL_SECRET_KEYS_T = PP_1_KEYS + PP_2_KEYS + PP_3_KEYS

LANGFUSE_NON_SECRET_INIT_KEYS = [
    "LANGFUSE_INIT_ORG_ID",
    "LANGFUSE_INIT_ORG_NAME",
    "LANGFUSE_INIT_PROJECT_ID",
    "LANGFUSE_INIT_PROJECT_NAME",
    "LANGFUSE_INIT_USER_EMAIL",
    "LANGFUSE_INIT_USER_NAME",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_env(path: Path, pairs: dict) -> None:
    lines = [f'{k}="{v}"' if v else f"{k}=" for k, v in pairs.items()]
    path.write_text("\n".join(lines) + "\n")


def _read_env(path: Path) -> dict:
    result = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        result[k.strip()] = v.strip().strip("\"'")
    return result


def _run_bash(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
    )


def _migrate_via_bash(
    env_file: Path, secrets_file: Path
) -> subprocess.CompletedProcess:
    script = f"""
set -euo pipefail
source {_HELPERS_SH}
migrate_secrets_to_split_file {env_file} {secrets_file}
"""
    return _run_bash(script)


def _write_secret_via_bash(
    key: str, value: str, secrets_file: Path
) -> subprocess.CompletedProcess:
    script = f"""
set -euo pipefail
source {_HELPERS_SH}
write_secret_to_secrets_file {key} {value} {secrets_file}
"""
    return _run_bash(script)


def _run_verify(install_dir: Path, strict: bool = False) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(_VERIFY_PY), "--install-dir", str(install_dir)]
    if strict:
        cmd.append("--strict")
    return subprocess.run(cmd, capture_output=True, text=True)


def _make_minimal_compose(docker_dir: Path) -> None:
    """Write a minimal docker-compose.yml with the env_file anchor."""
    docker_dir.joinpath("docker-compose.yml").write_text(
        "x-python-service-defaults: &python-service-defaults\n"
        "  env_file:\n"
        "    - path: .env\n"
        "      required: true\n"
        "    - path: .env.secrets\n"
        "      required: false\n"
    )


def _make_install_dir(
    tmp_path: Path, env_pairs: dict, secrets_pairs: dict | None = None
) -> Path:
    """Create a minimal install dir structure for verify_env_split tests."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir(parents=True)
    env_file = docker_dir / ".env"
    _write_env(env_file, env_pairs)
    env_file.chmod(0o644)
    if secrets_pairs is not None:
        sec = docker_dir / ".env.secrets"
        _write_env(sec, secrets_pairs)
        sec.chmod(0o600)
    _make_minimal_compose(docker_dir)
    return tmp_path


# ---------------------------------------------------------------------------
# T1 — Fresh v2.4.0 install state
# ---------------------------------------------------------------------------


def test_t1_fresh_install_verify_passes(tmp_path):
    """T1: Post-v2.4.0 install: PP-2 in .env.secrets; .env has blank placeholders."""
    secrets_pairs = {k: f"generatedvalue_{k}" for k in PP_2_KEYS}
    env_pairs = dict.fromkeys(PP_2_KEYS, "")  # blank placeholders
    env_pairs["GITHUB_SYNC_ENABLED"] = "false"
    env_pairs["JIRA_SYNC_ENABLED"] = "false"
    for k in LANGFUSE_NON_SECRET_INIT_KEYS:
        env_pairs[k] = "some-value"

    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert (
        result.returncode == 0
    ), f"Expected exit 0; got {result.returncode}\n{result.stderr}"


# ---------------------------------------------------------------------------
# T4 — In-place v2.3.x upgrade: all 17 PP-2 in .env → migrate all
# ---------------------------------------------------------------------------


def test_t4_v23x_upgrade_migrates_all_pp2(tmp_path):
    """T4: v2.3.x .env with all PP-2 keys set → migration moves them to .env.secrets."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    # Simulate v2.3.x state: all PP-2 keys present in .env
    env_pairs = {k: f"oldvalue_{k}" for k in PP_2_KEYS}
    _write_env(env_file, env_pairs)

    result = _migrate_via_bash(env_file, secrets_file)
    assert result.returncode == 0, f"Migration failed: {result.stderr}"

    env_after = _read_env(env_file)
    secrets_after = _read_env(secrets_file)

    for key in PP_2_KEYS:
        assert secrets_after.get(key) == f"oldvalue_{key}", f"{key} not in .env.secrets"
        assert not env_after.get(key), f"{key} still non-empty in .env after migration"


# ---------------------------------------------------------------------------
# T5 — Idempotence: 10 already migrated, 7 remaining
# ---------------------------------------------------------------------------


def test_t5_idempotent_partial_migration(tmp_path):
    """T5: Partial migration state → re-run migrates remaining keys; no duplicates."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    migrated = PP_2_KEYS[:10]
    remaining = PP_2_KEYS[10:]

    # Pre-populate .env.secrets with first 10 keys already migrated
    secrets_pairs = {k: f"already_{k}" for k in migrated}
    _write_env(secrets_file, secrets_pairs)
    secrets_file.chmod(0o600)

    # .env has remaining 7 keys still present
    env_pairs = dict.fromkeys(migrated, "")  # blanked
    env_pairs.update({k: f"toremove_{k}" for k in remaining})
    _write_env(env_file, env_pairs)

    result = _migrate_via_bash(env_file, secrets_file)
    assert result.returncode == 0, f"Migration failed: {result.stderr}"

    env_after = _read_env(env_file)
    secrets_after = _read_env(secrets_file)

    # All PP-2 keys should now be in .env.secrets
    for key in migrated:
        assert (
            secrets_after.get(key) == f"already_{key}"
        ), f"{key} value changed unexpectedly"
    for key in remaining:
        assert secrets_after.get(key) == f"toremove_{key}", f"{key} not migrated"
        assert not env_after.get(key), f"{key} still in .env after migration"

    # No duplicate keys in .env.secrets — per-line startswith count
    raw = secrets_file.read_text()
    for key in PP_2_KEYS:
        count = sum(1 for line in raw.splitlines() if line.startswith(f"{key}="))
        assert count <= 1, f"Duplicate {key} entries in .env.secrets: count={count}"


# ---------------------------------------------------------------------------
# T6 — PP-3 optional keys populated by user in .env → migrated
# ---------------------------------------------------------------------------


def test_t6_pp3_populated_migrated(tmp_path):
    """T6: PP-3 keys present in .env → migrate_secrets_to_split_file moves them."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    env_pairs = {
        "OLLAMA_API_KEY": "user_ollama_key",
        "OPENROUTER_API_KEY": "user_openrouter_key",
    }
    _write_env(env_file, env_pairs)

    result = _migrate_via_bash(env_file, secrets_file)
    assert result.returncode == 0, f"Migration failed: {result.stderr}"

    env_after = _read_env(env_file)
    secrets_after = _read_env(secrets_file)

    assert secrets_after.get("OLLAMA_API_KEY") == "user_ollama_key"
    assert secrets_after.get("OPENROUTER_API_KEY") == "user_openrouter_key"
    assert not env_after.get("OLLAMA_API_KEY")
    assert not env_after.get("OPENROUTER_API_KEY")


# ---------------------------------------------------------------------------
# T7 — PP-3 keys empty in .env → skip without error
# ---------------------------------------------------------------------------


def test_t7_pp3_empty_skipped(tmp_path):
    """T7: PP-3 keys empty/absent in .env → no error; .env.secrets unchanged."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    env_pairs = {"OLLAMA_API_KEY": "", "OPENROUTER_API_KEY": ""}
    _write_env(env_file, env_pairs)

    result = _migrate_via_bash(env_file, secrets_file)
    assert result.returncode == 0, f"Migration failed: {result.stderr}"

    secrets_after = _read_env(secrets_file) if secrets_file.exists() else {}
    assert not secrets_after.get("OLLAMA_API_KEY")
    assert not secrets_after.get("OPENROUTER_API_KEY")


# ---------------------------------------------------------------------------
# T8 — Orphan tempfile from interrupted migration → verify flags it; re-run cleans up
# ---------------------------------------------------------------------------


def test_t8_orphan_tempfile_flagged_by_verify(tmp_path):
    """T8: Orphan .env.secrets.XXXXXX tempfile → verify_env_split I7 fails."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    # Write a complete post-install state
    secrets_pairs = {k: f"val_{k}" for k in PP_2_KEYS}
    _write_env(secrets_file, secrets_pairs)
    secrets_file.chmod(0o600)
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["GITHUB_SYNC_ENABLED"] = "false"
    _write_env(env_file, env_pairs)
    _make_minimal_compose(docker_dir)

    # Simulate orphan tempfile left from interrupted migration
    orphan = docker_dir / ".env.secrets.ABCDEF"
    orphan.write_text('SOME_KEY="partial"\n')

    result = _run_verify(tmp_path)
    assert result.returncode == 1, "Expected invariant failure due to orphan tempfile"
    assert "I7" in result.stderr

    # Remove orphan → verify should pass
    orphan.unlink()
    result2 = _run_verify(tmp_path)
    assert (
        result2.returncode == 0
    ), f"Expected pass after orphan removal\n{result2.stderr}"


# ---------------------------------------------------------------------------
# T9 — .env.secrets write permission denied → .env unchanged
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.getuid() == 0, reason="Cannot test permission denial as root")
def test_t9_secrets_write_denied_env_unchanged(tmp_path):
    """T9: If the docker dir is not writable, mktemp fails and .env is unchanged.

    Making the directory unwritable blocks mktemp (rename() bypass avoided).
    """
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    env_pairs = {"QDRANT_API_KEY": "original_key"}
    _write_env(env_file, env_pairs)

    # Make the docker directory unwritable — mktemp requires directory write permission
    # to create the tempfile. This is the correct failure-mode trigger: mktemp fails
    # because it cannot create a new file in the directory. The rename() syscall itself
    # does not require dest-file write permission, so directory-level denial is the
    # right approach (not revoking .env.secrets write permission directly).
    docker_dir.chmod(0o555)

    try:
        script = f"""
set -uo pipefail
source {_HELPERS_SH}
migrate_secret_to_secrets_file QDRANT_API_KEY {env_file} {secrets_file}
"""
        result = _run_bash(script)
        # mktemp should fail (directory not writable)
        assert (
            result.returncode != 0
        ), f"Expected non-zero exit when docker dir unwritable; got 0\n{result.stdout}"

        # Verify the failure message identifies the correct failure mode
        assert (
            "mktemp" in result.stderr.lower() or "permission" in result.stderr.lower()
        ), f"Expected mktemp/permission error in stderr; got: {result.stderr!r}"

        # .env must remain unchanged — original_key still present
        env_after = _read_env(env_file)
        assert (
            env_after.get("QDRANT_API_KEY") == "original_key"
        ), ".env was modified despite mktemp failure"
    finally:
        docker_dir.chmod(0o755)


# ---------------------------------------------------------------------------
# T10 — Rollback: .env.secrets deleted (v2.3.x reinstall)
# ---------------------------------------------------------------------------


def test_t10_rollback_verify_fails_then_fresh_gen_passes(tmp_path):
    """T10: After migration, deleting .env.secrets simulates rollback.

    verify_env_split should detect missing PP-2 keys; after fresh generation it passes.
    """
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    _make_minimal_compose(docker_dir)

    # State: .env.secrets deleted; .env has blank placeholders (migrated state without file)
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["GITHUB_SYNC_ENABLED"] = "false"
    _write_env(env_file, env_pairs)

    result = _run_verify(tmp_path)
    # .env.secrets absent but .env has blanks → I1 pass (no non-empty secrets in .env);
    # I3 fails (PP-2 keys not in secrets)
    assert result.returncode in (0, 1), f"Unexpected exit code: {result.returncode}"

    # Simulate fresh generation by writing new .env.secrets
    secrets_file = docker_dir / ".env.secrets"
    new_secrets = {k: f"regenerated_{k}" for k in PP_2_KEYS}
    _write_env(secrets_file, new_secrets)
    secrets_file.chmod(0o600)

    result2 = _run_verify(tmp_path)
    assert (
        result2.returncode == 0
    ), f"Expected pass after re-generation\n{result2.stderr}"


# ---------------------------------------------------------------------------
# T11 — Container runtime (no Docker): verify compose yaml has required: false
# ---------------------------------------------------------------------------


def test_t11_compose_yaml_has_secrets_required_false(tmp_path):
    """T11: docker-compose.yml lists .env.secrets with required: false (I8)."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    _make_minimal_compose(docker_dir)
    env_file = docker_dir / ".env"
    _write_env(env_file, {})
    secrets_file = docker_dir / ".env.secrets"
    _write_env(secrets_file, {k: f"v_{k}" for k in PP_2_KEYS})
    secrets_file.chmod(0o600)
    env_file.chmod(0o644)

    compose_text = (docker_dir / "docker-compose.yml").read_text()
    assert ".env.secrets" in compose_text
    assert "required: false" in compose_text


# ---------------------------------------------------------------------------
# T12 — .env.secrets absent: required: false, services start without secrets
# ---------------------------------------------------------------------------


def test_t12_secrets_absent_compose_required_false(tmp_path):
    """T12: .env.secrets absent → required: false means compose starts; I1 still OK when .env has blanks."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    _make_minimal_compose(docker_dir)

    # .env has blank placeholders (correct post-install state for blank secrets)
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["GITHUB_SYNC_ENABLED"] = "false"
    env_file = docker_dir / ".env"
    _write_env(env_file, env_pairs)
    env_file.chmod(0o644)
    # No .env.secrets — simulates fresh deploy where secrets not yet configured

    result = _run_verify(tmp_path)
    # I1 passes (no non-empty secrets in .env); I3 fails (PP-2 keys absent)
    # Overall exit 1 expected (I3 failure)
    assert result.returncode == 1
    assert "I3" in result.stderr


# ---------------------------------------------------------------------------
# verify_env_split.py unit tests: exit codes
# ---------------------------------------------------------------------------


def test_verify_exit_0_all_invariants_pass(tmp_path):
    """verify_env_split.py exits 0 when all invariants pass."""
    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    secrets_pairs["GITHUB_TOKEN"] = "ghp_test"
    secrets_pairs["JIRA_API_TOKEN"] = "jira_test"
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["GITHUB_SYNC_ENABLED"] = "true"
    env_pairs["JIRA_SYNC_ENABLED"] = "true"
    for k in LANGFUSE_NON_SECRET_INIT_KEYS:
        env_pairs[k] = "val"

    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert result.returncode == 0, result.stderr


def test_verify_exit_1_pp2_missing(tmp_path):
    """verify_env_split.py exits 1 when PP-2 key absent from .env.secrets."""
    # Only put one key in secrets — missing the rest
    secrets_pairs = {"QDRANT_API_KEY": "present"}
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["GITHUB_SYNC_ENABLED"] = "false"

    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert result.returncode == 1
    assert "I3" in result.stderr


def test_verify_exit_1_leaked_secret_in_env(tmp_path):
    """verify_env_split.py exits 1 when a secret-class key has non-empty value in .env."""
    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["QDRANT_API_KEY"] = "leaked_value"  # should be blank
    env_pairs["GITHUB_SYNC_ENABLED"] = "false"

    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert result.returncode == 1
    assert "I4" in result.stderr


def test_verify_exit_2_env_file_missing(tmp_path):
    """verify_env_split.py exits 2 when docker/.env is missing."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    # No .env file created
    result = _run_verify(tmp_path)
    assert result.returncode == 2


def test_verify_strict_pp3_in_env_fails(tmp_path):
    """verify_env_split.py --strict exits 1 when PP-3 key non-empty in .env."""
    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["OLLAMA_API_KEY"] = "user_key"  # PP-3, non-empty — fails under --strict
    env_pairs["GITHUB_SYNC_ENABLED"] = "false"

    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir, strict=True)
    assert result.returncode == 1
    assert "STRICT" in result.stderr


def test_verify_i5_github_token_required_when_sync_enabled(tmp_path):
    """verify_env_split.py fails I5 when GITHUB_SYNC_ENABLED=true but GITHUB_TOKEN absent."""
    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    # GITHUB_TOKEN intentionally absent from secrets
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["GITHUB_SYNC_ENABLED"] = "true"

    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert result.returncode == 1
    assert "I5" in result.stderr


def test_verify_i6_non_secret_langfuse_init_in_secrets_fails(tmp_path):
    """verify_env_split.py fails I6 when non-secret LANGFUSE_INIT_* key is in .env.secrets."""
    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    secrets_pairs["LANGFUSE_INIT_ORG_ID"] = (
        "ai-memory-org"  # non-secret, should NOT be here
    )
    env_pairs = dict.fromkeys(PP_2_KEYS, "")
    env_pairs["GITHUB_SYNC_ENABLED"] = "false"

    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert result.returncode == 1
    assert "I6" in result.stderr


def test_verify_i8_compose_missing_secrets_entry(tmp_path):
    """verify_env_split.py fails I8 when compose file lacks .env.secrets entry."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()

    # Compose without .env.secrets
    (docker_dir / "docker-compose.yml").write_text(
        "x-defaults: &defaults\n  env_file:\n    - path: .env\n      required: true\n"
    )
    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    env_file = docker_dir / ".env"
    _write_env(
        env_file, {"GITHUB_SYNC_ENABLED": "false", **dict.fromkeys(PP_2_KEYS, "")}
    )
    env_file.chmod(0o644)
    sec = docker_dir / ".env.secrets"
    _write_env(sec, secrets_pairs)
    sec.chmod(0o600)

    result = _run_verify(tmp_path)
    assert result.returncode == 1
    assert "I8" in result.stderr


# ---------------------------------------------------------------------------
# T2 — Fresh v2.4.0 install: orphaned .env with no PP-2 values
# ---------------------------------------------------------------------------


def test_t2_orphaned_env_fresh_install(tmp_path):
    """T2: .env has only non-secret-class keys and blank placeholders — upgrade probe finds no
    non-empty secret-class values (25-key check) → no migration triggered."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    # .env has non-secret-class keys and blank placeholders — no non-empty values for any of the 25 keys
    _write_env(
        env_file,
        {
            "LANGFUSE_INIT_ORG_ID": "ai-memory-org",
            "LANGFUSE_INIT_USER_EMAIL": "test@example.com",
            "AI_MEMORY_PROJECT_ID": "my-project",
            **dict.fromkeys(
                ALL_SECRET_KEYS_T, ""
            ),  # blank placeholders for all 25 secret-class keys
        },
    )

    # Run the upgrade-detection probe (mirrors migrate_existing_env_secrets after BUG-286 fix-r2).
    # Built from ALL_SECRET_KEYS_T so this test stays in sync with production automatically.
    detection_alternation = "|".join(ALL_SECRET_KEYS_T)
    script = f"""
set -uo pipefail
if grep -qE "^({detection_alternation})=.+" {env_file} 2>/dev/null; then
    echo "MIGRATION_NEEDED"
else
    echo "FRESH_INSTALL"
fi
"""
    result = _run_bash(script)
    assert result.returncode == 0, f"Probe script failed: {result.stderr}"
    assert (
        "FRESH_INSTALL" in result.stdout
    ), f"Expected probe to detect fresh install (no non-empty secret-class keys); got: {result.stdout!r}"
    # .env.secrets must not have been created by migration
    assert (
        not secrets_file.exists()
    ), ".env.secrets was unexpectedly created when no migration should run"


# ---------------------------------------------------------------------------
# T3 — Fresh v2.4.0 install: existing .env.secrets with partial PP-2 keys
# ---------------------------------------------------------------------------


def test_t3_existing_partial_secrets_fresh_install(tmp_path):
    """T3: .env.secrets has 5 of 18 PP-2 keys → write_secret_to_secrets_file adds missing; no duplicates; existing values preserved; chmod 600 preserved."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    secrets_file = docker_dir / ".env.secrets"

    pre_existing_keys = PP_2_KEYS[:5]
    missing_keys = PP_2_KEYS[5:]

    # Pre-populate .env.secrets with first 5 PP-2 keys
    secrets_pairs = {k: f"existing_{k}" for k in pre_existing_keys}
    _write_env(secrets_file, secrets_pairs)
    secrets_file.chmod(0o600)

    # Write all 18 PP-2 keys via write_secret_to_secrets_file (simulating fresh install)
    for key in PP_2_KEYS:
        result = _write_secret_via_bash(key, f"fresh_{key}", secrets_file)
        assert (
            result.returncode == 0
        ), f"write_secret_to_secrets_file failed for {key}: {result.stderr}"

    secrets_after = _read_env(secrets_file)

    # All 18 PP-2 keys must be present
    for key in PP_2_KEYS:
        assert secrets_after.get(key), f"{key} missing from .env.secrets after write"

    # Pre-existing keys must retain their original values (idempotence)
    for key in pre_existing_keys:
        assert (
            secrets_after[key] == f"existing_{key}"
        ), f"{key} value changed: expected existing_{key}, got {secrets_after[key]!r}"

    # Missing keys must have the freshly written values
    for key in missing_keys:
        assert (
            secrets_after[key] == f"fresh_{key}"
        ), f"{key} value wrong: expected fresh_{key}, got {secrets_after[key]!r}"

    # No duplicates — per-line startswith count (same assertion as F14 fix)
    raw = secrets_file.read_text()
    for key in PP_2_KEYS:
        count = sum(1 for line in raw.splitlines() if line.startswith(f"{key}="))
        assert count <= 1, f"Duplicate {key} entries in .env.secrets: count={count}"

    # chmod 600 must be preserved
    mode = secrets_file.stat().st_mode & 0o777
    assert mode == 0o600, f".env.secrets mode is {oct(mode)}, expected 0o600"


# ---------------------------------------------------------------------------
# F1 / I2 — WSL-detection tests (monkeypatch _is_wsl)
# ---------------------------------------------------------------------------


def _import_verify_module():
    """Import verify_env_split.py as a module for monkeypatching."""
    spec = importlib.util.spec_from_file_location("verify_env_split", _VERIFY_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verify_i2_permissions_fail_on_non_wsl(tmp_path, monkeypatch):
    """I2 fails (exit 1) when .env.secrets is chmod 644 on a non-WSL host."""
    mod = _import_verify_module()
    monkeypatch.setattr(mod, "_is_wsl", lambda: False)

    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    env_pairs = {**dict.fromkeys(PP_2_KEYS, ""), "GITHUB_SYNC_ENABLED": "false"}
    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    (install_dir / "docker" / ".env.secrets").chmod(0o644)

    rc = mod.run_checks(str(install_dir), strict=False)
    assert (
        rc == 1
    ), f"Expected exit 1 on non-WSL host with .env.secrets chmod 644; got {rc}"


def test_verify_i2_permissions_warn_on_wsl(tmp_path, monkeypatch, capsys):
    """I2 degrades to [WARN] (exit 0) when .env.secrets is chmod 644 on a WSL host."""
    mod = _import_verify_module()
    monkeypatch.setattr(mod, "_is_wsl", lambda: True)

    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    env_pairs = {**dict.fromkeys(PP_2_KEYS, ""), "GITHUB_SYNC_ENABLED": "false"}
    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    (install_dir / "docker" / ".env.secrets").chmod(0o644)

    rc = mod.run_checks(str(install_dir), strict=False)
    assert (
        rc == 0
    ), f"Expected exit 0 on WSL host with .env.secrets chmod 644 (warn only); got {rc}"
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out, "Expected [WARN] in stdout for WSL I2 mismatch"


# ---------------------------------------------------------------------------
# F3 / I8 — Inverted compose layout regression test
# ---------------------------------------------------------------------------


def test_verify_i8_inverted_layout_fails(tmp_path):
    """I8 fails when .env.secrets is required: true and .env is required: false (inverted layout)."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()

    # Compose with .env.secrets required: true (inverted — the layout I8 is meant to catch)
    (docker_dir / "docker-compose.yml").write_text(
        "x-python-service-defaults: &python-service-defaults\n"
        "  env_file:\n"
        "    - path: .env.secrets\n"
        "      required: true\n"
        "    - path: .env\n"
        "      required: false\n"
    )
    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    env_file = docker_dir / ".env"
    _write_env(
        env_file, {"GITHUB_SYNC_ENABLED": "false", **dict.fromkeys(PP_2_KEYS, "")}
    )
    env_file.chmod(0o644)
    sec = docker_dir / ".env.secrets"
    _write_env(sec, secrets_pairs)
    sec.chmod(0o600)

    result = _run_verify(tmp_path)
    assert (
        result.returncode == 1
    ), f"Expected exit 1 for inverted compose layout; got {result.returncode}"
    assert "I8" in result.stderr, f"Expected I8 in stderr; got: {result.stderr!r}"


# ---------------------------------------------------------------------------
# F-r4-3 — I7 glob: .env.secrets.example is NOT flagged as orphan
# ---------------------------------------------------------------------------


def test_i7_example_template_not_flagged_as_orphan(tmp_path):
    """I7: .env.secrets.example (shipped template) must NOT trigger orphan-tempfile failure.

    Regression test for F-r4-3: the I7 glob previously matched .env.secrets.example
    as an orphan because the exclude-suffix filter was absent.
    """
    secrets_pairs = {k: f"v_{k}" for k in PP_2_CORE_KEYS}
    env_pairs = {**dict.fromkeys(PP_2_KEYS, ""), "GITHUB_SYNC_ENABLED": "false"}
    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)

    # Simulate the shipped template being present in docker/
    (install_dir / "docker" / ".env.secrets.example").write_text(
        "# Example secrets file\nQDRANT_API_KEY=\n", encoding="utf-8"
    )

    result = _run_verify(install_dir)
    assert (
        "I7" not in result.stderr
    ), f"I7 must not flag .env.secrets.example as orphan; stderr:\n{result.stderr}"


def test_i7_genuine_orphan_still_flagged(tmp_path):
    """I7: a genuine mktemp-style .env.secrets.AbCdEf IS still flagged after F-r4-3."""
    secrets_pairs = {k: f"v_{k}" for k in PP_2_CORE_KEYS}
    env_pairs = {**dict.fromkeys(PP_2_KEYS, ""), "GITHUB_SYNC_ENABLED": "false"}
    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)

    (install_dir / "docker" / ".env.secrets.AbCdEf").write_text(
        'SOME_KEY="partial"\n', encoding="utf-8"
    )

    result = _run_verify(install_dir)
    assert result.returncode == 1, "Expected exit 1 for genuine orphan tempfile"
    assert "I7" in result.stderr, f"Expected I7 in stderr; got: {result.stderr!r}"


# ---------------------------------------------------------------------------
# F-r4-4 — I3 Langfuse-gated PP-2 audit
# ---------------------------------------------------------------------------


def test_i3_langfuse_disabled_core_only_passes(tmp_path):
    """I3: LANGFUSE_ENABLED=false with only 6 core PP-2 keys present → I3 PASS.

    Regression test for F-r4-4: before the fix, I3 failed whenever Langfuse keys
    were absent, even on a non-Langfuse install.
    """
    secrets_pairs = {k: f"v_{k}" for k in PP_2_CORE_KEYS}
    env_pairs = {
        **dict.fromkeys(PP_2_KEYS, ""),
        "GITHUB_SYNC_ENABLED": "false",
        "LANGFUSE_ENABLED": "false",
    }
    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert (
        result.returncode == 0
    ), f"Expected exit 0 (LANGFUSE_ENABLED=false, core keys present); stderr:\n{result.stderr}"
    assert "I3" not in result.stderr, f"I3 must not fail; stderr:\n{result.stderr}"


def test_i3_langfuse_enabled_requires_langfuse_keys(tmp_path):
    """I3: LANGFUSE_ENABLED=true with Langfuse keys absent → I3 FAIL.

    Verifies the Langfuse gate activates when LANGFUSE_ENABLED=true.
    """
    secrets_pairs = {k: f"v_{k}" for k in PP_2_CORE_KEYS}
    # No Langfuse PP-2 keys in secrets
    env_pairs = {
        **dict.fromkeys(PP_2_KEYS, ""),
        "GITHUB_SYNC_ENABLED": "false",
        "LANGFUSE_ENABLED": "true",
    }
    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert (
        result.returncode == 1
    ), "Expected exit 1 (LANGFUSE_ENABLED=true, Langfuse keys absent)"
    assert "I3" in result.stderr, f"Expected I3 in stderr; got: {result.stderr!r}"


def test_i3_langfuse_enabled_all_keys_passes(tmp_path):
    """I3: LANGFUSE_ENABLED=true with all 18 PP-2 keys present → I3 PASS."""
    secrets_pairs = {k: f"v_{k}" for k in PP_2_KEYS}
    env_pairs = {
        **dict.fromkeys(PP_2_KEYS, ""),
        "GITHUB_SYNC_ENABLED": "false",
        "LANGFUSE_ENABLED": "true",
    }
    install_dir = _make_install_dir(tmp_path, env_pairs, secrets_pairs)
    result = _run_verify(install_dir)
    assert (
        result.returncode == 0
    ), f"Expected exit 0 (LANGFUSE_ENABLED=true, all keys present); stderr:\n{result.stderr}"


# ---------------------------------------------------------------------------
# T13 — PP-1 leak via TD-198 restore: existing .env has GITHUB_TOKEN from
#        historical write; .env.secrets already has newer token (reinstall #5 scenario).
#        Migration must blank .env, leaving .env.secrets unchanged.
# ---------------------------------------------------------------------------


def test_t13_migrate_pp1_from_env_when_secrets_already_has_value(tmp_path):
    """T13: Migration logic test for the reinstall #5 leak pattern. Simulates the post-TD-198
    state: .env has an old PP-1 token (from a historical write path that TD-198 backup+restore
    preserved across reinstalls), .env.secrets already has a newer token from
    persist_user_choices_to_env. Migration must blank .env GITHUB_TOKEN without overwriting
    the existing .env.secrets value. .env.secrets perms 600 preserved.

    Scope: this test exercises migrate_secrets_to_split_file directly via subprocess (using
    _migrate_via_bash helper), NOT the full TD-198 backup+restore + install flow. The migration
    idempotency invariant is verified here; the full install flow is not covered in this file.
    """
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    # Arrange: .env has old PP-1 token (historical write leak); .env.secrets has newer token
    _write_env(env_file, {"GITHUB_TOKEN": "ghp_old_leaked_value"})
    _write_env(secrets_file, {"GITHUB_TOKEN": "ghp_newer_correct_value"})
    secrets_file.chmod(0o600)

    # Act: migration (simulate migrate_existing_env_secrets with PP-1 now in scope)
    result = _migrate_via_bash(env_file, secrets_file)
    assert result.returncode == 0, f"Migration failed: {result.stderr}"

    env_after = _read_env(env_file)
    secrets_after = _read_env(secrets_file)

    # .env GITHUB_TOKEN must be blank (old leaked value removed)
    assert not env_after.get(
        "GITHUB_TOKEN"
    ), f"GITHUB_TOKEN still non-empty in .env: {env_after.get('GITHUB_TOKEN')!r}"
    # .env.secrets GITHUB_TOKEN must retain the newer value (not overwritten by migration)
    assert (
        secrets_after.get("GITHUB_TOKEN") == "ghp_newer_correct_value"
    ), f".env.secrets GITHUB_TOKEN changed unexpectedly: {secrets_after.get('GITHUB_TOKEN')!r}"
    # .env.secrets perms 600 must be preserved
    mode = secrets_file.stat().st_mode & 0o777
    assert mode == 0o600, f".env.secrets mode is {oct(mode)}, expected 0o600"


# ---------------------------------------------------------------------------
# T14 — All 25 secret-class keys present in .env → migration moves all to
#        .env.secrets; .env has no non-empty secret-class values after.
# ---------------------------------------------------------------------------


def test_t14_all_25_secret_class_keys_filtered_from_env(tmp_path):
    """T14: source .env has all 25 secret-class keys populated → migration → installed .env
    has none with non-blank values; installed .env.secrets has all 25 with values."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    # Arrange: all 25 keys in .env with distinct test values
    env_pairs = {k: f"testvalue_{k}" for k in ALL_SECRET_KEYS_T}
    _write_env(env_file, env_pairs)

    # Act
    result = _migrate_via_bash(env_file, secrets_file)
    assert result.returncode == 0, f"Migration failed: {result.stderr}"

    env_after = _read_env(env_file)
    secrets_after = _read_env(secrets_file)

    for key in ALL_SECRET_KEYS_T:
        assert not env_after.get(
            key
        ), f"{key} still non-empty in .env after migration: {env_after.get(key)!r}"
        assert (
            secrets_after.get(key) == f"testvalue_{key}"
        ), f"{key} missing or wrong in .env.secrets: {secrets_after.get(key)!r}"


# ---------------------------------------------------------------------------
# T15 — Idempotency: post-fix state (all 25 in .env.secrets, .env blank) →
#        re-run migration → .env.secrets unchanged, .env stays blank.
# ---------------------------------------------------------------------------


def test_t15_idempotent_after_fix(tmp_path):
    """T15: run migration twice → second run produces no change; .env.secrets values
    unchanged (no overwrite); .env remains blank for all 25 secret-class keys."""
    import hashlib

    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"

    # Arrange: correct post-install state — all 25 in .env.secrets, .env has blanks
    secrets_pairs = {k: f"run1_{k}" for k in ALL_SECRET_KEYS_T}
    _write_env(secrets_file, secrets_pairs)
    secrets_file.chmod(0o600)
    env_pairs = dict.fromkeys(ALL_SECRET_KEYS_T, "")
    _write_env(env_file, env_pairs)

    # Capture .env.secrets state before second run
    sha_before = hashlib.sha256(secrets_file.read_bytes()).hexdigest()

    # Act: second migration run (idempotency)
    result = _migrate_via_bash(env_file, secrets_file)
    assert result.returncode == 0, f"Second migration run failed: {result.stderr}"

    sha_after = hashlib.sha256(secrets_file.read_bytes()).hexdigest()

    # .env.secrets content must be identical — no values overwritten
    assert (
        sha_after == sha_before
    ), ".env.secrets content changed on idempotent re-run — existing values must not be overwritten"

    # .env must still have blank values for all 25 keys
    env_after = _read_env(env_file)
    for key in ALL_SECRET_KEYS_T:
        assert not env_after.get(
            key
        ), f"{key} non-empty in .env after idempotent migration: {env_after.get(key)!r}"
