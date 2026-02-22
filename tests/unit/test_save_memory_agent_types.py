"""Tests for /save-memory agent memory type support (SPEC-017 S4).

Tests parse_args() directly and main() via importlib to verify
actual code paths rather than testing mocks.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load manual_save_memory as a module from the hooks script path
_script_path = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "hooks"
    / "scripts"
    / "manual_save_memory.py"
)


def _load_script():
    """Import manual_save_memory.py as a module."""
    spec = importlib.util.spec_from_file_location("manual_save_memory", _script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParseArgs:
    """Test parse_args() function extracted from manual_save_memory.py."""

    @pytest.fixture(autouse=True)
    def _load(self, monkeypatch):
        """Skip if script not found (e.g. CI without full install)."""
        if not _script_path.exists():
            pytest.skip(f"Script not found: {_script_path}")
        # Point to repo root so src/memory is found during import
        repo_root = str(Path(__file__).resolve().parents[2])
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", repo_root)
        self.mod = _load_script()

    def test_no_args(self):
        """No arguments returns empty description and no type."""
        desc, typ = self.mod.parse_args([])
        assert desc == ""
        assert typ is None

    def test_description_only(self):
        """Plain description with no --type flag."""
        desc, typ = self.mod.parse_args(["some", "description", "text"])
        assert desc == "some description text"
        assert typ is None

    def test_type_agent_memory(self):
        """--type agent_memory is parsed correctly."""
        desc, typ = self.mod.parse_args(["note here", "--type", "agent_memory"])
        assert desc == "note here"
        assert typ == "agent_memory"

    def test_type_agent_insight(self):
        """--type agent_insight is parsed correctly."""
        desc, typ = self.mod.parse_args(["--type", "agent_insight", "some", "text"])
        assert desc == "some text"
        assert typ == "agent_insight"

    def test_type_only_no_description(self):
        """--type with no description words."""
        desc, typ = self.mod.parse_args(["--type", "agent_memory"])
        assert desc == ""
        assert typ == "agent_memory"

    def test_dangling_type_raises(self):
        """--type without a value raises ValueError."""
        with pytest.raises(ValueError, match="--type requires a value"):
            self.mod.parse_args(["some", "text", "--type"])

    def test_invalid_type_passes_through(self):
        """parse_args does not validate type values (main() does)."""
        _desc, typ = self.mod.parse_args(["--type", "bogus"])
        assert typ == "bogus"


class TestMainAgentPath:
    """Test main() agent memory path using mocked storage."""

    @pytest.fixture(autouse=True)
    def _load(self, monkeypatch):
        if not _script_path.exists():
            pytest.skip(f"Script not found: {_script_path}")
        # Point to repo root so src/memory is found during import
        repo_root = str(Path(__file__).resolve().parents[2])
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", repo_root)
        self.mod = _load_script()

    def test_agent_memory_calls_store_agent_memory(self):
        """AC-8: --type agent_memory routes to store_agent_memory()."""
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "test-id-1234",
            "embedding_status": "complete",
        }
        mock_config = MagicMock()
        mock_config.parzival_enabled = True

        with (
            patch.object(
                self.mod.sys, "argv", ["script", "Test note", "--type", "agent_memory"]
            ),
            patch("memory.config.get_config", return_value=mock_config),
            patch("memory.storage.MemoryStorage", return_value=mock_storage),
            patch.object(self.mod, "detect_project", return_value="test-project"),
            patch.object(self.mod, "log_manual_save"),
        ):
            result = self.mod.main()

        assert result == 0
        mock_storage.store_agent_memory.assert_called_once()
        call_kwargs = mock_storage.store_agent_memory.call_args[1]
        assert call_kwargs["memory_type"] == "agent_memory"
        assert call_kwargs["agent_id"] == "parzival"
        assert call_kwargs["group_id"] == "test-project"
        assert call_kwargs["content"] == "Test note"

    def test_agent_insight_calls_store_agent_memory(self):
        """AC-9: --type agent_insight routes to store_agent_memory()."""
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "test-id-5678",
            "embedding_status": "complete",
        }
        mock_config = MagicMock()
        mock_config.parzival_enabled = True

        with (
            patch.object(
                self.mod.sys,
                "argv",
                ["script", "--type", "agent_insight", "Key learning"],
            ),
            patch("memory.config.get_config", return_value=mock_config),
            patch("memory.storage.MemoryStorage", return_value=mock_storage),
            patch.object(self.mod, "detect_project", return_value="test-project"),
            patch.object(self.mod, "log_manual_save"),
        ):
            result = self.mod.main()

        assert result == 0
        call_kwargs = mock_storage.store_agent_memory.call_args[1]
        assert call_kwargs["memory_type"] == "agent_insight"

    def test_invalid_type_returns_error(self):
        """AC-11: Invalid --type value returns exit code 1."""
        with (
            patch.object(self.mod.sys, "argv", ["script", "--type", "bogus", "text"]),
            patch.object(self.mod, "detect_project", return_value="test-project"),
        ):
            result = self.mod.main()

        assert result == 1

    def test_parzival_disabled_returns_error(self):
        """Agent types require parzival_enabled=true."""
        mock_config = MagicMock()
        mock_config.parzival_enabled = False

        with (
            patch.object(
                self.mod.sys, "argv", ["script", "--type", "agent_memory", "text"]
            ),
            patch("memory.config.get_config", return_value=mock_config),
            patch.object(self.mod, "detect_project", return_value="test-project"),
        ):
            result = self.mod.main()

        assert result == 1

    def test_no_type_uses_default_path(self):
        """No --type flag uses the existing store_manual_summary path."""
        with (
            patch.object(self.mod.sys, "argv", ["script", "regular save"]),
            patch.object(self.mod, "detect_project", return_value="test-project"),
            patch.object(
                self.mod, "store_manual_summary", return_value=True
            ) as mock_store,
            patch.object(self.mod, "log_manual_save"),
        ):
            result = self.mod.main()

        assert result == 0
        mock_store.assert_called_once()

    def test_unhandled_status_returns_error(self):
        """Unrecognized result status returns exit code 1."""
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.return_value = {
            "status": "error",
            "memory_id": "test-id",
        }
        mock_config = MagicMock()
        mock_config.parzival_enabled = True

        with (
            patch.object(
                self.mod.sys, "argv", ["script", "--type", "agent_memory", "text"]
            ),
            patch("memory.config.get_config", return_value=mock_config),
            patch("memory.storage.MemoryStorage", return_value=mock_storage),
            patch.object(self.mod, "detect_project", return_value="test-project"),
            patch.object(self.mod, "log_manual_save"),
        ):
            result = self.mod.main()

        assert result == 1

    def test_default_content_when_no_description(self):
        """Empty description uses 'Manual save' default."""
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "test-id",
            "embedding_status": "complete",
        }
        mock_config = MagicMock()
        mock_config.parzival_enabled = True

        with (
            patch.object(self.mod.sys, "argv", ["script", "--type", "agent_memory"]),
            patch("memory.config.get_config", return_value=mock_config),
            patch("memory.storage.MemoryStorage", return_value=mock_storage),
            patch.object(self.mod, "detect_project", return_value="test-project"),
            patch.object(self.mod, "log_manual_save"),
        ):
            result = self.mod.main()

        assert result == 0
        call_kwargs = mock_storage.store_agent_memory.call_args[1]
        assert call_kwargs["content"] == "Manual save"
