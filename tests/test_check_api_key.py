"""Companion test for scripts/lib/check_api_key.sh (BP-016 conformant).

Consolidates the 5 byte-identical inline API-key-check forms from:
  api-dispatch/steps/audio-generate/step-04-execute.md
  api-dispatch/steps/audio-process/step-03-execute.md
  api-dispatch/steps/image-analyze/step-03-execute.md
  api-dispatch/steps/image-generate/step-04-execute.md
  api-dispatch/steps/video-generate/step-04-execute.md

Parity rule (work-order §12 + wb locked rule):
  - The 5 forms echo "Error: No ... API key…" to stdout; the helper does the same.
  - Net-new arg/usage errors (no inline equivalent) route to stderr.
Harness: stdlib subprocess.run only (no pytest-shell-utilities).

Calling convention:
  Sourced:  source check_api_key.sh; check_api_key --provider <name>
  Executed: bash check_api_key.sh --provider <name>
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "_ai-memory/pov/skills/aim-model-dispatch/scripts/lib"
)


def _minimal_env(home_dir: Path, extra: dict | None = None) -> dict:
    """Explicit minimal env: HOME + LC_ALL=C + PATH, plus any test-specific vars.

    Never inherits os.environ wholesale (BP-016 anti-flake rule).
    PATH is read from the real environment so bash + system tools resolve.
    """
    env: dict = {
        "HOME": str(home_dir),
        "LC_ALL": "C",
        "PATH": os.environ["PATH"],
    }
    if extra:
        env.update(extra)
    return env


# ---------------------------------------------------------------------------
# Success cases — key available; env var carries the expected value.
# Tested via source+function-call to verify the env-var side-effect.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra_env,write_token,expected_val",
    [
        pytest.param(
            {"OPENROUTER_API_KEY": "envval"},
            None,
            "envval",
            id="key-in-env",
        ),
        pytest.param({}, "filekey", "filekey", id="token-file"),
        pytest.param({}, "", "", id="token-file-empty"),
    ],
)
def test_key_loaded(
    tmp_path: Path,
    extra_env: dict,
    write_token: str | None,
    expected_val: str,
) -> None:
    """Exit 0; env var carries expected value; stdout == expected_val; stderr empty."""
    if write_token is not None:
        (tmp_path / ".openrouter-token").write_text(write_token)
    helper = SCRIPTS_DIR / "check_api_key.sh"
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{helper}"; check_api_key --provider openrouter; '
            f'printf "%s" "$OPENROUTER_API_KEY"',
        ],
        env=_minimal_env(tmp_path, extra_env),
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == expected_val
    assert result.stderr == ""


# ---------------------------------------------------------------------------
# Inline-parity failure (executed path) — key absent; echoes error to stdout
# matching the 5 inline forms byte-for-byte; exits 1.
# ---------------------------------------------------------------------------


def test_no_key_exits_1(tmp_path: Path) -> None:
    """Exit 1; inline error on stdout (parity with 5 inline forms); stderr empty."""
    helper = SCRIPTS_DIR / "check_api_key.sh"
    result = subprocess.run(
        ["bash", str(helper), "--provider", "openrouter"],
        env=_minimal_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "No OpenRouter API key" in result.stdout
    assert "model-dispatch install" in result.stdout
    assert result.stderr == ""


# ---------------------------------------------------------------------------
# Inline-parity failure (sourced path) — key absent; function returns non-zero
# WITHOUT terminating the surrounding shell; error still echoes to stdout.
# This is the dual-use safety test: exit vs return behaviour.
# ---------------------------------------------------------------------------


def test_sourced_no_key_survives(tmp_path: Path) -> None:
    """Sourced key-not-found: function returns non-zero; shell survives; error on stdout."""
    helper = SCRIPTS_DIR / "check_api_key.sh"
    # Capture the function's return code; continue running to prove shell is alive.
    script = (
        f'source "{helper}"; '
        f"check_api_key --provider openrouter; "
        f'rc=$?; echo "ALIVE:$rc"'
    )
    result = subprocess.run(
        ["bash", "-c", script],
        env=_minimal_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    # Outer shell survives: exits 0 (last command is echo).
    assert result.returncode == 0
    # Function signalled failure.
    assert "ALIVE:1" in result.stdout
    # Inline error message was echoed to stdout.
    assert "No OpenRouter API key" in result.stdout
    assert result.stderr == ""


# ---------------------------------------------------------------------------
# Net-new arg/usage errors — introduced by the --provider interface (no
# inline-form equivalent); route to stderr; stdout must be empty; exit 2.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args,expected_stderr_fragment",
    [
        pytest.param([], "--provider required", id="missing-provider"),
        pytest.param(["--provider"], "--provider requires a value", id="missing-value"),
    ],
)
def test_usage_error_exits_2(
    tmp_path: Path,
    args: list,
    expected_stderr_fragment: str,
) -> None:
    """Exit 2; net-new usage diagnostic on stderr; stdout empty."""
    helper = SCRIPTS_DIR / "check_api_key.sh"
    result = subprocess.run(
        ["bash", str(helper), *args],
        env=_minimal_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert expected_stderr_fragment in result.stderr
