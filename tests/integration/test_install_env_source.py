"""Regression tests for install.sh env sourcing patterns.

BUG-273 tests: verify the `source <(grep -v -E '^(UID|GID)=' .env)` fix at the two
code sites in setup_github_indexes() and run_initial_github_sync().

W1-F1 tests (defense-in-depth): verify that setup_github_indexes, run_initial_github_sync,
and drain_pending_queue source docker/.env.secrets in addition to docker/.env, matching
the setup_collections dual-source pattern (BUG-292 fix).

W1-F1 implementation: each test extracts the env-loading block from the actual
install.sh function via sed process substitution (mirrors test_run_with_env_dual_source.py
pattern), so structural regressions in the script are caught rather than just verifying
the documented pattern.

No external services required — shells out to bash only.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# install.sh under test — W1-F1 env-loading blocks are extracted via sed
INSTALL_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "install.sh"

# BUG-273 fixture: matches docker/.env.example shape with real key values.
# Used by test_fixed_pattern_succeeds and test_old_pattern_emits_readonly_error.
ENV_CONTENT = """\
UID=1000
GID=1000
QDRANT_API_KEY=testkey123
GITHUB_TOKEN=ghp_test
GITHUB_REPO=owner/repo
MARKER_VAR=hello
"""

# W1-F1 fixture: post-BUG-277 split layout — PP-1/PP-2 keys are blank placeholders
# in .env; real values live in .env.secrets. Used by dual_source_dir fixture.
DUAL_SOURCE_ENV_CONTENT = """\
UID=1000
GID=1000
QDRANT_API_KEY=
GITHUB_TOKEN=
GITHUB_REPO=owner/repo
MARKER_VAR=hello
"""

# Value that lives in .env.secrets post-BUG-277 (blank placeholders in DUAL_SOURCE_ENV_CONTENT)
SECRETS_CONTENT = """\
QDRANT_API_KEY=secrets_qdrant_key
GITHUB_TOKEN=secrets_github_token
"""


@pytest.fixture()
def env_file(tmp_path):
    """Write a temp .env file with the same shape as docker/.env.example (BUG-273 scenario)."""
    p = tmp_path / ".env"
    p.write_text(ENV_CONTENT)
    return str(p)


@pytest.fixture()
def dual_source_dir(tmp_path):
    """Create a docker/ subdir with both .env (blank secrets) and .env.secrets (real values).

    Simulates the post-BUG-277 split layout: PP-2 keys are blank placeholders in .env and
    have real values in .env.secrets. Used by the W1-F1 dual-source tests.
    """
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    (docker_dir / ".env").write_text(DUAL_SOURCE_ENV_CONTENT)
    (docker_dir / ".env.secrets").write_text(SECRETS_CONTENT)
    return tmp_path  # INSTALL_DIR points here; docker/ is the subdirectory


def _minimal_env():
    """Return a minimal environment with only PATH so python resolves correctly."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}


def test_fixed_pattern_succeeds(env_file):
    """The grep -v fix allows sourcing without UID/GID readonly collisions.

    Verifies: no readonly error in stderr, MARKER_VAR propagated to child
    process, exit status 0.
    """
    python = sys.executable
    cmd = (
        f"set -a && source <(grep -v -E '^(UID|GID)=' {env_file}) && set +a"
        f" && {python} -c \"import os; print(os.environ['MARKER_VAR'])\""
    )
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        env=_minimal_env(),
    )
    assert b"UID: readonly variable" not in result.stderr
    assert b"GID: readonly variable" not in result.stderr
    assert (
        result.returncode == 0
    ), f"Expected exit 0, got {result.returncode}; stderr: {result.stderr.decode()}"
    assert b"hello" in result.stdout


def test_old_pattern_emits_readonly_error(env_file):
    """The old bare `source .env` pattern emits a UID readonly error (BUG-273 pre-fix).

    This test documents pre-fix behavior and acts as a regression-catcher:
    if this test starts failing (no readonly error), it means either bash
    behavior changed or UID/GID were removed from the fixture — either of
    which warrants investigation.
    """
    cmd = f"set -a && source {env_file} && set +a && echo ok"
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        env=_minimal_env(),
    )
    # Either the readonly error appears in stderr OR the command exits non-zero.
    # Both are acceptable signals that the old pattern is broken by UID/GID.
    uid_error = b"UID: readonly variable" in result.stderr
    gid_error = b"GID: readonly variable" in result.stderr
    nonzero_exit = result.returncode != 0
    assert uid_error or gid_error or nonzero_exit, (
        "Expected old pattern to fail with readonly error or non-zero exit,"
        f" but got returncode={result.returncode} and no readonly error in stderr."
        " Check if UID/GID were removed from the fixture."
    )


