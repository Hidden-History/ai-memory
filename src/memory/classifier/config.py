"""Memory Classifier Configuration.

All configurable settings at the top for easy modification.
Environment variables override these defaults.

TECH-DEBT-069: LLM-based memory classification system.
"""

import logging
import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_memory.classifier.config")


def _load_env_file() -> None:
    """Load .env file from docker directory if it exists.

    Only loads variables that aren't already set in the environment.
    """
    # Try multiple possible locations for .env
    possible_paths = [
        Path(__file__).parent.parent.parent.parent
        / "docker"
        / ".env",  # src/memory/classifier -> project/docker/.env
        Path.home() / ".ai-memory" / ".env",
        Path("/app/docker/.env"),  # Docker container path
    ]

    for env_path in possible_paths:
        if env_path.exists():
            try:
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, _, value = line.partition("=")
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            # Only set if not already in environment
                            if key and value and key not in os.environ:
                                os.environ[key] = value
                logger.debug("env_file_loaded", extra={"path": str(env_path)})
                break
            except Exception as e:
                logger.debug(
                    "env_file_load_failed",
                    extra={"path": str(env_path), "error": str(e)},
                )


def _detect_ollama_url() -> str:
    """Auto-detect the correct Ollama URL based on environment.

    Detection order:
    1. OLLAMA_BASE_URL environment variable (if set)
    2. WSL: Use Windows host IP from default gateway (works for WSL2)
    3. Docker container: Use host.docker.internal
    4. Default: localhost

    Returns:
        Ollama base URL string
    """
    import socket

    # Check if explicitly set (not "auto")
    explicit_url = os.getenv("OLLAMA_BASE_URL", "").strip()
    if explicit_url and explicit_url.lower() != "auto":
        return explicit_url

    # Check if running in WSL (check BEFORE Docker since Docker Desktop also sets host.docker.internal in WSL)
    is_wsl = False
    try:
        with open("/proc/version") as f:
            is_wsl = "microsoft" in f.read().lower()
    except Exception:
        pass

    if is_wsl:
        # WSL detected - get Windows host IP from default gateway
        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Parse: "default via 172.18.48.1 dev eth0"
                parts = result.stdout.strip().split()
                if len(parts) >= 3 and parts[0] == "default" and parts[1] == "via":
                    windows_ip = parts[2]
                    url = f"http://{windows_ip}:11434"
                    logger.info(
                        "ollama_url_wsl_detected",
                        extra={"url": url, "windows_ip": windows_ip},
                    )
                    return url
        except Exception as e:
            logger.debug("wsl_ip_detection_failed", extra={"error": str(e)})

    # Check if running in Docker container (not WSL)
    # In a Docker container, /proc/1/cgroup contains docker/containerd paths
    is_docker = False
    try:
        with open("/proc/1/cgroup") as f:
            content = f.read()
            is_docker = "docker" in content or "containerd" in content
    except Exception:
        pass

    if is_docker:
        try:
            socket.gethostbyname("host.docker.internal")
            url = "http://host.docker.internal:11434"
            logger.info("ollama_url_docker_detected", extra={"url": url})
            return url
        except socket.gaierror:
            pass

    # Default to localhost
    return "http://localhost:11434"


# Load .env file before reading config
_load_env_file()


def _get_float_env(
    key: str, default: float, min_val: float = 0.0, max_val: float = 1.0
) -> float:
    """Safely get float from env var with validation.

    Args:
        key: Environment variable name
        default: Default value if not set or invalid
        min_val: Minimum acceptable value
        max_val: Maximum acceptable value

    Returns:
        Validated float value or default
    """
    raw = os.getenv(key, str(default))
    try:
        value = float(raw)
        if not min_val <= value <= max_val:
            logger.warning(
                "env_var_out_of_range",
                extra={
                    "key": key,
                    "value": value,
                    "min": min_val,
                    "max": max_val,
                    "using_default": default,
                },
            )
            return default
        return value
    except (ValueError, TypeError):
        logger.warning(
            "env_var_invalid_type",
            extra={"key": key, "raw_value": raw, "using_default": default},
        )
        return default


