#!/usr/bin/env python3
# LANGFUSE: V4 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
# FORBIDDEN: Langfuse(host=...) with explicit creds, start_span(), start_generation(), langfuse_context
# REQUIRED: get_client(), create_dataset(), create_dataset_item(), flush()
"""Create 5 Langfuse golden datasets for regression testing.

Datasets created:
  DS-01: Retrieval Golden Set     (20-30 items) — query-result pairs across all 5 collections
  DS-02: Error Pattern Match      (10-15 items) — error messages → code-patterns entries
  DS-03: Bootstrap Round-Trip     (5-10 items)  — handoff content stored/retrieved via parzival
  DS-04: Keyword Trigger Routing  (68 items)    — one item per keyword pattern in triggers.py
  DS-05: Chunking Quality         (10 items)    — content types → chunk counts and boundaries

Usage:
  python scripts/create_datasets.py
  python scripts/create_datasets.py --dry-run

Requires env vars: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL

PLAN-012 Phase 3 — Section 6.1
"""

import argparse
import sys

# ---------------------------------------------------------------------------
# Dataset definitions
# ---------------------------------------------------------------------------

DATASET_METADATA = {
    "version": "1.0",
    "created": "2026-03-14",
    "project": "ai-memory",
}


# ---------------------------------------------------------------------------
# DS-01: Retrieval Golden Set (25 items)
# Covers all 5 collections: code-patterns, conventions, discussions, github, jira-data
# Mix: error queries, naming convention queries, decision queries, session history queries,
#       code pattern queries
# ---------------------------------------------------------------------------

