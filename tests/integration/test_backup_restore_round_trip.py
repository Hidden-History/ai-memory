"""Integration tests for the Qdrant backup/restore round-trip (TD-517).

Exercises ``scripts/backup_qdrant.py`` and ``scripts/restore_qdrant.py`` end
to end against a real Qdrant instance, using a production-shape collection:

- Hybrid schema — named dense (768) + ColBERT multivector + BM25 sparse,
  scalar int8 quantization, HNSW m=16, and the full baseline payload-index
  set from ``scripts/setup-collections.py``.
- Realistic data volume — well over 100 points, each with a >=1 KB payload,
  so the snapshot exercises the multi-chunk download path rather than a
  toy fixture (per the realistic-size production-artifact testing rule).

Two scenarios:

1. ``test_round_trip_fresh_install`` — back up, delete the collection, then
   restore via the real ``restore_qdrant.py`` CLI. Asserts byte-equivalent
   schema, exact point count, and that a random 5% sample of points retains
   its dense + sparse + ColBERT vectors and payload. This is the regression
   guard for TD-517 R-1 (the single-vector prefab that broke hybrid-schema
   restores).

2. ``test_rollback_preserves_existing_on_failure`` — back up, mutate the
   live collection, then run a restore that fails mid-flight. Asserts the
   pre-existing collection is rolled back to exactly its mutated state
   (TD-517 R-6).

Requirements: a reachable Qdrant at ``QDRANT_URL`` (default
``http://localhost:26350``). Marked ``integration`` automatically by
``tests/integration/conftest.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
BACKUP_SCRIPT = SCRIPTS_DIR / "backup_qdrant.py"
RESTORE_SCRIPT = SCRIPTS_DIR / "restore_qdrant.py"

QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")

# Connection resolution: prefer explicit QDRANT_HOST + QDRANT_PORT (the CI
# integration job sets these, and the integration conftest force-injects a
# QDRANT_URL default that does not match the CI Qdrant port). Fall back to
# QDRANT_URL otherwise.
if os.environ.get("QDRANT_HOST") and os.environ.get("QDRANT_PORT"):
    QDRANT_HOST = os.environ["QDRANT_HOST"]
    QDRANT_PORT = int(os.environ["QDRANT_PORT"])
    QDRANT_URL = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
else:
    QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:26350")
    _parsed = urlparse(QDRANT_URL)
    QDRANT_HOST = _parsed.hostname or "localhost"
    QDRANT_PORT = _parsed.port or 26350

# Production-shape volume: comfortably over the 100-point realistic-size bar.
POINT_COUNT = 120
DENSE_DIM = 768
COLBERT_DIM = 128
COLBERT_TOKENS = 16


def _headers(json_body: bool = False) -> dict:
    h: dict = {}
    if QDRANT_API_KEY:
        h["api-key"] = QDRANT_API_KEY
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _qdrant_up() -> bool:
    try:
        r = httpx.get(f"{QDRANT_URL}/healthz", headers=_headers(), timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _qdrant_up(), reason=f"Qdrant not reachable at {QDRANT_URL}"
)


def _delete_collection(name: str) -> None:
    with httpx.Client(timeout=30.0) as client:
        client.delete(f"{QDRANT_URL}/collections/{name}", headers=_headers())


def _create_production_collection(name: str) -> None:
    """Create a collection with the full v2.x hybrid schema + payload indexes."""
    body = {
        "vectors": {
            "": {"size": DENSE_DIM, "distance": "Cosine"},
            "colbert": {
                "size": COLBERT_DIM,
                "distance": "Cosine",
                "multivector_config": {"comparator": "max_sim"},
                "hnsw_config": {"m": 0},
            },
        },
        "sparse_vectors": {"bm25": {"modifier": "idf"}},
        "hnsw_config": {
            "m": 16,
            "ef_construct": 100,
            "full_scan_threshold": 10000,
            "on_disk": True,
        },
        "quantization_config": {
            "scalar": {"type": "int8", "quantile": 0.99, "always_ram": True}
        },
        "on_disk_payload": True,
    }
    r = httpx.put(
        f"{QDRANT_URL}/collections/{name}",
        headers=_headers(json_body=True),
        json=body,
        timeout=30.0,
    )
    r.raise_for_status()

    # Baseline payload indexes mirrored from scripts/setup-collections.py.
    indexes = [
        ("group_id", {"type": "keyword", "is_tenant": True}),
        ("type", "keyword"),
        ("content_hash", {"type": "keyword"}),
        ("content", {"type": "text", "tokenizer": "word"}),
        ("timestamp", "datetime"),
    ]
    for field, schema in indexes:
        r = httpx.put(
            f"{QDRANT_URL}/collections/{name}/index",
            headers=_headers(json_body=True),
            json={"field_name": field, "field_schema": schema},
            timeout=15.0,
        )
        r.raise_for_status()


def _insert_points(name: str, count: int, content_tag: str) -> None:
    """Insert ``count`` production-shape points (>=1 KB payload each)."""
    points = []
    for i in range(count):
        dense = [((i + j) % 97) / 97.0 for j in range(DENSE_DIM)]
        colbert = [
            [((i + t + d) % 53) / 53.0 for d in range(COLBERT_DIM)]
            for t in range(COLBERT_TOKENS)
        ]
        # >=1 KB of realistic-size content.
        content = f"{content_tag} point {i} :: " + ("lorem ipsum dolor " * 70)
        points.append(
            {
                "id": i + 1,
                "vector": {
                    "": dense,
                    "colbert": colbert,
                    "bm25": {
                        "indices": [i % 500, (i + 7) % 500, (i + 19) % 500],
                        "values": [0.5, 1.0, 0.25],
                    },
                },
                "payload": {
                    "content": content,
                    "type": "implementation",
                    "group_id": "td517-round-trip",
                    "content_hash": f"hash-{i:08x}",
                    "timestamp": "2026-05-15T00:00:00Z",
                },
            }
        )
    # Upload in batches to keep request bodies bounded.
    for start in range(0, len(points), 40):
        batch = points[start : start + 40]
        r = httpx.put(
            f"{QDRANT_URL}/collections/{name}/points?wait=true",
            headers=_headers(json_body=True),
            json={"points": batch},
            timeout=60.0,
        )
        r.raise_for_status()


def _schema_fingerprint(name: str) -> dict:
    """Distill a collection's structural schema (matches the script fingerprint)."""
    r = httpx.get(f"{QDRANT_URL}/collections/{name}", headers=_headers(), timeout=15.0)
    r.raise_for_status()
    result = r.json()["result"]
    params = result.get("config", {}).get("params", {}) or {}

    def _strip_points(payload_schema: dict | None) -> dict:
        out: dict = {}
        for field, info in (payload_schema or {}).items():
            if isinstance(info, dict):
                out[field] = {k: v for k, v in info.items() if k != "points"}
            else:
                out[field] = info
        return out

    return {
        "params": {
            "vectors": params.get("vectors"),
            "sparse_vectors": params.get("sparse_vectors"),
            "shard_number": params.get("shard_number"),
            "on_disk_payload": params.get("on_disk_payload"),
        },
        "hnsw_config": result.get("config", {}).get("hnsw_config"),
        "quantization_config": result.get("config", {}).get("quantization_config"),
        "payload_schema": _strip_points(result.get("payload_schema")),
    }