# ---------------------------------------------------------------------------
# W1-F1 dual-source tests (BUG-292 fix — defense-in-depth pattern alignment)
# ---------------------------------------------------------------------------
# Each test verifies that the named install.sh subshell sources docker/.env.secrets
# in addition to docker/.env, so that PP-2/PP-1 secret-class keys (QDRANT_API_KEY,
# GITHUB_TOKEN) are available in the subshell environment after the W1-F1 fix.
# The canonical reference pattern is setup_collections (BUG-275 anchor).
#
# Implementation: each test extracts the env-loading block from the actual
# install.sh function body via sed process substitution, sets INSTALL_DIR to the
# fixture directory, then runs a Python env-check command in place of the original
# Python script. This ensures structural regressions (e.g., accidentally dropping
# the .env.secrets source line) are caught.
# ---------------------------------------------------------------------------


def test_drain_pending_queue_dual_source(dual_source_dir):
    """drain_pending_queue subshell sources .env.secrets in addition to .env (W1-F1 fix).

    Extracts the env-loading block from install.sh::drain_pending_queue via sed
    (sed range: (   set -a through .env.secrets source within the function). Sets
    INSTALL_DIR to the fixture directory and runs a Python env-check in place of
    process_retry_queue.py. Asserts QDRANT_API_KEY resolves from .env.secrets.

    Defense-in-depth: process_retry_queue.py currently uses MemoryStorage/MemoryConfig
    (W1-F2 RESOLVED), but the pattern alignment ensures future direct env reads will
    also work correctly.
    """
    install_dir = str(dual_source_dir)
    python = sys.executable
    install_script = str(INSTALL_SCRIPT)

    # Source the env-loading block from drain_pending_queue in the actual install.sh.
    # sed range: from the subshell opener (   set -a through the .env.secrets source line.
    # The ( opener is stripped (s/^    (   set -a$/set -a/) so the block is
    # sourceable without an unclosed subshell.
    cmd = (
        f"INSTALL_DIR={install_dir!r}\n"
        "source <(sed -n '/^drain_pending_queue/,/^setup_github_indexes/{\n"
        '    /^    (   set -a$/,/source "\\$INSTALL_DIR\\/docker\\/.env.secrets"/{\n'
        "        s/^    (   set -a$/set -a/\n"
        "        p\n"
        "    }\n"
        f"}}' {install_script!r})\n"
        f"{python} -c \"import os; print(os.environ.get('QDRANT_API_KEY', 'MISSING'))\""
    )
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        env=_minimal_env(),
    )
    assert result.returncode == 0, f"exit {result.returncode}; stderr: {result.stderr}"
    assert (
        "secrets_qdrant_key" in result.stdout
    ), f"Expected secrets_qdrant_key from .env.secrets in stdout; got: {result.stdout!r}"


def test_setup_github_indexes_dual_source(dual_source_dir):
    """setup_github_indexes subshell sources .env.secrets in addition to .env (W1-F1 fix).

    Extracts the env-loading block from install.sh::setup_github_indexes via sed
    (sed range: set -a through .env.secrets source within the function). Cds to
    docker/ (matching the function's cd) and sets INSTALL_DIR to the fixture
    directory. Asserts QDRANT_API_KEY resolves from .env.secrets.
    """
    install_dir = str(dual_source_dir)
    python = sys.executable
    install_script = str(INSTALL_SCRIPT)

    # Source the env-loading block from setup_github_indexes in the actual install.sh.
    # sed range: from set -a (8-space indent) through .env.secrets source within the function.
    # cd to docker/ first to match the function's CWD (source <(grep -v ... .env) uses relative path).
    cmd = (
        f"INSTALL_DIR={install_dir!r}\n"
        f"cd {install_dir!r}/docker || exit 1\n"
        "source <(sed -n '/^setup_github_indexes/,/^run_initial_github_sync/{\n"
        '    /^        set -a$/,/source "\\$INSTALL_DIR\\/docker\\/.env.secrets"/{\n'
        "        p\n"
        "    }\n"
        f"}}' {install_script!r})\n"
        f"{python} -c \"import os; print(os.environ.get('QDRANT_API_KEY', 'MISSING'))\""
    )
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        env=_minimal_env(),
    )
    assert result.returncode == 0, f"exit {result.returncode}; stderr: {result.stderr}"
    assert (
        "secrets_qdrant_key" in result.stdout
    ), f"Expected secrets_qdrant_key from .env.secrets in stdout; got: {result.stdout!r}"


