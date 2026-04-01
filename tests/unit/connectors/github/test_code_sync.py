# Location: ai-memory/tests/unit/connectors/github/test_code_sync.py

import logging
import os
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_code_sync_logger(caplog):
    """Ensure caplog captures logs from code_sync despite propagate=False."""
    logger = logging.getLogger("ai_memory.github.code_sync")
    logger.addHandler(caplog.handler)
    yield
    logger.removeHandler(caplog.handler)


from memory.connectors.github.client import GitHubClientError
from memory.connectors.github.code_sync import (
    CodeBlobSync,
    CodeSyncResult,
    _build_context_header,
    _chunk_semantic,
    _extract_import_lines,
    _path_matches_pattern,
    chunk_python_ast,
    detect_language,
    extract_python_imports,
    extract_python_symbols,
    is_binary_file,
)

# -- CodeSyncResult Tests --------------------------------------------


def test_code_sync_result_defaults():
    """All counts default to zero."""
    result = CodeSyncResult()
    assert result.files_synced == 0
    assert result.chunks_created == 0


def test_code_sync_result_to_dict():
    """to_dict includes all fields."""
    result = CodeSyncResult(files_synced=5, chunks_created=15, errors=1)
    d = result.to_dict()
    assert d["files_synced"] == 5
    assert d["chunks_created"] == 15


# -- Language Detection Tests ----------------------------------------


def test_detect_python():
    assert detect_language("src/memory/storage.py") == "python"


def test_detect_javascript():
    assert detect_language("app/index.js") == "javascript"


def test_detect_typescript():
    assert detect_language("src/types.ts") == "typescript"


def test_detect_yaml():
    assert detect_language("config.yaml") == "yaml"
    assert detect_language("config.yml") == "yaml"


def test_detect_shell():
    assert detect_language("scripts/setup.sh") == "bash"


def test_detect_dockerfile():
    assert detect_language("Dockerfile") == "dockerfile"
    assert detect_language("docker/Dockerfile") == "dockerfile"


@pytest.mark.parametrize(
    "file_path,expected",
    [
        ("Makefile", "makefile"),
        ("CODEOWNERS", "text"),
        (".dockerignore", "text"),
        (".gitignore", "text"),
        (".editorconfig", "editorconfig"),
    ],
)
def test_detect_special_files(file_path, expected):
    assert detect_language(file_path) == expected


def test_detect_unknown():
    assert detect_language("README") == "unknown"
    assert detect_language("file.xyz") == "unknown"


def test_is_binary():
    assert is_binary_file("image.png") is True
    assert is_binary_file("app.exe") is True
    assert is_binary_file("data.sqlite") is True


def test_is_not_binary():
    assert is_binary_file("app.py") is False
    assert is_binary_file("config.yaml") is False


# -- Symbol Extraction Tests -----------------------------------------


def test_extract_class():
    code = "class Foo:\n    pass\n"
    assert "Foo" in extract_python_symbols(code)


def test_extract_function():
    code = "def bar():\n    pass\n"
    assert "bar" in extract_python_symbols(code)


def test_extract_async_function():
    code = "async def baz():\n    pass\n"
    assert "baz" in extract_python_symbols(code)


def test_extract_multiple_symbols():
    code = "class A:\n    pass\ndef b():\n    pass\nclass C:\n    pass\n"
    symbols = extract_python_symbols(code)
    assert symbols == ["A", "b", "C"]


def test_extract_syntax_error():
    """SyntaxError returns empty list."""
    symbols = extract_python_symbols("def broken(:\n")
    assert symbols == []


def test_extract_nested_not_included():
    """Nested functions/classes not included (top-level only)."""
    code = "class Outer:\n    def inner(self):\n        pass\n"
    symbols = extract_python_symbols(code)
    assert symbols == ["Outer"]  # inner is nested, not top-level


# -- Import Extraction Tests -----------------------------------------


def test_extract_import():
    code = "import os\nimport sys\n"
    imports = extract_python_imports(code)
    assert "os" in imports
    assert "sys" in imports


def test_extract_from_import():
    code = "from pathlib import Path\nfrom os.path import join\n"
    imports = extract_python_imports(code)
    assert "pathlib" in imports
    assert "os" in imports


def test_extract_imports_deduped():
    code = "import os\nfrom os import path\n"
    imports = extract_python_imports(code)
    assert imports.count("os") == 1


# -- Context Header Tests --------------------------------------------


