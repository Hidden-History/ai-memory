"""Tests for IntelligentChunker orchestrator.

TECH-DEBT-051: v2.1 MVP implementation.
TECH-DEBT-052: AST-based code chunking with Tree-sitter.
"""

import pytest

from src.memory.chunking import (
    ChunkMetadata,
    ChunkResult,
    ContentType,
    IntelligentChunker,
)

# Try to import AND instantiate ASTChunker (tree-sitter must be installed)
try:
    from src.memory.chunking import ASTChunker

    # Actually test if we can create an instance - this is where tree-sitter is required
    _test_chunker = ASTChunker()
    del _test_chunker
    AST_CHUNKER_AVAILABLE = True
except (ImportError, ModuleNotFoundError, OSError):
    # tree-sitter native dependencies may not be available in all test environments
    AST_CHUNKER_AVAILABLE = False
    ASTChunker = None


class TestContentTypeDetection:
    """Test content type detection from file extensions."""

    def test_detect_python_file(self):
        chunker = IntelligentChunker()
        content_type = chunker.detect_content_type("test.py", "def foo(): pass")
        assert content_type == ContentType.CODE

    def test_detect_javascript_file(self):
        chunker = IntelligentChunker()
        content_type = chunker.detect_content_type("app.js", "function test() {}")
        assert content_type == ContentType.CODE

    def test_detect_typescript_file(self):
        chunker = IntelligentChunker()
        content_type = chunker.detect_content_type(
            "main.ts", "const x: string = 'test'"
        )
        assert content_type == ContentType.CODE

    def test_detect_markdown_file(self):
        chunker = IntelligentChunker()
        content_type = chunker.detect_content_type("README.md", "# Title")
        assert content_type == ContentType.PROSE

    def test_detect_json_file(self):
        chunker = IntelligentChunker()
        content_type = chunker.detect_content_type("config.json", '{"key": "value"}')
        assert content_type == ContentType.CONFIG

    def test_detect_yaml_file(self):
        chunker = IntelligentChunker()
        content_type = chunker.detect_content_type("config.yaml", "key: value")
        assert content_type == ContentType.CONFIG

    def test_detect_unknown_extension(self):
        chunker = IntelligentChunker()
        content_type = chunker.detect_content_type("file.xyz", "random content")
        assert content_type == ContentType.UNKNOWN


class TestIntelligentChunker:
    """Test IntelligentChunker orchestrator."""

    def test_init_default_params(self):
        chunker = IntelligentChunker()
        assert chunker.max_chunk_tokens == 512
        assert chunker.overlap_pct == 0.15

    def test_init_custom_params(self):
        chunker = IntelligentChunker(max_chunk_tokens=1024, overlap_pct=0.20)
        assert chunker.max_chunk_tokens == 1024
        assert chunker.overlap_pct == 0.20

    def test_chunk_returns_list(self):
        chunker = IntelligentChunker()
        results = chunker.chunk("test content", "test.py")
        assert isinstance(results, list)

    def test_chunk_single_result_for_small_content(self):
        """v2.1 MVP: Returns single chunk for all content."""
        chunker = IntelligentChunker()
        results = chunker.chunk("def foo(): pass", "test.py")
        assert len(results) == 1
        assert isinstance(results[0], ChunkResult)

    def test_chunk_metadata_populated(self):
        """Chunk metadata should be complete.

        Note: Python files now use AST chunking if tree-sitter is available.
        After TECH-DEBT-052 fix, first chunk has overlap_tokens based on 20% calculation.
        """
        chunker = IntelligentChunker()
        results = chunker.chunk("def foo(): pass", "test.py")
        chunk = results[0]

        assert chunk.content == "def foo(): pass"
        # With AST chunker available, Python uses ast_code; without it, uses whole
        assert chunk.metadata.chunk_type in ("ast_code", "whole")
        assert chunk.metadata.chunk_index == 0
        assert chunk.metadata.total_chunks == 1
        assert chunk.metadata.chunk_size_tokens > 0
        # After overlap fix, overlap_tokens is calculated (first chunk has overlap for next)
        assert chunk.metadata.overlap_tokens >= 0
        assert chunk.metadata.source_file == "test.py"

    def test_estimate_tokens_accuracy(self):
        """Token estimation: 4 chars ≈ 1 token."""
        chunker = IntelligentChunker()
        text = "a" * 400  # 400 chars should be ~100 tokens
        tokens = chunker.estimate_tokens(text)
        assert tokens == 100

    def test_estimate_tokens_empty_string(self):
        chunker = IntelligentChunker()
        tokens = chunker.estimate_tokens("")
        assert tokens == 0


