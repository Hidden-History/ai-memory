"""Real-Qdrant teeth for the payload-index doctor check (PLAN-036 P3, BUG-530).

These assert on **live** ``payload_schema`` values from a real Qdrant, not on a
fake: the defect class being detected (a canonical field present under degraded
params) only exists in what the engine actually returns. A permissive double
would report the degraded field as fine.

Deliberately NOT modelled on ``tests/integration/test_payload_index_teeth.py``:
that file asserts on field-*name* sets, which is precisely the blind spot this
check exists to close, and its client double cannot raise. Copying it here
would be self-defeating.

Safety (TD-876): ``tests/integration/conftest.py`` defaults ``QDRANT_URL`` to
the operator's live ``:26350`` directory-wide, and ``tests/conftest.py``
re-asserts ``QDRANT_PORT=26350`` session-wide. Every client below is built
**only** from the ``ephemeral_qdrant`` fixture's own host/port, and
``_client()`` hard-refuses to proceed if that port is the live one — these
tests create and delete collections under canonical names, so contacting the
live instance would be destructive.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from memory.config import COLLECTION_DISCUSSIONS, COLLECTION_GITHUB
from memory.payload_index_doctor import (
    MISMATCHED,
    MISSING,
    audit_payload_indexes,
    diff_payload_schema,
)
from memory.qdrant_client import ensure_payload_indexes

LIVE_INSTALL_PORT = 26350

REPO_ROOT = Path(__file__).parent.parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "aim_doctor.py"
_spec = importlib.util.spec_from_file_location("aim_doctor", _SCRIPT)
doctor = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = doctor
_spec.loader.exec_module(doctor)


def _client(ephemeral_qdrant) -> QdrantClient:
    """Client bound to the throwaway instance only — never the live install."""
    port = ephemeral_qdrant["port"]
    assert port != LIVE_INSTALL_PORT, (
        f"refusing to run: ephemeral_qdrant resolved to the live install port "
        f"{LIVE_INSTALL_PORT}; these tests create and delete canonical collections"
    )
    return QdrantClient(
        host=ephemeral_qdrant["host"],
        port=port,
        api_key=ephemeral_qdrant["api_key"],
        timeout=30,
        check_compatibility=False,
    )


@pytest.fixture
def indexed_collection(ephemeral_qdrant):
    """A real collection carrying the full canonical index set, torn down after.

    Built with ``ensure_payload_indexes`` on purpose: the healthy case must
    assert that the doctor agrees with the helper that authors the indexes, not
    with a second hand-written copy of the canonical set.
    """
    client = _client(ephemeral_qdrant)
    created: list[str] = []

    def _make(collection: str) -> QdrantClient:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.create_collection(
            collection, vectors_config=VectorParams(size=4, distance=Distance.COSINE)
        )
        created.append(collection)
        ensure_payload_indexes(client, collection)
        return client

    yield _make

    for collection in created:
        client.delete_collection(collection)


def _live_schema(client: QdrantClient, collection: str) -> dict:
    return client.get_collection(collection).payload_schema


class TestAgainstRealQdrant:
    def test_healthy_collection_is_clean(self, indexed_collection):
        client = indexed_collection(COLLECTION_DISCUSSIONS)

        found = diff_payload_schema(
            COLLECTION_DISCUSSIONS, _live_schema(client, COLLECTION_DISCUSSIONS)
        )

        assert found == (), f"healthy collection reported divergences: {found}"

    def test_healthy_instance_audits_clean(self, indexed_collection):
        client = indexed_collection(COLLECTION_DISCUSSIONS)

        audit = audit_payload_indexes(client, collections=(COLLECTION_DISCUSSIONS,))

        assert audit.unreachable is None
        assert audit.unverifiable == ()
        assert audit.divergences == ()

    def test_missing_timestamp_is_reported(self, indexed_collection):
        """Dropping timestamp is the BUG-530 symptom — get_recent() then raises."""
        client = indexed_collection(COLLECTION_DISCUSSIONS)
        client.delete_payload_index(COLLECTION_DISCUSSIONS, "timestamp")

        found = diff_payload_schema(
            COLLECTION_DISCUSSIONS, _live_schema(client, COLLECTION_DISCUSSIONS)
        )

        assert [(d.field, d.kind) for d in found] == [("timestamp", MISSING)]

    @pytest.mark.parametrize(
        ("collection", "field"),
        [
            (COLLECTION_DISCUSSIONS, "agent_id"),
            (COLLECTION_GITHUB, "source"),
        ],
    )
    def test_tenant_field_degraded_to_plain_keyword_is_mismatched(
        self, indexed_collection, collection, field
    ):
        """THE test that proves the check is not name-only.

        The field is still present and still ``data_type=KEYWORD`` — a name-only
        implementation passes every other test in this file and fails only this
        one. Asserted against the live schema, so the premise is measured rather
        than assumed.
        """
        client = indexed_collection(collection)
        client.delete_payload_index(collection, field)
        client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )

        schema = _live_schema(client, collection)

        # The premise: name-only and data_type-only diffs are both blind here.
        assert field in schema
        assert schema[field].data_type == PayloadSchemaType.KEYWORD

        (found,) = diff_payload_schema(collection, schema)

        assert (found.field, found.kind) == (field, MISMATCHED)
        assert "is_tenant=True" in found.expected
        assert "lost" in found.actual and "isolation boundary" in found.actual


class TestDoctorAdapterAgainstRealQdrant:
    """The registered check + --strict exit codes, end to end."""

    @staticmethod
    def _install_dir(tmp_path: Path, ephemeral_qdrant) -> Path:
        install_dir = tmp_path / ".ai-memory"
        (install_dir / "docker").mkdir(parents=True)
        (install_dir / "docker" / ".env").write_text(
            f"QDRANT_HOST={ephemeral_qdrant['host']}\n"
            f"QDRANT_PORT={ephemeral_qdrant['port']}\n",
            encoding="utf-8",
        )
        return install_dir

    def _result(self, install_dir: Path):
        result = doctor.check_payload_indexes(install_dir)
        assert result.name == "payload-indexes"
        return result

    def test_clean_install_passes_and_strict_exits_zero(
        self, tmp_path, ephemeral_qdrant, indexed_collection, capsys
    ):
        indexed_collection(COLLECTION_DISCUSSIONS)
        install_dir = self._install_dir(tmp_path, ephemeral_qdrant)

        result = self._result(install_dir)
        assert result.status == doctor.Status.PASS, result.detail

        exit_code = doctor.main(["--install-dir", str(install_dir), "--strict"])
        capsys.readouterr()
        assert exit_code == 0

    def test_divergence_warns_and_strict_exits_non_zero(
        self, tmp_path, ephemeral_qdrant, indexed_collection, capsys
    ):
        client = indexed_collection(COLLECTION_DISCUSSIONS)
        client.delete_payload_index(COLLECTION_DISCUSSIONS, "timestamp")
        install_dir = self._install_dir(tmp_path, ephemeral_qdrant)

        result = self._result(install_dir)
        assert result.status == doctor.Status.WARNING
        assert "timestamp" in result.detail

        exit_code = doctor.main(["--install-dir", str(install_dir), "--strict"])
        capsys.readouterr()
        assert exit_code == 1

    def test_degraded_tenant_field_warns(
        self, tmp_path, ephemeral_qdrant, indexed_collection
    ):
        client = indexed_collection(COLLECTION_DISCUSSIONS)
        client.delete_payload_index(COLLECTION_DISCUSSIONS, "agent_id")
        client.create_payload_index(
            collection_name=COLLECTION_DISCUSSIONS,
            field_name="agent_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        install_dir = self._install_dir(tmp_path, ephemeral_qdrant)

        result = self._result(install_dir)

        assert result.status == doctor.Status.WARNING
        assert "isolation boundary" in result.detail

    def test_detail_contains_no_credential(
        self, tmp_path, ephemeral_qdrant, indexed_collection
    ):
        client = indexed_collection(COLLECTION_DISCUSSIONS)
        client.delete_payload_index(COLLECTION_DISCUSSIONS, "timestamp")
        install_dir = self._install_dir(tmp_path, ephemeral_qdrant)
        secret = "s3cr3t-doctor-key"
        (install_dir / "docker" / ".env.secrets").write_text(
            f"QDRANT_API_KEY={secret}\n", encoding="utf-8"
        )

        detail = self._result(install_dir).detail

        assert secret not in detail
        assert "http://" not in detail and "https://" not in detail

    def test_check_is_read_only(self, ephemeral_qdrant, indexed_collection, tmp_path):
        """Running the doctor must not repair, create, or drop anything."""
        client = indexed_collection(COLLECTION_DISCUSSIONS)
        client.delete_payload_index(COLLECTION_DISCUSSIONS, "timestamp")
        before = set(_live_schema(client, COLLECTION_DISCUSSIONS))
        install_dir = self._install_dir(tmp_path, ephemeral_qdrant)

        self._result(install_dir)

        assert set(_live_schema(client, COLLECTION_DISCUSSIONS)) == before
        assert "timestamp" not in before


class TestNoLiveInstallContact:
    def test_fixture_is_not_the_live_install(self, ephemeral_qdrant):
        assert ephemeral_qdrant["port"] != LIVE_INSTALL_PORT

    def test_unreachable_qdrant_skips_within_budget(self, tmp_path):
        """Qdrant down must SKIP fast — install.sh runs this on every install."""
        install_dir = tmp_path / ".ai-memory"
        (install_dir / "docker").mkdir(parents=True)
        # Port 1 is reserved and never listening: a connect here fails, it does
        # not hang, and it is not the live install.
        (install_dir / "docker" / ".env").write_text(
            "QDRANT_HOST=127.0.0.1\nQDRANT_PORT=1\n", encoding="utf-8"
        )

        started = time.monotonic()
        result = doctor.check_payload_indexes(install_dir)
        elapsed = time.monotonic() - started

        assert result.status == doctor.Status.SKIP
        assert "not reachable" in result.detail
        assert elapsed < doctor.PAYLOAD_INDEX_TIMEOUT_S * 3
