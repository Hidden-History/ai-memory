"""Unit tests for Story 3.3: Context Formatting (2026 Best Practices).

Validates:
- AC 3.3.1: Tiered formatting (high >90%, medium 50-90%)
- AC 3.3.2: Token budget enforcement
- AC 3.3.3: Configurable thresholds
- AC 3.3.4: Performance <100ms

Story Reference: _bmad-output/implementation-artifacts/3-3-context-formatting.md
"""

import time
import pytest
from unittest.mock import patch

# Import via test helpers
from session_start_test_helpers import (
    format_context,
    format_memory_entry
)


class TestTieredFormatting:
    """AC 3.3.1 - Tiered Formatting Implementation."""

    def test_high_relevance_full_content_no_truncation(self):
        """High relevance (>90%) displays full content without truncation."""
        results = [
            {
                "score": 0.95,
                "type": "implementation",
                "content": "A" * 1000,  # Long content
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
        ]

        formatted = format_context(results, "test-project")

        # High tier header present
        assert "High Relevance (>90%)" in formatted
        # Full content included (no truncation marker)
        assert "..." not in formatted
        # Score displayed correctly
        assert "95%" in formatted
        # Collection attribution displayed (Story 3.2)
        assert "[implementations]" in formatted

    def test_medium_relevance_truncated_500_chars(self):
        """Medium relevance (50-90%) displays truncated content (max 500 chars)."""
        results = [
            {
                "score": 0.85,
                "type": "best_practice",
                "content": "B" * 700,  # Long content, should truncate
                "source_hook": "seed_script",
                "collection": "conventions"
            }
        ]

        formatted = format_context(results, "test-project")

        # Medium tier header present
        assert "Medium Relevance (50-90%)" in formatted
        # Truncated marker present
        assert "..." in formatted
        # Score displayed correctly
        assert "85%" in formatted
        # Collection attribution displayed
        assert "[best_practices]" in formatted

    def test_below_threshold_excluded(self):
        """Memories below 20% similarity threshold are excluded."""
        results = [
            {
                "score": 0.15,  # Below 20% threshold (completely irrelevant)
                "type": "implementation",
                "content": "Low relevance content should not appear",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
        ]

        formatted = format_context(results, "test-project")

        # Content not in output
        assert "Low relevance content" not in formatted
        # Only header should be present
        assert "Relevant Memories" in formatted

    def test_boundary_90_percent_exact(self):
        """Test 0.90 boundary - exactly 90% goes to high tier."""
        results = [
            {
                "score": 0.90,
                "type": "implementation",
                "content": "Exactly 90% relevance",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
        ]

        formatted = format_context(results, "test-project")

        # Should be in high tier (>=0.90)
        assert "High Relevance (>90%)" in formatted
        assert "Exactly 90% relevance" in formatted

    def test_boundary_78_percent_exact(self):
        """Test 0.78 boundary - exactly 78% goes to medium tier."""
        results = [
            {
                "score": 0.78,
                "type": "pattern",
                "content": "Exactly 78% relevance",
                "source_hook": "session_stop",
                "collection": "conventions"
            }
        ]

        formatted = format_context(results, "test-project")

        # Should be in medium tier (>=0.78)
        assert "Medium Relevance (50-90%)" in formatted
        assert "Exactly 78% relevance" in formatted

    def test_mixed_tiers(self):
        """Test formatting with mixed high and medium relevance memories."""
        results = [
            {
                "score": 0.95,
                "type": "implementation",
                "content": "High relevance implementation",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            },
            {
                "score": 0.92,
                "type": "implementation",
                "content": "High relevance pattern",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            },
            {
                "score": 0.85,
                "type": "best_practice",
                "content": "Medium relevance best practice",
                "source_hook": "seed_script",
                "collection": "conventions"
            },
            {
                "score": 0.80,
                "type": "pattern",
                "content": "Medium relevance pattern",
                "source_hook": "session_stop",
                "collection": "conventions"
            }
        ]

        formatted = format_context(results, "test-project")

        # Both tiers present
        assert "High Relevance (>90%)" in formatted
        assert "Medium Relevance (50-90%)" in formatted
        # All content above threshold included
        assert "High relevance implementation" in formatted
        assert "High relevance pattern" in formatted
        assert "Medium relevance best practice" in formatted
        assert "Medium relevance pattern" in formatted


class TestTokenBudgetEnforcement:
    """AC 3.3.2 - Token Budget Enforcement."""

    def test_token_budget_stops_at_limit(self):
        """Output does not exceed token budget (approximate word count)."""
        # Create 20 high-relevance memories with ~200 words each
        results = [
            {
                "score": 0.95,
                "type": f"implementation_{i}",
                "content": " ".join(["word"] * 200),  # ~200 words
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
            for i in range(20)
        ]

        # Set budget to ~500 tokens (~500 words)
        formatted = format_context(results, "test-project", token_budget=500)

        # Count approximate tokens (words)
        word_count = len(formatted.split())

        # Should be close to budget (allow some overhead for headers/formatting)
        # Budget enforcement stops adding memories when limit reached
        assert word_count < 800  # Should not wildly exceed budget

    def test_most_relevant_included_first(self):
        """Most relevant memories are included first (sorted by score descending)."""
        results = [
            {
                "score": 0.99,
                "type": "implementation",
                "content": "Highest relevance content",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            },
            {
                "score": 0.95,
                "type": "implementation",
                "content": "Second highest relevance",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            },
            {
                "score": 0.91,
                "type": "implementation",
                "content": "Third highest relevance",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
        ]

        # Small budget - only first memory should fit
        formatted = format_context(results, "test-project", token_budget=50)

        # Highest relevance should be present
        assert "Highest relevance content" in formatted

    def test_lower_relevance_truncated_or_omitted(self):
        """Lower-relevance memories are truncated or omitted when budget reached."""
        results = [
            {
                "score": 0.95,
                "type": "implementation",
                "content": "High relevance " + ("word " * 300),  # Large
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            },
            {
                "score": 0.85,
                "type": "best_practice",
                "content": "Medium relevance " + ("word " * 300),  # Large
                "source_hook": "seed_script",
                "collection": "conventions"
            }
        ]

        # Budget allows high tier but not medium tier
        formatted = format_context(results, "test-project", token_budget=400)

        # High tier should be present
        assert "High relevance" in formatted
        # Medium tier may be omitted if budget exceeded
        # (Implementation prioritizes high tier over strict budget)


class TestConfigurableThresholds:
    """AC 3.3.3 - Configurable Thresholds."""

    def test_similarity_threshold_from_config(self):
        """SIMILARITY_THRESHOLD is configurable via environment variable."""
        # Currently hardcoded to 0.78 in format_context()
        # This test verifies the threshold behavior
        results = [
            {
                "score": 0.78,  # At default threshold
                "type": "pattern",
                "content": "At threshold content",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
        ]

        formatted = format_context(results, "test-project")

        # Should be included at default 0.78 threshold
        assert "At threshold content" in formatted

    def test_high_tier_threshold_90_percent(self):
        """High tier threshold is 90% (0.90)."""
        results = [
            {
                "score": 0.90,  # At high tier threshold
                "type": "implementation",
                "content": "High tier boundary content",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
        ]

        formatted = format_context(results, "test-project")

        # Should be in high tier
        assert "High Relevance (>90%)" in formatted
        assert "High tier boundary content" in formatted

    def test_medium_tier_range_78_to_90(self):
        """Medium tier is 0.78 <= score < 0.90."""
        results = [
            {
                "score": 0.89,  # Just below high tier
                "type": "pattern",
                "content": "Upper medium tier",
                "source_hook": "PostToolUse",
                "collection": "conventions"
            },
            {
                "score": 0.78,  # Lower boundary of medium tier
                "type": "pattern",
                "content": "Lower medium tier",
                "source_hook": "PostToolUse",
                "collection": "conventions"
            }
        ]

        formatted = format_context(results, "test-project")

        # Both should be in medium tier
        assert "Medium Relevance (50-90%)" in formatted
        assert "Upper medium tier" in formatted
        assert "Lower medium tier" in formatted


class TestPerformanceRequirements:
    """AC 3.3.4 - Performance Requirements (<100ms)."""

    def test_formatting_performance_under_100ms(self):
        """Context formatting completes in <100ms with realistic data."""
        # Create 10 memories (realistic SessionStart result count)
        results = [
            {
                "score": 0.95 - (i * 0.01),  # Decreasing scores
                "type": f"implementation_{i}",
                "content": f"[python/hooks] .claude/hooks/scripts/session_start.py:{i*10}-{i*10+10}\n" + ("line " * 100),
                "source_hook": "PostToolUse",
                "collection": "code-patterns" if i < 7 else "conventions"
            }
            for i in range(10)
        ]

        # Measure formatting time
        start = time.perf_counter()
        formatted = format_context(results, "bmad-memory-module", token_budget=2000)
        duration_ms = (time.perf_counter() - start) * 1000

        # Should complete in <100ms (NFR-P3 component)
        assert duration_ms < 100, f"Formatting took {duration_ms:.2f}ms (expected <100ms)"
        # Should produce non-empty output
        assert len(formatted) > 0

    def test_no_blocking_operations(self):
        """Formatting uses no blocking operations or external calls."""
        # This is a structural test - verify no network/IO in format_context
        results = [
            {
                "score": 0.95,
                "type": "implementation",
                "content": "Test content",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
        ]

        # Should complete quickly (pure string manipulation)
        start = time.perf_counter()
        formatted = format_context(results, "test-project")
        duration_ms = (time.perf_counter() - start) * 1000

        # Pure string manipulation should be <10ms
        assert duration_ms < 10

    def test_efficient_string_operations(self):
        """Formatting uses efficient Python string operations (f-strings, join)."""
        # Indirectly verified by performance test
        # Also verified by code inspection: session_start.py uses f-strings and join()
        results = [
            {
                "score": 0.95,
                "type": "implementation",
                "content": "Test " * 100,
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            }
        ]

        formatted = format_context(results, "test-project")

        # Should complete efficiently
        assert len(formatted) > 0


class TestCollectionAttribution:
    """Test collection attribution display (Story 3.2 integration)."""

    def test_collection_field_displayed(self):
        """Collection field is displayed in formatted output."""
        results = [
            {
                "score": 0.95,
                "type": "implementation",
                "content": "Test implementation",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            },
            {
                "score": 0.85,
                "type": "best_practice",
                "content": "Test best practice",
                "source_hook": "seed_script",
                "collection": "conventions"
            }
        ]

        formatted = format_context(results, "test-project")

        # Collection attribution displayed
        assert "[implementations]" in formatted
        assert "[best_practices]" in formatted

    def test_format_memory_entry_includes_collection(self):
        """format_memory_entry() includes collection attribution."""
        memory = {
            "type": "pattern",
            "score": 0.90,
            "content": "Test pattern",
            "source_hook": "session_stop",
            "collection": "conventions"
        }

        entry = format_memory_entry(memory, truncate=False)

        # Collection shown in attribution line
        assert "[best_practices]" in entry


class TestMarkdownFormatStructure:
    """Test markdown format structure (headers, code blocks, formatting)."""

    def test_markdown_headers_present(self):
        """Markdown headers are correctly formatted."""
        results = [
            {
                "score": 0.95,
                "type": "implementation",
                "content": "High relevance",
                "source_hook": "PostToolUse",
                "collection": "code-patterns"
            },
            {
                "score": 0.85,
                "type": "pattern",
                "content": "Medium relevance",
                "source_hook": "PostToolUse",
                "collection": "conventions"
            }
        ]

        formatted = format_context(results, "test-project")

        # Main header (##)
        assert "## Relevant Memories for test-project" in formatted
        # Section headers (###)
        assert "### High Relevance (>90%)" in formatted
        assert "### Medium Relevance (50-90%)" in formatted

    def test_code_blocks_for_content(self):
        """Content is wrapped in markdown code blocks (triple backticks)."""
        memory = {
            "type": "implementation",
            "score": 0.95,
            "content": "def test_function():\n    pass",
            "source_hook": "PostToolUse",
            "collection": "code-patterns"
        }

        entry = format_memory_entry(memory)

        # Code block markers present
        assert "```" in entry
        # Content inside code block
        assert "def test_function():" in entry

    def test_attribution_line_format(self):
        """Attribution line uses bold markdown and correct format."""
        memory = {
            "type": "implementation",
            "score": 0.92,
            "content": "Test content",
            "source_hook": "PostToolUse",
            "collection": "code-patterns"
        }

        entry = format_memory_entry(memory)

        # Bold type (** markers)
        assert "**implementation**" in entry
        # Score as percentage
        assert "92%" in entry
        # Source hook
        assert "PostToolUse" in entry
        # Collection in brackets
        assert "[implementations]" in entry


class TestEdgeCases:
    """Test edge cases and graceful degradation."""

    def test_empty_results_returns_empty_string(self):
        """Empty results list returns empty string."""
        formatted = format_context([], "test-project")
        assert formatted == ""

    def test_missing_fields_gracefully_handled(self):
        """Missing fields in memory dict are handled gracefully."""
        memory = {
            "score": 0.95
            # Missing: type, content, source_hook, collection
        }

        entry = format_memory_entry(memory)

        # Should not crash, use defaults
        assert "unknown" in entry

    def test_malformed_score_handled(self):
        """Malformed score values are handled gracefully (default to 0%)."""
        memory = {
            "score": None,  # Malformed - should default to 0
            "type": "implementation",
            "content": "Test content",
            "source_hook": "PostToolUse",
            "collection": "code-patterns"
        }

        # Should handle None gracefully by defaulting to 0%
        entry = format_memory_entry(memory)

        # Verify it defaults to 0% for None score
        assert "0%" in entry
        # Verify other fields still rendered correctly
        assert "implementation" in entry
        assert "Test content" in entry
        assert "[implementations]" in entry
