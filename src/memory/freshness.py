"""Freshness detection for code-patterns memories (Tier 1).

Compares code-patterns memories against GitHub code blob data to detect
when stored memories have become stale because the underlying source code
has changed.

Tier 1 is on-demand (invoked via /freshness-report skill), not scheduled.
Tier 2 (inline freshness at query time) is Phase 3 scope.

References:
    - SPEC-013 (this spec)
    - BP-066 (Cross-Collection Freshness Validation)
    - BP-060 (Solving Freshness in RAG)
    - SPEC-001 (complementary decay scoring)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
)

from .config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_DISCUSSIONS,
    MemoryConfig,
    get_config,
)
from .qdrant_client import get_qdrant_client
from .trace_buffer import emit_trace_event

logger = logging.getLogger("ai_memory.freshness")

__all__ = [
    "FreshnessReport",
    "FreshnessResult",
    "FreshnessTier",
    "GroundTruth",
    "build_ground_truth_map",
    "classify_freshness",
    "count_commits_for_file",
    "run_freshness_scan",
]


class FreshnessTier(str, Enum):
    """Freshness classification tier for code-patterns memories."""

    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """Ground truth data for a single file from GitHub sync."""

    blob_hash: str
    last_commit_sha: str
    last_synced: str = ""


@dataclass
class FreshnessResult:
    """Freshness check result for a single code-patterns point."""

    point_id: str
    file_path: str
    memory_type: str
    status: str
    reason: str
    stored_at: str
    blob_hash_match: bool | None
    commit_count: int


@dataclass
class FreshnessReport:
    """Aggregated freshness report across all code-patterns points.

    Attributes:
        total_checked: Total code-patterns points with file_path.
        fresh_count: Points classified as fresh.
        aging_count: Points classified as aging.
        stale_count: Points classified as stale.
        expired_count: Points classified as expired.
        unknown_count: Points with no ground truth data.
        duration_seconds: Total scan duration.
        results: Per-point freshness results.
        timestamp: ISO 8601 UTC timestamp of the report.
    """

    total_checked: int
    fresh_count: int
    aging_count: int
    stale_count: int
    expired_count: int
    unknown_count: int
    duration_seconds: float
    results: list[FreshnessResult]
    timestamp: str


def build_ground_truth_map(
    client: QdrantClient,
    config: MemoryConfig,
) -> dict[str, GroundTruth]:
    """Build file_path -> GroundTruth lookup from GitHub code blob data.

    Scrolls discussions collection filtered to source="github",
    type="github_code_blob", is_current=True. Single scroll operation
    per BP-066 Section 5.3 batch lookup map pattern.

    Args:
        client: QdrantClient instance.
        config: MemoryConfig instance (unused in Tier 1, reserved for
            future config-driven filtering).

    Returns:
        Mapping of file_path to GroundTruth. Empty dict if no GitHub
        data exists.
    """
    ground_truth: dict[str, GroundTruth] = {}

    scroll_filter = Filter(
        must=[
            FieldCondition(key="source", match=MatchValue(value="github")),
            FieldCondition(key="type", match=MatchValue(value="github_code_blob")),
            FieldCondition(key="is_current", match=MatchValue(value=True)),
        ]
    )

    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION_DISCUSSIONS,
            scroll_filter=scroll_filter,
            limit=100,
            offset=offset,
            with_payload=[
                "file_path",
                "blob_hash",
                "last_commit_sha",
                "last_synced",
            ],
        )

        for point in points:
            payload = point.payload or {}
            file_path = payload.get("file_path")
            if not file_path:
                continue

            gt = GroundTruth(
                blob_hash=payload.get("blob_hash", ""),
                last_commit_sha=payload.get("last_commit_sha", ""),
                last_synced=payload.get("last_synced", ""),
            )

            # First entry per file_path wins (all chunks of the same
            # file share the same blob_hash)
            if file_path not in ground_truth:
                ground_truth[file_path] = gt

        if next_offset is None:
            break
        offset = next_offset

    logger.info(
        "ground_truth_map_built",
        extra={"file_count": len(ground_truth)},
    )

    return ground_truth


def count_commits_for_file(
    client: QdrantClient,
    file_path: str,
    since: str,
) -> int:
    """Count GitHub commits touching a file since a given timestamp.

    Scrolls github_commit points and checks files_changed list for the
    target file_path. O(total_commits) per call -- acceptable for Tier 1
    on-demand usage. Phase 3 (task 3.5) optimizes with pre-built map.

    Args:
        client: QdrantClient instance.
        file_path: File path to check commits for.
        since: ISO 8601 UTC timestamp. Only count commits after this.

    Returns:
        Number of commits touching file_path since the given timestamp.
        Returns 0 if ``since`` is not a valid ISO 8601 timestamp.
    """
    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        return 0  # Corrupt stored_at — treat as no commits

    count = 0
    offset = None

    scroll_filter = Filter(
        must=[
            FieldCondition(key="source", match=MatchValue(value="github")),
            FieldCondition(key="type", match=MatchValue(value="github_commit")),
            FieldCondition(key="is_current", match=MatchValue(value=True)),
        ]
    )

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION_DISCUSSIONS,
            scroll_filter=scroll_filter,
            limit=100,
            offset=offset,
            with_payload=["files_changed", "timestamp"],
        )

        for point in points:
            payload = point.payload or {}
            timestamp_str = payload.get("timestamp", "")
            files_changed = payload.get("files_changed", [])

            if not timestamp_str or not files_changed:
                continue

            try:
                commit_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            if commit_dt > since_dt and file_path in files_changed:
                count += 1

        if next_offset is None:
            break
        offset = next_offset

    return count


def classify_freshness(
    blob_hash_match: bool | None,
    commit_count: int,
    config: MemoryConfig,
) -> tuple[FreshnessTier, str]:
    """Classify freshness tier based on multi-signal assessment.

    Priority order:
        1. Blob hash mismatch (False) -> expired
        2. Blob hash unavailable (None) -> fall through to commit count
        3. commit_count >= expired threshold -> expired
        4. commit_count >= stale threshold -> stale
        5. commit_count >= aging threshold -> aging
        6. Otherwise -> fresh

    Note: FreshnessTier.UNKNOWN is assigned by the caller
    (run_freshness_scan) when no ground truth exists, before this
    function is called. This function only runs when ground truth
    EXISTS.

    Args:
        blob_hash_match: True if hashes match, False if mismatch,
            None if hash comparison unavailable (expected in Tier 1).
        commit_count: Commits since memory was stored.
        config: MemoryConfig with freshness threshold fields.

    Returns:
        Tuple of (FreshnessTier, reason).
    """
    if blob_hash_match is False:
        return FreshnessTier.EXPIRED, (
            f"Blob hash mismatch: source file content has changed "
            f"(commit_count={commit_count})"
        )

    hash_note = (
        "content matches, "
        if blob_hash_match is True
        else "hash comparison unavailable, "
    )

    if commit_count >= config.freshness_commit_threshold_expired:
        return FreshnessTier.EXPIRED, (
            f"High churn: {hash_note}{commit_count} commits "
            f"(threshold={config.freshness_commit_threshold_expired})"
        )

    if commit_count >= config.freshness_commit_threshold_stale:
        return FreshnessTier.STALE, (
            f"Significant activity: {hash_note}{commit_count} commits "
            f"(threshold={config.freshness_commit_threshold_stale})"
        )

    if commit_count >= config.freshness_commit_threshold_aging:
        return FreshnessTier.AGING, (
            f"Some activity: {hash_note}{commit_count} commits "
            f"(threshold={config.freshness_commit_threshold_aging})"
        )

    return FreshnessTier.FRESH, (
        f"Low activity ({commit_count} commits), " f"{hash_note.rstrip(', ')}"
    )


def run_freshness_scan(
    config: MemoryConfig | None = None,
    group_id: str | None = None,
    cwd: str | None = None,
) -> FreshnessReport:
    """Run full freshness scan of code-patterns collection.

    Orchestrates the complete freshness detection pipeline:
    1. Build ground truth map from GitHub code blob data
    2. Scroll code-patterns with file_path field
    3. Compare each point against ground truth
    4. Classify freshness tier
    5. Update Qdrant payload with freshness_status
    6. Log results to .audit/logs/freshness-log.jsonl

    Args:
        config: Optional MemoryConfig. Uses get_config() if not provided.
        group_id: Optional project filter. If None, scans all projects.
        cwd: Working directory for resolving relative paths (e.g.,
            audit_dir). If None, uses os.getcwd().

    Returns:
        FreshnessReport with aggregated statistics and per-point results.

    Raises:
        No exceptions raised. Returns report with zero counts if services
        are unavailable (graceful degradation).
    """
    config = config or get_config()
    start_time = time.perf_counter()

    if not config.freshness_enabled:
        logger.info("freshness_scan_disabled")
        return FreshnessReport(
            total_checked=0,
            fresh_count=0,
            aging_count=0,
            stale_count=0,
            expired_count=0,
            unknown_count=0,
            duration_seconds=0.0,
            results=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    try:
        client = get_qdrant_client(config)
    except Exception as e:
        logger.error(
            "freshness_scan_qdrant_unavailable",
            extra={"error": str(e)},
        )
        return FreshnessReport(
            total_checked=0,
            fresh_count=0,
            aging_count=0,
            stale_count=0,
            expired_count=0,
            unknown_count=0,
            duration_seconds=time.perf_counter() - start_time,
            results=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # Step 1: Build ground truth map
    ground_truth_map = build_ground_truth_map(client, config)

    if not ground_truth_map:
        logger.warning("freshness_scan_no_ground_truth")
        return FreshnessReport(
            total_checked=0,
            fresh_count=0,
            aging_count=0,
            stale_count=0,
            expired_count=0,
            unknown_count=0,
            duration_seconds=time.perf_counter() - start_time,
            results=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    _trace_start = datetime.now(timezone.utc)
    emit_trace_event(
        event_type="freshness_scan_start",
        data={
            "input": f"Freshness scan: {len(ground_truth_map)} ground truth files, group_id={group_id or 'all'}",
            "output": "",
            "metadata": {
                "ground_truth_files": len(ground_truth_map),
                "group_id": group_id,
            },
        },
        start_time=_trace_start,
    )

    # Step 2: Scroll code-patterns and compare
    results: list[FreshnessResult] = []
    commit_count_cache: dict[str, int] = {}

    scroll_conditions = []
    if group_id is not None:
        scroll_conditions.append(
            FieldCondition(key="group_id", match=MatchValue(value=group_id))
        )
    scroll_filter = Filter(must=scroll_conditions) if scroll_conditions else None

    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=scroll_filter,
            limit=100,
            offset=offset,
            with_payload=["file_path", "type", "stored_at"],
        )

        for point in points:
            payload = point.payload or {}
            file_path = payload.get("file_path")
            if not file_path:
                continue  # Skip points without file_path

            stored_at = payload.get("stored_at", "")
            memory_type = payload.get("type", "unknown")

            # Look up ground truth
            gt = ground_truth_map.get(file_path)

            if gt is None:
                # No ground truth for this file — classify as UNKNOWN
                result = FreshnessResult(
                    point_id=str(point.id),
                    file_path=file_path,
                    memory_type=memory_type,
                    status=FreshnessTier.UNKNOWN,
                    reason="No GitHub code blob data for this file path",
                    stored_at=stored_at,
                    blob_hash_match=None,
                    commit_count=0,
                )
                results.append(result)
                continue

            # Blob hash comparison: code-patterns points do NOT have
            # a blob_hash field (only github_code_blob points in
            # discussions do). In Tier 1, hash comparison is always
            # None, and classification relies on commit count alone.
            # Phase 3 may add blob_hash propagation to code-patterns.
            blob_hash_match = None

            # Commit count (cached per file_path:stored_at pair)
            cache_key = f"{file_path}:{stored_at}"
            if cache_key in commit_count_cache:
                commit_count = commit_count_cache[cache_key]
            else:
                if stored_at:
                    commit_count = count_commits_for_file(client, file_path, stored_at)
                else:
                    commit_count = 0
                commit_count_cache[cache_key] = commit_count

            # Classify
            status, reason = classify_freshness(blob_hash_match, commit_count, config)

            result = FreshnessResult(
                point_id=str(point.id),
                file_path=file_path,
                memory_type=memory_type,
                status=status,
                reason=reason,
                stored_at=stored_at,
                blob_hash_match=blob_hash_match,
                commit_count=commit_count,
            )
            results.append(result)

        if next_offset is None:
            break
        offset = next_offset

    # Step 3: Update Qdrant payloads
    _update_freshness_payloads(client, results)

    # Step 4: Log to audit trail
    _log_freshness_results(results, config, cwd=cwd)

    # Step 5: Build report
    duration = time.perf_counter() - start_time

    fresh = sum(1 for r in results if r.status == FreshnessTier.FRESH)
    aging = sum(1 for r in results if r.status == FreshnessTier.AGING)
    stale = sum(1 for r in results if r.status == FreshnessTier.STALE)
    expired = sum(1 for r in results if r.status == FreshnessTier.EXPIRED)
    unknown = sum(1 for r in results if r.status == FreshnessTier.UNKNOWN)

    report = FreshnessReport(
        total_checked=len(results),
        fresh_count=fresh,
        aging_count=aging,
        stale_count=stale,
        expired_count=expired,
        unknown_count=unknown,
        duration_seconds=duration,
        results=results,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    logger.info(
        "freshness_scan_complete",
        extra={
            "total": report.total_checked,
            "fresh": fresh,
            "aging": aging,
            "stale": stale,
            "expired": expired,
            "unknown": unknown,
            "duration_seconds": round(duration, 2),
        },
    )

    emit_trace_event(
        event_type="freshness_scan_complete",
        data={
            "input": f"Freshness scan for {group_id or 'all projects'}",
            "output": f"{report.total_checked} checked: {fresh} fresh, {aging} aging, {stale} stale, {expired} expired, {unknown} unknown in {duration:.1f}s",
            "metadata": {
                "total_checked": report.total_checked,
                "fresh": fresh,
                "aging": aging,
                "stale": stale,
                "expired": expired,
                "unknown": unknown,
                "duration_seconds": round(duration, 2),
            },
        },
        start_time=_trace_start,
        end_time=datetime.now(timezone.utc),
    )

    # Step 6: Push Prometheus metrics (fire-and-forget)
    try:
        from .metrics_push import push_freshness_metrics_async

        push_freshness_metrics_async(
            fresh=fresh,
            aging=aging,
            stale=stale,
            expired=expired,
            unknown=unknown,
            duration_seconds=duration,
            project=group_id or "unknown",
        )
    except ImportError:
        logger.debug("metrics_push not available, skipping freshness metrics")

    return report


def _update_freshness_payloads(
    client: QdrantClient,
    results: list[FreshnessResult],
) -> None:
    """Update freshness_status payload field on code-patterns points.

    Uses Qdrant set_payload API. Updates are applied one point at a time
    (Qdrant set_payload accepts a points list but we iterate to isolate
    failures). Failures are logged but do not abort the scan.

    Args:
        client: QdrantClient instance.
        results: List of FreshnessResult to update.
    """
    from collections import defaultdict

    now_iso = datetime.now(timezone.utc).isoformat()
    groups: dict = defaultdict(list)
    for result in results:
        groups[result.status].append(result)
    for status, group in groups.items():
        point_ids = [r.point_id for r in group]
        try:
            client.set_payload(
                collection_name=COLLECTION_CODE_PATTERNS,
                payload={"freshness_status": status, "freshness_checked_at": now_iso},
                points=point_ids,
            )
        except Exception as e:
            logger.warning(
                "freshness_payload_update_failed",
                extra={
                    "point_ids": point_ids,
                    "status": status,
                    "error": str(e),
                },
            )


def _log_freshness_results(
    results: list[FreshnessResult],
    config: MemoryConfig,
    cwd: str | None = None,
) -> None:
    """Append freshness results to .audit/logs/freshness-log.jsonl.

    One JSON line per result. Creates log file if it doesn't exist.
    Failures are logged but do not abort the scan.

    Args:
        results: List of FreshnessResult to log.
        config: MemoryConfig with audit_dir path.
        cwd: Working directory for resolving relative audit_dir.
            If None, uses os.getcwd().
    """
    import os

    base = Path(cwd) if cwd else Path(os.getcwd())
    log_path = base / config.audit_dir / "logs" / "freshness-log.jsonl"

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()

        with open(log_path, "a", encoding="utf-8") as f:
            for result in results:
                entry = {
                    "timestamp": timestamp,
                    "point_id": result.point_id,
                    "file_path": result.file_path,
                    "memory_type": result.memory_type,
                    "status": result.status,
                    "reason": result.reason,
                    "stored_at": result.stored_at,
                    "blob_hash_match": result.blob_hash_match,
                    "commit_count": result.commit_count,
                }
                f.write(json.dumps(entry) + "\n")

        logger.debug(
            "freshness_log_written",
            extra={"path": str(log_path), "entries": len(results)},
        )

    except Exception as e:
        logger.warning(
            "freshness_log_write_failed",
            extra={"path": str(log_path), "error": str(e)},
        )
