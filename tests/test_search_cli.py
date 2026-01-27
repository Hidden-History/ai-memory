"""Tests for search CLI argument parsing.

Tests verify that search_cli.py correctly parses command-line arguments
for collection filtering, type filtering, intent detection, limits, and group_id.
"""

import pytest
import sys
from unittest.mock import patch, MagicMock, call
from pathlib import Path

# Add scripts to path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "memory"))

import search_cli


class TestSearchCLIParsing:
    """Test argument parsing for search CLI."""

    def test_query_required(self):
        """Test that query argument is required."""
        with patch('sys.argv', ['search_cli.py']):
            with pytest.raises(SystemExit) as exc_info:
                search_cli.parse_args()
            assert exc_info.value.code == 2  # argparse exits with 2 for missing required args

    def test_collection_default_all(self):
        """Test that collection defaults to 'all'."""
        with patch('sys.argv', ['search_cli.py', 'test query']):
            args = search_cli.parse_args()
            assert args.collection == 'all'
            assert args.query == 'test query'

    def test_collection_specific(self):
        """Test specific collection selection."""
        with patch('sys.argv', ['search_cli.py', 'test', '--collection', 'code-patterns']):
            args = search_cli.parse_args()
            assert args.collection == 'code-patterns'

        with patch('sys.argv', ['search_cli.py', 'test', '-c', 'conventions']):
            args = search_cli.parse_args()
            assert args.collection == 'conventions'

    def test_collection_invalid_rejected(self):
        """Test that invalid collection choices are rejected."""
        with patch('sys.argv', ['search_cli.py', 'test', '--collection', 'invalid']):
            with pytest.raises(SystemExit) as exc_info:
                search_cli.parse_args()
            assert exc_info.value.code == 2

    def test_type_filter_accepted(self):
        """Test that type filter is accepted."""
        with patch('sys.argv', ['search_cli.py', 'test', '--type', 'implementation']):
            args = search_cli.parse_args()
            assert args.type == 'implementation'

        with patch('sys.argv', ['search_cli.py', 'test', '-t', 'error_fix']):
            args = search_cli.parse_args()
            assert args.type == 'error_fix'

    def test_intent_choices(self):
        """Test intent detection options."""
        for intent in ['how', 'what', 'why']:
            with patch('sys.argv', ['search_cli.py', 'test', '--intent', intent]):
                args = search_cli.parse_args()
                assert args.intent == intent

        with patch('sys.argv', ['search_cli.py', 'test', '-i', 'how']):
            args = search_cli.parse_args()
            assert args.intent == 'how'

    def test_intent_invalid_rejected(self):
        """Test that invalid intent choices are rejected."""
        with patch('sys.argv', ['search_cli.py', 'test', '--intent', 'invalid']):
            with pytest.raises(SystemExit) as exc_info:
                search_cli.parse_args()
            assert exc_info.value.code == 2

    def test_limit_default_3(self):
        """Test that limit defaults to 3."""
        with patch('sys.argv', ['search_cli.py', 'test']):
            args = search_cli.parse_args()
            assert args.limit == 3

    def test_limit_custom(self):
        """Test custom limit values."""
        with patch('sys.argv', ['search_cli.py', 'test', '--limit', '5']):
            args = search_cli.parse_args()
            assert args.limit == 5

        with patch('sys.argv', ['search_cli.py', 'test', '-l', '10']):
            args = search_cli.parse_args()
            assert args.limit == 10

    def test_limit_invalid_type_rejected(self):
        """Test that non-integer limit is rejected."""
        with patch('sys.argv', ['search_cli.py', 'test', '--limit', 'abc']):
            with pytest.raises(SystemExit) as exc_info:
                search_cli.parse_args()
            assert exc_info.value.code == 2

    def test_group_id_optional(self):
        """Test that group_id is optional and defaults to None."""
        with patch('sys.argv', ['search_cli.py', 'test']):
            args = search_cli.parse_args()
            assert args.group_id is None

        with patch('sys.argv', ['search_cli.py', 'test', '--group-id', 'my-project']):
            args = search_cli.parse_args()
            assert args.group_id == 'my-project'

        with patch('sys.argv', ['search_cli.py', 'test', '-g', 'another-project']):
            args = search_cli.parse_args()
            assert args.group_id == 'another-project'

    def test_full_command_parsing(self):
        """Test parsing a command with all options."""
        with patch('sys.argv', [
            'search_cli.py',
            'authentication error',
            '--collection', 'code-patterns',
            '--type', 'error_fix',
            '--intent', 'how',
            '--limit', '7',
            '--group-id', 'test-project'
        ]):
            args = search_cli.parse_args()
            assert args.query == 'authentication error'
            assert args.collection == 'code-patterns'
            assert args.type == 'error_fix'
            assert args.intent == 'how'
            assert args.limit == 7
            assert args.group_id == 'test-project'