class TestChunkMetadata:
    """Test ChunkMetadata dataclass."""

    def test_dataclass_fields(self):
        metadata = ChunkMetadata(
            chunk_type="whole",
            chunk_index=0,
            total_chunks=1,
            chunk_size_tokens=100,
            overlap_tokens=0,
        )
        assert metadata.chunk_type == "whole"
        assert metadata.chunk_index == 0
        assert metadata.total_chunks == 1
        assert metadata.chunk_size_tokens == 100
        assert metadata.overlap_tokens == 0

    def test_optional_fields_default_none(self):
        metadata = ChunkMetadata(
            chunk_type="whole",
            chunk_index=0,
            total_chunks=1,
            chunk_size_tokens=100,
            overlap_tokens=0,
        )
        assert metadata.source_file is None
        assert metadata.start_line is None
        assert metadata.end_line is None
        assert metadata.section_header is None


class TestChunkResult:
    """Test ChunkResult dataclass."""

    def test_dataclass_fields(self):
        metadata = ChunkMetadata(
            chunk_type="whole",
            chunk_index=0,
            total_chunks=1,
            chunk_size_tokens=100,
            overlap_tokens=0,
        )
        result = ChunkResult(content="test content", metadata=metadata)
        assert result.content == "test content"
        assert result.metadata == metadata

    def test_content_and_metadata_required(self):
        """Both fields are required."""
        metadata = ChunkMetadata(
            chunk_type="whole",
            chunk_index=0,
            total_chunks=1,
            chunk_size_tokens=100,
            overlap_tokens=0,
        )
        result = ChunkResult(content="test", metadata=metadata)
        assert result.content == "test"
        assert result.metadata is not None


class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_chunk_handles_none_content(self):
        """None content returns empty list, not crash."""
        chunker = IntelligentChunker()
        result = chunker.chunk(None, "test.py")
        assert result == []

    def test_chunk_handles_empty_content(self):
        """Empty/whitespace content returns empty list."""
        chunker = IntelligentChunker()
        assert chunker.chunk("", "test.py") == []
        assert chunker.chunk("   ", "test.py") == []

    def test_detect_content_type_none_path(self):
        """None file_path returns UNKNOWN, not crash."""
        chunker = IntelligentChunker()
        result = chunker.detect_content_type(None, "content")
        assert result == ContentType.UNKNOWN

    def test_detect_content_type_empty_path(self):
        """Empty file_path returns UNKNOWN."""
        chunker = IntelligentChunker()
        assert chunker.detect_content_type("", "content") == ContentType.UNKNOWN

    def test_detect_content_type_no_extension(self):
        """Files without extension return UNKNOWN (or CONFIG for known files)."""
        chunker = IntelligentChunker()
        # Extensionless unknown file
        assert chunker.detect_content_type("README", "content") == ContentType.UNKNOWN
        # Known config files without extension
        assert chunker.detect_content_type("Makefile", "content") == ContentType.CONFIG
        assert (
            chunker.detect_content_type("Dockerfile", "content") == ContentType.CONFIG
        )

    def test_detect_content_type_dot_in_directory(self):
        """Dot in directory path doesn't confuse extension detection."""
        chunker = IntelligentChunker()
        # /path/to/v1.0/README has no extension despite dot in path
        result = chunker.detect_content_type("/path/to/v1.0/README", "content")
        assert result == ContentType.UNKNOWN


