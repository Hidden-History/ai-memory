---
name: parzival-save-insight
description: "Save a Parzival insight or learning to Qdrant for cross-session memory"
allowed-tools: Bash
---

```python
"""Save Parzival insight to Qdrant: /parzival-save-insight

Store an insight, learning, or pattern discovered during a session.
Lightweight operation — typically 100-500 tokens.

Usage:
    /parzival-save-insight "PyYAML not in test deps caused CI failures"
    /parzival-save-insight "The decay formula uses 0.7/0.3 weighting per BP-060"
"""

from __future__ import annotations

import os
import sys
import time

_install_dir = os.path.expanduser("~/.ai-memory")
sys.path.insert(0, os.path.join(_install_dir, "src"))

from memory.config import get_config
from memory.project import detect_project
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

    # PLAN-028 P1B / W-09 (DEC-PM302-D1): store_agent_memory requires explicit
    # group_id. Resolve env-first; on detection failure raise with clear message.
    group_id = os.environ.get("AI_MEMORY_PROJECT_ID") or ""
    if not group_id.strip():
        try:
            group_id = detect_project(os.getcwd())
        except ValueError as _proj_e:
            print(f"Error: Failed to resolve project scope: {_proj_e}")
            push_skill_metrics_async("parzival-save-insight", "error", time.perf_counter() - start_time)
            sys.exit(1)

    storage = MemoryStorage(config)
    try:
        result = storage.store_agent_memory(
            content=content,
            memory_type="agent_insight",
            agent_id="parzival",
            cwd=os.getcwd(),
            group_id=group_id,
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

    # Skill tracing (PLAN-014 G-06)
    try:
        from memory.trace_buffer import emit_trace_event
        emit_trace_event(
            event_type="skill_execution",
            data={
                "input": f"Skill: parzival-save-insight"[:10000],
                "output": f"Result: completed"[:10000],
                "metadata": {"skill_name": "parzival-save-insight"},
            },
            session_id=os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            tags=["skill"],
        )
    except Exception:
        pass  # Tracing failures never break skill execution


if __name__ == "__main__":
    main()
```
