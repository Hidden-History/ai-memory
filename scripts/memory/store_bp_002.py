#!/usr/bin/env python3
"""Store BP-002: Conversation Memory Best Practices to conventions collection.

This script stores the comprehensive conversation memory best practices research
to the database for semantic retrieval.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.storage import store_best_practice

# Condensed version for storage (optimized for semantic search)
# Full document available at: oversight/knowledge/best-practices/BP-002-conversation-memory-vector-databases-2026.md
CONTENT = """
Conversation Memory Best Practices for Vector Databases (2026)

STORAGE STRATEGY:
- Store individual turns separately (user vs assistant)
- Chunk size: 300-500 tokens with 10-20% overlap
- Use late chunking for messages >2000 tokens (Jina 8K context)
- Multi-level summarization: turn-level, topic-level (5-10 turns), session-level (15+ turns)
- Deduplication at 0.92 cosine similarity threshold

PAYLOAD STRUCTURE (Qdrant):
- role: "user" | "assistant"
- message_type: "question" | "answer" | "clarification"
- topics: ["api_usage", "error_handling"]
- entities: ["FastAPI", "Python"]
- tools_used, files_modified: track actions
- parent_message_id, session_id: maintain context

CONTEXT RECONSTRUCTION:
- Token budget: 8,000 tokens total
  - Session summary: 500 tokens
  - Recent turns (last 5-10): 2,000 tokens
  - Retrieved memories (top-10): 4,500 tokens
  - Entity facts: 1,000 tokens

HYBRID RETRIEVAL SCORING:
- Semantic relevance: 45% weight
- Recency (1-week half-life): 25% weight
- Type priority (summaries 1.2x): 15% weight
- Entity overlap: 10% weight
- Same session boost: 5% weight

RETRIEVAL STRATEGY:
1. Session context: Last 5-10 turns verbatim + summary
2. Semantic retrieval: Top-15 by hybrid score
3. Diversity filter: Max 3 from same past session
4. Deduplicate similar (>0.95 similarity)

SIZE POLICIES:
- <300 tokens: Store whole
- 300-800 tokens: Store or summarize
- 800-2000 tokens: Chunk by topic
- 2000-8192 tokens: Late chunking
- >8192 tokens: Hierarchical processing

DEDUPLICATION:
- Level 1: SHA-256 content hash (exact)
- Level 2: Fuzzy matching (>95% textual similarity)
- Level 3: Semantic (0.90-0.95 cosine similarity)
- User questions: Lower threshold (0.88) for repetition handling

QDRANT CONFIGURATION:
- Single collection with payload filtering (multi-tenant)
- Indexes: user_id, session_id, timestamp, topics
- Distance: Cosine similarity
- Storage: Vectors in RAM, payloads auto-optimized

PRODUCTION ARCHITECTURES:
- Mem0: Memory-centric, 1.4s latency, graph-based relationships
- MemGPT/Letta: OS-inspired memory tiers, self-editing core memory
- LangMem: LangChain SDK, semantic/episodic/procedural memory types

CAPACITY PLANNING:
- 1000 users × 10 sessions/month × 20 turns × 6 months retention = 1.2M turns
- Storage per point: ~5KB (768 float32 vector + 2KB payload)
- Total: ~5.7GB base, ~11.4GB with summaries/facts

KEY METRICS:
- Search latency: <100ms (p95)
- Retrieval recall@10: >80%
- Deduplication rate: 10-20%
- Context token usage: monitor average per query

PITFALLS TO AVOID:
- Never truncate user instructions (summarize instead)
- Always filter by user_id to prevent cross-contamination
- Don't exceed 8192 token Jina limit (pre-chunk if needed)
- Implement retention policies (90 days default)
- Version embedding model for migration planning

IMPLEMENTATION PHASES:
Week 1: Basic storage (turns, indexes, search)
Week 2: Chunking & summarization
Week 3: Retrieval & context reconstruction
Week 4: Deduplication
Week 5-6: Production hardening (background workers, monitoring)
Week 7+: Advanced (AFM, entity extraction, reranking)

Sources: Mem0, MemGPT/Letta, LangMem (2025-2026), Qdrant docs, Jina embeddings v2/v3,
NVIDIA NeMo, Adaptive Focus Memory paper, LOCOMO benchmark, 50+ production RAG sources
""".strip()


def main():
    """Store BP-002 to conventions collection."""

    # Get session ID from environment or use default
    session_id = os.environ.get("CLAUDE_SESSION_ID", "bp-002-storage")

    print("Storing BP-002 to conventions collection...")
    print(f"Session ID: {session_id}")
    print(f"Content length: {len(CONTENT)} chars")

    try:
        result = store_best_practice(
            content=CONTENT,
            session_id=session_id,
            source_hook="manual",
            domain="conversation-memory",
            tags=[
                "vector-database",
                "qdrant",
                "jina-embeddings",
                "rag",
                "semantic-retrieval",
                "conversation-history",
                "chunking",
                "deduplication",
                "context-reconstruction",
                "memory-management",
            ],
            source="https://github.com/ai-memory/docs/conversation-memory-best-practices.md",
            source_date="2026-02-06",
            auto_seeded=True,
            type="guideline",
        )

        print("\n✓ Storage Result:")
        print(f"  Status: {result.get('status')}")
        print(f"  Memory ID: {result.get('memory_id')}")
        print(f"  Embedding Status: {result.get('embedding_status')}")
        print(f"  Collection: {result.get('collection')}")
        print(f"  Group ID: {result.get('group_id')}")

        if result.get("status") == "stored":
            print("\n✓ SUCCESS: BP-002 stored to conventions collection")
            return 0
        elif result.get("status") == "duplicate":
            print("\n! DUPLICATE: BP-002 already exists in database")
            return 0
        else:
            print(f"\n✗ WARNING: Unexpected status: {result.get('status')}")
            return 1

    except Exception as e:
        print("\n✗ ERROR: Failed to store BP-002")
        print(f"  Error: {e!s}")
        print(f"  Type: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
