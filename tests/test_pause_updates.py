"""Hermetic tests for scripts/memory/pause_updates.py — Item 10, aim-pause-updates.

All file I/O operates on tmp_path fixtures. memory.* is faked via sys.modules
injection before spec-loading, so no ai-memory install is required.
AI_MEMORY_PROJECT_ID is intentionally unset throughout.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "memory" / "pause_updates.py"


def _make_memory_stubs():
    """Return minimal sys.modules stubs for memory.* hard + soft imports."""
    mem_pkg = types.ModuleType("memory")
    metrics = types.ModuleType("memory.metrics_push")
    metrics.push_skill_metrics_async = lambda *a, **kw: None
    trace = types.ModuleType("memory.trace_buffer")
    trace.emit_trace_event = lambda *a, **kw: None
    return {
        "memory": mem_pkg,
        "memory.metrics_push": metrics,
        "memory.trace_buffer": trace,
    }


def _load_module(monkeypatch):
    """Load pause_updates.py with faked memory.* modules; returns the module."""
    for name, mod in _make_memory_stubs().items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "pause_updates", raising=False)
    spec = importlib.util.spec_from_file_location("pause_updates", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFindEnvFile:
    def test_local_env_wins(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch)
        env_file = tmp_path / ".env"
        env_file.write_text("AUTO_UPDATE_ENABLED=true\n")
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        assert mod._find_env_file() == env_file

    def test_install_dir_tier(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch)
        install_dir = tmp_path / "install"
        docker_env = install_dir / "docker" / ".env"
        docker_env.parent.mkdir(parents=True)
        docker_env.write_text("AUTO_UPDATE_ENABLED=true\n")
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(install_dir))
        empty_cwd = tmp_path / "work"
        empty_cwd.mkdir()
        monkeypatch.setattr(Path, "cwd", lambda: empty_cwd)
        assert mod._find_env_file() == docker_env


class TestReadWriteEnvValue:
    def test_roundtrip_preserves_other_lines(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch)
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=val\nAUTO_UPDATE_ENABLED=true\nMORE=x\n")
        mod._write_env_value(env_file, "AUTO_UPDATE_ENABLED", "false")
        assert mod._read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "false"
        text = env_file.read_text()
        assert "OTHER=val" in text
        assert "MORE=x" in text

    def test_missing_key_appended(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch)
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=val\n")
        mod._write_env_value(env_file, "AUTO_UPDATE_ENABLED", "false")
        assert mod._read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "false"


class TestLogToggle:
    def test_audit_log_written_correctly(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch)
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("")
        mod._log_toggle(env_file, "true", "false")
        log_path = tmp_path / ".audit" / "logs" / "kill-switch-log.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["field"] == "AUTO_UPDATE_ENABLED"
        assert entry["old_value"] == "true"
        assert entry["new_value"] == "false"
        assert entry["env_file"] == str(env_file)


class TestMain:
    def _setup(
        self, monkeypatch, tmp_path, argv, env_content="AUTO_UPDATE_ENABLED=true\n"
    ):
        """Load module, write fixture .env, monkeypatch cwd + argv."""
        mod = _load_module(monkeypatch)
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        monkeypatch.setattr(sys, "argv", argv)
        return mod, env_file

    def test_toggle_enabled_to_paused(self, monkeypatch, tmp_path, capsys):
        """No arg, currently true → writes false, prints PAUSED."""
        mod, env_file = self._setup(monkeypatch, tmp_path, ["pause_updates.py"])
        assert mod.main() == 0
        assert mod._read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "false"
        assert "PAUSED" in capsys.readouterr().out

    def test_toggle_paused_to_enabled(self, monkeypatch, tmp_path, capsys):
        """No arg, currently false → writes true, prints ENABLED."""
        mod, env_file = self._setup(
            monkeypatch,
            tmp_path,
            ["pause_updates.py"],
            env_content="AUTO_UPDATE_ENABLED=false\n",
        )
        assert mod.main() == 0
        assert mod._read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "true"
        assert "ENABLED" in capsys.readouterr().out

    def test_explicit_on_idempotent(self, monkeypatch, tmp_path, capsys):
        """Explicit 'on' when already enabled → stays true, prints ENABLED."""
        mod, env_file = self._setup(monkeypatch, tmp_path, ["pause_updates.py", "on"])
        assert mod.main() == 0
        assert mod._read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "true"
        assert "ENABLED" in capsys.readouterr().out

    def test_read_after_write_consistency(self, monkeypatch, tmp_path):
        """After toggle, _read_env_value reflects the new value."""
        mod, env_file = self._setup(monkeypatch, tmp_path, ["pause_updates.py"])
        mod.main()
        assert mod._read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "false"

    def test_missing_key_defaults_to_enabled_then_toggles(self, monkeypatch, tmp_path):
        """AUTO_UPDATE_ENABLED absent → treated as True → toggle → writes false."""
        mod, env_file = self._setup(
            monkeypatch, tmp_path, ["pause_updates.py"], env_content="OTHER=x\n"
        )
        assert mod.main() == 0
        assert mod._read_env_value(env_file, "AUTO_UPDATE_ENABLED") == "false"

    def test_missing_env_file_returns_1(self, monkeypatch, tmp_path):
        """No .env anywhere → main() returns 1."""
        mod = _load_module(monkeypatch)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setattr(Path, "cwd", lambda: empty_dir)
        monkeypatch.delenv("AI_MEMORY_INSTALL_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")
        monkeypatch.setattr(sys, "argv", ["pause_updates.py"])
        assert mod.main() == 1

    def test_invalid_arg_returns_1(self, monkeypatch, tmp_path):
        """Unknown arg string → main() returns 1."""
        mod, _ = self._setup(monkeypatch, tmp_path, ["pause_updates.py", "bad"])
        assert mod.main() == 1
