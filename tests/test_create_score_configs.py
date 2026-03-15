"""Tests for scripts/create_score_configs.py idempotency and dedup logic.

Validates:
  - Pre-check via list API skips configs that already exist
  - New configs are created when absent
  - --cleanup-duplicates removes extra copies, keeps oldest
  - flush() is called before exit (V3 requirement)

PLAN-012 Phase 2 — Section 5.6 (S-16.2)
"""

import importlib
import os
import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_CONFIG_NAMES = [
    "retrieval_relevance",
    "bootstrap_quality",
    "session_coherence",
    "injection_value",
    "capture_completeness",
    "classification_accuracy",
]


def _make_config(
    name: str, cfg_id: str = "abc123", created_at: str = "2026-01-01T00:00:00Z"
):
    cfg = MagicMock()
    cfg.name = name
    cfg.id = cfg_id
    cfg.created_at = created_at
    return cfg


def _make_list_response(items: list, total_pages: int = 1):
    response = MagicMock()
    response.data = items
    meta = MagicMock()
    meta.total_pages = total_pages
    response.meta = meta
    return response


def _build_langfuse_modules(mock_client):
    """Build the fake langfuse module tree needed for create_score_configs imports."""
    fake_langfuse = types.ModuleType("langfuse")
    fake_langfuse.get_client = MagicMock(return_value=mock_client)

    fake_commons = types.ModuleType("langfuse.api.resources.commons.types")
    fake_commons.ConfigCategory = MagicMock(side_effect=lambda **kw: kw)
    fake_commons.ScoreConfigDataType = MagicMock()
    fake_commons.ScoreConfigDataType.NUMERIC = "NUMERIC"
    fake_commons.ScoreConfigDataType.BOOLEAN = "BOOLEAN"
    fake_commons.ScoreConfigDataType.CATEGORICAL = "CATEGORICAL"

    fake_sc_types = types.ModuleType("langfuse.api.resources.score_configs.types")
    fake_sc_types.CreateScoreConfigRequest = MagicMock(side_effect=lambda **kw: kw)
    fake_sc_types.UpdateScoreConfigRequest = MagicMock(side_effect=lambda **kw: kw)

    modules = {
        "langfuse": fake_langfuse,
        "langfuse.api": MagicMock(),
        "langfuse.api.resources": MagicMock(),
        "langfuse.api.resources.commons": MagicMock(),
        "langfuse.api.resources.commons.types": fake_commons,
        "langfuse.api.resources.score_configs": MagicMock(),
        "langfuse.api.resources.score_configs.types": fake_sc_types,
    }
    return modules


@contextmanager
def _patched_module(mock_client):
    """Context manager: inject fake langfuse, import module, yield (mod, client)."""
    sys.modules.pop("create_score_configs", None)
    fake_modules = _build_langfuse_modules(mock_client)

    original = {k: sys.modules.get(k) for k in fake_modules}
    sys.modules.update(fake_modules)
    try:
        mod = importlib.import_module("create_score_configs")
        yield mod, mock_client
    finally:
        sys.modules.pop("create_score_configs", None)
        for k, v in original.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _make_client_with_existing(existing_names: list[str], list_side_effect=None):
    """Build a mock client where existing_names are already in Langfuse."""
    client = MagicMock()
    configs = [_make_config(n) for n in existing_names]
    if list_side_effect is not None:
        client.api.score_configs.get.side_effect = list_side_effect
    else:
        client.api.score_configs.get.return_value = _make_list_response(configs)
    client.api.score_configs.create.return_value = MagicMock()
    client.api.score_configs.update.return_value = None
    client.flush.return_value = None
    return client


# ---------------------------------------------------------------------------
# Tests: _fetch_existing_configs
# ---------------------------------------------------------------------------


class TestFetchExistingConfigs:
    def test_returns_empty_when_no_configs(self):
        client = _make_client_with_existing([])
        with _patched_module(client) as (mod, c):
            result = mod._fetch_existing_configs(c)
        assert result == {}

    def test_returns_configs_by_name(self):
        client = _make_client_with_existing(["retrieval_relevance", "injection_value"])
        with _patched_module(client) as (mod, c):
            result = mod._fetch_existing_configs(c)
        assert "retrieval_relevance" in result
        assert "injection_value" in result

    def test_detects_duplicates(self):
        configs = [
            _make_config("retrieval_relevance", "id-1"),
            _make_config("retrieval_relevance", "id-2"),
        ]
        client = MagicMock()
        client.api.score_configs.get.return_value = _make_list_response(configs)
        with _patched_module(client) as (mod, c):
            result = mod._fetch_existing_configs(c)
        assert len(result["retrieval_relevance"]) == 2

    def test_handles_list_api_error_gracefully(self):
        client = MagicMock()
        client.api.score_configs.get.side_effect = RuntimeError("network error")
        with _patched_module(client) as (mod, c):
            result = mod._fetch_existing_configs(c)
        assert result == {}


# ---------------------------------------------------------------------------
# Tests: _cleanup_duplicates
# ---------------------------------------------------------------------------


