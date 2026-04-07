#!/usr/bin/env python3
r"""Brittle line-reference detection script (TD-411).

Detects brittle inline line-number references in comments, docstrings,
and CHANGELOG that will become stale after nearby edits.

Patterns detected:
- (line \d+) - parenthetical line references
- at line \d+ - "at line N" references
- at lines \d+ - "at lines N" references (single or range)
- lines \d+-\d+ - range references
- filename.py:\d+ - file:line references in comments/docstrings

Exception: Cross-file references to stable anchors are acceptable
(e.g., "see models.py MemoryType enum" is fine, "see models.py:N" is not).

Always exits 0 (advisory, not blocking).

Usage:
    python scripts/check_brittle_refs.py [--path PATH]
    python scripts/check_brittle_refs.py --test  # Run self-test
"""

import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple


class Violation(NamedTuple):
    """A brittle reference violation."""

    file: str
    line: int
    pattern: str
    text: str


# Patterns to detect (in comments and docstrings only)
BRITTLE_PATTERNS = [
    # Parenthetical line references: (line N), (lines N-M)
    (re.compile(r"\(line\s+\d+\)"), "parenthetical 'line N'"),
    (re.compile(r"\(lines\s+\d+"), "parenthetical 'lines N'"),
    # "at line X" references
    (re.compile(r"\bat\s+line\s+\d+", re.IGNORECASE), "'at line N'"),
    # "at lines X" references
    (re.compile(r"\bat\s+lines\s+\d+", re.IGNORECASE), "'at lines N'"),
    # Range references: lines N-M
    (re.compile(r"\blines\s+\d+\s*-\s*\d+"), "'lines N-M' range"),
    # File:line references in text (not imports or tracebacks)
    (re.compile(r"\b\w+\.py:\d+\b"), "file:line reference"),
]

# Patterns to exclude (false positives)
EXCLUDE_PATTERNS = [
    # Standard import statements (not brittle)
    re.compile(r"^import\s+"),
    re.compile(r"^from\s+"),
    # Traceback patterns (not in comments/docstrings)
    re.compile(r"Traceback\s+\(most recent call last\)"),
    re.compile(r'File\s+"[^"]+",\s+line\s+\d+'),
    # URL patterns (not line refs)
    re.compile(r"https?://"),
]