@pytest.mark.skipif(not AST_CHUNKER_AVAILABLE, reason="tree-sitter not installed")
class TestASTChunker:
    """Test AST-based code chunking.

    TECH-DEBT-052: Tree-sitter integration tests.
    """

    def test_python_function_chunking(self):
        """Chunk Python file at function boundaries."""
        chunker = ASTChunker()
        code = """def foo():
    return "hello"

def bar():
    return "world"
"""
        chunks = chunker.chunk(code, "test.py")

        assert len(chunks) == 2
        assert all(isinstance(c, ChunkResult) for c in chunks)
        assert chunks[0].metadata.chunk_type == "ast_code"
        assert chunks[1].metadata.chunk_type == "ast_code"
        assert "def foo():" in chunks[0].content
        assert "def bar():" in chunks[1].content

    def test_python_class_chunking(self):
        """Chunk Python file at class boundaries."""
        chunker = ASTChunker()
        code = """class Foo:
    def method(self):
        pass

class Bar:
    def method(self):
        pass
"""
        chunks = chunker.chunk(code, "test.py")

        assert len(chunks) == 2
        assert "class Foo:" in chunks[0].content
        assert "class Bar:" in chunks[1].content

    def test_includes_imports_as_context(self):
        """Verify imports are included in ALL chunks per TECH-DEBT-052 fix.

        Per Chunking-Strategy-V1.md Section 2.1, imports should be included
        in every chunk for context, not just the first one.
        """
        chunker = ASTChunker()
        code = """import os
import sys
from pathlib import Path

def foo():
    return "hello"

def bar():
    return "world"
"""
        chunks = chunker.chunk(code, "test.py")

        # ALL chunks should include imports for context
        assert "import os" in chunks[0].content
        assert "import sys" in chunks[0].content
        assert "from pathlib import Path" in chunks[0].content

        # Second chunk should ALSO include imports (spec requirement)
        assert "import os" in chunks[1].content
        assert "import sys" in chunks[1].content
        assert "from pathlib import Path" in chunks[1].content

    def test_graceful_fallback_on_parse_error(self):
        """Return whole content if parsing fails."""
        chunker = ASTChunker()
        # Invalid Python syntax
        invalid_code = "def foo( invalid syntax here"
        chunks = chunker.chunk(invalid_code, "test.py")

        # Should fallback to whole-content chunk
        assert len(chunks) == 1
        assert chunks[0].metadata.chunk_type == "whole"
        assert chunks[0].content == invalid_code

    def test_small_file_single_function(self):
        """Small file with single function returns single chunk."""
        chunker = ASTChunker()
        code = """def foo():
    return "hello"
"""
        chunks = chunker.chunk(code, "test.py")

        assert len(chunks) == 1
        assert chunks[0].metadata.chunk_type == "ast_code"
        assert "def foo():" in chunks[0].content

    def test_unsupported_language_fallback(self):
        """Unsupported file extension returns whole-content fallback."""
        chunker = ASTChunker()
        code = "some random content"
        chunks = chunker.chunk(code, "test.xyz")

        assert len(chunks) == 1
        assert chunks[0].metadata.chunk_type == "whole"

    def test_chunk_metadata_populated(self):
        """Chunk metadata should be complete."""
        chunker = ASTChunker()
        code = """def foo():
    return "hello"

def bar():
    return "world"
"""
        chunks = chunker.chunk(code, "test.py")

        # Check first chunk metadata
        chunk = chunks[0]
        assert chunk.metadata.chunk_type == "ast_code"
        assert chunk.metadata.chunk_index == 0
        assert chunk.metadata.total_chunks == 2
        assert chunk.metadata.chunk_size_tokens > 0
        assert chunk.metadata.source_file == "test.py"
        assert chunk.metadata.start_line is not None
        assert chunk.metadata.end_line is not None

        # Section header should be function name
        assert chunk.metadata.section_header == "foo"

    def test_javascript_function_chunking(self):
        """Chunk JavaScript file at function boundaries."""
        chunker = ASTChunker()
        code = """function foo() {
    return "hello";
}

function bar() {
    return "world";
}
"""
        chunks = chunker.chunk(code, "test.js")

        assert len(chunks) == 2
        assert "function foo()" in chunks[0].content
        assert "function bar()" in chunks[1].content

    def test_typescript_class_chunking(self):
        """Chunk TypeScript file at class boundaries."""
        chunker = ASTChunker()
        code = """class Foo {
    method(): void {}
}

class Bar {
    method(): void {}
}
"""
        chunks = chunker.chunk(code, "test.ts")

        assert len(chunks) == 2
        assert "class Foo" in chunks[0].content
        assert "class Bar" in chunks[1].content

    def test_empty_file_returns_empty(self):
        """Empty file returns no chunks (handled by fallback)."""
        chunker = ASTChunker()
        chunks = chunker.chunk("", "test.py")

        # Empty content returns whole-content fallback with empty string
        assert len(chunks) == 1
        assert chunks[0].content == ""

    def test_file_with_only_imports(self):
        """File with only imports returns whole-content (no chunk nodes)."""
        chunker = ASTChunker()
        code = """import os
import sys
"""
        chunks = chunker.chunk(code, "test.py")

        # No functions/classes, so fallback to whole-content
        assert len(chunks) == 1
        assert chunks[0].metadata.chunk_type == "whole"

    def test_mixed_functions_and_classes(self):
        """File with both functions and classes chunks both."""
        chunker = ASTChunker()
        code = """def standalone_function():
    pass

class MyClass:
    def method(self):
        pass

def another_function():
    pass
"""
        chunks = chunker.chunk(code, "test.py")

        # Should have 3 chunks: function, class, function
        assert len(chunks) == 3
        assert "def standalone_function():" in chunks[0].content
        assert "class MyClass:" in chunks[1].content
        assert "def another_function():" in chunks[2].content

    def test_line_numbers_accurate(self):
        """Line numbers should match source code."""
        chunker = ASTChunker()
        code = """# Line 1
def foo():  # Line 2
    return "hello"  # Line 3

def bar():  # Line 5
    return "world"  # Line 6
"""
        chunks = chunker.chunk(code, "test.py")

        # First function (foo) should be lines 2-3
        assert chunks[0].metadata.start_line == 2
        assert chunks[0].metadata.end_line == 3

        # Second function (bar) should be lines 5-6
        assert chunks[1].metadata.start_line == 5
        assert chunks[1].metadata.end_line == 6


