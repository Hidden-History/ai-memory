---
name: aim-parzival-bootstrap
description: Load Parzival cross-session memory from Qdrant
allowed-tools: Bash
---

## Load Policy

This skill is invoked **only on demand** from `[ST]` Session Start workflow step-01b. It does NOT auto-load at activation.

`parzival.md` activation step 4 verifies the **presence** of the core skills (aim-parzival-bootstrap, aim-parzival-constraints) in `{skills_path}` without reading their content. Per `parzival.md <rules> r6` ("Load files ONLY when executing user-chosen workflow"), skill content is read only when the menu command that uses the skill is invoked.

# Parzival Bootstrap — Cross-Session Memory

Load cross-session context from previous Parzival sessions stored in Qdrant. This replaces the automatic startup injection with an on-demand skill invocation.

## Steps

1. Run the following Python script to retrieve cross-session context:

```python
import sys
import os
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

# Set up import path for ai-memory source
_install_dir = os.path.expanduser("~/.ai-memory")
sys.path.insert(0, os.path.join(_install_dir, "src"))

# Option P: load Tier B helper from sibling module (enables unit testing)
_bootstrap_skill_dir = os.path.join(_install_dir, "_ai-memory", "pov", "skills", "aim-parzival-bootstrap")
if _bootstrap_skill_dir not in sys.path:
    sys.path.insert(0, _bootstrap_skill_dir)
try:
    from sanctum_tier_b import load_sanctum_tier_b
except ImportError:
    load_sanctum_tier_b = None

start_ms = time.perf_counter()
_trace_start = datetime.now(tz=timezone.utc)

try:
    from memory.config import MemoryConfig
    from memory.search import MemorySearch
    from memory.injection import (
        retrieve_bootstrap_context,
        select_results_greedy,
        format_injection_output,
        init_session_state,
        log_injection_event,
    )
    from memory.project import detect_project
    from memory.qdrant_client import QdrantUnavailable
except ImportError as e:
    print(f"## Cross-Session Memory (Parzival Bootstrap)\n")
    print(f"**Unavailable**: AI Memory module not installed ({e})")
    print(f"\nBootstrap: import error | Qdrant: unknown")
    sys.exit(0)

# Optional: Prometheus metrics (best-effort, never blocks)
try:
    from memory.metrics_push import push_skill_metrics_async
except ImportError:
    push_skill_metrics_async = None

# Optional: Langfuse trace events (best-effort, never blocks)
# LANGFUSE: V3 ONLY. See LANGFUSE-INTEGRATION-SPEC.md
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 10000

try:
    config = MemoryConfig()
except Exception as e:
    print(f"## Cross-Session Memory (Parzival Bootstrap)\n")
    print(f"**Unavailable**: Failed to load configuration ({e})")
    print(f"\nBootstrap: config error | Qdrant: unknown")
    sys.exit(0)

if not config.parzival_enabled:
    print("## Cross-Session Memory (Parzival Bootstrap)\n")
    print("Parzival is not enabled. Set `PARZIVAL_ENABLED=true` in .env to activate.")
    sys.exit(0)


class _LayerStatusCapture(logging.Handler):
    """Capture named warnings from ai_memory.injection to track per-layer Qdrant status."""

    _LAYER_WARNINGS = frozenset({
        "bootstrap_handoff_unavailable",
        "bootstrap_decisions_unavailable",
        "bootstrap_insights_unavailable",
        "bootstrap_github_unavailable",
    })

    def __init__(self):
        super().__init__()
        self.failed_layers = set()

    def emit(self, record):
        if record.getMessage() in self._LAYER_WARNINGS or record.msg in self._LAYER_WARNINGS:
            self.failed_layers.add(record.msg)


try:
    project_name = detect_project(os.getcwd())
    search_client = MemorySearch(config)
    session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")

    # Per-layer Qdrant status tracking (BUG-285)
    _capture = _LayerStatusCapture()
    _injection_logger = logging.getLogger("ai_memory.injection")
    _injection_logger.addHandler(_capture)

    # Retrieve bootstrap context from Qdrant.
    # BUG-297 / BP-158 P2: retrieve_bootstrap_context returns (results, meta);
    # meta carries the Layer 1 handoff-ceiling rejection signal.
    results, retrieval_meta = retrieve_bootstrap_context(
        search_client, project_name, config
    )

    _injection_logger.removeHandler(_capture)

    # Compute accurate Qdrant status from per-layer capture
    if not _capture.failed_layers:
        _qdrant_status = "available"
    elif len(_capture.failed_layers) == 4:
        _qdrant_status = "unreachable (all retrieval calls failed)"
    else:
        _n_fail = len(_capture.failed_layers)
        _qdrant_status = f"degraded ({_n_fail} of 4 layers unreachable)"

    # Greedy-fill within token budget.
    # BUG-297 / BP-158 P2: pass return_meta=True so handoff-class budget
    # rejections surface as fallback_signaled in the returned meta dict.
    selected, tokens_used, greedy_meta = select_results_greedy(
        results,
        config.bootstrap_token_budget,
        tier=1,
        return_meta=True,
    )

    # BUG-297 / BP-158 P2: merge fallback signals from both retrieval pre-filter
    # (Layer 1 ceiling) and greedy fill (snippet budget). Either is grounds for
    # the L1 Handoff Gate to invoke filesystem fallback at step-01b.
    _fallback_signaled = bool(
        retrieval_meta.get("fallback_signaled")
        or greedy_meta.get("fallback_signaled")
    )
    _fallback_reject = None
    for _r in list(retrieval_meta.get("rejects", [])) + list(
        greedy_meta.get("rejects", [])
    ):
        if _r.get("reason") in ("budget_exceeded", "ceiling_exceeded") and (
            _r.get("type") == "agent_handoff"
        ):
            _fallback_reject = _r
            break

    # Format as markdown with attribution
    formatted = format_injection_output(selected, tier=1)

    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    duration_seconds = time.perf_counter() - start_ms

    # Initialize session state for Tier 2 deduplication (HIGH)
    injected_ids = [str(r.get("id", "")) for r in selected if r.get("id")]
    init_session_state(session_id, injected_ids)

    # Audit log (HIGH)
    audit_dir = Path(os.getcwd()) / ".audit"
    log_injection_event(
        tier=1,
        trigger="skill:aim-parzival-bootstrap",
        project=project_name,
        session_id=session_id,
        results_considered=len(results),
        results_selected=len(selected),
        tokens_used=tokens_used,
        budget=config.bootstrap_token_budget,
        audit_dir=audit_dir,
    )

    # Tier B — sanctum LORE + BOND prepend (filesystem-only per DEC-253-14)
    if load_sanctum_tier_b is not None:
        try:
            sanctum_path = Path(os.getcwd()) / "_ai-memory" / "sanctum"
            tier_b_output = load_sanctum_tier_b(sanctum_path)
            if tier_b_output:
                print(tier_b_output)
        except Exception:
            pass
        try:
            workspace_root = Path(os.getcwd())
            source_repo_candidate = workspace_root.parent / "ai-memory"
            if source_repo_candidate.exists() and (source_repo_candidate / ".git").exists():
                from sanctum_tier_b import warn_if_workspace_stale
                warn_if_workspace_stale(workspace_root / "_ai-memory", source_repo_candidate)
        except Exception:
            pass  # Best-effort; never blocks bootstrap

    # Build output
    print("## Cross-Session Memory (Parzival Bootstrap)\n")

    # BUG-297 / BP-158 P2: FALLBACK-NEEDED marker emitted as the FIRST
    # content line of this block when a handoff-class result was rejected
    # at retrieval time (ceiling) or by greedy fill (budget). The L1
    # Handoff Gate at step-01b-parzival-bootstrap (CASE B) parses this
    # marker to trigger filesystem fallback so cross-session continuity
    # never silently degrades.
    if _fallback_signaled:
        _r = _fallback_reject or {}
        _r_reason = _r.get("reason", "budget_exceeded")
        _r_type = _r.get("type", "agent_handoff")
        _r_tokens = _r.get("tokens", 0)
        if _r_reason == "ceiling_exceeded":
            _r_budget = config.handoff_ceiling_tokens
        else:
            _r_budget = greedy_meta.get("budget", config.bootstrap_token_budget)
        print(
            f"[FALLBACK-NEEDED: reason={_r_reason} type={_r_type} "
            f"tokens={_r_tokens} budget={_r_budget}]\n"
        )

    if not selected:
        print("No cross-session memories found for this project.\n")
    else:
        # Group results by type for organized display
        handoffs = [r for r in selected if r.get("type") == "agent_handoff"]
        decisions = [r for r in selected if r.get("type") in ("decision", "agent_memory")]
        insights = [r for r in selected if r.get("type") == "agent_insight"]
        github = [r for r in selected if r.get("type", "").startswith("github_")]
        other = [r for r in selected if r not in handoffs + decisions + insights + github]

        if handoffs:
            print("### Last Handoff\n")
            for h in handoffs:
                print(h.get("content", "").strip())
                print()

        if decisions:
            print("### Recent Decisions\n")
            for d in decisions:
                score_pct = int(d.get("score", 0) * 100)
                print(f"- **[{score_pct}%]** {d.get('content', '').strip()[:200]}")
            print()

        if insights:
            print("### Insights\n")
            for i in insights:
                score_pct = int(i.get("score", 0) * 100)
                print(f"- **[{score_pct}%]** {i.get('content', '').strip()[:200]}")
            print()

        if github:
            print("### GitHub Activity (since last session)\n")
            for g in github:
                score_pct = int(g.get("score", 0) * 100)
                print(f"- **[{g.get('type', 'github')}|{score_pct}%]** {g.get('content', '').strip()[:200]}")
            print()

        if other:
            print("### Other Context\n")
            for o in other:
                score_pct = int(o.get("score", 0) * 100)
                print(f"- **[{o.get('type', 'unknown')}|{score_pct}%]** {o.get('content', '').strip()[:200]}")
            print()

        # Include raw formatted output for full context
        print("<details><summary>Raw retrieved context</summary>\n")
        print(formatted)
        print("\n</details>\n")

    print("---")
    print(f"Bootstrap: {len(selected)} results | {tokens_used} tokens | {elapsed_ms}ms | Qdrant: {_qdrant_status}")

    # Prometheus metrics (CRITICAL — best-effort, never blocks)
    if push_skill_metrics_async:
        try:
            push_skill_metrics_async(
                "aim-parzival-bootstrap",
                "success" if selected else "empty",
                duration_seconds,
            )
        except Exception:
            pass

    # Top-level Langfuse trace (MEDIUM — best-effort, never blocks)
    # LANGFUSE: V3 trace buffer pattern. See LANGFUSE-INTEGRATION-SPEC.md §3.1
    if emit_trace_event:
        try:
            emit_trace_event(
                event_type="skill_bootstrap",
                data={
                    "input": f"Parzival bootstrap skill for project: {project_name}",
                    "output": f"Selected {len(selected)} results, {tokens_used} tokens, {elapsed_ms}ms"[:TRACE_CONTENT_MAX],
                    "metadata": {
                        "skill_name": "aim-parzival-bootstrap",
                        "project_name": project_name,
                        "results_considered": len(results),
                        "results_selected": len(selected),
                        "tokens_used": tokens_used,
                        "elapsed_ms": elapsed_ms,
                        "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                        "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                    },
                },
                project_id=project_name,
                session_id=session_id,
                start_time=_trace_start,
                end_time=datetime.now(tz=timezone.utc),
                tags=["skill", "bootstrap"],
            )
        except Exception:
            pass

except (QdrantUnavailable, ConnectionError, TimeoutError) as e:
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    print("## Cross-Session Memory (Parzival Bootstrap)\n")
    print(f"**Qdrant unavailable**: {e}\n")
    print("Continuing with file-based context only.\n")
    print("---")
    print(f"Bootstrap: 0 results | 0 tokens | {elapsed_ms}ms | Qdrant: unavailable")
    if push_skill_metrics_async:
        try:
            push_skill_metrics_async("aim-parzival-bootstrap", "failed", time.perf_counter() - start_ms)
        except Exception:
            pass

except Exception as e:
    elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
    error_type = type(e).__name__
    print("## Cross-Session Memory (Parzival Bootstrap)\n")
    print(f"**Error retrieving context**: {error_type}: {e}\n")
    print("Continuing with file-based context only.\n")
    print("---")
    print(f"Bootstrap: 0 results | 0 tokens | {elapsed_ms}ms | Qdrant: error")
    if push_skill_metrics_async:
        try:
            push_skill_metrics_async("aim-parzival-bootstrap", "failed", time.perf_counter() - start_ms)
        except Exception:
            pass
```

2. Include the script output in your current context as cross-session memory from previous Parzival sessions.

3. If the script reports Qdrant unavailable or an error, note this and continue with file-based context only (MEMORY.md, oversight/ files).
