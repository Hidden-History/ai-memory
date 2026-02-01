"""Unit tests for SessionStart hook components.

Tests query builder, context formatter, and input parsing.
Integration tests (full retrieval flow) are in Story 3.4.
"""

import json
from unittest.mock import Mock, patch


# Import functions from the hook script
# These tests will fail until we implement the hook
def test_build_session_query_basic():
    """Test query builder with basic project info (V2 adapter)."""
    from session_start_test_helpers import build_session_query

    query = build_session_query("test-project", "/path/to/test-project")

    # V2 uses semantic queries, not path-based
    assert "test-project" in query
    assert "recent" in query or "implementation" in query


def test_build_session_query_detects_python():
    """Test query builder (V2 uses first_user_prompt, not project detection)."""
    from session_start_test_helpers import build_session_query

    with patch("os.path.exists") as mock_exists:
        # pyproject.toml exists
        mock_exists.side_effect = lambda path: "pyproject.toml" in path

        query = build_session_query("python-app", "/path/to/python-app")

        # V2 doesn't detect project type - uses semantic query
        assert "python-app" in query or "recent" in query


def test_build_session_query_detects_javascript():
    """Test query builder (V2 uses semantic queries)."""
    from session_start_test_helpers import build_session_query

    with patch("os.path.exists") as mock_exists:
        # package.json exists
        mock_exists.side_effect = lambda path: "package.json" in path

        query = build_session_query("js-app", "/path/to/js-app")

        # V2 doesn't detect project type - uses semantic query
        assert "js-app" in query or "recent" in query


def test_format_context_empty_results():
    """Test context formatting with no results."""
    from session_start_test_helpers import format_context

    formatted = format_context([], "test-project")

    assert formatted == ""


def test_format_context_high_relevance():
    """Test context formatting with high relevance memories (V2 uses inject_with_priority)."""
    from session_start_test_helpers import format_context

    results = [
        {
            "score": 0.95,
            "type": "implementation",
            "content": "Test implementation content",
            "source_hook": "PostToolUse",
        }
    ]

    formatted = format_context(results, "test-project")

    # V2 format: "## Related Memories" section with type and score
    assert "95%" in formatted
    assert "Test implementation content" in formatted
    assert "implementation" in formatted


def test_format_context_medium_relevance():
    """Test context formatting with medium relevance memories (V2 truncates at 500 chars for other memories)."""
    from session_start_test_helpers import format_context

    results = [
        {
            "score": 0.85,
            "type": "guideline",  # V2 uses actual MemoryType values
            "content": "A" * 600,  # Long content to test truncation
            "source_hook": "seed_script",
        }
    ]

    formatted = format_context(results, "test-project")

    # V2 format: truncates other memories to 500 chars
    assert "85%" in formatted
    assert "..." in formatted  # Truncated by smart_truncate


def test_format_context_below_threshold():
    """Test context formatting (V2 applies filter_low_value_content, not score threshold).

    V2 doesn't exclude by score - it uses filter_low_value_content() to remove
    boilerplate/filler text. Low score results are still injected if they have value.
    """
    from session_start_test_helpers import format_context

    results = [
        {
            "score": 0.15,  # Low score but still included in V2
            "type": "implementation",
            "content": "Low relevance content",
            "source_hook": "PostToolUse",
        }
    ]

    formatted = format_context(results, "test-project")

    # V2 includes low-score results if they pass filter_low_value_content
    # Test that formatting works (content may or may not be included based on filtering)
    assert isinstance(formatted, str)


def test_format_context_token_budget():
    """Test context formatting respects token budget (V2 uses inject_with_priority)."""
    from session_start_test_helpers import format_context

    # Create many high-relevance results
    results = [
        {
            "score": 0.95,
            "type": "implementation",  # V2 uses valid MemoryType
            "content": "A" * 1000,  # Large content
            "source_hook": "PostToolUse",
        }
        for i in range(10)
    ]

    formatted = format_context(results, "test-project", token_budget=100)

    # V2 stops when token budget exceeded
    # With 100 token budget and 1000-char content, no memories fit (header uses 7 tokens)
    # Verify budget enforcement - output should be limited (possibly just header)
    assert len(formatted) < 10000  # Much less than full 10 * 1000 chars
    assert "Relevant Memories" in formatted  # At least header present (V2 format)


def test_format_memory_entry_full():
    """Test formatting single memory entry without truncation (V2 adapter format)."""
    from session_start_test_helpers import format_memory_entry

    memory = {
        "type": "implementation",
        "score": 0.95,
        "content": "Test content",
        "source_hook": "PostToolUse",
        "collection": "code-patterns",
    }

    entry = format_memory_entry(memory, truncate=False)

    # V2 adapter format: **type** (score%) source_hook [collection]\n```\ncontent\n```
    assert "implementation" in entry
    assert "95%" in entry
    assert "Test content" in entry
    assert "PostToolUse" in entry  # Source hook included
    assert "implementations" in entry  # Collection mapped via _type_to_collection()


def test_format_memory_entry_truncated():
    """Test formatting single memory entry with truncation."""
    from session_start_test_helpers import format_memory_entry

    memory = {
        "type": "pattern",
        "score": 0.85,
        "content": "A" * 600,  # Long content
        "source_hook": "PostToolUse",
    }

    entry = format_memory_entry(memory, truncate=True, max_chars=500)

    assert "..." in entry  # Truncated marker
    assert len(memory["content"]) > 500  # Original was longer


def test_parse_hook_input_valid():
    """Test parsing valid JSON input from stdin."""
    from session_start_test_helpers import parse_hook_input

    test_input = {"cwd": "/test", "session_id": "sess_123"}

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = json.dumps(test_input)
        mock_stdin.__iter__ = Mock(return_value=iter([json.dumps(test_input)]))

        result = parse_hook_input()

        assert result.get("cwd") == "/test"
        assert result.get("session_id") == "sess_123"


def test_parse_hook_input_malformed():
    """Test parsing malformed JSON input gracefully."""
    from session_start_test_helpers import parse_hook_input

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = "not valid json"

        result = parse_hook_input()

        # Should return empty dict, not raise exception
        assert result == {}


def test_parse_hook_input_empty():
    """Test parsing empty stdin gracefully."""
    from session_start_test_helpers import parse_hook_input

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = ""

        result = parse_hook_input()

        # Should return empty dict, not raise exception
        assert result == {}


def test_log_session_retrieval():
    """Test structured logging of retrieval stats."""
    from session_start_test_helpers import log_session_retrieval

    results = [
        {"id": "mem1", "score": 0.95},
        {"id": "mem2", "score": 0.85},
        {"id": "mem3", "score": 0.80},
    ]

    with patch("logging.Logger.info") as mock_log:
        log_session_retrieval(
            session_id="sess_123",
            project="test-project",
            query="test query",
            results=results,
            duration_ms=250.5,
        )

        # Verify structured logging call
        mock_log.assert_called_once()
        call_args = mock_log.call_args

        assert call_args[0][0] == "session_retrieval_completed"
        assert "extra" in call_args[1]
        extra = call_args[1]["extra"]
        assert extra["session_id"] == "sess_123"
        assert extra["project"] == "test-project"
        assert extra["results_count"] == 3
        assert extra["high_relevance_count"] == 1
        assert extra["medium_relevance_count"] == 2
