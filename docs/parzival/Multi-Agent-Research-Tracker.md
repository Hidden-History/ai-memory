# Multi-Agent System Research Tracker

**Purpose**: Track all research needed for BMAD Multi-Agent Architecture implementation
**Created**: 2026-01-21
**Status**: Research Phase (gather all findings before implementation decisions)

---

## Research Strategy

**Phase 1**: Research ALL topics below → Document findings
**Phase 2**: Review all findings together → Identify conflicts/synergies
**Phase 3**: Make informed architectural decisions → Create implementation plan

---

## Research Status Overview

| BP-ID | Topic | Status | Confidence | Priority |
|-------|-------|--------|------------|----------|
| BP-008 | React Multi-Terminal UI | ✅ COMPLETE | Verified | Critical |
| BP-009 | PostgreSQL Agent Schema | ✅ COMPLETE | Informed | Critical |
| BP-010 | FastAPI WebSocket Patterns | ✅ COMPLETE | Verified | Critical |
| BP-011 | Human-in-the-Loop Approvals | ✅ COMPLETE | Verified | High |
| BP-012 | Claude SDK Subagent Lifecycle | ✅ COMPLETE | Verified | Critical |
| BP-013 | LLM Cost Tracking | ✅ COMPLETE | Informed | High |
| BP-014 | Intelligent Document Chunking | ✅ COMPLETE | Verified | Critical |
| BP-015 | RAG Collection Management | ✅ COMPLETE | Informed | Critical |
| BP-016 | Advanced Chunking Optimization | ✅ COMPLETE | Verified | High |
| BP-017 | Advanced Collection Management | ✅ COMPLETE | Verified | High |
| BP-022 | Memory Context Injection | ✅ COMPLETE | Verified | Critical |
| BP-023 | Agent Error Recovery | ✅ COMPLETE | Verified | High |
| BP-024 | PostgreSQL vs Redis Messaging | ✅ COMPLETE | Verified | **BLOCKING** |
| BP-025 | GDPR Privacy Audit Trails | ✅ COMPLETE | Verified | **BLOCKING** |
| BP-026 | Hook Reliability Patterns | ✅ COMPLETE | Verified | **BLOCKING** |
| BP-027 | Multi-Agent State Persistence | ✅ COMPLETE | Verified | **BLOCKING** |

**Research Sprint Complete**: All BLOCKING questions resolved (BP-024 through BP-027)

---

## Completed Research (BP-008 through BP-013)

### Infrastructure Foundation

#### BP-008: React Multi-Terminal UI Architecture
**Question**: How to build multi-terminal GUI for agent orchestration?
**Finding**: Use **react-xtermjs** (Sept 2025 by Qovery) - modern React wrapper with hooks
**Recommendation**: Build with xterm.js + @xterm/addon-fit + @xterm/addon-attach
**Why**: Only actively maintained React wrapper, used in production (Qovery CI/CD)
**Source**: [BP-008 Full Document](../../oversight/knowledge/best-practices/BP-008-react-xterm-multi-terminal-2025.md)

#### BP-009: PostgreSQL Schema for Agent Orchestration
**Question**: How to design database schema for agent communication and workflow tracking?
**Finding**: **Hybrid schema** - structured columns for filtering + JSONB for metadata
**Recommendation**: PostgreSQL 17/18 with UUIDv7, GIN indexes, partial indexes for active records
**Why**: 10-100x faster JSONB queries with GIN, 60% faster parallel execution, time-ordered IDs
**Source**: [BP-009 Full Document](../../oversight/knowledge/best-practices/BP-009-postgresql-agent-schema-2025.md)

#### BP-010: FastAPI WebSocket Patterns for Real-Time Streaming
**Question**: How to implement WebSocket server for terminal streaming?
**Finding**: **Three-layer architecture** - Transport (WebSocket) + Concurrency (ConnectionManager) + Domain (agent logic)
**Recommendation**: Use FastAPI native WebSocket + connection sharding by agent_id
**Why**: Clean separation of concerns, scales to 10k+ concurrent connections per process
**Source**: [BP-010 Full Document](../../oversight/knowledge/best-practices/BP-010-fastapi-websocket-2025.md)