def _get_int_env(
    key: str, default: int, min_val: int = 0, max_val: int = 1000000
) -> int:
    """Safely get int from env var with validation.

    Args:
        key: Environment variable name
        default: Default value if not set or invalid
        min_val: Minimum acceptable value
        max_val: Maximum acceptable value

    Returns:
        Validated int value or default
    """
    raw = os.getenv(key, str(default))
    try:
        value = int(raw)
        if not min_val <= value <= max_val:
            logger.warning(
                "env_var_out_of_range",
                extra={
                    "key": key,
                    "value": value,
                    "min": min_val,
                    "max": max_val,
                    "using_default": default,
                },
            )
            return default
        return value
    except (ValueError, TypeError):
        logger.warning(
            "env_var_invalid_type",
            extra={"key": key, "raw_value": raw, "using_default": default},
        )
        return default


__all__ = [
    "ANTHROPIC_MODEL",
    "ASYNC_CLASSIFICATION",
    "CLASSIFIER_ENABLED",
    "CONFIDENCE_THRESHOLD",
    "COST_PER_MILLION",
    "FALLBACK_PROVIDERS",
    "LOW_PATTERNS",
    "MAX_INPUT_CHARS",
    "MAX_OUTPUT_TOKENS",
    "MIN_CONTENT_LENGTH",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_MODEL",
    "PRIMARY_PROVIDER",
    "QUEUE_ON_FAILURE",
    "RATE_LIMIT_PER_MINUTE",
    "RULE_CONFIDENCE_THRESHOLD",
    "RULE_PATTERNS",
    "SIGNIFICANCE_BEHAVIOR",
    "SKIP_PATTERNS",
    "SKIP_RECLASSIFICATION_TYPES",
    "TIMEOUT_SECONDS",
    "VALID_TYPES",
    "WARM_UP_ON_START",
    "Significance",
]

# =============================================================================
# FEATURE TOGGLES
# =============================================================================
CLASSIFIER_ENABLED = os.getenv("MEMORY_CLASSIFIER_ENABLED", "true").lower() == "true"
WARM_UP_ON_START = os.getenv("MEMORY_CLASSIFIER_WARM_UP", "true").lower() == "true"
ASYNC_CLASSIFICATION = os.getenv("MEMORY_CLASSIFIER_ASYNC", "true").lower() == "true"
QUEUE_ON_FAILURE = (
    os.getenv("MEMORY_CLASSIFIER_QUEUE_ON_FAILURE", "true").lower() == "true"
)

# =============================================================================
# PROVIDER CONFIGURATION
# =============================================================================
PRIMARY_PROVIDER = os.getenv("MEMORY_CLASSIFIER_PRIMARY_PROVIDER", "ollama")
FALLBACK_PROVIDERS = os.getenv(
    "MEMORY_CLASSIFIER_FALLBACK_PROVIDERS", "openrouter,claude"
).split(",")

# Provider-specific settings
OLLAMA_BASE_URL = _detect_ollama_url()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "sam860/LFM2:2.6b")

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-haiku")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

# =============================================================================
# CLASSIFICATION THRESHOLDS
# =============================================================================
CONFIDENCE_THRESHOLD = _get_float_env(
    "MEMORY_CLASSIFIER_CONFIDENCE_THRESHOLD", default=0.7, min_val=0.0, max_val=1.0
)
RULE_CONFIDENCE_THRESHOLD = _get_float_env(
    "MEMORY_CLASSIFIER_RULE_CONFIDENCE", default=0.85, min_val=0.0, max_val=1.0
)
MIN_CONTENT_LENGTH = _get_int_env(
    "MEMORY_CLASSIFIER_MIN_CONTENT_LENGTH", default=20, min_val=1, max_val=1000
)

