# Conversation Memory Best Practices for Vector Databases (2026)

> **SUPERSEDED**: This is a research reference document. The authoritative implementation spec is **`oversight/specs/Chunking-Strategy-V2.md`** (V2.1). Where this document recommends truncation for storage, the V2.1 spec mandates **zero truncation** — content is chunked into multiple vectors, never discarded. Refer to the spec for all implementation decisions.

**Date:** 2026-02-06
**Technology Stack:** Qdrant + Jina Embeddings (768-dim, 8192 token context)
**Document Version:** 1.1 (superseded notice added 2026-02-07)

## Executive Summary

This document synthesizes 2026 best practices for storing AI assistant conversation history in vector databases for semantic retrieval. It covers production architectures from Mem0, MemGPT/Letta, LangMem, and industry-standard RAG systems, with specific recommendations for Qdrant and Jina embeddings.

---

## 1. Storing Individual Conversation Turns

### 1.1 Storage Granularity

**Current Best Practice (2026):**
- **Multi-granularity chunking** outperforms naive turn- or session-level chunking
- **Topically segmented units** provide better retrieval precision due to higher topical purity and reduced irrelevant detail
- Single exchange units between user and agent (conversational turns) should be identified, segmented, and transformed into structured summaries

**Recommendation for Your System:**
```
Option A: Store each message as a whole (preferred for <512 tokens)
- User messages: Single vector point
- Agent responses: Single vector point
- Advantages: Preserves complete context, simpler implementation
- Disadvantages: May embed multiple topics in one vector

Option B: Topical chunking (preferred for >512 tokens)
- Split long messages by topic shifts using semantic chunking
- Each chunk: 256-512 tokens with 10-20% overlap
- Advantages: Better retrieval precision, handles multi-topic messages
- Disadvantages: More complex implementation, more storage
```

### 1.2 Maximum Token Count Per Vector Point

**Research-Backed Recommendations:**
- **Optimal range: 256-512 tokens** per chunk for most RAG applications
- **Hard limit: 8192 tokens** (Jina embeddings v2/v3 maximum context)
- **Sweet spot: 400 tokens with 10-20% overlap** achieves 88-89% recall (Chroma research)

**Token Size Guidelines:**
- **128-256 tokens:** Best for fact-based queries requiring precise keyword matching
- **256-512 tokens:** Best for tasks requiring broader context (summarization, concept understanding)
- **512+ tokens:** Risk of weaker embeddings representing too many ideas simultaneously

**For Conversation Memory:**
```
Recommended: 300-500 tokens per point
- Short messages (<300 tokens): Store whole
- Medium messages (300-800 tokens): Store whole or split by topic
- Long messages (>800 tokens): Apply semantic/topical chunking
```

### 1.3 User Messages vs Agent Responses

**Separate Storage Approach (Recommended):**

Production systems increasingly partition memory into user, assistant, and shared slots, with role-distinguishing tokens or embeddings.

```python
# Qdrant payload structure
{
    "vector": [...],  # 768-dim embedding
    "payload": {
        "role": "user" | "assistant",
        "message_id": "uuid",
        "conversation_id": "uuid",
        "timestamp": "2026-02-06T10:30:00Z",
        "token_count": 342,
        "content": "original text",
        "content_hash": "sha256...",

        # Metadata for retrieval
        "message_type": "question" | "answer" | "clarification",
        "topics": ["api_usage", "error_handling"],
        "entities": ["FastAPI", "Python"],
        "tools_used": ["code_execution", "file_read"],
        "files_modified": ["/path/to/file.py"],

        # Context linking
        "parent_message_id": "uuid",
        "thread_position": 3,
        "session_id": "uuid"
    }
}
```

**Why Separate?**
- Different retrieval patterns (user intent vs solution patterns)
- Enables role-specific filtering
- Better deduplication (users often repeat similar questions)
- Supports asymmetric retrieval strategies

### 1.4 Late Chunking Strategy

**For 8192-Token Context (Jina Embeddings):**

Late chunking leverages long-context embedding models by:
1. Embedding all tokens of long text first (full 8192-token capacity)
2. Applying chunking after transformer model, before mean pooling
3. Resulting embeddings capture full contextual information

**Implementation:**
```python
# With Jina API
response = jina_client.embed(
    input=["full conversation text up to 8192 tokens"],
    late_chunking=True,
    model="jina-embeddings-v3"
)
# Returns list of chunk embeddings with global context preserved
```

**Benefits:**
- Preserves cross-chunk context
- 35% performance improvement over naive chunking
- Ideal for multi-turn conversations with topic continuity

---

## 2. Session Summaries

### 2.1 Summarization Approach

**Multi-Level Summarization (Production Standard):**

```
Level 1: Turn-level (immediate)
├─ Each exchange: 1-2 sentence summary
├─ Key entities and actions extracted
└─ Stored alongside raw turn

Level 2: Topic segments (5-10 turns)
├─ Topical coherence: group related turns
├─ 3-5 sentence summary per topic
└─ Preserve: decisions made, problems solved, context established

Level 3: Session-level (end of conversation)
├─ Executive summary: 1 paragraph
├─ Key outcomes and unresolved items
└─ Important context for future sessions
```

### 2.2 Summary Storage Strategy

**Best Practice (2026):**
- **Store summaries as separate vector points** with special payload marking
- **Chunk summaries if >500 tokens** (same rules as regular messages)
- **Use hierarchical retrieval**: Check summaries first, then drill into turns

**Summary Quality Standards:**
- Mark uncertain facts as "UNVERIFIED" rather than guessing
- Organize details into categories/sections vs long paragraphs
- Include timing of events for temporal reasoning
- Highlight important events: issue resolved, information uncovered, details collected
- Ensure no self-contradiction or conflicts with system instructions

### 2.3 Critical Metadata for Summaries