### Agent Operations

#### BP-011: Human-in-the-Loop Approval Workflows
**Question**: How to implement safety gates for agent actions?
**Finding**: **Three-loop HITL pattern** - Pre-loop (constraints) + In-loop (approval) + Post-loop (review)
**Recommendation**: Use LangGraph `interrupt()` function, approval decision matrix by risk level
**Why**: EU AI Act Article 14 compliance, prevents irreversible errors, audit trail
**Source**: [BP-011 Full Document](../../oversight/knowledge/best-practices/BP-011-human-in-loop-approval-workflows-2025.md)

#### BP-012: Claude Agent SDK Subagent Lifecycle Management
**Question**: How to manage subagent spawning and context isolation?
**Finding**: **Initializer + Orchestrator + Worker pattern** - Parzival orchestrates, workers execute in isolated contexts
**Recommendation**: Define subagents in `.claude/agents/` with clear description fields for auto-delegation
**Why**: Anthropic official pattern, prevents context pollution, enables parallelization
**Source**: [BP-012 Full Document](../../oversight/knowledge/best-practices/BP-012-claude-agent-sdk-subagent-lifecycle-2025.md)

#### BP-013: LLM Cost Tracking & Token Budgeting
**Question**: How to track and control costs for multi-agent systems?
**Finding**: **AI gateway pattern** - single pane of glass, tool-call budgets > token budgets
**Recommendation**: Hierarchical budgets (Org → Team → Agent → Session), real-time enforcement
**Why**: Tool-call budgets more relevant for agents, prevents runaway costs, LangSmith/Langfuse integration
**Source**: [BP-013 Full Document](../../oversight/knowledge/best-practices/BP-013-llm-cost-tracking-token-budgeting-2025.md)

---

## Memory Module Research (BP-014 through BP-017)

### Completed Research

#### BP-014: Intelligent Document Chunking for RAG Systems
**Question**: How to chunk markdown and code files for optimal RAG retrieval?
**Finding**: **Semantic chunking with tree-sitter AST parsing** - language-aware boundaries preserve code context
**Recommendation**: 512-1024 tokens per chunk, 10-15% overlap, metadata-rich payloads with file path + section headers
**Why**: Tree-sitter 36-52x faster than regex parsers, semantic boundaries prevent context loss, overlap handles boundary cases
**Source**: [BP-014 Full Document](../../oversight/knowledge/best-practices/BP-014-intelligent-document-chunking-2025.md)

#### BP-015: RAG Collection Management Patterns
**Question**: How to route content to correct collections and search across them?
**Finding**: **Intent-based routing + cascading search** - classify query intent, search targeted collections first, expand if needed
**Recommendation**: Use Qdrant hybrid search (vector + keyword), RRF score fusion, collection health monitoring
**Why**: Intent classification 85-92% accurate (SetFit), cascading reduces latency vs. multi-collection broadcast, hybrid search handles exact matches + semantic similarity
**Source**: [BP-015 Full Document](../../oversight/knowledge/best-practices/BP-015-rag-collection-management-2025.md)

#### BP-016: Advanced Chunking Optimization
**Question**: How to handle large codebases and incremental updates efficiently?
**Finding**: **Tree-sitter incremental parsing + file-level change detection** - only re-chunk modified files, cache AST trees
**Recommendation**: SHA-256 content hashing for change detection, parallel chunking (8 cores), lazy embedding generation
**Why**: Incremental parsing 150-200x faster for small edits, parallel processing scales linearly, lazy embedding prevents wasted work
**Source**: [BP-016 Full Document](../../oversight/knowledge/best-practices/BP-016-advanced-chunking-optimization-2025.md)

