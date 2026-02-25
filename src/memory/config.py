"""Configuration management with pydantic-settings for AI Memory Module.

2026 Best Practices Applied:
- pydantic-settings v2.6+ for type-safe configuration
- Automatic .env file loading with proper precedence
- Validation with clear error messages
- Environment variable prefixes for clarity and namespacing
- SecretStr for sensitive data
- Frozen config (thread-safe, immutable after load)

References:
- Pydantic Settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- Environment Variable Security: https://securityboulevard.com/2025/12/are-environment-variables-still-safe-for-secrets-in-2026/
"""

import logging
import os
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

__all__ = [
    "AGENTS",
    "AGENT_TOKEN_BUDGETS",
    "COLLECTION_CODE_PATTERNS",
    "COLLECTION_CONVENTIONS",
    "COLLECTION_DISCUSSIONS",
    "COLLECTION_JIRA_DATA",
    "COLLECTION_NAMES",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL",
    "TYPE_AGENT_RESPONSE",
    "TYPE_SESSION",
    "TYPE_USER_MESSAGE",
    "VALID_AGENTS",
    "MemoryConfig",
    "ProjectSyncConfig",
    "discover_projects",
    "get_agent_token_budget",
    "get_config",
    "reset_config",
]

# Memory System v2.0 Collection Names (MEMORY-SYSTEM-REDESIGN-v2.md Section 4)
COLLECTION_CODE_PATTERNS = "code-patterns"  # HOW things are built
COLLECTION_CONVENTIONS = "conventions"  # WHAT rules to follow
COLLECTION_DISCUSSIONS = "discussions"  # WHY things were decided

# Jira integration collection (PLAN-004 Phase 1)
# NOTE: This is a CONDITIONAL collection (only created when jira_sync_enabled=True)
# Therefore it is NOT included in COLLECTION_NAMES to avoid breaking existing iteration logic
COLLECTION_JIRA_DATA = "jira-data"  # External work items from Jira Cloud

# All collection names for iteration/validation
COLLECTION_NAMES = [
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
]

# Memory types for conversations (V2.0)
TYPE_USER_MESSAGE = "user_message"
TYPE_AGENT_RESPONSE = "agent_response"
TYPE_SESSION = "session"  # Session summaries from PreCompact hook

# Embedding configuration (SPEC-010: Dual Embedding Models)
EMBEDDING_DIMENSIONS = 768
EMBEDDING_MODEL = (
    "jina-embeddings-v2-base-en"  # Legacy constant, kept for backward compat
)
EMBEDDING_MODEL_EN = "jina-embeddings-v2-base-en"  # Prose model
EMBEDDING_MODEL_CODE = "jina-embeddings-v2-base-code"  # Code model