DS_01_ITEMS = [
    # --- code-patterns (5 items) ---
    {
        "input": {
            "query": "TypeError unhashable type list when using dict key",
            "collection": "code-patterns",
            "type_filter": "error_pattern",
        },
        "expected_output": {
            "should_match": "TypeError: unhashable type fix — convert list to tuple before using as dict key",
            "min_relevance": 0.75,
        },
    },
    {
        "input": {
            "query": "ImportError cannot import name get_client from langfuse",
            "collection": "code-patterns",
            "type_filter": "error_pattern",
        },
        "expected_output": {
            "should_match": "ImportError langfuse — install langfuse>=4.0.0,<4.1.0 and use V4 get_client() import",
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "query": "QdrantUnavailable connection refused port 6333",
            "collection": "code-patterns",
            "type_filter": "error_pattern",
        },
        "expected_output": {
            "should_match": "QdrantUnavailable — check docker-compose stack is running; verify QDRANT_URL env var",
            "min_relevance": 0.75,
        },
    },
    {
        "input": {
            "query": "retry logic with exponential backoff for Qdrant client",
            "collection": "code-patterns",
            "type_filter": "implementation_pattern",
        },
        "expected_output": {
            "should_match": "exponential backoff pattern with jitter for Qdrant and HTTP calls",
            "min_relevance": 0.70,
        },
    },
    {
        "input": {
            "query": "async context manager pattern for resource cleanup in Python",
            "collection": "code-patterns",
            "type_filter": "implementation_pattern",
        },
        "expected_output": {
            "should_match": "async context manager using __aenter__ and __aexit__ for deterministic cleanup",
            "min_relevance": 0.70,
        },
    },
    # --- conventions (5 items) ---
    {
        "input": {
            "query": "naming convention for Claude Code hook scripts",
            "collection": "conventions",
            "type_filter": "naming",
        },
        "expected_output": {
            "should_match": "hook scripts follow pattern: {phase}_{event}_{action}.py e.g. user_prompt_capture.py",
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "query": "Python module docstring convention for memory submodules",
            "collection": "conventions",
            "type_filter": "structure",
        },
        "expected_output": {
            "should_match": "module docstring pattern: one-line summary, Architecture Reference, Best Practices URLs",
            "min_relevance": 0.70,
        },
    },
    {
        "input": {
            "query": "how should collection names be formatted in Qdrant",
            "collection": "conventions",
            "type_filter": "naming",
        },
        "expected_output": {
            "should_match": "Qdrant collection names use kebab-case: code-patterns, conventions, discussions, github, jira-data",
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "query": "pytest fixture naming patterns for memory module tests",
            "collection": "conventions",
            "type_filter": "structure",
        },
        "expected_output": {
            "should_match": "pytest fixtures use snake_case and descriptive names; mock_qdrant_client, mock_langfuse",
            "min_relevance": 0.65,
        },
    },
    {
        "input": {
            "query": "environment variable naming standard for LANGFUSE settings",
            "collection": "conventions",
            "type_filter": "naming",
        },
        "expected_output": {
            "should_match": "LANGFUSE_* env vars in SCREAMING_SNAKE_CASE; defined in dot-env-dot-example file, never committed",
            "min_relevance": 0.75,
        },
    },
    # --- discussions (5 items) ---
    {
        "input": {
            "query": "why did we choose port 26350 for Qdrant instead of default 6333",
            "collection": "discussions",
            "type_filter": "decision",
        },
        "expected_output": {
            "should_match": "decision to use non-standard Qdrant port 26350 to avoid conflicts with other local services",
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "query": "decision about using hybrid search with sparse and dense vectors",
            "collection": "discussions",
            "type_filter": "decision",
        },
        "expected_output": {
            "should_match": "DEC-042 hybrid search chosen for improved recall on short queries and code snippets",
            "min_relevance": 0.75,
        },
    },
    {
        "input": {
            "query": "what did we decide about Langfuse SDK version compatibility",
            "collection": "discussions",
            "type_filter": "decision",
        },
        "expected_output": {
            "should_match": "DEC-068 mandates Langfuse V3 SDK only; V2 patterns forbidden; get_client() singleton",
            "min_relevance": 0.85,
        },
    },
    {
        "input": {
            "query": "session summary for PLAN-012 evaluation pipeline implementation",
            "collection": "discussions",
            "type_filter": "session",
        },
        "expected_output": {
            "should_match": "PLAN-012 session: implemented LLM-as-judge evaluator with Ollama, OpenRouter, Anthropic providers",
            "min_relevance": 0.75,
        },
    },
    {
        "input": {
            "query": "blocker discussion about ClickHouse memory limits for Langfuse",
            "collection": "discussions",
            "type_filter": "blocker",
        },
        "expected_output": {
            "should_match": "ClickHouse max_server_memory_usage capped at 16 GiB to prevent OOM on WSL2",
            "min_relevance": 0.70,
        },
    },
    # --- github (5 items) ---
    {
        "input": {
            "query": "PR for adding LLM-as-judge evaluation engine PLAN-012",
            "collection": "github",
            "type_filter": "pull_request",
        },
        "expected_output": {
            "should_match": "PR: feat(evaluator): add LLM-as-judge evaluation engine with multi-provider support",
            "min_relevance": 0.75,
        },
    },
    {
        "input": {
            "query": "commit that fixed Langfuse V3 migration from V2 constructor",
            "collection": "github",
            "type_filter": "commit",
        },
        "expected_output": {
            "should_match": "commit dc1335e: migrate Langfuse to V3 get_client() singleton pattern",
            "min_relevance": 0.75,
        },
    },
    {
        "input": {
            "query": "CI workflow for regression tests on memory module changes",
            "collection": "github",
            "type_filter": "workflow",
        },
        "expected_output": {
            "should_match": "GitHub Actions workflow triggers on src/memory/** changes; runs pytest regression suite",
            "min_relevance": 0.70,
        },
    },
    {
        "input": {
            "query": "issue for implementing hybrid vector search with HNSW optimization",
            "collection": "github",
            "type_filter": "issue",
        },
        "expected_output": {
            "should_match": "issue: implement hybrid HNSW + sparse vector index for improved search recall",
            "min_relevance": 0.70,
        },
    },
    {
        "input": {
            "query": "feature branch for v2.2.3 cleanup and evaluation pipeline",
            "collection": "github",
            "type_filter": "branch",
        },
        "expected_output": {
            "should_match": "branch feature/v2.2.3-cleanup contains PLAN-012 wave 2 evaluator and dataset work",
            "min_relevance": 0.70,
        },
    },
    # --- jira-data (5 items) ---
    {
        "input": {
            "query": "PLAN-012 Langfuse observability optimization epic requirements",
            "collection": "jira-data",
            "type_filter": "epic",
        },
        "expected_output": {
            "should_match": "PLAN-012: Langfuse observability optimization — evaluator engine, datasets, CI gate",
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "query": "TD-275 add trace tags for classification and retrieval events",
            "collection": "jira-data",
            "type_filter": "story",
        },
        "expected_output": {
            "should_match": "TD-275: add Langfuse trace tags to all 17 hook scripts for evaluator filtering",
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "query": "TD-228 fix deterministic trace IDs for deduplication",
            "collection": "jira-data",
            "type_filter": "story",
        },
        "expected_output": {
            "should_match": "TD-228: implement deterministic trace ID via md5 seed for score deduplication",
            "min_relevance": 0.75,
        },
    },
    {
        "input": {
            "query": "tech debt item for ClickHouse TTL configuration 90 days",
            "collection": "jira-data",
            "type_filter": "tech_debt",
        },
        "expected_output": {
            "should_match": "tech debt: set ClickHouse TTL to 90 days for traces, observations, scores tables",
            "min_relevance": 0.70,
        },
    },
    {
        "input": {
            "query": "sprint planning for v2.2.3 evaluation and regression testing",
            "collection": "jira-data",
            "type_filter": "sprint",
        },
        "expected_output": {
            "should_match": "sprint v2.2.3: evaluation pipeline WP-1 through WP-4, regression CI gate",
            "min_relevance": 0.70,
        },
    },
]

# ---------------------------------------------------------------------------
# DS-02: Error Pattern Match (13 items)
# Input: actual error messages; Expected: matching error_pattern in code-patterns
# Covers Python, JavaScript, bash error patterns
# ---------------------------------------------------------------------------

