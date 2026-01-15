"""Structured logging configuration for BMAD Memory Module.

Implements AC 6.2.1 and AC 6.2.2:
- JSON structured logging with StructuredFormatter
- Logger hierarchy under bmad.memory namespace
- Environment variable control (BMAD_LOG_LEVEL, BMAD_LOG_FORMAT)

Research sources:
- Python Logging Best Practices 2026: https://www.carmatec.com/blog/python-logging-best-practices-complete-guide/
- Structured Logging Best Practices: https://uptrace.dev/glossary/structured-logging
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional


# Sensitive keys that should be redacted in log output (2026 security best practice)
# Per: https://www.apriorit.com/dev-blog/cybersecurity-logging-python
SENSITIVE_KEYS = {
    "password", "token", "secret", "apikey", "api_key",
    "authorization", "credential", "auth", "key", "bearer",
}


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter per AC 6.2.1.

    Outputs logs in JSON format with:
    - timestamp: UTC ISO 8601 format with 'Z' suffix
    - level: Log level name (INFO, ERROR, etc.)
    - logger: Logger name (bmad.memory hierarchy)
    - message: Log message
    - context: Extras dict merged from LogRecord attributes

    Security: Sensitive keys (password, token, api_key, etc.) are automatically
    redacted to prevent accidental credential leakage in logs.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: LogRecord to format

        Returns:
            JSON string with structured log data
        """
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extras (excluding standard LogRecord fields and private attributes)
        # Per AC 6.2.1: extras dict properly merged into context
        standard_fields = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "thread",
            "threadName",
            "exc_info",
            "exc_text",
            "stack_info",
            "taskName",
        }

        extras = {
            k: ("[REDACTED]" if k.lower() in SENSITIVE_KEYS else v)
            for k, v in record.__dict__.items()
            if k not in standard_fields and not k.startswith("_")
        }

        if extras:
            log_data["context"] = extras

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter for development (AC 6.2.5).

    Used when BMAD_LOG_FORMAT=text for easier local debugging.
    """

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def configure_logging(level: Optional[str] = None) -> None:
    """Configure structured logging for all bmad.memory loggers.

    Implements AC 6.2.1, AC 6.2.2, and AC 6.2.5.

    Args:
        level: Optional log level override. If not provided, uses BMAD_LOG_LEVEL
               environment variable (default: INFO).

    Environment Variables:
        BMAD_LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR). Default: INFO
        BMAD_LOG_FORMAT: Output format (json, text). Default: json
    """
    # Determine log level from parameter or environment variable
    if level is None:
        level = os.getenv("BMAD_LOG_LEVEL", "INFO")

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Determine formatter from environment variable
    log_format = os.getenv("BMAD_LOG_FORMAT", "json").lower()

    if log_format == "text":
        formatter = TextFormatter()
    else:
        formatter = StructuredFormatter()

    # Configure root logger for bmad.memory hierarchy
    # Per AC 6.2.2: logger names follow bmad.memory hierarchy
    logger = logging.getLogger("bmad.memory")
    logger.setLevel(log_level)

    # Idempotency check: only add handler if none exist (prevents memory leak)
    # Per: https://uptrace.dev/blog/python-logging - "Creating handlers inside loops
    # or forgetting to close file handlers are common mistakes"
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Per AC 6.2.2: prevent propagation to avoid duplicate logs
    logger.propagate = False