#### BP-017: Advanced Collection Management
**Question**: When to create new collections vs. using payload filtering?
**Finding**: **Payload filtering for most cases, separate collections only for isolation** - Qdrant payload filtering 90-95% as fast as separate collections
**Recommendation**: Single collection per project with `type` field filtering, separate collections only for multi-tenant isolation
**Why**: Payload filtering simplifies operations, enables cross-type search, separate collections only add overhead unless strong isolation needed
**Source**: [BP-017 Full Document](../../oversight/knowledge/best-practices/BP-017-advanced-collection-management-2025.md)

---

## Agent Architecture & Infrastructure Research (BP-022 through BP-027)

### Completed Research

#### BP-022: Memory Context Injection Patterns
**Question**: How and when to inject memories into agent context?
**Finding**: **SessionStart:compact hook with cascading search** - inject after compaction to maximize available context, use multi-stage search (recent → relevant → broad)
**Recommendation**: 15-25% context budget for memories (~30-50K tokens for Claude), recency bias (exponential decay), confidence filtering (>0.7 threshold)
**Why**: Post-compact injection prevents wasted tokens, cascading search balances precision and recall, recency bias prioritizes fresh knowledge
**Source**: [BP-022 Full Document](../../oversight/knowledge/best-practices/BP-022-memory-context-injection-2025.md)

#### BP-023: Agent Error Recovery & Resilience
**Question**: What happens when agent crashes mid-execution?
**Finding**: **Circuit breaker + exponential backoff + DLQ pattern** - detect failures, prevent cascades, retry with backoff, dead-letter failed tasks
**Recommendation**: 5 failures → OPEN state (30s), exponential backoff with jitter (1s, 2s, 4s, 8s, 16s), DLQ after 3 retry attempts
**Why**: Circuit breaker prevents resource exhaustion, jittered backoff prevents thundering herd, DLQ preserves failed work for analysis
**Source**: [BP-023 Full Document](../../oversight/knowledge/best-practices/BP-023-agent-error-recovery-2025.md)

#### BP-024: PostgreSQL LISTEN/NOTIFY vs Redis Pub/Sub for Agent Messaging
**Question**: Should we use PostgreSQL native pub/sub instead of polling or Redis?
**Finding**: **Redis Streams recommended over PostgreSQL LISTEN/NOTIFY** - PostgreSQL has global lock causing production downtimes at scale
**Recommendation**: Redis Streams with consumer groups for Parzival, PostgreSQL for durable storage only
**Why**: Redis Streams handle millions msg/sec vs 100-500 for PostgreSQL, no global lock, built-in acknowledgment tracking, production-proven at Recall.ai (3 downtimes caused by PG LISTEN/NOTIFY)
**Relations**: Resolves BP-007-Q2 (BLOCKING), BP-009-Q2 (High Priority)
**Source**: [BP-024 Full Document](../../oversight/knowledge/best-practices/BP-024-postgresql-redis-agent-messaging-2025.md)

#### BP-025: GDPR Compliance & Privacy Audit Trails
**Question**: How to ensure GDPR compliance for memory injection and agent actions?
**Finding**: **Hash-chain audit logs + differential privacy + TEEs** - cryptographically tamper-proof logs, privacy-preserving embeddings, secure enclaves for sensitive data
**Recommendation**: AuditableLLM framework, OpenTelemetry instrumentation, 6-month log retention (EU AI Act Article 19), differential privacy ε=0.5
**Why**: EU AI Act effective Aug 2, 2026 with €35M fines, hash-chain prevents log tampering, differential privacy limits re-identification attacks, TEEs protect data in use
**Relations**: Resolves BP-022-Q5 (BLOCKING - memory injection tracking)
**Source**: [BP-025 Full Document](../../oversight/knowledge/best-practices/BP-025-gdpr-privacy-audit-trails-2025.md)

