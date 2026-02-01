"""Tests for safe environment variable handling in config.

TECH-DEBT-069: Ensure config handles invalid env vars gracefully.
"""

import importlib


class TestEnvVarSafety:
    """Test safe environment variable handling."""

    def test_invalid_float_env_uses_default(self, monkeypatch):
        """Invalid float env var should use default, not crash."""
        monkeypatch.setenv("MEMORY_CLASSIFIER_CONFIDENCE_THRESHOLD", "not_a_number")

        # Re-import to trigger env var parsing
        from src.memory.classifier import config

        importlib.reload(config)

        # Should use default, not crash
        assert config.CONFIDENCE_THRESHOLD == 0.7

    def test_out_of_range_float_uses_default(self, monkeypatch):
        """Out of range float should use default."""
        monkeypatch.setenv("MEMORY_CLASSIFIER_CONFIDENCE_THRESHOLD", "1.5")  # > 1.0

        from src.memory.classifier import config

        importlib.reload(config)

        # Should clamp to default
        assert config.CONFIDENCE_THRESHOLD == 0.7

    def test_negative_float_uses_default(self, monkeypatch):
        """Negative float should use default."""
        monkeypatch.setenv("MEMORY_CLASSIFIER_CONFIDENCE_THRESHOLD", "-0.5")

        from src.memory.classifier import config

        importlib.reload(config)

        assert config.CONFIDENCE_THRESHOLD == 0.7

    def test_invalid_int_env_uses_default(self, monkeypatch):
        """Invalid int env var should use default."""
        monkeypatch.setenv("MEMORY_CLASSIFIER_TIMEOUT", "abc")

        from src.memory.classifier import config

        importlib.reload(config)

        assert config.TIMEOUT_SECONDS == 10

    def test_out_of_range_int_uses_default(self, monkeypatch):
        """Out of range int should use default."""
        monkeypatch.setenv("MEMORY_CLASSIFIER_TIMEOUT", "999999")  # > max

        from src.memory.classifier import config

        importlib.reload(config)

        assert config.TIMEOUT_SECONDS == 10

    def test_negative_int_uses_default(self, monkeypatch):
        """Negative int should use default."""
        monkeypatch.setenv("MEMORY_CLASSIFIER_MIN_CONTENT_LENGTH", "-10")

        from src.memory.classifier import config

        importlib.reload(config)

        assert config.MIN_CONTENT_LENGTH == 20

    def test_valid_float_env_accepted(self, monkeypatch):
        """Valid float env var should be accepted."""
        monkeypatch.setenv("MEMORY_CLASSIFIER_CONFIDENCE_THRESHOLD", "0.85")

        from src.memory.classifier import config

        importlib.reload(config)

        assert config.CONFIDENCE_THRESHOLD == 0.85

    def test_valid_int_env_accepted(self, monkeypatch):
        """Valid int env var should be accepted."""
        monkeypatch.setenv("MEMORY_CLASSIFIER_TIMEOUT", "30")

        from src.memory.classifier import config

        importlib.reload(config)

        assert config.TIMEOUT_SECONDS == 30
