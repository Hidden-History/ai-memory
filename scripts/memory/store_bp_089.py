#!/usr/bin/env python3
"""Store BP-089: Progressive Context Injection and Adaptive Token Budgets to conventions collection.

This script stores the progressive context injection and adaptive token budget
best practices research to the database for semantic retrieval.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.storage import store_best_practice

# Condensed version for storage (optimized for semantic search)
# Full document: oversight/knowledge/best-practices/BP-089-progressive-context-injection-adaptive-token-budgets-2026.md
CONTENT = """
Progressive Context Injection and Adaptive Token Budget Strategies for RAG-Augmented LLM Coding Assistants (2025-2026)

ADAPTIVE VS FIXED TOKEN BUDGETS:
- Fixed budgets (e.g. PER_TURN_TOKEN_BUDGET=1000) are suboptimal — waste tokens on simple queries, starve complex ones
- TALE (ACL 2025): Dynamic budgets achieve 81% accuracy at 32% of vanilla token cost
- SelfBudgeter: 74.5% response length compression while maintaining accuracy
- Progressive Context Loading: Session costs reduced from $4.50 to $0.06 (98.7% reduction) via demand-driven loading
- No major production system uses a single fixed budget — all use variable/adaptive approaches
- Recommended: Adaptive range with floor (500 tokens) and ceiling (1500 tokens)
- Adaptive signal: 60% quality factor (best retrieval score) + 40% relevance density (results above threshold)
- Migration: PER_TURN_TOKEN_BUDGET=1000 becomes midpoint of [500, 1500] adaptive range

CONFIDENCE THRESHOLD GATING — WHEN TO SKIP INJECTION:
- Critical insight: Unconditional retrieval frequently HURTS accuracy (TARG research)
- TARG: Always-retrieving achieved only 48.6% EM vs 53.8% for never-retrieving on NQ-Open
- Selective gating achieved 57.6% EM by retrieving for only 0.8% of queries
- SEAL-RAG: "Context Dilution" is the primary failure mode — marginally relevant content drowns the signal
- Pattern 1: Fixed threshold (0.6) — simple, predictable
- Pattern 2: Per-collection thresholds — conventions=0.65, code-patterns=0.55, discussions=0.60, jira-data=0.60
- Pattern 3: Margin-based uncertainty (TARG) — gap between top-1 and top-2 scores is better gating signal than absolute score
- Hard floor: Never inject below 0.45 — below this even "relevant" results are noise
- Key TARG insight: Large margin between top-1 and top-2 = confident retrieval; tiny margin = ambiguous retrieval

SELECTION ALGORITHMS FOR FILLING TOKEN BUDGET:
- Greedy fill by score: O(N), good for uniform chunks, sufficient for top_k <= 5
- Greedy with redundancy penalty (AdaGReS, 2025): State-of-the-art, prevents near-duplicate chunks consuming budget
- AdaGReS objective: Maximize alpha*sum(sim(q,c)) - beta*sum(sim(c_i,c_j)) subject to token budget
- Adaptive beta calibration eliminates manual tuning — adapts to candidate pool statistics per-query
- Theoretical guarantee: epsilon-approximate submodularity, near-optimal for greedy selection
- Density-based (score/tokens): Prioritize high information density when chunk sizes vary
- Knapsack NOT recommended: assumes additive utility (wrong for submodular relevance), greedy dominates at small N
- Recommendation: Greedy fill for ai-memory (top_k <= 5, uniform chunks); AdaGReS for discussions collection

THREE-TIER INJECTION ARCHITECTURE:
- Tier 1 Bootstrap (SessionStart): 2000-3000 tokens — session resume, active task, sprint goal, recent files, blockers
- Tier 2 Per-Turn (UserPromptSubmit): 500-1500 tokens adaptive — relevance-filtered memories from routed collections
- Tier 3 Tool-Triggered: 500-1000 tokens — file-type conventions, code patterns for edited file
- Do NOT put full code patterns, all conventions, or discussion history in Tier 1 — those are Tier 2/3

COMPETITIVE ANALYSIS — PRODUCTION CODING ASSISTANTS:
- Cursor: Local embeddings, @-symbol context, IDE-managed budget, three-layer agent architecture
- Continue.dev: Shifted from @Codebase to agent-driven tool-based retrieval (reactive recall over proactive injection)
- Sourcegraph Cody: Abandoned embeddings for BM25+ranking, "First N snippets" implicit budgeting
- Augment Code: Cloud real-time semantic index (400K-500K files), custom-trained context models, "Context is the new compiler"
- All moved from monolithic context loading to demand-driven progressive injection

