"""Pattern extraction from code edits using Python AST and regex.

This module extracts meaningful patterns from code changes for semantic memory storage.
Uses Python stdlib only (ast, re, pathlib) for zero external dependencies.

Architecture Compliance:
- Functions: snake_case (extract_patterns, detect_framework)
- Constants: UPPER_SNAKE (LANGUAGE_MAP, HIGH_IMPORTANCE_INDICATORS)
- Structured logging with extra={} dict
- Graceful degradation (returns None on invalid input)
- Performance target: <100ms total extraction time

Story: 2.3 - Pattern Extraction Logic

TODO (v1.1+): Consider Tree-sitter hybrid approach for multi-language AST support.
Per 2026 best practices, ASTs excel at indexing/logic while Tree-sitter preserves
full syntax fidelity for retrieval. Current approach uses Python AST + regex fallback.
See: https://medium.com/@email2dineshkuppan/semantic-code-indexing-with-ast-and-tree-sitter-for-ai-agents-part-1-of-3-eb5237ba687a
"""

import ast
import logging
import re
from pathlib import Path

# Configure structured logging
logger = logging.getLogger(__name__)

# Language detection map (extensible to 15+ languages)
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
}

# High importance pattern indicators
HIGH_IMPORTANCE_INDICATORS = [
    "def __init__",
    "class ",
    "async def",
    "try:",
    "@dataclass",
    "@decorator",
    "CREATE TABLE",
    "migration",
    "auth",
    "security",
]

# High importance file path patterns
HIGH_IMPORTANCE_PATHS = ["auth", "security", "config", "model"]

# Low importance file path patterns
LOW_IMPORTANCE_PATHS = ["test", "example", "tmp"]


def extract_patterns(content: str, file_path: str) -> dict | None:
    """Extract meaningful patterns from code content.

    Main entry point for pattern extraction. Orchestrates language detection,
    framework detection, importance assessment, and tag extraction.

    Args:
        content: File content to analyze
        file_path: Path to the file being analyzed

    Returns:
        Dict with keys: content, domain, importance, tags, language, framework, file_path
        Returns None for invalid/empty/binary content

    Performance: Target <100ms total extraction time
    """
    logger.info(
        "pattern_extraction_started",
        extra={"file_path": file_path, "content_length": len(content)},
    )

    # Edge case: empty content
    if not content:
        logger.info(
            "invalid_content_skipped", extra={"reason": "empty", "content_length": 0}
        )
        return None

    # Edge case: content too short (< 10 chars)
    if len(content) < 10:
        logger.info(
            "invalid_content_skipped",
            extra={"reason": "too_short", "content_length": len(content)},
        )
        return None

    # Edge case: binary content detection
    if "\x00" in content:
        logger.info(
            "invalid_content_skipped",
            extra={"reason": "binary", "content_length": len(content)},
        )
        return None

    # Detect language from file extension
    language = detect_language(file_path)

    # Detect framework from content patterns
    framework = detect_framework(content, language)

    # Assess importance based on content and file path
    importance = assess_importance(content, file_path)

    # Extract tags from content and structure
    tags = extract_tags(content, language, framework)

    # Build enriched content with context header
    enriched_content = build_enriched_content(content, file_path, language, framework)

    # Python AST extraction for deeper structure analysis
    if language == "python":
        python_structure = extract_python_structure(content)
        if python_structure:
            # Add structural tags from AST
            if python_structure.get("has_classes"):
                tags.append("has_classes")
            if python_structure.get("has_async"):
                tags.append("has_async")

    logger.info(
        "pattern_extraction_complete",
        extra={
            "language": language,
            "framework": framework,
            "importance": importance,
            "tag_count": len(tags),
            "enriched_length": len(enriched_content),
        },
    )

    return {
        "content": enriched_content,
        "domain": language,  # Used for collection filtering in v1.1+
        "importance": importance,
        "tags": tags,
        "language": language,
        "framework": framework,
        "file_path": file_path,
    }


def detect_language(file_path: str) -> str:
    """Detect language from file extension.

    Args:
        file_path: Path to the file

    Returns:
        Language name from LANGUAGE_MAP, or "unknown" if not recognized
    """
    suffix = Path(file_path).suffix.lower()
    language = LANGUAGE_MAP.get(suffix, "unknown")

    logger.debug(
        "language_detected",
        extra={"language": language, "suffix": suffix, "file_path": file_path},
    )

    return language