def test_context_header_basic():
    header = _build_context_header("src/app.py", "python", [], ["os"])
    assert "File: src/app.py" in header
    assert "Language: python" in header
    assert "Imports: os" in header


def test_context_header_with_class():
    header = _build_context_header("src/app.py", "python", ["MyClass"], [])
    assert "Symbol: MyClass" in header


def test_context_header_with_class_and_method():
    header = _build_context_header("src/app.py", "python", ["MyClass", "my_method"], [])
    assert "Class: MyClass" in header
    assert "Method: my_method" in header


def test_context_header_starts_with_comment():
    header = _build_context_header("test.py", "python", [], [])
    assert header.startswith("# ")


# -- Python AST Chunking Tests ---------------------------------------


def test_chunk_python_single_function():
    code = "import os\n\ndef hello():\n    print('hi')\n"
    chunks = chunk_python_ast(code, "test.py")
    assert len(chunks) >= 1
    assert any("hello" in c.content for c in chunks)


def test_chunk_python_class_and_function():
    code = (
        "class Foo:\n    def bar(self):\n        pass\n\ndef standalone():\n    pass\n"
    )
    chunks = chunk_python_ast(code, "test.py")
    assert len(chunks) >= 2


def test_chunk_python_context_header():
    """Each chunk has context enrichment header."""
    code = "import os\n\ndef hello():\n    print('hi')\n"
    chunks = chunk_python_ast(code, "src/test.py")
    for chunk in chunks:
        assert chunk.content.startswith("# File: src/test.py")


def test_chunk_python_syntax_error_fallback():
    """SyntaxError falls back to semantic chunking."""
    code = "def broken(:\n    pass\n"
    chunks = chunk_python_ast(code, "test.py")
    assert len(chunks) >= 1  # Should not raise


def test_chunk_python_indices():
    """Chunk indices and totals set correctly."""
    code = "def a():\n    pass\n\ndef b():\n    pass\n\ndef c():\n    pass\n"
    chunks = chunk_python_ast(code, "test.py")
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.total_chunks == len(chunks)


def test_chunk_python_module_level():
    """Module-level code captured separately."""
    code = "X = 42\nY = 'hello'\n\ndef func():\n    pass\n"
    chunks = chunk_python_ast(code, "test.py")
    # Should have module-level chunk + function chunk
    assert len(chunks) >= 2


# -- Semantic Chunking Tests -----------------------------------------


def test_semantic_chunk_basic():
    """Non-Python code chunked semantically."""
    code = "\n".join([f"line {i}" for i in range(100)])
    chunks = _chunk_semantic(code, "app.js", "javascript")
    assert len(chunks) >= 1


def test_semantic_chunk_has_header():
    """Semantic chunks have context headers."""
    code = "const x = 1;\n" * 50
    chunks = _chunk_semantic(code, "app.js", "javascript")
    for chunk in chunks:
        assert "File: app.js" in chunk.content


def test_semantic_chunk_overlap():
    """Multiple chunks have overlapping content."""
    code = "\n".join([f"line {i}: content here" for i in range(200)])
    chunks = _chunk_semantic(code, "big.js", "javascript")
    if len(chunks) >= 2:
        # Check some overlap exists between adjacent chunks
        lines_chunk0 = set(chunks[0].raw_content.split("\n"))
        lines_chunk1 = set(chunks[1].raw_content.split("\n"))
        assert lines_chunk0 & lines_chunk1  # Some overlap


# -- File Filtering Tests --------------------------------------------


def _make_initialized_sync(
    *,
    include: str = "",
    exclude: str = "",
    max_size: int = 102400,
    include_max_size: int = 512000,
):
    mock_client = MagicMock()
    config = MagicMock()
    config.github_branch = "main"
    config.github_repo = "owner/repo"
    config.github_code_blob_max_size = max_size
    config.github_code_blob_include = include
    config.github_code_blob_include_max_size = include_max_size
    config.github_code_blob_exclude = exclude
    config.github_sync_circuit_breaker_threshold = 5
    config.github_sync_circuit_breaker_reset = 60
    config.security_scanning_enabled = False

    with (
        patch("memory.connectors.github.code_sync.MemoryStorage"),
        patch("memory.connectors.github.code_sync.get_qdrant_client"),
    ):
        return CodeBlobSync(mock_client, config)