```python
{
    "vector": [...],
    "payload": {
        "content_type": "summary",
        "summary_level": "turn" | "topic" | "session",
        "summary_of_ids": ["msg1", "msg2", "msg3"],
        "time_range": {
            "start": "2026-02-06T10:00:00Z",
            "end": "2026-02-06T11:30:00Z"
        },

        # Critical for retrieval
        "tools_used": ["bash", "read", "edit", "grep"],
        "files_modified": [
            "/src/api/endpoints.py",
            "/tests/test_api.py"
        ],
        "key_decisions": [
            "Switched to async implementation",
            "Added Redis caching layer"
        ],
        "unresolved_items": [
            "Performance testing needed",
            "Documentation update pending"
        ],

        # Structured outcomes
        "problems_solved": ["ISSUE-123: API timeout"],
        "entities_mentioned": {
            "technologies": ["Redis", "FastAPI"],
            "files": [...],
            "concepts": ["async", "caching"]
        }
    }
}
```

### 2.4 Session Summary Timing

**When to Create Summaries:**
- **Turn-level:** After every 1-2 exchanges (real-time)
- **Topic-level:** When topic shift detected (semantic similarity drop)
- **Session-level:** At conversation end or after 15+ turns
- **Background processing:** Use async workers to avoid blocking conversation

---

## 3. Context Reconstruction

### 3.1 Token Budget Management

**2026 Standard Approach:**

```
Total Context Window (e.g., 200K tokens for Claude Opus 4.6)
├─ System Prompt: 5-10% (10-20K tokens)
├─ Retrieved Memories: 20-30% (40-60K tokens)
├─ Current Conversation: 30-40% (60-80K tokens)
├─ Documents/Code: 20-30% (40-60K tokens)
└─ Output Reserve: 10-20% (20-40K tokens)
```

**Memory Budget Allocation:**
```python
memory_budget = {
    "session_summary": 500,      # Current session overview
    "relevant_past": 3000,       # Top-k similar past interactions
    "recent_context": 2000,      # Last 5-10 turns verbatim
    "entity_facts": 1000,        # User preferences, established facts
    "procedural": 500            # How-to knowledge, established patterns
}
```

### 3.2 Priority Ordering: Relevance vs Recency vs Type

**Hybrid Scoring Model (Industry Standard 2026):**

```python
def compute_retrieval_score(memory_point, query):
    """
    Balanced scoring combining multiple factors
    """
    # Semantic relevance (40-50% weight)
    semantic_score = cosine_similarity(query_embedding, memory_embedding)

    # Recency (20-30% weight)
    age_hours = (now - timestamp).hours
    recency_score = exp(-age_hours / 168)  # Half-life of 1 week

    # Type priority (10-20% weight)
    type_weights = {
        "summary": 1.2,      # Summaries more valuable
        "user": 1.0,
        "assistant": 0.9,
        "system": 0.8
    }
    type_score = type_weights.get(memory_point["role"], 1.0)

    # Contextual factors (10-20% weight)
    same_session_boost = 1.5 if same_session else 1.0
    entity_overlap = len(set(query_entities) & set(memory_entities)) / max(len(query_entities), 1)

    final_score = (
        0.45 * semantic_score +
        0.25 * recency_score +
        0.15 * type_score +
        0.10 * entity_overlap +
        0.05 * same_session_boost
    )

    return final_score
```

**Retrieval Strategy:**
```
1. Session context (always include)
   ├─ Last 5-10 turns verbatim
   └─ Current session summary

2. Semantic retrieval (relevance-focused)
   ├─ Top-15 by hybrid score
   ├─ Diversity filter: Max 3 from same past session
   └─ Deduplicate semantically similar (>0.95 similarity)

3. Temporal retrieval (recency-focused)
   ├─ Last 5 user questions similar to current query
   └─ Recent actions on same files/topics

4. Type-specific retrieval
   ├─ Relevant summaries (max 3)
   ├─ Entity facts matching query
   └─ Procedural knowledge if query is "how-to"
```

### 3.3 Optimal Context Amount

**Research Findings (2026):**
- **Retrieval-augmented memory reduces token usage by 90-95%** vs full-context
- **Sliding window of 3-5 exchanges** captures immediate context
- **Beyond 20-30 retrieved memories:** Diminishing returns, increased noise
- **Context becomes noise when:**
  - Semantic similarity <0.7 to current query
  - From unrelated sessions with no shared entities
  - Older than 30 days without subsequent reference

**Practical Limits:**
```
Minimum effective context: 2,000 tokens
├─ Current session: 5 recent turns
└─ Top-5 relevant memories

Optimal context: 5,000-8,000 tokens
├─ Current session: 10 recent turns
├─ Session summary
├─ Top-10 relevant memories
└─ Relevant entity facts

Maximum before noise: 15,000 tokens
├─ Current session: Full history
├─ Top-20 relevant memories
└─ Multiple past session summaries
```

### 3.4 Sliding Window + Summarization Pattern

**Production Implementation:**
```python
def construct_context(current_session, query, max_tokens=8000):
    context_parts = []
    remaining_budget = max_tokens

    # 1. Session summary (always include)
    session_summary = summarize_session(current_session)
    context_parts.append(session_summary)
    remaining_budget -= count_tokens(session_summary)

    # 2. Recent turns (verbatim)
    recent_turns = current_session[-5:]
    context_parts.extend(recent_turns)
    remaining_budget -= sum(count_tokens(t) for t in recent_turns)

    # 3. Semantic retrieval with budget
    relevant_memories = hybrid_search(
        query=query,
        top_k=20,
        filters={"not_in_current_session": True}
    )

    for memory in relevant_memories:
        memory_tokens = count_tokens(memory["content"])
        if memory_tokens <= remaining_budget:
            context_parts.append(memory)
            remaining_budget -= memory_tokens
        else:
            # Summarize if important but too large
            if memory["score"] > 0.85:
                summary = summarize_memory(memory, max_tokens=remaining_budget)
                context_parts.append(summary)
            break

    return context_parts
```