ADAPTIVE BUDGET SIGNALS:
- Primary (implement now): best retrieval score, results above threshold count, score margin top-1 vs top-2, collection routed to
- Secondary (phase 2+): query complexity, session turn count, available context window, topic drift between turns
- Tier 2 budget formula: 50% quality weight + 30% density weight + 20% session/drift weight

CONFIG DESIGN:
- BOOTSTRAP_TOKEN_BUDGET=2500 (Tier 1, keep as-is)
- PER_TURN_BUDGET_FLOOR=500 (Tier 2 minimum)
- PER_TURN_BUDGET_CEILING=1500 (Tier 2 maximum)
- CONFIDENCE_THRESHOLD_TIER2=0.6 (below: skip injection)
- HARD_FLOOR_THRESHOLD=0.45 (never inject below this)
- INJECTION_FILE_BUDGET=500 (Tier 3, keep as-is)
- SELECTION_ALGORITHM=greedy_fill (options: greedy_fill, density, adagres)

IMPLEMENTATION PRIORITY:
- Phase 1 (Small/High): Add confidence gating to UserPromptSubmit hook — skip when best_score < 0.6
- Phase 2 (Medium/High): Replace fixed 1000 with adaptive range [500, 1500] driven by retrieval quality
- Phase 3 (Small/Medium): Per-collection confidence thresholds (0.55 code, 0.65 conventions)
- Phase 4 (Small/Low-Med): Density-based selection for variable-size chunks
- Phase 5 (Medium/Low): AdaGReS redundancy penalty for discussions collection

EXPECTED IMPACT:
- Avg tokens injected: ~1000 (always) -> ~600-800 (varies)
- Turns with no injection (gated): 0% -> ~30-40%
- Noise injections (score < 0.6): ~30% -> 0% (gated out)
- Wasted tokens per session (20 turns): ~6000-8000 -> ~2000-3000

Sources: TALE (ACL 2025), SelfBudgeter (arXiv 2505.11274), AdaGReS (arXiv 2512.25052),
TARG (arXiv 2511.09803), SEAL-RAG (arXiv 2512.10787), Cursor, Continue.dev, Sourcegraph Cody,
Augment Code, Progressive Context Loading (Zujkowski 2025), BP-076, PLAN-006
""".strip()


def main():
    """Store BP-089 to conventions collection."""
    session_id = os.environ.get("CLAUDE_SESSION_ID", "bp-089-storage")

    print("Storing BP-089 to conventions collection...")
    print(f"Session ID: {session_id}")
    print(f"Content length: {len(CONTENT)} chars")

    try:
        result = store_best_practice(
            content=CONTENT,
            session_id=session_id,
            source_hook="manual",
            domain="progressive-context-injection-adaptive-token-budgets",
            tags=[
                "adaptive-token-budget",
                "progressive-context-injection",
                "confidence-threshold",
                "retrieval-gating",
                "selection-algorithm",
                "greedy-fill",
                "adagres",
                "three-tier-injection",
                "rag",
                "context-management",
                "token-budget",
                "coding-assistant",
            ],
            source="oversight/knowledge/best-practices/BP-089-progressive-context-injection-adaptive-token-budgets-2026.md",
            source_date="2026-02-13",
            auto_seeded=True,
            type="guideline",
            bp_id="BP-089",
            doc_type="best-practice",
            topic="progressive-context-injection-adaptive-token-budgets",
            created="2026-02-13",
        )

        print("\nStorage Result:")
        print(f"  Status: {result.get('status')}")
        print(f"  Memory ID: {result.get('memory_id')}")
        print(f"  Embedding Status: {result.get('embedding_status')}")
        print(f"  Collection: {result.get('collection')}")
        print(f"  Group ID: {result.get('group_id')}")

        if result.get("status") == "stored":
            print("\nSUCCESS: BP-089 stored to conventions collection")
            return 0
        elif result.get("status") == "duplicate":
            print("\nDUPLICATE: BP-089 already exists in database")
            return 0
        else:
            print(f"\nWARNING: Unexpected status: {result.get('status')}")
            return 1

    except Exception as e:
        print("\nERROR: Failed to store BP-089")
        print(f"  Error: {e!s}")
        print(f"  Type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
