#!/usr/bin/env python3
"""Commit message validation script (TD-410).

Advisory validation for commit messages:
- Subject line max 72 characters (warning if exceeded)
- Prefer Unicode arrows over ASCII '->' (warning)
- Conventional commit format check (warning)

Always exits 0 (advisory only, never blocks commits).
Can be wired into pre-commit or commit-msg hooks.

Usage:
    python scripts/validate_commit_msg.py <commit_msg_file>
    python scripts/validate_commit_msg.py --test  # Run self-test
"""

import re
import sys
from pathlib import Path

# Configuration
SUBJECT_MAX_LENGTH = 72
CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[^)]+)\))?"  # F10: Optional scope in parens
    r"!?"  # F10: Optional breaking change indicator
    r":\s+"
    r"(?P<description>.+)$"
)
ASCII_ARROW_PATTERN = re.compile(r"->")  # F7: Match arrow with or without spaces
UNICODE_ARROW = "→"


def read_commit_message(filepath: str) -> str:
    """Read commit message from file (standard git commit-msg hook interface).

    Args:
        filepath: Path to the commit message file.

    Returns:
        The commit message content.
    """
    return Path(filepath).read_text(encoding="utf-8")


def validate_commit_message(message: str) -> list[str]:
    """Validate commit message and return list of advisory warnings.

    Args:
        message: The commit message to validate.

    Returns:
        List of warning messages (empty if all checks pass).
    """
    warnings: list[str] = []

    # Extract subject line (first non-empty line, ignoring comments)
    lines = message.strip().split("\n")
    subject = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            subject = stripped
            break

    if not subject:
        warnings.append("WARNING: Empty commit message")
        return warnings

    # Check 1: Subject line length
    if len(subject) > SUBJECT_MAX_LENGTH:
        warnings.append(
            f"WARNING: Subject line exceeds {SUBJECT_MAX_LENGTH} characters "
            f"(got {len(subject)}): '{subject[:50]}...'"
        )

    # Check 2: ASCII arrow preference
    if ASCII_ARROW_PATTERN.search(subject):
        warnings.append(
            f"WARNING: Subject contains ASCII arrow '->'. "
            f"Prefer Unicode arrow '{UNICODE_ARROW}' for better typography."
        )

    # Check 3: Conventional commit format
    match = CONVENTIONAL_COMMIT_PATTERN.match(subject)
    if not match:
        warnings.append(
            f"WARNING: Subject does not follow conventional commit format. "
            f"Expected: 'type(scope): description' or 'type: description'. "
            f"Got: '{subject}'"
        )

    return warnings


def main() -> int:
    """Main entry point. Always returns 0 (advisory only)."""
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/validate_commit_msg.py <commit_msg_file>",
            file=sys.stderr,
        )
        print("       python scripts/validate_commit_msg.py --test", file=sys.stderr)
        return 0

    if sys.argv[1] == "--test":
        return _run_self_test()

    filepath = sys.argv[1]

    try:
        message = read_commit_message(filepath)
    except FileNotFoundError:
        print(f"WARNING: Commit message file not found: {filepath}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"WARNING: Error reading commit message: {e}", file=sys.stderr)
        return 0

    warnings = validate_commit_message(message)

    for warning in warnings:
        print(warning, file=sys.stderr)

    if warnings:
        print(
            f"\nINFO: {len(warnings)} advisory warning(s) issued. "
            "Commit will proceed.",
            file=sys.stderr,
        )
    else:
        print("✓ Commit message passes all checks", file=sys.stderr)

    return 0


def _run_self_test() -> int:
    """Run self-test with sample messages. Returns 0 always."""
    test_cases = [
        # (message, expected_warnings_count)
        ("feat: add new feature", 0),
        ("fix(core): resolve race condition", 0),
        ("docs: update README", 0),
        ("feat!: breaking change", 0),  # NEW-2: Breaking change ! indicator
        (
            "This is a very long subject line that definitely exceeds the seventy-two character limit",
            2,
        ),  # Long + non-conventional
        ("feat: add X -> Y transformation", 1),  # ASCII arrow
        ("not a conventional commit", 1),
        ("", 1),  # Empty
        (
            "feat: add X → Y transformation with a very long subject line that exceeds the limit",
            1,
        ),  # Long only (format OK)
    ]

    print("Running self-test...", file=sys.stderr)
    passed = 0

    for i, (msg, expected) in enumerate(test_cases):
        warnings = validate_commit_message(msg)
        actual = len(warnings)
        status = "✓" if actual == expected else "✗"
        if actual == expected:
            passed += 1
        print(
            f"  {status} Test {i + 1}: {actual} warnings (expected {expected})",
            file=sys.stderr,
        )
        if actual != expected:
            print(f"    Message: '{msg[:40]}...' ", file=sys.stderr)
            for w in warnings:
                print(f"    {w}", file=sys.stderr)

    print(
        f"\nSelf-test: {passed}/{len(test_cases)} passed",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