---

## 4. Deduplication Strategies

### 4.1 Content Hash vs Semantic Similarity

**Multi-Level Deduplication (Best Practice):**

```
Level 1: Exact deduplication (content hash)
├─ SHA-256 of normalized content
├─ Use: Prevent storing identical messages
└─ When: Pre-ingestion

Level 2: Near-exact deduplication (fuzzy)
├─ Edit distance or MinHash
├─ Use: Catch copy-paste with minor edits
└─ Threshold: >95% textual similarity

Level 3: Semantic deduplication
├─ Cosine similarity of embeddings
├─ Use: Identify semantically equivalent messages
└─ Threshold: >0.90-0.95 similarity
```

### 4.2 Deduplication Thresholds

**NVIDIA NeMo Framework Guidelines:**
- **Cosine similarity threshold:** Pairs above threshold = semantic duplicates
- **Lower threshold (e.g., 0.90):** Stricter, requires higher similarity
- **Higher threshold (e.g., 0.95):** Aggressive, may remove somewhat similar content
- **Recommendation:** Start at 0.92, tune based on dataset characteristics

**Implementation:**
```python
def deduplicate_semantic(new_memory, existing_memories, threshold=0.92):
    """
    Check if new memory is semantically duplicate of existing
    """
    new_embedding = new_memory["vector"]

    # Check against recent memories from same user (sliding window)
    recent_window = existing_memories[-100:]  # Last 100 memories

    for existing in recent_window:
        similarity = cosine_similarity(new_embedding, existing["vector"])

        if similarity > threshold:
            # Semantic duplicate found
            # Decision: merge or skip?
            if should_merge(new_memory, existing):
                return merge_memories(new_memory, existing)
            else:
                return None  # Skip storing duplicate

    return new_memory  # Not a duplicate, store it
```

### 4.3 Near-Duplicate Handling

**Merge Strategy (Recommended for conversation memory):**
```python
def should_merge(new_memory, existing_memory):
    """
    Decide whether to merge or keep separate
    """
    # Don't merge if different roles
    if new_memory["role"] != existing_memory["role"]:
        return False

    # Don't merge if from different sessions
    if new_memory["session_id"] != existing_memory["session_id"]:
        return False

    # Don't merge if significant time gap
    time_diff = abs(new_memory["timestamp"] - existing_memory["timestamp"])
    if time_diff > timedelta(hours=24):
        return False

    # Merge if high similarity + same context
    return True

def merge_memories(new_memory, existing_memory):
    """
    Merge near-duplicate memories
    """
    return {
        "vector": existing_memory["vector"],  # Keep existing embedding
        "payload": {
            **existing_memory["payload"],
            "occurrences": existing_memory["payload"].get("occurrences", 1) + 1,
            "last_seen": new_memory["timestamp"],
            "variants": existing_memory["payload"].get("variants", []) + [
                {
                    "timestamp": new_memory["timestamp"],
                    "content_hash": new_memory["content_hash"]
                }
            ]
        }
    }
```

### 4.4 User Questions: Special Deduplication Case

Users often ask the same questions multiple times. Special handling:

```python
# Store user questions with deduplication
if role == "user" and is_question(content):
    similar_questions = search_similar(
        content=content,
        filters={"role": "user", "message_type": "question"},
        threshold=0.88  # Lower threshold for questions
    )

    if similar_questions:
        # Increment counter, update timestamp
        update_question_frequency(similar_questions[0], new_timestamp)

        # Still retrieve best answer, don't re-store question
        return retrieve_best_answer(similar_questions[0])
```

---

## 5. Content Size Limits and Truncation

### 5.1 Truncation vs Summarization vs Chunking

**Decision Matrix:**

| Content Size | Approach | Reasoning |
|--------------|----------|-----------|
| <300 tokens | Store whole | No processing needed, preserves full context |
| 300-800 tokens | Store whole or summarize | Depends on information density and retrieval pattern |
| 800-2000 tokens | Intelligent chunking | Split by topic/semantics, maintain overlap |
| 2000-8192 tokens | Late chunking + summarization | Use Jina's 8K context, then chunk embeddings |
| >8192 tokens | Hierarchical processing | Chunk first, then embed chunks separately |

### 5.2 When Truncation is Acceptable

**Acceptable Truncation:**
- **Log outputs:** Keep first 200 + last 200 tokens
- **Stack traces:** Keep error message + last 500 tokens
- **Repetitive content:** Truncate after pattern detected
- **Code snippets:** Truncate if >1000 tokens, store file reference instead

**Unacceptable Truncation (Data Loss):**
- **User instructions:** Never truncate, always summarize or chunk
- **Critical decisions:** Must preserve complete reasoning
- **Multi-part questions:** Truncation loses question structure
- **Conversation turns with references:** Breaking references = context loss

### 5.3 Intelligent Summarization Approach

**Adaptive Focus Memory (AFM) - 2026 State-of-the-Art:**

```python
def adaptive_focus_memory(message, relevance_score, age_days):
    """
    Dynamically assign fidelity level based on importance
    """
    # Fidelity levels
    FULL = "full"           # Verbatim storage
    COMPRESSED = "compressed"  # Summarized
    PLACEHOLDER = "placeholder"  # Metadata only

    # Importance classification
    is_high_importance = (
        relevance_score > 0.85 or
        "decision" in message["topics"] or
        message.get("unresolved_items") or
        message["tools_used"]
    )

    # Temporal decay
    temporal_factor = exp(-age_days / 30)  # 30-day half-life

    # Combined score
    importance = relevance_score * 0.7 + temporal_factor * 0.3

    if is_high_importance and importance > 0.7:
        return FULL  # Keep verbatim
    elif importance > 0.4:
        return COMPRESSED  # Summarize
    else:
        return PLACEHOLDER  # Metadata only
```

