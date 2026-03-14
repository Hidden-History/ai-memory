# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
"""Tests for evaluator configuration — YAML loading, validation, and defaults.

Tests that evaluator_config.yaml loads correctly, that defaults are applied,
and that the config contains zero secrets.

PLAN-012 Phase 2 — AC-8
"""

from pathlib import Path

import pytest
import yaml

from memory.evaluator.provider import EvaluatorConfig
from memory.evaluator.runner import EvaluatorRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def full_config_yaml(tmp_path) -> Path:
    """A complete evaluator_config.yaml for testing."""
    config = {
        "evaluator_model": {
            "provider": "ollama",
            "model_name": "llama3.2:8b",
            "temperature": 0.0,
            "max_tokens": 512,
        },
        "evaluators_dir": str(tmp_path / "evaluators"),
        "schedule": {
            "enabled": True,
            "cron": "0 5 * * *",
            "lookback_hours": 24,
        },
        "thresholds": {
            "retrieval_relevance": 0.7,
            "injection_value": 0.6,
            "capture_completeness": 0.9,
            "classification_accuracy": 0.8,
            "bootstrap_quality": 0.7,
            "session_coherence": 0.7,
        },
        "datasets": {
            "retrieval_golden_set": 20,
            "error_pattern_match": 10,
            "bootstrap_round_trip": 5,
            "keyword_trigger_routing": 63,
            "chunking_quality": 10,
        },
        "audit": {
            "log_file": str(tmp_path / ".audit" / "evaluations.jsonl"),
            "log_level": "INFO",
        },
    }
    (tmp_path / "evaluators").mkdir()
    config_file = tmp_path / "evaluator_config.yaml"
    config_file.write_text(yaml.dump(config))
    return config_file


# ---------------------------------------------------------------------------
# Tests: YAML loading
# ---------------------------------------------------------------------------


class TestYAMLLoading:
    def test_loads_provider(self, full_config_yaml):
        config = EvaluatorConfig.from_yaml(str(full_config_yaml))
        assert config.provider == "ollama"

    def test_loads_model_name(self, full_config_yaml):
        config = EvaluatorConfig.from_yaml(str(full_config_yaml))
        assert config.model_name == "llama3.2:8b"

    def test_loads_temperature(self, full_config_yaml):
        config = EvaluatorConfig.from_yaml(str(full_config_yaml))
        assert config.temperature == 0.0

    def test_loads_max_tokens(self, full_config_yaml):
        config = EvaluatorConfig.from_yaml(str(full_config_yaml))
        assert config.max_tokens == 512

    def test_runner_loads_evaluators_dir(self, full_config_yaml):
        runner = EvaluatorRunner(config_path=str(full_config_yaml))
        assert runner.evaluators_dir.exists() or str(runner.evaluators_dir).endswith(
            "evaluators"
        )

    def test_runner_loads_audit_log_path(self, full_config_yaml, tmp_path):
        runner = EvaluatorRunner(config_path=str(full_config_yaml))
        assert "evaluations.jsonl" in str(runner.audit_log_path)

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            EvaluatorConfig.from_yaml(str(tmp_path / "nonexistent.yaml"))


class TestDefaults:
    """Test that missing fields use correct defaults."""

    def test_provider_defaults_to_ollama(self, tmp_path):
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text("evaluator_model: {}\n")
        config = EvaluatorConfig.from_yaml(str(config_file))
        assert config.provider == "ollama"

    def test_model_defaults_to_llama(self, tmp_path):
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text("evaluator_model: {}\n")
        config = EvaluatorConfig.from_yaml(str(config_file))
        assert config.model_name == "llama3.2:8b"

    def test_temperature_defaults_to_zero(self, tmp_path):
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text("evaluator_model: {}\n")
        config = EvaluatorConfig.from_yaml(str(config_file))
        assert config.temperature == 0.0

    def test_runner_uses_evaluators_dir_from_config(self, full_config_yaml, tmp_path):
        runner = EvaluatorRunner(config_path=str(full_config_yaml))
        assert "evaluators" in str(runner.evaluators_dir)


