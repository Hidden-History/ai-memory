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

from pathlib import Path

from memory.evaluator.provider import EvaluatorConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "evaluator_config.yaml"


def test_openai_sdk_importable():
    """The openai SDK (used by the default ollama provider path) is installed."""
    from openai import OpenAI  # noqa: F401


def test_shipped_default_provider_is_ollama():
    """The image-mounted evaluator_config.yaml selects the ollama provider."""
    config = EvaluatorConfig.from_yaml(str(DEFAULT_CONFIG))
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
