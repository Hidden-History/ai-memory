#!/usr/bin/env python3
"""Example hook for graceful degradation testing.

This is a TEST FIXTURE, not a production hook.
Used by: tests/integration/test_graceful.py

Purpose:
- Demonstrates graceful degradation patterns
- Tests exit code behavior (0=success, 1=non-blocking, 2=blocking)
- Never exits with code 2 (blocking) per hook contract

Exit Codes:
- 0: Success (services available or graceful degradation worked)
- 1: Non-blocking error (logged but doesn't block Claude)
- 2: NEVER - blocking errors are forbidden for hooks
"""

import json
import os
import socket
import sys


def check_service_available(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a service is available."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, socket.error, ConnectionRefusedError, OSError):
        return False


def main():
    """Example hook main function demonstrating graceful degradation."""
    # Log start
    print("example_hook_started", file=sys.stderr)

    # Check Qdrant availability (optional - graceful if down)
    qdrant_port = int(os.environ.get("QDRANT_PORT", "6333"))
    qdrant_available = check_service_available("localhost", qdrant_port)

    if qdrant_available:
        print("example_hook_qdrant_available", file=sys.stderr)
    else:
        print("example_hook_qdrant_unavailable_graceful", file=sys.stderr)

    # Read stdin if provided (hook input)
    try:
        if not sys.stdin.isatty():
            input_data = sys.stdin.read()
            if input_data.strip():
                try:
                    parsed = json.loads(input_data)
                    print(
                        f"example_hook_input_parsed: {len(parsed)} keys",
                        file=sys.stderr,
                    )
                except json.JSONDecodeError:
                    print("example_hook_input_invalid_json", file=sys.stderr)
    except Exception as e:
        print(f"example_hook_stdin_error: {e}", file=sys.stderr)

    # Log completion
    print("example_hook_completed", file=sys.stderr)

    # Always exit 0 or 1, NEVER 2
    # Exit 0 = success, Exit 1 = non-blocking warning
    sys.exit(0)


if __name__ == "__main__":
    main()
