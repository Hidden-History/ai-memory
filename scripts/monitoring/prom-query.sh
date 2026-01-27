#!/bin/bash
# Quick Prometheus query wrapper
# Usage: ./prom-query.sh "bmad_collection_size"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/prometheus_query.py" "$@"