# =============================================================================
# PERFORMANCE SETTINGS
# =============================================================================
TIMEOUT_SECONDS = _get_int_env(
    "MEMORY_CLASSIFIER_TIMEOUT", default=10, min_val=1, max_val=300
)
MAX_OUTPUT_TOKENS = _get_int_env(
    "MEMORY_CLASSIFIER_MAX_TOKENS", default=500, min_val=50, max_val=4000
)
MAX_INPUT_CHARS = _get_int_env(
    "MEMORY_CLASSIFIER_MAX_INPUT_CHARS", default=4000, min_val=100, max_val=100000
)
RATE_LIMIT_PER_MINUTE = _get_int_env(
    "MEMORY_CLASSIFIER_RATE_LIMIT", default=60, min_val=1, max_val=1000
)

# =============================================================================
# COST TRACKING (per 1M tokens in USD)
# =============================================================================
COST_PER_MILLION = {
    "ollama": {"input": 0.0, "output": 0.0},
    "openrouter": {"input": 0.25, "output": 1.25},
    "claude": {"input": 0.25, "output": 1.25},
    "openai": {"input": 0.15, "output": 0.60},  # gpt-4o-mini pricing
}

# =============================================================================
# SIGNIFICANCE LEVELS
# =============================================================================


class Significance(str, Enum):
    """Content significance levels for filtering."""

    HIGH = "high"  # Store permanently, full embedding
    MEDIUM = "medium"  # Store 90 days, full embedding
    LOW = "low"  # Store 30 days, no embedding cost
    SKIP = "skip"  # Don't store at all


SIGNIFICANCE_BEHAVIOR = {
    Significance.HIGH: {"store": True, "embed": True, "ttl_days": None},
    Significance.MEDIUM: {"store": True, "embed": True, "ttl_days": 90},
    Significance.LOW: {"store": True, "embed": False, "ttl_days": 30},
    Significance.SKIP: {"store": False, "embed": False, "ttl_days": None},
}

# Patterns that indicate SKIP significance (regex patterns)
SKIP_PATTERNS: list[str] = [
    r"^(ok|okay|yes|no|sure|thanks|thank you|got it|done|yep|nope)\.?$",
    r"^[\U0001F300-\U0001F9FF]+$",  # Emoji-only
]

# Patterns that indicate LOW significance
LOW_PATTERNS: list[str] = [
    r"^(sounds good|will do|on it|understood|acknowledged)",
]

# =============================================================================
# MEMORY TYPES BY COLLECTION
# =============================================================================
VALID_TYPES: dict[str, list[str]] = {
    "code-patterns": ["implementation", "error_fix", "refactor", "file_pattern"],
    "conventions": ["rule", "guideline", "port", "naming", "structure"],
    "discussions": [
        "decision",
        "session",
        "blocker",
        "preference",
        "user_message",
        "agent_response",
    ],
}

# Types that should NOT be reclassified
SKIP_RECLASSIFICATION_TYPES: list[str] = ["session", "error_fix"]

# =============================================================================
# RULE-BASED CLASSIFICATION PATTERNS
# =============================================================================
RULE_PATTERNS: dict[str, dict[str, Any]] = {
    "error_fix": {
        "patterns": [
            r"(?i)(fixed|resolved|solved).*(error|exception|bug|issue)",
            r"(?i)(error|exception|traceback).*\n.*fixed",
            r"(?i)the (fix|solution) (was|is)",
        ],
        "confidence": 0.90,
    },
    "port": {
        "patterns": [
            r"(?i)port\s*[:=]?\s*\d{4,5}",
            r"(?i)(runs?|listens?|available)\s+(on|at)\s+port\s+\d+",
        ],
        "confidence": 0.95,
    },
    "rule": {
        "patterns": [
            r"\b(MUST|NEVER|ALWAYS|REQUIRED|SHALL NOT)\b",  # Caps only
            r"(?i)^(rule|requirement):\s*",
        ],
        "confidence": 0.90,
    },
    "blocker": {
        "patterns": [
            r"(?i)(blocked|blocking|can'?t proceed|waiting on|stuck)",
            r"(?i)BLK-\d+",
        ],
        "confidence": 0.85,
    },
    "decision": {
        "patterns": [
            r"(?i)DEC-\d+",  # Explicit decision reference
        ],
        "confidence": 0.95,
    },
}
