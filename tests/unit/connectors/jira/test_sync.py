"""Unit tests for Jira sync engine.

Tests JiraSyncEngine with:
- Full vs incremental sync modes
- Per-issue error recovery (fail-open)
- Comment update pattern (delete + insert)
- Content hash deduplication via MemoryStorage
- Sync state persistence
- group_id extraction from instance URL
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, call
from urllib.parse import urlparse

from src.memory.connectors.jira.sync import JiraSyncEngine, SyncResult


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_config(tmp_path):
    """Mock MemoryConfig with Jira settings."""
    config = Mock()
    config.jira_sync_enabled = True
    config.jira_instance_url = "https://company.atlassian.net"
    config.jira_email = "test@example.com"
    config.jira_api_token = Mock()
    config.jira_api_token.get_secret_value.return_value = "test-token"
    config.jira_projects = ["PROJ"]
    config.jira_sync_delay_ms = 0
    config.install_dir = tmp_path
    config.similarity_threshold = 0.7
    config.hnsw_ef_accurate = 128
    return config


@pytest.fixture
def mock_jira_client():
    """Mock JiraClient."""
    client = AsyncMock()
    client.search_issues = AsyncMock(return_value=[])
    client.get_comments = AsyncMock(return_value=[])
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_storage():
    """Mock MemoryStorage."""
    storage = Mock()
    storage.store_memory = Mock(return_value={"status": "stored", "memory_id": "mem-123"})
    return storage


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client."""
    qdrant = Mock()
    qdrant.scroll = Mock(return_value=([],None))
    qdrant.delete = Mock()
    return qdrant


# =============================================================================
# Initialization Tests
# =============================================================================


class TestInitialization:
    """Test sync engine initialization."""

    def test_init_with_config(self, mock_config):
        """Initialize with provided config."""
        with patch("src.memory.connectors.jira.sync.JiraClient"):
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        engine = JiraSyncEngine(config=mock_config)

        assert engine.config == mock_config

    def test_group_id_extracted_from_url(self, mock_config):
        """group_id extracted from Jira instance URL hostname."""
        with patch("src.memory.connectors.jira.sync.JiraClient"):
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        engine = JiraSyncEngine(config=mock_config)

        assert engine.group_id == "company.atlassian.net"

    def test_init_jira_not_enabled_raises(self, mock_config):
        """Initialization fails if Jira sync not enabled."""
        mock_config.jira_sync_enabled = False

        with pytest.raises(ValueError, match="not enabled"):
            JiraSyncEngine(config=mock_config)

    def test_init_missing_instance_url_raises(self, mock_config):
        """Initialization fails if instance URL not configured."""
        mock_config.jira_instance_url = None

        with pytest.raises(ValueError, match="JIRA_INSTANCE_URL"):
            JiraSyncEngine(config=mock_config)

    def test_init_missing_email_raises(self, mock_config):
        """Initialization fails if email not configured."""
        mock_config.jira_email = None

        with pytest.raises(ValueError, match="JIRA_EMAIL"):
            JiraSyncEngine(config=mock_config)

    def test_init_missing_api_token_raises(self, mock_config):
        """Initialization fails if API token not configured."""
        mock_config.jira_api_token.get_secret_value.return_value = ""

        with pytest.raises(ValueError, match="JIRA_API_TOKEN"):
            JiraSyncEngine(config=mock_config)


# =============================================================================
# Sync Modes
# =============================================================================


class TestSyncModes:
    """Test full vs incremental sync modes."""

    @pytest.mark.asyncio
    async def test_full_mode_jql(self, mock_config):
        """Full mode generates JQL without updated filter."""
        with patch("src.memory.connectors.jira.sync.JiraClient") as mock_client_cls:
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        mock_client = AsyncMock()
                        mock_client.search_issues = AsyncMock(return_value=[])
                        mock_client.close = AsyncMock()
                        mock_client_cls.return_value = mock_client

                        engine = JiraSyncEngine(config=mock_config)
                        updated_since = engine._get_updated_since("PROJ", "full")

        # Full mode: no updated filter
        assert updated_since is None

    @pytest.mark.asyncio
    async def test_incremental_mode_with_last_synced(self, mock_config, tmp_path):
        """Incremental mode uses last_synced timestamp."""
        # Create state file with last_synced
        state_file = tmp_path / "jira_sync_state.json"
        state_file.write_text(
            json.dumps({
                "version": "1.0",
                "projects": {
                    "PROJ": {
                        "last_synced": "2026-02-01T00:00:00+00:00",
                        "last_issue_count": 5,
                        "last_comment_count": 10,
                    }
                },
            })
        )

        with patch("src.memory.connectors.jira.sync.JiraClient"):
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        engine = JiraSyncEngine(config=mock_config)
                        updated_since = engine._get_updated_since("PROJ", "incremental")

        # Incremental mode: returns last_synced timestamp
        assert updated_since == "2026-02-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_incremental_fallback_to_full(self, mock_config):
        """Incremental mode falls back to full if no previous sync."""
        with patch("src.memory.connectors.jira.sync.JiraClient"):
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        engine = JiraSyncEngine(config=mock_config)
                        updated_since = engine._get_updated_since("PROJ", "incremental")

        # No previous sync: falls back to full (returns None)
        assert updated_since is None