class TestDefaultConfigFile:
    """Test the actual evaluator_config.yaml in the repo root."""

    @pytest.fixture()
    def repo_config(self):
        repo_root = Path(__file__).parent.parent
        config_path = repo_root / "evaluator_config.yaml"
        if not config_path.exists():
            pytest.skip("evaluator_config.yaml not found in repo root")
        return config_path

    def test_default_provider_is_ollama(self, repo_config):
        config = EvaluatorConfig.from_yaml(str(repo_config))
        assert config.provider == "ollama"

    def test_default_model_is_llama(self, repo_config):
        config = EvaluatorConfig.from_yaml(str(repo_config))
        assert config.model_name == "llama3.2:8b"

    def test_no_secrets_in_config_file(self, repo_config):
        content = repo_config.read_text()
        # No API key values (only commented-out env var references)
        assert "sk-" not in content
        assert "OPENROUTER_API_KEY:" not in content.replace("# ", "").replace("#", "")
        assert "ANTHROPIC_API_KEY:" not in content.replace("# ", "").replace("#", "")

    def test_zero_api_keys_in_yaml_values(self, repo_config):
        """YAML values should not contain any API key patterns."""
        with open(repo_config) as f:
            data = yaml.safe_load(f)

        model_cfg = data.get("evaluator_model", {})
        # These keys must not be present in the parsed YAML values
        for key in ["api_key", "openrouter_key", "anthropic_key", "openai_key"]:
            assert (
                key not in model_cfg
            ), f"Found secret key '{key}' in evaluator_model config"

    def test_evaluators_dir_defined(self, repo_config):
        with open(repo_config) as f:
            data = yaml.safe_load(f)
        assert "evaluators_dir" in data

    def test_audit_log_defined(self, repo_config):
        with open(repo_config) as f:
            data = yaml.safe_load(f)
        assert "audit" in data
        assert "log_file" in data["audit"]
        assert "evaluations.jsonl" in data["audit"]["log_file"]

    def test_schedule_defined(self, repo_config):
        with open(repo_config) as f:
            data = yaml.safe_load(f)
        assert "schedule" in data
        assert "cron" in data["schedule"]
        assert "lookback_hours" in data["schedule"]

    def test_thresholds_defined_for_all_evaluators(self, repo_config):
        with open(repo_config) as f:
            data = yaml.safe_load(f)
        thresholds = data.get("thresholds", {})
        expected_keys = [
            "retrieval_relevance",
            "injection_value",
            "capture_completeness",
            "classification_accuracy",
            "bootstrap_quality",
            "session_coherence",
        ]
        for key in expected_keys:
            assert key in thresholds, f"Missing threshold for '{key}'"


class TestProviderValidation:
    """Test that provider values are validated correctly."""

    def test_valid_providers_accepted(self, tmp_path):
        for provider in ["ollama", "openrouter", "anthropic", "openai", "custom"]:
            config_file = tmp_path / f"{provider}.yaml"
            config_file.write_text(f"evaluator_model:\n  provider: {provider}\n")
            config = EvaluatorConfig.from_yaml(str(config_file))
            assert config.provider == provider

    def test_explicit_provider_overrides_default(self, tmp_path):
        config_file = tmp_path / "openrouter.yaml"
        config_file.write_text(
            "evaluator_model:\n  provider: openrouter\n  model_name: openai/gpt-4o\n"
        )
        config = EvaluatorConfig.from_yaml(str(config_file))
        assert config.provider == "openrouter"
        assert config.model_name == "openai/gpt-4o"


class TestEvaluatorDefinitionLoading:
    """Test that EvaluatorRunner correctly loads evaluator YAML definitions."""

    def test_loads_evaluator_yaml_files(self, tmp_path, full_config_yaml):
        ev_dir = tmp_path / "evaluators"

        ev = {
            "id": "EV-01",
            "name": "retrieval_relevance",
            "score_type": "NUMERIC",
            "filter": {"tags": ["retrieval"]},
            "sampling_rate": 0.05,
            "prompt_file": "ev01_prompt.md",
        }
        (ev_dir / "ev01.yaml").write_text(yaml.dump(ev))
        (ev_dir / "ev01_prompt.md").write_text("Evaluate this.")

        runner = EvaluatorRunner(config_path=str(full_config_yaml))
        evaluators = runner._load_evaluators()

        assert len(evaluators) == 1
        assert evaluators[0]["id"] == "EV-01"
        assert evaluators[0]["name"] == "retrieval_relevance"

    def test_filters_by_evaluator_id(self, tmp_path, full_config_yaml):
        ev_dir = tmp_path / "evaluators"

        for ev_id, ev_name in [
            ("EV-01", "retrieval_relevance"),
            ("EV-02", "injection_value"),
        ]:
            ev = {
                "id": ev_id,
                "name": ev_name,
                "score_type": "NUMERIC",
                "filter": {},
                "sampling_rate": 0.05,
                "prompt_file": "prompt.md",
            }
            (ev_dir / f"{ev_id.lower()}.yaml").write_text(yaml.dump(ev))
        (ev_dir / "prompt.md").write_text("Evaluate.")

        runner = EvaluatorRunner(config_path=str(full_config_yaml))
        evaluators = runner._load_evaluators(evaluator_id="EV-01")

        assert len(evaluators) == 1
        assert evaluators[0]["id"] == "EV-01"

    def test_returns_empty_list_when_dir_missing(self, tmp_path):
        config_content = {
            "evaluator_model": {"provider": "ollama", "model_name": "llama3.2:8b"},
            "evaluators_dir": str(tmp_path / "nonexistent_dir"),
            "audit": {"log_file": str(tmp_path / "eval.jsonl")},
        }
        config_file = tmp_path / "cfg.yaml"
        config_file.write_text(yaml.dump(config_content))

        runner = EvaluatorRunner(config_path=str(config_file))
        evaluators = runner._load_evaluators()
        assert evaluators == []