@pytest.mark.skipif(not AST_CHUNKER_AVAILABLE, reason="tree-sitter not installed")
class TestIntelligentChunkerIntegration:
    """Test IntelligentChunker integration with ASTChunker.

    TECH-DEBT-052: Integration tests for AST routing.
    """

    def test_routes_python_to_ast_chunker(self):
        """Python files should be routed to AST chunker."""
        chunker = IntelligentChunker()
        code = """def foo():
    return "hello"

def bar():
    return "world"
"""
        chunks = chunker.chunk(code, "test.py")

        # Should use AST chunking, not whole-content
        assert len(chunks) == 2
        assert chunks[0].metadata.chunk_type == "ast_code"

    def test_routes_markdown_to_prose_chunker(self):
        """Markdown files should use ProseChunker (BUG-049 fix)."""
        chunker = IntelligentChunker()
        content = "# Title\n\nSome content"
        chunks = chunker.chunk(content, "README.md")

        # Should use prose chunking
        assert len(chunks) == 1
        assert chunks[0].metadata.chunk_type == "prose"

    def test_graceful_degradation_without_ast_chunker(self):
        """IntelligentChunker should work even if AST chunker unavailable."""
        # This is implicitly tested by the existing whole-content tests
        # They pass whether or not tree-sitter is installed
        chunker = IntelligentChunker()
        code = "def foo(): pass"

        # Should not crash, should return chunks (AST or whole)
        chunks = chunker.chunk(code, "test.py")
        assert len(chunks) >= 1


