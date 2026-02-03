#!/usr/bin/env python3
"""Prometheus Query Helper - Authenticated queries to Prometheus API.

Handles basic auth automatically using credentials from environment variables.

Usage:
    # Set credentials via environment
    export PROMETHEUS_PASSWORD=your_password

    python3 prometheus_query.py "bmad_collection_size"
    python3 prometheus_query.py "rate(ai_memory_captures_total[5m])"
    python3 prometheus_query.py --range "bmad_hook_duration_seconds_sum" --start 1h

Exit Codes:
    0: Success
    1: Query failed
    2: Missing credentials
"""

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# Configuration - credentials MUST be set via environment variables
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:29090")
PROMETHEUS_USER = os.getenv("PROMETHEUS_USER", "admin")
PROMETHEUS_PASSWORD = os.getenv("PROMETHEUS_PASSWORD", "")


def get_auth_header() -> str:
    """Generate Basic Auth header."""
    credentials = f"{PROMETHEUS_USER}:{PROMETHEUS_PASSWORD}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def query_instant(query: str) -> dict:
    """Execute instant query.

    Args:
        query: PromQL query string

    Returns:
        JSON response from Prometheus
    """
    url = f"{PROMETHEUS_URL}/api/v1/query"
    params = urllib.parse.urlencode({"query": query})
    full_url = f"{url}?{params}"

    request = urllib.request.Request(full_url)
    request.add_header("Authorization", get_auth_header())

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(
                "❌ Authentication failed. Check PROMETHEUS_USER and PROMETHEUS_PASSWORD",
                file=sys.stderr,
            )
        raise


def query_range(query: str, start: str, end: str = "now", step: str = "15s") -> dict:
    """Execute range query.

    Args:
        query: PromQL query string
        start: Start time (e.g., "1h", "2024-01-01T00:00:00Z")
        end: End time (default: now)
        step: Query resolution step

    Returns:
        JSON response from Prometheus
    """
    url = f"{PROMETHEUS_URL}/api/v1/query_range"

    # Parse relative time
    now = datetime.now()
    if start.endswith("h"):
        start_time = now - timedelta(hours=int(start[:-1]))
    elif start.endswith("m"):
        start_time = now - timedelta(minutes=int(start[:-1]))
    elif start.endswith("d"):
        start_time = now - timedelta(days=int(start[:-1]))
    else:
        start_time = datetime.fromisoformat(start)

    end_time = now if end == "now" else datetime.fromisoformat(end)

    params = urllib.parse.urlencode(
        {
            "query": query,
            "start": start_time.timestamp(),
            "end": end_time.timestamp(),
            "step": step,
        }
    )
    full_url = f"{url}?{params}"

    request = urllib.request.Request(full_url)
    request.add_header("Authorization", get_auth_header())

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def format_result(result: dict, verbose: bool = False) -> str:
    """Format Prometheus response for display."""
    if result.get("status") != "success":
        return f"❌ Query failed: {result.get('error', 'Unknown error')}"

    data = result.get("data", {})
    result_type = data.get("resultType", "unknown")
    results = data.get("result", [])

    if not results:
        return "No data"

    lines = []
    for r in results:
        metric = r.get("metric", {})
        value = r.get("value", [None, None])

        # Format metric labels
        labels = ", ".join(f'{k}="{v}"' for k, v in metric.items() if k != "__name__")
        name = metric.get("__name__", "")

        if labels:
            metric_str = f"{name}{{{labels}}}" if name else f"{{{labels}}}"
        else:
            metric_str = name or "(no labels)"

        # Format value
        if result_type == "vector":
            timestamp, val = value
            lines.append(f"{metric_str} => {val}")
        elif result_type == "matrix":
            values = r.get("values", [])
            lines.append(f"{metric_str}:")
            for ts, val in values[-5:]:  # Show last 5 values
                lines.append(f"  {datetime.fromtimestamp(ts).isoformat()} => {val}")
        else:
            lines.append(f"{metric_str} => {value}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Query Prometheus with authentication")
    parser.add_argument("query", help="PromQL query")
    parser.add_argument("--range", action="store_true", help="Execute range query")
    parser.add_argument("--start", default="1h", help="Range start (e.g., 1h, 30m, 1d)")
    parser.add_argument("--end", default="now", help="Range end")
    parser.add_argument("--step", default="15s", help="Query step")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    try:
        if args.range:
            result = query_range(args.query, args.start, args.end, args.step)
        else:
            result = query_instant(args.query)

        if args.raw:
            print(json.dumps(result, indent=2))
        else:
            print(format_result(result))

        return 0

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
