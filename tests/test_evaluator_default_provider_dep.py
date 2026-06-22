# LANGFUSE: not used in this module. See LANGFUSE-INTEGRATION-SPEC.md
"""Smoke test: the evaluator default-provider SDK is installed in the image.

BUG-316 — the evaluator-scheduler image installs only requirements.txt. The
shipped default provider (ollama) builds its client via `from openai import
OpenAI` (evaluator/provider.py), so the ``openai`` package must be present in
the image; otherwise every evaluation fails with ``No module named 'openai'``
and the scheduler reports ``scored: 0`` while still reporting a "complete" run.

These tests exercise the real import + client-construction path used by
``provider.get_client()`` for the configured default provider — no mocks — so a
missing dependency fails the build instead of silently zeroing scores at
runtime.
"""

import re
from pathlib import Path

import yaml

from memory.evaluator.provider import EvaluatorConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "evaluator_config.yaml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
LANGFUSE_COMPOSE = REPO_ROOT / "docker" / "docker-compose.langfuse.yml"


def test_requirements_txt_declares_provider_sdks():
    """requirements.txt — the image-bake source-of-truth — pins openai + anthropic.

    The evaluator-scheduler image installs ONLY requirements.txt (not the
    pyproject [dev]/observability extras), so the import smoke tests above pass
    in the CI .[dev] venv even if a provider SDK is dropped from requirements.txt
    — the exact BUG-316 regression. This static assertion locks the image
    source-of-truth: removing the openai (or anthropic) line from
    requirements.txt fails here regardless of what the [dev] venv has installed.
    """
    text = REQUIREMENTS.read_text()
    assert re.search(
        r"(?m)^openai[>=<]", text
    ), "openai must be declared in requirements.txt (evaluator image SDK, BUG-316)"
    assert re.search(
        r"(?m)^anthropic[>=<]", text
    ), "anthropic must be declared in requirements.txt (conversation-capture SDK)"


def test_openai_sdk_importable():
    """The openai SDK (used by the default ollama provider path) is installed."""
    from openai import OpenAI  # noqa: F401


def test_shipped_default_provider_is_ollama():
    """The image-mounted evaluator_config.yaml selects the ollama provider."""
    config = EvaluatorConfig.from_yaml(str(DEFAULT_CONFIG))
    # If this fails after a config change, verify the new default provider's SDK
    # is declared in requirements.txt + pyproject [dev] (links back to BUG-316).
    assert config.provider == "ollama"


def test_default_provider_client_builds_without_mock():
    """The shipped default config builds a real client via the openai SDK.

    Exercises provider.get_client()'s actual import + client construction for
    the configured default provider. The ollama path constructs the client
    without a network call, so this verifies the SDK is importable and the
    client type is correct end to end.
    """
    from openai import OpenAI

    config = EvaluatorConfig.from_yaml(str(DEFAULT_CONFIG))
    client = config.get_client()
    assert isinstance(client, OpenAI)


def test_evaluator_scheduler_env_has_install_dir():
    """evaluator-scheduler must declare AI_MEMORY_INSTALL_DIR=/app (TD-712).

    Running as uid 1000 sets HOME=/ inside the container; MemoryConfig then
    rejects install_dir='/.ai-memory' and the service crash-loops.  Mirroring
    the trace-flush-worker pattern, AI_MEMORY_INSTALL_DIR=/app must be in the
    evaluator-scheduler environment block so the config path resolves to /app.
    """
    compose = yaml.safe_load(LANGFUSE_COMPOSE.read_text())
    env_list = compose["services"]["evaluator-scheduler"]["environment"]
    # env_list is a list of "KEY=VALUE" strings
    env_vars = {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in env_list
        if isinstance(item, str) and "=" in item
    }
    assert env_vars.get("AI_MEMORY_INSTALL_DIR") == "/app", (
        "evaluator-scheduler environment must contain AI_MEMORY_INSTALL_DIR=/app "
        "(TD-712: uid 1000 run sets HOME=/ → MemoryConfig crash)"
    )