class TestCleanupDuplicates:
    def test_skips_non_duplicates(self):
        client = MagicMock()
        with _patched_module(client) as (mod, c):
            existing = {
                "retrieval_relevance": [_make_config("retrieval_relevance", "id-1")]
            }
            mod._cleanup_duplicates(c, existing)
        client.api.score_configs.update.assert_not_called()

    def test_deletes_extra_copies_keeps_oldest(self):
        client = MagicMock()
        older = _make_config("retrieval_relevance", "id-old", "2026-01-01T00:00:00Z")
        newer = _make_config("retrieval_relevance", "id-new", "2026-02-01T00:00:00Z")
        with _patched_module(client) as (mod, c):
            existing = {"retrieval_relevance": [older, newer]}
            mod._cleanup_duplicates(c, existing)
        # Newer (id-new) should be archived; oldest (id-old) kept
        client.api.score_configs.update.assert_called_once()
        assert client.api.score_configs.update.call_args[0][0] == "id-new"

    def test_handles_delete_error_gracefully(self):
        client = MagicMock()
        client.api.score_configs.update.side_effect = RuntimeError("delete failed")
        older = _make_config("retrieval_relevance", "id-old", "2026-01-01T00:00:00Z")
        newer = _make_config("retrieval_relevance", "id-new", "2026-02-01T00:00:00Z")
        with _patched_module(client) as (mod, c):
            existing = {"retrieval_relevance": [older, newer]}
            # Should not raise
            mod._cleanup_duplicates(c, existing)

    def test_missing_created_at_sorts_last_and_gets_deleted(self):
        """Config without created_at should sort last (treated as newest) and be deleted."""
        client = MagicMock()
        client.api.score_configs.update.return_value = None
        # Config with a real date — should be kept as the "oldest"
        with_date = _make_config(
            "retrieval_relevance", "id-with-date", "2026-01-01T00:00:00Z"
        )
        # Config with no created_at attribute — fallback "9999-99-99" sorts last, gets deleted
        no_date = MagicMock()
        no_date.name = "retrieval_relevance"
        no_date.id = "id-no-date"
        del no_date.created_at  # ensure getattr fallback is triggered
        with _patched_module(client) as (mod, c):
            existing = {"retrieval_relevance": [with_date, no_date]}
            mod._cleanup_duplicates(c, existing)
        # The one without created_at should be archived; the dated one kept
        c.api.score_configs.update.assert_called_once()
        assert c.api.score_configs.update.call_args[0][0] == "id-no-date"


# ---------------------------------------------------------------------------
# Tests: main() idempotency
# ---------------------------------------------------------------------------


def _run_main(client, argv=None):
    """Run main() with injected fake langfuse and given argv."""
    if argv is None:
        argv = ["create_score_configs.py"]
    orig_argv = sys.argv
    sys.argv = argv
    try:
        with _patched_module(client) as (mod, c):
            rc = mod.main()
            return rc, c
    finally:
        sys.argv = orig_argv


class TestMainIdempotency:
    def test_skips_all_when_all_exist(self):
        client = _make_client_with_existing(ALL_CONFIG_NAMES)
        rc, c = _run_main(client)
        assert rc == 0
        c.api.score_configs.create.assert_not_called()
        c.flush.assert_called_once()

    def test_creates_all_when_none_exist(self):
        client = _make_client_with_existing([])
        rc, c = _run_main(client)
        assert rc == 0
        # 6 configs: 3 NUMERIC + 2 BOOLEAN + 1 CATEGORICAL
        assert c.api.score_configs.create.call_count == 6
        c.flush.assert_called_once()

    def test_creates_only_missing_configs(self):
        existing = ["retrieval_relevance", "injection_value", "classification_accuracy"]
        client = _make_client_with_existing(existing)
        rc, c = _run_main(client)
        assert rc == 0
        # 3 missing: bootstrap_quality, session_coherence, capture_completeness
        assert c.api.score_configs.create.call_count == 3
        c.flush.assert_called_once()

    def test_flush_always_called_on_success(self):
        client = _make_client_with_existing([])
        rc, c = _run_main(client)
        assert rc == 0
        c.flush.assert_called_once()

    def test_cleanup_duplicates_flag_triggers_dedup(self):
        older = _make_config("retrieval_relevance", "id-old", "2026-01-01T00:00:00Z")
        newer = _make_config("retrieval_relevance", "id-new", "2026-02-01T00:00:00Z")
        other_existing = [
            _make_config(n) for n in ALL_CONFIG_NAMES if n != "retrieval_relevance"
        ]

        # After cleanup, deduped list returned
        deduped = [_make_config("retrieval_relevance", "id-old"), *other_existing]

        client = MagicMock()
        client.api.score_configs.get.side_effect = [
            _make_list_response([older, newer, *other_existing]),  # initial fetch
            _make_list_response(deduped),  # post-cleanup fetch
        ]
        client.api.score_configs.create.return_value = MagicMock()
        client.api.score_configs.update.return_value = None
        client.flush.return_value = None

        rc, c = _run_main(
            client, argv=["create_score_configs.py", "--cleanup-duplicates"]
        )

        assert rc == 0
        # Duplicate archived
        c.api.score_configs.update.assert_called_once()
        assert c.api.score_configs.update.call_args[0][0] == "id-new"
        # All 6 configs present after cleanup — nothing to create
        c.api.score_configs.create.assert_not_called()
        c.flush.assert_called_once()

    def test_idempotent_on_repeated_runs(self):
        """Second run with all configs present creates nothing."""
        client = _make_client_with_existing(ALL_CONFIG_NAMES)
        # Run twice
        rc1, _ = _run_main(client)
        rc2, c = _run_main(client)
        assert rc1 == 0
        assert rc2 == 0
        c.api.score_configs.create.assert_not_called()