def _make_filtering_sync():
    sync = CodeBlobSync.__new__(CodeBlobSync)
    sync.config = MagicMock()
    sync.config.github_code_blob_max_size = 102400
    sync.config.github_code_blob_include_max_size = 512000
    sync._exclude_patterns = []
    sync._include_patterns = []
    sync._include_max_size = 512000
    return sync


def test_should_sync_python():
    sync = _make_filtering_sync()
    sync._exclude_patterns = ["node_modules", "__pycache__"]
    assert sync._should_sync_file({"path": "src/app.py", "size": 5000}) is True


def test_should_skip_binary():
    sync = _make_filtering_sync()
    assert sync._should_sync_file({"path": "icon.png", "size": 1000}) is False


def test_should_reject_binary_even_when_explicitly_included():
    sync = _make_initialized_sync(include="*.png")
    assert sync._should_sync_file({"path": "icon.png", "size": 1000}) is False


def test_should_skip_large_file():
    sync = _make_filtering_sync()
    assert sync._should_sync_file({"path": "big.py", "size": 200000}) is False


def test_should_skip_excluded_dir():
    sync = _make_filtering_sync()
    sync._exclude_patterns = ["node_modules", "__pycache__"]
    assert (
        sync._should_sync_file({"path": "node_modules/pkg/index.js", "size": 100})
        is False
    )


def test_should_skip_excluded_extension():
    sync = _make_filtering_sync()
    sync._exclude_patterns = ["*.min.js"]
    assert sync._should_sync_file({"path": "dist/app.min.js", "size": 100}) is False


def test_should_skip_unknown_language():
    sync = _make_filtering_sync()
    assert sync._should_sync_file({"path": "data.xyz", "size": 100}) is False


@pytest.mark.parametrize(
    "file_path,bare_pattern,suffix_pattern,expected",
    [
        ("Makefile", "Makefile", "*Makefile", True),
        ("infra/Makefile", "Makefile", "*Makefile", True),
        ("dist/app.min.js", "dist", "*.min.js", True),
        ("src/app.js", "dist", "*.min.js", False),
    ],
)
def test_filter_pattern_modes_match_for_include_and_exclude(
    file_path, bare_pattern, suffix_pattern, expected
):
    """Bare-token and suffix rules are shared across include and exclude matching."""
    assert _path_matches_pattern(file_path, bare_pattern) is expected
    assert _path_matches_pattern(file_path, suffix_pattern) is expected


def test_should_allow_unknown_language_when_explicitly_included():
    sync = _make_filtering_sync()
    sync._include_patterns = ["*.foo"]
    assert sync._should_sync_file({"path": "data.foo", "size": 100}) is True


def test_should_allow_excluded_path_when_explicitly_included():
    sync = _make_filtering_sync()
    sync._exclude_patterns = ["dist"]
    sync._include_patterns = ["*.js"]
    assert sync._should_sync_file({"path": "dist/app.js", "size": 100}) is True


def test_should_allow_oversize_file_when_explicitly_included_below_hard_ceiling():
    sync = _make_filtering_sync()
    sync._include_patterns = ["*.xml"]
    assert (
        sync._should_sync_file({"path": "config/catalog.xml", "size": 200000}) is True
    )


def test_should_reject_explicit_include_above_hard_ceiling(caplog):
    sync = _make_filtering_sync()
    sync._include_patterns = ["*.xml"]
    caplog.set_level("WARNING")
    assert (
        sync._should_sync_file({"path": "config/catalog.xml", "size": 600000}) is False
    )
    assert "exceeds include hard ceiling" in caplog.text


@pytest.mark.parametrize(
    "file_path",
    ["Makefile", "CODEOWNERS", ".dockerignore", ".gitignore", ".editorconfig"],
)
def test_should_sync_supported_special_files_without_include(file_path):
    sync = _make_filtering_sync()
    assert sync._should_sync_file({"path": file_path, "size": 100}) is True


def test_code_blob_sync_init_skips_invalid_patterns_and_keeps_valid_ones(caplog):
    caplog.set_level("WARNING")
    sync = _make_initialized_sync(
        include="nested/path,*.foo,Makefile",
        exclude="vendor/generated,dist,*.min.js",
    )

    assert sync._include_patterns == ["*.foo", "Makefile"]
    assert sync._exclude_patterns == ["dist", "*.min.js"]
    # Both include ("nested/path") and exclude ("vendor/generated") invalid patterns should warn
    assert caplog.text.count("invalid_include_pattern_ignored") >= 2
    assert sync._should_sync_file({"path": "folder/file.foo", "size": 100}) is True
    assert sync._should_sync_file({"path": "dist/app.min.js", "size": 100}) is False