class MemoryConfig(BaseSettings):
    """Configuration for AI Memory Module.

    Loads from (in order of precedence):
    1. Environment variables (highest priority)
    2. .env file in project root
    3. Default values (lowest priority)

    All threshold values are validated on load.

    Attributes:
        similarity_threshold: Semantic similarity cutoff (0.0-1.0) for search results
        dedup_threshold: Similarity cutoff (0.80-0.99) for duplicate detection
        max_retrievals: Maximum number of memories to retrieve per search
        token_budget: Maximum token budget for context injection
        qdrant_host: Qdrant server hostname
        qdrant_port: Qdrant server port (default 26350 per Story 1.1)
        qdrant_api_key: Optional API key for Qdrant authentication
        embedding_host: Embedding service hostname
        embedding_port: Embedding service port (default 28080 per DEC-004)
        monitoring_host: Monitoring API hostname
        monitoring_port: Monitoring API port (default 28000)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format (json for production, text for development)
        collection_size_warning: Warning threshold for collection size
        collection_size_critical: Critical threshold for collection size
        install_dir: Installation directory for config/data files
        queue_path: Path to file-based retry queue for failed operations
        session_log_path: Path to session logs
        jira_instance_url: Jira Cloud instance URL (e.g., https://company.atlassian.net)
        jira_email: Jira account email for Basic Auth
        jira_api_token: Jira API token (stored as SecretStr for security)
        jira_projects: List of Jira project keys to sync
        jira_sync_enabled: Enable automatic Jira synchronization
        jira_sync_delay_ms: Delay between Jira API requests for rate limiting
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # Use defaults instead of empty strings
        case_sensitive=False,  # SIMILARITY_THRESHOLD = similarity_threshold
        validate_default=True,  # Validate default values
        frozen=True,  # Immutable after creation (thread-safe)
        extra="ignore",  # Allow extra env vars (STREAMLIT_PORT, PLATFORM, etc.)
    )

    # Core thresholds (FR42)
    similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for retrieval (0.0-1.0). Lower = more results, potentially less relevant.",
    )

    dedup_threshold: float = Field(
        default=0.95,
        ge=0.80,
        le=0.99,
        description="Similarity threshold for deduplication (0.80-0.99). Higher = stricter dedup, fewer similar memories stored.",
    )

    max_retrievals: int = Field(
        default=5, ge=1, le=50, description="Maximum memories to retrieve per session"
    )

    # Token budget increased from 2000 to 4000 per BP-039 Section 3:
    # "Target 50% context window utilization" - higher budget enables richer context injection
    # for complex sessions. Can increase to 6000 if needed (TECH-DEBT-116).
    token_budget: int = Field(
        default=4000,
        ge=100,
        le=100000,
        description="Token budget for context injection. Controls how much context is sent to Claude.",
    )

    # Search performance tuning (TECH-DEBT-066)
    hnsw_ef_fast: int = Field(
        default=64,
        ge=16,
        le=512,
        description="HNSW ef parameter for trigger mode (speed priority). Lower = faster search.",
    )

    hnsw_ef_accurate: int = Field(
        default=128,
        ge=16,
        le=512,
        description="HNSW ef parameter for user search mode (accuracy priority). Higher = more accurate.",
    )

    # Service configuration
    qdrant_host: str = Field(default="localhost", description="Qdrant server hostname")

    qdrant_port: int = Field(
        default=26350,
        ge=1024,
        le=65535,
        description="Qdrant server port (Story 1.1: 26350 to avoid conflicts)",
    )

    qdrant_api_key: str | None = Field(
        default=None, description="Optional API key for Qdrant authentication (BP-040)"
    )

    qdrant_use_https: bool = Field(
        default=False,
        description="Use HTTPS for Qdrant connections (BP-040: required for production with API keys)",
    )

    qdrant_timeout: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Qdrant client timeout in seconds (TASK-023: increased from 10 to 30 for index creation under load)",
    )

    embedding_host: str = Field(
        default="localhost", description="Embedding service hostname"
    )

    embedding_port: int = Field(
        default=28080,
        ge=1024,
        le=65535,
        description="Embedding service port (DEC-004: 28080 to avoid conflicts)",
    )

    monitoring_host: str = Field(
        default="localhost", description="Monitoring API hostname"
    )

    monitoring_port: int = Field(
        default=28000,
        ge=1024,
        le=65535,
        description="Monitoring API port for health checks and metrics",
    )

    embedding_dimension: int = Field(
        default=768,
        ge=128,
        le=4096,
        description="Embedding vector dimension (default 768 for jina-embeddings-v2-base-en)",
    )

    # Logging & Monitoring
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    log_format: str = Field(
        default="json",
        pattern="^(json|text)$",
        description="Log format: json (production), text (development)",
    )

    collection_size_warning: int = Field(
        default=10000, ge=100, description="Collection size warning threshold"
    )

    collection_size_critical: int = Field(
        default=50000, ge=1000, description="Collection size critical threshold"
    )

    # Paths
    install_dir: Path = Field(
        default_factory=lambda: Path.home() / ".ai-memory",
        description="Installation directory",
    )

    queue_path: Path = Field(
        default_factory=lambda: Path.home() / ".ai-memory" / "pending_queue.jsonl",
        description="Queue file for pending operations",
    )

    session_log_path: Path = Field(
        default_factory=lambda: Path.home() / ".ai-memory" / "sessions.jsonl",
        description="Session logs",
    )

    # Jira Cloud Integration (PLAN-004 Phase 1)
    jira_instance_url: str = Field(
        default="",
        description="Jira Cloud instance URL (e.g., https://company.atlassian.net)",
    )

    jira_email: str = Field(
        default="",
        description="Jira account email for Basic Auth",
    )

    jira_api_token: SecretStr = Field(
        default=SecretStr(""),
        description="Jira API token for authentication (stored securely)",
    )

    jira_projects: list[str] = Field(
        default_factory=list,
        description="List of Jira project keys to sync (e.g., ['PROJ', 'DEV'])",
    )

    jira_sync_enabled: bool = Field(
        default=False,
        description="Enable automatic Jira synchronization",
    )

    jira_sync_delay_ms: int = Field(
        default=100,
        ge=0,
        le=5000,
        description="Delay between Jira API requests in milliseconds (rate limiting)",
    )

    # =========================================================================
    # v2.0.6 — GitHub Integration (SPEC-004, Tier 1: conditional required)
    # =========================================================================

    github_sync_enabled: bool = Field(
        default=False,
        description="Enable GitHub sync integration",
    )
    github_token: SecretStr = Field(
        default=SecretStr(""),
        description="GitHub PAT for API access (fine-grained, minimum scopes: repo:read, issues:read, pull_requests:read)",
    )
    github_repo: str = Field(
        default="",
        description="Target repository (owner/repo). Auto-detected from .git/config.",
    )

    # --- GitHub Integration (Tier 2: defaults) ---
    github_sync_interval: int = Field(
        default=1800,
        ge=60,
        le=86400,
        description="Polling interval in seconds (default: 1800 = 30 min)",
    )
    github_branch: str = Field(
        default="main",
        description="Branch to sync code blobs from",
    )
    github_code_blob_enabled: bool = Field(
        default=True,
        description="Sync source code files from repository",
    )
    github_code_blob_max_size: int = Field(
        default=102400,
        ge=1024,
        le=1048576,
        description="Skip files larger than this (bytes, default: 102400 = 100KB)",
    )
    github_code_blob_exclude: str = Field(
        default="node_modules,*.min.js,.git,__pycache__,*.pyc,build,dist,*.egg-info",
        description="Comma-separated glob patterns to exclude from code blob sync",
    )

    # --- GitHub Sync Resilience (BUG-112) ---
    github_sync_total_timeout: int = Field(
        default=1800,
        ge=60,
        le=7200,
        description="Total timeout for code blob sync in service mode (seconds, default: 30 min)",
    )
    github_sync_install_timeout: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="Total timeout for code blob sync during install (seconds, default: 10 min)",
    )
    github_sync_per_file_timeout: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Per-file timeout covering fetch+chunk+embed+store (seconds, default: 60)",
    )
    github_sync_circuit_breaker_threshold: int = Field(
        default=5,
        ge=2,
        le=20,
        description="Consecutive file failures before circuit breaker opens",
    )
    github_sync_circuit_breaker_reset: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Seconds before circuit breaker transitions OPEN -> HALF_OPEN",
    )

    # =========================================================================
    # v2.0.6 — Decay Scoring (SPEC-001 Section 4.3)
    # =========================================================================

    # Tier 2 — defaults, user CAN override
    decay_enabled: bool = Field(
        default=True,
        description="Enable decay scoring",
    )

    decay_semantic_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for semantic similarity in fused score (0.0-1.0). Temporal weight = 1 - this.",
    )

    decay_half_life_code_patterns: int = Field(
        default=14,
        ge=1,
        description="Half-life in days for code-patterns collection decay",
    )

    decay_half_life_discussions: int = Field(
        default=21,
        ge=1,
        description="Half-life in days for discussions collection decay",
    )

    decay_half_life_conventions: int = Field(
        default=60,
        ge=1,
        description="Half-life in days for conventions collection decay",
    )

    decay_half_life_jira_data: int = Field(
        default=30,
        ge=1,
        description="Half-life in days for jira-data collection decay",
    )

    decay_min_score: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Minimum decay score floor. Reserved for Phase 3 — not enforced yet.",
    )

    # Tier 3 — hidden/advanced (not in .env.example uncommented)
    decay_type_overrides: str = Field(
        default="github_ci_result:7,agent_task:14,github_code_blob:14,github_commit:14,github_issue:30,github_pr:30,jira_issue:30,agent_memory:30,guideline:60,rule:60,agent_handoff:180,agent_insight:180",
        description="Per-type half-life overrides. Format: type:days,type:days,...",
    )

    # =========================================================================
    # v2.0.6 — Audit Trail (SPEC-002 Section 5.2)
    # =========================================================================

    audit_dir: Path = Field(
        default_factory=lambda: Path(".audit"),
        description="Project-local audit directory (gitignored). Created by install script.",
    )

    # =========================================================================
    # v2.0.6 — Automated Updates (SPEC-002 Section 5.3)
    # =========================================================================

    auto_update_enabled: bool = Field(
        default=True,
        description="Global kill switch for automated memory updates. When false: sync runs, no auto-corrections applied.",
    )

    # =========================================================================
    # v2.0.6 — Dual Embedding (SPEC-010)
    # =========================================================================

    embedding_model_dense_en: str = Field(
        default="jinaai/jina-embeddings-v2-base-en",
        description="Prose embedding model name (SDK-side display/logging only)",
    )

    embedding_model_dense_code: str = Field(
        default="jinaai/jina-embeddings-v2-base-code",
        description="Code embedding model name (SDK-side display/logging only)",
    )

    # =========================================================================
    # v2.0.6 — Security Scanning (SPEC-009)
    # =========================================================================

    security_scanning_enabled: bool = Field(
        default=True,
        description="Master toggle for scanning pipeline",
    )

    security_scanning_ner_enabled: bool = Field(
        default=True,
        description="Enable SpaCy NER layer (Layer 3). Set False if SpaCy not installed.",
    )

    security_block_on_secrets: bool = Field(
        default=True,
        description="Block content with detected secrets. If False, mask instead.",
    )

    security_scan_github_mode: str = Field(
        default="relaxed",
        description="Scan mode for GitHub content: 'relaxed' (PII only, skip detect-secrets), "
        "'strict' (full 3-layer scan), 'off' (no scanning for GitHub content).",
        pattern="^(relaxed|strict|off)$",
    )

    security_scan_session_mode: str = Field(
        default="relaxed",
        description="Scan mode for session content (user prompts, agent responses): "
        "'relaxed' (Layer 1 regex only, skip detect-secrets Layer 2), "
        "'strict' (full Layer 1+2 scan), 'off' (no scanning for session content).",
        pattern="^(relaxed|strict|off)$",
    )

    # =========================================================================
    # v2.0.6 — Progressive Context Injection (SPEC-012, AD-6)
    # =========================================================================

    # Tier 2 — defaults, user CAN override
    injection_enabled: bool = Field(
        default=True,
        description="Enable progressive context injection (Tier 1 + Tier 2)",
    )

    bootstrap_token_budget: int = Field(
        default=2500,
        ge=500,
        le=5000,
        description="Token budget for Tier 1 bootstrap injection (startup trigger)",
    )

    injection_confidence_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum best retrieval score to inject context (Tier 2). Below this, skip injection entirely.",
    )

    injection_budget_floor: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Minimum token budget for Tier 2 per-turn injection",
    )

    injection_budget_ceiling: int = Field(
        default=1500,
        ge=500,
        le=5000,
        description="Maximum token budget for Tier 2 per-turn injection",
    )

    # Tier 3 — hidden/advanced
    injection_quality_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for quality signal in adaptive budget computation",
    )

    injection_density_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight for density signal in adaptive budget computation",
    )

    injection_drift_weight: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Weight for topic drift signal in adaptive budget computation",
    )

    # =========================================================================
    # v2.0.6 — Encryption (SPEC-011)
    # =========================================================================

    secrets_backend: str = Field(
        default="env-file",
        pattern="^(sops-age|keyring|env-file)$",
        description="Secrets storage method (informational/diagnostic only). Indicates which secrets storage method was selected during install: sops-age (SOPS+age encryption), keyring (OS-level encryption), env-file (plaintext). This field does NOT control decryption behavior (handled by start.sh wrapper script). Used for logging, telemetry, and status reporting.",
    )

    # =========================================================================
    # v2.0.6 — Freshness Detection (SPEC-013 Section 6)
    # =========================================================================

    freshness_enabled: bool = Field(
        default=True,
        description="Enable freshness detection for code-patterns memories",
    )

    freshness_commit_threshold_aging: int = Field(
        default=3,
        ge=1,
        le=100,
        description=(
            "Commits touching a file since memory stored before "
            "classifying as 'aging'. Default: 3."
        ),
    )

    freshness_commit_threshold_stale: int = Field(
        default=10,
        ge=2,
        le=500,
        description=(
            "Commits touching a file since memory stored before "
            "classifying as 'stale'. Default: 10."
        ),
    )

    freshness_commit_threshold_expired: int = Field(
        default=25,
        ge=3,
        le=1000,
        description=(
            "Commits touching a file since memory stored before "
            "classifying as 'expired' (even if blob hash matches). "
            "Default: 25."
        ),
    )

    # =========================================================================
    # v2.0.6 — Parzival Session Agent (SPEC-015)
    # =========================================================================

    parzival_enabled: bool = Field(
        default=False,
        description="Enable Parzival session agent. Set by installer when user opts in.",
    )

    parzival_user_name: str = Field(
        default="Developer",
        description="User's display name for Parzival greeting and handoffs.",
    )

    parzival_language: str = Field(
        default="English",
        description="Parzival communication language.",
    )

    parzival_doc_language: str = Field(
        default="English",
        description="Language for Parzival-generated documents (handoffs, specs).",
    )

    parzival_oversight_folder: str = Field(
        default="oversight",
        description="Project-relative path to oversight directory. Created by installer.",
    )

    parzival_handoff_retention: int = Field(
        default=10,
        ge=1,
        description="Number of recent handoff files to keep in oversight/session-logs/.",
    )

    # =========================================================================
    # v2.0.7 — Langfuse LLM Observability (SPEC-019, PLAN-008)
    # =========================================================================

    langfuse_enabled: bool = Field(
        default=False,
        env="LANGFUSE_ENABLED",
        description="Enable Langfuse LLM observability integration",
    )

    langfuse_public_key: str = Field(
        default="",
        env="LANGFUSE_PUBLIC_KEY",
        description="Langfuse project public key",
    )

    langfuse_secret_key: SecretStr = Field(
        default=SecretStr(""),
        env="LANGFUSE_SECRET_KEY",
        description="Langfuse project secret key",
    )

    langfuse_base_url: str = Field(
        default="http://localhost:23100",
        env="LANGFUSE_BASE_URL",
        description="Langfuse self-hosted instance URL",
    )

    langfuse_flush_interval: int = Field(
        default=5,
        ge=1,
        le=300,
        env="LANGFUSE_FLUSH_INTERVAL",
        description="Flush worker interval in seconds",
    )

    langfuse_trace_hooks: bool = Field(
        default=True,
        env="LANGFUSE_TRACE_HOOKS",
        description="Enable Tier 2 hook-level tracing",
    )

    langfuse_trace_sessions: bool = Field(
        default=True,
        env="LANGFUSE_TRACE_SESSIONS",
        description="Enable Tier 1 session-level tracing",
    )

    langfuse_retention_days: int = Field(
        default=90,
        ge=7,
        le=365,
        env="LANGFUSE_RETENTION_DAYS",
        description="ClickHouse trace retention in days (DEC-PLAN008-001)",
    )

    langfuse_trace_buffer_max_mb: int = Field(
        default=100,
        ge=10,
        le=1000,
        env="LANGFUSE_TRACE_BUFFER_MAX_MB",
        description="Maximum trace buffer size in MB before oldest-first eviction (DEC-PLAN008-004)",
    )

    @field_validator("decay_type_overrides", mode="before")
    @classmethod
    def parse_type_overrides(cls, v: str) -> str:
        """Validate format: type:days,type:days,..."""
        if not v:
            return v
        for pair in v.split(","):
            if not pair.strip():
                continue
            parts = pair.strip().split(":")
            if (
                len(parts) != 2
                or not parts[0].strip()
                or not parts[1].strip().isdigit()
            ):
                raise ValueError(
                    f"Invalid decay override format: '{pair}'. Expected 'type:days'."
                )
            days = int(parts[1].strip())
            if days < 1:
                raise ValueError(
                    f"Invalid decay override days: '{pair}'. Days must be >= 1."
                )
        return v

    @field_validator(
        "install_dir", "queue_path", "session_log_path", "audit_dir", mode="before"
    )
    @classmethod
    def expand_user_paths(cls, v):
        """Expand ~ and environment variables in paths."""
        if isinstance(v, str):
            return Path(os.path.expanduser(os.path.expandvars(v)))
        return v

    @field_validator("jira_projects", mode="before")
    @classmethod
    def parse_jira_projects(cls, v):
        """Parse comma-separated string into list for JIRA_PROJECTS env var."""
        if isinstance(v, str):
            if v.startswith("["):
                return v  # Already JSON format, let pydantic handle it
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @model_validator(mode="after")
    def validate_github_config(self) -> "MemoryConfig":
        """Validate GitHub config is complete when enabled."""
        if self.github_sync_enabled:
            if not self.github_token.get_secret_value():
                raise ValueError("GITHUB_TOKEN required when GITHUB_SYNC_ENABLED=true")
            if not self.github_repo:
                raise ValueError("GITHUB_REPO required when GITHUB_SYNC_ENABLED=true")
            if "/" not in self.github_repo:
                raise ValueError("GITHUB_REPO must be in owner/repo format")
        return self

    @model_validator(mode="after")
    def validate_injection_config(self) -> "MemoryConfig":
        """Validate injection config consistency."""
        if self.injection_budget_floor > self.injection_budget_ceiling:
            raise ValueError(
                f"INJECTION_BUDGET_FLOOR ({self.injection_budget_floor}) "
                f"must be <= INJECTION_BUDGET_CEILING ({self.injection_budget_ceiling})"
            )
        weight_sum = (
            self.injection_quality_weight
            + self.injection_density_weight
            + self.injection_drift_weight
        )
        if abs(weight_sum - 1.0) > 0.01:
            raise ValueError(
                f"Injection signal weights must sum to 1.0, got {weight_sum:.2f}"
            )
        return self

    @model_validator(mode="after")
    def validate_freshness_thresholds(self) -> "MemoryConfig":
        """Validate freshness thresholds are in ascending order.

        Always validates regardless of freshness_enabled state to
        prevent deferred errors when the feature is later enabled.
        """
        if not (
            self.freshness_commit_threshold_aging
            < self.freshness_commit_threshold_stale
            < self.freshness_commit_threshold_expired
        ):
            raise ValueError(
                "Freshness thresholds must be in ascending order: "
                f"aging ({self.freshness_commit_threshold_aging}) < "
                f"stale ({self.freshness_commit_threshold_stale}) < "
                f"expired ({self.freshness_commit_threshold_expired})"
            )
        return self

    @model_validator(mode="after")
    def validate_langfuse_config(self) -> "MemoryConfig":
        """Warn if Langfuse config is incomplete when enabled.

        Does NOT raise — keys may not be available at install time
        (Langfuse container starts after setup-collections runs).
        Runtime: langfuse_config.py handles missing keys gracefully (BUG-132).
        """
        if self.langfuse_enabled and (
            not self.langfuse_public_key
            or not self.langfuse_secret_key.get_secret_value()
        ):
            logger.warning(
                "LANGFUSE_ENABLED=true but API keys not configured — "
                "Langfuse features will be unavailable until keys are set"
            )
        return self

    def get_qdrant_url(self) -> str:
        """Get full Qdrant URL for connections."""
        scheme = "https" if self.qdrant_use_https else "http"
        return f"{scheme}://{self.qdrant_host}:{self.qdrant_port}"

    def get_embedding_url(self) -> str:
        """Get full embedding service URL."""
        return f"http://{self.embedding_host}:{self.embedding_port}"

    def get_monitoring_url(self) -> str:
        """Get full monitoring API URL."""
        return f"http://{self.monitoring_host}:{self.monitoring_port}"

    def get_decay_type_overrides(self) -> dict[str, int]:
        """Parse decay_type_overrides string into dict.

        Returns:
            Mapping of content type name to half-life in days.
        """
        if not self.decay_type_overrides:
            return {}
        result = {}
        for pair in self.decay_type_overrides.split(","):
            if not pair.strip():
                continue
            type_name, days = pair.strip().split(":")
            result[type_name.strip()] = int(days.strip())
        return result


# Agent configuration - SINGLE SOURCE OF TRUTH (CR-4.27)
# Consolidates agent names (previously duplicated in models.py) with token budgets
# Higher budgets for agents that need more context (architects, analysts)
# Lower budgets for focused agents (scrum-master, qa)
AGENTS = {
    "architect": {"budget": 1500},
    "analyst": {"budget": 1200},
    "pm": {"budget": 1200},
    "developer": {"budget": 1200},
    "dev": {"budget": 1200},
    "solo-dev": {"budget": 1500},
    "quick-flow-solo-dev": {"budget": 1500},
    "ux-designer": {"budget": 1000},
    "qa": {"budget": 1000},
    "tea": {"budget": 1000},
    "code-review": {"budget": 1200},
    "code-reviewer": {"budget": 1200},
    "scrum-master": {"budget": 800},
    "sm": {"budget": 800},
    "tech-writer": {"budget": 800},
    "default": {"budget": 1000},
}

# Valid agent names for validation (exported for models.py)
VALID_AGENTS = [k for k in AGENTS if k != "default"]

# Backward compatibility - deprecated, use AGENTS dict directly
AGENT_TOKEN_BUDGETS = {k: v["budget"] for k, v in AGENTS.items()}


@dataclass
class ProjectSyncConfig:
    """Per-project sync configuration loaded from projects.d/ YAML."""

    project_id: str
    source_directory: str | None = None
    github_repo: str | None = None
    github_branch: str = "main"
    github_enabled: bool = True
    jira_enabled: bool = False
    jira_instance_url: str | None = None
    jira_projects: list[str] = dataclass_field(default_factory=list)


def discover_projects(config_dir: Path | None = None) -> dict[str, ProjectSyncConfig]:
    """Scan projects.d/ for per-project YAML configs.

    Resolution order for config_dir:
    1. Explicit ``config_dir`` argument (used in tests and CLI).
    2. ``AI_MEMORY_PROJECTS_DIR`` environment variable (set by Docker so the
       container-mounted path ``/config/projects.d`` is found correctly, since
       ``Path.home()`` inside the container is NOT ``/config``).
    3. ``~/.ai-memory/config/projects.d`` — host default.

    Falls back to legacy GITHUB_REPO env var if the resolved directory yields
    no valid configs.
    """
    import yaml

    if config_dir is None:
        env_dir = os.environ.get("AI_MEMORY_PROJECTS_DIR")
        if env_dir:
            config_dir = Path(env_dir)
        else:
            config_dir = Path.home() / ".ai-memory" / "config" / "projects.d"

    projects: dict[str, ProjectSyncConfig] = {}

    if config_dir.is_dir():
        for path in sorted(config_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text())
                if not raw or not raw.get("project_id"):
                    logger.warning("Skipping %s: missing project_id", path.name)
                    continue
                github = raw.get("github", {})
                jira = raw.get("jira", {})
                # Coerce jira.projects to list — a scalar YAML string
                # ("projects: PROJ") arrives as str, not list.
                jira_proj_raw = jira.get("projects", [])
                if isinstance(jira_proj_raw, str):
                    jira_proj_raw = [jira_proj_raw] if jira_proj_raw else []
                projects[raw["project_id"]] = ProjectSyncConfig(
                    project_id=raw["project_id"],
                    source_directory=raw.get("source_directory"),
                    github_repo=github.get("repo"),
                    github_branch=github.get("branch", "main"),
                    github_enabled=github.get("enabled", True),
                    jira_enabled=jira.get("enabled", False),
                    jira_instance_url=jira.get("instance_url"),
                    jira_projects=jira_proj_raw,
                )
            except (yaml.YAMLError, KeyError, TypeError, ValueError) as e:
                logger.warning("Skipping malformed config %s: %s", path.name, e)
            except OSError as e:
                logger.error("Cannot read config %s: %s", path.name, e)

    if not projects:
        legacy_repo = os.environ.get("GITHUB_REPO")
        if legacy_repo:
            logger.warning(
                "Using legacy GITHUB_REPO env var. Migrate to projects.d/. See: docs/multi-project.md"
            )
            projects[legacy_repo] = ProjectSyncConfig(
                project_id=legacy_repo,
                github_repo=legacy_repo,
            )

    return projects


def get_agent_token_budget(agent_name: str) -> int:
    """Get token budget for an agent.

    Args:
        agent_name: Agent identifier (e.g., "architect", "dev")

    Returns:
        Token budget for the agent, or default if not found.
    """
    # Normalize: lowercase, strip whitespace
    normalized = agent_name.lower().strip() if agent_name else "default"
    agent_config = AGENTS.get(normalized, AGENTS["default"])
    return agent_config["budget"]


# Module-level singleton with lru_cache for thread-safety
@lru_cache(maxsize=1)
def get_config() -> MemoryConfig:
    """Get global configuration singleton.

    First call loads from environment + .env file, subsequent calls return cached instance.
    This ensures consistent configuration across all modules.

    Uses lru_cache for thread-safe singleton pattern (2026 best practice).

    Returns:
        MemoryConfig singleton instance.

    Raises:
        ValidationError: If configuration values are invalid.

    Example:
        >>> config = get_config()
        >>> config.qdrant_port
        26350
        >>> config2 = get_config()
        >>> config is config2  # Same instance
        True
    """
    return MemoryConfig()


def reset_config() -> None:
    """Reset configuration singleton for testing.

    This function clears the cached configuration, allowing tests to
    verify behavior with different environment variable configurations.

    Warning:
        Only use in test code. Production code should not reset config.

    Example:
        >>> reset_config()
        >>> os.environ["QDRANT_PORT"] = "26360"
        >>> config = get_config()
        >>> config.qdrant_port
        26360
        >>> reset_config()  # Clean up after test
    """
    get_config.cache_clear()
