# AI Memory Module - Roadmap

This roadmap outlines the development direction for AI Memory Module. Community feedback and contributions help shape these priorities.

---

## Current Release: v2.0.2 (Released 2026-02-03)

**V2.0 Architecture** - Complete memory system redesign with specialized collections, automatic triggers, and intelligent context injection.

### Architecture Overview

**Three-Collection Memory System** (V2.7 Architecture Spec):

| Collection | Purpose | Example Types |
|------------|---------|---------------|
| **code-patterns** | HOW things are built | implementation, error_fix, refactor, file_pattern |
| **conventions** | WHAT rules to follow | rule, guideline, port, naming, structure |
| **discussions** | WHY things were decided | decision, session, preference, user_message, agent_response |

**Best Practices Applied**:
- **BP-038** (Qdrant Best Practices 2026): HNSW configuration, payload indexing, 8-bit scalar quantization
- **BP-039** (RAG Best Practices): Intent detection, token budgets, context injection
- **BP-040** (Event-Driven Architecture): Hook classification, graceful degradation

### V2.0.x Features

- **15 Memory Types** for precise categorization
- **6 Automatic Triggers** (signal-driven retrieval):
  1. **Error Detection** - Retrieves past error fixes when commands fail
  2. **New File Creation** - Retrieves naming conventions and structure patterns
  3. **First Edit to File** - Retrieves file-specific patterns on first modification
  4. **Decision Keywords** - "why did we..." triggers decision memory retrieval
  5. **Best Practices Keywords** - "how should I..." triggers convention retrieval
  6. **Session History Keywords** - "what have we done..." triggers session summaries
- **Intent Detection** - Routes queries to appropriate collections automatically
- **Rich Session Summaries** - PreCompact stores full conversation context for resume
- **Knowledge Discovery**:
  - `best-practices-researcher` skill - Web research with local Qdrant caching
  - `skill-creator` agent - Generates Claude Code skills from research
  - `search-memory` skill - Semantic search across collections
- **Backup & Restore** - `backup_qdrant.py` and `restore_qdrant.py` scripts
- **Graceful Degradation** - Claude works even when services are temporarily unavailable
- **Multi-Project Isolation** - `group_id` filtering keeps projects separate

### V2.0.2 Fixes
- Installer now runs `pip install` for Python dependencies (BUG-054)
- SessionStart hook timeout parameter cast to int (BUG-051)
- store_async.py handles missing session_id gracefully (BUG-058)

---

## Planned - v2.0.3: Quality & Performance (In Progress)

**Theme:** Technical debt resolution and performance optimization

### Performance
- [ ] **TECH-DEBT-104**: Add `content_hash` payload index for O(1) deduplication
- [ ] **TECH-DEBT-117**: Add retrieval latency NFR (<500ms)
- [ ] **TECH-DEBT-118**: Clarify embedding latency NFR (batch vs real-time)

### Documentation
- [x] **TECH-DEBT-109**: ROADMAP.md rewrite for V2.0+ architecture
- [x] **TECH-DEBT-108**: Update trigger count from 5 to 6 in README (verified in v2.0.3)

### Configuration
- [x] **TECH-DEBT-116**: Increase token budget from 2000 to 4000 per BP-039 Section 3

**Target Release:** February 2026

---

## Planned - v2.1: Resilience & Quality (Q1 2026)

**Theme:** Circuit breaker implementation and code quality improvements

### Resilience
- [ ] **TECH-DEBT-081**: Circuit Breaker Pattern Implementation
  - failure_threshold=5, reset_timeout=30s, half-open state per BP-040 Section 6
- [ ] **TECH-DEBT-080**: Service Down Graceful Degradation Testing
  - Verify Qdrant unavailability handling and queue fallback
- [ ] **TECH-DEBT-078**: Automatic Queue Processor
  - Background thread in classifier-worker container

### Code Quality
- [ ] **TECH-DEBT-102**: Migrate to asyncio.TaskGroup (Python 3.11+)
  - 11 places using legacy asyncio.create_task()
- [ ] **TECH-DEBT-111**: Strongly-typed hook event classes
  - Add CaptureEvent, RetrievalEvent dataclasses per BP-040 Section 1
- [ ] **TECH-DEBT-113**: Keyword pattern collision detection
  - 63 patterns in triggers.py need maintenance workflow
- [ ] **TECH-DEBT-115**: Context injection delimiter spec
  - Add `<retrieved_context>` format for source attribution per BP-039 Section 1

### Data Quality
- [ ] **TECH-DEBT-059**: Backfill embeddings script
  - 762 records pending migration
- [ ] **TECH-DEBT-048**: Filter low-value agent responses
- [ ] **TECH-DEBT-049**: Deduplicate similar user messages
- [ ] **TECH-DEBT-050**: Smart truncation for context injection

**Target Release:** March 2026

---

