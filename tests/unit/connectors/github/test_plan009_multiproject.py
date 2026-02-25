"""Tests for PLAN-009 Phase 2: Multi-project GitHub sync parameterization.

Covers:
- GitHubSyncEngine(config, repo=...) param override
- GitHubSyncEngine(config) backward compat
- Per-repo state file naming
- CodeBlobSync(client, config, repo=...) param override
- CodeBlobSync(client, config) backward compat
- run_sync_cycle iterates over projects.d/ via mocked discover_projects
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Allow importing github_sync_service from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

import github_sync_service
from github_sync_service import run_sync_cycle

from memory.connectors.github.code_sync import CodeBlobSync
from memory.connectors.github.sync import GitHubSyncEngine


@pytest.fixture(autouse=True)
def _reset_shutdown_flag():
    """Reset SHUTDOWN_REQUESTED before and after each test."""
    github_sync_service.SHUTDOWN_REQUESTED = False
    yield
    github_sync_service.SHUTDOWN_REQUESTED = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path | None = None, repo: str = "owner/repo") -> MagicMock:
    """Create a minimal MemoryConfig mock for GitHubSyncEngine init."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = repo
    config.github_token.get_secret_value.return_value = "ghp_test"
    config.security_scanning_enabled = False
    config.project_path = str(tmp_path) if tmp_path else "/tmp/test"
    return config


def _make_project(repo: str = "owner/repo", github_enabled: bool = True) -> MagicMock:
    """Create a mock ProjectSyncConfig-like object."""
    p = MagicMock()
    p.github_enabled = github_enabled
    p.github_repo = repo
    return p


# ---------------------------------------------------------------------------
# GitHubSyncEngine — repo parameter
# ---------------------------------------------------------------------------


def test_engine_repo_param_overrides_config(tmp_path):
    """GitHubSyncEngine(config, repo='org/repo') sets self.repo and _group_id."""
    config = _make_config(tmp_path, repo="default/repo")

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
        patch("memory.connectors.github.sync.GitHubClient"),
    ):
        engine = GitHubSyncEngine(config, repo="org/repo")

    assert engine.repo == "org/repo"
    assert engine._group_id == "org/repo"


def test_engine_backward_compat_uses_config_repo(tmp_path):
    """GitHubSyncEngine(config) falls back to config.github_repo."""
    config = _make_config(tmp_path, repo="owner/repo")

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
        patch("memory.connectors.github.sync.GitHubClient"),
    ):
        engine = GitHubSyncEngine(config)

    assert engine.repo == "owner/repo"
    assert engine._group_id == "owner/repo"