def detect_framework(content: str, language: str) -> str:
    """Detect framework from content patterns.

    Uses regex patterns to identify common frameworks based on import statements
    and function calls.

    Args:
        content: File content to analyze
        language: Detected language

    Returns:
        Framework name or "general" if no specific framework detected
    """
    framework = "general"

    if language == "python":
        # Python frameworks (expanded regex for import variations)
        if re.search(r"(?:from\s+)?fastapi|import.*FastAPI", content):
            framework = "fastapi"
        elif re.search(r"(?:from\s+)?flask|import.*Flask", content):
            framework = "flask"
        elif re.search(r"from django", content):
            framework = "django"
        elif re.search(r"import pytest|from pytest", content):
            framework = "pytest"

    elif language in ("javascript", "typescript"):
        # JavaScript/TypeScript frameworks
        if re.search(r"from ['\"]react['\"]|import.*['\"]react['\"]", content):
            framework = "react"
        elif re.search(r"from ['\"]next['\"]|import.*['\"]next['\"]", content):
            framework = "nextjs"
        elif re.search(r"from ['\"]vue['\"]|import.*['\"]vue['\"]", content):
            framework = "vue"
        elif re.search(r"express\(", content):
            framework = "express"

    logger.debug(
        "framework_detected", extra={"framework": framework, "language": language}
    )

    return framework


def assess_importance(content: str, file_path: str) -> str:
    """Assess code importance based on content patterns and file path.

    Returns "high", "normal", or "low" based on heuristics.

    Args:
        content: File content to analyze
        file_path: Path to the file

    Returns:
        "high", "normal", or "low"
    """
    # Check high importance first (before low importance checks)
    if any(indicator in content for indicator in HIGH_IMPORTANCE_INDICATORS):
        return "high"

    if any(pattern in file_path.lower() for pattern in HIGH_IMPORTANCE_PATHS):
        return "high"

    # Low importance indicators
    if len(content) < 50:
        return "low"

    # Check number of lines (split gives count including last line if non-empty)
    if len(content.split("\n")) < 3:
        return "low"

    if any(pattern in file_path.lower() for pattern in LOW_IMPORTANCE_PATHS):
        return "low"

    # Default to normal
    return "normal"


def extract_tags(content: str, language: str, framework: str) -> list[str]:
    """Extract relevant tags from content and code structure.

    Args:
        content: File content to analyze
        language: Detected language
        framework: Detected framework

    Returns:
        List of tags (always includes language tag)
    """
    tags = [language]

    # Add framework tag if not "general"
    if framework != "general":
        tags.append(framework)

    # Pattern-based tags
    if "async" in content or "await" in content:
        tags.append("async")

    if "test" in content.lower() or "pytest" in content or "describe(" in content:
        tags.append("testing")

    if "api" in content.lower() or "endpoint" in content.lower():
        tags.append("api")

    if "config" in content.lower() or "settings" in content.lower():
        tags.append("config")

    if "try:" in content or "catch" in content or "except" in content:
        tags.append("error-handling")

    return tags


def build_enriched_content(
    content: str, file_path: str, language: str, framework: str
) -> str:
    """Build enriched content with context header for LLM retrieval.

    Format: [language/framework] file_path\n\ncontent

    Args:
        content: Original file content
        file_path: Path to the file
        language: Detected language
        framework: Detected framework

    Returns:
        Enriched content string with header
    """
    # Build framework part (omit if "general")
    framework_part = f"/{framework}" if framework != "general" else ""

    # Format: [language/framework] file_path\n\ncontent
    header = f"[{language}{framework_part}] {file_path}"
    enriched = f"{header}\n\n{content}"

    return enriched


def extract_python_structure(code: str) -> dict | None:
    """Extract code structure from Python using AST.

    Uses Python stdlib ast module for zero-dependency structure extraction.
    Falls back to regex on SyntaxError (malformed code).

    Args:
        code: Python source code

    Returns:
        Dict with keys: functions, classes, imports, has_classes, has_async
        Returns None on parse error (graceful degradation)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        logger.warning(
            "ast_parse_failed",
            extra={"language": "python", "error": str(e), "fallback": "regex"},
        )
        return None

    functions = []
    classes = []
    imports = []
    has_async = False

    for node in ast.walk(tree):
        # Extract function definitions
        if isinstance(node, ast.FunctionDef):
            func_info = {
                "name": node.name,
                "args": [arg.arg for arg in node.args.args],
                "decorators": [ast.unparse(d) for d in node.decorator_list],
                "returns": ast.unparse(node.returns) if node.returns else None,
            }
            functions.append(func_info)

        # Extract async function definitions
        elif isinstance(node, ast.AsyncFunctionDef):
            has_async = True
            func_info = {
                "name": node.name,
                "args": [arg.arg for arg in node.args.args],
                "decorators": [ast.unparse(d) for d in node.decorator_list],
                "returns": ast.unparse(node.returns) if node.returns else None,
                "async": True,
            }
            functions.append(func_info)

        # Extract class definitions
        elif isinstance(node, ast.ClassDef):
            class_info = {
                "name": node.name,
                "methods": [
                    m.name
                    for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                ],
                "bases": [
                    b.id if isinstance(b, ast.Name) else str(b) for b in node.bases
                ],
            }
            classes.append(class_info)

        # Extract import statements
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)

    return {
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "has_classes": len(classes) > 0,
        "has_async": has_async,
    }