**Hierarchical Summarization:**
```python
def hierarchical_compress(old_messages, token_budget):
    """
    Compress older messages with progressive fidelity loss
    """
    compressed = []

    # Recent (last 7 days): Keep verbatim
    recent = [m for m in old_messages if age_days(m) <= 7]
    compressed.extend(recent)
    budget_used = sum(count_tokens(m) for m in recent)

    # Medium (7-30 days): Summarize per conversation
    medium = [m for m in old_messages if 7 < age_days(m) <= 30]
    for session in group_by_session(medium):
        summary = summarize_session(session, max_tokens=200)
        compressed.append(summary)
        budget_used += count_tokens(summary)

    # Old (30+ days): Only high-importance or placeholder
    old = [m for m in old_messages if age_days(m) > 30]
    for message in old:
        if is_high_importance(message):
            summary = summarize_message(message, max_tokens=100)
            compressed.append(summary)
        else:
            # Placeholder: metadata only
            compressed.append({
                "type": "placeholder",
                "id": message["id"],
                "timestamp": message["timestamp"],
                "topics": message["topics"]
            })

    return compressed
```

### 5.4 Content Size Policies

**Hard Limits (Qdrant + Jina):**
- **Single vector point payload:** 10MB (Qdrant default, can be configured)
- **Embedding input:** 8192 tokens (Jina v2/v3 limit)
- **Practical payload size:** <100KB per point for optimal performance

**Recommended Policies:**
```python
content_policies = {
    "conversation_turn": {
        "max_tokens": 2000,
        "over_limit_action": "chunk_by_topic",
        "preserve": ["user_intent", "key_decisions", "code_snippets"]
    },
    "session_summary": {
        "max_tokens": 1000,
        "over_limit_action": "hierarchical_summarize",
        "preserve": ["outcomes", "unresolved_items", "entity_facts"]
    },
    "code_context": {
        "max_tokens": 1500,
        "over_limit_action": "truncate_with_reference",
        "preserve": ["function_signatures", "class_definitions", "file_path"]
    },
    "error_logs": {
        "max_tokens": 800,
        "over_limit_action": "truncate_smart",  # First 200 + last 500
        "preserve": ["error_message", "stack_trace_tail"]
    }
}
```

---

## 6. Production System Architectures (2026)

### 6.1 Mem0 Architecture

**Key Features:**
- **Memory-centric architecture:** Dynamically extracts, consolidates, retrieves salient information
- **Graph-based variant (Mem0g):** Captures complex relational structures among conversational elements
- **Performance:** 66.9% judge accuracy, 1.4s latency (LOCOMO benchmark)

**Storage Strategy:**
```python
# Mem0 approach
{
    "entities": {
        "user_facts": [...],     # Long-term user profile
        "preferences": [...],    # User preferences
        "context": [...]         # Contextual information
    },
    "relations": {
        "entity_links": [...],   # Relationships between entities
        "temporal": [...]        # Time-based connections
    },
    "observations": {
        "conversation_turns": [...],  # Individual exchanges
        "summaries": [...]       # Session summaries
    }
}
```

**Strengths:**
- Fast retrieval (1.4s latency)
- Good for entity-centric conversations
- Automatic consolidation of facts

**Limitations:**
- Published benchmarks disputed by MemGPT team
- Less transparent implementation

### 6.2 MemGPT / Letta Architecture

**Core Innovation:** Virtual context management inspired by OS memory hierarchies

**Memory Tiers:**
```
In-Context Memory (limited by model window)
├─ Core Memory
│   ├─ Agent Persona (self-editable)
│   └─ User Information (self-editable)
└─ Active Conversation Window

Out-of-Context Memory (external storage)
├─ Archival Memory (vector DB)
│   ├─ Past conversations
│   ├─ Documents
│   └─ Long-term knowledge
└─ Recall Memory (traditional DB)
    ├─ Full conversation history
    └─ Structured metadata
```

**Self-Editing Memory:**
- Agent can update its own persona as it learns
- User information evolves over time
- Memory management through tool calls

**Performance:**
- ~48% on LOCOMO (disputed benchmarks)
- Higher latency (~4.4s) due to memory operations
- Excellent for long-term learning agents

**Strengths:**
- Transparent, open-source architecture
- Filesystem-based memory model
- Strong long-term context maintenance

### 6.3 LangMem (LangChain) Architecture

**Official Release:** December 2025 by LangChain

**Core Components:**
```
LangMem SDK
├─ Memory API (storage-agnostic)
├─ In-Hot-Path Tools (agent-accessible during conversation)
│   ├─ create_memory()
│   ├─ search_memories()
│   └─ update_memory()
└─ Background Memory Manager
    ├─ Automatic extraction
    ├─ Consolidation
    └─ Knowledge updates
```

**Memory Types:**
- **Semantic Memory:** Essential facts grounding agent responses
- **Episodic Memory:** Specific past interactions and events
- **Procedural Memory:** How-to knowledge and established patterns

**Integration:**
- Native with LangGraph Platform
- Works with any storage backend (Qdrant, Pinecone, Postgres)
- Uses LangGraph BaseStore for long-term memory
- LangGraph Checkpointers for execution history

**Namespace Strategy:**
```python
# Prevent memory cross-contamination
namespace_structure = {
    "user_id": "user_123",
    "agent_id": "agent_456",
    "context": "project_xyz"
}
# All memories tagged with namespace
```

**Strengths:**
- Seamless LangChain integration
- Background processing doesn't block conversation
- Clear separation of memory types
- Production-ready with LangGraph Platform

