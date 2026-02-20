"""Tests for GitHub sync service container entrypoint (SPEC-008 Section 3.3)."""

import signal
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add scripts directory to path for importing the service module
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

import github_sync_service
from github_sync_service import handle_signal, main, run_sync_cycle


@pytest.fixture(autouse=True)
def _reset_shutdown_flag():
    """Reset SHUTDOWN_REQUESTED before and after each test."""
    github_sync_service.SHUTDOWN_REQUESTED = False
    yield
    github_sync_service.SHUTDOWN_REQUESTED = False


# -- run_sync_cycle Tests -----------------------------------------------


@pytest.mark.asyncio
async def test_run_sync_cycle_both_engines():
    """Both GitHubSyncEngine and CodeBlobSync called in sequence."""
    config = MagicMock()
    config.github_code_blob_enabled = True
    config.github_token.get_secret_value.return_value = "ghp_test"
    config.github_repo = "owner/repo"

    mock_engine = AsyncMock()
    mock_engine.sync.return_value = MagicMock(
        issues_synced=5,
        prs_synced=3,
        commits_synced=10,
        ci_results_synced=2,
        errors=0,
    )

    mock_code_result = MagicMock(
        files_synced=10,
        files_skipped=5,
        files_deleted=1,
        errors=0,
    )
    mock_code_sync = AsyncMock()
    mock_code_sync.sync_code_blobs.return_value = mock_code_result

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(
            github_sync_service, "GitHubSyncEngine", return_value=mock_engine
        ) as mock_eng_cls,
        patch.object(github_sync_service, "GitHubClient") as mock_client_cls,
        patch.object(
            github_sync_service, "CodeBlobSync", return_value=mock_code_sync
        ) as mock_cs_cls,
    ):
        mock_client_cls.return_value = mock_client
        mock_client_cls.generate_batch_id.return_value = "batch-1"
        result = await run_sync_cycle(config)

    assert result is True
    mock_eng_cls.assert_called_once_with(config)
    mock_engine.sync.assert_awaited_once()
    mock_cs_cls.assert_called_once_with(mock_client, config)
    mock_code_sync.sync_code_blobs.assert_awaited_once_with("batch-1")


@pytest.mark.asyncio
async def test_run_sync_cycle_code_disabled():
    """CodeBlobSync skipped when github_code_blob_enabled=False."""
    config = MagicMock()
    config.github_code_blob_enabled = False

    mock_engine = AsyncMock()
    mock_engine.sync.return_value = MagicMock(
        issues_synced=5,
        prs_synced=3,
        commits_synced=10,
        ci_results_synced=2,
        errors=0,
    )

    with (
        patch.object(github_sync_service, "GitHubSyncEngine", return_value=mock_engine),
        patch.object(github_sync_service, "GitHubClient") as mock_client_cls,
        patch.object(github_sync_service, "CodeBlobSync") as mock_cs_cls,
    ):
        result = await run_sync_cycle(config)

    assert result is True
    mock_engine.sync.assert_awaited_once()
    mock_client_cls.assert_not_called()
    mock_cs_cls.assert_not_called()


@pytest.mark.asyncio
async def test_run_sync_cycle_engine_failure_continues():
    """Engine failure doesn't prevent code blob sync."""
    config = MagicMock()
    config.github_code_blob_enabled = True
    config.github_token.get_secret_value.return_value = "ghp_test"
    config.github_repo = "owner/repo"

    mock_engine = AsyncMock()
    mock_engine.sync.side_effect = RuntimeError("Engine failed")

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
        patch.object(github_sync_service, "GitHubSyncEngine", return_value=mock_engine),
        patch.object(github_sync_service, "GitHubClient") as mock_client_cls,
        patch.object(github_sync_service, "CodeBlobSync", return_value=mock_code_sync),
    ):
        mock_client_cls.return_value = mock_client
        mock_client_cls.generate_batch_id.return_value = "batch-1"
        result = await run_sync_cycle(config)

    # Engine failed so sync_ok is False, but code blob sync still ran
    assert result is False
    mock_code_sync.sync_code_blobs.assert_awaited_once_with("batch-1")


# -- Signal Handling Tests -----------------------------------------------


def test_shutdown_signal_stops_loop():
    """SIGTERM sets SHUTDOWN_REQUESTED flag."""
    assert github_sync_service.SHUTDOWN_REQUESTED is False
    handle_signal(signal.SIGTERM, None)
    assert github_sync_service.SHUTDOWN_REQUESTED is True


# -- Health File Tests ---------------------------------------------------


def test_health_file_written_on_success():
    """Health file created after successful sync."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_sync_interval = 1
    config.github_repo = "owner/repo"

    def mock_asyncio_run(coro):
        if hasattr(coro, "close"):
            coro.close()
        return True

    with (
        patch.object(github_sync_service, "get_config", return_value=config),
        patch("github_sync_service.asyncio.run", side_effect=mock_asyncio_run),
        patch(
            "github_sync_service.time.sleep",
            side_effect=lambda s: setattr(
                github_sync_service, "SHUTDOWN_REQUESTED", True
            ),
        ),
        patch("github_sync_service.signal.signal"),
        patch.object(github_sync_service, "write_health_file") as mock_write,
    ):
        main()

    mock_write.assert_called_once()


def test_health_file_written_on_failure():
    """BUG-111: Health file IS created even when sync fails (service is alive)."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_sync_interval = 1
    config.github_repo = "owner/repo"

    def mock_asyncio_run(coro):
        if hasattr(coro, "close"):
            coro.close()
        return False

    with (
        patch.object(github_sync_service, "get_config", return_value=config),
        patch("github_sync_service.asyncio.run", side_effect=mock_asyncio_run),
        patch(
            "github_sync_service.time.sleep",
            side_effect=lambda s: setattr(
                github_sync_service, "SHUTDOWN_REQUESTED", True
            ),
        ),
        patch("github_sync_service.signal.signal"),
        patch.object(github_sync_service, "write_health_file") as mock_write,
    ):
        main()

    # BUG-111: Health file indicates "service is alive", not "last sync was perfect"
    mock_write.assert_called_once()


def test_warning_logged_on_sync_failure():
    """BUG-111: Warning logged when sync cycle fails."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_sync_interval = 1
    config.github_repo = "owner/repo"

    def mock_asyncio_run(coro):
        if hasattr(coro, "close"):
            coro.close()
        return False

    with (
        patch.object(github_sync_service, "get_config", return_value=config),
        patch("github_sync_service.asyncio.run", side_effect=mock_asyncio_run),
        patch(
            "github_sync_service.time.sleep",
            side_effect=lambda s: setattr(
                github_sync_service, "SHUTDOWN_REQUESTED", True
            ),
        ),
        patch("github_sync_service.signal.signal"),
        patch.object(github_sync_service, "write_health_file"),
        patch.object(github_sync_service.logger, "warning") as mock_warning,
    ):
        main()

    # BUG-111: Warning should be logged when sync fails
    mock_warning.assert_called_once()
    assert "errors" in mock_warning.call_args[0][0].lower() or "error" in mock_warning.call_args[0][0].lower()


# -- Config Validation Tests ---------------------------------------------


def test_config_validation_fails_without_github_enabled():
    """Service exits if GITHUB_SYNC_ENABLED != true."""
    config = MagicMock()
    config.github_sync_enabled = False

    with (
        patch.object(github_sync_service, "get_config", return_value=config),
        patch("github_sync_service.signal.signal"),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