# =============================================================================
# Per-Issue Error Recovery
# =============================================================================


class TestPerIssueErrorRecovery:
    """Test fail-open error handling."""

    @pytest.mark.asyncio
    async def test_single_issue_fails_others_continue(self, mock_config):
        """Single issue failure doesn't block other issues."""
        issues = [
            {"key": "PROJ-1", "fields": {"summary": "Issue 1", "issuetype": {"name": "Task"}, "status": {"name": "Open"}, "priority": None, "reporter": None, "creator": None, "labels": [], "updated": "2026-02-01T00:00:00Z"}},
            {"key": "PROJ-2", "fields": {"summary": "Issue 2", "issuetype": {"name": "Task"}, "status": {"name": "Open"}, "priority": None, "reporter": None, "creator": None, "labels": [], "updated": "2026-02-01T00:00:00Z"}},
            {"key": "PROJ-3", "fields": {"summary": "Issue 3", "issuetype": {"name": "Task"}, "status": {"name": "Open"}, "priority": None, "reporter": None, "creator": None, "labels": [], "updated": "2026-02-01T00:00:00Z"}},
        ]

        with patch("src.memory.connectors.jira.sync.JiraClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.search_issues = AsyncMock(return_value=issues)
            mock_client.get_comments = AsyncMock(return_value=[])
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            with patch("src.memory.connectors.jira.sync.MemoryStorage") as mock_storage_cls:
                mock_storage = Mock()
                # PROJ-2 fails, others succeed
                mock_storage.store_memory = Mock(
                    side_effect=[
                        {"status": "stored"},  # PROJ-1 succeeds
                        Exception("Storage error"),  # PROJ-2 fails
                        {"status": "stored"},  # PROJ-3 succeeds
                    ]
                )
                mock_storage_cls.return_value = mock_storage

                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        with patch("src.memory.connectors.jira.sync.compose_issue_document", return_value="doc"):
                            engine = JiraSyncEngine(config=mock_config)
                            result = await engine.sync_project("PROJ")

        # 2 issues synced, 1 error
        assert result.issues_synced == 2
        assert len(result.errors) == 1
        assert "PROJ-2" in result.errors[0]

    @pytest.mark.asyncio
    async def test_errors_accumulated_in_result(self, mock_config):
        """All errors accumulated in SyncResult."""
        issues = [
            {"key": "PROJ-1", "fields": {"summary": "Issue 1", "issuetype": {"name": "Task"}, "status": {"name": "Open"}, "priority": None, "reporter": None, "creator": None, "labels": [], "updated": "2026-02-01T00:00:00Z"}},
            {"key": "PROJ-2", "fields": {"summary": "Issue 2", "issuetype": {"name": "Task"}, "status": {"name": "Open"}, "priority": None, "reporter": None, "creator": None, "labels": [], "updated": "2026-02-01T00:00:00Z"}},
        ]

        with patch("src.memory.connectors.jira.sync.JiraClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.search_issues = AsyncMock(return_value=issues)
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            with patch("src.memory.connectors.jira.sync.MemoryStorage") as mock_storage_cls:
                mock_storage = Mock()
                # Both issues fail
                mock_storage.store_memory = Mock(
                    side_effect=[
                        Exception("Error 1"),
                        Exception("Error 2"),
                    ]
                )
                mock_storage_cls.return_value = mock_storage

                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        with patch("src.memory.connectors.jira.sync.compose_issue_document", return_value="doc"):
                            engine = JiraSyncEngine(config=mock_config)
                            result = await engine.sync_project("PROJ")

        # 0 issues synced, 2 errors
        assert result.issues_synced == 0
        assert len(result.errors) == 2


# =============================================================================
# Comment Update Pattern
# =============================================================================


class TestCommentUpdate:
    """Test delete + insert pattern for comments."""

    @pytest.mark.asyncio
    async def test_delete_old_comments_called(self, mock_config):
        """Old comments deleted before inserting new ones."""
        issues = [
            {"key": "PROJ-1", "fields": {"summary": "Issue 1", "issuetype": {"name": "Bug"}, "status": {"name": "Open"}, "updated": "2026-02-01T00:00:00Z"}}
        ]
        comments = [{"id": "10001", "author": {"displayName": "Alice"}, "created": "2026-02-01T00:00:00Z", "body": None}]

        with patch("src.memory.connectors.jira.sync.JiraClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.search_issues = AsyncMock(return_value=issues)
            mock_client.get_comments = AsyncMock(return_value=comments)
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            with patch("src.memory.connectors.jira.sync.MemoryStorage") as mock_storage_cls:
                mock_storage = Mock()
                mock_storage.store_memory = Mock(return_value={"status": "stored"})
                mock_storage_cls.return_value = mock_storage

                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client") as mock_qdrant_fn:
                        mock_qdrant = Mock()
                        mock_qdrant.scroll = Mock(return_value=([Mock(id="point-1")], None))
                        mock_qdrant.delete = Mock()
                        mock_qdrant_fn.return_value = mock_qdrant

                        with patch("src.memory.connectors.jira.sync.compose_issue_document", return_value="issue doc"):
                            with patch("src.memory.connectors.jira.sync.compose_comment_document", return_value="comment doc"):
                                engine = JiraSyncEngine(config=mock_config)
                                await engine.sync_project("PROJ")

        # Verify delete called
        mock_qdrant.delete.assert_called()

    @pytest.mark.asyncio
    async def test_insert_new_comments(self, mock_config):
        """New comments inserted after deletion."""
        issues = [
            {"key": "PROJ-1", "fields": {"summary": "Issue 1", "issuetype": {"name": "Bug"}, "status": {"name": "Open"}, "updated": "2026-02-01T00:00:00Z"}}
        ]
        comments = [
            {"id": "10001", "author": {"displayName": "Alice"}, "created": "2026-02-01T00:00:00Z", "body": None},
            {"id": "10002", "author": {"displayName": "Bob"}, "created": "2026-02-02T00:00:00Z", "body": None},
        ]

        with patch("src.memory.connectors.jira.sync.JiraClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.search_issues = AsyncMock(return_value=issues)
            mock_client.get_comments = AsyncMock(return_value=comments)
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            with patch("src.memory.connectors.jira.sync.MemoryStorage") as mock_storage_cls:
                mock_storage = Mock()
                mock_storage.store_memory = Mock(return_value={"status": "stored"})
                mock_storage_cls.return_value = mock_storage

                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client") as mock_qdrant_fn:
                        mock_qdrant = Mock()
                        mock_qdrant.scroll = Mock(return_value=([], None))
                        mock_qdrant_fn.return_value = mock_qdrant

                        with patch("src.memory.connectors.jira.sync.compose_issue_document", return_value="issue doc"):
                            with patch("src.memory.connectors.jira.sync.compose_comment_document", return_value="comment doc"):
                                engine = JiraSyncEngine(config=mock_config)
                                result = await engine.sync_project("PROJ")

        # Verify comments synced
        assert result.comments_synced == 2

    @pytest.mark.asyncio
    async def test_per_comment_fail_open(self, mock_config):
        """Per-comment failures don't block other comments."""
        issues = [
            {"key": "PROJ-1", "fields": {"summary": "Issue 1", "issuetype": {"name": "Bug"}, "status": {"name": "Open"}, "updated": "2026-02-01T00:00:00Z"}}
        ]
        comments = [
            {"id": "10001", "author": {"displayName": "Alice"}, "created": "2026-02-01T00:00:00Z", "body": None},
            {"id": "10002", "author": {"displayName": "Bob"}, "created": "2026-02-02T00:00:00Z", "body": None},
        ]

        with patch("src.memory.connectors.jira.sync.JiraClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.search_issues = AsyncMock(return_value=issues)
            mock_client.get_comments = AsyncMock(return_value=comments)
            mock_client.close = AsyncMock()
            mock_client_cls.return_value = mock_client

            with patch("src.memory.connectors.jira.sync.MemoryStorage") as mock_storage_cls:
                mock_storage = Mock()
                # First comment fails, second succeeds (issue succeeds)
                mock_storage.store_memory = Mock(
                    side_effect=[
                        {"status": "stored"},  # Issue
                        Exception("Comment 1 error"),  # Comment 1 fails
                        {"status": "stored"},  # Comment 2 succeeds
                    ]
                )
                mock_storage_cls.return_value = mock_storage

                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client") as mock_qdrant_fn:
                        mock_qdrant = Mock()
                        mock_qdrant.scroll = Mock(return_value=([], None))
                        mock_qdrant_fn.return_value = mock_qdrant

                        with patch("src.memory.connectors.jira.sync.compose_issue_document", return_value="issue doc"):
                            with patch("src.memory.connectors.jira.sync.compose_comment_document", return_value="comment doc"):
                                engine = JiraSyncEngine(config=mock_config)
                                result = await engine.sync_project("PROJ")

        # 1 comment synced (out of 2)
        assert result.comments_synced == 1


# =============================================================================
# Sync State Persistence
# =============================================================================


class TestStatePersistence:
    """Test sync state file management."""

    def test_state_file_creation(self, mock_config):
        """State file created if doesn't exist."""
        with patch("src.memory.connectors.jira.sync.JiraClient"):
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        engine = JiraSyncEngine(config=mock_config)
                        engine._save_project_state("PROJ", 5, 10)

        # Verify state file exists
        state_file = mock_config.install_dir / "jira_sync_state.json"
        assert state_file.exists()

        # Verify content
        state = json.loads(state_file.read_text())
        assert state["version"] == "1.0"
        assert "PROJ" in state["projects"]
        assert state["projects"]["PROJ"]["last_issue_count"] == 5
        assert state["projects"]["PROJ"]["last_comment_count"] == 10

    def test_state_file_update(self, mock_config, tmp_path):
        """State file updated with new sync data."""
        # Create initial state
        state_file = tmp_path / "jira_sync_state.json"
        state_file.write_text(
            json.dumps({
                "version": "1.0",
                "projects": {
                    "PROJ": {
                        "last_synced": "2026-01-01T00:00:00+00:00",
                        "last_issue_count": 1,
                        "last_comment_count": 2,
                    }
                },
            })
        )

        with patch("src.memory.connectors.jira.sync.JiraClient"):
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        engine = JiraSyncEngine(config=mock_config)
                        engine._save_project_state("PROJ", 5, 10)

        # Verify updated
        state = json.loads(state_file.read_text())
        assert state["projects"]["PROJ"]["last_issue_count"] == 5
        assert state["projects"]["PROJ"]["last_comment_count"] == 10

    def test_state_load_missing_file(self, mock_config):
        """Missing state file returns default state."""
        with patch("src.memory.connectors.jira.sync.JiraClient"):
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        engine = JiraSyncEngine(config=mock_config)
                        state = engine._load_state()

        # Default state
        assert state["version"] == "1.0"
        assert state["projects"] == {}

    def test_atomic_write(self, mock_config):
        """State file written atomically (tmp + rename)."""
        with patch("src.memory.connectors.jira.sync.JiraClient"):
            with patch("src.memory.connectors.jira.sync.MemoryStorage"):
                with patch("src.memory.connectors.jira.sync.EmbeddingClient"):
                    with patch("src.memory.connectors.jira.sync.get_qdrant_client"):
                        engine = JiraSyncEngine(config=mock_config)
                        engine._save_project_state("PROJ", 5, 10)

        # Verify no .tmp file left behind
        tmp_file = mock_config.install_dir / "jira_sync_state.json.tmp"
        assert not tmp_file.exists()


# =============================================================================
# SyncResult Tests
# =============================================================================


class TestSyncResult:
    """Test SyncResult data class."""

    def test_sync_result_creation(self):
        """SyncResult created with counts."""
        result = SyncResult(
            issues_synced=5,
            comments_synced=10,
            errors=["error1", "error2"],
            duration_seconds=12.5,
        )

        assert result.issues_synced == 5
        assert result.comments_synced == 10
        assert len(result.errors) == 2
        assert result.duration_seconds == 12.5

    def test_sync_result_to_dict(self):
        """SyncResult converts to dict."""
        result = SyncResult(
            issues_synced=3,
            comments_synced=6,
            errors=["err"],
            duration_seconds=5.0,
        )

        data = result.to_dict()
        assert data["issues_synced"] == 3
        assert data["comments_synced"] == 6
        assert data["errors"] == ["err"]
        assert data["duration_seconds"] == 5.0