@pytest.mark.parametrize("file_path", [".env", ".DS_Store"])
def test_should_reject_unlisted_dotfiles_without_include(file_path):
    sync = _make_filtering_sync()
    assert sync._should_sync_file({"path": file_path, "size": 100}) is False


# -- Sync Integration Tests ------------------------------------------


def _make_sync_instance():
    """Helper to create a CodeBlobSync instance without __init__."""
    sync = CodeBlobSync.__new__(CodeBlobSync)
    sync.config = MagicMock()
    sync.config.github_branch = "main"
    sync.config.github_repo = "owner/repo"
    sync.config.github_code_blob_max_size = 102400
    sync.config.github_code_blob_include = ""
    sync.config.github_code_blob_include_max_size = 512000
    sync.config.github_sync_total_timeout = 1800
    sync.config.github_sync_per_file_timeout = 60
    sync.config.github_sync_circuit_breaker_threshold = 5
    sync.config.github_sync_circuit_breaker_reset = 60
    sync.config.github_code_blob_file_concurrency = 2
    sync.config.github_code_blob_chunk_batch_size = 8
    sync.config.github_code_blob_batch_storage_enabled = True
    sync.client = AsyncMock()
    sync._group_id = "owner/repo"
    sync._branch = "main"
    sync._exclude_patterns = []
    sync._include_patterns = []
    sync._include_max_size = 512000
    sync.storage = MagicMock()

    # BUG-112: Circuit breaker required by sync_code_blobs
    from memory.classifier.circuit_breaker import CircuitBreaker

    sync._circuit_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60)
    return sync


@pytest.mark.asyncio
async def test_sync_code_blobs_empty_tree():
    """Empty tree produces zero synced files."""
    sync = _make_sync_instance()
    sync.client.get_tree = AsyncMock(return_value=[])

    with (
        patch.object(sync, "_get_stored_blob_map", return_value={}),
        patch.object(
            sync, "_detect_deleted_files", new_callable=AsyncMock, return_value=0
        ),
        patch.object(sync, "_push_metrics"),
    ):
        result = await sync.sync_code_blobs("batch-1")

    assert result.files_synced == 0
    assert result.chunks_created == 0


@pytest.mark.asyncio
async def test_sync_code_blobs_unchanged_skips():
    """Unchanged files (matching blob_hash) are skipped via batch update."""
    sync = _make_sync_instance()
    sync.client.get_tree = AsyncMock(
        return_value=[
            {"path": "src/app.py", "type": "blob", "sha": "abc123", "size": 500}
        ]
    )

    with (
        patch.object(
            sync, "_get_stored_blob_map", return_value={"src/app.py": "abc123"}
        ),
        patch.object(sync, "_batch_update_last_synced") as mock_batch,
        patch.object(
            sync, "_detect_deleted_files", new_callable=AsyncMock, return_value=0
        ),
        patch.object(sync, "_push_metrics"),
    ):
        result = await sync.sync_code_blobs("batch-1")

    assert result.files_synced == 0
    assert result.files_skipped >= 1
    mock_batch.assert_called_once_with(["src/app.py"])


@pytest.mark.asyncio
async def test_sync_code_blobs_changed_stores():
    """Changed files are re-embedded and stored."""
    sync = _make_sync_instance()
    sync.client.get_tree = AsyncMock(
        return_value=[
            {"path": "src/app.py", "type": "blob", "sha": "new_sha", "size": 500}
        ]
    )

    mock_sync_file = AsyncMock(return_value=3)

    with (
        patch.object(
            sync, "_get_stored_blob_map", return_value={"src/app.py": "old_sha"}
        ),
        patch.object(sync, "_sync_file", mock_sync_file),
        patch.object(
            sync, "_detect_deleted_files", new_callable=AsyncMock, return_value=0
        ),
        patch.object(sync, "_push_metrics"),
    ):
        result = await sync.sync_code_blobs("batch-1")

    assert result.files_synced == 1
    assert result.chunks_created == 3


@pytest.mark.asyncio
async def test_sync_detects_deleted_files():
    """Files in Qdrant but not in tree marked is_current=False."""
    sync = _make_sync_instance()
    sync.client.get_tree = AsyncMock(return_value=[])  # No files in tree

    with (
        patch.object(sync, "_get_stored_blob_map", return_value={}),
        patch.object(
            sync, "_detect_deleted_files", new_callable=AsyncMock, return_value=2
        ),
        patch.object(sync, "_push_metrics"),
    ):
        result = await sync.sync_code_blobs("batch-1")

    assert result.files_deleted == 2


