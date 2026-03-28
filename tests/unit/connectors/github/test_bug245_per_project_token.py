"""Tests for BUG-245: Per-project GitHub token support.

Covers:
- ProjectSyncConfig.github_token field (optional)
- discover_projects() reading github.token from YAML
- discover_projects() backward compat (no token field)
- Token resolution: project-level > global fallback
- Token resolution: fallback to global when no project token
- GitHubSyncEngine token parameter
- github_sync_service._resolve_project_token()
- github_sync_service.run_sync_cycle() passes resolved token
- validate_project_tokens() uses repo access check (H-1, M-1, M-6)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import github_sync_service
import pytest
from github_sync_service import (
    _resolve_project_token,
    run_sync_cycle,
    validate_project_tokens,
)

from memory.config import ProjectSyncConfig, discover_projects
from memory.connectors.github.sync import GitHubSyncEngine


@pytest.fixture(autouse=True)
def _reset_shutdown_flag():
    """Reset SHUTDOWN_REQUESTED before and after each test."""
    github_sync_service.SHUTDOWN_REQUESTED = False
    yield
    github_sync_service.SHUTDOWN_REQUESTED = False


# ---------------------------------------------------------------------------
# Phase 2: ProjectSyncConfig.github_token field
# ---------------------------------------------------------------------------


def test_project_sync_config_token_field():
    """ProjectSyncConfig accepts optional github_token field (BUG-245)."""
    cfg = ProjectSyncConfig(
        project_id="test-proj",
        github_repo="org/repo",
        github_token="github_pat_XXXX",
    )
    assert cfg.github_token == "github_pat_XXXX"
    assert cfg.github_repo == "org/repo"
    assert cfg.project_id == "test-proj"


def test_project_sync_config_token_field_default_none():
    """ProjectSyncConfig.github_token defaults to None for backward compat."""
    cfg = ProjectSyncConfig(project_id="test-proj")
    assert cfg.github_token is None


# ---------------------------------------------------------------------------
# Phase 2: discover_projects() reads github.token from YAML
# ---------------------------------------------------------------------------


def test_discover_projects_with_token(tmp_path):
    """discover_projects() reads github.token from YAML when present."""
    projects_dir = tmp_path / "projects.d"
    projects_dir.mkdir()
    yaml_content = """\
project_id: doc-pipeline
source_directory: /home/user/projects/doc-pipeline
github:
  repo: Hidden-History/Document-Pipeline
  branch: main
  enabled: true
  token: github_pat_PROJECT_TOKEN
jira:
  enabled: false
"""
    (projects_dir / "doc-pipeline.yaml").write_text(yaml_content)

    projects = discover_projects(config_dir=projects_dir)

    assert "doc-pipeline" in projects
    proj = projects["doc-pipeline"]
    assert proj.github_token == "github_pat_PROJECT_TOKEN"
    assert proj.github_repo == "Hidden-History/Document-Pipeline"
    assert proj.github_enabled is True


def test_discover_projects_without_token(tmp_path):
    """discover_projects() works with existing YAML without token field (backward compat)."""
    projects_dir = tmp_path / "projects.d"
    projects_dir.mkdir()
    yaml_content = """\
project_id: ai-memory
source_directory: /home/user/projects/ai-memory
github:
  repo: Hidden-History/ai-memory
  branch: main
  enabled: true
jira:
  enabled: false
"""
    (projects_dir / "ai-memory.yaml").write_text(yaml_content)

    projects = discover_projects(config_dir=projects_dir)

    assert "ai-memory" in projects
    proj = projects["ai-memory"]
    assert proj.github_token is None
    assert proj.github_repo == "Hidden-History/ai-memory"
    assert proj.github_enabled is True


# ---------------------------------------------------------------------------
# Phase 3: Token resolution logic
# ---------------------------------------------------------------------------


def test_token_resolution_project_override():
    """Per-project token takes precedence over global token (BUG-245)."""
    config = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL_TOKEN"

    project = MagicMock()
    project.github_token = "github_pat_PROJECT_TOKEN"

    resolved = _resolve_project_token(config, project)
    assert resolved == "github_pat_PROJECT_TOKEN"
    # Global token should NOT be accessed when project token exists
    config.github_token.get_secret_value.assert_not_called()


def test_token_resolution_fallback():
    """Falls back to global token when no project token set (BUG-245)."""
    config = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL_TOKEN"

    project = MagicMock()
    project.github_token = None

    resolved = _resolve_project_token(config, project)
    assert resolved == "ghp_GLOBAL_TOKEN"
    config.github_token.get_secret_value.assert_called_once()


def test_token_resolution_empty_string_fallback():
    """Empty string project token falls back to global (BUG-245)."""
    config = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL_TOKEN"

    project = MagicMock()
    project.github_token = ""

    resolved = _resolve_project_token(config, project)
    assert resolved == "ghp_GLOBAL_TOKEN"
    config.github_token.get_secret_value.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 3: GitHubSyncEngine token parameter
# ---------------------------------------------------------------------------


def test_engine_uses_project_token_when_provided(tmp_path):
    """GitHubSyncEngine uses project-specific token when token param given."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"
    config.security_scanning_enabled = False
    config.project_path = str(tmp_path)

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
        patch("memory.connectors.github.sync.GitHubClient") as MockClient,
    ):
        GitHubSyncEngine(config, repo="org/repo", token="github_pat_PROJECT")

    # Verify GitHubClient was called with the project token, not the global one
    MockClient.assert_called_once_with(token="github_pat_PROJECT", repo="org/repo")


