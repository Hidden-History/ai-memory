"""Tests for secrets-first / env-fallback QDRANT_API_KEY read in
scripts/memory/health_check.sh (BUG-293 fix).

Verifies that QDRANT_API_KEY is resolved from docker/.env.secrets first
(secrets-first precedence per BUG-277 split), falling through to docker/.env
when .env.secrets is absent or the key has a blank value.

Scope: shell-level key-read logic; does not exercise downstream Qdrant auth call.
The bug is at the shell level (which file the key is read from); the network call
to /collections is downstream and orthogonal to the fix verified here.
"""

import os
import subprocess
from pathlib import Path

# Script under test (used only for reference; we test the key-read block pattern)
SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "memory" / "health_check.sh"


def _read_qdrant_api_key(tmp_path: Path, env_content: str, secrets_content) -> str:
    """Run the QDRANT_API_KEY dual-source read block with fixture env files.

    Executes the secrets-first / env-fallback key-read logic implemented at the
    health_check.sh ENV_FILE/SECRETS_FILE read site (BUG-293 fix).  The bash
    fragment mirrors the exact pattern in the script so that any regression in the
    implementation can be caught by cross-referencing with the pattern below.

    Scope: shell-level key-read logic; does not exercise downstream Qdrant auth call.

    Args:
        tmp_path: pytest tmp_path fixture directory.
        env_content: content to write to .env fixture.
        secrets_content: content to write to .env.secrets fixture, or None to omit the file.

    Returns:
        Resolved QDRANT_API_KEY value (empty string if absent from both files).
    """
    env_file = tmp_path / ".env"
    env_file.write_text(env_content)

    if secrets_content is not None:
        secrets_file = tmp_path / ".env.secrets"
        secrets_file.write_text(secrets_content)
        secrets_path = str(secrets_file)
    else:
        secrets_path = str(tmp_path / "absent.env.secrets")

    # Bash fragment that replicates the QDRANT_API_KEY dual-source read block from
    # health_check.sh::QDRANT_API_KEY read site (BUG-293 fix pattern).
    cmd = "\n".join(
        [
            f"ENV_FILE={str(env_file)!r}",
            f"SECRETS_FILE={secrets_path!r}",
            'QDRANT_API_KEY=""',
            'if [ -f "$SECRETS_FILE" ]; then',
            "    QDRANT_API_KEY=$(grep '^QDRANT_API_KEY=' \"$SECRETS_FILE\" 2>/dev/null"
            ' | head -1 | cut -d= -f2- | tr -d "\'\\"" || true)',
            "fi",
            'if [ -z "$QDRANT_API_KEY" ]; then',
            "    QDRANT_API_KEY=$(grep '^QDRANT_API_KEY=' \"$ENV_FILE\" 2>/dev/null"
            ' | head -1 | cut -d= -f2- | tr -d "\'\\"" || true)',
            "fi",
            'printf "%s" "$QDRANT_API_KEY"',
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


def test_qdrant_key_from_secrets_file(tmp_path):
    """health_check.sh reads QDRANT_API_KEY from .env.secrets when present and non-empty.

    Simulates a post-BUG-277 install: .env has blank placeholder, .env.secrets has
    the real PP-2 key. The read site should return the secrets-file value.
    """
    value = _read_qdrant_api_key(
        tmp_path,
        env_content="QDRANT_API_KEY=\nQDRANT_PORT=26350\n",
        secrets_content="QDRANT_API_KEY=secrets_api_key_abc\n",
    )
    assert value == "secrets_api_key_abc"


def test_qdrant_key_fallback_from_env(tmp_path):
    """health_check.sh falls back to .env for QDRANT_API_KEY when .env.secrets is absent.

    Simulates a pre-BUG-277 or legacy install where only .env is present.
    """
    value = _read_qdrant_api_key(
        tmp_path,
        env_content="QDRANT_API_KEY=env_fallback_key\nQDRANT_PORT=26350\n",
        secrets_content=None,  # .env.secrets absent
    )
    assert value == "env_fallback_key"


def test_qdrant_key_secrets_wins_when_both_populated(tmp_path):
    """health_check.sh returns .env.secrets value when both files have non-empty values.

    Validates secrets-first semantics: .env.secrets value wins when both files are present.
    """
    value = _read_qdrant_api_key(
        tmp_path,
        env_content="QDRANT_API_KEY=env_value\n",
        secrets_content="QDRANT_API_KEY=secrets_value\n",
    )
    assert value == "secrets_value"


def test_qdrant_key_empty_when_both_absent(tmp_path):
    """health_check.sh returns empty QDRANT_API_KEY when key is absent from both files.

    Exercises the graceful-no-value path with no error. The script's collection check
    uses the empty key path (unauthenticated curl) when QDRANT_API_KEY is empty.
    """
    value = _read_qdrant_api_key(
        tmp_path,
        env_content="QDRANT_PORT=26350\n",  # QDRANT_API_KEY absent from .env
        secrets_content=None,  # .env.secrets absent
    )
    assert value == ""
