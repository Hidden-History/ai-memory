---
name: parzival-save-insight
description: "Save a Parzival insight or learning to Qdrant for cross-session memory"
---

"""Save Parzival insight to Qdrant: /parzival-save-insight

Store an insight, learning, or pattern discovered during a session.
Lightweight operation — typically 100-500 tokens.

Usage:
    /parzival-save-insight "PyYAML not in test deps caused CI failures"
    /parzival-save-insight "The decay formula uses 0.7/0.3 weighting per BP-060"
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root / "ai-memory" / "src"))

from memory.config import get_config
from memory.storage import MemoryStorage
from memory.metrics_push import push_skill_metrics_async


def main():
    start_time = time.perf_counter()
    config = get_config()

    if not config.parzival_enabled:
        print("Parzival is not enabled. Set PARZIVAL_ENABLED=true in .env.")
        return

    if len(sys.argv) < 2:
        print("Error: No insight text provided.")
        print('Usage: /parzival-save-insight "Your insight here"')
        sys.exit(1)

    content = " ".join(sys.argv[1:])

    storage = MemoryStorage(config)
    try:
        result = storage.store_agent_memory(
            content=content,
            memory_type="agent_insight",
            agent_id="parzival",
            cwd=str(_project_root),
        )
    except Exception as e:
        print(f"Error: Failed to save insight to Qdrant: {e}")
        sys.exit(1)

    status = result.get("status", "unknown")
    if status == "stored":
        print(f"Insight saved (id: {result.get('memory_id', 'unknown')[:8]}...)")
    elif status == "duplicate":
        print("Insight already exists (duplicate detected).")
    else:
        print(f"Storage result: {status}")

    metric_status = "success" if status == "stored" else "error"
    push_skill_metrics_async("parzival-save-insight", metric_status, time.perf_counter() - start_time)


if __name__ == "__main__":
    main()