DS_02_ITEMS = [
    # --- Python errors ---
    {
        "input": {
            "error_message": "TypeError: unhashable type: 'list'",
            "language": "python",
            "context": "Using a list as a dictionary key in memory storage lookup",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "TypeError",
            "fix_summary": "Convert list to tuple before using as dict key; or use frozenset for sets",
        },
    },
    {
        "input": {
            "error_message": "ImportError: cannot import name 'get_client' from 'langfuse'",
            "language": "python",
            "context": "Running hook script with outdated langfuse package (V2 installed)",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "ImportError",
            "fix_summary": "Upgrade: pip install 'langfuse>=4.0.0,<4.1.0'; V4 compatible — get_client() API preserved",
        },
    },
    {
        "input": {
            "error_message": "AttributeError: 'NoneType' object has no attribute 'create_dataset'",
            "language": "python",
            "context": "Langfuse client is None because LANGFUSE_ENABLED=false or keys not set",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "AttributeError",
            "fix_summary": "Set LANGFUSE_ENABLED=true and verify LANGFUSE_PUBLIC_KEY/SECRET_KEY before calling client methods",
        },
    },
    {
        "input": {
            "error_message": "KeyError: 'session_id'",
            "language": "python",
            "context": "Hook input JSON missing session_id field during user_prompt_capture",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "KeyError",
            "fix_summary": "Use hook_input.get('session_id', '') with fallback; never index directly on hook input dicts",
        },
    },
    {
        "input": {
            "error_message": "ValueError: score value 1.5 out of range [0.0, 1.0] for NUMERIC score config",
            "language": "python",
            "context": "Evaluation score exceeds 1.0 maximum defined in Langfuse score config",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "ValueError",
            "fix_summary": "Clamp evaluation score: value = max(0.0, min(1.0, raw_score)) before create_score()",
        },
    },
    {
        "input": {
            "error_message": "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/trace_buffer/event_abc.json'",
            "language": "python",
            "context": "Trace flush worker trying to process event file already consumed by another process",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "FileNotFoundError",
            "fix_summary": "Use try/except FileNotFoundError in flush worker; files may be consumed by concurrent worker",
        },
    },
    {
        "input": {
            "error_message": "ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))",
            "language": "python",
            "context": "Qdrant client HTTP connection dropped during large batch upsert",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "ConnectionError",
            "fix_summary": "Implement retry with exponential backoff; check Qdrant health before large batch operations",
        },
    },
    {
        "input": {
            "error_message": "TimeoutError: Langfuse flush timed out after 15 seconds",
            "language": "python",
            "context": "Stop hook flush exceeds LANGFUSE_FLUSH_TIMEOUT_SECONDS during high-traffic session",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "TimeoutError",
            "fix_summary": "Increase LANGFUSE_FLUSH_TIMEOUT_SECONDS or reduce batch size; use SIGALRM guard in stop hook",
        },
    },
    {
        "input": {
            "error_message": "PermissionError: [Errno 13] Permission denied: '/var/run/ai-memory/trace_buffer'",
            "language": "python",
            "context": "Hook script cannot write to trace buffer directory due to ownership mismatch",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "PermissionError",
            "fix_summary": "chown trace_buffer dir to hook subprocess user; or set TRACE_BUFFER_PATH to user-writable path",
        },
    },
    # --- JavaScript errors ---
    {
        "input": {
            "error_message": "TypeError: Cannot read properties of undefined (reading 'session_id')",
            "language": "javascript",
            "context": "Claude Code settings.json hook config missing session_id in env block",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "TypeError",
            "fix_summary": "Use optional chaining: obj?.session_id ?? ''; verify settings.json env block has CLAUDE_SESSION_ID",
        },
    },
    {
        "input": {
            "error_message": "SyntaxError: Unexpected token '<' in JSON at position 0",
            "language": "javascript",
            "context": "Langfuse API returned HTML error page instead of JSON (auth failure or wrong base URL)",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "SyntaxError",
            "fix_summary": "Check LANGFUSE_BASE_URL env var; verify API keys are set; Langfuse server may be returning HTML error",
        },
    },
    # --- Bash errors ---
    {
        "input": {
            "error_message": "bash: python3: command not found",
            "language": "bash",
            "context": "Hook script calling python3 but not in virtual environment path",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "command_not_found",
            "fix_summary": "Use absolute path to venv python: /path/to/.venv/bin/python3; or activate venv before hook",
        },
    },
    {
        "input": {
            "error_message": "FAILED: test_create_datasets.py::test_ds04_item_count - AssertionError: assert 60 == 68",
            "language": "bash",
            "context": "pytest test detecting DS-04 missing 3 keyword patterns from triggers.py",
        },
        "expected_output": {
            "collection": "code-patterns",
            "type_filter": "error_pattern",
            "error_type": "AssertionError",
            "fix_summary": "Count keyword patterns in TRIGGER_CONFIG; best_practices_keywords has 27, decision_keywords 20, session_history_keywords 16, error_detection 5 = 68 total",
        },
    },
]

# ---------------------------------------------------------------------------
# DS-03: Bootstrap Round-Trip (7 items)
# Input: handoff content stored via parzival-save-handoff
# Expected: same content retrieved by aim-parzival-bootstrap
# Tests agent_id=parzival tenant isolation
# ---------------------------------------------------------------------------

