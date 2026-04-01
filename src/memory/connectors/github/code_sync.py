"""Code blob sync for GitHub repository source files.

Ingests repository source code into github collection as github_code_blob
type with AST-aware chunking (Python) and context enrichment headers.
Delivers +70.1% Recall@5 over fixed-size chunking (BP-065).

Reference: PLAN-006 Section 3.3 (Code Blob Embedding Strategy)
"""

import ast
import asyncio
import atexit
import base64
import contextlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from qdrant_client import models

from memory.config import (
    GITHUB_CODE_BLOB_INCLUDE_MAX_SIZE_MULTIPLIER,
    MemoryConfig,
    get_config,
)

# LANGFUSE: Uses direct SDK (Path B). See LANGFUSE-INTEGRATION-SPEC.md §3.2, §7.3
# SDK VERSION: V4. Use get_client(), observe(), propagate_attributes().
# Do NOT use Langfuse() constructor, start_span(), start_generation(), or langfuse_context.

# Langfuse @observe() + propagate_attributes — conditional import (graceful degradation)
try:
    from langfuse import get_client as _langfuse_get_client
    from langfuse import observe, propagate_attributes
except ImportError:
    _langfuse_get_client = None  # type: ignore[assignment]

    def observe(**kwargs):
        def decorator(func):
            return func

        return decorator

    def propagate_attributes(**kwargs):
        """No-op context manager when Langfuse unavailable."""
        import contextlib

        return contextlib.nullcontext()


def _langfuse_shutdown():
    """Flush and shutdown Langfuse client on process exit (TD-246)."""
    if _langfuse_get_client is not None:
        try:
            client = _langfuse_get_client()
            if client:
                client.flush()
                client.shutdown()
        except Exception:
            pass


atexit.register(_langfuse_shutdown)

from memory.connectors.github.client import (
    GitHubClient,
    GitHubClientError,
)
from memory.connectors.github.schema import (
    GITHUB_COLLECTION,
    SOURCE_AUTHORITY_MAP,
    compute_content_hash,
)
from memory.extraction import detect_language as detect_language_from_path
from memory.models import MemoryType
from memory.qdrant_client import get_qdrant_client
from memory.storage import MemoryStorage

logger = logging.getLogger("ai_memory.github.code_sync")


@dataclass
class CodeSyncResult:
    """Result of a code blob sync operation."""

    files_synced: int = 0
    files_skipped: int = 0
    files_deleted: int = 0
    chunks_created: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    error_details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for metrics and logging."""
        return {
            "files_synced": self.files_synced,
            "files_skipped": self.files_skipped,
            "files_deleted": self.files_deleted,
            "chunks_created": self.chunks_created,
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 2),
        }


# ---------------------------------------------------------------------------
# 3.2  Language Detection
# ---------------------------------------------------------------------------

# Binary file extensions to always skip
BINARY_EXTENSIONS: set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".webp",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".obj",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".wav",
    ".sqlite",
    ".db",
    ".lock",
}


def detect_language(file_path: str) -> str:
    """Detect programming language from the shared extraction classifier.

    Args:
        file_path: File path in repository

    Returns:
        Language name string, or "unknown" if not recognized
    """
    return detect_language_from_path(file_path)


def is_binary_file(file_path: str) -> bool:
    """Check if file is binary based on extension.

    Args:
        file_path: File path in repository

    Returns:
        True if file extension indicates binary content
    """
    ext = PurePosixPath(file_path).suffix.lower()
    return ext in BINARY_EXTENSIONS


def _parse_filter_patterns(raw_patterns: str, *, setting_name: str) -> list[str]:
    """Parse comma-separated include/exclude patterns with basic validation."""
    patterns: list[str] = []
    for raw_pattern in raw_patterns.split(","):
        pattern = raw_pattern.strip()
        if not pattern:
            continue

        # F-09/F-11: Reject bare wildcards and too-short patterns
        # "*" → endswith("") always True; "*." → matches extensionless files
        if pattern.startswith("*") and len(pattern) < 3:
            logger.warning(
                "invalid_include_pattern_ignored",
                extra={
                    "context": {
                        "setting": setting_name,
                        "pattern": pattern,
                        "reason": "pattern too short — use e.g. *.py, *.yaml",
                    }
                },
            )
            continue

        if "/" in pattern and not pattern.startswith("*"):
            logger.warning(
                "invalid_include_pattern_ignored",
                extra={
                    "context": {
                        "setting": setting_name,
                        "pattern": pattern,
                        "reason": "path patterns with / not supported — use *.py or bare tokens like Makefile",
                    }
                },
            )
            continue

        patterns.append(pattern)
    return patterns


def _path_matches_pattern(file_path: str, pattern: str) -> bool:
    """Match patterns using the same two-mode rules as exclude filters."""
    if pattern.startswith("*"):
        return file_path.endswith(pattern[1:])
    return pattern in PurePosixPath(file_path).parts


def _matches_any_pattern(file_path: str, patterns: list[str]) -> bool:
    """Return True when file_path matches any configured filter pattern."""
    return any(_path_matches_pattern(file_path, pattern) for pattern in patterns)


def _resolve_include_max_size(config: MemoryConfig) -> int:
    """Return the effective hard ceiling for explicitly included files."""
    include_max_size = getattr(config, "github_code_blob_include_max_size", None)
    if include_max_size is None:
        return (
            config.github_code_blob_max_size
            * GITHUB_CODE_BLOB_INCLUDE_MAX_SIZE_MULTIPLIER
        )
    return include_max_size


# ---------------------------------------------------------------------------
# 3.3  Python Symbol Extraction
# ---------------------------------------------------------------------------


def extract_python_symbols(content: str) -> list[str]:
    """Extract class and function names from Python source using AST.

    Only extracts top-level definitions (module scope). Nested definitions
    are captured as part of their parent's chunk.

    Args:
        content: Python source code

    Returns:
        List of symbol names (e.g., ["MemoryStorage", "store_memory", "get_config"])
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        logger.debug("Failed to parse Python AST, returning empty symbols")
        return []

    symbols = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(node.name)

    return symbols


