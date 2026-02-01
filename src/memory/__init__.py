"""AI Memory Module - Core memory storage and retrieval system.

Provides persistent semantic memory for Claude Code through:
- Configuration management with environment overrides
- Embedding service client (Nomic Embed Code)
- Qdrant vector store client wrapper
- Memory payload models and validation

Architecture Reference: architecture.md
Python Version: 3.10+ required
"""

# Logging Configuration (Story 6.2) - Configure before other imports
from .logging_config import StructuredFormatter, configure_logging

# Initialize structured logging on module import
configure_logging()

# Configuration
# Async SDK Wrapper (TECH-DEBT-035 Phase 2)
from .async_sdk_wrapper import (
    AsyncConversationCapture,
    AsyncSDKWrapper,
    QueueDepthExceededError,
    QueueTimeoutError,
    RateLimitQueue,
)
from .config import MemoryConfig, get_config, reset_config

# Service Clients
from .embeddings import EmbeddingClient, EmbeddingError

# Graceful Degradation (Story 1.7)
from .graceful import (
    EXIT_BLOCKING,
    EXIT_NON_BLOCKING,
    EXIT_SUCCESS,
    exit_graceful,
    exit_success,
    graceful_hook,
)
from .health import check_services, get_fallback_mode

# Models and Validation
from .models import EmbeddingStatus, MemoryPayload, MemoryType
from .qdrant_client import QdrantUnavailable, check_qdrant_health, get_qdrant_client
from .queue import (
    LOCK_TIMEOUT_SECONDS,
    LockedFileAppend,
    LockedReadModifyWrite,
    LockTimeoutError,
    MemoryQueue,
    QueueEntry,
    queue_operation,
)

# Search (Story 1.6)
from .search import MemorySearch

# Collection Statistics (Story 6.6)
from .stats import CollectionStats, get_collection_stats

# Storage (Story 1.5)
from .storage import MemoryStorage

# Template Models (Story 7.5)
from .template_models import (
    BestPracticeTemplate,
    TemplateListAdapter,
    load_templates_from_file,
)

# Logging Infrastructure (Story 6.2)
from .timing import timed_operation
from .validation import ValidationError, compute_content_hash, validate_payload
from .warnings import check_collection_thresholds

# Submodule exports for test mocking compatibility (Python 3.10+)
# These must be imported as modules (not just their contents) to support
# patch("memory.metrics.collection_size") style mocking
from . import metrics, stats, warnings

__all__ = [
    # Configuration (Story 1.4)
    "MemoryConfig",
    "get_config",
    "reset_config",
    # Embedding Client (Story 1.4)
    "EmbeddingClient",
    "EmbeddingError",
    # Qdrant Client (Story 1.4)
    "get_qdrant_client",
    "check_qdrant_health",
    "QdrantUnavailable",
    # Models (Story 1.3)
    "MemoryPayload",
    "MemoryType",
    "EmbeddingStatus",
    # Validation (Story 1.3)
    "ValidationError",
    "validate_payload",
    "compute_content_hash",
    # Template Models (Story 7.5)
    "BestPracticeTemplate",
    "TemplateListAdapter",
    "load_templates_from_file",
    # Storage (Story 1.5)
    "MemoryStorage",
    # Search (Story 1.6)
    "MemorySearch",
    # Async SDK Wrapper (TECH-DEBT-035 Phase 2)
    "AsyncSDKWrapper",
    "AsyncConversationCapture",
    "RateLimitQueue",
    "QueueTimeoutError",
    "QueueDepthExceededError",
    # Graceful Degradation (Story 1.7)
    "graceful_hook",
    "exit_success",
    "exit_graceful",
    "EXIT_SUCCESS",
    "EXIT_NON_BLOCKING",
    "EXIT_BLOCKING",
    "check_services",
    "get_fallback_mode",
    # Queue (Story 5.1)
    "MemoryQueue",
    "QueueEntry",
    "LockedFileAppend",
    "LockedReadModifyWrite",
    "LockTimeoutError",
    "LOCK_TIMEOUT_SECONDS",
    "queue_operation",
    # Logging (Story 6.2)
    "configure_logging",
    "StructuredFormatter",
    "timed_operation",
    # Collection Statistics (Story 6.6)
    "CollectionStats",
    "get_collection_stats",
    "check_collection_thresholds",
]
