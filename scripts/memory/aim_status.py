#!/usr/bin/env python3
"""Check AI Memory system status.

Canonical runtime for the /aim-status skill. This script is intended to be
executed through scripts/memory/run-with-env.sh so it always uses the
ai-memory virtualenv plus the expected local service defaults.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

INSTALL_DIR = os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    get_config,
)
from memory.connectors.github.paths import resolve_github_state_file
from memory.metrics_push import push_skill_metrics_async
from memory.qdrant_client import get_qdrant_client

TRACE_CONTENT_MAX = 10000  # Path A emit_trace_event content cap (V4; no other value)


def _time_ago(iso_ts: str) -> str:
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - ts
        hours = int(delta.total_seconds() / 3600)
        if hours < 1:
            minutes = int(delta.total_seconds() / 60)
            return f"{minutes}m ago"
        if hours < 48:
            return f"{hours}h ago"
        return f"{delta.days}d ago"
    except Exception:
        return ""


def _bar(count: int, max_count: int, width: int = 12) -> str:
    if max_count == 0:
        return ""
    filled = int(round(width * count / max_count))
    return "█" * filled


def section_health(config, client) -> list[str]:
    lines = ["Health"]
    services = [
        ("Qdrant", f"{config.qdrant_host}:{config.qdrant_port}"),
        ("Embedding", f"{config.embedding_host}:{config.embedding_port}"),
        ("Monitoring", f"{config.monitoring_host}:{config.monitoring_port}"),
    ]
    for name, endpoint in services:
        try:
            if name == "Qdrant":
                client.get_collections()
                status = "ok"
            else:
                import urllib.request

                urllib.request.urlopen(f"http://{endpoint}/health", timeout=2)
                status = "ok"
        except Exception:
            status = "unavailable"
        lines.append(f"  {name}: {status} ({endpoint})")
    return lines


def section_collections(client) -> list[str]:
    lines = ["Collections"]
    for coll in [
        COLLECTION_CODE_PATTERNS,
        COLLECTION_CONVENTIONS,
        COLLECTION_DISCUSSIONS,
    ]:
        try:
            info = client.get_collection(coll)
            count = info.points_count or 0
            lines.append(f"  {coll}: {count} points")
        except Exception:
            lines.append(f"  {coll}: unavailable")
    return lines


def section_services(config, client) -> list[str]:
    lines = ["Services"]
    try:
        client.get_collection(COLLECTION_CODE_PATTERNS)
        lines.append(f"  Qdrant:      running | port {config.qdrant_port}")
    except Exception:
        lines.append(f"  Qdrant:      down    | port {config.qdrant_port}")

    lines.append(f"  Embedding:   port {config.embedding_port}")
    lines.append(f"  Monitoring:  port {config.monitoring_port}")
    lines.append("  Grafana:     port 23000")
    lines.append("  Pushgateway: port 29091")
    return lines


def section_sync(config) -> list[str]:
    lines = ["Sync Status"]
    sync_state_path = resolve_github_state_file(
        config.install_dir,
        config.github_repo,
        cwd=os.getcwd(),
    )

    if not config.github_sync_enabled:
        lines.append("  GitHub Sync: disabled")
        return lines

    if sync_state_path is None or not sync_state_path.exists():
        lines.append("  No sync history found")
        lines.append("  GitHub Sync: enabled")
        return lines

    try:
        with sync_state_path.open(encoding="utf-8") as file_handle:
            state = json.load(file_handle)

        type_entries = {k: v for k, v in state.items() if isinstance(v, dict)}
        last_synced_times = [
            v.get("last_synced", "") for v in type_entries.values() if v.get("last_synced")
        ]
        last_sync = max(last_synced_times) if last_synced_times else ""

        total = sum(v.get("last_count", 0) for v in type_entries.values())
        parts = [
            f"{v.get('last_count', 0)} {k}"
            for k, v in type_entries.items()
            if v.get("last_count")
        ]
        breakdown = f" ({', '.join(parts)})" if parts else ""

        ago = _time_ago(last_sync) if last_sync else ""
        ago_str = f" ({ago})" if ago else ""
        lines.append(f"  Last Sync: {last_sync}{ago_str}")
        lines.append(f"  Items Synced: {total}{breakdown}")
        lines.append("  GitHub Sync: enabled")
    except Exception as exc:
        lines.append(f"  Sync state unreadable: {exc}")

    return lines


def section_freshness(config) -> list[str]:
    lines = ["Freshness Summary"]

    if not config.freshness_enabled:
        lines.append("  Freshness: disabled")
        return lines

    try:
        from memory.freshness import run_freshness_scan

        report = run_freshness_scan(config=config, cwd=os.getcwd())
        lines.append(
            f"  Fresh: {report.fresh_count} | "
            f"Aging: {report.aging_count} | "
            f"Stale: {report.stale_count} | "
            f"Expired: {report.expired_count}"
        )
        lines.append("  Coverage: code-patterns only (conventions/discussions exempt)")
    except Exception as exc:
        lines.append(f"  Freshness scan unavailable ({exc})")

    return lines


def section_decay(config, client) -> list[str]:
    lines = ["Decay Distribution"]
    collections = [
        (COLLECTION_CODE_PATTERNS, config.decay_half_life_code_patterns),
        (COLLECTION_CONVENTIONS, config.decay_half_life_conventions),
        (COLLECTION_DISCUSSIONS, config.decay_half_life_discussions),
    ]

    type_overrides: dict[str, int] = {}
    for entry in config.decay_type_overrides.split(","):
        parts = entry.strip().split(":")
        if len(parts) == 2:
            try:
                type_overrides[parts[0]] = int(parts[1])
            except ValueError:
                pass

    buckets = [0] * 5
    total_sampled = 0

    try:
        for coll, default_half_life in collections:
            try:
                points = client.scroll(
                    collection_name=coll,
                    limit=50,
                    with_payload=True,
                    with_vectors=False,
                )[0]
                now = datetime.now(timezone.utc)
                for point in points:
                    payload = point.payload or {}
                    stored_at = payload.get("stored_at") or payload.get("timestamp", "")
                    memory_type = payload.get("type", "")
                    half_life = type_overrides.get(memory_type, default_half_life)
                    if stored_at:
                        try:
                            ts = datetime.fromisoformat(stored_at.replace("Z", "+00:00"))
                            age_days = (now - ts).days
                            temporal_score = 0.5 ** (age_days / half_life)
                        except Exception:
                            temporal_score = 0.5
                    else:
                        temporal_score = 0.5
                    bucket_idx = min(int(temporal_score / 0.2), 4)
                    buckets[bucket_idx] += 1
                    total_sampled += 1
            except Exception:
                continue

        if total_sampled == 0:
            lines.append("  No vectors to sample")
            return lines

        lines.append(f"(sampled {total_sampled} vectors)")
        max_count = max(buckets) if buckets else 1
        labels = [
            ("0.8-1.0 (fresh) ", 4),
            ("0.6-0.8 (recent)", 3),
            ("0.4-0.6 (aging) ", 2),
            ("0.2-0.4 (old)   ", 1),
            ("0.0-0.2 (stale) ", 0),
        ]
        for label, idx in labels:
            bar = _bar(buckets[idx], max_count)
            lines.append(f"  {label}: {bar} {buckets[idx]}")
    except Exception as exc:
        lines.append(f"  Decay distribution unavailable ({exc})")

    return lines


def section_flags(config) -> list[str]:
    lines = ["System Flags"]
    for name, enabled in [
        ("Auto-update", config.auto_update_enabled),
        ("Freshness", config.freshness_enabled),
        ("GitHub Sync", config.github_sync_enabled),
        ("Parzival", config.parzival_enabled),
    ]:
        status = "enabled" if enabled else "disabled"
        lines.append(f"  {name}: {status}")
    return lines


def main() -> int:
    start_time = time.perf_counter()
    parser = argparse.ArgumentParser(description="Memory system status")
    parser.add_argument(
        "--section",
        choices=["sync", "freshness", "decay", "flags"],
        help="Show only a specific section",
    )
    args = parser.parse_args()

    config = get_config()

    try:
        client = get_qdrant_client(config)
        qdrant_ok = True
    except Exception:
        client = None
        qdrant_ok = False

    output_lines: list[str] = ["## Memory System Status", ""]

    if args.section is None:
        if qdrant_ok:
            output_lines.extend(section_health(config, client))
            output_lines.append("")
            output_lines.extend(section_collections(client))
            output_lines.append("")
            output_lines.extend(section_services(config, client))
            output_lines.append("")
        else:
            output_lines.append("Health")
            output_lines.append("  Qdrant: unavailable")
            output_lines.append("")

    if args.section is None or args.section == "sync":
        output_lines.extend(section_sync(config))
        output_lines.append("")

    if args.section is None or args.section == "freshness":
        output_lines.extend(section_freshness(config))
        output_lines.append("")

    if args.section is None or args.section == "decay":
        if qdrant_ok:
            output_lines.extend(section_decay(config, client))
        else:
            output_lines.append("Decay Distribution")
            output_lines.append("  Decay distribution unavailable (Qdrant offline)")
        output_lines.append("")

    if args.section is None or args.section == "flags":
        output_lines.extend(section_flags(config))
        output_lines.append("")

    output_lines.append("─" * 40)
    output_lines.append("Output budget: < 2K tokens")
    print("\n".join(output_lines))

    push_skill_metrics_async("memory-status", "success", time.perf_counter() - start_time)

    try:
        from memory.trace_buffer import emit_trace_event

        emit_trace_event(
            event_type="skill_execution",
            data={
                "input": "Skill: aim-status"[:TRACE_CONTENT_MAX],
                "output": "Result: completed"[:TRACE_CONTENT_MAX],
                "metadata": {"skill_name": "aim-status"},
            },
            session_id=os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            tags=["skill"],
        )
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