### 6.4 Hybrid Approaches (Industry Standard)

**2026 Production Pattern:**
```
Conversational Layer (hot path)
├─ Short-term buffer: Last 10 turns in memory
└─ Real-time memory operations

Memory Management Layer
├─ Background extraction: Topic shifts, entities, decisions
├─ Periodic summarization: Every 10-15 turns
└─ Consolidation: Merge similar memories

Storage Layer (Qdrant)
├─ Collections:
│   ├─ conversation_turns (raw turns)
│   ├─ session_summaries (summaries)
│   ├─ entity_facts (extracted facts)
│   └─ procedural_knowledge (how-tos)
└─ Indexes:
    ├─ user_id (payload index)
    ├─ session_id (payload index)
    ├─ timestamp (payload index)
    └─ topics (payload index)

Retrieval Layer
├─ Hybrid search: Vector + keyword (BM25)
├─ Reranking: Cross-encoder for final ordering
└─ Diversity: Max N from same source
```

---

## 7. Qdrant-Specific Best Practices

### 7.1 Collection Strategy

**Option A: Single Collection (Recommended)**
```python
# Unified collection with payload filtering
collection_name = "conversation_memory"

# Multi-tenancy via payload
payload_structure = {
    "user_id": "user_123",      # Index this
    "session_id": "session_456", # Index this
    "role": "user|assistant",
    "content_type": "turn|summary|fact",
    "timestamp": 1738843200
}

# Benefits:
# - Simpler management
# - Cross-user analytics possible
# - Efficient multi-tenancy
```

**Option B: Collection Per User**
```python
# Separate collection per user
collection_name = f"memory_user_{user_id}"

# Benefits:
# - Strong data isolation
# - User-specific optimization
# - Easier data deletion (drop collection)

# Drawbacks:
# - Collection proliferation
# - Management overhead
```

### 7.2 Indexing Strategy

**Critical Indexes (Payload):**
```python
# Index fields you filter by frequently
indexes = [
    {"field": "user_id", "type": "keyword"},
    {"field": "session_id", "type": "keyword"},
    {"field": "role", "type": "keyword"},
    {"field": "content_type", "type": "keyword"},
    {"field": "timestamp", "type": "integer"},
    {"field": "topics", "type": "keyword"},  # Array field
]

# Qdrant will speed up filtered searches
client.create_payload_index(
    collection_name="conversation_memory",
    field_name="user_id",
    field_schema="keyword"
)
```

**Storage Optimization:**
```python
# Store frequently accessed data in RAM
# Offload rarely used payloads to disk
collection_config = {
    "vectors": {
        "size": 768,
        "distance": "Cosine",
        "on_disk": False  # Vectors in RAM for speed
    },
    "payload_storage_type": "auto",  # Auto-optimize
}

# For cost optimization with large datasets
collection_config_disk = {
    "vectors": {
        "size": 768,
        "distance": "Cosine",
        "on_disk": True  # Vectors on SSD, use mmap
    },
    "payload_storage_type": "on_disk"
}
```

### 7.3 Search Configuration

**Basic Semantic Search:**
```python
results = client.search(
    collection_name="conversation_memory",
    query_vector=query_embedding,
    limit=20,
    score_threshold=0.7,  # Minimum similarity
    with_payload=True,
    with_vectors=False    # Don't return vectors (save bandwidth)
)
```

**Filtered Search (Common Pattern):**
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

results = client.search(
    collection_name="conversation_memory",
    query_vector=query_embedding,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="user_id",
                match=MatchValue(value="user_123")
            ),
            FieldCondition(
                key="role",
                match=MatchValue(value="assistant")
            )
        ],
        should=[  # Boost recent or same-session
            FieldCondition(
                key="session_id",
                match=MatchValue(value="current_session_id")
            )
        ]
    ),
    limit=15,
    score_threshold=0.65
)
```

**Hybrid Search Implementation:**
```python
# Qdrant doesn't have built-in BM25, implement custom hybrid

# 1. Sparse retrieval (BM25 via external library)
from rank_bm25 import BM25Okapi
bm25_results = bm25_search(query_text, top_k=20)

# 2. Dense retrieval (Qdrant)
vector_results = client.search(
    collection_name="conversation_memory",
    query_vector=query_embedding,
    limit=20
)

# 3. Reciprocal Rank Fusion
def reciprocal_rank_fusion(results_list, k=60):
    scores = {}
    for results in results_list:
        for rank, doc in enumerate(results):
            doc_id = doc.id
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

hybrid_results = reciprocal_rank_fusion([bm25_results, vector_results])
```

### 7.4 Memory Management

**Automatic Cleanup:**
```python
import asyncio
from datetime import datetime, timedelta

async def cleanup_old_memories(retention_days=90):
    """
    Archive or delete old low-importance memories
    """
    cutoff = datetime.now() - timedelta(days=retention_days)
    cutoff_timestamp = int(cutoff.timestamp())

    # Find old, low-importance memories
    old_memories = client.scroll(
        collection_name="conversation_memory",
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="timestamp",
                    range={"lt": cutoff_timestamp}
                ),
                FieldCondition(
                    key="importance_score",
                    range={"lt": 0.5}
                )
            ]
        ),
        limit=1000
    )

    # Option 1: Delete
    ids_to_delete = [m.id for m in old_memories[0]]
    client.delete(
        collection_name="conversation_memory",
        points_selector=ids_to_delete
    )

    # Option 2: Archive to cheaper storage
    # archive_to_s3(old_memories)
```

**Capacity Planning:**
```python
# Estimate storage needs
estimates = {
    "avg_turn_size": 400,        # tokens
    "turns_per_session": 20,
    "sessions_per_user_month": 10,
    "users": 1000,
    "retention_months": 6,
}