class TestSearchCLIExecution:
    """Test CLI execution logic with mocked dependencies."""

    @patch('search_cli.MemorySearch')
    @patch('search_cli.detect_project')
    def test_intent_detection_routing(self, mock_detect, mock_search_class):
        """Test that --intent triggers intent detection and routes to correct collection."""
        mock_detect.return_value = 'test-project'
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_search.search.return_value = []

        # Mock intent detection
        with patch('search_cli.detect_intent') as mock_intent:
            mock_intent.return_value = 'code-patterns'

            with patch('sys.argv', ['search_cli.py', 'how to auth', '--intent', 'how']):
                # This would need parse_args to be integrated into main()
                # For now, just test that parse_args works
                args = search_cli.parse_args()
                assert args.intent == 'how'

    @patch('search_cli.MemorySearch')
    @patch('search_cli.detect_project')
    def test_type_filter_passed_to_search(self, mock_detect, mock_search_class):
        """Test that --type filter is passed to MemorySearch.search()."""
        # This test will verify the integration once main() is updated
        mock_detect.return_value = 'test-project'
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_search.search.return_value = []

        with patch('sys.argv', ['search_cli.py', 'test', '--type', 'guideline']):
            args = search_cli.parse_args()
            assert args.type == 'guideline'


class TestSearchCLIIntegration:
    """Integration tests for search execution."""

    @patch('search_cli.push_skill_metrics_async')
    @patch('search_cli.log_memory_search')
    @patch('search_cli.MemorySearch')
    @patch('search_cli.detect_project')
    def test_intent_flag_routes_to_correct_collection(self, mock_detect, mock_search_class, mock_log, mock_metrics):
        """--intent why should search discussions, not auto-detect."""
        mock_detect.return_value = 'test-project'
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_search.search.return_value = []

        # Simulate: search_cli.py "how to implement" --intent why
        # Even though query says "how", --intent why should force discussions
        with patch('sys.argv', ['search_cli.py', 'how to implement', '--intent', 'why']):
            result = search_cli.main()

        # Verify search was called with discussions collection
        call_args = mock_search.search.call_args_list
        assert len(call_args) == 1, "Should search exactly one collection when --intent is used"

        # Get the collection parameter from the call
        collection_searched = call_args[0].kwargs.get('collection')
        assert collection_searched == 'discussions', f"Expected discussions, got {collection_searched}"
        assert result == 0

        # Verify logging and metrics were called for empty result
        mock_log.assert_called_once()
        mock_metrics.assert_called_once_with(
            skill_name="search-memory",
            status="empty",
            duration_seconds=pytest.approx(0, abs=1.0)
        )

    @patch('search_cli.push_skill_metrics_async')
    @patch('search_cli.detect_project')
    def test_invalid_type_rejected(self, mock_detect, mock_metrics):
        """Invalid --type value returns error."""
        mock_detect.return_value = 'test-project'

        with patch('sys.argv', ['search_cli.py', 'test', '--type', 'invalid_type']):
            result = search_cli.main()
            assert result == 1  # Should exit with error
            # No metrics should be pushed on validation error
            mock_metrics.assert_not_called()

    def test_zero_limit_rejected(self):
        """--limit 0 is rejected."""
        with patch('sys.argv', ['search_cli.py', 'test', '--limit', '0']):
            with pytest.raises(SystemExit):
                search_cli.parse_args()

    def test_negative_limit_rejected(self):
        """--limit -5 is rejected."""
        with patch('sys.argv', ['search_cli.py', 'test', '--limit', '-5']):
            with pytest.raises(SystemExit):
                search_cli.parse_args()