## Planned - v2.2: Search Intelligence (Q2 2026)

**Theme:** Hybrid search and advanced retrieval

### Search Improvements
- [ ] **TECH-DEBT-058**: Hybrid Search (BM25 + Dense Vectors)
  - +15-25% accuracy improvement per BP-039 Section 5
  - Reciprocal Rank Fusion (RRF) for result combination
- [ ] **TECH-DEBT-003**: Embedding Migration Phases 2-3
  - SPLADE sparse vectors for keyword matching
  - ColBERT reranking (+15-20% accuracy per BP-039 Section 5)
- [ ] **TECH-DEBT-055**: Late chunking for long documents
  - +24% accuracy for documents >2000 tokens

### Architecture
- [ ] **TECH-DEBT-114**: Entity memory tier
  - Hierarchical memory for cross-session entity knowledge per BP-039 Section 4
- [ ] **TECH-DEBT-110**: Event sourcing / audit trail
  - Append-only event log with hash-chain verification per BP-040 Section 7
- [ ] **TECH-DEBT-112**: Multi-agent lifecycle events
  - MultiAgentInitializedEvent, BeforeMultiAgentInvocationEvent per BP-040 Section 1

### Performance
- [ ] **TECH-DEBT-106**: HNSW inline_storage (Qdrant 1.16+)
  - Disk optimization with inline_storage=True
- [ ] **TECH-DEBT-107**: gRPC client for higher throughput
  - prefer_grpc=True for Qdrant connections
- [ ] **TECH-DEBT-060**: Cross-collection deduplication

### Code Quality
- [ ] **TECH-DEBT-105**: Add type hints for mypy strict mode
- [ ] **TECH-DEBT-001**: Python 3.12+ optimizations

**Target Release:** June 2026

---

## Planned - v3.0: Enterprise & Extensibility (Q3-Q4 2026)

**Theme:** CI/CD enhancements and enterprise features

### CI/CD (TECH-DEBT-096)
- [ ] Automated documentation deployment
- [ ] PyPI Trusted Publishing
- [ ] AI workflow enhancements
- [ ] Artifact attestation

### Enterprise Features
- [ ] Team collaboration with shared memory pools
- [ ] Access control and permissions
- [ ] Memory review and approval workflows
- [ ] SSO integration (SAML 2.0, OAuth 2.0 / OIDC)
- [ ] Role-based access control (RBAC)

### Architecture
- [ ] Plugin system for custom extractors
- [ ] Distributed deployment support (multi-node Qdrant)
- [ ] Alternative vector DB support (Milvus, Weaviate adapters)

**Target Release:** To be determined based on community demand

---

## Best Practices Foundation

This system is built on verified best practices research:

| BP-ID | Topic | Applied |
|-------|-------|---------|
| **BP-038** | Qdrant Best Practices 2026 | Collection design, HNSW config, payload indexing, quantization |
| **BP-039** | RAG Best Practices | Intent detection, token budgets, context injection, hybrid search planning |
| **BP-040** | Event-Driven Architecture | Hook classification, graceful degradation, circuit breaker planning |
| **BP-037** | Multi-Tenancy Patterns | group_id isolation, is_tenant config, mandatory tenant filter |

---

## Community Requests

Features requested by the community are tracked here. Submit requests via [GitHub Issues](https://github.com/Hidden-History/ai-memory/issues/new?template=feature_request.yml).

### Under Consideration
_Submit a feature request to be the first!_

### Recently Implemented
- **V2.0 Three-Collection Architecture** - Community feedback on memory organization
- **Session History Trigger** - Requested continuity for "where were we" questions
- **Backup/Restore Scripts** - Production deployment requirements

---

## How to Contribute

### Submit Feature Requests
Use our [Feature Request template](https://github.com/Hidden-History/ai-memory/issues/new?template=feature_request.yml).

### Vote on Existing Proposals
React with a thumbs-up on issues you want prioritized.

### Contribute Code
1. Check issues labeled [`help wanted`](https://github.com/Hidden-History/ai-memory/labels/help%20wanted)
2. Read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines
3. Submit a PR linked to the relevant issue

### Join Discussions
Participate in [GitHub Discussions](https://github.com/Hidden-History/ai-memory/discussions).

---

## Roadmap Principles

1. **User Value First** - Features must solve real user problems
2. **Stability Over Features** - Performance and reliability come before new capabilities
3. **Community-Driven** - Your feedback shapes priorities
4. **Incremental Delivery** - Small, frequent releases over big-bang updates
5. **Backward Compatibility** - Breaking changes only in major versions (x.0.0)
6. **Best Practices Foundation** - All features verified against current research (BP-xxx)

---

**Last Updated:** 2026-02-03
**Architecture Version:** V2.7
**Maintainer:** [@Hidden-History](https://github.com/Hidden-History)

_This roadmap is a living document and evolves based on community feedback and project needs._