@pytest.mark.asyncio
async def test_sync_fail_open_per_file():
    """Individual file failure doesn't stop sync."""
    sync = _make_sync_instance()
    sync.client.get_tree = AsyncMock(
        return_value=[
            {"path": "src/bad.py", "type": "blob", "sha": "sha1", "size": 500},
            {"path": "src/good.py", "type": "blob", "sha": "sha2", "size": 500},
        ]
    )

    call_count = 0

    async def sync_file_effect(entry, batch_id, old_hash):
        nonlocal call_count
        call_count += 1
        if entry["path"] == "src/bad.py":
            raise RuntimeError("boom")
        return 2

    with (
        patch.object(sync, "_get_stored_blob_map", return_value={}),
        patch.object(sync, "_sync_file", side_effect=sync_file_effect),
        patch.object(
            sync, "_detect_deleted_files", new_callable=AsyncMock, return_value=0
        ),
        patch.object(sync, "_push_metrics"),
    ):
        result = await sync.sync_code_blobs("batch-1")

    assert result.errors == 1
    assert result.files_synced == 1  # good.py still synced


@pytest.mark.asyncio
async def test_sync_tree_failure_returns_error():
    """Tree fetch failure returns error result."""
    sync = _make_sync_instance()
    sync.client.get_tree = AsyncMock(side_effect=GitHubClientError("timeout"))

    result = await sync.sync_code_blobs("batch-1")

    assert result.errors >= 1
    assert result.files_synced == 0


# -- FIX-1: Sub-chunk header on all chunks ----------------------------


def test_chunk_python_large_function_sub_chunked():
    """Large functions (>1024 tokens) are sub-chunked with headers on ALL chunks."""
    # Generate a function with 5000+ chars to trigger sub-chunking
    body_lines = [
        f"    x_{i} = {i} * 2  # padding line to make content large enough"
        for i in range(150)
    ]
    code = "import os\n\ndef big_func():\n" + "\n".join(body_lines) + "\n"

    chunks = chunk_python_ast(code, "big.py")
    # Should produce more than 1 chunk (the big_func gets sub-chunked)
    func_chunks = [c for c in chunks if c.symbol_name == "big_func"]
    assert len(func_chunks) > 1, f"Expected >1 sub-chunks, got {len(func_chunks)}"

    # ALL sub-chunks must start with context header
    for i, chunk in enumerate(func_chunks):
        assert chunk.content.startswith(
            "# File: big.py"
        ), f"Sub-chunk {i} missing context header: {chunk.content[:80]}"


# -- FIX-2: Decorator preservation ------------------------------------


def test_chunk_python_decorated_function():
    """Decorated functions include decorator lines in chunk content."""
    code = "import functools\n\n@functools.lru_cache\ndef cached():\n    return 42\n"
    chunks = chunk_python_ast(code, "deco.py")
    func_chunks = [c for c in chunks if c.symbol_name == "cached"]
    assert len(func_chunks) == 1
    assert "@functools.lru_cache" in func_chunks[0].raw_content


def test_chunk_python_decorated_class():
    """Decorated classes include decorator lines in chunk content."""
    code = "from dataclasses import dataclass\n\n@dataclass\nclass Point:\n    x: int\n    y: int\n"
    chunks = chunk_python_ast(code, "point.py")
    class_chunks = [c for c in chunks if c.symbol_name == "Point"]
    assert len(class_chunks) == 1
    assert "@dataclass" in class_chunks[0].raw_content


# -- FIX-4: Malformed imports -----------------------------------------


def test_chunk_python_empty_file():
    """Empty file returns empty chunk list."""
    chunks = chunk_python_ast("", "empty.py")
    assert chunks == []


def test_extract_import_lines_malformed():
    """Bare 'import' without module name doesn't crash."""
    lines = ["import", "import os", ""]
    result = _extract_import_lines(lines, "python")
    # Should not raise IndexError; 'os' should be extracted
    assert "os" in result


# -- FIX-5/Overlap: Semantic chunk overlap percentage ------------------


