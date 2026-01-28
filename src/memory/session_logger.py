#!/usr/bin/env python3
# src/memory/session_logger.py
"""Dedicated session log file handler (optional feature).

Writes session retrieval logs to JSONL file with rotation.
Enabled via SESSION_LOG_ENABLED=true environment variable.

Best Practices (2026):
- JSONL format: one JSON object per line
- RotatingFileHandler for size-based rotation (10MB)
- Gzip compression for archived logs
- 90-day retention policy for production
- TimedRotatingFileHandler alternative for daily rotation

References:
- https://pypi.org/project/python-json-logger/
- https://choudharycodes.hashnode.dev/python-log-rotation-a-comprehensive-guide-to-better-log-management
- https://docs.python.org/3/library/logging.handlers.html
"""

import os
import json
import logging
import gzip
import shutil
from datetime import datetime, UTC
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Session log configuration (defaults) - uses AI_MEMORY_INSTALL_DIR for multi-project support
INSTALL_DIR = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
SESSION_LOG_PATH = os.path.join(INSTALL_DIR, "logs", "sessions.jsonl")
SESSION_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB per file
SESSION_LOG_BACKUP_COUNT = 90  # Keep 90 rotated files (90 days if daily rotation)


class JsonFallbackFormatter(logging.Formatter):
    """Fallback JSON formatter that includes extra fields when python-json-logger unavailable.

    2026 best practice: Always include extra fields in structured logs.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with all extra fields included."""
        # Base fields
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }

        # Add extra fields (exclude standard LogRecord attributes)
        standard_attrs = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
            'taskName', 'message'
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith('_'):
                log_entry[key] = value

        return json.dumps(log_entry)


class GzipRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that compresses rotated logs with gzip.

    2026 best practice: Compress archived logs to save disk space.
    """

    def rotation_filename(self, default_name: str) -> str:
        """Add .gz extension to rotated files."""
        return default_name + ".gz"

    def rotate(self, source: str, dest: str):
        """Compress file during rotation using gzip."""
        if os.path.exists(source):
            with open(source, 'rb') as f_in:
                with gzip.open(dest, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(source)


def get_session_logger() -> Optional[logging.Logger]:
    """Get configured session logger or None if disabled.

    Returns:
        Logger instance if SESSION_LOG_ENABLED=true, else None
    """
    # Check environment variable at runtime (not import time)
    if os.getenv("SESSION_LOG_ENABLED", "false").lower() != "true":
        return None

    # Access module globals at runtime to support monkeypatching in tests
    import sys
    this_module = sys.modules[__name__]
    log_path = getattr(this_module, 'SESSION_LOG_PATH')
    max_bytes = getattr(this_module, 'SESSION_LOG_MAX_BYTES')
    backup_count = getattr(this_module, 'SESSION_LOG_BACKUP_COUNT')

    # Create log directory if needed
    log_dir = Path(log_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure logger
    session_logger = logging.getLogger("ai_memory.sessions")
    session_logger.setLevel(logging.INFO)
    session_logger.propagate = False  # Don't propagate to root logger

    # Check if handler already exists
    if session_logger.handlers:
        return session_logger

    # Add rotating file handler with gzip compression
    handler = GzipRotatingFileHandler(
        filename=log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )

    # Use JSON formatter (requires python-json-logger)
    try:
        from pythonjsonlogger.json import JsonFormatter
        formatter = JsonFormatter(
            fmt='%(timestamp)s %(levelname)s %(name)s %(message)s',
            timestamp=True
        )
        handler.setFormatter(formatter)
    except ImportError:
        # Fallback to custom formatter that includes extra fields
        handler.setFormatter(JsonFallbackFormatter())

    session_logger.addHandler(handler)
    return session_logger


def log_to_session_file(session_data: dict):
    """Append session retrieval to dedicated JSONL file.

    Args:
        session_data: Dict containing session retrieval information

    Example:
        log_to_session_file({
            "session_id": "sess-123",
            "project": "my-project",
            "results_count": 5,
            "duration_ms": 1234.56
        })
    """
    session_logger = get_session_logger()
    if session_logger:
        session_logger.info("session_retrieval", extra=session_data)
