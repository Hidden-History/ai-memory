"""Unit tests for classifier provider model defaults — T4 and T5.

Covers T4-T5 per Wave 2 dispatch brief §4 (BP-156 §7 test design):
  T4: OPENROUTER_MODEL default not retired (config.py + .env.example parity)
  T5: ANTHROPIC_MODEL default not retired (config.py + .env.example parity)

File-content assertions only — no network calls, CI-stable.
Uses re.search with re.DOTALL for config.py checks (formatter-agnostic).
BUG-290 Factor #1 (OpenRouter retired model) and BUG-295 (Anthropic retired model).
"""

import re
from pathlib import Path

# Resolve project root two levels above tests/test_classifier/
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CONFIG_PY = _PROJECT_ROOT / "src" / "memory" / "classifier" / "config.py"
_ENV_EXAMPLE = _PROJECT_ROOT / "docker" / ".env.example"

_EXPECTED_OPENROUTER_MODEL = "meta-llama/llama-3.2-3b-instruct:free"
_RETIRED_OPENROUTER_MODEL = "google/gemma-2-9b-it:free"

_EXPECTED_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
# All retired Anthropic defaults (both pre- and post-escalation)
_RETIRED_ANTHROPIC_MODELS = [
    "claude-3-haiku-20240307",
    "claude-3-5-haiku-20241022",
]


def _config_openrouter_default(config_text: str) -> str | None:
    """Extract the hardcoded default from os.getenv("OPENROUTER_MODEL", <default>).

    Handles both single-line and black-wrapped multi-line forms.
    """
    match = re.search(
        r'os\.getenv\s*\(\s*"OPENROUTER_MODEL"\s*,\s*"([^"]+)"\s*\)',
        config_text,
        re.DOTALL,
    )
    return match.group(1) if match else None


def _config_anthropic_default(config_text: str) -> str | None:
    """Extract the hardcoded default from os.getenv("ANTHROPIC_MODEL", <default>)."""
    match = re.search(
        r'os\.getenv\s*\(\s*"ANTHROPIC_MODEL"\s*,\s*"([^"]+)"\s*\)',
        config_text,
        re.DOTALL,
    )
    return match.group(1) if match else None


class TestOpenRouterModelDefault:
    """T4 — OPENROUTER_MODEL default is not a retired model (BP-156 §7 T4)."""

    def test_openrouter_model_default_not_retired_in_config_py(self):
        """config.py OPENROUTER_MODEL default == meta-llama/llama-3.2-3b-instruct:free."""
        config_text = _CONFIG_PY.read_text()
        default = _config_openrouter_default(config_text)
        assert (
            default is not None
        ), 'config.py: os.getenv("OPENROUTER_MODEL", ...) call not found'
        assert default == _EXPECTED_OPENROUTER_MODEL, (
            f"config.py OPENROUTER_MODEL default must be '{_EXPECTED_OPENROUTER_MODEL}', "
            f"got '{default}'"
        )

    def test_openrouter_model_default_not_retired_in_env_example(self):
        """.env.example OPENROUTER_MODEL= line == meta-llama/llama-3.2-3b-instruct:free."""
        env_text = _ENV_EXAMPLE.read_text()
        expected_line = f"OPENROUTER_MODEL={_EXPECTED_OPENROUTER_MODEL}"
        assert expected_line in env_text, (
            f".env.example must contain '{expected_line}'. "
            f"Retired or missing OPENROUTER_MODEL default detected."
        )

    def test_openrouter_model_retired_default_absent_from_config_py(self):
        """config.py must not default to the retired google/gemma-2-9b-it:free model."""
        config_text = _CONFIG_PY.read_text()
        default = _config_openrouter_default(config_text)
        assert default != _RETIRED_OPENROUTER_MODEL, (
            f"config.py still defaults to retired OPENROUTER_MODEL: "
            f"{_RETIRED_OPENROUTER_MODEL!r}"
        )

    def test_openrouter_model_env_example_matches_config_py_default(self):
        """OPENROUTER_MODEL value in .env.example matches config.py hardcoded default."""
        config_text = _CONFIG_PY.read_text()
        env_text = _ENV_EXAMPLE.read_text()

        config_default = _config_openrouter_default(config_text)
        assert config_default == _EXPECTED_OPENROUTER_MODEL

        env_line = f"OPENROUTER_MODEL={_EXPECTED_OPENROUTER_MODEL}"
        assert env_line in env_text


class TestAnthropicModelDefault:
    """T5 — ANTHROPIC_MODEL default is not a retired model (BP-156 §7 T5)."""

    def test_anthropic_model_default_not_retired_in_config_py(self):
        """config.py ANTHROPIC_MODEL default == claude-haiku-4-5-20251001."""
        config_text = _CONFIG_PY.read_text()
        default = _config_anthropic_default(config_text)
        assert (
            default is not None
        ), 'config.py: os.getenv("ANTHROPIC_MODEL", ...) call not found'
        assert default == _EXPECTED_ANTHROPIC_MODEL, (
            f"config.py ANTHROPIC_MODEL default must be '{_EXPECTED_ANTHROPIC_MODEL}', "
            f"got '{default}'"
        )

    def test_anthropic_model_default_not_retired_in_env_example(self):
        """.env.example ANTHROPIC_MODEL= line == claude-haiku-4-5-20251001."""
        env_text = _ENV_EXAMPLE.read_text()
        expected_line = f"ANTHROPIC_MODEL={_EXPECTED_ANTHROPIC_MODEL}"
        assert expected_line in env_text, (
            f".env.example must contain '{expected_line}'. "
            f"Retired or missing ANTHROPIC_MODEL default detected."
        )

    def test_anthropic_model_retired_defaults_absent_from_config_py(self):
        """config.py must not default to any retired Anthropic model."""
        config_text = _CONFIG_PY.read_text()
        default = _config_anthropic_default(config_text)
        for retired in _RETIRED_ANTHROPIC_MODELS:
            assert (
                default != retired
            ), f"config.py still defaults to retired ANTHROPIC_MODEL: {retired!r}"

    def test_anthropic_model_env_example_matches_config_py_default(self):
        """ANTHROPIC_MODEL value in .env.example matches config.py hardcoded default."""
        config_text = _CONFIG_PY.read_text()
        env_text = _ENV_EXAMPLE.read_text()

        config_default = _config_anthropic_default(config_text)
        assert config_default == _EXPECTED_ANTHROPIC_MODEL

        env_line = f"ANTHROPIC_MODEL={_EXPECTED_ANTHROPIC_MODEL}"
        assert env_line in env_text
