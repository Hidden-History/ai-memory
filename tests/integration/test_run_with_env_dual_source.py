"""Tests for secrets-first / env-fallback dual-source pattern in
scripts/memory/run-with-env.sh::load_env_var (BUG-292 fix).

Verifies that PP-2/PP-1 secret-class keys (QDRANT_API_KEY, GITHUB_TOKEN) are read
from docker/.env.secrets first (secrets-first precedence per BUG-277 split), falling
through to docker/.env when .env.secrets is absent or the key has a blank value.

Implementation: extracts load_env_var from the actual script via process substitution
so tests exercise the real function body rather than a reimplementation.
"""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "memory" / "run-with-env.sh"


def _invoke_load_env_var(
    tmp_path: Path, key: str, env_content: str, secrets_content
) -> str:
    """Source load_env_var from run-with-env.sh and invoke it with fixture env files.

    Creates .env (always) and optionally .env.secrets (when secrets_content is not None)
    in tmp_path, sets ENV_FILE and SECRETS_FILE to those paths, sources the function from
    the real script via process substitution, and returns the exported value for key
    (empty string if the key was not set by load_env_var).

    Args:
        tmp_path: pytest tmp_path fixture directory.
        key: env var key to look up (e.g. "QDRANT_API_KEY").
        env_content: content to write to .env fixture.
        secrets_content: content to write to .env.secrets fixture, or None to omit the file.

    Returns:
        The exported value string (empty string when key is absent from both files).
    """
    env_file = tmp_path / ".env"
    env_file.write_text(env_content)

    if secrets_content is not None:
        secrets_file = tmp_path / ".env.secrets"
        secrets_file.write_text(secrets_content)
        secrets_path = str(secrets_file)
    else:
        # Point to a path that does not exist so the file-exists check fails cleanly
        secrets_path = str(tmp_path / "absent.env.secrets")

    # Source just the load_env_var function body from the real script via process
    # substitution.  sed extracts lines from the 'load_env_var()' definition through
    # the first unindented closing brace, which is the function's closing '}'.
    cmd = "\n".join(
        [
            "set -uo pipefail",
            f"ENV_FILE={str(env_file)!r}",
            f"SECRETS_FILE={secrets_path!r}",
            f"source <(sed -n '/^load_env_var/,/^}}/p' {str(SCRIPT)!r})",
            f"load_env_var {key!r}",
            f'printf "%s" "${{{key}:-}}"',
        ]
    )
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    assert (
        result.returncode == 0
    ), f"bash exited {result.returncode}; stderr={result.stderr!r}; stdout={result.stdout!r}"
    return result.stdout


def test_secrets_file_wins(tmp_path):
    """load_env_var returns the .env.secrets value when key is populated there.

    Simulates a post-BUG-277 install layout: .env has a blank placeholder for
    QDRANT_API_KEY (PP-2), while .env.secrets holds the real value. load_env_var
    should return the secrets-file value (secrets-first precedence).
    """
    value = _invoke_load_env_var(
        tmp_path,
        key="QDRANT_API_KEY",
        env_content="QDRANT_API_KEY=\nGITHUB_TOKEN=\n",
        secrets_content="QDRANT_API_KEY=real_secret_key_123\nGITHUB_TOKEN=ghp_real_token\n",
    )
    assert value == "real_secret_key_123"


def test_env_fallback_when_secrets_blank(tmp_path):
    """load_env_var falls back to .env when the .env.secrets entry is blank.

    Exercises the blank-value fallthrough: .env.secrets has the key but the value
    is empty, so load_env_var falls through to .env and picks up the value there.
    """
    value = _invoke_load_env_var(
        tmp_path,
        key="QDRANT_API_KEY",
        env_content="QDRANT_API_KEY=legacy_key_456\n",
        secrets_content="QDRANT_API_KEY=\n",
    )
    assert value == "legacy_key_456"


def test_secrets_file_precedence_over_env(tmp_path):
    """load_env_var returns .env.secrets value when both files have different non-empty values.

    Validates secrets-first semantics: when both files have a non-empty value for the
    same key, .env.secrets wins regardless of .env content.
    """
    value = _invoke_load_env_var(
        tmp_path,
        key="GITHUB_TOKEN",
        env_content="GITHUB_TOKEN=old_env_token\n",
        secrets_content="GITHUB_TOKEN=new_secrets_token\n",
    )
    assert value == "new_secrets_token"


def test_env_fallback_when_secrets_missing(tmp_path):
    """load_env_var falls back to .env cleanly when .env.secrets does not exist.

    Simulates a pre-BUG-277 install where .env.secrets has not been created yet,
    or an operator environment where only .env is present.
    """
    value = _invoke_load_env_var(
        tmp_path,
        key="QDRANT_API_KEY",
        env_content="QDRANT_API_KEY=only_in_env_file\n",
        secrets_content=None,  # .env.secrets absent
    )
    assert value == "only_in_env_file"


def test_both_missing_returns_empty(tmp_path):
    """load_env_var returns empty string without error when key is absent from both files.

    Exercises the graceful-no-value path: the key does not appear in either file.
    load_env_var should complete without error and export nothing (empty value).
    """
    value = _invoke_load_env_var(
        tmp_path,
        key="QDRANT_API_KEY",
        env_content="OTHER_KEY=other_value\n",
        secrets_content=None,  # .env.secrets absent; QDRANT_API_KEY also absent from .env
    )
    assert value == ""