DS_03_ITEMS = [
    {
        "input": {
            "agent_id": "parzival",
            "content_type": "session_summary",
            "content": "Session PM #190: Completed PLAN-012 Wave 2 WP-1 and WP-2. Implemented LLM-as-judge evaluator with Ollama default provider and 5 alternative providers. Created 6 evaluator definitions (EV-01 through EV-06) with judge prompts. Branch: feature/v2.2.3-cleanup. Next: WP-3 golden datasets, WP-4 CI gate.",
            "skill": "parzival-save-handoff",
        },
        "expected_output": {
            "agent_id": "parzival",
            "retrieved_by_skill": "aim-parzival-bootstrap",
            "content_present": True,
            "key_terms_required": [
                "PLAN-012",
                "WP-1",
                "WP-2",
                "evaluator",
                "Ollama",
                "feature/v2.2.3-cleanup",
            ],
            "min_relevance": 0.85,
        },
    },
    {
        "input": {
            "agent_id": "parzival",
            "content_type": "decision",
            "content": "DEC-068: Langfuse V3 SDK only in this project. Use get_client() singleton pattern. Never use the constructor with explicit creds. Rationale: V2/V3 divergence caused 13+ integration failures across 10 sessions.",
            "skill": "parzival-save-handoff",
        },
        "expected_output": {
            "agent_id": "parzival",
            "retrieved_by_skill": "aim-parzival-bootstrap",
            "content_present": True,
            "key_terms_required": ["DEC-068", "Langfuse", "V3", "get_client"],
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "agent_id": "parzival",
            "content_type": "insight",
            "content": "Insight from PM #145: When migrating Langfuse V2 to V3, the critical change is replacing Langfuse(public_key=..., secret_key=..., host=...) with get_client() which reads env vars automatically. The V3 SDK is OTel-based and not fully backward compatible.",
            "skill": "parzival-save-handoff",
        },
        "expected_output": {
            "agent_id": "parzival",
            "retrieved_by_skill": "aim-parzival-bootstrap",
            "content_present": True,
            "key_terms_required": [
                "PM #145",
                "Langfuse",
                "V2",
                "V3",
                "get_client",
                "OTel",
            ],
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "agent_id": "parzival",
            "content_type": "handoff_document",
            "content": "HANDOFF PM #188: Qdrant collections verified healthy. All 5 collections (code-patterns, conventions, discussions, github, jira-data) operational. Hybrid search enabled on code-patterns and conventions. HNSW m=16 ef_construct=200. Next session: run PLAN-012 WP-3 dataset creation script.",
            "skill": "parzival-save-handoff",
        },
        "expected_output": {
            "agent_id": "parzival",
            "retrieved_by_skill": "aim-parzival-bootstrap",
            "content_present": True,
            "key_terms_required": [
                "Qdrant",
                "code-patterns",
                "conventions",
                "discussions",
                "hybrid search",
                "HNSW",
            ],
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "agent_id": "parzival",
            "content_type": "blocker",
            "content": "BLOCKER PM #171: ClickHouse OOM crash when Langfuse processes large trace batch. Root cause: default memory limit too high for WSL2. Fix: set max_server_memory_usage to 17179869184 (16 GiB) in clickhouse-config.xml. Status: RESOLVED.",
            "skill": "parzival-save-handoff",
        },
        "expected_output": {
            "agent_id": "parzival",
            "retrieved_by_skill": "aim-parzival-bootstrap",
            "content_present": True,
            "key_terms_required": [
                "ClickHouse",
                "OOM",
                "WSL2",
                "max_server_memory_usage",
                "RESOLVED",
            ],
            "min_relevance": 0.75,
        },
    },
    {
        "input": {
            "agent_id": "parzival",
            "content_type": "session_summary",
            "content": "Session PM #185: Completed TD-275 (trace tags) and TD-228 (deterministic trace IDs). All 17 hook scripts now emit Langfuse tags: search/retrieval, classification, capture, injection, bootstrap, skill. Deterministic score_id uses md5(trace_id:evaluator_name:since) for idempotency.",
            "skill": "parzival-save-handoff",
        },
        "expected_output": {
            "agent_id": "parzival",
            "retrieved_by_skill": "aim-parzival-bootstrap",
            "content_present": True,
            "key_terms_required": [
                "TD-275",
                "TD-228",
                "trace tags",
                "17 hook",
                "md5",
                "idempotency",
            ],
            "min_relevance": 0.80,
        },
    },
    {
        "input": {
            "agent_id": "parzival",
            "content_type": "decision",
            "content": "DEC-055: Use port 26350 for Qdrant REST API (non-standard). Rationale: avoids conflict with other local services that commonly use 6333. Port 26351 used for Qdrant gRPC. Documented in docker-compose.yml and the dot-env template file.",
            "skill": "parzival-save-handoff",
        },
        "expected_output": {
            "agent_id": "parzival",
            "retrieved_by_skill": "aim-parzival-bootstrap",
            "content_present": True,
            "key_terms_required": [
                "DEC-055",
                "port 26350",
                "Qdrant",
                "non-standard",
                "26351",
                "gRPC",
            ],
            "min_relevance": 0.80,
        },
    },
]

# ---------------------------------------------------------------------------
# DS-04: Keyword Trigger Routing (68 items)
# One item per keyword pattern in src/memory/triggers.py TRIGGER_CONFIG
# Triggers: error_detection (5), decision_keywords (20), session_history_keywords (16), best_practices_keywords (27)
# ---------------------------------------------------------------------------

