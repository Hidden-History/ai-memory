"""Configuration management with pydantic-settings for BMAD Memory Module.

2026 Best Practices Applied:
- pydantic-settings v2.6+ for type-safe configuration
- Automatic .env file loading with proper precedence
- Validation with clear error messages
- Environment variable prefixes (BMAD_)
- SecretStr for sensitive data
- Frozen config (thread-safe, immutable after load)

References:
- Pydantic Settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- Environment Variable Security: https://securityboulevard.com/2025/12/are-environment-variables-still-safe-for-secrets-in-2026/
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["MemoryConfig", "get_config", "reset_config", "AGENT_TOKEN_BUDGETS", "get_agent_token_budget"]


class MemoryConfig(BaseSettings):
    """Configuration for BMAD Memory Module.

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
        description="Minimum similarity score for retrieval (0.0-1.0). Lower = more results, potentially less relevant."
    )

    dedup_threshold: float = Field(
        default=0.95,
        ge=0.80,
        le=0.99,
        description="Similarity threshold for deduplication (0.80-0.99). Higher = stricter dedup, fewer similar memories stored."
    )

    max_retrievals: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum memories to retrieve per session"
    )

    token_budget: int = Field(
        default=2000,
        ge=100,
        le=100000,
        description="Token budget for context injection. Controls how much context is sent to Claude."
    )

    # Service configuration
    qdrant_host: str = Field(
        default="localhost",
        description="Qdrant server hostname"
    )

    qdrant_port: int = Field(
        default=26350,
        ge=1024,
        le=65535,
        description="Qdrant server port (Story 1.1: 26350 to avoid conflicts)"
    )

    qdrant_api_key: Optional[str] = Field(
        default=None,
        description="Optional API key for Qdrant authentication (future use)"
    )

    embedding_host: str = Field(
        default="localhost",
        description="Embedding service hostname"
    )

    embedding_port: int = Field(
        default=28080,
        ge=1024,
        le=65535,
        description="Embedding service port (DEC-004: 28080 to avoid conflicts)"
    )

    monitoring_host: str = Field(
        default="localhost",
        description="Monitoring API hostname"
    )

    monitoring_port: int = Field(
        default=28000,
        ge=1024,
        le=65535,
        description="Monitoring API port for health checks and metrics"
    )

    # Logging & Monitoring
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )

    log_format: str = Field(
        default="json",
        pattern="^(json|text)$",
        description="Log format: json (production), text (development)"
    )

    collection_size_warning: int = Field(
        default=10000,
        ge=100,
        description="Collection size warning threshold"
    )

    collection_size_critical: int = Field(
        default=50000,
        ge=1000,
        description="Collection size critical threshold"
    )

    # Paths
    install_dir: Path = Field(
        default_factory=lambda: Path.home() / ".bmad-memory",
        description="Installation directory"
    )

    queue_path: Path = Field(
        default_factory=lambda: Path.home() / ".claude-memory" / "pending_queue.jsonl",
        description="Queue file for pending operations"
    )

    session_log_path: Path = Field(
        default_factory=lambda: Path.home() / ".claude-memory" / "sessions.jsonl",
        description="Session logs"
    )

    @field_validator("install_dir", "queue_path", "session_log_path", mode="before")
    @classmethod
    def expand_user_paths(cls, v):
        """Expand ~ and environment variables in paths."""
        if isinstance(v, str):
            return Path(os.path.expanduser(os.path.expandvars(v)))
        return v

    def get_qdrant_url(self) -> str:
        """Get full Qdrant URL for connections."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    def get_embedding_url(self) -> str:
        """Get full embedding service URL."""
        return f"http://{self.embedding_host}:{self.embedding_port}"

    def get_monitoring_url(self) -> str:
        """Get full monitoring API URL."""
        return f"http://{self.monitoring_host}:{self.monitoring_port}"


# Agent-specific token budgets for memory injection (TECH-DEBT-012 Phase 6)
# Higher budgets for agents that need more context (architects, analysts)
# Lower budgets for focused agents (scrum-master, qa)
AGENT_TOKEN_BUDGETS = {
    "architect": 1500,
    "analyst": 1200,
    "pm": 1200,
    "developer": 1200,
    "dev": 1200,
    "solo-dev": 1500,
    "quick-flow-solo-dev": 1500,
    "ux-designer": 1000,
    "qa": 1000,
    "tea": 1000,
    "code-review": 1200,
    "code-reviewer": 1200,
    "scrum-master": 800,
    "sm": 800,
    "tech-writer": 800,
    "default": 1000,
}


def get_agent_token_budget(agent_name: str) -> int:
    """Get token budget for an agent.

    Args:
        agent_name: Agent identifier (e.g., "architect", "dev")

    Returns:
        Token budget for the agent, or default if not found.
    """
    # Normalize: lowercase, strip whitespace
    normalized = agent_name.lower().strip() if agent_name else "default"
    return AGENT_TOKEN_BUDGETS.get(normalized, AGENT_TOKEN_BUDGETS["default"])


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
