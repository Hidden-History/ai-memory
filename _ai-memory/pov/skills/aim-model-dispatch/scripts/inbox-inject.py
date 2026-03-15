#!/usr/bin/env python3
"""inbox-inject.py — Inject a message into a Claude Code teammate inbox.

Usage:
    python3 inbox-inject.py --inbox PATH --from NAME --message TEXT [--color COLOR]
"""
import argparse
import json
import fcntl
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

def main():
    parser = argparse.ArgumentParser(description="Inject message into Claude Code inbox")
    parser.add_argument("--inbox", required=True, help="Path to inbox JSON file")
    parser.add_argument("--from", dest="sender", required=True, help="Sender name")
    parser.add_argument("--message", required=True, help="Message text")
    parser.add_argument("--color", default="blue", help="Message color (default: blue)")
    args = parser.parse_args()

    # Validate color against allowlist
    VALID_COLORS = {"blue", "green", "orange", "purple", "red", "yellow"}
    if args.color not in VALID_COLORS:
        parser.error(f"Invalid color. Must be one of: {', '.join(sorted(VALID_COLORS))}")

    # Expand and validate inbox path first (before length checks that need inbox_path)
    inbox_path = os.path.expanduser(args.inbox)

    # Length limits for security
    MAX_MESSAGE_LEN = 100 * 1024  # 100KB
    MAX_SENDER_LEN = 100  # 100 chars
    MAX_INBOX_SIZE = 10 * 1024 * 1024  # 10MB

    if len(args.message) > MAX_MESSAGE_LEN:
        parser.error(f"Message exceeds maximum length of {MAX_MESSAGE_LEN} bytes")
    if len(args.sender) > MAX_SENDER_LEN:
        parser.error(f"Sender name exceeds maximum length of {MAX_SENDER_LEN} characters")
    if not re.match(r'^[a-zA-Z0-9_@.-]+$', args.sender):
        parser.error("Sender name contains invalid characters. Use only letters, numbers, hyphens, underscores, @, and dots.")

    # Check inbox file size (prevent DoS via huge file) - after expanduser
    if os.path.exists(inbox_path):
        if os.path.getsize(inbox_path) > MAX_INBOX_SIZE:
            parser.error(f"Inbox file exceeds maximum size of {MAX_INBOX_SIZE} bytes")

    # Require .json extension
    if not inbox_path.endswith(".json"):
        parser.error("Inbox path must have .json extension")

    # Restrict to ~/.claude/teams/ only
    inbox_path_real = os.path.realpath(inbox_path)
    allowed_base = os.path.realpath(os.path.expanduser("~/.claude/teams/"))
    if not os.path.normpath(inbox_path_real).startswith(os.path.normpath(allowed_base)):
        parser.error("Inbox must be under ~/.claude/teams/")

    # Path traversal prevention via real path check
    if os.path.normpath(inbox_path) != os.path.normpath(inbox_path_real):
        parser.error("Symbolic link in path not allowed")

    inbox_dir = os.path.dirname(inbox_path_real)

    # Ensure inbox directory exists
    os.makedirs(inbox_dir, exist_ok=True)

    # Use a lockfile to serialize the entire read-modify-write cycle
    lock_path = inbox_path + ".lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    except FileExistsError:
        # Lockfile exists - check if it's a symlink (attack vector)
        if os.path.islink(lock_path):
            parser.error("Lockfile is a symlink - possible attack")
        # Open with O_NOFOLLOW to prevent symlink swap between check and open
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        # Read existing inbox
        messages = []
        if os.path.exists(inbox_path):
            try:
                with open(inbox_path, "r") as f:
                    content = f.read()
                if content.strip():
                    messages = json.loads(content)
            except (json.JSONDecodeError, IOError):
                messages = []

        # Append new message
        new_msg = {
            "from": args.sender,
            "text": args.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False,
            "color": args.color,
        }
        messages.append(new_msg)

        # Write atomically: mkstemp in same dir (required for os.replace on same fs)
        fd, tmp_path = tempfile.mkstemp(dir=inbox_dir, prefix=".inbox-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(messages, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, inbox_path)
        except Exception:
            os.unlink(tmp_path)
            raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)

    print(f"Injected message from '{args.sender}' into {inbox_path}")

if __name__ == "__main__":
    main()
