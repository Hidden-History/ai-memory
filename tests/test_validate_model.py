"""Companion test for scripts/lib/validate_model.sh.

Consolidates the 2 byte-identical pre-spawn model-validation blocks from:
  - workflows/bmad-dispatch/steps/step-02-launch-and-activate.md §0b
  - workflows/tmux-dispatch/steps/step-02-launch-pane.md §0b

Exit codes under test:
  0  validation passed, skipped (empty model / gemini backend), or no catalog (WARN)
  1  catalog file missing from disk, or model not found in catalog
  2  usage error (missing required arg)
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "_ai-memory/pov/skills/aim-model-dispatch/scripts/lib"
)

FAKE_MODEL = "test-model-xyz"
_BASE_ENV = {"PATH": os.environ["PATH"], "LC_ALL": "C"}


def _run(scripts_dir: Path, args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(scripts_dir / "validate_model.sh"), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=_BASE_ENV,
    )


@pytest.fixture()
def skill_dir_with_ollama_catalog(tmp_path: Path) -> Path:
    """Fake skill dir with an ollama catalog containing FAKE_MODEL."""
    refs = tmp_path / "references"
    refs.mkdir()
    (refs / "models-ollama.md").write_text(f"| `{FAKE_MODEL}` | test model |\n")
    return tmp_path


def test_known_model_passes(
    skill_dir_with_ollama_catalog: Path,
) -> None:
    """Known model in ollama catalog -> exit 0, stdout contains OK:, stderr empty."""
    result = _run(
        SCRIPTS_DIR,
        [
            "--model",
            FAKE_MODEL,
            "--backend",
            "ollama",
            "--skill-dir",
            str(skill_dir_with_ollama_catalog),
        ],
        skill_dir_with_ollama_catalog,
    )
    assert result.returncode == 0
    assert "OK:" in result.stdout
    assert result.stderr == ""


def test_unknown_model_fails(
    skill_dir_with_ollama_catalog: Path,
) -> None:
    """Model absent from catalog -> exit 1, FAIL: model on stdout, stderr empty."""
    result = _run(
        SCRIPTS_DIR,
        [
            "--model",
            "bogus-model-zzz",
            "--backend",
            "ollama",
            "--skill-dir",
            str(skill_dir_with_ollama_catalog),
        ],
        skill_dir_with_ollama_catalog,
    )
    assert result.returncode == 1
    assert "FAIL: model" in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    "model,backend",
    [
        ("", "ollama"),  # empty model -> outer guard skips
        (FAKE_MODEL, "gemini"),  # gemini backend -> outer guard skips
    ],
)
def test_validation_skipped(tmp_path: Path, model: str, backend: str) -> None:
    """Empty model or gemini backend -> exit 0, stdout empty, stderr empty."""
    result = _run(
        SCRIPTS_DIR,
        ["--model", model, "--backend", backend, "--skill-dir", str(tmp_path)],
        tmp_path,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_unknown_backend_warns(tmp_path: Path) -> None:
    """Backend with no catalog (e.g. claude) -> exit 0, WARN: on stdout, stderr empty."""
    result = _run(
        SCRIPTS_DIR,
        ["--model", FAKE_MODEL, "--backend", "claude", "--skill-dir", str(tmp_path)],
        tmp_path,
    )
    assert result.returncode == 0
    assert "WARN:" in result.stdout
    assert result.stderr == ""


def test_missing_catalog_fails(tmp_path: Path) -> None:
    """Catalog expected (ollama) but file absent -> exit 1, FAIL: catalog file on stdout, stderr empty."""
    result = _run(
        SCRIPTS_DIR,
        ["--model", FAKE_MODEL, "--backend", "ollama", "--skill-dir", str(tmp_path)],
        tmp_path,
    )
    assert result.returncode == 1
    assert "FAIL: catalog file" in result.stdout
    assert result.stderr == ""