def test_engine_no_repo_raises(tmp_path):
    """GitHubSyncEngine raises ValueError when no repo param and config.github_repo is falsy."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = None
    config.github_token.get_secret_value.return_value = "ghp_test"
    config.security_scanning_enabled = False
    config.project_path = str(tmp_path)

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
        patch("memory.connectors.github.sync.GitHubClient"),
        pytest.raises(ValueError, match="No repo specified"),
    ):
        GitHubSyncEngine(config)


def test_engine_per_repo_state_file_slash_and_dash(tmp_path):
    """State file replaces '/' with '__' for safe filenames; '-' is preserved."""
    config = _make_config(tmp_path)

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
        patch("memory.connectors.github.sync.GitHubClient"),
    ):
        engine = GitHubSyncEngine(config, repo="org/my-repo")

    assert engine._state_file.name == "github_sync_state_org__my-repo.json"


def test_engine_state_file_default_uses_config_repo(tmp_path):
    """State file uses sanitised config.github_repo when no repo param."""
    config = _make_config(tmp_path, repo="owner/my-project")

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
        patch("memory.connectors.github.sync.GitHubClient"),
    ):
        engine = GitHubSyncEngine(config)

    assert engine._state_file.name == "github_sync_state_owner__my-project.json"


def test_engine_different_repos_get_different_state_files(tmp_path):
    """Two engines with different repos use isolated state files."""
    config = _make_config(tmp_path)

    with (
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
        patch("memory.connectors.github.sync.GitHubClient"),
    ):
        engine_a = GitHubSyncEngine(config, repo="org/repo-a")
        engine_b = GitHubSyncEngine(config, repo="org/repo-b")

    assert engine_a._state_file.name != engine_b._state_file.name
    assert "repo-a" in engine_a._state_file.name
    assert "repo-b" in engine_b._state_file.name


# ---------------------------------------------------------------------------
# CodeBlobSync — repo parameter
# ---------------------------------------------------------------------------


def _make_code_sync(config: MagicMock, repo: str | None = None) -> CodeBlobSync:
    """Construct CodeBlobSync with all heavy deps mocked."""
    client = MagicMock()
    with (
        patch("memory.connectors.github.code_sync.MemoryStorage"),
        patch("memory.connectors.github.code_sync.get_qdrant_client"),
        patch("memory.classifier.circuit_breaker.CircuitBreaker"),
    ):
        return CodeBlobSync(client, config, repo=repo)


def test_code_blob_sync_repo_param_overrides_config():
    """CodeBlobSync(client, config, repo='org/repo') sets _group_id."""
    config = MagicMock()
    config.github_repo = "default/repo"
    config.github_code_blob_exclude = ""
    config.security_scanning_enabled = False
    config.github_sync_circuit_breaker_threshold = 5
    config.github_sync_circuit_breaker_reset = 60

    sync = _make_code_sync(config, repo="org/repo")

    assert sync._group_id == "org/repo"


def test_code_blob_sync_backward_compat():
    """CodeBlobSync(client, config) falls back to config.github_repo."""
    config = MagicMock()
    config.github_repo = "owner/repo"
    config.github_code_blob_exclude = ""
    config.security_scanning_enabled = False
    config.github_sync_circuit_breaker_threshold = 5
    config.github_sync_circuit_breaker_reset = 60

    sync = _make_code_sync(config)

    assert sync._group_id == "owner/repo"


def test_code_blob_sync_group_id_used_for_qdrant_filters():
    """_group_id (not config.github_repo) is used in blob map scroll."""
    config = MagicMock()
    config.github_repo = "default/repo"
    config.github_code_blob_exclude = ""
    config.security_scanning_enabled = False
    config.github_sync_circuit_breaker_threshold = 5
    config.github_sync_circuit_breaker_reset = 60

    mock_qdrant = MagicMock()
    mock_qdrant.scroll.return_value = ([], None)

    client = MagicMock()
    with (
        patch("memory.connectors.github.code_sync.MemoryStorage"),
        patch(
            "memory.connectors.github.code_sync.get_qdrant_client",
            return_value=mock_qdrant,
        ),
        patch("memory.classifier.circuit_breaker.CircuitBreaker"),
    ):
        sync = CodeBlobSync(client, config, repo="override/repo")

    # Trigger _get_stored_blob_map which uses _group_id in the filter
    sync._get_stored_blob_map()

    # Verify the scroll was called with group_id="override/repo"
    call_kwargs = mock_qdrant.scroll.call_args
    scroll_filter = call_kwargs[1]["scroll_filter"] if call_kwargs else None
    assert scroll_filter is not None
    # At least one must-filter should match "override/repo"
    must_conditions = scroll_filter.must
    group_id_values = [
        c.match.value
        for c in must_conditions
        if hasattr(c, "match") and hasattr(c.match, "value")
    ]
    assert "override/repo" in group_id_values


# ---------------------------------------------------------------------------
# run_sync_cycle — multi-project with mocked discover_projects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sync_cycle_no_projects_returns_true():
    """Returns True (no-op success) when discover_projects returns empty dict."""
    config = MagicMock()

    with patch("memory.config.discover_projects", return_value={}):
        result = await run_sync_cycle(config)

    assert result is True


@pytest.mark.asyncio
async def test_run_sync_cycle_iterates_all_github_projects():
    """run_sync_cycle spawns one GitHubSyncEngine per enabled project."""
    config = MagicMock()
    config.github_code_blob_enabled = False

    projects = {
        "proj-a": _make_project("org/repo-a"),
        "proj-b": _make_project("org/repo-b"),
    }

    mock_engine = AsyncMock()
    mock_engine.sync.return_value = MagicMock(
        issues_synced=1, prs_synced=0, commits_synced=0, ci_results_synced=0, errors=0
    )

    engine_repos: list[str] = []

    def make_engine(cfg, repo=None, branch=None):
        engine_repos.append(repo)
        return mock_engine

    with (
        patch("memory.config.discover_projects", return_value=projects),
        patch.object(github_sync_service, "GitHubSyncEngine", side_effect=make_engine),
    ):
        result = await run_sync_cycle(config)

    assert result is True
    assert sorted(engine_repos) == ["org/repo-a", "org/repo-b"]


@pytest.mark.asyncio
async def test_run_sync_cycle_skips_github_disabled_projects():
    """Projects with github_enabled=False are skipped entirely."""
    config = MagicMock()
    config.github_code_blob_enabled = False

    projects = {
        "enabled": _make_project("org/active", github_enabled=True),
        "disabled": _make_project("org/inactive", github_enabled=False),
    }

    mock_engine = AsyncMock()
    mock_engine.sync.return_value = MagicMock(
        issues_synced=0, prs_synced=0, commits_synced=0, ci_results_synced=0, errors=0
    )

    engine_repos: list[str] = []

    def make_engine(cfg, repo=None, branch=None):
        engine_repos.append(repo)
        return mock_engine

    with (
        patch("memory.config.discover_projects", return_value=projects),
        patch.object(github_sync_service, "GitHubSyncEngine", side_effect=make_engine),
    ):
        result = await run_sync_cycle(config)

    assert result is True
    assert engine_repos == ["org/active"]


@pytest.mark.asyncio
async def test_run_sync_cycle_code_blobs_per_project():
    """Code blob sync runs per-project with the project-specific repo."""
    config = MagicMock()
    config.github_code_blob_enabled = True
    config.github_token.get_secret_value.return_value = "ghp_test"

    projects = {"proj": _make_project("org/targeted-repo")}

    mock_engine = AsyncMock()
    mock_engine.sync.return_value = MagicMock(
        issues_synced=1, prs_synced=0, commits_synced=0, ci_results_synced=0, errors=0
    )

    mock_code_result = MagicMock(
        files_synced=3, files_skipped=1, files_deleted=0, errors=0
    )
    mock_code_sync = AsyncMock()
    mock_code_sync.sync_code_blobs.return_value = mock_code_result

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    code_sync_repos: list[str] = []
    client_repos: list[str] = []

    def make_code_sync(client, cfg, repo=None, branch=None):
        code_sync_repos.append(repo)
        return mock_code_sync

    def make_client(**kwargs):
        client_repos.append(kwargs.get("repo"))
        return mock_client

    with (
        patch("memory.config.discover_projects", return_value=projects),
        patch.object(github_sync_service, "GitHubSyncEngine", return_value=mock_engine),
        patch.object(
            github_sync_service, "GitHubClient", side_effect=make_client
        ) as mock_client_cls,
        patch.object(github_sync_service, "CodeBlobSync", side_effect=make_code_sync),
    ):
        mock_client_cls.generate_batch_id.return_value = "batch-xyz"
        result = await run_sync_cycle(config)

    assert result is True
    assert code_sync_repos == ["org/targeted-repo"]
    assert client_repos == ["org/targeted-repo"]


@pytest.mark.asyncio
async def test_run_sync_cycle_partial_failure_continues():
    """A sync failure for one project marks result False but continues others."""
    config = MagicMock()
    config.github_code_blob_enabled = False

    projects = {
        "proj-a": _make_project("org/repo-a"),
        "proj-b": _make_project("org/repo-b"),
    }

    call_count = [0]

    async def engine_sync_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("First project sync failed")
        return MagicMock(
            issues_synced=5,
            prs_synced=0,
            commits_synced=0,
            ci_results_synced=0,
            errors=0,
        )

    mock_engine = AsyncMock()
    mock_engine.sync.side_effect = engine_sync_side_effect

    with (
        patch("memory.config.discover_projects", return_value=projects),
        patch.object(github_sync_service, "GitHubSyncEngine", return_value=mock_engine),
    ):
        result = await run_sync_cycle(config)

    # One failure → sync_ok=False, but both projects were attempted
    assert result is False
    assert call_count[0] == 2


@pytest.mark.asyncio
async def test_run_sync_cycle_skips_project_without_repo(tmp_path):
    """Project with github_enabled=True but github_repo=None is skipped."""
    config = _make_config(tmp_path)
    project = _make_project("")  # empty repo string
    with (
        patch("memory.config.discover_projects", return_value={"jira-only": project}),
        patch.object(github_sync_service, "GitHubSyncEngine") as mock_engine_cls,
    ):
        result = await run_sync_cycle(config)
    mock_engine_cls.assert_not_called()
    assert result is True