def test_run_initial_github_sync_dual_source(dual_source_dir):
    """run_initial_github_sync subshell sources .env.secrets in addition to .env (W1-F1 fix).

    Extracts the env-loading block from install.sh::run_initial_github_sync via sed
    (sed range: set -a through docker/.env.secrets source within the function). Cds to
    INSTALL_DIR (matching the function's CWD) and sets INSTALL_DIR to the fixture
    directory. Asserts both GITHUB_TOKEN (PP-1) and QDRANT_API_KEY (PP-2) resolve
    from .env.secrets.
    """
    install_dir = str(dual_source_dir)
    python = sys.executable
    install_script = str(INSTALL_SCRIPT)

    # Source the env-loading block from run_initial_github_sync in the actual install.sh.
    # sed range: from set -a (12-space indent) through docker/.env.secrets source within the function.
    # cd to INSTALL_DIR first (source docker/.env uses relative path from that CWD).
    cmd = (
        f"INSTALL_DIR={install_dir!r}\n"
        f"cd {install_dir!r} || exit 1\n"
        "source <(sed -n '/^run_initial_github_sync/,/^setup_langfuse/{\n"
        "    /^            set -a$/,/source docker\\/\\.env\\.secrets/{\n"
        "        p\n"
        "    }\n"
        f"}}' {install_script!r})\n"
        f'{python} -c "'
        "import os; "
        "qdrant=os.environ.get('QDRANT_API_KEY','MISSING'); "
        "github=os.environ.get('GITHUB_TOKEN','MISSING'); "
        "print(f'qdrant={qdrant} github={github}')"
        '"'
    )
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        env=_minimal_env(),
    )
    assert result.returncode == 0, f"exit {result.returncode}; stderr: {result.stderr}"
    assert (
        "secrets_qdrant_key" in result.stdout
    ), f"QDRANT_API_KEY not resolved from .env.secrets; got: {result.stdout!r}"
    assert (
        "secrets_github_token" in result.stdout
    ), f"GITHUB_TOKEN not resolved from .env.secrets; got: {result.stdout!r}"


# ---------------------------------------------------------------------------
# BUG-309 regression tests — install.sh detection-layer symmetry
# ---------------------------------------------------------------------------
# Pre-BUG-309 fix, install.sh's discover_jira_projects and configure_project_sources
# grepped docker/.env only for credential detection — missing values that legitimately
# live in docker/.env.secrets post-BUG-277 split. The fix substitutes _read_env_key
# (secrets-first fallthrough) for the open-coded grep blocks at both sites.
#
# These tests cover three angles:
#   1. Helper-level: _read_env_key returns the secrets value when both files have
#      the key (precedence ordering — secrets-first).
#   2. Helper-level: _read_env_key returns the secrets value when .env has the key
#      blanked (BUG-309's exact post-BUG-286 state).
#   3. Structural: install.sh's detection blocks reference _read_env_key (catches
#      regression if the substitution is ever reverted).
# ---------------------------------------------------------------------------

HELPERS_SCRIPT = (
    Path(__file__).parent.parent.parent / "scripts" / "_env_split_helpers.sh"
)


@pytest.fixture()
def bug309_split_env_dir(tmp_path):
    """Create a docker/ subdir matching the BUG-309 post-BUG-286 state.

    docker/.env has the secret-class keys BLANKED (KEY= empty values) — the
    BUG-286 defense-in-depth pattern leaves the line behind with an empty value.
    docker/.env.secrets carries the canonical values.

    The brief's R1.5 test request: assert detection reads .env.secrets values
    rather than misinterpreting the blank .env entries as missing credentials.
    """
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    (docker_dir / ".env").write_text(
        "UID=1000\n"
        "GID=1000\n"
        "JIRA_INSTANCE_URL=\n"
        "JIRA_EMAIL=\n"
        "JIRA_API_TOKEN=\n"
        "GITHUB_TOKEN=\n"
        "GITHUB_SYNC_ENABLED=\n"
        "GITHUB_REPO=owner/repo\n"
    )
    (docker_dir / ".env.secrets").write_text(
        'JIRA_INSTANCE_URL="https://example.atlassian.net"\n'
        'JIRA_EMAIL="ops@example.com"\n'
        'JIRA_API_TOKEN="secrets_jira_token"\n'
        'GITHUB_TOKEN="secrets_github_token"\n'
        'GITHUB_SYNC_ENABLED="true"\n'
    )
    return docker_dir


