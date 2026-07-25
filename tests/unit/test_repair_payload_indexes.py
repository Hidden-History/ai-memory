"""Unit tests for the non-destructive payload-index repair command
(BUG-530 / PLAN-036 P4 / issue #337).

``scripts/memory/repair_payload_indexes.py`` reuses the canonical helpers
(``memory.qdrant_client.canonical_payload_indexes`` /
``ensure_payload_indexes``) and implements the PLAN-036 §2a failure-policy
contract on top of them. These tests drive each of the four outcomes the
helper can produce (SUCCESS, CREATE-ERROR, DEFINITIVE-ABSENT,
TRANSIENT-INCONCLUSIVE) via a controllable ``MagicMock`` client — mirroring
``tests/unit/test_payload_index_helper.py::TestEnsurePayloadIndexesReadBack``
rather than ``tests/integration/test_payload_index_teeth.py``'s
``FakeQdrantClient`` (which cannot raise and is out of scope here).
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from memory.config import COLLECTION_CONVENTIONS
from memory.qdrant_client import canonical_payload_indexes

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts/memory/repair_payload_indexes.py"
)


def _load_module():
    """Load repair_payload_indexes via importlib (not on sys.path as a package —
    scripts/memory would collide with the top-level memory package)."""
    spec = importlib.util.spec_from_file_location(
        "repair_payload_indexes", _SCRIPT_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load_module()

CANONICAL = canonical_payload_indexes(COLLECTION_CONVENTIONS)


def _make_client(schema: dict | None = None, count: int = 10) -> MagicMock:
    client = MagicMock()
    client.count.return_value = SimpleNamespace(count=count)
    client.get_collection.return_value = SimpleNamespace(
        payload_schema=dict(schema or {})
    )
    return client


# ─── select_collections ─────────────────────────────────────────────────────


class TestSelectCollections:
    def test_defaults_to_known_collections_present_on_instance(self):
        available = ["code-patterns", "conventions", "some-other-project-collection"]
        result = repair.select_collections(available, None)
        assert result == ["code-patterns", "conventions"]

    def test_explicit_collection_flag_overrides_default(self):
        available = ["code-patterns", "conventions", "discussions"]
        result = repair.select_collections(available, ["discussions"])
        assert result == ["discussions"]

    def test_explicit_collection_not_present_is_still_selected(self):
        # main() lets repair_collection's own not-found handling surface this,
        # rather than silently dropping an operator-requested collection.
        available = ["code-patterns"]
        result = repair.select_collections(available, ["typo-collection"])
        assert result == ["typo-collection"]

    def test_empty_requested_list_falls_back_to_default(self):
        available = ["code-patterns"]
        assert repair.select_collections(available, []) == ["code-patterns"]


# ─── repair_collection: the four ensure_payload_indexes outcomes ──────────


class TestRepairCollectionOutcomes:
    def test_success_reports_added_fields_and_unchanged_points(self):
        # Empty before repair; full canonical set on the read-back inside
        # ensure_payload_indexes.
        client = _make_client(schema={}, count=42)
        client.get_collection.side_effect = [
            SimpleNamespace(payload_schema={}),  # pre-repair read
            SimpleNamespace(payload_schema=dict(CANONICAL)),  # ensure's read-back
        ]

        result = repair.repair_collection(client, COLLECTION_CONVENTIONS, dry_run=False)

        assert result["outcome"] == "success"
        assert result["point_count_before"] == 42
        assert result["point_count_after"] == 42
        assert set(result["added_fields"]) == set(CANONICAL)
        assert result["error"] is None

    def test_dry_run_never_calls_create_payload_index(self):
        client = _make_client(schema={}, count=7)

        result = repair.repair_collection(client, COLLECTION_CONVENTIONS, dry_run=True)

        assert result["outcome"] == "dry_run"
        assert result["point_count_before"] == 7
        assert result["point_count_after"] == 7
        assert set(result["added_fields"]) == set(CANONICAL)
        client.create_payload_index.assert_not_called()

    def test_create_error_propagates_and_leaves_points_unchanged(self):
        client = _make_client(schema={}, count=15)
        client.create_payload_index.side_effect = ConnectionError("qdrant unreachable")

        result = repair.repair_collection(client, COLLECTION_CONVENTIONS, dry_run=False)

        assert result["outcome"] == "create_error"
        assert "qdrant unreachable" in result["error"]
        assert result["point_count_before"] == 15
        assert result["point_count_after"] == 15

    def test_definitive_absent_fails_loud_after_poll_budget(self):
        # Every read-back attempt (including the pre-repair check) reports
        # the same field permanently missing.
        incomplete = {k: v for k, v in CANONICAL.items() if k != "timestamp"}
        client = _make_client(schema=incomplete, count=8)

        with patch("memory.qdrant_client.time.sleep"):
            result = repair.repair_collection(
                client, COLLECTION_CONVENTIONS, dry_run=False
            )

        assert result["outcome"] == "definitive_absent"
        assert "timestamp" in result["error"]
        assert result["point_count_before"] == 8
        assert result["point_count_after"] == 8

    def test_transient_inconclusive_is_never_reported_as_success(self):
        client = _make_client(count=23)
        client.get_collection.side_effect = ConnectionError("verify-GET blip")

        with patch("memory.qdrant_client.time.sleep"):
            result = repair.repair_collection(
                client, COLLECTION_CONVENTIONS, dry_run=False
            )

        assert result["outcome"] == "transient_inconclusive"
        assert result["outcome"] != "success"
        assert result["point_count_before"] == 23
        assert result["point_count_after"] == 23

    def test_not_found_when_collection_does_not_exist(self):
        client = MagicMock()
        client.count.side_effect = Exception("404 Not Found")

        result = repair.repair_collection(client, "does-not-exist", dry_run=False)

        assert result["outcome"] == "not_found"
        assert result["point_count_before"] is None
        assert result["point_count_after"] is None
        client.create_payload_index.assert_not_called()


# ─── main(): exit codes + point-count invariant ─────────────────────────────


class TestMainExitCodes:
    def _patch_client(self, monkeypatch, client, collections):
        client.get_collections.return_value = SimpleNamespace(
            collections=[SimpleNamespace(name=n) for n in collections]
        )
        monkeypatch.setattr(repair, "get_config", lambda: MagicMock())
        monkeypatch.setattr(repair, "get_qdrant_client", lambda config: client)

    def test_exit_zero_on_full_success(self, monkeypatch):
        client = _make_client(schema=dict(CANONICAL), count=5)
        self._patch_client(monkeypatch, client, [COLLECTION_CONVENTIONS])
        monkeypatch.setattr(
            "sys.argv",
            ["repair_payload_indexes.py", "--collection", COLLECTION_CONVENTIONS],
        )

        assert repair.main() == repair.EXIT_SUCCESS

    def test_exit_one_when_a_collection_fails(self, monkeypatch):
        client = _make_client(count=5)
        client.create_payload_index.side_effect = ConnectionError("boom")
        self._patch_client(monkeypatch, client, [COLLECTION_CONVENTIONS])
        monkeypatch.setattr(
            "sys.argv",
            ["repair_payload_indexes.py", "--collection", COLLECTION_CONVENTIONS],
        )

        assert repair.main() == repair.EXIT_ERROR

    def test_exit_one_when_point_count_moves(self, monkeypatch):
        client = _make_client(schema={}, count=5)
        client.get_collection.side_effect = [
            SimpleNamespace(payload_schema={}),
            SimpleNamespace(payload_schema=dict(CANONICAL)),
        ]
        # Simulate the point count changing between the before/after reads —
        # the invariant must fail this even though the schema looks right.
        client.count.side_effect = [
            SimpleNamespace(count=5),
            SimpleNamespace(count=6),
        ]
        self._patch_client(monkeypatch, client, [COLLECTION_CONVENTIONS])
        monkeypatch.setattr(
            "sys.argv",
            ["repair_payload_indexes.py", "--collection", COLLECTION_CONVENTIONS],
        )

        assert repair.main() == repair.EXIT_ERROR

    def test_dry_run_exit_zero_and_no_mutation(self, monkeypatch):
        client = _make_client(schema={}, count=5)
        self._patch_client(monkeypatch, client, [COLLECTION_CONVENTIONS])
        monkeypatch.setattr("sys.argv", ["repair_payload_indexes.py", "--dry-run"])

        assert repair.main() == repair.EXIT_SUCCESS
        client.create_payload_index.assert_not_called()

    def test_no_target_collections_is_a_clean_success(self, monkeypatch):
        client = _make_client(count=0)
        self._patch_client(monkeypatch, client, ["unrelated-collection"])
        monkeypatch.setattr("sys.argv", ["repair_payload_indexes.py"])

        assert repair.main() == repair.EXIT_SUCCESS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