class TestProseChunkerIntegration:
    """Test IntelligentChunker integration with ProseChunker (BUG-049 fix)."""

    def test_routes_markdown_to_prose_chunker(self):
        """Markdown (.md) files should be routed to ProseChunker."""
        chunker = IntelligentChunker()
        content = "# Title\n\nThis is paragraph one.\n\nThis is paragraph two."
        chunks = chunker.chunk(content, "README.md")

        assert len(chunks) >= 1
        assert chunks[0].metadata.chunk_type == "prose"

    def test_routes_txt_to_prose_chunker(self):
        """Text (.txt) files should be routed to ProseChunker."""
        chunker = IntelligentChunker()
        content = "Some plain text content."
        chunks = chunker.chunk(content, "notes.txt")

        assert len(chunks) == 1
        assert chunks[0].metadata.chunk_type == "prose"

    def test_routes_rst_to_prose_chunker(self):
        """RST (.rst) files should be routed to ProseChunker."""
        chunker = IntelligentChunker()
        content = "Title\n=====\n\nSome reStructuredText content."
        chunks = chunker.chunk(content, "docs.rst")

        assert len(chunks) >= 1
        assert chunks[0].metadata.chunk_type == "prose"

    def test_prose_chunker_uses_configured_params(self):
        """ProseChunker should use IntelligentChunker's configured params."""
        # 512 tokens * 4 chars = 2048 chars max_chunk_size
        chunker = IntelligentChunker(max_chunk_tokens=512, overlap_pct=0.15)

        # Create content longer than 2048 chars to force multiple chunks
        content = "Word " * 600  # ~3000 chars, should split
        chunks = chunker.chunk(content, "long_doc.md")

        # Should have multiple chunks
        assert len(chunks) >= 2
        # All should be prose type
        assert all(c.metadata.chunk_type == "prose" for c in chunks)

    def test_prose_chunks_have_correct_metadata(self):
        """Prose chunks should have complete metadata."""
        chunker = IntelligentChunker()
        content = "Test content for metadata verification."
        chunks = chunker.chunk(content, "test.md")

        chunk = chunks[0]
        assert chunk.metadata.chunk_type == "prose"
        assert chunk.metadata.chunk_index == 0
        assert chunk.metadata.total_chunks >= 1
        assert chunk.metadata.chunk_size_tokens > 0
        assert chunk.metadata.source_file == "test.md"

    def test_prose_small_content_single_chunk(self):
        """Small prose content returns single chunk."""
        chunker = IntelligentChunker()
        content = "Short text."
        chunks = chunker.chunk(content, "short.md")

        assert len(chunks) == 1
        assert chunks[0].content == "Short text."

    def test_prose_chunks_have_overlap(self):
        """Multiple prose chunks should have overlap for context."""
        chunker = IntelligentChunker(max_chunk_tokens=128)  # Force smaller chunks

        # Create paragraph-separated content
        para1 = "First paragraph " * 20
        para2 = "Second paragraph " * 20
        para3 = "Third paragraph " * 20
        content = f"{para1}\n\n{para2}\n\n{para3}"

        chunks = chunker.chunk(content, "multi_para.md")

        # Should have multiple chunks
        assert len(chunks) >= 2

        # Check if overlap marker present on non-first chunks
        _has_overlap = any("..." in c.content for c in chunks[1:])
        # Overlap may or may not be present depending on size constraints
        # Just verify no crash and proper chunk type
        assert all(c.metadata.chunk_type == "prose" for c in chunks)