def _invoke_read_env_key(key: str, secrets_file: Path, env_file: Path) -> str:
    """Source _env_split_helpers.sh and invoke _read_env_key; return stdout."""
    cmd = (
        f"source {str(HELPERS_SCRIPT)!r} && "
        f"_read_env_key {key!r} {str(secrets_file)!r} {str(env_file)!r}"
    )
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        env=_minimal_env(),
    )
    assert result.returncode == 0, (
        f"_read_env_key {key!r} returned exit {result.returncode}; "
        f"stderr: {result.stderr}"
    )
    return result.stdout


def test_helper_read_env_key_returns_secrets_first(tmp_path):
    """_read_env_key returns the .env.secrets value when both files have the key.

    Verifies precedence: secrets-first fallthrough. Matches MemoryConfig tuple
    env_file last-file-wins (.env, .env.secrets) and docker-compose --env-file
    last-file-wins, so detection-time UX is aligned with runtime precedence.
    """
    env_file = tmp_path / ".env"
    secrets_file = tmp_path / ".env.secrets"
    env_file.write_text('JIRA_API_TOKEN="env_token_value"\n')
    secrets_file.write_text('JIRA_API_TOKEN="secrets_token_value"\n')

    out = _invoke_read_env_key("JIRA_API_TOKEN", secrets_file, env_file)
    assert (
        out == "secrets_token_value"
    ), f"Expected secrets_token_value (secrets-first precedence); got {out!r}"


def test_jira_detection_reads_from_secrets_when_env_blank(bug309_split_env_dir):
    """discover_jira_projects detection: JIRA_API_TOKEN resolves from .env.secrets.

    BUG-309 reproducer state: docker/.env has JIRA_API_TOKEN= (blanked by
    BUG-286 defense-in-depth), docker/.env.secrets has the real token.
    Pre-fix: install.sh grepped .env only and saw empty value → emitted the
    'Jira credentials not configured -- run fresh install' warning.
    Post-fix: detection uses _read_env_key which falls through to .env.secrets.
    """
    env_file = bug309_split_env_dir / ".env"
    secrets_file = bug309_split_env_dir / ".env.secrets"

    assert _invoke_read_env_key("JIRA_INSTANCE_URL", secrets_file, env_file) == (
        "https://example.atlassian.net"
    )
    assert _invoke_read_env_key("JIRA_EMAIL", secrets_file, env_file) == (
        "ops@example.com"
    )
    assert _invoke_read_env_key("JIRA_API_TOKEN", secrets_file, env_file) == (
        "secrets_jira_token"
    )


def test_github_detection_reads_from_secrets_when_env_blank(bug309_split_env_dir):
    """configure_project_sources detection: GITHUB_TOKEN resolves from .env.secrets.

    BUG-309 reproducer state: docker/.env has GITHUB_TOKEN= (blanked), real
    token in .env.secrets. Pre-fix install.sh grepped .env only → emitted
    'No GITHUB_TOKEN found' warning + skipped per-project token verification.
    Post-fix uses _read_env_key with secrets-first fallthrough.
    """
    env_file = bug309_split_env_dir / ".env"
    secrets_file = bug309_split_env_dir / ".env.secrets"

    assert _invoke_read_env_key("GITHUB_TOKEN", secrets_file, env_file) == (
        "secrets_github_token"
    )
    assert _invoke_read_env_key("GITHUB_SYNC_ENABLED", secrets_file, env_file) == (
        "true"
    )


def test_install_sh_detection_sites_reference_read_env_key():
    """Structural regression: install.sh detection blocks invoke _read_env_key.

    Catches future regression if the open-coded grep '^KEY=' "$env_file" pattern
    is ever reintroduced. We assert:
      1. The defective shape is absent for the BUG-309 keys.
      2. _read_env_key is invoked for each of the 5 keys covered by R1.2 + R1.3.
    """
    install_sh = INSTALL_SCRIPT.read_text()

    # Defective shape MUST NOT appear for BUG-309 keys
    defective_keys = (
        "JIRA_INSTANCE_URL",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "GITHUB_TOKEN",
        "GITHUB_SYNC_ENABLED",
    )
    for key in defective_keys:
        defective = f"grep '^{key}=' \"$env_file\""
        assert defective not in install_sh, (
            f"Regression: defective shape {defective!r} present in install.sh "
            f"(BUG-309 substitution reverted)"
        )

    # _read_env_key MUST be invoked for each BUG-309 key
    for key in defective_keys:
        helper_call = f'_read_env_key "{key}"'
        assert (
            helper_call in install_sh
        ), f"Regression: install.sh missing _read_env_key invocation for {key!r}"
