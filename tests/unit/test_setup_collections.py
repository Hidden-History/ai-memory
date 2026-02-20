"""Unit tests for setup-collections.py v2.0.6 payload index creation.

Tests verify:
- v2.0.6 freshness indexes are created for each collection (FAIL-003 fix)
- Migration creates the same indexes (schema parity with ADD-002)
- Migration index creation is idempotent (running twice doesn't error)
"""

import importlib.util
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.models import (
    PayloadSchemaType,
)

# ─── Constants ────────────────────────────────────────────────────────────────

V206_FIELDS = [
    ("decay_score", PayloadSchemaType.FLOAT),
    ("freshness_status", PayloadSchemaType.KEYWORD),
    ("source_authority", PayloadSchemaType.FLOAT),
    ("is_current", PayloadSchemaType.BOOL),
    ("version", PayloadSchemaType.INTEGER),
]

ALL_COLLECTIONS = ["code-patterns", "conventions", "discussions"]

SETUP_SCRIPT = (
    "/mnt/e/projects/dev-ai-memory/ai-memory/scripts/setup-collections.py"
)
MIGRATE_SCRIPT = (
    "/mnt/e/projects/dev-ai-memory/ai-memory/scripts/migrate_v205_to_v206.py"
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_index_calls(mock_client):
    """Return all create_payload_index calls as (collection, field, schema) tuples."""
    return [
        (
            c.kwargs.get("collection_name", c.args[0] if c.args else None),
            c.kwargs.get("field_name", c.args[1] if len(c.args) > 1 else None),
            c.kwargs.get("field_schema", c.args[2] if len(c.args) > 2 else None),
        )
        for c in mock_client.create_payload_index.call_args_list
    ]


def _load_module(path, name):
    """Load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with (
        patch("memory.config.get_config"),
        patch("memory.qdrant_client.get_qdrant_client"),
    ):
        spec.loader.exec_module(module)
    return module


def _run_setup_collections(mock_client):
    """Load and run create_collections() with a mocked Qdrant client."""
    spec = importlib.util.spec_from_file_location("setup_collections", SETUP_SCRIPT)
    module = importlib.util.module_from_spec(spec)

    with (
        patch("memory.qdrant_client.get_qdrant_client", return_value=mock_client),
        patch("memory.config.get_config") as mock_cfg,
    ):
        mock_cfg.return_value = MagicMock(
            qdrant_host="localhost",
            qdrant_port=6333,
            qdrant_api_key=None,
            qdrant_use_https=False,
            jira_sync_enabled=False,
        )
        spec.loader.exec_module(module)
        module.create_collections(dry_run=False, force=False)


# ─── setup-collections.py tests ───────────────────────────────────────────────


class TestSetupCollectionsV206Indexes:
    """Verify create_collections() creates v2.0.6 payload indexes."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.collection_exists.return_value = False
        return client

    def test_v206_indexes_created_for_all_base_collections(self, mock_client):
        """All 5 v2.0.6 indexes are created for every base collection."""
        _run_setup_collections(mock_client)

        calls = _get_index_calls(mock_client)

        for collection in ALL_COLLECTIONS:
            for field, schema in V206_FIELDS:
                assert (
                    collection,
                    field,
                    schema,
                ) in calls, f"Missing v2.0.6 index '{field}' on {collection}"

    def test_v206_decay_score_is_float(self, mock_client):
        """decay_score is indexed as FLOAT for range queries."""
        _run_setup_collections(mock_client)
        calls = _get_index_calls(mock_client)
        assert ("code-patterns", "decay_score", PayloadSchemaType.FLOAT) in calls

    def test_v206_freshness_status_is_keyword(self, mock_client):
        """freshness_status is indexed as KEYWORD for equality filtering."""
        _run_setup_collections(mock_client)
        calls = _get_index_calls(mock_client)
        assert (
            "code-patterns",
            "freshness_status",
            PayloadSchemaType.KEYWORD,
        ) in calls

    def test_v206_source_authority_is_float(self, mock_client):
        """source_authority is indexed as FLOAT for range queries."""
        _run_setup_collections(mock_client)
        calls = _get_index_calls(mock_client)
        assert (
            "code-patterns",
            "source_authority",
            PayloadSchemaType.FLOAT,
        ) in calls

    def test_v206_is_current_is_bool(self, mock_client):
        """is_current is indexed as BOOL for boolean filtering."""
        _run_setup_collections(mock_client)
        calls = _get_index_calls(mock_client)
        assert ("code-patterns", "is_current", PayloadSchemaType.BOOL) in calls

    def test_v206_version_is_integer(self, mock_client):
        """version is indexed as INTEGER for equality/range filtering."""
        _run_setup_collections(mock_client)
        calls = _get_index_calls(mock_client)
        assert ("code-patterns", "version", PayloadSchemaType.INTEGER) in calls


# ─── migrate_v205_to_v206.py tests ───────────────────────────────────────────


class TestMigrationV206Indexes:
    """Verify create_v206_payload_indexes() in migration script."""

    @pytest.fixture
    def migration_module(self):
        """Load the migration module."""
        return _load_module(MIGRATE_SCRIPT, "migrate_v205_to_v206")

    def test_migration_creates_all_v206_indexes(self, migration_module):
        """create_v206_payload_indexes creates all 5 fields on all 4 collections."""
        mock_client = MagicMock()
        migration_module.create_v206_payload_indexes(mock_client, dry_run=False)

        calls = _get_index_calls(mock_client)

        for collection in migration_module.COLLECTIONS:
            for field, schema in V206_FIELDS:
                assert (
                    collection,
                    field,
                    schema,
                ) in calls, f"Migration missing v2.0.6 index '{field}' on {collection}"

    def test_migration_schema_parity_with_setup(self, migration_module):
        """Migration creates exactly the same 5 field/schema pairs as setup-collections."""
        mock_client = MagicMock()
        migration_module.create_v206_payload_indexes(mock_client, dry_run=False)

        calls = _get_index_calls(mock_client)
        # Collect unique (field, schema) pairs across all collections
        field_schema_pairs = {(fld, schema) for _, fld, schema in calls}

        expected_pairs = set(V206_FIELDS)
        assert field_schema_pairs == expected_pairs, (
            f"Schema mismatch. Expected: {expected_pairs}, got: {field_schema_pairs}"
        )

    def test_migration_idempotent_on_already_exists(self, migration_module):
        """Running create_v206_payload_indexes when index already exists doesn't error."""
        mock_client = MagicMock()

        def side_effect(**kwargs):
            raise Exception("Index already exists: conflict")

        mock_client.create_payload_index.side_effect = side_effect

        result = migration_module.create_v206_payload_indexes(mock_client, dry_run=False)
        assert result is True, "Idempotent run should return True when indexes already exist"

    def test_migration_returns_false_on_unexpected_error(self, migration_module):
        """Returns False when a non-idempotent error occurs."""
        mock_client = MagicMock()
        mock_client.create_payload_index.side_effect = Exception("Connection reset")

        result = migration_module.create_v206_payload_indexes(mock_client, dry_run=False)
        assert result is False, "Should return False on unexpected errors"

    def test_migration_dry_run_skips_client_calls(self, migration_module):
        """In dry_run mode, no create_payload_index calls are made."""
        mock_client = MagicMock()
        migration_module.create_v206_payload_indexes(mock_client, dry_run=True)

        mock_client.create_payload_index.assert_not_called()

    def test_migration_dry_run_returns_true(self, migration_module):
        """dry_run mode always returns True."""
        mock_client = MagicMock()
        result = migration_module.create_v206_payload_indexes(mock_client, dry_run=True)
        assert result is True
