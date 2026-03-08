# AI Memory Module - Roadmap

This roadmap outlines the development direction for AI Memory Module. Community feedback and contributions help shape these priorities.

---

## Current Release: v2.2.1 (Released 2026-03-08)

**Triple Fusion Hybrid Search** - Dense + BM25 sparse + ColBERT late interaction via Qdrant RRF fusion, with RRF score normalization and 4-path search composition.

### Architecture Overview

**Five-Collection Memory System** (V3.4 Architecture Spec):

| Collection | Purpose | Example Types |
|------------|---------|---------------|
| **code-patterns** | HOW things are built | implementation, error_pattern, refactor, file_pattern |
| **conventions** | WHAT rules to follow | rule, guideline, port, naming, structure |
| **discussions** | WHY things were decided | decision, session, preference, user_message, agent_response |
| **github** | Code context from repos | github_code_blob |
| **jira-data** | Project management context | jira_issue, jira_comment |

**Core Capabilities:**
- **30+ Memory Types** for precise categorization across all five collections
- **Agent-Activated Injection**: Sessions start clean -- no ambient Qdrant noise. Bootstrap via skills only.
- **Parzival V2**: Layered bootstrap (L1-L4), constraint re-injection, skill-activated retrieval
- **Langfuse V3**: Full OTel-based tracing with dual-path architecture (trace buffer for hooks, direct SDK for services)
- **Zero-Truncation Principle**: Content is chunked into multiple vectors, never truncated for storage
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

**Best Practices Applied**:
- **BP-038** (Qdrant Best Practices 2026): HNSW configuration, payload indexing, 8-bit scalar quantization
- **BP-039** (RAG Best Practices): Intent detection, token budgets, context injection, hybrid search
- **BP-040** (Event-Driven Architecture): Hook classification, graceful degradation
- **BP-001** (RAG Chunking 2026): 256-512 token chunks, 10-20% overlap, topical chunking

---

## In Development: v2.3

See **Planned - v2.3** section below.

---

## Release History

| Version | Date | Highlights |
|---------|------|------------|
| **v2.2.1** | 2026-03-08 | Triple Fusion Hybrid Search (dense + BM25 + ColBERT), RRF normalization, 4-path search |
| **v2.2.0** | 2026-03-08 | Parzival V2, agent-activated injection, PCB step-files, constraint re-injection |
| **v2.1.0** | 2026-03-06 | Langfuse V3 SDK, DEC-038, TRACE_CONTENT_MAX |
| **v2.0.8** | 2026-02 | Multi-project sync, credential hardening, `aim-` prefix rename |
| **v2.0.7** | 2026-02 | Langfuse tracing, stack.sh, 20 bug fixes |
| **v2.0.5** | 2026-02 | Jira integration, CI hardening |
| **v2.0.4** | 2026-02 | Zero-truncation principle, topical chunking, `_enforce_content_limit` removed |
| **v2.0.3** | 2026-02-03 | First stable release with 3-collection architecture |

---

## Planned - v2.3: Search Hardening (Q2 2026)

**Theme:** ColBERT production hardening and test reorganization

### Search Quality
- [ ] ColBERT production hardening (memory optimization, model caching)
- [ ] Search accuracy benchmarking and regression testing
- [ ] BM25 index maintenance and vocabulary tuning

### Code Quality
- [ ] Test reorganization (unit / integration / e2e separation)
- [ ] Type hints for mypy strict mode
- [ ] Async migration to asyncio.TaskGroup (Python 3.11+)

### Resilience
- [ ] Circuit breaker pattern implementation (failure_threshold=5, reset_timeout=30s)
- [ ] Automatic queue processor (background thread in classifier-worker container)

**Target Release:** June 2026

---

## Planned - v3.0: Multi-Modal & Query API (Q3-Q4 2026)

**Theme:** Multi-modal memory and natural language query interface

### Multi-Modal Memory
- [ ] Image and diagram memory (screenshots, architecture diagrams)
- [ ] Multi-modal embeddings for visual content
- [ ] Cross-modal retrieval (text query to image results)

### Natural Language Query API
- [ ] Natural language query interface for memory retrieval
- [ ] Structured query builder from natural language
- [ ] Query explanation and confidence reporting

### Enterprise Features
- [ ] Team collaboration with shared memory pools
- [ ] Access control and permissions
- [ ] Plugin system for custom extractors

**Target Release:** To be determined based on community demand

---

## Best Practices Foundation

This system is built on verified best practices research:

| BP-ID | Topic | Applied |
|-------|-------|---------|
| **BP-038** | Qdrant Best Practices 2026 | Collection design, HNSW config, payload indexing, quantization |
| **BP-039** | RAG Best Practices | Intent detection, token budgets, context injection, hybrid search |
| **BP-040** | Event-Driven Architecture | Hook classification, graceful degradation, circuit breaker planning |
| **BP-037** | Multi-Tenancy Patterns | group_id isolation, is_tenant config, mandatory tenant filter |
| **BP-001** | RAG Chunking 2026 | 256-512 token chunks, 10-20% overlap, topical chunking |

---

## Community Requests

Features requested by the community are tracked here. Submit requests via [GitHub Issues](https://github.com/Hidden-History/ai-memory/issues/new?template=feature_request.yml).

### Under Consideration
_Submit a feature request to be the first!_

### Recently Implemented
- **Parzival V2 Agent Architecture** - Agent-activated bootstrap, clean session starts
- **Triple Fusion Hybrid Search** (v2.2.1) - Dense + sparse + late interaction retrieval
- **Langfuse V3 Observability** - Full OTel-based tracing for all hook and service operations
- **Five-Collection Architecture** - Dedicated github and jira-data collections
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

**Last Updated:** 2026-03-08
**Architecture Version:** V3.4
**Maintainer:** [@Hidden-History](https://github.com/Hidden-History)

_This roadmap is a living document and evolves based on community feedback and project needs._