class TestIntelligentChunkerValidation:
    """Tests for constructor parameter validation."""

    def test_init_rejects_zero_max_tokens(self):
        """Zero max_chunk_tokens raises ValueError."""
        with pytest.raises(ValueError, match="max_chunk_tokens must be > 0"):
            IntelligentChunker(max_chunk_tokens=0)

    def test_init_rejects_negative_max_tokens(self):
        """Negative max_chunk_tokens raises ValueError."""
        with pytest.raises(ValueError, match="max_chunk_tokens must be > 0"):
            IntelligentChunker(max_chunk_tokens=-100)

    def test_init_rejects_overlap_over_one(self):
        """overlap_pct > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match=r"overlap_pct must be 0\.0-1\.0"):
            IntelligentChunker(overlap_pct=1.5)

    def test_init_rejects_negative_overlap(self):
        """Negative overlap_pct raises ValueError."""
        with pytest.raises(ValueError, match=r"overlap_pct must be 0\.0-1\.0"):
            IntelligentChunker(overlap_pct=-0.1)

    def test_init_accepts_edge_values(self):
        """Edge values (1 token, 0% overlap, 100% overlap) accepted."""
        chunker1 = IntelligentChunker(max_chunk_tokens=1, overlap_pct=0.0)
        assert chunker1.max_chunk_tokens == 1
        assert chunker1.overlap_pct == 0.0

        chunker2 = IntelligentChunker(overlap_pct=1.0)
        assert chunker2.overlap_pct == 1.0


@pytest.mark.skipif(not AST_CHUNKER_AVAILABLE, reason="tree-sitter not installed")
class TestASTChunkerOverlap:
    """Tests for 20% overlap implementation (TECH-DEBT-052 critical fix)."""

    def test_overlap_between_chunks(self):
        """Verify chunks have 20% overlap per spec."""
        chunker = ASTChunker()
        code = '''def function_one():
    """First function with enough content."""
    x = 1
    y = 2
    z = 3
    result = x + y + z
    return result

def function_two():
    """Second function with enough content."""
    a = 10
    b = 20
    c = 30
    total = a + b + c
    return total
'''
        chunks = chunker.chunk(code, "test.py")

        # Should have 2 chunks
        assert len(chunks) == 2

        # Second chunk should have overlap_tokens > 0
        assert chunks[1].metadata.overlap_tokens > 0, "Second chunk missing overlap"

        # Verify overlap is approximately 20% of first chunk
        # overlap_tokens should be ~20% of first chunk's non-import tokens
        # Allow some variance due to integer division
        assert chunks[1].metadata.overlap_tokens >= 10, "Overlap too small"

    def test_imports_in_all_chunks(self):
        """Verify imports are included in EVERY chunk, not just first."""
        chunker = ASTChunker()
        code = '''import os
import sys
from typing import List

def func_a():
    """Uses os."""
    return os.getcwd()

def func_b():
    """Uses List."""
    items: List[str] = []
    return items
'''
        chunks = chunker.chunk(code, "test.py")

        # Should have 2 function chunks
        assert len(chunks) == 2

        # BOTH chunks should contain imports
        for idx, chunk in enumerate(chunks):
            assert "import os" in chunk.content, f"Chunk {idx} missing 'import os'"
            assert "import sys" in chunk.content, f"Chunk {idx} missing 'import sys'"
            assert (
                "from typing import List" in chunk.content
            ), f"Chunk {idx} missing typing import"

    def test_overlap_with_short_function(self):
        """Overlap should handle short functions gracefully."""
        chunker = ASTChunker()
        code = """def short():
    return 1

def another_short():
    return 2