DS_04_ITEMS = [
    # -----------------------------------------------------------------------
    # error_detection (5 patterns) → collection: code-patterns
    # Patterns: "Error:", "Exception:", "Traceback", "FAILED:", "error:"
    # -----------------------------------------------------------------------
    {
        "input": {
            "user_prompt": "TypeError: 'NoneType' object is not subscriptable when reading hook output"
        },
        "expected_output": {
            "expected_trigger": "error_detection",
            "expected_collection": "code-patterns",
        },
    },
    {
        "input": {
            "user_prompt": "RuntimeException: connection pool exhausted after 30s timeout in storage layer"
        },
        "expected_output": {
            "expected_trigger": "error_detection",
            "expected_collection": "code-patterns",
        },
    },
    {
        "input": {
            "user_prompt": "Traceback (most recent call last): MemoryError during large batch embedding"
        },
        "expected_output": {
            "expected_trigger": "error_detection",
            "expected_collection": "code-patterns",
        },
    },
    {
        "input": {
            "user_prompt": "FAILED: tests/test_search.py::test_hybrid_search - AssertionError: results empty"
        },
        "expected_output": {
            "expected_trigger": "error_detection",
            "expected_collection": "code-patterns",
        },
    },
    {
        "input": {
            "user_prompt": "error: failed to connect to Qdrant at http://localhost:26350 — is the service running?"
        },
        "expected_output": {
            "expected_trigger": "error_detection",
            "expected_collection": "code-patterns",
        },
    },
    # -----------------------------------------------------------------------
    # decision_keywords (20 patterns) → collection: discussions
    # -----------------------------------------------------------------------
    {
        "input": {
            "user_prompt": "why did we choose to use Qdrant over Weaviate for this project?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "why do we use port 26350 instead of the default Qdrant port?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what was decided about the Langfuse SDK version we should use?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what did we decide on the evaluation scoring thresholds?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "remember when we had that ClickHouse OOM crash during tracing?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "remember the decision to standardize on get_client() for Langfuse?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "remember what we agreed on for the hook script naming convention?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "remember how we solved the thread-safety issue in the storage module?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "do you remember the architecture decisions we made for the evaluation pipeline?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "recall when we switched from synchronous to async embedding calls?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "recall the original design rationale for the dual-collection search approach?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "recall how we implemented the tenant isolation for the parzival agent?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "last session we were working on the evaluator runner implementation"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "in the previous session we discussed the HNSW index configuration for Qdrant"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "earlier we agreed to use Ollama as the default evaluation provider"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "before we started PLAN-012, we had decided on the scoring approach"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "previously we tried using the V2 Langfuse SDK and had many failures"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "last time we worked on the chunker we left the code review unfinished"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what did we do to fix the memory leak in the trace buffer worker?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "where did we leave off with the hybrid vector migration script?"
        },
        "expected_output": {
            "expected_trigger": "decision_keywords",
            "expected_collection": "discussions",
        },
    },
    # -----------------------------------------------------------------------
    # session_history_keywords (16 patterns) → collection: discussions (type: session)
    # -----------------------------------------------------------------------
    {
        "input": {
            "user_prompt": "what have we done on the PLAN-012 evaluation pipeline so far?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what did we work on during the last sprint for the memory system?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the project status for the v2.2.3 cleanup sprint?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "where were we with the Langfuse integration before the holiday?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what's the status of the evaluator engine implementation?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "let's continue from where we left off on the regression test suite"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "can we pick up where we left off with the dataset creation script?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "continue where we were on the score config Langfuse setup"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {"user_prompt": "what's left to do on the PLAN-012 wave 2 stories?"},
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "how much remaining work is there for the regression CI gate?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what's next for the memory system after PLAN-012 completes?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what's next on the backlog after the evaluation pipeline is done?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what's next in the sprint after WP-3 golden datasets?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "what are the next steps for the Langfuse evaluation pipeline rollout?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "show me the todo items we identified in the last session review"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    {
        "input": {
            "user_prompt": "how many tasks remaining in the current v2.2.3 sprint?"
        },
        "expected_output": {
            "expected_trigger": "session_history_keywords",
            "expected_collection": "discussions",
        },
    },
    # -----------------------------------------------------------------------
    # best_practices_keywords (27 patterns) → collection: conventions
    # -----------------------------------------------------------------------
    {
        "input": {
            "user_prompt": "what is the best practice for Python logging in hook scripts?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what are the best practices for Qdrant collection schema design?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the coding standard for async functions in the memory module?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what are the coding standards followed in this project for Python?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what convention should I follow for naming new agent scripts?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what are the conventions for Python hook naming in Claude Code?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what's the pattern for error handling in async memory operations?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the pattern for dependency injection in the memory module?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "how should I name my hooks when creating a new Claude Code integration?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "how do I structure a new submodule under src/memory/?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what's the right way to handle session IDs in hook pipeline traces?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the right way to call flush() at the end of a Langfuse script?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what naming convention should I use for new pytest fixtures?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what style guide do we follow for Python formatting in this project?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "research the pattern for implementing retry with exponential backoff in Python"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "research best practice for embedding model selection for semantic search"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "should I use dataclasses or TypedDict for configuration objects?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what's recommended for chunking long markdown documents for embedding?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is recommended for structuring evaluator YAML config files?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the recommended approach for session isolation between agents?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the preferred approach for logging structured data in Python?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the preferred way to initialize the Qdrant client in tests?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "look up the pattern for using sparse vectors in Qdrant hybrid search"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "find out about best practices for writing idempotent data migration scripts"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what do the docs say about Langfuse V3 session ID propagation?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the industry standard for API versioning in REST services?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
    {
        "input": {
            "user_prompt": "what is the common pattern for implementing a circuit breaker in Python?"
        },
        "expected_output": {
            "expected_trigger": "best_practices_keywords",
            "expected_collection": "conventions",
        },
    },
]

# ---------------------------------------------------------------------------
# DS-05: Chunking Quality (10 items)
# Input: various content types; Expected: chunk count, token sizes, boundary quality
# Tests IntelligentChunker routing decisions
# ---------------------------------------------------------------------------

DS_05_ITEMS = [
    {
        "input": {
            "content": "The memory system stores three categories of knowledge.\n\nFirst, code patterns capture recurring implementation strategies and their trade-offs. These are indexed by error type and language for fast retrieval during debugging sessions.\n\nSecond, conventions record project-specific rules about naming, structure, and style. Unlike code patterns, conventions are normative rather than descriptive — they prescribe what should be done.\n\nThird, discussions preserve decisions, session summaries, and architectural rationale. These are the most valuable for cross-session continuity.",
            "content_type": "prose_paragraphs",
            "estimated_tokens": 120,
        },
        "expected_output": {
            "expected_chunk_count": 3,
            "chunk_strategy": "paragraph_boundary",
            "avg_tokens_per_chunk": 40,
            "boundary_quality": "high",
            "chunker_type": "prose",
        },
    },
    {
        "input": {
            "content": 'def search_memories(\n    query: str,\n    collection: str,\n    type_filter: str | None = None,\n    limit: int = 5,\n    score_threshold: float = 0.6,\n) -> list[dict]:\n    """Search Qdrant collection with hybrid sparse+dense vectors."""\n    client = get_qdrant_client()\n    embedding = EmbeddingClient().embed(query)\n    filters = build_filters(type_filter)\n    results = client.query_points(\n        collection_name=collection,\n        prefetch=[\n            Prefetch(query=embedding.dense, using="dense", limit=limit * 2),\n            Prefetch(query=SparseVector(embedding.sparse), using="sparse", limit=limit * 2),\n        ],\n        query=FusionQuery(fusion=Fusion.RRF),\n        query_filter=filters,\n        limit=limit,\n        score_threshold=score_threshold,\n    )\n    return [point.payload for point in results.points]',
            "content_type": "python_function",
            "estimated_tokens": 150,
        },
        "expected_output": {
            "expected_chunk_count": 1,
            "chunk_strategy": "whole_function",
            "avg_tokens_per_chunk": 150,
            "boundary_quality": "high",
            "chunker_type": "code",
        },
    },
    {
        "input": {
            "content": "# Memory System Collections\n\n## code-patterns\n\nStores implementation patterns, error fixes, and code examples.\n\n**Fields**: `type` (error_pattern | implementation_pattern | snippet), `language`, `content`, `tags`\n\n## conventions\n\nStores naming conventions, style guides, and project standards.\n\n**Fields**: `type` (naming | structure | style | process), `content`, `scope`\n\n## discussions\n\nStores decisions, session summaries, and architectural rationale.\n\n**Fields**: `type` (decision | session | blocker | preference), `content`, `session_id`",
            "content_type": "markdown_sections",
            "estimated_tokens": 110,
        },
        "expected_output": {
            "expected_chunk_count": 3,
            "chunk_strategy": "markdown_heading",
            "avg_tokens_per_chunk": 37,
            "boundary_quality": "high",
            "chunker_type": "markdown",
        },
    },
    {
        "input": {
            "content": "The IntelligentChunker routes content to the appropriate strategy.\n\n```python\nif content_type == 'code':\n    return CodeChunker().chunk(content)\nelif content_type == 'markdown':\n    return MarkdownChunker().chunk(content)\nelse:\n    return ProseChunker().chunk(content)\n```\n\nEach chunker preserves semantic boundaries. Code chunkers keep function bodies intact. Markdown chunkers split on heading boundaries. Prose chunkers use sentence and paragraph detection.",
            "content_type": "mixed_prose_code",
            "estimated_tokens": 100,
        },
        "expected_output": {
            "expected_chunk_count": 2,
            "chunk_strategy": "mixed_split",
            "avg_tokens_per_chunk": 50,
            "boundary_quality": "medium",
            "chunker_type": "intelligent",
        },
    },
    {
        "input": {
            "content": "Session complete.",
            "content_type": "very_short_text",
            "estimated_tokens": 3,
        },
        "expected_output": {
            "expected_chunk_count": 1,
            "chunk_strategy": "no_split_needed",
            "avg_tokens_per_chunk": 3,
            "boundary_quality": "high",
            "chunker_type": "passthrough",
        },
    },
    {
        "input": {
            "content": 'class EvaluatorRunner:\n    """Core evaluation pipeline — fetch traces, evaluate, score."""\n\n    def __init__(self, config_path: str) -> None:\n        self.config = EvaluatorConfig.from_yaml(config_path)\n        self.langfuse = get_client()\n\n    def run(\n        self,\n        evaluator_id: str | None,\n        since: datetime,\n        until: datetime,\n        dry_run: bool = False,\n    ) -> dict:\n        """Run evaluation pipeline for specified time window."""\n        results = []\n        cursor = None\n        while True:\n            page = self.langfuse.api.trace.list(\n                start_time=since,\n                end_time=until,\n                cursor=cursor,\n                limit=self.config.batch_size,\n            )\n            for trace in page.data:\n                if not self._should_evaluate(trace, evaluator_id):\n                    continue\n                score = self._evaluate_trace(trace)\n                if not dry_run:\n                    self._attach_score(trace.id, score)\n                results.append(score)\n            cursor = page.meta.next_cursor\n            if not cursor:\n                break\n        return {"total": len(results), "scores": results}',
            "content_type": "python_class_method",
            "estimated_tokens": 200,
        },
        "expected_output": {
            "expected_chunk_count": 1,
            "chunk_strategy": "whole_class_method",
            "avg_tokens_per_chunk": 200,
            "boundary_quality": "high",
            "chunker_type": "code",
        },
    },
    {
        "input": {
            "content": "Error handling in hook scripts follows a strict no-crash policy. Every Langfuse call is wrapped in try/except Exception: pass. The rationale is simple: tracing is observability infrastructure, not business logic. A crashed hook blocks Claude Code entirely, which is far worse than a missing trace.\n\nThis policy extends to the trace buffer writes. If the buffer directory is not writable, we log a warning and continue. If the JSON serialization fails, we skip that event. The hook must complete and return control to Claude Code within its SLA.\n\nThere is one exception: if the hook's PRIMARY work fails (e.g., cannot store a memory due to Qdrant being down), we DO propagate that error. But any ancillary tracing or logging failure is silently swallowed.",
            "content_type": "prose_three_paragraphs",
            "estimated_tokens": 145,
        },
        "expected_output": {
            "expected_chunk_count": 3,
            "chunk_strategy": "paragraph_boundary",
            "avg_tokens_per_chunk": 48,
            "boundary_quality": "high",
            "chunker_type": "prose",
        },
    },
    {
        "input": {
            "content": "## LANGFUSE-INTEGRATION-SPEC.md\n\n**Version**: 1.2  \n**Status**: AUTHORITATIVE\n\n### 2. CRITICAL: V3 SDK Only\n\nThe Langfuse Python SDK V3 (released May 2025) is OTel-based and NOT backward compatible with V2.\n\n```python\n# CORRECT — V3 singleton\nfrom langfuse import get_client\nlangfuse = get_client()\n\n# WRONG — V2 pattern: bypasses env config, do not use\n# Langfuse(host=...) with explicit creds is DISCOURAGED\n```\n\n### 3. Architecture: Dual Integration\n\nPath A (hooks): emit_trace_event() → JSON buffer → trace_flush_worker  \nPath B (services): get_client() → direct SDK calls",
            "content_type": "markdown_with_code_blocks",
            "estimated_tokens": 130,
        },
        "expected_output": {
            "expected_chunk_count": 3,
            "chunk_strategy": "markdown_heading_with_code_preservation",
            "avg_tokens_per_chunk": 43,
            "boundary_quality": "high",
            "chunker_type": "markdown",
        },
    },
    {
        "input": {
            "content": " ".join(
                [
                    "The evaluation pipeline processes memory system traces to assess quality across six dimensions.",
                    "Retrieval relevance measures whether retrieved memories are pertinent to the triggering query.",
                    "Injection value measures whether injected context improved the Claude Code response.",
                    "Capture completeness verifies that all required fields were extracted from hook events.",
                    "Classification accuracy checks whether the LLM classifier correctly typed the captured content.",
                    "Bootstrap quality evaluates whether cross-session memories surfaced by aim-parzival-bootstrap were relevant to the new session.",
                    "Session coherence verifies that the right memories were injected at the right times throughout a session.",
                    "Each dimension is evaluated by a separate evaluator definition with its own judge prompt.",
                    "Evaluators run on different sampling rates based on trace volume.",
                    "High-volume evaluators sample 5% of traces; low-volume ones sample 100%.",
                    "Results are stored as Langfuse scores and surfaced in the Langfuse UI dashboard.",
                    "The CI regression gate checks that average scores remain above defined thresholds.",
                    "Threshold violations block PR merges to the main branch.",
                    "This creates a continuous quality feedback loop for the memory system.",
                    "The loop is: capture → classify → retrieve → inject → evaluate → score → gate.",
                ]
            ),
            "content_type": "very_long_single_paragraph",
            "estimated_tokens": 210,
        },
        "expected_output": {
            "expected_chunk_count": 2,
            "chunk_strategy": "sentence_boundary_split",
            "avg_tokens_per_chunk": 105,
            "boundary_quality": "medium",
            "chunker_type": "prose",
        },
    },
    {
        "input": {
            "content": "TRIGGER_CONFIG stores keyword patterns for six trigger types:\n\n1. error_detection — 5 patterns matching Error:, Exception:, Traceback, FAILED:, error:\n2. new_file — no patterns (event-driven)\n3. first_edit — no patterns (event-driven)\n4. decision_keywords — 20 patterns for past-decision recall\n5. session_history_keywords — 16 patterns for session continuity\n6. best_practices_keywords — 27 patterns for convention lookup\n\nTotal keyword-based patterns: 63\n\nPattern collision detection runs at module load via validate_keyword_patterns().",
            "content_type": "structured_list_with_prose",
            "estimated_tokens": 100,
        },
        "expected_output": {
            "expected_chunk_count": 2,
            "chunk_strategy": "structure_aware_split",
            "avg_tokens_per_chunk": 50,
            "boundary_quality": "high",
            "chunker_type": "intelligent",
        },
    },
]


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

DATASETS = [
    {
        "name": "ds-01-retrieval-golden-set",
        "description": (
            "Golden set for retrieval quality regression. "
            "25 query-result pairs covering all 5 Qdrant collections."
        ),
        "metadata": {
            **DATASET_METADATA,
            "evaluator": "EV-01",
            "item_count": len(DS_01_ITEMS),
        },
        "items": DS_01_ITEMS,
    },
    {
        "name": "ds-02-error-pattern-match",
        "description": (
            "Error pattern matching dataset. "
            "13 realistic error messages from Python, JavaScript, and bash."
        ),
        "metadata": {
            **DATASET_METADATA,
            "evaluator": "EV-03",
            "item_count": len(DS_02_ITEMS),
        },
        "items": DS_02_ITEMS,
    },
    {
        "name": "ds-03-bootstrap-round-trip",
        "description": (
            "Bootstrap round-trip dataset. "
            "7 handoff documents stored via parzival-save-handoff and retrieved via aim-parzival-bootstrap."
        ),
        "metadata": {
            **DATASET_METADATA,
            "evaluator": "EV-05",
            "item_count": len(DS_03_ITEMS),
        },
        "items": DS_03_ITEMS,
    },
    {
        "name": "ds-04-keyword-trigger-routing",
        "description": (
            "Keyword trigger routing dataset. "
            "68 items — one per keyword pattern in src/memory/triggers.py TRIGGER_CONFIG."
        ),
        "metadata": {
            **DATASET_METADATA,
            "evaluator": "EV-04",
            "item_count": len(DS_04_ITEMS),
        },
        "items": DS_04_ITEMS,
    },
    {
        "name": "ds-05-chunking-quality",
        "description": (
            "Chunking quality dataset. "
            "10 content samples testing IntelligentChunker routing and boundary quality."
        ),
        "metadata": {
            **DATASET_METADATA,
            "evaluator": "EV-03",
            "item_count": len(DS_05_ITEMS),
        },
        "items": DS_05_ITEMS,
    },
]


# ---------------------------------------------------------------------------
# Creation logic
# ---------------------------------------------------------------------------


def create_all_datasets(dry_run: bool = False) -> int:
    """Create all 5 golden datasets in Langfuse.

    Idempotent — safe to run multiple times. Existing datasets and items
    are left unchanged; only new items are created.

    Args:
        dry_run: If True, print what would be created without calling Langfuse.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    if dry_run:
        print("[DRY RUN] Would create the following datasets:\n")
        for ds in DATASETS:
            print(f"  Dataset: {ds['name']}")
            print(f"    Description: {ds['description']}")
            print(f"    Items: {len(ds['items'])}")
            print(f"    Metadata: {ds['metadata']}")
            print()
        total_items = sum(len(ds["items"]) for ds in DATASETS)
        print(f"[DRY RUN] Total datasets: {len(DATASETS)}, total items: {total_items}")
        return 0

    try:
        from langfuse import (
            get_client,  # V3 singleton — NEVER use constructor with explicit creds
        )

        langfuse = get_client()
    except ImportError as exc:
        print(f"ERROR: langfuse package not installed — {exc}", file=sys.stderr)
        print("Run: pip install 'langfuse>=4.0.0,<4.1.0'", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Failed to get Langfuse client — {exc}", file=sys.stderr)
        return 1

    total_datasets_created = 0
    total_items_created = 0
    errors = 0

    for ds in DATASETS:
        name = ds["name"]
        print(f"\nProcessing dataset: {name}")

        # Create dataset (idempotent — skip if already exists)
        try:
            langfuse.create_dataset(
                name=name,
                description=ds["description"],
                metadata=ds["metadata"],
            )
            print(f"  [OK] Dataset created: {name}")
            total_datasets_created += 1
        except Exception as exc:
            # Dataset may already exist — log and continue to item creation
            print(f"  [SKIP] Dataset {name!r}: {exc}")

        # Create items (idempotent — Langfuse deduplicates by source_trace_id if provided;
        # without it, items are appended; re-running creates duplicates only if items changed)
        item_count = 0
        for i, item in enumerate(ds["items"]):
            stable_id = f"{name}-item-{i:03d}"
            try:
                langfuse.create_dataset_item(
                    id=stable_id,
                    dataset_name=name,
                    input=item["input"],
                    expected_output=item["expected_output"],
                )
                item_count += 1
            except Exception as exc:
                print(f"  [ERROR] Item {i} in {name}: {exc}", file=sys.stderr)
                errors += 1

        total_items_created += item_count
        print(f"  [OK] {item_count}/{len(ds['items'])} items created for {name}")

    # Flush all buffered data before exit (V3 requirement for short-lived scripts)
    try:
        langfuse.flush()
    except Exception as exc:
        print(f"WARNING: Langfuse flush failed — {exc}", file=sys.stderr)

    print(
        f"\nDone. Datasets: {total_datasets_created}/{len(DATASETS)}, "
        f"Items: {total_items_created}, Errors: {errors}"
    )
    return 0 if errors == 0 else 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create 5 Langfuse golden datasets for regression testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Requires env vars: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL\n"
            "PLAN-012 Phase 3 — Section 6.1"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without calling Langfuse API.",
    )
    args = parser.parse_args()
    return create_all_datasets(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