#### BP-026: Claude Code Hook Reliability Patterns
**Question**: How to ensure hooks don't fail silently?
**Finding**: **CRITICAL BUG: Hooks stop after 2.5 hours** - GitHub #16047, requires heartbeat monitoring workaround
**Recommendation**: <500ms response (fork background workers), graceful degradation (exit 0 for non-critical), circuit breaker, idempotency tracking (Redis), heartbeat monitoring every 15 minutes
**Why**: Hook timeout bug unfixed, background forking prevents blocking, graceful degradation keeps Claude working, circuit breaker prevents cascades, idempotency prevents duplicate work
**Relations**: Resolves BP-022-Q1 (BLOCKING - SessionStart reliability), BP-003-Q1 (High Priority - hook patterns)
**Source**: [BP-026 Full Document](../../oversight/knowledge/best-practices/BP-026-claude-code-hook-reliability-2025.md)

#### BP-027: Multi-Agent State Persistence & Recovery
**Question**: How to persist Parzival state for crash recovery and long-running workflows?
**Finding**: **LangGraph checkpointing + Saga pattern + Event Sourcing** - automatic state snapshots, compensating transactions, event replay
**Recommendation**: LangGraph PostgresSaver for checkpointing, SagaLLM for long transactions, hybrid Redis hot + PostgreSQL warm + S3 cold storage
**Why**: LangGraph built-in checkpointing (no custom code), Saga pattern ensures consistency across agent workflows, event sourcing enables point-in-time recovery, multi-tier storage balances cost and performance
**Relations**: Resolves BP-012-Q5 (BLOCKING - subagent crash recovery), BP-023-Q3 (High Priority - state persistence)
**Source**: [BP-027 Full Document](../../oversight/knowledge/best-practices/BP-027-agent-state-persistence-2025.md)

---

## Memory Module Research (BP-014 through BP-021) - Detailed Research Topics

### Critical Path (Blocks Implementation)

#### BP-014: Intelligent Document Chunking (2025-2026)
**Status**: 🔄 IN PROGRESS
**Question**: How to chunk markdown and code files for optimal RAG retrieval?
**Research Topics**:
- Semantic chunking vs fixed-size (markdown-aware)
- Token overlap strategies (prevent context loss at boundaries)
- Metadata preservation (file path, section headers, code context)
- Chunk size optimization for jina-embeddings-v2-base-en (768 dimensions)
- Code vs prose chunking (AST-aware for code, paragraph-aware for docs)
- Language-specific strategies (Python, TypeScript, Markdown)

**Why Critical**: All file ingestion depends on chunking strategy. Poor chunking = poor retrieval accuracy.

**Expected Deliverables**:
- Recommended chunk size (tokens/characters)
- Overlap strategy (fixed vs semantic)
- Metadata schema for chunks
- Code example: `IntelligentChunker` class

---

#### BP-015: RAG Collection Management Patterns (2025-2026)
**Status**: 🔄 IN PROGRESS
**Question**: How to route content to correct collections and search across them?
**Research Topics**:
- Collection routing logic (content type → collection mapping)
- Cross-collection search strategies (when to query multiple collections)
- Collection lifecycle management (archive, merge, split)
- Hybrid search patterns (vector + keyword combined)
- Query routing (user intent → collection selection)

**Why Critical**: Multi-collection architecture needs clear routing rules. Wrong collection = retrieval failure.

**Expected Deliverables**:
- Collection routing decision tree
- Cross-collection search patterns
- Collection health metrics
- Code example: `CollectionRouter` class

---

### High Priority (User Experience)

#### BP-016: Codebase Auto-Indexing Strategies (2025-2026)
**Status**: ⏳ NOT STARTED
**Question**: How to automatically index BMAD project files into memory?
**Research Topics**:
- File watch patterns (inotify, watchdog, fswatch)
- Incremental indexing (only changed files, not full re-index)
- AST parsing for code structure (functions, classes, imports)
- Documentation cross-referencing (README → code files)
- Git-aware indexing (respect .gitignore, track file renames)
- BMAD-specific patterns (_bmad-output/, oversight/, src/)

**Why High Priority**: Manual upload is tedious. Auto-indexing critical for developer experience.

**Expected Deliverables**:
- Watch pattern configuration
- Incremental indexing algorithm
- BMAD project scanner script
- Code example: `BMadProjectScanner` class

---

