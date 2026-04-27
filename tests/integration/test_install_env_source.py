"""Regression tests for install.sh env sourcing pattern (BUG-273).

Exercises the `source <(grep -v -E '^(UID|GID)=' .env)` fix at the two
code sites in setup_github_indexes() and run_initial_github_sync().

No external services required — shells out to bash only.
"""

import os
import subprocess
import sys

import pytest

ENV_CONTENT = """\
UID=1000
GID=1000
QDRANT_API_KEY=testkey123
GITHUB_TOKEN=ghp_test
GITHUB_REPO=owner/repo
MARKER_VAR=hello
"""


@pytest.fixture()
def env_file(tmp_path):
    """Write a temp .env file with the same shape as docker/.env.example (BUG-273 scenario)."""
    p = tmp_path / ".env"
    p.write_text(ENV_CONTENT)
    return str(p)


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
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}; stderr: {result.stderr.decode()}"
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
