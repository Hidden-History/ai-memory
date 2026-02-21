"""Tests for GitHub sync CLI script (SPEC-008 Section 3.4)."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add scripts directory to path for importing the CLI module
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

import github_sync
from github_sync import main

# -- Status Display Tests -----------------------------------------------


def test_status_display(capsys, tmp_path, monkeypatch):
    """--status shows sync state."""
    monkeypatch.chdir(tmp_path)

    # Create state directory and file
    state_dir = tmp_path / ".audit" / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "github_sync_state.json"
    state_file.write_text(
        '{"issues": {"last_synced": "2026-01-01T00:00:00", "last_count": 42}}'
    )

    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_code_blob_enabled = True
    config.github_sync_interval = 1800

    with (
        patch.object(github_sync, "get_config", return_value=config),
        patch("sys.argv", ["github_sync.py", "--status"]),
    ):
        main()

    output = capsys.readouterr().out
    assert "GitHub Sync Status" in output
    assert "owner/repo" in output
    assert "issues" in output
    assert "last_synced=2026-01-01T00:00:00" in output


# -- Sync Mode Tests ----------------------------------------------------


def test_full_sync_uses_full_mode():
    """--full passes mode="full" to engine."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_code_blob_enabled = False

    mock_engine = AsyncMock()
    mock_result = MagicMock(
        issues_synced=5,
        comments_synced=2,
        prs_synced=3,
        reviews_synced=1,
        diffs_synced=4,
        commits_synced=10,
        ci_results_synced=2,
        items_skipped=1,
        errors=0,
        duration_seconds=5.0,
    )
    mock_engine.sync.return_value = mock_result

    with (
        patch.object(github_sync, "get_config", return_value=config),
        patch.object(github_sync, "GitHubSyncEngine", return_value=mock_engine),
        patch("sys.argv", ["github_sync.py", "--full"]),
    ):
        main()

    mock_engine.sync.assert_awaited_once_with(mode="full")


def test_code_only_skips_engine():
    """--code-only only runs CodeBlobSync."""
    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_branch = "main"
    config.github_code_blob_enabled = True
    config.github_token.get_secret_value.return_value = "ghp_test"

    mock_code_sync = AsyncMock()
    mock_code_result = MagicMock(
        files_synced=5,
        files_skipped=0,
        files_deleted=0,
        errors=0,
    )
    mock_code_sync.sync_code_blobs.return_value = mock_code_result

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(github_sync, "get_config", return_value=config),
        patch.object(github_sync, "GitHubSyncEngine") as mock_engine_cls,
        patch.object(github_sync, "GitHubClient") as mock_client_cls,
        patch.object(github_sync, "CodeBlobSync", return_value=mock_code_sync),
        patch("sys.argv", ["github_sync.py", "--code-only"]),
    ):
        mock_client_cls.return_value = mock_client
        mock_client_cls.generate_batch_id.return_value = "batch-1"
        main()

    mock_engine_cls.assert_not_called()
    mock_code_sync.sync_code_blobs.assert_awaited_once_with(
        "batch-1", total_timeout=config.github_sync_total_timeout
    )


# -- Config Validation Tests ---------------------------------------------


def test_disabled_exits_with_error():
    """Exits with code 1 when not enabled."""
    config = MagicMock()
    config.github_sync_enabled = False

    with (
        patch.object(github_sync, "get_config", return_value=config),
        patch("sys.argv", ["github_sync.py", "--full"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
