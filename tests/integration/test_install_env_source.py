"""Regression tests for install.sh env sourcing patterns.

BUG-273 tests: verify the `source <(grep -v -E '^(UID|GID)=' .env)` fix at the two
code sites in setup_github_indexes() and run_initial_github_sync().

W1-F1 tests (defense-in-depth): verify that setup_github_indexes, run_initial_github_sync,
and drain_pending_queue source docker/.env.secrets in addition to docker/.env, matching
the setup_collections dual-source pattern (BUG-292 fix).

No external services required — shells out to bash only.
"""

import os
import subprocess
import sys

import pytest

ENV_CONTENT = """\
UID=1000
GID=1000
QDRANT_API_KEY=
GITHUB_TOKEN=
GITHUB_REPO=owner/repo
MARKER_VAR=hello
"""

# Value that lives in .env.secrets post-BUG-277 (blank in .env)
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
    (docker_dir / ".env").write_text(ENV_CONTENT)
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
# ---------------------------------------------------------------------------


def test_setup_github_indexes_dual_source(dual_source_dir):
    """setup_github_indexes subshell sources .env.secrets in addition to .env (W1-F1 fix).

    Runs the dual-source env-loading block from setup_github_indexes with fixture
    files where .env has a blank QDRANT_API_KEY and .env.secrets has the real value.
    Asserts the secret value is visible inside the subshell.
    """
    install_dir = str(dual_source_dir)
    python = sys.executable

    # Replicate the dual-source block from install.sh::setup_github_indexes after W1-F1 fix:
    # cd docker/ → set -a → source .env (UID/GID filtered) → source .env.secrets → python
    cmd = (
        f"cd {install_dir!r}/docker || exit 1\n"
        f"set -a\n"
        f"source <(grep -v -E '^(UID|GID)=' .env)\n"
        f"[ -f {install_dir!r}/docker/.env.secrets ] && source {install_dir!r}/docker/.env.secrets\n"
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

    Runs the dual-source env-loading block from run_initial_github_sync with fixture
    files where .env has blank PP-1/PP-2 keys and .env.secrets has real values.
    Asserts both GITHUB_TOKEN (PP-1) and QDRANT_API_KEY (PP-2) are visible in the subshell.
    """
    install_dir = str(dual_source_dir)
    python = sys.executable

    # Replicate the dual-source block from install.sh::run_initial_github_sync after W1-F1 fix:
    # cd $INSTALL_DIR → set -a → source docker/.env (UID/GID filtered) → source docker/.env.secrets → python
    cmd = (
        f"cd {install_dir!r} || exit 1\n"
        f"set -a\n"
        f"source <(grep -v -E '^(UID|GID)=' docker/.env)\n"
        f"[ -f docker/.env.secrets ] && source docker/.env.secrets\n"
        f'{python} -c "'
        f"import os; "
        f"qdrant=os.environ.get('QDRANT_API_KEY','MISSING'); "
        f"github=os.environ.get('GITHUB_TOKEN','MISSING'); "
        f"print(f'qdrant={{qdrant}} github={{github}}')"
        f'"'
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


def test_drain_pending_queue_dual_source(dual_source_dir):
    """drain_pending_queue subshell sources .env.secrets in addition to .env (W1-F1 fix).

    Runs the dual-source env-loading block from drain_pending_queue with fixture
    files where .env has a blank QDRANT_API_KEY and .env.secrets has the real value.
    Asserts the secret value is visible inside the subshell (defense-in-depth: current
    consumer process_retry_queue.py uses MemoryStorage/MemoryConfig, but the pattern
    alignment ensures future direct env reads will also work correctly).
    """
    install_dir = str(dual_source_dir)
    python = sys.executable

    # Replicate the dual-source block from install.sh::drain_pending_queue after W1-F1 fix:
    # set -a → source .env (UID/GID filtered) → source .env.secrets → python
    cmd = (
        f"set -a\n"
        f"[ -f {install_dir!r}/docker/.env ] && "
        f"source <(grep -v -E '^(UID|GID)=' {install_dir!r}/docker/.env)\n"
        f"[ -f {install_dir!r}/docker/.env.secrets ] && "
        f"source {install_dir!r}/docker/.env.secrets\n"
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
