"""Tests for /pause-updates skill: kill switch toggle + audit log.

Tests the core functions from the pause-updates skill without
requiring the full memory config stack.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# -- Inline functions from the skill for testability -----------------------
# (The skill code lives in SKILL.md, not an importable module)


def _read_env_value(env_file: Path, key: str) -> str | None:
    """Read a value from .env file."""
    if not env_file or not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _write_env_value(env_file: Path, key: str, value: str) -> bool:
    """Update a value in .env file (preserves other lines)."""
    if not env_file or not env_file.exists():
        return False
    lines = env_file.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _log_toggle(log_path: Path, env_file: Path, old_value: str, new_value: str) -> None:
    """Write toggle event to JSONL audit log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "field": "AUTO_UPDATE_ENABLED",
        "old_value": old_value,
        "new_value": new_value,
        "env_file": str(env_file),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# -- Toggle tests ----------------------------------------------------------


class TestToggle:
    def test_toggle_on_to_off(self, tmp_path):
        """Toggle from enabled to disabled."""
        env_file = tmp_path / ".env"
        env_file.write_text("AUTO_UPDATE_ENABLED=true\nOTHER=value\n")

        current = _read_env_value(env_file, "AUTO_UPDATE_ENABLED")
        current_bool = current.lower() in ("true", "1", "yes") if current else True
        new_bool = not current_bool
        new_value = "true" if new_bool else "false"

        _write_env_value(env_file, "AUTO_UPDATE_ENABLED", new_value)

        assert _read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "false"
        # Verify OTHER preserved
        assert _read_env_value(env_file, "OTHER") == "value"

    def test_toggle_off_to_on(self, tmp_path):
        """Toggle from disabled to enabled."""
        env_file = tmp_path / ".env"
        env_file.write_text("AUTO_UPDATE_ENABLED=false\n")

        current = _read_env_value(env_file, "AUTO_UPDATE_ENABLED")
        current_bool = current.lower() in ("true", "1", "yes") if current else True
        new_bool = not current_bool
        new_value = "true" if new_bool else "false"

        _write_env_value(env_file, "AUTO_UPDATE_ENABLED", new_value)

        assert _read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "true"

    def test_explicit_on(self, tmp_path):
        """Explicit 'on' sets value to true."""
        env_file = tmp_path / ".env"
        env_file.write_text("AUTO_UPDATE_ENABLED=false\n")

        _write_env_value(env_file, "AUTO_UPDATE_ENABLED", "true")
        assert _read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "true"

    def test_explicit_off(self, tmp_path):
        """Explicit 'off' sets value to false."""
        env_file = tmp_path / ".env"
        env_file.write_text("AUTO_UPDATE_ENABLED=true\n")

        _write_env_value(env_file, "AUTO_UPDATE_ENABLED", "false")
        assert _read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "false"


class TestEnvReadWrite:
    def test_read_missing_key(self, tmp_path):
        """Reading a missing key returns None."""
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=value\n")
        assert _read_env_value(env_file, "AUTO_UPDATE_ENABLED") is None

    def test_read_quoted_value(self, tmp_path):
        """Reading a quoted value strips quotes."""
        env_file = tmp_path / ".env"
        env_file.write_text('AUTO_UPDATE_ENABLED="true"\n')
        assert _read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "true"

    def test_write_appends_missing_key(self, tmp_path):
        """Writing a missing key appends it."""
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=value\n")

        _write_env_value(env_file, "AUTO_UPDATE_ENABLED", "false")

        assert _read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "false"
        assert _read_env_value(env_file, "OTHER") == "value"

    def test_write_preserves_other_lines(self, tmp_path):
        """Writing one key doesn't disturb other env vars."""
        env_file = tmp_path / ".env"
        env_file.write_text("A=1\nAUTO_UPDATE_ENABLED=true\nB=2\n")

        _write_env_value(env_file, "AUTO_UPDATE_ENABLED", "false")

        content = env_file.read_text()
        assert "A=1" in content
        assert "B=2" in content
        assert "AUTO_UPDATE_ENABLED=false" in content

    def test_read_nonexistent_file(self, tmp_path):
        """Reading from nonexistent file returns None."""
        env_file = tmp_path / "nonexistent.env"
        assert _read_env_value(env_file, "AUTO_UPDATE_ENABLED") is None

    def test_write_nonexistent_file(self, tmp_path):
        """Writing to nonexistent file returns False."""
        env_file = tmp_path / "nonexistent.env"
        assert _write_env_value(env_file, "AUTO_UPDATE_ENABLED", "true") is False


class TestAuditLog:
    def test_audit_log_written(self, tmp_path):
        """Toggle writes to kill-switch-log.jsonl."""
        log_path = tmp_path / ".audit" / "logs" / "kill-switch-log.jsonl"
        env_file = tmp_path / ".env"
        env_file.write_text("AUTO_UPDATE_ENABLED=true\n")

        _log_toggle(log_path, env_file, "true", "false")

        assert log_path.exists()
        log_data = json.loads(log_path.read_text().strip())
        assert log_data["field"] == "AUTO_UPDATE_ENABLED"
        assert log_data["old_value"] == "true"
        assert log_data["new_value"] == "false"
        assert "timestamp" in log_data

    def test_audit_log_appends(self, tmp_path):
        """Multiple toggles append to the same log file."""
        log_path = tmp_path / ".audit" / "logs" / "kill-switch-log.jsonl"
        env_file = tmp_path / ".env"
        env_file.write_text("AUTO_UPDATE_ENABLED=true\n")

        _log_toggle(log_path, env_file, "true", "false")
        _log_toggle(log_path, env_file, "false", "true")

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