def test_semantic_chunk_overlap_percentage():
    """Overlap between adjacent semantic chunks is approximately 20%."""
    # Generate enough content for multiple chunks
    code = "\n".join(
        [f"// line {i}: some JavaScript code here padding" for i in range(500)]
    )
    chunks = _chunk_semantic(code, "big.js", "javascript")
    assert len(chunks) >= 2, "Need at least 2 chunks to test overlap"

    for i in range(len(chunks) - 1):
        lines_a = set(chunks[i].raw_content.split("\n"))
        lines_b = set(chunks[i + 1].raw_content.split("\n"))
        overlap = lines_a & lines_b
        chunk_a_size = len(lines_a)
        if chunk_a_size > 0:
            overlap_ratio = len(overlap) / chunk_a_size
            # Should be roughly 20% (allow 10%-35% range for boundary effects)
            assert 0.10 <= overlap_ratio <= 0.35, (
                f"Overlap ratio {overlap_ratio:.2f} outside expected range "
                f"(overlap={len(overlap)}, chunk_size={chunk_a_size})"
            )


# -- FIX-3: Deleted files source/type filter ---------------------------


@pytest.mark.asyncio
async def test_detect_deleted_files_with_source_filter():
    """_detect_deleted_files includes source and type in Qdrant filter."""
    sync = _make_sync_instance()
    sync.qdrant = MagicMock()

    mock_point = MagicMock()
    mock_point.id = "point-1"
    sync.qdrant.scroll.return_value = ([mock_point], None)

    current_paths = {"src/kept.py"}
    stored_map = {"src/kept.py": "sha1", "src/deleted.py": "sha2"}

    await sync._detect_deleted_files(current_paths, stored_map=stored_map)

    # Verify the scroll call includes source and type filters
    call_args = sync.qdrant.scroll.call_args
    scroll_filter = call_args.kwargs.get("scroll_filter") or call_args[1].get(
        "scroll_filter"
    )
    must_conditions = scroll_filter.must

    filter_keys = [c.key for c in must_conditions]
    assert "source" in filter_keys, "Missing 'source' filter condition"
    assert "type" in filter_keys, "Missing 'type' filter condition"

    # Verify values
    source_cond = next(c for c in must_conditions if c.key == "source")
    type_cond = next(c for c in must_conditions if c.key == "type")
    assert source_cond.match.value == "github"
    assert type_cond.match.value == "github_code_blob"


def test_supersede_old_blobs_filters_by_previous_blob_hash():
    sync = _make_sync_instance()
    sync.qdrant = MagicMock()
    sync.qdrant.scroll.return_value = ([], None)

    sync._supersede_old_blobs("src/file.py", "oldsha")

    call_args = sync.qdrant.scroll.call_args
    scroll_filter = call_args.kwargs.get("scroll_filter") or call_args[1].get(
        "scroll_filter"
    )
    must_conditions = scroll_filter.must
    blob_hash_cond = next(c for c in must_conditions if c.key == "blob_hash")
    assert blob_hash_cond.match.value == "oldsha"

    file_path_conditions = [c for c in must_conditions if c.key == "file_path"]
    assert len(file_path_conditions) == 1
    assert file_path_conditions[0].match.value == "src/file.py"


# -- FIX-5: Pagination in _update_last_synced --------------------------


def test_update_last_synced_pagination():
    """_update_last_synced paginates through >100 chunks."""
    sync = _make_sync_instance()
    sync.qdrant = MagicMock()

    # First page: 100 points, next_offset set
    page1_points = [MagicMock(id=f"p-{i}") for i in range(100)]
    # Second page: 20 points, no next_offset
    page2_points = [MagicMock(id=f"p-{100 + i}") for i in range(20)]

    sync.qdrant.scroll.side_effect = [
        (page1_points, "offset-2"),
        (page2_points, None),
    ]

    sync._update_last_synced("src/big.py")

    # Should have called scroll twice (pagination)
    assert sync.qdrant.scroll.call_count == 2

    # set_payload should be called once with ALL 120 point IDs
    sync.qdrant.set_payload.assert_called_once()
    call_kwargs = sync.qdrant.set_payload.call_args.kwargs
    assert len(call_kwargs["points"]) == 120
    assert "last_synced" in call_kwargs["payload"]


# -- BUG-251: Synthetic CLAUDE_SESSION_ID in service contexts -----------

