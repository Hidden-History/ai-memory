"""Puts scripts/perf on sys.path so tests can import embedding_capacity.* directly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "perf"))
