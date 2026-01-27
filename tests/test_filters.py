"""Unit tests for memory filtering module.

Tests implementation pattern filtering to ensure junk patterns
are properly excluded while significant code is stored.

Phase A: Implementation Pattern Filtering
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from memory.filters import ImplementationFilter


class TestImplementationFilter:
    """Test suite for ImplementationFilter class."""

    def test_skip_markdown_files(self):
        """Should skip markdown files."""
        f = ImplementationFilter()
        assert f.should_store("README.md", "# Header\nSome text", "Write") is False

    def test_skip_json_files(self):
        """Should skip JSON configuration files."""
        f = ImplementationFilter()
        json_content = '{"key": "value", "nested": {"foo": "bar"}}'
        assert f.should_store("config.json", json_content, "Write") is False

    def test_skip_yaml_files(self):
        """Should skip YAML configuration files."""
        f = ImplementationFilter()
        yaml_content = "key: value\nnested:\n  foo: bar"
        assert f.should_store("config.yaml", yaml_content, "Write") is False

    def test_skip_small_changes(self):
        """Should skip changes below minimum line threshold."""
        f = ImplementationFilter()
        small_content = "x = 1\ny = 2\nz = 3"
        assert f.should_store("file.py", small_content, "Edit") is False

    def test_store_significant_function(self):
        """Should store content with function definitions."""
        f = ImplementationFilter()
        content = '''
def complex_function(arg1, arg2):
    """Docstring."""
    result = []
    for item in arg1:
        if item > arg2:
            result.append(item)
    return result
'''
        assert f.should_store("module.py", content, "Write") is True

    def test_store_class_definition(self):
        """Should store content with class definitions."""
        f = ImplementationFilter()
        content = '''
class MyClass:
    def __init__(self, value):
        self.value = value

    def get_value(self):
        return self.value

    def set_value(self, new_value):
        self.value = new_value
'''
        assert f.should_store("models.py", content, "Write") is True

    def test_store_import_block(self):
        """Should store content with significant import blocks."""
        f = ImplementationFilter()
        content = '''
import os
import sys
import json
from pathlib import Path
from typing import Optional

def main():
    pass
'''
        assert f.should_store("app.py", content, "Write") is True

    def test_skip_node_modules(self):
        """Should skip files in node_modules directory."""
        f = ImplementationFilter()
        content = "function x() { console.log('test'); }\n" * 20
        assert f.should_store("node_modules/pkg/index.js", content, "Write") is False

    def test_skip_venv(self):
        """Should skip files in virtual environment directories."""
        f = ImplementationFilter()
        content = "def foo():\n    pass\n" * 10
        assert f.should_store("venv/lib/python3.9/site-packages/module.py", content, "Write") is False

    def test_skip_pycache(self):
        """Should skip Python cache directories."""
        f = ImplementationFilter()
        content = "# compiled bytecode\n" * 15
        assert f.should_store("src/__pycache__/module.cpython-39.pyc", content, "Write") is False

    def test_skip_build_directories(self):
        """Should skip build/dist directories."""
        f = ImplementationFilter()
        content = "// build artifact\n" * 15
        assert f.should_store("dist/bundle.js", content, "Write") is False
        assert f.should_store("build/output.js", content, "Write") is False

    def test_environment_variable_min_lines(self):
        """Should respect BMAD_FILTER_MIN_LINES environment variable."""
        with patch.dict(os.environ, {'BMAD_FILTER_MIN_LINES': '20'}):
            f = ImplementationFilter()
            assert f.min_lines == 20

            # 15 lines of INSIGNIFICANT content should fail (below 20)
            # Use variable assignments (not significant) to test min_lines threshold
            short_content = "\n".join([f"x{i} = {i}" for i in range(15)])
            assert f.should_store("test.py", short_content, "Write") is False

            # 25 lines of insignificant content should pass (above 20)
            long_content = "\n".join([f"x{i} = {i}" for i in range(25)])
            assert f.should_store("test.py", long_content, "Write") is False  # Still insignificant

            # But significant content passes regardless of line count
            significant_short = "def foo():\n    pass\n" * 7  # 14 lines but significant
            assert f.should_store("test.py", significant_short, "Write") is True

    def test_environment_variable_skip_extensions(self):
        """Should respect BMAD_FILTER_SKIP_EXTENSIONS environment variable."""
        with patch.dict(os.environ, {'BMAD_FILTER_SKIP_EXTENSIONS': 'xyz,abc'}):
            f = ImplementationFilter()
            assert '.xyz' in f.skip_extensions
            assert '.abc' in f.skip_extensions

            content = "def foo():\n    pass\n" * 10
            assert f.should_store("test.xyz", content, "Write") is False
            assert f.should_store("test.abc", content, "Write") is False

    def test_is_significant_python_function(self):
        """Should detect Python function definitions."""
        f = ImplementationFilter()
        content = "def my_function(arg1, arg2):\n    return arg1 + arg2"
        assert f.is_significant(content) is True

    def test_is_significant_javascript_function(self):
        """Should detect JavaScript function definitions."""
        f = ImplementationFilter()
        content = "function myFunction(arg1, arg2) {\n    return arg1 + arg2;\n}"
        assert f.is_significant(content) is True

    def test_is_significant_class(self):
        """Should detect class definitions."""
        f = ImplementationFilter()
        content = "class MyClass:\n    pass"
        assert f.is_significant(content) is True

    def test_is_significant_decorator(self):
        """Should detect Python decorators."""
        f = ImplementationFilter()
        content = "@app.route('/api')\ndef handler():\n    pass"
        assert f.is_significant(content) is True

    def test_is_not_significant_variables(self):
        """Should not consider simple variable assignments significant."""
        f = ImplementationFilter()
        content = "x = 1\ny = 2\nz = 3\na = 4\nb = 5"
        assert f.is_significant(content) is False

    def test_is_not_significant_comments(self):
        """Should not consider only comments significant."""
        f = ImplementationFilter()
        content = "# Comment 1\n# Comment 2\n# Comment 3\n# Comment 4"
        assert f.is_significant(content) is False

    def test_truncate_content_under_limit(self):
        """Should not truncate content under max length."""
        f = ImplementationFilter()
        content = "def foo():\n    pass\n" * 50  # ~600 chars
        result = f.truncate_content(content)
        assert result == content
        assert "[TRUNCATED]" not in result

    def test_truncate_content_over_limit(self):
        """Should truncate content over max length."""
        f = ImplementationFilter()
        content = "x" * 6000  # Over 5000 char limit
        result = f.truncate_content(content)
        assert len(result) <= 5000
        assert result.endswith("[TRUNCATED]")

    def test_is_duplicate_not_found(self):
        """Should return False when content_hash not found."""
        f = ImplementationFilter()

        # Mock Qdrant client to return empty results
        with patch('memory.filters.get_qdrant_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.scroll.return_value = ([], None)  # Empty results
            mock_get_client.return_value = mock_client

            result = f.is_duplicate("sha256:abc123", "code-patterns")
            assert result is False

    def test_is_duplicate_found(self):
        """Should return True when content_hash exists."""
        f = ImplementationFilter()

        # Mock Qdrant client to return existing record
        with patch('memory.filters.get_qdrant_client') as mock_get_client:
            mock_client = MagicMock()
            mock_record = MagicMock()
            mock_record.id = "existing-uuid-123"
            mock_client.scroll.return_value = ([mock_record], None)
            mock_get_client.return_value = mock_client

            result = f.is_duplicate("sha256:abc123", "code-patterns")
            assert result is True

    def test_is_duplicate_error_fail_open(self):
        """Should fail open (return False) on Qdrant errors."""
        f = ImplementationFilter()

        # Mock Qdrant client to raise exception
        with patch('memory.filters.get_qdrant_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.scroll.side_effect = Exception("Qdrant unavailable")
            mock_get_client.return_value = mock_client

            result = f.is_duplicate("sha256:abc123", "code-patterns")
            assert result is False  # Fail open

    def test_typescript_interface(self):
        """Should detect TypeScript interface definitions."""
        f = ImplementationFilter()
        content = '''
interface User {
    id: string;
    name: string;
    email: string;
}
'''
        assert f.is_significant(content) is True

    def test_rust_struct(self):
        """Should detect Rust struct definitions."""
        f = ImplementationFilter()
        content = '''
struct Point {
    x: f64,
    y: f64,
}
'''
        assert f.is_significant(content) is True

    def test_go_function(self):
        """Should detect Go function definitions."""
        f = ImplementationFilter()
        content = '''
func calculateSum(a int, b int) int {
    return a + b
}
'''
        assert f.is_significant(content) is True

    def test_path_pattern_case_insensitive(self):
        """Should handle path patterns with different separators."""
        f = ImplementationFilter()
        content = "def foo():\n    pass\n" * 10

        # Both Unix and Windows paths
        assert f.should_store("src/node_modules/pkg/file.js", content, "Write") is False
        assert f.should_store("src\\node_modules\\pkg\\file.js", content, "Write") is False


class TestConversationFilter:
    """Test suite for conversation content filtering (TECH-DEBT-047-050)."""

    def test_filter_menu_patterns(self):
        """Should filter out UI menu patterns."""
        from memory.filters import filter_low_value_content

        content = """Hello Parzival.