from memory.connectors.github.sync import GitHubSyncEngine

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def test_code_blob_sync_sets_claude_session_id(monkeypatch):
    """BUG-251: CodeBlobSync.__init__() sets CLAUDE_SESSION_ID with github-code-sync-{date} prefix."""
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

    mock_client = MagicMock()
    config = MagicMock()
    config.github_repo = "owner/repo"
    config.github_branch = "main"
    config.github_code_blob_max_size = 102400
    config.github_code_blob_include = ""
    config.github_code_blob_include_max_size = 512000
    config.github_code_blob_exclude = ""
    config.github_sync_circuit_breaker_threshold = 5
    config.github_sync_circuit_breaker_reset = 60
    config.security_scanning_enabled = False

    with (
        patch("memory.connectors.github.code_sync.MemoryStorage"),
        patch("memory.connectors.github.code_sync.get_qdrant_client"),
    ):
        CodeBlobSync(mock_client, config)

    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    prefix = "github-code-sync-"
    assert session_id.startswith(
        prefix
    ), f"Expected 'github-code-sync-{{date}}' prefix, got: {session_id!r}"
    assert _ISO_DATE_RE.match(
        session_id[len(prefix) :]
    ), f"Expected ISO date suffix (YYYY-MM-DD), got: {session_id[len(prefix):]!r}"


def test_code_blob_sync_does_not_override_existing_claude_session_id(monkeypatch):
    """BUG-251: CodeBlobSync.__init__() uses setdefault — must not override a pre-existing CLAUDE_SESSION_ID."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "real-session-abc123")

    mock_client = MagicMock()
    config = MagicMock()
    config.github_repo = "owner/repo"
    config.github_branch = "main"
    config.github_code_blob_max_size = 102400
    config.github_code_blob_include = ""
    config.github_code_blob_include_max_size = 512000
    config.github_code_blob_exclude = ""
    config.github_sync_circuit_breaker_threshold = 5
    config.github_sync_circuit_breaker_reset = 60
    config.security_scanning_enabled = False

    with (
        patch("memory.connectors.github.code_sync.MemoryStorage"),
        patch("memory.connectors.github.code_sync.get_qdrant_client"),
    ):
        CodeBlobSync(mock_client, config)

    assert os.environ["CLAUDE_SESSION_ID"] == "real-session-abc123"


def test_github_sync_engine_sets_claude_session_id(monkeypatch):
    """BUG-251: GitHubSyncEngine.__init__() sets CLAUDE_SESSION_ID with github-event-sync-{date} prefix."""
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_branch = "main"
    config.github_token.get_secret_value.return_value = "test-token"
    config.security_scanning_enabled = False

    with (
        patch("memory.connectors.github.sync.GitHubClient"),
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
    ):
        GitHubSyncEngine(config=config)

    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    prefix = "github-event-sync-"
    assert session_id.startswith(
        prefix
    ), f"Expected 'github-event-sync-{{date}}' prefix, got: {session_id!r}"
    assert _ISO_DATE_RE.match(
        session_id[len(prefix) :]
    ), f"Expected ISO date suffix (YYYY-MM-DD), got: {session_id[len(prefix):]!r}"


def test_github_sync_engine_does_not_override_existing_claude_session_id(monkeypatch):
    """BUG-251: GitHubSyncEngine.__init__() uses setdefault — must not override a pre-existing CLAUDE_SESSION_ID."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "real-session-xyz789")

    config = MagicMock()
    config.github_sync_enabled = True
    config.github_repo = "owner/repo"
    config.github_branch = "main"
    config.github_token.get_secret_value.return_value = "test-token"
    config.security_scanning_enabled = False

    with (
        patch("memory.connectors.github.sync.GitHubClient"),
        patch("memory.connectors.github.sync.MemoryStorage"),
        patch("memory.connectors.github.sync.get_qdrant_client"),
    ):
        GitHubSyncEngine(config=config)

    assert os.environ["CLAUDE_SESSION_ID"] == "real-session-xyz789"


# -- Batch _update_last_synced (Issue #102) ------------------------------------