def test_engine_falls_back_to_global_token(tmp_path):
    """GitHubSyncEngine falls back to global token when no token param given."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"
    config.security_scanning_enabled = False
    config.project_path = str(tmp_path)
    config.github_branch = "main"

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
        patch("memory.connectors.github.sync.GitHubClient") as MockClient,
    ):
        GitHubSyncEngine(config, repo="org/repo")

    MockClient.assert_called_once_with(token="ghp_GLOBAL", repo="org/repo")


# ---------------------------------------------------------------------------
# Phase 3: run_sync_cycle passes resolved token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_cycle_passes_project_token():
    """run_sync_cycle passes per-project token to GitHubSyncEngine."""
    config = MagicMock()
    config.github_code_blob_enabled = False
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"

    project = MagicMock()
    project.github_enabled = True
    project.github_repo = "org/other-repo"
    project.github_branch = "main"
    project.github_token = "github_pat_PROJECT_SPECIFIC"

    mock_engine = AsyncMock()
    mock_engine.sync.return_value = MagicMock(
        issues_synced=1,
        prs_synced=0,
        commits_synced=0,
        ci_results_synced=0,
        errors=0,
    )

    with (
        patch(
            "memory.config.discover_projects",
            create=True,
            return_value={"other-proj": project},
        ),
        patch(
            "github_sync_service.GitHubSyncEngine",
            return_value=mock_engine,
        ) as MockEngine,
    ):
        result = await run_sync_cycle(config)

    assert result is True
    # Verify the engine was created with the project-specific token
    MockEngine.assert_called_once_with(
        config,
        repo="org/other-repo",
        branch="main",
        token="github_pat_PROJECT_SPECIFIC",
    )


@pytest.mark.asyncio
async def test_sync_cycle_skips_failed_projects():
    """run_sync_cycle skips projects in the skip_projects set."""
    config = MagicMock()
    config.github_code_blob_enabled = False
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"

    project = MagicMock()
    project.github_enabled = True
    project.github_repo = "org/repo"
    project.github_branch = "main"
    project.github_token = None

    with (
        patch(
            "memory.config.discover_projects",
            create=True,
            return_value={"skipped-proj": project},
        ),
        patch(
            "github_sync_service.GitHubSyncEngine",
        ) as MockEngine,
    ):
        result = await run_sync_cycle(config, skip_projects={"skipped-proj"})

    assert result is True
    # Engine should NOT be created for skipped project
    MockEngine.assert_not_called()


@pytest.mark.asyncio
async def test_sync_cycle_code_blob_uses_project_token():
    """run_sync_cycle passes per-project token to CodeBlobSync GitHubClient."""
    config = MagicMock()
    config.github_code_blob_enabled = True
    config.github_sync_total_timeout = 300
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"

    project = MagicMock()
    project.github_enabled = True
    project.github_repo = "org/other-repo"
    project.github_branch = "main"
    project.github_token = "github_pat_CODE_TOKEN"

    mock_engine = AsyncMock()
    mock_engine.sync.return_value = MagicMock(
        issues_synced=0,
        prs_synced=0,
        commits_synced=0,
        ci_results_synced=0,
        errors=0,
    )

    mock_code_result = MagicMock(
        files_synced=5,
        files_skipped=0,
        files_deleted=0,
        errors=0,
    )
    mock_code_sync = AsyncMock()
    mock_code_sync.sync_code_blobs.return_value = mock_code_result

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "memory.config.discover_projects",
            create=True,
            return_value={"code-proj": project},
        ),
        patch(
            "github_sync_service.GitHubSyncEngine",
            return_value=mock_engine,
        ),
        patch(
            "github_sync_service.GitHubClient",
            return_value=mock_client,
        ) as MockGHClient,
        patch(
            "github_sync_service.CodeBlobSync",
            return_value=mock_code_sync,
        ),
    ):
        result = await run_sync_cycle(config)

    assert result is True
    # Verify GitHubClient for code blobs was called with project token
    MockGHClient.assert_called_once_with(
        token="github_pat_CODE_TOKEN",
        repo="org/other-repo",
    )


# ---------------------------------------------------------------------------
# M-1: validate_project_tokens() tests (H-1: uses test_repo_access, M-6: specific exceptions)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_project_tokens_success():
    """validate_project_tokens returns empty set when all projects validate OK (M-1)."""
    config = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"

    project = MagicMock()
    project.github_enabled = True
    project.github_repo = "org/repo"
    project.github_token = None

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.test_repo_access = AsyncMock(
        return_value={"success": True, "status": 200, "repo": "org/repo"}
    )

    with (
        patch(
            "memory.config.discover_projects",
            create=True,
            return_value={"proj-ok": project},
        ),
        patch(
            "github_sync_service.GitHubClient",
            return_value=mock_client,
        ),
    ):
        failed = await validate_project_tokens(config)

    assert failed == set()
    mock_client.test_repo_access.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_project_tokens_failure_adds_to_set():
    """validate_project_tokens returns project ID in failed set when HTTP check fails (M-1)."""
    config = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"

    project = MagicMock()
    project.github_enabled = True
    project.github_repo = "org/private-repo"
    project.github_token = None

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.test_repo_access = AsyncMock(
        return_value={
            "success": False,
            "status": 404,
            "repo": "org/private-repo",
            "error": "GitHub API error 404: Not Found",
        }
    )

    with (
        patch(
            "memory.config.discover_projects",
            create=True,
            return_value={"proj-fail": project},
        ),
        patch(
            "github_sync_service.GitHubClient",
            return_value=mock_client,
        ),
    ):
        failed = await validate_project_tokens(config)

    assert "proj-fail" in failed
    assert len(failed) == 1


@pytest.mark.asyncio
async def test_validate_project_tokens_disabled_project_skipped():
    """validate_project_tokens skips projects with github_enabled=False (M-1)."""
    config = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"

    project = MagicMock()
    project.github_enabled = False
    project.github_repo = "org/repo"
    project.github_token = None

    with (
        patch(
            "memory.config.discover_projects",
            create=True,
            return_value={"disabled-proj": project},
        ),
        patch(
            "github_sync_service.GitHubClient",
        ) as MockGHClient,
    ):
        failed = await validate_project_tokens(config)

    assert failed == set()
    MockGHClient.assert_not_called()


@pytest.mark.asyncio
async def test_validate_project_tokens_exception_adds_to_set():
    """validate_project_tokens adds project to failed set on unexpected exception (M-1, M-6)."""
    config = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"

    project = MagicMock()
    project.github_enabled = True
    project.github_repo = "org/repo"
    project.github_token = None

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.test_repo_access = AsyncMock(
        side_effect=ConnectionError("Network unreachable")
    )

    with (
        patch(
            "memory.config.discover_projects",
            create=True,
            return_value={"exc-proj": project},
        ),
        patch(
            "github_sync_service.GitHubClient",
            return_value=mock_client,
        ),
    ):
        failed = await validate_project_tokens(config)

    assert "exc-proj" in failed
    assert len(failed) == 1


@pytest.mark.asyncio
async def test_validate_project_tokens_empty_projects():
    """validate_project_tokens returns empty set when no projects configured (M-1)."""
    config = MagicMock()

    with patch(
        "memory.config.discover_projects",
        create=True,
        return_value={},
    ):
        failed = await validate_project_tokens(config)

    assert failed == set()


@pytest.mark.asyncio
async def test_validate_project_tokens_timeout_adds_to_set():
    """validate_project_tokens returns project ID when validation times out (M-6)."""
    import asyncio

    config = MagicMock()
    config.github_token.get_secret_value.return_value = "ghp_GLOBAL"
    project = MagicMock()
    project.github_enabled = True
    project.github_repo = "org/slow-repo"
    project.github_token = None
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with (
        patch(
            "memory.config.discover_projects",
            create=True,
            return_value={"timeout-proj": project},
        ),
        patch("github_sync_service.GitHubClient", return_value=mock_client),
    ):
        failed = await validate_project_tokens(config)
    assert "timeout-proj" in failed