total_turns = (
    estimates["users"] *
    estimates["sessions_per_user_month"] *
    estimates["retention_months"] *
    estimates["turns_per_session"]
)  # 1.2M turns

# Qdrant storage per point
storage_per_point = (
    768 * 4 +      # Vector: 768 float32 = 3KB
    2000           # Payload: ~2KB average
)  # ~5KB per point

total_storage_gb = (total_turns * storage_per_point) / (1024**3)
# ~5.7 GB

# With summaries and facts (2x multiplier)
total_with_summaries = total_storage_gb * 2  # ~11.4 GB
```

---

## 8. Implementation Checklist

### Phase 1: Basic Storage (Week 1)
- [ ] Set up Qdrant collection with 768-dim vectors
- [ ] Configure Jina embeddings API
- [ ] Implement basic turn storage (user + assistant separate)
- [ ] Add essential payload fields (user_id, session_id, timestamp, role)
- [ ] Create payload indexes on filtered fields
- [ ] Test basic semantic search

### Phase 2: Chunking & Summarization (Week 2)
- [ ] Implement token counting
- [ ] Add chunking logic (300-500 token chunks with overlap)
- [ ] Build session summarization (end-of-session)
- [ ] Store summaries as separate vector points
- [ ] Test late chunking with Jina API

### Phase 3: Retrieval & Context (Week 3)
- [ ] Implement hybrid scoring (relevance + recency + type)
- [ ] Build context reconstruction with token budget
- [ ] Add diversity filtering (max N from same session)
- [ ] Implement sliding window for recent context
- [ ] Test retrieval quality on sample conversations

### Phase 4: Deduplication (Week 4)
- [ ] Add content hashing (SHA-256)
- [ ] Implement semantic similarity check
- [ ] Build merge logic for near-duplicates
- [ ] Test deduplication with repeated questions
- [ ] Monitor deduplication rate

### Phase 5: Production Hardening (Week 5-6)
- [ ] Add background summarization worker
- [ ] Implement memory cleanup/archival
- [ ] Build monitoring dashboard (memory usage, retrieval latency)
- [ ] Load testing with concurrent users
- [ ] Add error handling and retry logic
- [ ] Document API and maintenance procedures

### Phase 6: Advanced Features (Week 7+)
- [ ] Implement adaptive focus memory (AFM)
- [ ] Add entity extraction and linking
- [ ] Build topic detection for semantic chunking
- [ ] Implement cross-encoder reranking
- [ ] Add A/B testing framework for retrieval strategies

---

## 9. Key Metrics to Track

### Storage Metrics
- **Total vector points:** Track growth rate
- **Storage size:** Monitor disk usage (target: <20GB for 1000 users)
- **Average payload size:** Should stay <5KB per point
- **Deduplication rate:** Target: 10-20% of conversations

### Retrieval Metrics
- **Search latency (p50, p95, p99):** Target <100ms for vector search
- **Retrieval recall@10:** Aim for >80% relevance
- **Context token usage:** Monitor average tokens per query
- **Cache hit rate:** If using semantic caching

### Quality Metrics
- **User satisfaction:** Explicit feedback on retrieved context
- **Context usefulness:** % of conversations where past memory was relevant
- **Hallucination rate:** Does retrieval reduce fabricated responses?
- **Answer consistency:** Do similar questions get similar answers?

### Operational Metrics
- **Summarization lag:** Time between conversation end and summary creation
- **Embedding API latency:** Jina API response times
- **Failed embeddings:** Error rate from embedding service
- **Memory cleanup jobs:** Track archived/deleted memory rate

---

## 10. Common Pitfalls & Solutions

### Pitfall 1: Token Limit Exceeded
**Problem:** Messages exceed 8192-token Jina limit
**Solution:** Pre-chunk before embedding, or use hierarchical processing

### Pitfall 2: Slow Retrieval
**Problem:** Search takes >500ms
**Solution:**
- Add payload indexes on filter fields
- Reduce top-k value
- Use approximate search (HNSW ef parameter tuning)
- Consider caching frequent queries

### Pitfall 3: Low Retrieval Relevance
**Problem:** Retrieved memories aren't useful
**Solution:**
- Lower score threshold (try 0.65 instead of 0.7)
- Implement hybrid search (vector + keyword)
- Add reranking step with cross-encoder
- Improve query embedding (add context to query)

### Pitfall 4: Memory Explosion
**Problem:** Storage grows too fast
**Solution:**
- Aggressive deduplication (0.90 threshold)
- Implement retention policy (archive after 90 days)
- Summarize old conversations more aggressively
- Use payload compression (gzip in application layer)

### Pitfall 5: Cross-User Contamination
**Problem:** User A sees User B's memories
**Solution:**
- Always filter by user_id in searches
- Use namespacing in LangMem approach
- Consider separate collections per user for strict isolation
- Add integration tests for multi-tenancy

### Pitfall 6: Lost Context
**Problem:** Truncation loses critical information
**Solution:**
- Never truncate user instructions
- Use intelligent summarization instead
- Keep references to full content (file paths, message IDs)
- Store important snippets separately

### Pitfall 7: Embedding Drift
**Problem:** Old embeddings incompatible with new model
**Solution:**
- Version your embedding model in metadata
- Plan for re-embedding migration
- Keep original text for re-processing
- Use model-agnostic normalization

---

## 11. Future-Proofing (2026-2027)

### Emerging Trends

**1. Multi-Modal Memory (2027)**
- Store images, code snippets, diagrams alongside text
- Multi-modal embeddings (CLIP, ImageBind)
- Qdrant supports multi-vector per point (named vectors)

**2. Persistent Memory Standards (2027)**
- Industry moving toward standardized memory formats
- Interoperability between Mem0, LangMem, MemGPT
- Expect OpenAI/Anthropic to release native memory APIs

**3. Agentic Memory Management**
- Agents self-manage memory importance
- Automatic archival decisions
- User-specific memory retention policies

**4. Graph-Enhanced Vector Search**
- Combining knowledge graphs with vector search
- Neo4j + Qdrant integrations
- Entity-relationship aware retrieval

**5. Federated Memory**
- Cross-organization memory sharing (privacy-preserving)
- Personal memory clouds
- Blockchain-based memory provenance

### Preparing Your System

```python
# Build with flexibility for future enhancements
future_ready_schema = {
    "vector": [...],
    "payload": {
        # Current fields
        "content": "...",
        "role": "...",

        # Versioning for migrations
        "schema_version": "1.0",
        "embedding_model": "jina-v3-768",
        "embedding_date": "2026-02-06",

        # Multi-modal ready
        "content_type": "text",  # Future: "image", "code", "audio"
        "attachments": [],       # Future: references to multi-modal content

        # Graph connections ready
        "entity_ids": [],        # Future: link to knowledge graph
        "relationship_types": [],

        # Privacy and governance
        "privacy_level": "user_private",
        "retention_policy": "90_days",
        "user_consent": True
    }
}
```

---

## 12. Recommended Architecture for Your System

Based on your Qdrant + Jina (768-dim, 8K context) stack:

```
┌─────────────────────────────────────────────────────────────┐
│                     Conversation Layer                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │   User   │→→│  Agent   │→→│  Tools   │→→│   Memory    │ │
│  │  Message │  │ Response │  │   Used   │  │  Manager    │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Processing Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  Chunking    │  │  Embedding   │  │  Deduplication     │ │
│  │  (300-500t)  │→→│  (Jina API)  │→→│  (similarity>0.92) │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
│                                               ↓               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  Summary     │  │  Entity      │  │  Metadata          │ │
│  │  Generation  │  │  Extraction  │  │  Enrichment        │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 Storage Layer (Qdrant)                       │
│                                                              │
│  Collection: conversation_memory                            │
│  ├─ Vectors: 768-dim, Cosine similarity                     │
│  ├─ Indexed Payloads: user_id, session_id, timestamp       │
│  └─ Storage: Hybrid (vectors in RAM, payloads auto)         │
│                                                              │
│  Points:                                                     │
│  ├─ conversation_turns (role: user|assistant)               │
│  ├─ session_summaries (content_type: summary)               │
│  └─ entity_facts (content_type: fact)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Retrieval Layer                           │
│                                                              │
│  1. Query → Jina Embedding                                   │
│  2. Hybrid Search:                                           │
│     ├─ Qdrant vector search (top-20)                        │
│     └─ BM25 keyword search (top-20)                          │
│  3. Reciprocal Rank Fusion                                   │
│  4. Hybrid Scoring (relevance + recency + type)              │
│  5. Diversity Filter (max 3 from same session)              │
│  6. Token Budget Allocation (max 8K for context)            │
│  7. Return top-10 memories                                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Context Construction                       │
│                                                              │
│  Context Budget: 8,000 tokens                                │
│  ├─ Session summary: 500 tokens                             │
│  ├─ Recent turns (last 5): 2,000 tokens                     │
│  ├─ Retrieved memories (top-10): 4,500 tokens               │
│  └─ Entity facts: 1,000 tokens                              │
│                                                              │
│  → Inject into agent prompt                                  │
└─────────────────────────────────────────────────────────────┘
```

**Key Implementation Points:**
1. **Single Qdrant collection** with payload filtering for multi-tenancy
2. **Separate storage** for user/assistant messages (role field)
3. **300-500 token chunks** with 10-20% overlap for long messages
4. **Late chunking** for messages >2000 tokens using Jina's 8K context
5. **Session summaries** created every 10-15 turns, stored as separate points
6. **Deduplication** at 0.92 similarity threshold for semantic duplicates
7. **Hybrid retrieval** with vector + keyword, fused with RRF
8. **8K token context budget** with priority: recent > relevant > summaries
9. **Background workers** for summarization, entity extraction, cleanup
10. **Retention policy** of 90 days with importance-based archival

---

## 13. Sources & References

### Core Research Papers & Technical Documentation

1. **Qdrant Documentation**
   - [Storage Best Practices](https://qdrant.tech/documentation/concepts/storage/)
   - [Capacity Planning Guide](https://qdrant.tech/documentation/guides/capacity-planning/)
   - [Payload Management](https://qdrant.tech/documentation/concepts/payload/)
   - [Vector Search Filtering](https://qdrant.tech/articles/vector-search-filtering/)

2. **Jina AI Embeddings**
   - [Jina Embeddings Documentation](https://qdrant.tech/documentation/embeddings/jina-embeddings/)
   - [Late Chunking Paper](https://github.com/jina-ai/late-chunking)
   - [Jina Embeddings v2 Announcement](https://jina.ai/news/jina-embeddings-2-the-best-solution-for-embedding-long-documents/)
   - [Late Chunking in Long-Context Models](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)

3. **Production RAG Systems (2026)**
   - [Building Production RAG Systems in 2026: Complete Architecture Guide](https://brlikhon.engineer/blog/building-production-rag-systems-in-2026-complete-architecture-guide)
   - [RAG at Scale: Production AI Systems](https://redis.io/blog/rag-at-scale/)
   - [Contextual RAG: Maintaining Conversation Context](https://articles.chatnexus.io/knowledge-base/contextual-rag-maintaining-conversation-context-in-retrieval/)

4. **Memory-Augmented LLM Systems**
   - [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)
   - [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560)
   - [Letta (MemGPT) Documentation](https://docs.letta.com/concepts/memgpt/)
   - [LangMem SDK Announcement](https://blog.langchain.com/langmem-sdk-launch/)
   - [LangMem Documentation](https://langchain-ai.github.io/langmem/)

5. **Context Window Management**
   - [Context Window Management: Strategies for Long-Context AI Agents](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/)
   - [Context Window Overflow in 2026](https://redis.io/blog/context-window-overflow/)
   - [Managing Token Budgets for Complex Prompts](https://apxml.com/courses/getting-started-with-llm-toolkit/chapter-3-context-and-token-management/managing-token-budgets)

6. **Chunking Strategies**
   - [Optimal Chunk Size for RAG Applications](https://milvus.io/ai-quick-reference/what-is-the-optimal-chunk-size-for-rag-applications)
   - [Chunking for RAG: Best Practices](https://unstructured.io/blog/chunking-for-rag-best-practices)
   - [Chunking in RAG: The Optimization Nobody Talks About](https://medium.com/@nikhil.dharmaram/chunking-in-rag-the-rag-optimization-nobody-talks-about-86609f43d46f)

7. **Semantic Deduplication**
   - [NVIDIA NeMo Semantic Deduplication](https://docs.nvidia.com/nemo/curator/latest/curate-text/process-data/deduplication/semdedup.html)
   - [SemHash: Fast Multimodal Semantic Deduplication](https://github.com/MinishLab/semhash)
   - [Semantic Caching and Memory Patterns](https://www.dataquest.io/blog/semantic-caching-and-memory-patterns-for-vector-databases/)

8. **Hybrid Search & Reranking**
   - [Optimizing RAG with Hybrid Search & Reranking](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking)
   - [Beyond Basic RAG: Query-Aware Hybrid Retrieval Systems](https://ragaboutit.com/beyond-basic-rag-building-query-aware-hybrid-retrieval-systems-that-scale/)

9. **Session Summarization & Memory**
   - [How Does LLM Memory Work: Context-Aware AI Applications](https://www.datacamp.com/blog/how-does-llm-memory-work)
   - [LLM Chat History Summarization Guide](https://mem0.ai/blog/llm-chat-history-summarization-guide-2025)
   - [Context Engineering: The Missing Layer in RAG](https://robotsandpencils.com/context-engineering-rag-policy-compliance/)

10. **Benchmarks & Evaluation**
    - [Benchmarking AI Agent Memory: Is a Filesystem All You Need?](https://www.letta.com/blog/benchmarking-ai-agent-memory)
    - [Mem0 Research: 26% Accuracy Boost for LLMs](https://mem0.ai/research)
    - [Evaluating Very Long-Term Conversational Memory (LOCOMO)](https://snap-research.github.io/locomo/)

11. **Advanced Memory Techniques**
    - [Adaptive Focus Memory for Language Models](https://arxiv.org/html/2511.12712)
    - [Amazon Bedrock AgentCore Episodic Memory](https://aws.amazon.com/blogs/machine-learning/build-agents-to-learn-from-experiences-using-amazon-bedrock-agentcore-episodic-memory/)
    - [AWS AgentCore Long-Term Memory Deep Dive](https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/)

12. **2026 Industry Trends**
    - [The Death of Sessionless AI: Memory Evolution 2026-2030](https://medium.com/@aniruddhyak/the-death-of-sessionless-ai-how-conversation-memory-will-evolve-from-2026-2030-9afb9943bbb5)
    - [AI Memory vs. Context Understanding: Next Frontier](https://www.sphereinc.com/blogs/ai-memory-and-context/)
    - [From RAG to Context: 2025 Year-End Review](https://www.ragflow.io/blog/rag-review-2025-from-rag-to-context)

---

## Appendix A: Quick Reference Card

```
┌────────────────────────────────────────────────────────────┐
│              CONVERSATION MEMORY QUICK REFERENCE            │
├────────────────────────────────────────────────────────────┤
│ STORAGE                                                     │
│ • Granularity: 300-500 tokens per point                    │
│ • User/Assistant: Separate (role field)                    │
│ • Max tokens: 8192 (Jina limit)                            │
│ • Chunking: 10-20% overlap                                 │
├────────────────────────────────────────────────────────────┤
│ SUMMARIES                                                   │
│ • Create: Every 10-15 turns                                │
│ • Size: 500-1000 tokens                                    │
│ • Metadata: tools_used, files_modified, decisions          │
│ • Storage: Separate vector points                          │
├────────────────────────────────────────────────────────────┤
│ RETRIEVAL                                                   │
│ • Hybrid: Vector (45%) + Recency (25%) + Type (15%)        │
│ • Top-k: 15-20 results                                     │
│ • Diversity: Max 3 from same session                       │
│ • Context budget: 8,000 tokens                             │
├────────────────────────────────────────────────────────────┤
│ DEDUPLICATION                                               │
│ • Threshold: 0.92 cosine similarity                        │
│ • Hash: SHA-256 for exact duplicates                       │
│ • Merge: Same role + session + <24h gap                    │
├────────────────────────────────────────────────────────────┤
│ SIZE LIMITS                                                 │
│ • <300 tokens: Store whole                                 │
│ • 300-800: Store or summarize                              │
│ • 800-2000: Chunk by topic                                 │
│ • 2000-8192: Late chunking                                 │
│ • >8192: Hierarchical chunking                             │
├────────────────────────────────────────────────────────────┤
│ QDRANT CONFIG                                               │
│ • Collection: Single, multi-tenant                         │
│ • Indexes: user_id, session_id, timestamp, topics          │
│ • Distance: Cosine                                         │
│ • Vectors: RAM, Payloads: Auto                             │
└────────────────────────────────────────────────────────────┘
```

---

**Document End**

*This best practices document synthesizes research from 50+ sources including production systems (Mem0, MemGPT/Letta, LangMem), academic papers, vector database documentation, and 2026 industry benchmarks. All recommendations are grounded in empirical evidence and production deployments.*

*Last Updated: 2026-02-06*