def test_batch_update_last_synced_one_scroll_one_set_payload():
    """_batch_update_last_synced does ONE scroll and ONE set_payload, not per-file."""
    sync = _make_sync_instance()
    sync.qdrant = MagicMock()

    file_paths = ["src/a.py", "src/b.py", "src/c.py"]
    points = [MagicMock(id=f"pt-{i}") for i in range(3)]
    sync.qdrant.scroll.return_value = (points, None)

    sync._batch_update_last_synced(file_paths)

    # Exactly ONE scroll call regardless of number of files
    assert sync.qdrant.scroll.call_count == 1

    # The scroll filter must use MatchAny for file_path
    call_kwargs = sync.qdrant.scroll.call_args.kwargs
    filter_conditions = call_kwargs["scroll_filter"].must
    match_any_conditions = [c for c in filter_conditions if hasattr(c.match, "any")]
    assert len(match_any_conditions) == 1
    assert set(match_any_conditions[0].match.any) == set(file_paths)

    # Exactly ONE set_payload call with all 3 point IDs
    sync.qdrant.set_payload.assert_called_once()
    set_payload_kwargs = sync.qdrant.set_payload.call_args.kwargs
    assert len(set_payload_kwargs["points"]) == 3
    assert "last_synced" in set_payload_kwargs["payload"]


@pytest.mark.asyncio
async def test_sync_code_blobs_collects_unchanged_and_calls_batch():
    """sync_code_blobs collects unchanged paths and delegates to _batch_update_last_synced."""
    sync = _make_sync_instance()
    sync.client.get_tree = AsyncMock(
        return_value=[
            {"path": "src/x.py", "type": "blob", "sha": "sha-x", "size": 100},
            {"path": "src/y.py", "type": "blob", "sha": "sha-y", "size": 100},
            {"path": "src/z.py", "type": "blob", "sha": "sha-z-new", "size": 100},
        ]
    )

    mock_batch = MagicMock()
    mock_sync_file = AsyncMock(return_value=2)

    with (
        patch.object(
            sync,
            "_get_stored_blob_map",
            return_value={"src/x.py": "sha-x", "src/y.py": "sha-y"},
        ),
        patch.object(sync, "_batch_update_last_synced", mock_batch),
        patch.object(sync, "_sync_file", mock_sync_file),
        patch.object(
            sync, "_detect_deleted_files", new_callable=AsyncMock, return_value=0
        ),
        patch.object(sync, "_push_metrics"),
    ):
        result = await sync.sync_code_blobs("batch-1")

    # Two unchanged files → batch called with both paths
    mock_batch.assert_called_once()
    batch_paths = mock_batch.call_args.args[0]
    assert set(batch_paths) == {"src/x.py", "src/y.py"}

    # One changed file → synced normally
    assert result.files_synced == 1
    assert result.files_skipped == 2


def test_batch_update_last_synced_empty_list_no_qdrant_calls():
    """Empty file_paths list → no Qdrant operations at all."""
    sync = _make_sync_instance()
    sync.qdrant = MagicMock()

    sync._batch_update_last_synced([])

    sync.qdrant.scroll.assert_not_called()
    sync.qdrant.set_payload.assert_not_called()


def test_batch_update_last_synced_pagination():
    """_batch_update_last_synced paginates through >100 points, then ONE set_payload."""
    sync = _make_sync_instance()
    sync.qdrant = MagicMock()

    file_paths = [f"src/file_{i}.py" for i in range(5)]

    # First page: 100 points, second page: 30 points
    page1 = [MagicMock(id=f"pt-{i}") for i in range(100)]
    page2 = [MagicMock(id=f"pt-{100 + i}") for i in range(30)]
    sync.qdrant.scroll.side_effect = [
        (page1, "offset-page-2"),
        (page2, None),
    ]

    sync._batch_update_last_synced(file_paths)

    # Two scroll calls due to pagination
    assert sync.qdrant.scroll.call_count == 2

    # ONE set_payload call with all 130 IDs
    sync.qdrant.set_payload.assert_called_once()
    set_payload_kwargs = sync.qdrant.set_payload.call_args.kwargs
    assert len(set_payload_kwargs["points"]) == 130
    assert "last_synced" in set_payload_kwargs["payload"]


def test_batch_update_last_synced_no_points_skips_set_payload():
    """Scroll returns no points → set_payload not called."""
    sync = _make_sync_instance()
    sync.qdrant = MagicMock()
    sync.qdrant.scroll.return_value = ([], None)

    sync._batch_update_last_synced(["src/gone.py"])

    sync.qdrant.scroll.assert_called_once()
    sync.qdrant.set_payload.assert_not_called()


def test_batch_update_last_synced_scroll_exception_handled():
    """scroll raises → warning logged → method returns without raising."""
    sync = _make_sync_instance()
    sync.qdrant = MagicMock()
    sync.qdrant.scroll.side_effect = Exception("Connection reset")

    sync._batch_update_last_synced(["src/file.py"])  # Should not raise

    sync.qdrant.set_payload.assert_not_called()