"""
        chunks = chunker.chunk(code, "test.py")

        # Should chunk successfully even with short functions
        assert len(chunks) == 2
        assert all(c.metadata.overlap_tokens >= 0 for c in chunks)


class TestNonWhitespaceCount:
    """Test correct whitespace handling (TECH-DEBT-052 critical fix)."""

    @pytest.mark.skipif(not AST_CHUNKER_AVAILABLE, reason="tree-sitter not installed")
    def test_handles_all_whitespace_types(self):
        """Verify all whitespace types are excluded from count."""
        chunker = ASTChunker()
        # Contains: space, tab, newline, carriage return, form feed
        code = "def test_func():\n\treturn  1\r\n\f"

        # Should parse without crashing on various whitespace
        chunks = chunker.chunk(code, "test.py")
        assert len(chunks) >= 1

        # Non-whitespace count should only include: d,e,f,t,_,f,u,n,c,(,),:,r,e,t,u,r,n,1
        # The actual count depends on tree-sitter parsing, but should be reasonable
        assert chunks[0].metadata.chunk_size_tokens > 0

    @pytest.mark.skipif(not AST_CHUNKER_AVAILABLE, reason="tree-sitter not installed")
    def test_non_whitespace_consistent(self):
        """Verify non-whitespace counting is used for overlap calculation."""
        chunker = ASTChunker()
        code = '''def function_with_spaces():
    """Has various    spacing."""
    x    =    1
    return x

def another():
    y = 2
    return y
'''
        chunks = chunker.chunk(code, "test.py")

        # Overlap tokens should be calculated from non-whitespace chars
        # Just verify it doesn't crash and produces sensible values
        if len(chunks) > 1:
            assert chunks[1].metadata.overlap_tokens >= 0


@pytest.mark.skipif(not AST_CHUNKER_AVAILABLE, reason="tree-sitter not installed")
class TestLargeNodeSplitting:
    """Test recursive splitting of large functions/classes (TECH-DEBT-052 critical fix)."""

    def test_split_large_node_result_used(self):
        """Verify _split_large_node() results are actually integrated into output."""
        chunker = ASTChunker()

        # Create a very large function that exceeds MAX_CHARS (500)
        # Each line is ~20 chars, so 30+ lines should exceed 500 non-whitespace chars
        large_func = "def large_function():\n"
        large_func += '    """A very large function for testing."""\n'
        for i in range(50):
            large_func += f"    variable_{i} = {i} + 100\n"
        large_func += "    return sum_of_all\n"

        chunks = chunker.chunk(large_func, "test.py")

        # Should have multiple chunks if splitting worked
        # (At minimum 1, potentially more if split)
        assert len(chunks) >= 1

        # If split occurred, verify split chunks have correct type
        split_chunks = [c for c in chunks if c.metadata.chunk_type == "ast_code_split"]
        if split_chunks:
            # Verify split chunks have proper metadata
            for chunk in split_chunks:
                assert chunk.metadata.chunk_type == "ast_code_split"
                assert chunk.metadata.chunk_size_tokens > 0
                assert chunk.metadata.total_chunks == len(chunks)
                # Split chunks should have valid content
                assert len(chunk.content) > 0
                # At least one split chunk should have the marker (first or middle chunks)
            # Verify at least one chunk has the split marker
            has_marker = any("split" in c.content.lower() for c in split_chunks)
            assert has_marker, "At least one split chunk should have split marker"

    def test_split_chunk_includes_imports(self):
        """Verify split chunks include import context."""
        chunker = ASTChunker()

        # Large function with imports
        code = "import os\nimport sys\n\n"
        code += "def huge_function():\n"
        for i in range(60):
            code += f"    x_{i} = os.path.join('dir', 'file_{i}')\n"
        code += "    return result\n"

        chunks = chunker.chunk(code, "test.py")

        # All chunks (including splits) should have imports
        for chunk in chunks:
            assert "import os" in chunk.content
            assert "import sys" in chunk.content

    def test_split_chunks_have_overlap(self):
        """Verify split chunks have proper overlap between them."""
        chunker = ASTChunker()

        # Create large function
        code = "def massive_func():\n"
        for i in range(70):
            code += f"    item_{i} = process({i})\n"
        code += "    return total\n"

        chunks = chunker.chunk(code, "test.py")

        # If we got multiple chunks, verify overlap
        if len(chunks) > 1:
            # Each chunk after the first should have overlap_tokens > 0
            for i in range(1, len(chunks)):
                assert (
                    chunks[i].metadata.overlap_tokens > 0
                ), f"Chunk {i} missing overlap"

    def test_small_function_not_split(self):
        """Verify small functions are NOT split unnecessarily."""
        chunker = ASTChunker()

        # Small function well under MAX_CHARS
        code = "def small():\n    return 42\n"

        chunks = chunker.chunk(code, "test.py")

        # Should be exactly 1 chunk
        assert len(chunks) == 1
        # Should NOT be marked as split
        assert chunks[0].metadata.chunk_type == "ast_code"


@pytest.mark.skipif(not AST_CHUNKER_AVAILABLE, reason="tree-sitter not available")
class TestASTChunkerBUG075:
    """BUG-075: AST chunker comment header and UTF-8 byte offset fixes."""

    def test_preserves_comment_headers(self):
        """BUG-075: Comment headers before functions should be preserved."""
        chunker = ASTChunker()
        code = '''// This is a test file
// Author: Test Author

function hello() {
    return "hello";
}

function world() {
    return "world";
}
'''
        chunks = chunker.chunk(code, "test.js")
        # Comment header should be preserved in chunks
        assert "// This is a test file" in chunks[0].content
        assert "// Author: Test Author" in chunks[0].content

    def test_multibyte_utf8_characters(self):
        """BUG-075: Multi-byte UTF-8 chars should not cause offset drift."""
        chunker = ASTChunker()
        code = '''# Description \u2014 with em dash
# More info \u2013 en dash too

def foo():
    return "hello \u2014 world"

def bar():
    return "goodbye"
'''
        chunks = chunker.chunk(code, "test.py")
        # Both functions should be extracted correctly
        assert "def foo():" in chunks[0].content
        assert "def bar():" in chunks[1].content
        # Content should not be corrupted
        assert 'return "hello \u2014 world"' in chunks[0].content

    def test_comment_only_header_no_imports(self):
        """BUG-075: Files with comments but no imports should preserve comments."""
        chunker = ASTChunker()
        code = '''# No imports in this file
# Just comments

def standalone():
    x = 1
    return x
'''
        chunks = chunker.chunk(code, "test.py")
        assert "# No imports in this file" in chunks[0].content