def extract_python_imports(content: str) -> list[str]:
    """Extract import statements from Python source using AST.

    Args:
        content: Python source code

    Returns:
        List of imported module names (e.g., ["qdrant_client", "httpx", "logging"])
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])

    return sorted(set(imports))


# ---------------------------------------------------------------------------
# 3.4  AST-Aware Chunking (Python)
# ---------------------------------------------------------------------------


@dataclass
class CodeChunk:
    """A chunk of code with metadata for embedding."""

    content: str  # The chunk content (with context header)
    raw_content: str  # Original code without header
    chunk_index: int  # Position in file
    total_chunks: int  # Total chunks for this file (set after all chunks created)
    symbol_name: str | None  # Class/function name if applicable
    start_line: int  # Starting line number in source
    end_line: int  # Ending line number in source


def chunk_python_ast(content: str, file_path: str) -> list[CodeChunk]:
    """Chunk Python source code using AST into function/class-level chunks.

    Strategy (BP-065):
    - Each top-level class or function = one chunk
    - Module-level code (imports, constants, top-level statements) = one chunk
    - Chunks > 1024 tokens get sub-chunked semantically
    - Each chunk gets a context enrichment header

    Args:
        content: Python source code
        file_path: File path for context header

    Returns:
        List of CodeChunk objects
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Fall back to semantic chunking on parse failure
        return _chunk_semantic(content, file_path, "python")

    lines = content.split("\n")
    imports = extract_python_imports(content)
    chunks: list[CodeChunk] = []

    # Collect top-level node ranges
    node_ranges: list[tuple[int, int, str | None]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.decorator_list:
                start = node.decorator_list[0].lineno - 1
            else:
                start = node.lineno - 1  # ast uses 1-based
            end = node.end_lineno or start + 1
            node_ranges.append((start, end, node.name))

    # Sort by start line
    node_ranges.sort(key=lambda x: x[0])

    # Module-level code: lines not covered by any class/function
    module_lines = _extract_module_level_lines(lines, node_ranges)
    if module_lines.strip():
        header = _build_context_header(file_path, "python", [], imports)
        chunks.append(
            CodeChunk(
                content=f"{header}\n{module_lines}",
                raw_content=module_lines,
                chunk_index=0,
                total_chunks=0,  # Updated after all chunks created
                symbol_name=None,
                start_line=1,
                end_line=len(lines),
            )
        )

    # Class/function chunks
    for start, end, name in node_ranges:
        chunk_lines = "\n".join(lines[start:end])
        symbols_in_scope = [name] if name else []

        # Top-level nodes only for MVP; parent class detection deferred to Phase 2
        scope_symbols = symbols_in_scope

        header = _build_context_header(file_path, "python", scope_symbols, imports)
        chunk_content = f"{header}\n{chunk_lines}"

        # Check token estimate (rough: 1 token ~ 4 chars for code)
        estimated_tokens = len(chunk_content) // 4
        if estimated_tokens > 1024:
            # Sub-chunk large functions/classes
            sub_chunks = _sub_chunk_large_block(
                chunk_content, file_path, name, imports, start
            )
            chunks.extend(sub_chunks)
        else:
            chunks.append(
                CodeChunk(
                    content=chunk_content,
                    raw_content=chunk_lines,
                    chunk_index=0,
                    total_chunks=0,
                    symbol_name=name,
                    start_line=start + 1,
                    end_line=end,
                )
            )

    # Set total_chunks and chunk_index
    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i
        chunk.total_chunks = len(chunks)

    return chunks


def _extract_module_level_lines(lines: list[str], node_ranges: list[tuple]) -> str:
    """Extract lines not covered by any class/function definition.

    Args:
        lines: All source lines
        node_ranges: List of (start, end, name) tuples for AST nodes

    Returns:
        Module-level code as string
    """
    covered = set()
    for start, end, _ in node_ranges:
        covered.update(range(start, end))

    module_lines = []
    for i, line in enumerate(lines):
        if i not in covered:
            module_lines.append(line)

    return "\n".join(module_lines).strip()


def _sub_chunk_large_block(
    content: str,
    file_path: str,
    symbol_name: str | None,
    imports: list[str],
    start_line: int,
) -> list[CodeChunk]:
    """Sub-chunk a code block that exceeds 1024 token estimate.

    Uses line-based splitting with 20% overlap (BP-065).
    Prepends a fresh context header to EVERY sub-chunk (AC 5.4).

    Args:
        content: The oversized chunk content (with header)
        file_path: File path for header regeneration
        symbol_name: Parent symbol name
        imports: Import list
        start_line: Starting line in original file

    Returns:
        List of sub-chunks
    """
    lines = content.split("\n")
    # Skip the header line from the input (it was prepended by caller)
    header_line = lines[0] if lines and lines[0].startswith("# ") else None
    code_lines = lines[1:] if header_line else lines

    # Target ~512 tokens per sub-chunk, ~4 chars/token for code
    target_chars = 512 * 4

    sub_chunks: list[CodeChunk] = []
    pos = 0
    while pos < len(code_lines):
        # Find end of chunk by character count
        char_count = 0
        end = pos
        while end < len(code_lines) and char_count < target_chars:
            char_count += len(code_lines[end]) + 1
            end += 1

        chunk_code = "\n".join(code_lines[pos:end])
        # Regenerate header for EVERY sub-chunk
        symbols = [symbol_name] if symbol_name else []
        header = _build_context_header(file_path, "python", symbols, imports)

        sub_chunks.append(
            CodeChunk(
                content=f"{header}\n{chunk_code}",
                raw_content=chunk_code,
                chunk_index=0,
                total_chunks=0,
                symbol_name=symbol_name,
                start_line=start_line + pos,
                end_line=start_line + end,
            )
        )

        # Advance with overlap (ensure forward progress to avoid infinite loop)
        chunk_size = end - pos
        if chunk_size <= 1:
            pos = end  # Single-line chunk: no overlap possible
        else:
            overlap_lines = max(1, int(chunk_size * 0.20))
            pos = end - overlap_lines

    return sub_chunks


# ---------------------------------------------------------------------------
# 3.5  Semantic Chunking (Non-Python)
# ---------------------------------------------------------------------------


def _chunk_semantic(content: str, file_path: str, language: str) -> list[CodeChunk]:
    """Chunk non-Python code using semantic (line-based) chunking.

    Parameters per Chunking-Strategy-V2 and BP-065:
    - Target: 512 tokens per chunk
    - Overlap: 20% for code
    - Minimum: 50 tokens (skip trivially small chunks)

    Args:
        content: Source code content
        file_path: File path for context header
        language: Detected language

    Returns:
        List of CodeChunk objects
    """
    # Rough token estimate: 1 token ~ 4 chars for code
    target_chars = 512 * 4
    min_chars = 50 * 4

    lines = content.split("\n")
    chunks: list[CodeChunk] = []
    pos = 0

    # Extract first 3 import-like lines for context header
    import_lines = _extract_import_lines(lines, language)

    while pos < len(lines):
        char_count = 0
        end = pos
        while end < len(lines) and char_count < target_chars:
            char_count += len(lines[end]) + 1
            end += 1

        chunk_text = "\n".join(lines[pos:end])

        # Skip trivially small trailing chunks
        if len(chunk_text) < min_chars and chunks:
            # Append to previous chunk instead
            prev = chunks[-1]
            chunks[-1] = CodeChunk(
                content=prev.content + "\n" + chunk_text,
                raw_content=prev.raw_content + "\n" + chunk_text,
                chunk_index=prev.chunk_index,
                total_chunks=prev.total_chunks,
                symbol_name=prev.symbol_name,
                start_line=prev.start_line,
                end_line=prev.end_line + (end - pos),
            )
            break

        header = _build_context_header(file_path, language, [], import_lines)
        chunks.append(
            CodeChunk(
                content=f"{header}\n{chunk_text}",
                raw_content=chunk_text,
                chunk_index=0,
                total_chunks=0,
                symbol_name=None,
                start_line=pos + 1,
                end_line=end,
            )
        )

        # Advance with overlap (ensure forward progress to avoid infinite loop)
        chunk_size = end - pos
        if chunk_size <= 1:
            pos = end  # Single-line chunk: no overlap possible
        else:
            overlap_lines = max(1, int(chunk_size * 0.20))
            pos = end - overlap_lines

    # Set indices
    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i
        chunk.total_chunks = len(chunks)

    return chunks


def _extract_import_lines(lines: list[str], language: str) -> list[str]:
    """Extract import/include statements for context header.

    Args:
        lines: Source code lines
        language: Programming language

    Returns:
        Up to 5 import module names
    """
    import_keywords = {
        "python": ("import ", "from "),
        "javascript": ("import ", "require(", "const "),
        "typescript": ("import ", "require("),
        "java": ("import ",),
        "go": ("import ",),
        "rust": ("use ", "extern crate "),
        "c": ("#include ",),
        "cpp": ("#include ",),
    }
    keywords = import_keywords.get(language, ("import ",))

    imports = []
    for line in lines[:50]:  # Only scan first 50 lines
        stripped = line.strip()
        if any(stripped.startswith(kw) for kw in keywords):
            # Extract module name (simplified)
            parts = stripped.split()
            if len(parts) >= 2:
                imports.append(parts[1].strip(";").strip("\"'").split(".")[0])
            if len(imports) >= 5:
                break

    return imports


# ---------------------------------------------------------------------------
# 3.6  Context Enrichment Header
# ---------------------------------------------------------------------------


def _build_context_header(
    file_path: str,
    language: str,
    symbols: list[str],
    imports: list[str],
) -> str:
    """Build context enrichment header prepended to each chunk.

    This header is the key to the +70.1% Recall@5 improvement (BP-065 S4.2).
    It bridges the NL/code semantic gap by providing scope context.

    Format:
        # File: src/memory/storage.py | Class: MemoryStorage | Imports: qdrant_client, httpx

    Args:
        file_path: File path in repository
        language: Detected language
        symbols: Class/function scope chain (e.g., ["MemoryStorage", "store_memory"])
        imports: Import module names

    Returns:
        Single-line context header string
    """
    parts = [f"File: {file_path}"]

    if symbols:
        # Build scope chain: Class: Foo | Method: bar
        if len(symbols) >= 2:
            parts.append(f"Class: {symbols[0]}")
            parts.append(f"Method: {symbols[1]}")
        elif len(symbols) == 1:
            parts.append(f"Symbol: {symbols[0]}")

    if imports:
        parts.append(f"Imports: {', '.join(imports[:5])}")

    parts.append(f"Language: {language}")

    return "# " + " | ".join(parts)


# ---------------------------------------------------------------------------
# 3.7  CodeBlobSync Class
# ---------------------------------------------------------------------------


class CodeBlobSync:
    """Syncs repository source files into github collection.

    Uses tree-based incremental sync: compares blob SHA from GitHub tree
    against stored blob_hash to detect changes. Only fetches and re-embeds
    changed files.

    Attributes:
        client: GitHubClient for API calls
        config: Memory configuration
        storage: MemoryStorage for store_memory() pipeline
    """

    def __init__(
        self,
        client: GitHubClient,
        config: MemoryConfig | None = None,
        repo: str | None = None,
        branch: str | None = None,
    ) -> None:
        """Initialize code blob sync.

        Args:
            client: Active GitHubClient instance (caller manages lifecycle)
            config: Memory configuration. Uses get_config() if None.
            repo: Repository in "owner/repo" format. Overrides config.github_repo.
            branch: Git branch to sync. Overrides config.github_branch.
        """
        self.client = client
        self.config = config or get_config()
        # BUG-251: Synthetic session ID for service contexts that lack CLAUDE_SESSION_ID
        os.environ.setdefault(
            "CLAUDE_SESSION_ID",
            f"github-code-sync-{datetime.now(timezone.utc).date().isoformat()}",
        )
        self.storage = MemoryStorage(self.config)
        self.qdrant = get_qdrant_client(self.config)
        self._group_id = repo or self.config.github_repo
        if not self._group_id:
            raise ValueError("No repo specified and GITHUB_REPO not configured")
        self._branch = branch or self.config.github_branch
        self._exclude_patterns = _parse_filter_patterns(
            getattr(self.config, "github_code_blob_exclude", "") or "",
            setting_name="github_code_blob_exclude",
        )
        self._include_patterns = _parse_filter_patterns(
            getattr(self.config, "github_code_blob_include", "") or "",
            setting_name="github_code_blob_include",
        )
        self._include_max_size = _resolve_include_max_size(self.config)

        # BUG-112: Circuit breaker for code blob sync resilience
        from memory.classifier.circuit_breaker import CircuitBreaker

        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.github_sync_circuit_breaker_threshold,
            reset_timeout=self.config.github_sync_circuit_breaker_reset,
        )

        # SEC-2: Security scanner to scan file content before chunking/storage
        if self.config.security_scanning_enabled:
            from memory.security_scanner import SecurityScanner

            self._scanner = SecurityScanner(
                enable_ner=self.config.security_scanning_ner_enabled
            )
        else:
            self._scanner = None

    @observe(name="github_code_sync")
    async def sync_code_blobs(
        self,
        batch_id: str,
        total_timeout: int | None = None,
    ) -> CodeSyncResult:
        """Sync code blobs from repository.

        Flow:
        1. Fetch file tree from GitHub
        2. Filter eligible files (size, patterns, binary)
        3. Compare blob_hash against stored versions
        4. Fetch, chunk, and store changed/new files (with per-file timeout)
        5. Detect and mark deleted files

        BUG-112: Added total_timeout, per-file timeout, circuit breaker, and
        progress logging to prevent indefinite hangs during code blob sync.

        Args:
            batch_id: Sync batch ID for versioning (BP-074)
            total_timeout: Total timeout in seconds. Defaults to config value.

        Returns:
            CodeSyncResult with file/chunk counts
        """
        try:
            with propagate_attributes(
                session_id="github_sync",
                user_id="system",
                metadata={"sync_type": "code_blobs"},
            ):
                start = time.monotonic()
                result = CodeSyncResult()
                if total_timeout is None:
                    total_timeout = self.config.github_sync_total_timeout
                per_file_timeout = self.config.github_sync_per_file_timeout

                logger.info(
                    "Starting code blob sync: branch=%s, batch=%s, total_timeout=%ds, per_file_timeout=%ds",
                    self._branch,
                    batch_id,
                    total_timeout,
                    per_file_timeout,
                )

                # Step 1: Fetch file tree
                try:
                    tree_entries = await self._walk_tree()
                except GitHubClientError as e:
                    logger.error("Failed to fetch file tree: %s", e)
                    result.errors += 1
                    result.error_details.append(f"get_tree: {e}")
                    result.duration_seconds = time.monotonic() - start
                    return result

                # Step 2: Build stored blob lookup map (BP-066 batch lookup)
                stored_map = await asyncio.to_thread(self._get_stored_blob_map)

                # Step 3: Pre-filter eligible files for accurate progress counts
                current_paths: set[str] = set()
                eligible_entries: list[tuple[dict, str | None]] = (
                    []
                )  # (entry, stored_hash)
                unchanged_paths: list[str] = []
                for entry in tree_entries:
                    file_path = entry["path"]
                    current_paths.add(file_path)

                    if not self._should_sync_file(entry):
                        result.files_skipped += 1
                        continue

                    stored_hash = stored_map.get(file_path)
                    if stored_hash == entry["sha"]:
                        unchanged_paths.append(file_path)
                        result.files_skipped += 1
                        continue

                    eligible_entries.append((entry, stored_hash))

                total_eligible = len(eligible_entries)
                logger.info(
                    "Code blob sync: %d eligible files to process (of %d total tree entries)",
                    total_eligible,
                    len(tree_entries),
                )

                # Step 4: Sync eligible files with bounded concurrency, timeouts, CB
                cb_provider = "code_blob_sync"  # Circuit breaker provider key
                file_concurrency = max(1, self.config.github_code_blob_file_concurrency)
                next_entry_index = 0
                completed_files = 0
                next_progress_log = 10
                pending_tasks: dict[
                    asyncio.Task[tuple[float, int | Exception]],
                    tuple[dict[str, Any], str | None],
                ] = {}

                def _remaining_files() -> int:
                    return total_eligible - completed_files

                total_timeout_recorded = False

                def _record_total_timeout(elapsed: float) -> None:
                    nonlocal total_timeout_recorded
                    if not total_timeout_recorded:
                        result.error_details.append(
                            f"total_timeout: stopped after {completed_files}/{total_eligible} files ({elapsed:.0f}s)"
                        )
                        total_timeout_recorded = True

                def _record_circuit_breaker_open() -> None:
                    result.error_details.append(
                        f"circuit_breaker_open: stopped after {completed_files}/{total_eligible} files"
                    )

                async def _sync_entry(
                    entry_pair: tuple[dict[str, Any], str | None],
                ) -> int:
                    entry, stored_hash = entry_pair
                    return await self._sync_file(entry, batch_id, stored_hash)

                async def _run_sync_entry(
                    entry_pair: tuple[dict[str, Any], str | None],
                ) -> tuple[float, int | Exception]:
                    try:
                        outcome = await asyncio.wait_for(
                            _sync_entry(entry_pair), timeout=per_file_timeout
                        )
                    except Exception as e:
                        return (time.monotonic(), e)
                    return (time.monotonic(), outcome)

                async def _cancel_pending(cancel_reason: str) -> None:
                    cancelled = len(pending_tasks)
                    for task in pending_tasks:
                        task.cancel()
                    if not pending_tasks:
                        return
                    await asyncio.gather(*pending_tasks, return_exceptions=True)
                    pending_tasks.clear()
                    logger.warning(
                        "Cancelled %d in-flight code blob task(s) %s",
                        cancelled,
                        cancel_reason,
                    )

                while next_entry_index < total_eligible or pending_tasks:
                    while (
                        next_entry_index < total_eligible
                        and len(pending_tasks) < file_concurrency
                    ):
                        elapsed = time.monotonic() - start
                        if elapsed >= total_timeout:
                            remaining = _remaining_files()
                            logger.warning(
                                "Code blob sync total timeout reached (%.0fs >= %ds). "
                                "Stopping with %d files remaining.",
                                elapsed,
                                total_timeout,
                                remaining,
                            )
                            await _cancel_pending("due to total timeout")
                            _record_total_timeout(elapsed)
                            next_entry_index = total_eligible
                            break

                        if not self._circuit_breaker.is_available(cb_provider):
                            remaining = _remaining_files()
                            logger.warning(
                                "Code blob sync circuit breaker OPEN after %d consecutive failures. "
                                "Stopping with %d files remaining.",
                                self._circuit_breaker.failure_threshold,
                                remaining,
                            )
                            await _cancel_pending("after circuit breaker opened")
                            _record_circuit_breaker_open()
                            next_entry_index = total_eligible
                            break

                        entry_pair = eligible_entries[next_entry_index]
                        task = asyncio.create_task(_run_sync_entry(entry_pair))
                        pending_tasks[task] = entry_pair
                        next_entry_index += 1

                    if not pending_tasks:
                        continue

                    remaining_total = total_timeout - (time.monotonic() - start)
                    if remaining_total <= 0:
                        await _cancel_pending("due to total timeout")
                        _record_total_timeout(time.monotonic() - start)
                        break

                    done, _ = await asyncio.wait(
                        set(pending_tasks),
                        timeout=remaining_total,
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if not done:
                        elapsed = time.monotonic() - start
                        remaining = _remaining_files()
                        logger.warning(
                            "Code blob sync total timeout reached (%.0fs >= %ds). "
                            "Stopping with %d files remaining.",
                            elapsed,
                            total_timeout,
                            remaining,
                        )
                        await _cancel_pending("due to total timeout")
                        _record_total_timeout(elapsed)
                        break

                    completed_outcomes: list[
                        tuple[float, dict[str, Any], int | Exception]
                    ] = []
                    for task in done:
                        entry, _ = pending_tasks.pop(task)
                        try:
                            finished_at, outcome = task.result()
                        except asyncio.CancelledError:
                            logger.warning("Cancelled sync for %s", entry["path"])
                            continue
                        completed_outcomes.append((finished_at, entry, outcome))

                    breaker_opened_in_cycle = False
                    for _, entry, outcome in sorted(
                        completed_outcomes, key=lambda item: item[0]
                    ):
                        file_path = entry["path"]
                        completed_files += 1
                        if isinstance(outcome, asyncio.TimeoutError):
                            logger.error(
                                "Per-file timeout (%ds) for %s",
                                per_file_timeout,
                                file_path,
                            )
                            result.errors += 1
                            result.error_details.append(
                                f"{file_path}: per_file_timeout ({per_file_timeout}s)"
                            )
                            self._circuit_breaker.record_failure(cb_provider, "timeout")
                            if not self._circuit_breaker.is_available(cb_provider):
                                breaker_opened_in_cycle = True
                        elif isinstance(outcome, Exception):
                            logger.error(
                                "Failed to sync file %s: %s", file_path, outcome
                            )
                            result.errors += 1
                            result.error_details.append(f"{file_path}: {outcome}")
                            self._circuit_breaker.record_failure(
                                cb_provider, type(outcome).__name__
                            )
                            if not self._circuit_breaker.is_available(cb_provider):
                                breaker_opened_in_cycle = True
                        else:
                            result.files_synced += 1
                            result.chunks_created += int(outcome)
                            if not breaker_opened_in_cycle:
                                self._circuit_breaker.record_success(cb_provider)

                    if (
                        completed_files >= next_progress_log
                        and completed_files < total_eligible
                    ):
                        logger.info(
                            "Code blob sync progress: %d/%d files (%.0fs elapsed)",
                            completed_files,
                            total_eligible,
                            time.monotonic() - start,
                        )
                        next_progress_log += 10

                    if not self._circuit_breaker.is_available(cb_provider):
                        remaining = _remaining_files()
                        logger.warning(
                            "Code blob sync circuit breaker OPEN after %d consecutive failures. "
                            "Stopping with %d files remaining.",
                            self._circuit_breaker.failure_threshold,
                            remaining,
                        )
                        await _cancel_pending("after circuit breaker opened")
                        _record_circuit_breaker_open()
                        break

                if unchanged_paths:
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(
                                self._batch_update_last_synced, unchanged_paths
                            ),
                            timeout=30.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Batch last_synced update timed out after 30s for %d files",
                            len(unchanged_paths),
                        )

                # Step 5: Detect deleted files
                deleted = await self._detect_deleted_files(
                    current_paths, stored_map=stored_map
                )
                result.files_deleted = deleted

                result.duration_seconds = time.monotonic() - start
                self._push_metrics(result)

                logger.info(
                    "Code blob sync complete: %d synced, %d skipped, %d deleted, "
                    "%d chunks, %d errors in %.1fs",
                    result.files_synced,
                    result.files_skipped,
                    result.files_deleted,
                    result.chunks_created,
                    result.errors,
                    result.duration_seconds,
                )
                return result
        finally:
            # Flush Langfuse traces after sync cycle (runs on all exit paths)
            if _langfuse_get_client is not None:
                with contextlib.suppress(Exception):
                    _langfuse_get_client().flush()

    async def _walk_tree(self) -> list[dict[str, Any]]:
        """Fetch and filter repository file tree.

        Returns:
            List of tree entry dicts (blobs only, filtered)
        """
        entries = await self.client.get_tree(
            tree_sha=self._branch,
            recursive=True,
        )
        # Only blobs (files), not trees (directories)
        return [e for e in entries if e.get("type") == "blob"]

    def _should_sync_file(self, entry: dict[str, Any]) -> bool:
        """Check if a file should be synced.

        Filters:
        - Binary files (by extension)
        - Files exceeding max size
        - Excluded patterns (node_modules, __pycache__, etc.)
        - Unknown/unsupported file types

        Args:
            entry: Tree entry dict with path, size, sha

        Returns:
            True if file should be synced
        """
        file_path = entry["path"]
        size = entry.get("size", 0)
        is_explicitly_included = _matches_any_pattern(file_path, self._include_patterns)

        # Skip binary files
        if is_binary_file(file_path):
            return False

        if is_explicitly_included:
            if size > self._include_max_size:
                logger.warning(
                    "Skipping explicitly included file %s: size %d exceeds include hard ceiling %d",
                    file_path,
                    size,
                    self._include_max_size,
                )
                return False
        else:
            if size > self.config.github_code_blob_max_size:
                return False
            if _matches_any_pattern(file_path, self._exclude_patterns):
                return False

        language = detect_language(file_path)
        return is_explicitly_included or language != "unknown"

    async def _sync_file(
        self,
        entry: dict[str, Any],
        batch_id: str,
        old_blob_hash: str | None,
    ) -> int:
        """Sync a single file: fetch content, chunk, store.

        Args:
            entry: Tree entry dict
            batch_id: Sync batch ID
            old_blob_hash: Previous blob hash (None if new file)

        Returns:
            Number of chunks stored
        """
        file_path = entry["path"]
        blob_sha = entry["sha"]

        # Fetch file content
        blob = await self.client.get_blob(blob_sha)
        content = base64.b64decode(blob["content"]).decode("utf-8", errors="replace")

        # SEC-2: Security scan before chunking — avoids wasting work on blocked files
        if self._scanner is not None:
            from memory.security_scanner import ScanAction

            scan_result = self._scanner.scan(content, source_type="github_code_blob")
            if scan_result.action == ScanAction.BLOCKED:
                logger.warning(
                    "Security scan blocked file %s: %d secret finding(s)",
                    file_path,
                    len(scan_result.findings),
                )
                return 0
            content = scan_result.content  # Use masked version

        # Detect language and extract symbols
        language = detect_language(file_path)
        symbols = extract_python_symbols(content) if language == "python" else []

        # Chunk content
        if language == "python":
            chunks = chunk_python_ast(content, file_path)
        else:
            chunks = _chunk_semantic(content, file_path, language)

        if not chunks:
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        source_authority = SOURCE_AUTHORITY_MAP.get("github_code_blob", 1.0)
        file_url = (
            f"https://github.com/{self._group_id}/blob/{self._branch}/{file_path}"
        )
        base_chunk_payload = {
            "source": "github",
            "github_id": 0,
            "repo": self._group_id,
            "timestamp": now_iso,
            "last_synced": now_iso,
            "url": file_url,
            "version": 1,
            "is_current": True,
            "supersedes": None,
            "update_batch_id": batch_id,
            "source_authority": source_authority,
            "decay_score": 1.0,
            "freshness_status": "unverified",
            "file_path": file_path,
            "language": language,
            "last_commit_sha": blob_sha,
            "symbols": symbols,
            "blob_hash": blob_sha,
            "content_type": "github_code_blob",
        }

        def _build_chunk_payload(
            chunk: Any, *, include_content: bool
        ) -> dict[str, Any]:
            payload = {
                **base_chunk_payload,
                "content_hash": compute_content_hash(chunk.content),
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
            }
            if include_content:
                payload["content"] = chunk.content
            return payload

        if self.config.github_code_blob_batch_storage_enabled:
            chunk_items = [
                _build_chunk_payload(chunk, include_content=True) for chunk in chunks
            ]
            try:
                batch_results = await asyncio.to_thread(
                    self.storage.store_github_code_blob_chunks_batch,
                    chunk_items,
                    cwd=str(Path.cwd()),
                    collection=GITHUB_COLLECTION,
                    group_id=self._group_id,
                    memory_type=MemoryType.GITHUB_CODE_BLOB,
                    source_hook="github_code_sync",
                    session_id=batch_id,
                    chunk_batch_size=self.config.github_code_blob_chunk_batch_size,
                )
                stored_count = sum(
                    1 for r in batch_results if r.get("status") == "stored"
                )
                has_real_embeddings = any(
                    r.get("embedding_status") != "pending" for r in batch_results
                )
                if (
                    old_blob_hash
                    and stored_count == len(chunks)
                    and has_real_embeddings
                ):
                    await asyncio.to_thread(
                        self._supersede_old_blobs, file_path, old_blob_hash
                    )
                elif old_blob_hash:
                    logger.warning(
                        "skipping_supersede",
                        extra={
                            "context": {
                                "file_path": file_path,
                                "stored": stored_count,
                                "total": len(chunks),
                                "has_embeddings": has_real_embeddings,
                            }
                        },
                    )
                return stored_count
            except Exception as e:
                logger.error(
                    "Failed to batch-store chunks for %s: %s",
                    file_path,
                    e,
                )
                raise RuntimeError(f"batch store failed for {file_path}: {e}") from e

        stored_count = 0
        for chunk in chunks:
            payload = _build_chunk_payload(chunk, include_content=False)

            try:
                store_result = await asyncio.to_thread(
                    self.storage.store_memory,
                    content=chunk.content,
                    cwd=str(Path.cwd()),
                    memory_type=MemoryType.GITHUB_CODE_BLOB,
                    source_hook="github_code_sync",
                    session_id=batch_id,
                    collection=GITHUB_COLLECTION,
                    group_id=self._group_id,
                    **payload,
                )
                if store_result and store_result.get("status") != "error":
                    stored_count += 1
            except Exception as e:
                logger.error(
                    "Failed to store chunk %d/%d of %s: %s",
                    chunk.chunk_index,
                    chunk.total_chunks,
                    file_path,
                    e,
                )

        if stored_count == len(chunks) and old_blob_hash:
            await asyncio.to_thread(self._supersede_old_blobs, file_path, old_blob_hash)

        return stored_count

    def _get_stored_blob_map(self) -> dict[str, str]:
        """Build lookup map of stored file_path -> blob_hash.

        Uses batch lookup pattern (BP-066) for O(1) freshness checks
        instead of N+1 queries.

        Returns:
            Dict mapping file_path to blob_hash for current blobs
        """
        try:
            blob_map: dict[str, str] = {}
            offset = None

            while True:
                points, next_offset = self.qdrant.scroll(
                    collection_name=GITHUB_COLLECTION,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="group_id",
                                match=models.MatchValue(value=self._group_id),
                            ),
                            models.FieldCondition(
                                key="source",
                                match=models.MatchValue(value="github"),
                            ),
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="github_code_blob"),
                            ),
                            models.FieldCondition(
                                key="is_current",
                                match=models.MatchValue(value=True),
                            ),
                            # NOTE: Only queries chunk_index=0 for efficiency. Files that lost their
                            # index-0 chunk in a prior partial failure appear as new on next sync,
                            # causing re-ingestion (self-healing behavior).
                            models.FieldCondition(
                                key="chunk_index",
                                match=models.MatchValue(value=0),
                            ),
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=["file_path", "blob_hash"],
                )

                for point in points:
                    fp = point.payload.get("file_path", "")
                    bh = point.payload.get("blob_hash", "")
                    if fp and bh:
                        blob_map[fp] = bh

                if next_offset is None:
                    break
                offset = next_offset

            return blob_map
        except Exception as e:
            logger.warning("Failed to build blob lookup map: %s", e)
            return {}

    # Retained for backward compat — primary sync path now uses _batch_update_last_synced
    def _update_last_synced(self, file_path: str) -> None:
        """Update last_synced for unchanged file blobs.

        Args:
            file_path: File path to update
        """
        try:
            now_iso = datetime.now(timezone.utc).isoformat()

            # Paginate to collect all chunk point IDs
            offset = None
            all_point_ids = []
            while True:
                points, next_offset = self.qdrant.scroll(
                    collection_name=GITHUB_COLLECTION,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="group_id",
                                match=models.MatchValue(value=self._group_id),
                            ),
                            models.FieldCondition(
                                key="source",
                                match=models.MatchValue(value="github"),
                            ),
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="github_code_blob"),
                            ),
                            models.FieldCondition(
                                key="file_path",
                                match=models.MatchValue(value=file_path),
                            ),
                            models.FieldCondition(
                                key="is_current",
                                match=models.MatchValue(value=True),
                            ),
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=False,
                )
                all_point_ids.extend([p.id for p in points])
                if next_offset is None:
                    break
                offset = next_offset

            if all_point_ids:
                self.qdrant.set_payload(
                    collection_name=GITHUB_COLLECTION,
                    payload={"last_synced": now_iso},
                    points=all_point_ids,
                )
        except Exception as e:
            logger.warning("Failed to update last_synced for %s: %s", file_path, e)

    def _batch_update_last_synced(self, file_paths: list[str]) -> None:
        """Batch update last_synced for multiple unchanged file blobs.

        Replaces O(n) per-file scroll+set_payload with a single scroll
        (using MatchAny filter) and a single set_payload call across all
        matched point IDs.

        Args:
            file_paths: List of file paths whose last_synced should be updated.
        """
        if not file_paths:
            return
        try:
            logger.info(
                "Batch updating last_synced for %d unchanged files", len(file_paths)
            )
            now_iso = datetime.now(timezone.utc).isoformat()

            # Collect all point IDs via paginated scroll with MatchAny filter
            offset = None
            all_point_ids = []
            while True:
                points, next_offset = self.qdrant.scroll(
                    collection_name=GITHUB_COLLECTION,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="group_id",
                                match=models.MatchValue(value=self._group_id),
                            ),
                            models.FieldCondition(
                                key="source",
                                match=models.MatchValue(value="github"),
                            ),
                            models.FieldCondition(
                                key="type",
                                match=models.MatchValue(value="github_code_blob"),
                            ),
                            models.FieldCondition(
                                key="file_path",
                                match=models.MatchAny(any=file_paths),
                            ),
                            models.FieldCondition(
                                key="is_current",
                                match=models.MatchValue(value=True),
                            ),
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=False,
                )
                all_point_ids.extend([p.id for p in points])
                if next_offset is None:
                    break
                offset = next_offset

            if all_point_ids:
                BATCH_SIZE = 500
                for i in range(0, len(all_point_ids), BATCH_SIZE):
                    batch = all_point_ids[i : i + BATCH_SIZE]
                    self.qdrant.set_payload(
                        collection_name=GITHUB_COLLECTION,
                        payload={"last_synced": now_iso},
                        points=batch,
                    )
                logger.info(
                    "Batch updated last_synced: %d points across %d files",
                    len(all_point_ids),
                    len(file_paths),
                )
        except Exception as e:
            logger.warning(
                "Failed to batch update last_synced for %d files: %s",
                len(file_paths),
                e,
            )

    def _supersede_old_blobs(
        self, file_path: str, blob_hash: str | None = None
    ) -> None:
        """Mark existing blobs for a file as superseded.

        Args:
            file_path: File path to supersede
            blob_hash: Optional previous blob hash to limit superseding scope
        """
        try:
            # Paginate to collect all chunk point IDs
            offset = None
            all_point_ids = []
            while True:
                must_filters = [
                    models.FieldCondition(
                        key="group_id",
                        match=models.MatchValue(value=self._group_id),
                    ),
                    models.FieldCondition(
                        key="source",
                        match=models.MatchValue(value="github"),
                    ),
                    models.FieldCondition(
                        key="type",
                        match=models.MatchValue(value="github_code_blob"),
                    ),
                    models.FieldCondition(
                        key="file_path",
                        match=models.MatchValue(value=file_path),
                    ),
                    models.FieldCondition(
                        key="is_current",
                        match=models.MatchValue(value=True),
                    ),
                ]
                if blob_hash:
                    must_filters.append(
                        models.FieldCondition(
                            key="blob_hash",
                            match=models.MatchValue(value=blob_hash),
                        )
                    )
                points, next_offset = self.qdrant.scroll(
                    collection_name=GITHUB_COLLECTION,
                    scroll_filter=models.Filter(must=must_filters),
                    limit=100,
                    offset=offset,
                    with_payload=False,
                )
                all_point_ids.extend([p.id for p in points])
                if next_offset is None:
                    break
                offset = next_offset

            if all_point_ids:
                self.qdrant.set_payload(
                    collection_name=GITHUB_COLLECTION,
                    payload={"is_current": False},
                    points=all_point_ids,
                )
                logger.debug(
                    "Superseded %d chunks for %s", len(all_point_ids), file_path
                )
        except Exception as e:
            logger.error(
                "supersede_old_blobs_failed",
                extra={
                    "context": {
                        "file_path": file_path,
                        "blob_hash": blob_hash,
                        "error": str(e),
                    }
                },
            )

    async def _detect_deleted_files(
        self,
        current_paths: set[str],
        stored_map: dict[str, str] | None = None,
    ) -> int:
        """Detect files that were deleted from repository.

        Files stored in Qdrant but not in current tree are marked
        is_current=False.

        Args:
            current_paths: Set of file paths in current tree
            stored_map: Pre-fetched blob map to avoid redundant query.
                        If None, fetches internally.

        Returns:
            Count of deleted files detected
        """
        try:
            if stored_map is None:
                stored_map = self._get_stored_blob_map()
            deleted_paths = set(stored_map.keys()) - current_paths

            if not deleted_paths:
                return 0

            deleted_count = 0
            for file_path in deleted_paths:
                offset = None
                all_point_ids = []
                while True:
                    points, next_offset = self.qdrant.scroll(
                        collection_name=GITHUB_COLLECTION,
                        scroll_filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="group_id",
                                    match=models.MatchValue(value=self._group_id),
                                ),
                                models.FieldCondition(
                                    key="source",
                                    match=models.MatchValue(value="github"),
                                ),
                                models.FieldCondition(
                                    key="type",
                                    match=models.MatchValue(value="github_code_blob"),
                                ),
                                models.FieldCondition(
                                    key="file_path",
                                    match=models.MatchValue(value=file_path),
                                ),
                                models.FieldCondition(
                                    key="is_current",
                                    match=models.MatchValue(value=True),
                                ),
                            ]
                        ),
                        limit=100,
                        offset=offset,
                        with_payload=False,
                    )
                    all_point_ids.extend([p.id for p in points])
                    if next_offset is None:
                        break
                    offset = next_offset

                if all_point_ids:
                    self.qdrant.set_payload(
                        collection_name=GITHUB_COLLECTION,
                        payload={"is_current": False},
                        points=all_point_ids,
                    )
                    deleted_count += 1
                    logger.info(
                        "Marked deleted file: %s (%d chunks)",
                        file_path,
                        len(all_point_ids),
                    )

            return deleted_count
        except Exception as e:
            logger.warning("Failed to detect deleted files: %s", e)
            return 0

    def _push_metrics(self, result: CodeSyncResult) -> None:
        """Push code sync metrics to pushgateway.

        Args:
            result: CodeSyncResult with counts
        """
        try:
            from prometheus_client import CollectorRegistry, Counter, Gauge
            from prometheus_client.exposition import pushadd_to_gateway

            registry = CollectorRegistry()

            files_total = Counter(
                "github_code_sync_files_total",
                "Total code files processed",
                ["status"],
                registry=registry,
            )
            chunks_total = Counter(
                "github_code_sync_chunks_total",
                "Total code chunks created",
                registry=registry,
            )
            duration = Gauge(
                "github_code_sync_duration_seconds",
                "Code sync duration",
                registry=registry,
            )

            files_total.labels(status="synced").inc(result.files_synced)
            files_total.labels(status="skipped").inc(result.files_skipped)
            files_total.labels(status="deleted").inc(result.files_deleted)
            files_total.labels(status="error").inc(result.errors)
            chunks_total.inc(result.chunks_created)
            duration.set(result.duration_seconds)

            pushadd_to_gateway(
                os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
                job="github_code_sync",
                registry=registry,
                grouping_key={"instance": self._group_id},
            )
        except Exception as e:
            logger.warning("Failed to push code sync metrics: %s", e)