**Menu:**
1. [MH] Redisplay Menu Help
2. [CH] Chat with the Agent
3. [PS] Party Start
─────────────────────────
Select by number."""

        result = filter_low_value_content(content)
        assert "[MH]" not in result
        assert "[CH]" not in result
        assert "[PS]" not in result
        assert "─────" not in result

    def test_filter_preserves_normal_content(self):
        """Should preserve normal conversation content."""
        from memory.filters import filter_low_value_content

        content = "I need help implementing the authentication module."
        result = filter_low_value_content(content)
        assert result == content

    def test_smart_truncate_at_sentence_boundary(self):
        """Should truncate at sentence boundaries."""
        from memory.filters import smart_truncate

        content = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = smart_truncate(content, max_length=40)

        assert result.endswith(".")
        assert "..." in result
        assert not result.endswith(". ...")  # No trailing space

    def test_smart_truncate_at_word_boundary(self):
        """Should truncate at word boundary if no sentence boundary."""
        from memory.filters import smart_truncate

        content = "This is a very long string without any punctuation marks at all"
        result = smart_truncate(content, max_length=30)

        assert not result.endswith(" ")  # No trailing space
        assert "..." in result
        # Should not cut mid-word
        words = content.split()
        truncated_text = result.replace("...", "").strip()
        # Every word in result should be a complete word from original
        for word in truncated_text.split():
            assert word in words

    def test_smart_truncate_no_truncation_needed(self):
        """Should not add ... if content fits."""
        from memory.filters import smart_truncate

        content = "Short text."
        result = smart_truncate(content, max_length=100)

        assert result == content
        assert "..." not in result

    def test_detect_duplicate_messages(self):
        """Should detect duplicate messages within time window."""
        from memory.filters import is_duplicate_message
        from datetime import datetime, UTC, timedelta

        now = datetime.now(UTC)
        messages = [
            {"content": "Same message", "timestamp": (now - timedelta(minutes=2)).isoformat()},
            {"content": "Different message", "timestamp": (now - timedelta(minutes=3)).isoformat()},
        ]

        # Same content within 5 minutes should be duplicate
        assert is_duplicate_message("Same message", now.isoformat(), messages, window_minutes=5) is True

        # Different content should not be duplicate
        assert is_duplicate_message("Unique message", now.isoformat(), messages, window_minutes=5) is False

    def test_detect_duplicate_outside_window(self):
        """Should not flag duplicates outside time window."""
        from memory.filters import is_duplicate_message
        from datetime import datetime, UTC, timedelta

        now = datetime.now(UTC)
        messages = [
            {"content": "Same message", "timestamp": (now - timedelta(minutes=10)).isoformat()},
        ]

        # Same content but outside 5-minute window
        assert is_duplicate_message("Same message", now.isoformat(), messages, window_minutes=5) is False

    def test_filter_truncated_ascii_diagrams(self):
        """Should filter out truncated ASCII diagrams."""
        from memory.filters import filter_low_value_content

        content = """Here is a diagram:
┌─────────────...
│  Component  ...
└─────────────...

And more text."""

        result = filter_low_value_content(content)
        # Truncated diagram lines should be removed
        assert "┌─────────────..." not in result
        assert "│  Component  ..." not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