def extract_comments_and_docstrings(source: str) -> list[tuple[int, str]]:
    """Extract comments and docstrings from Python source.

    Args:
        source: Python source code.

    Returns:
        List of (line_number, text) tuples for comments and docstrings.
    """
    results: list[tuple[int, str]] = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # If we can't parse, return empty (skip file)
        return results

    # Extract docstrings with correct line numbers
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstring = ast.get_docstring(node)
            if docstring:
                # Get actual docstring line: first statement in body (Expr with Constant)
                if node.body and isinstance(node.body[0], ast.Expr):
                    if isinstance(node.body[0].value, ast.Constant):
                        line = node.body[0].lineno
                    else:
                        line = node.lineno
                else:
                    line = node.lineno
                results.append((line, docstring))
        elif isinstance(node, ast.Module):
            docstring = ast.get_docstring(node)
            if docstring:
                # Module docstring is first statement
                if node.body and isinstance(node.body[0], ast.Expr):
                    if isinstance(node.body[0].value, ast.Constant):
                        line = node.body[0].lineno
                    else:
                        line = 1
                else:
                    line = 1
                results.append((line, docstring))

    # Extract comments (lines starting with #)
    for i, line in enumerate(source.split("\n"), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            # Remove the # prefix
            comment_text = stripped[1:].strip()
            results.append((i, comment_text))

    return results


def scan_python_file(filepath: Path) -> list[Violation]:
    """Scan a Python file for brittle references in comments and docstrings.

    Args:
        filepath: Path to the Python file.

    Returns:
        List of violations found.
    """
    violations: list[Violation] = []

    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return violations

    # Get comments and docstrings
    texts = extract_comments_and_docstrings(source)

    for line_num, text in texts:
        for pattern, pattern_name in BRITTLE_PATTERNS:
            for match in pattern.finditer(text):
                # Apply exclusion patterns (F4)
                if any(excl.search(match.group(0)) for excl in EXCLUDE_PATTERNS):
                    continue
                violations.append(
                    Violation(
                        file=str(filepath),
                        line=line_num,
                        pattern=pattern_name,
                        text=match.group(0),
                    )
                )

    return violations


def scan_markdown_file(filepath: Path) -> list[Violation]:
    """Scan a Markdown file for brittle references.

    Args:
        filepath: Path to the Markdown file.

    Returns:
        List of violations found.
    """
    violations: list[Violation] = []

    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return violations

    for i, line in enumerate(source.split("\n"), start=1):
        for pattern, pattern_name in BRITTLE_PATTERNS:
            for match in pattern.finditer(line):
                # F5: Check if match is inside a URL context (match-level, not line-level)
                if re.search(r"https?://\S*", match.group(0)):
                    continue
                # F4: Apply exclusion patterns
                if any(excl.search(match.group(0)) for excl in EXCLUDE_PATTERNS):
                    continue
                violations.append(
                    Violation(
                        file=str(filepath),
                        line=i,
                        pattern=pattern_name,
                        text=match.group(0),
                    )
                )

    return violations


def scan_directory(base_path: Path) -> list[Violation]:
    """Scan src/, tests/, and scripts/ directories for brittle references.

    Args:
        base_path: Base directory containing src/, tests/, and scripts/.

    Returns:
        List of all violations found.
    """
    violations: list[Violation] = []

    # Scan Python files in src/
    src_path = base_path / "src"
    if src_path.is_dir():
        for py_file in src_path.rglob("*.py"):
            violations.extend(scan_python_file(py_file))

    # Scan Python files in tests/
    tests_path = base_path / "tests"
    if tests_path.is_dir():
        for py_file in tests_path.rglob("*.py"):
            violations.extend(scan_python_file(py_file))

    # F9: Scan Python files in scripts/
    scripts_path = base_path / "scripts"
    if scripts_path.is_dir():
        for py_file in scripts_path.rglob("*.py"):
            violations.extend(scan_python_file(py_file))

    # Scan CHANGELOG.md
    changelog = base_path / "CHANGELOG.md"
    if changelog.is_file():
        violations.extend(scan_markdown_file(changelog))

    return violations


def main() -> int:
    """Main entry point. Returns 0 with count of violations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check for brittle line-number references"
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Base path to scan (default: current directory)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run self-test",
    )
    args = parser.parse_args()

    if args.test:
        return _run_self_test()

    base_path = args.path or Path.cwd()

    if not (base_path / "src").is_dir() and not (base_path / "tests").is_dir():
        print(
            f"WARNING: Neither src/ nor tests/ found in {base_path}",
            file=sys.stderr,
        )

    violations = scan_directory(base_path)

    if violations:
        print(f"Found {len(violations)} brittle reference(s):", file=sys.stderr)
        for v in violations:
            print(
                f"  {v.file}:{v.line} [{v.pattern}]: '{v.text}'",
                file=sys.stderr,
            )
        print(
            f"\nINFO: {len(violations)} violation(s) found. "
            "These are advisory warnings.",
            file=sys.stderr,
        )
    else:
        print("✓ No brittle references found", file=sys.stderr)

    return 0


def _run_self_test() -> int:
    """Run self-test with sample violations. Returns 0 always."""
    print("Running self-test...", file=sys.stderr)

    # Test pattern detection
    test_texts = [
        # (text, should_match_patterns)
        ("(line 42)", ["parenthetical 'line N'"]),
        ("at line 192", ["'at line N'"]),
        ("at lines 10-20", ["'at lines N'", "'lines N-M' range"]),
        ("models.py:38", ["file:line reference"]),
        ("# See models.py:192 for details", ["file:line reference"]),
        ("# This is fine - no line refs", []),
        ("def func(): pass", []),  # Code, not comment
    ]

    passed = 0
    total = len(test_texts)

    for text, expected_patterns in test_texts:
        found_patterns: list[str] = []
        for pattern, pattern_name in BRITTLE_PATTERNS:
            if pattern.search(text):
                found_patterns.append(pattern_name)

        # F8: Check for exact pattern match (set equality) to catch false positives
        matches_expected = set(found_patterns) == set(expected_patterns)
        status = "✓" if matches_expected else "✗"
        if matches_expected:
            passed += 1
        print(
            f"  {status} Test: '{text[:30]}{'...' if len(text) > 30 else ''}' "
            f"-> {found_patterns or 'none'}",
            file=sys.stderr,
        )

    print(
        f"\nSelf-test: {passed}/{total} passed",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
