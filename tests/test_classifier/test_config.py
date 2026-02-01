"""Tests for classifier configuration.

TECH-DEBT-069: LLM-based memory classification system tests.
"""


class TestClassifierConfig:
    """Test classifier configuration loading and defaults."""

    def test_default_values(self):
        """Test that default configuration values are loaded correctly."""
        from src.memory.classifier.config import (
            CLASSIFIER_ENABLED,
            CONFIDENCE_THRESHOLD,
            MIN_CONTENT_LENGTH,
            OLLAMA_MODEL,
            PRIMARY_PROVIDER,
        )

        assert CLASSIFIER_ENABLED is True  # Default
        assert CONFIDENCE_THRESHOLD == 0.7
        assert MIN_CONTENT_LENGTH == 20
        assert OLLAMA_MODEL == "sam860/LFM2:2.6b"
        assert PRIMARY_PROVIDER == "ollama"

    def test_env_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        # Set environment variables
        monkeypatch.setenv("MEMORY_CLASSIFIER_ENABLED", "false")
        monkeypatch.setenv("MEMORY_CLASSIFIER_CONFIDENCE_THRESHOLD", "0.8")
        monkeypatch.setenv("MEMORY_CLASSIFIER_MIN_CONTENT_LENGTH", "50")

        # Reload module to pick up new env vars
        import importlib

        from src.memory.classifier import config

        importlib.reload(config)

        assert config.CLASSIFIER_ENABLED is False
        assert config.CONFIDENCE_THRESHOLD == 0.8
        assert config.MIN_CONTENT_LENGTH == 50

    def test_valid_types_structure(self):
        """Test that VALID_TYPES dictionary is correctly structured."""
        from src.memory.classifier.config import VALID_TYPES

        # Check collections exist
        assert "code-patterns" in VALID_TYPES
        assert "conventions" in VALID_TYPES
        assert "discussions" in VALID_TYPES

        # Check code-patterns types
        assert "implementation" in VALID_TYPES["code-patterns"]
        assert "error_fix" in VALID_TYPES["code-patterns"]
        assert "refactor" in VALID_TYPES["code-patterns"]
        assert "file_pattern" in VALID_TYPES["code-patterns"]

        # Check conventions types
        assert "rule" in VALID_TYPES["conventions"]
        assert "guideline" in VALID_TYPES["conventions"]
        assert "port" in VALID_TYPES["conventions"]
        assert "naming" in VALID_TYPES["conventions"]
        assert "structure" in VALID_TYPES["conventions"]

        # Check discussions types
        assert "decision" in VALID_TYPES["discussions"]
        assert "session" in VALID_TYPES["discussions"]
        assert "blocker" in VALID_TYPES["discussions"]
        assert "preference" in VALID_TYPES["discussions"]
        assert "user_message" in VALID_TYPES["discussions"]
        assert "agent_response" in VALID_TYPES["discussions"]

    def test_rule_patterns_structure(self):
        """Test that RULE_PATTERNS dictionary is correctly structured."""
        from src.memory.classifier.config import RULE_PATTERNS

        # Check each rule has required fields
        for _rule_type, rule_config in RULE_PATTERNS.items():
            assert "patterns" in rule_config
            assert "confidence" in rule_config
            assert isinstance(rule_config["patterns"], list)
            assert isinstance(rule_config["confidence"], float)
            assert 0.0 <= rule_config["confidence"] <= 1.0

    def test_significance_enum(self):
        """Test Significance enum values."""
        from src.memory.classifier.config import Significance

        assert Significance.HIGH.value == "high"
        assert Significance.MEDIUM.value == "medium"
        assert Significance.LOW.value == "low"
        assert Significance.SKIP.value == "skip"

    def test_cost_tracking_structure(self):
        """Test COST_PER_MILLION dictionary structure."""
        from src.memory.classifier.config import COST_PER_MILLION

        # Check providers exist
        assert "ollama" in COST_PER_MILLION
        assert "openrouter" in COST_PER_MILLION
        assert "claude" in COST_PER_MILLION

        # Check each provider has input/output costs
        for _provider, costs in COST_PER_MILLION.items():
            assert "input" in costs
            assert "output" in costs
            assert isinstance(costs["input"], (int, float))
            assert isinstance(costs["output"], (int, float))

        # Verify Ollama is free
        assert COST_PER_MILLION["ollama"]["input"] == 0.0
        assert COST_PER_MILLION["ollama"]["output"] == 0.0