def _count(name: str) -> int:
    r = httpx.post(
        f"{QDRANT_URL}/collections/{name}/points/count",
        headers=_headers(json_body=True),
        json={"exact": True},
        timeout=30.0,
    )
    if r.status_code != 200:
        return -1
    return r.json()["result"]["count"]


def _retrieve(name: str, point_ids: list[int]) -> list[dict]:
    r = httpx.post(
        f"{QDRANT_URL}/collections/{name}/points",
        headers=_headers(json_body=True),
        json={"ids": point_ids, "with_payload": True, "with_vector": True},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["result"]


def _script_env() -> dict:
    env = os.environ.copy()
    env["QDRANT_HOST"] = QDRANT_HOST
    env["QDRANT_PORT"] = str(QDRANT_PORT)
    env["QDRANT_API_KEY"] = QDRANT_API_KEY
    return env


def _run_backup(collection: str, output_dir: Path) -> Path:
    """Run backup_qdrant.py for a single named collection; return the backup dir.

    The backup script's --collection flag is restricted to the standard
    collection set, so the test collection is injected by monkeypatching the
    module's COLLECTIONS list inside a fresh subprocess that calls main().
    This still exercises the real backup main() end to end.
    """
    runner = (
        "import sys;"
        f"sys.path.insert(0, {str(SCRIPTS_DIR)!r});"
        "import backup_qdrant;"
        f"backup_qdrant.COLLECTIONS = [{collection!r}];"
        f"sys.argv = ['backup_qdrant.py', '--output', {str(output_dir)!r}];"
        "sys.exit(backup_qdrant.main())"
    )
    proc = subprocess.run(
        [sys.executable, "-c", runner],
        env=_script_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, (
        f"backup failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    backup_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(backup_dirs) == 1, f"expected one backup dir, got {backup_dirs}"
    return backup_dirs[0]


def _run_restore(
    backup_dir: Path, extra_args: list[str]
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [sys.executable, str(RESTORE_SCRIPT), str(backup_dir), *extra_args],
        env=_script_env(),
        capture_output=True,
        text=True,
        timeout=300,
        input="y\n",
    )
    return proc


def test_round_trip_fresh_install(tmp_path: Path) -> None:
    """Backup -> delete -> restore reproduces a byte-equivalent hybrid collection."""
    collection = f"test_backup_restore_rt_{uuid.uuid4().hex[:8]}"
    output_dir = tmp_path / "backup_out"
    output_dir.mkdir()

    try:
        _create_production_collection(collection)
        _insert_points(collection, POINT_COUNT, "fresh")
        assert _count(collection) == POINT_COUNT

        fingerprint_before = _schema_fingerprint(collection)
        sample_ids = list(range(1, POINT_COUNT + 1, 20))  # ~5% sample
        sample_before = {p["id"]: p for p in _retrieve(collection, sample_ids)}

        backup_dir = _run_backup(collection, output_dir)

        # The backup must carry the schema fingerprint (TD-517 B-1) and a
        # checksum file (TD-517 B-2).
        manifest = json.loads((backup_dir / "manifest.json").read_text())
        assert manifest["collections"][collection]["schema"] is not None
        assert (backup_dir / "CHECKSUMS.sha256").exists()

        # Fresh-install path: delete the collection, then restore via the CLI.
        _delete_collection(collection)
        assert _count(collection) == -1

        proc = _run_restore(backup_dir, ["--force"])
        assert proc.returncode == 0, (
            f"restore failed (rc={proc.returncode})\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

        # Schema must be byte-equivalent (TD-517 R-1).
        fingerprint_after = _schema_fingerprint(collection)
        assert json.dumps(fingerprint_after, sort_keys=True) == json.dumps(
            fingerprint_before, sort_keys=True
        ), "schema fingerprint drifted across the round-trip"

        # Exact point count restored (TD-517 R-5).
        assert _count(collection) == POINT_COUNT

        # 5% random sample must retain dense + sparse + colbert vectors + payload.
        sample_after = {p["id"]: p for p in _retrieve(collection, sample_ids)}
        assert set(sample_after) == set(sample_before)
        for pid, point in sample_after.items():
            vectors = point["vector"]
            assert vectors.get(""), f"point {pid} lost dense vector"
            assert vectors.get("colbert"), f"point {pid} lost colbert multivector"
            assert "bm25" in vectors, f"point {pid} lost bm25 sparse vector"
            assert (
                point["payload"]["content"] == sample_before[pid]["payload"]["content"]
            ), f"point {pid} payload content drifted"
    finally:
        _delete_collection(collection)


def test_rollback_preserves_existing_on_failure(tmp_path: Path) -> None:
    """A restore that fails mid-flight rolls a pre-existing collection back (R-6)."""
    collection = f"test_backup_restore_rb_{uuid.uuid4().hex[:8]}"
    output_dir = tmp_path / "backup_out"
    output_dir.mkdir()

    try:
        # Backup state: POINT_COUNT points.
        _create_production_collection(collection)
        _insert_points(collection, POINT_COUNT, "backup")
        backup_dir = _run_backup(collection, output_dir)

        # Mutate the live collection AFTER backup so its state is distinct.
        mutated_total = POINT_COUNT + 30
        _insert_points(collection, mutated_total, "mutated")
        assert _count(collection) == mutated_total

        # Corrupt the snapshot so the upload fails after the rollback snapshot
        # is taken. --skip-checksum-verify lets the corrupt file reach upload.
        snapshot = next((backup_dir / "qdrant").glob("*.snapshot"))
        snapshot.write_bytes(b"corrupted-not-a-real-snapshot")

        proc = _run_restore(backup_dir, ["--force", "--skip-checksum-verify"])
        assert proc.returncode == 4, (
            f"expected restore failure exit 4, got {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}"
        )

        # TD-517 R-6: the pre-existing collection must survive intact at its
        # mutated state — the failed restore must not have left it empty or
        # partially overwritten.
        assert _count(collection) == mutated_total, (
            "rollback did not restore the pre-existing collection to its "
            "pre-restore state"
        )
        fingerprint = _schema_fingerprint(collection)
        assert "colbert" in (
            fingerprint["params"]["vectors"] or {}
        ), "rollback left the collection with a degraded schema"
    finally:
        _delete_collection(collection)
