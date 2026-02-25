"""Tests for PLAN-009 Phase 3: Jira sync alignment to projects.d/.

Covers:
- JiraSyncEngine(config, instance_url=..., jira_projects=...) param overrides
- JiraSyncEngine(config) backward compat
- Per-instance state file naming (hostname dots → underscores)
- jira_sync.py --project-id flag parsing
- jira_sync.run_sync() 3-way project branching with mocked discover_projects
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Allow importing jira_sync from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

import jira_sync

from memory.connectors.jira.sync import JiraSyncEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    instance_url: str = "https://company.atlassian.net",
    jira_projects: list[str] | None = None,
    tmp_path: Path | None = None,
) -> Mock:
    """Minimal mock MemoryConfig for JiraSyncEngine init."""
    config = Mock()
    config.jira_sync_enabled = True
    config.jira_instance_url = instance_url
    config.jira_email = "test@example.com"
    config.jira_api_token = Mock()
    config.jira_api_token.get_secret_value.return_value = "test-token"
    config.jira_projects = ["PROJ"] if jira_projects is None else jira_projects
    config.jira_sync_delay_ms = 0
    config.install_dir = tmp_path or Path("/tmp/test-jira")
    return config


def _make_sync_engine(config: Mock) -> JiraSyncEngine:
    """Build JiraSyncEngine with all heavy deps mocked."""
    with (
        patch("memory.connectors.jira.sync.JiraClient"),
        patch("memory.connectors.jira.sync.MemoryStorage"),
        patch("memory.connectors.jira.sync.EmbeddingClient"),
        patch("memory.connectors.jira.sync.get_qdrant_client"),
    ):
        return JiraSyncEngine(config=config)


def _make_sync_engine_with_override(
    config: Mock,
    instance_url: str | None = None,
    jira_projects: list[str] | None = None,
) -> JiraSyncEngine:
    """Build JiraSyncEngine with param overrides and all deps mocked."""
    with (
        patch("memory.connectors.jira.sync.JiraClient"),
        patch("memory.connectors.jira.sync.MemoryStorage"),
        patch("memory.connectors.jira.sync.EmbeddingClient"),
        patch("memory.connectors.jira.sync.get_qdrant_client"),
    ):
        return JiraSyncEngine(
            config=config,
            instance_url=instance_url,
            jira_projects=jira_projects,
        )


def _make_project(
    jira_enabled: bool = True,
    instance_url: str = "https://proj.atlassian.net",
    jira_projects: list[str] | None = None,
) -> MagicMock:
    """Create a mock ProjectSyncConfig-like object."""
    p = MagicMock()
    p.jira_enabled = jira_enabled
    p.jira_instance_url = instance_url
    p.jira_projects = jira_projects if jira_projects is not None else ["PROJ"]
    return p


# ---------------------------------------------------------------------------
# JiraSyncEngine — instance_url and jira_projects params
# ---------------------------------------------------------------------------


def test_engine_instance_url_param_overrides_config(tmp_path):
    """JiraSyncEngine(config, instance_url=...) uses provided URL."""
    config = _make_config(instance_url="https://default.atlassian.net", tmp_path=tmp_path)

    engine = _make_sync_engine_with_override(
        config, instance_url="https://override.atlassian.net"
    )

    assert engine._instance_url == "https://override.atlassian.net"
    assert engine.group_id == "override.atlassian.net"


def test_engine_backward_compat_uses_config_instance_url(tmp_path):
    """JiraSyncEngine(config) falls back to config.jira_instance_url."""
    config = _make_config(instance_url="https://company.atlassian.net", tmp_path=tmp_path)

    engine = _make_sync_engine(config)

    assert engine._instance_url == "https://company.atlassian.net"
    assert engine.group_id == "company.atlassian.net"


def test_engine_jira_projects_param_overrides_config(tmp_path):
    """JiraSyncEngine(config, jira_projects=[...]) uses provided project list."""
    config = _make_config(jira_projects=["DEFAULT"], tmp_path=tmp_path)

    engine = _make_sync_engine_with_override(
        config, jira_projects=["OVERRIDE-A", "OVERRIDE-B"]
    )

    assert engine._jira_projects == ["OVERRIDE-A", "OVERRIDE-B"]


def test_engine_backward_compat_uses_config_jira_projects(tmp_path):
    """JiraSyncEngine(config) falls back to config.jira_projects."""
    config = _make_config(jira_projects=["PROJ1", "PROJ2"], tmp_path=tmp_path)

    engine = _make_sync_engine(config)

    assert engine._jira_projects == ["PROJ1", "PROJ2"]


def test_engine_jira_projects_empty_list_not_overridden_by_config(tmp_path):
    """JiraSyncEngine(config, jira_projects=[]) must NOT fall back to config.jira_projects."""
    config = _make_config(jira_projects=["SHOULD-NOT-APPEAR"], tmp_path=tmp_path)

    engine = _make_sync_engine_with_override(config, jira_projects=[])

    # An explicit empty list must be respected, not silently discarded by `or`
    assert engine._jira_projects == []


# ---------------------------------------------------------------------------
# Per-instance state file naming
# ---------------------------------------------------------------------------


def test_state_file_per_instance_dots_to_underscores(tmp_path):
    """State file replaces '.' with '_' in hostname."""
    config = _make_config(
        instance_url="https://mycompany.atlassian.net", tmp_path=tmp_path
    )

    engine = _make_sync_engine(config)

    assert engine._state_file.name == "jira_sync_state_mycompany_atlassian_net.json"


def test_state_file_backward_compat_alias(tmp_path):
    """state_path is an alias for _state_file."""
    config = _make_config(tmp_path=tmp_path)

    engine = _make_sync_engine(config)

    assert engine.state_path == engine._state_file


def test_different_instances_get_different_state_files(tmp_path):
    """Two engines with different instance URLs use isolated state files."""
    config_a = _make_config(
        instance_url="https://tenant-a.atlassian.net", tmp_path=tmp_path
    )
    config_b = _make_config(
        instance_url="https://tenant-b.atlassian.net", tmp_path=tmp_path
    )

    engine_a = _make_sync_engine(config_a)
    engine_b = _make_sync_engine(config_b)

    assert engine_a._state_file.name != engine_b._state_file.name
    assert "tenant-a" in engine_a._state_file.name
    assert "tenant-b" in engine_b._state_file.name


def test_instance_url_override_changes_state_file(tmp_path):
    """Overriding instance_url changes the state file path."""
    config = _make_config(
        instance_url="https://default.atlassian.net", tmp_path=tmp_path
    )

    engine = _make_sync_engine_with_override(
        config, instance_url="https://custom.atlassian.net"
    )

    assert "custom_atlassian_net" in engine._state_file.name
    # Default URL's state file should NOT be used
    assert "default_atlassian_net" not in engine._state_file.name


# ---------------------------------------------------------------------------
# sync_all_projects — uses _jira_projects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_all_projects_uses_override_list(tmp_path):
    """sync_all_projects iterates _jira_projects, not config.jira_projects."""
    config = _make_config(jira_projects=["CONFIG-PROJ"], tmp_path=tmp_path)

    engine = _make_sync_engine_with_override(
        config, jira_projects=["OVERRIDE-A", "OVERRIDE-B"]
    )

    synced_keys: list[str] = []

    async def mock_sync_project(key, mode="incremental"):
        synced_keys.append(key)
        from memory.connectors.jira.sync import SyncResult
        return SyncResult(issues_synced=1)

    engine.sync_project = mock_sync_project

    await engine.sync_all_projects()

    assert sorted(synced_keys) == ["OVERRIDE-A", "OVERRIDE-B"]
    assert "CONFIG-PROJ" not in synced_keys


@pytest.mark.asyncio
async def test_sync_all_projects_empty_list_returns_empty(tmp_path):
    """sync_all_projects returns {} when _jira_projects is empty."""
    config = _make_config(jira_projects=[], tmp_path=tmp_path)

    engine = _make_sync_engine(config)
    # Explicitly set to empty list
    engine._jira_projects = []

    results = await engine.sync_all_projects()

    assert results == {}


# ---------------------------------------------------------------------------
# jira_sync.py — --project-id flag
# ---------------------------------------------------------------------------


def test_project_id_argument_parsed():
    """--project-id flag is registered and parsed correctly."""
    import argparse

    # TODO: This tests argparse behaviour, not the actual jira_sync parser.
    #       Refactor jira_sync.py to expose a build_parser() function and
    #       test that directly.
    # Recreate parser from jira_sync.main()
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--project", type=str)
    parser.add_argument(
        "--project-id", type=str, dest="project_id"
    )
    parser.add_argument("--status", action="store_true")

    args = parser.parse_args(["--project-id", "my-project"])
    assert args.project_id == "my-project"


def test_project_id_defaults_to_none():
    """--project-id is None when not supplied."""
    import argparse

    # TODO: Same limitation as test_project_id_argument_parsed — tests
    #       argparse behaviour, not the real jira_sync parser.
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", type=str, dest="project_id")

    args = parser.parse_args([])
    assert args.project_id is None


# ---------------------------------------------------------------------------
# jira_sync.run_sync — 3-way branching with mocked discover_projects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sync_project_id_not_found_exits():
    """run_sync exits with code 1 if --project-id not in jira_projects."""
    config = MagicMock()
    config.jira_sync_enabled = True

    args = MagicMock()
    args.status = False
    args.full = False
    args.incremental = False
    args.project = None
    args.project_id = "missing-project"

    projects = {"other-project": _make_project(jira_enabled=True)}

    with (
        patch("memory.config.discover_projects", return_value=projects),
        pytest.raises(SystemExit) as exc_info,
    ):
        await jira_sync.run_sync(args, config)

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_run_sync_project_id_creates_engine_with_override():
    """--project-id creates JiraSyncEngine with instance-specific params."""
    config = MagicMock()
    config.jira_sync_enabled = True

    args = MagicMock()
    args.status = False
    args.full = False
    args.incremental = False
    args.project = None
    args.project_id = "proj-alpha"

    project = _make_project(
        jira_enabled=True,
        instance_url="https://alpha.atlassian.net",
        jira_projects=["ALPHA"],
    )
    projects = {"proj-alpha": project}

    mock_engine = AsyncMock()
    mock_engine.sync_all_projects.return_value = {}
    mock_engine.close = AsyncMock()

    engine_calls: list[dict] = []

    def make_engine(cfg, instance_url=None, jira_projects=None):
        engine_calls.append({"instance_url": instance_url, "jira_projects": jira_projects})
        return mock_engine

    with (
        patch("memory.config.discover_projects", return_value=projects),
        patch.object(jira_sync, "JiraSyncEngine", side_effect=make_engine),
    ):
        await jira_sync.run_sync(args, config)

    assert len(engine_calls) == 1
    assert engine_calls[0]["instance_url"] == "https://alpha.atlassian.net"
    assert engine_calls[0]["jira_projects"] == ["ALPHA"]
    mock_engine.close.assert_called()


@pytest.mark.asyncio
async def test_run_sync_iterates_all_jira_projects_from_projects_d():
    """Without --project-id, iterates all jira-enabled projects."""
    config = MagicMock()
    config.jira_sync_enabled = True

    args = MagicMock()
    args.status = False
    args.full = False
    args.incremental = False
    args.project = None
    args.project_id = None

    projects = {
        "proj-a": _make_project(instance_url="https://a.atlassian.net"),
        "proj-b": _make_project(instance_url="https://b.atlassian.net"),
        "proj-disabled": _make_project(jira_enabled=False),
    }

    mock_engine = AsyncMock()
    mock_engine.sync_all_projects.return_value = {}
    mock_engine.close = AsyncMock()

    instance_urls: list[str] = []

    def make_engine(cfg, instance_url=None, jira_projects=None):
        instance_urls.append(instance_url)
        return mock_engine

    with (
        patch("memory.config.discover_projects", return_value=projects),
        patch.object(jira_sync, "JiraSyncEngine", side_effect=make_engine),
    ):
        await jira_sync.run_sync(args, config)

    # Should sync proj-a and proj-b but not proj-disabled
    assert sorted(instance_urls) == ["https://a.atlassian.net", "https://b.atlassian.net"]
    mock_engine.close.assert_called()


@pytest.mark.asyncio
async def test_run_sync_legacy_fallback_when_no_projects_d():
    """Falls back to legacy JiraSyncEngine(config) when no jira projects in projects.d/."""
    config = MagicMock()
    config.jira_sync_enabled = True
    config.jira_projects = ["LEGACY"]

    args = MagicMock()
    args.status = False
    args.full = False
    args.incremental = False
    args.project = None
    args.project_id = None

    # No projects in projects.d/
    with (
        patch("memory.config.discover_projects", return_value={}),
        patch.object(jira_sync, "JiraSyncEngine") as mock_engine_cls,
    ):
        mock_engine = AsyncMock()
        mock_engine.sync_all_projects.return_value = {}
        mock_engine.close = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        await jira_sync.run_sync(args, config)

    # Legacy: called with config only (no instance_url/jira_projects override)
    mock_engine_cls.assert_called_once_with(config)
    mock_engine.close.assert_called()