#### BP-017: Vector Database Maintenance & Hygiene (2025-2026)
**Status**: ⏳ NOT STARTED
**Question**: How to prevent Qdrant degradation over time?
**Research Topics**:
- Deduplication strategies (beyond hash-based: semantic similarity)
- Stale memory detection (last accessed, relevance decay)
- Collection compaction and optimization (Qdrant-specific)
- Embedding drift detection (when to re-embed old content)
- Orphaned point cleanup (embeddings without source files)
- Performance monitoring (query latency, storage growth)

**Why High Priority**: Without maintenance, memory becomes polluted and slow.

**Expected Deliverables**:
- Maintenance schedule (daily, weekly, monthly tasks)
- Deduplication threshold recommendations
- Archival policy (when to delete vs archive)
- Code example: `db_maintenance.py` script

---

### Medium Priority (Accuracy & Security)

#### BP-018: Hybrid Search Patterns (Vector + Keyword) (2025-2026)
**Status**: ⏳ NOT STARTED
**Question**: How to combine vector and keyword search for better accuracy?
**Research Topics**:
- Qdrant hybrid search implementation
- Keyword boosting strategies (exact match priority)
- Score fusion methods (RRF, weighted average)
- Use cases (file names, error codes, function names → keyword)
- Performance impact (hybrid vs pure vector)

**Why Medium Priority**: Improves accuracy but pure vector is acceptable baseline.

**Expected Deliverables**:
- Hybrid search configuration
- Boosting factor recommendations
- Use case decision tree (when to use hybrid)
- Code example: `HybridSearchEngine` class

---

#### BP-020: Memory Provenance Tracking (2025-2026)
**Status**: ⏳ NOT STARTED
**Question**: How to trace memory lineage (source file → chunks → edits)?
**Research Topics**:
- Lineage graph structure (parent-child relationships)
- Provenance metadata (who created, when, why, from where)
- Chunk versioning (track edits to original content)
- Debugging workflows (find all chunks from file X)
- Visualization (provenance graph UI)

**Why Medium Priority**: Helpful for debugging but not blocking core functionality.

**Expected Deliverables**:
- Provenance schema (PostgreSQL or Qdrant payload)
- Lineage query patterns
- Debugging procedures
- Code example: `ProvenanceTracker` class

---

#### BP-021: Privacy-Aware Memory Filtering (2025-2026)
**Status**: ⏳ NOT STARTED
**Question**: How to prevent secrets/PII from being stored?
**Research Topics**:
- PII detection (regex patterns, ML models)
- Secret scanning (API keys, passwords, tokens)
- Pre-storage filtering (scan before embedding)
- Redaction strategies (mask vs reject)
- Compliance requirements (GDPR, SOC 2)

**Why Medium Priority**: Important for production use but dev environments less critical.

**Expected Deliverables**:
- PII/secret detection patterns
- Filtering policy (what to block vs redact)
- Compliance checklist
- Code example: `PrivacyFilter` class

---

### Low Priority (Future Enhancement)

#### BP-019: Embedding Model Versioning & Migration (2025-2026)
**Status**: ⏳ NOT STARTED
**Question**: How to handle embedding model upgrades?
**Research Topics**:
- Re-embedding strategies (full vs incremental)
- Backward compatibility (old embeddings still searchable)
- Model performance comparison (accuracy before/after)
- Migration tooling (batch re-embed, zero-downtime)
- Cost estimation (re-embedding entire corpus)

**Why Low Priority**: Current model stable, migration is future concern.

**Expected Deliverables**:
- Migration procedure
- Downtime estimation
- Cost analysis
- Code example: `EmbeddingMigrator` class

---

#### BP-025: Agent Consensus Patterns (2025-2026)
**Status**: ⏳ NOT STARTED
**Question**: How to handle disagreement between multiple agents?
**Research Topics**:
- Voting mechanisms (majority, weighted, quorum)
- Confidence-based resolution (highest confidence wins)
- Human escalation triggers (when agents can't agree)
- Consensus protocols (Raft, Paxos adapted for AI)
- Use cases (code review, architecture decisions)

**Why Low Priority**: Single Parzival orchestrator reduces need for consensus.

**Expected Deliverables**:
- Consensus algorithm selection
- Escalation policy
- Use case mapping
- Code example: `ConsensusResolver` class

---

## Additional Research Recommendations

### Recommended Additions

1. **BP-026: Agent Observability & Debugging (2025-2026)**
   - Distributed tracing (agent call chains)
   - Logging aggregation (ELK, Grafana Loki)
   - Performance profiling (agent execution time)
   - Debug replay (re-run agent with same inputs)

2. **BP-027: Agent Testing Strategies (2025-2026)**
   - Unit testing agents (mock LLM responses)
   - Integration testing (multi-agent workflows)
   - Regression testing (detect behavior changes)
   - Load testing (concurrent agent execution)

3. **BP-028: Agent Configuration Management (2025-2026)**
   - Environment-based configs (dev, staging, prod)
   - Feature flags (enable/disable agent capabilities)
   - Dynamic reloading (update config without restart)
   - Configuration validation (detect misconfigurations)

4. **BP-029: React Frontend State Management (2025-2026)**
   - State library selection (Redux, Zustand, Jotai)
   - WebSocket state synchronization
   - Optimistic updates (instant UI feedback)
   - Offline support (queue actions when disconnected)

5. **BP-030: API Design for Memory Upload Frontend (2025-2026)**
   - RESTful vs GraphQL (which for file upload + metadata)
   - Batch upload endpoints
   - Progress tracking (upload status)
   - Validation and error responses

---

## Research Methodology

### For Each Best Practice:

1. **Web Research** (2024-2026 sources prioritized)
   - Official documentation
   - Industry best practices
   - Production case studies
   - GitHub examples (active projects)

2. **Synthesis**
   - Summarize key findings
   - Compare alternatives
   - Assess applicability to BMAD project

3. **Documentation**
   - Create `BP-XXX-[topic]-2025.md` file
   - Store summary in Qdrant `conventions` collection
   - Update this tracker with findings

4. **Recommendation**
   - State clear recommendation with rationale
   - Confidence level (Verified, Informed, Inferred)
   - Implementation checklist

---

## Review Phase (After All Research Complete)

### Cross-Cutting Analysis

Once all BP-014 through BP-030 are researched:

1. **Identify Conflicts**
   - Do any recommendations contradict each other?
   - Are there competing patterns for same problem?

2. **Find Synergies**
   - Which components naturally work together?
   - Can we combine multiple patterns?

3. **Prioritize Implementation**
   - Critical path dependencies
   - Quick wins vs long-term investments

4. **Create Master Plan**
   - Phase 1: Foundation (chunking, collection routing, context injection)
   - Phase 2: User Experience (auto-indexing, upload UI)
   - Phase 3: Operations (maintenance, monitoring, cost tracking)
   - Phase 4: Advanced (consensus, multi-tenant, model versioning)

---

## Success Metrics

**Research Phase Complete When**:
- ✅ All BP-014 through BP-030 have status: COMPLETE
- ✅ All findings documented in `oversight/knowledge/best-practices/`
- ✅ All summaries stored in Qdrant `conventions` collection
- ✅ This tracker updated with findings and recommendations
- ✅ Confidence levels assigned (Verified/Informed/Inferred)

**Review Phase Complete When**:
- ✅ Conflicts identified and resolved
- ✅ Synergies documented
- ✅ Implementation plan created with phases
- ✅ Resource estimation done (time, cost, complexity)

---

## Notes

- **Research First, Decide Later**: No implementation decisions until all research gathered
- **Document Everything**: Each finding tracked in markdown + Qdrant
- **Confidence Matters**: Distinguish verified (official docs) from inferred (best guess)
- **Applicability Check**: Always assess "does this work for BMAD project?"

---

**Last Updated**: 2026-01-21
**Next Review**: After BP-030 research complete
**Total Research Topics**: 17 (BP-014 through BP-030)
