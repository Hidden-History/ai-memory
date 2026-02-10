"""Unit tests for Jira document composers.

Tests compose_issue_document and compose_comment_document with:
- Complete issue/comment with all fields
- Nullable fields (priority, assignee, labels, resolution)
- Empty descriptions/bodies
- Date formatting
- ADF integration
"""

from unittest.mock import patch

import pytest

from src.memory.connectors.jira.composer import (
    compose_comment_document,
    compose_issue_document,
)

# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def complete_issue():
    """Complete issue with all fields populated."""
    return {
        "key": "PROJ-123",
        "fields": {
            "summary": "Fix login bug",
            "issuetype": {"name": "Bug"},
            "status": {"name": "In Progress"},
            "priority": {"name": "High"},
            "reporter": {"displayName": "Alice"},
            "assignee": {"displayName": "Bob"},
            "labels": ["security", "authentication"],
            "created": "2026-02-01T10:00:00.000+0000",
            "updated": "2026-02-07T15:30:00.000+0000",
            "description": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Login fails with 401"}],
                    }
                ],
            },
        },
    }


@pytest.fixture
def complete_comment():
    """Complete comment with all fields populated."""
    return {
        "id": "10001",
        "author": {"displayName": "Charlie"},
        "created": "2026-02-07T14:00:00.000+0000",
        "body": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "I can reproduce this"}],
                }
            ],
        },
    }


# =============================================================================
# Issue Document Tests
# =============================================================================


class TestIssueDocumentFormat:
    """Test compose_issue_document format and structure."""

    def test_complete_issue_format(self, complete_issue):
        """Complete issue document with all fields."""
        result = compose_issue_document(complete_issue)

        # Header line: [KEY] Summary
        assert "[PROJ-123] Fix login bug" in result

        # Metadata line 1: Type | Priority | Status
        assert "Type: Bug | Priority: High | Status: In Progress" in result

        # Metadata line 2: Reporter | Assigned
        assert "Reporter: Alice | Assigned: Bob" in result

        # Metadata line 3: Labels
        assert "Labels: security, authentication" in result

        # Metadata line 4: Dates (formatted as YYYY-MM-DD)
        assert "Created: 2026-02-01 | Updated: 2026-02-07" in result

        # Description section
        assert "Description:" in result
        assert "Login fails with 401" in result

    def test_issue_structure_order(self, complete_issue):
        """Issue document structure in correct order."""
        result = compose_issue_document(complete_issue)
        lines = result.split("\n")

        # Verify order
        assert "[PROJ-123]" in lines[0]  # Header
        assert "Type:" in lines[1]  # Metadata 1
        assert "Reporter:" in lines[2]  # Metadata 2
        assert "Labels:" in lines[3]  # Metadata 3
        assert "Created:" in lines[4]  # Metadata 4
        assert lines[5] == ""  # Blank line
        assert lines[6] == "Description:"  # Section header

    def test_issue_with_all_metadata_fields(self, complete_issue):
        """All metadata fields present and formatted correctly."""
        result = compose_issue_document(complete_issue)

        # Verify all fields extracted
        assert "Bug" in result
        assert "High" in result
        assert "In Progress" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "security, authentication" in result
        assert "2026-02-01" in result
        assert "2026-02-07" in result


class TestNullablePriority:
    """Test nullable priority field handling."""

    def test_priority_none(self, complete_issue):
        """Priority is None (team-managed projects)."""
        complete_issue["fields"]["priority"] = None
        result = compose_issue_document(complete_issue)

        # Should show "None" instead of crashing
        assert "Priority: None" in result

    def test_priority_missing_name(self, complete_issue):
        """Priority object missing name field."""
        complete_issue["fields"]["priority"] = {}
        result = compose_issue_document(complete_issue)

        # Should handle gracefully
        assert "Priority:" in result

    def test_priority_missing_key(self, complete_issue):
        """Priority key missing entirely."""
        del complete_issue["fields"]["priority"]
        result = compose_issue_document(complete_issue)

        # Should default to None
        assert "Priority: None" in result


class TestNullableAssignee:
    """Test nullable assignee field handling."""

    def test_assignee_none(self, complete_issue):
        """Assignee is None (unassigned)."""
        complete_issue["fields"]["assignee"] = None
        result = compose_issue_document(complete_issue)

        # Should show "Unassigned"
        assert "Assigned: Unassigned" in result

    def test_assignee_missing_display_name(self, complete_issue):
        """Assignee object missing displayName."""
        complete_issue["fields"]["assignee"] = {}
        result = compose_issue_document(complete_issue)

        # Should handle gracefully
        assert "Assigned:" in result

    def test_assignee_missing_key(self, complete_issue):
        """Assignee key missing entirely."""
        del complete_issue["fields"]["assignee"]
        result = compose_issue_document(complete_issue)

        # Should default to Unassigned
        assert "Assigned: Unassigned" in result


class TestNullableLabels:
    """Test nullable labels field handling."""

    def test_labels_empty_list(self, complete_issue):
        """Labels is empty list."""
        complete_issue["fields"]["labels"] = []
        result = compose_issue_document(complete_issue)

        # Should show "None"
        assert "Labels: None" in result

    def test_labels_none(self, complete_issue):
        """Labels is None."""
        complete_issue["fields"]["labels"] = None
        result = compose_issue_document(complete_issue)

        # Should handle gracefully (defaults to empty list)
        assert "Labels: None" in result

    def test_labels_missing_key(self, complete_issue):
        """Labels key missing entirely."""
        del complete_issue["fields"]["labels"]
        result = compose_issue_document(complete_issue)

        # Should default to None
        assert "Labels: None" in result

    def test_single_label(self, complete_issue):
        """Single label in list."""
        complete_issue["fields"]["labels"] = ["hotfix"]
        result = compose_issue_document(complete_issue)

        assert "Labels: hotfix" in result

    def test_multiple_labels_concatenation(self, complete_issue):
        """Multiple labels joined with commas."""
        complete_issue["fields"]["labels"] = ["bug", "urgent", "frontend"]
        result = compose_issue_document(complete_issue)

        assert "Labels: bug, urgent, frontend" in result


class TestNullableReporter:
    """Test nullable reporter field handling."""

    def test_reporter_none(self, complete_issue):
        """Reporter is None."""
        complete_issue["fields"]["reporter"] = None
        result = compose_issue_document(complete_issue)

        # Should show "Unknown"
        assert "Reporter: Unknown" in result

    def test_reporter_missing_display_name(self, complete_issue):
        """Reporter object missing displayName."""
        complete_issue["fields"]["reporter"] = {}
        result = compose_issue_document(complete_issue)

        # Should default to Unknown
        assert "Reporter: Unknown" in result

    def test_reporter_missing_key(self, complete_issue):
        """Reporter key missing entirely."""
        del complete_issue["fields"]["reporter"]
        result = compose_issue_document(complete_issue)

        # Should default to Unknown
        assert "Reporter: Unknown" in result


class TestEmptyDescription:
    """Test empty/null description handling."""

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_description_none(self, mock_adf, complete_issue):
        """Description is None."""
        complete_issue["fields"]["description"] = None
        result = compose_issue_document(complete_issue)

        # Should show "(No description)"
        assert "(No description)" in result
        # adf_to_text should NOT be called
        mock_adf.assert_not_called()

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_description_empty_adf(self, mock_adf, complete_issue):
        """Description is empty ADF."""
        mock_adf.return_value = ""
        complete_issue["fields"]["description"] = {"type": "doc", "content": []}
        result = compose_issue_document(complete_issue)

        # Should call adf_to_text
        mock_adf.assert_called_once()
        # Empty result from ADF converter is included
        assert "Description:" in result

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_description_missing_key(self, mock_adf, complete_issue):
        """Description key missing entirely."""
        del complete_issue["fields"]["description"]
        result = compose_issue_document(complete_issue)

        # Should show "(No description)"
        assert "(No description)" in result
        mock_adf.assert_not_called()


class TestDateFormatting:
    """Test ISO 8601 date formatting."""

    def test_created_date_formatting(self, complete_issue):
        """Created date formatted as YYYY-MM-DD."""
        complete_issue["fields"]["created"] = "2026-02-01T10:30:45.123+0000"
        result = compose_issue_document(complete_issue)

        # Should extract just the date part
        assert "Created: 2026-02-01" in result

    def test_updated_date_formatting(self, complete_issue):
        """Updated date formatted as YYYY-MM-DD."""
        complete_issue["fields"]["updated"] = "2026-02-15T23:59:59.999+0000"
        result = compose_issue_document(complete_issue)

        # Should extract just the date part
        assert "Updated: 2026-02-15" in result

    def test_short_date_string(self, complete_issue):
        """Date string shorter than 10 chars handled gracefully."""
        complete_issue["fields"]["created"] = "2026-02"
        result = compose_issue_document(complete_issue)

        # Should not crash (slice returns partial string)
        assert "Created: 2026-02" in result


class TestADFIntegration:
    """Test ADF converter integration."""

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_adf_converter_called(self, mock_adf, complete_issue):
        """adf_to_text called with description ADF."""
        mock_adf.return_value = "Converted text"
        complete_issue["fields"]["description"] = {"type": "doc", "content": []}

        result = compose_issue_document(complete_issue)

        # Should call adf_to_text with description
        mock_adf.assert_called_once_with({"type": "doc", "content": []})
        assert "Converted text" in result

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_adf_result_included(self, mock_adf, complete_issue):
        """ADF conversion result included in document."""
        mock_adf.return_value = "This is the converted description\nwith multiple lines"

        result = compose_issue_document(complete_issue)

        assert "This is the converted description" in result
        assert "with multiple lines" in result


# =============================================================================
# Comment Document Tests
# =============================================================================


class TestCommentDocumentFormat:
    """Test compose_comment_document format and structure."""

    def test_complete_comment_format(self, complete_issue, complete_comment):
        """Complete comment document with all fields."""
        result = compose_comment_document(complete_issue, complete_comment)

        # Header line: [KEY] Summary (Type, Priority, Status)
        assert "[PROJ-123] Fix login bug (Bug, High, In Progress)" in result

        # Comment attribution line
        assert "Comment by Charlie (2026-02-07):" in result

        # Comment body
        assert "I can reproduce this" in result

    def test_comment_structure_order(self, complete_issue, complete_comment):
        """Comment document structure in correct order."""
        result = compose_comment_document(complete_issue, complete_comment)
        lines = result.split("\n")

        # Verify order
        assert "[PROJ-123]" in lines[0]  # Header with parent context
        assert lines[1] == ""  # Blank line
        assert "Comment by" in lines[2]  # Attribution

    def test_parent_context_in_header(self, complete_issue, complete_comment):
        """Parent issue context included in header."""
        result = compose_comment_document(complete_issue, complete_comment)

        # Should include parent issue summary, type, priority, status
        assert "Fix login bug" in result
        assert "Bug" in result
        assert "High" in result
        assert "In Progress" in result


class TestCommentNullablePriority:
    """Test nullable priority in parent issue context."""

    def test_parent_priority_none(self, complete_issue, complete_comment):
        """Parent issue priority is None."""
        complete_issue["fields"]["priority"] = None
        result = compose_comment_document(complete_issue, complete_comment)

        # Should show "None" in header context
        assert "(Bug, None, In Progress)" in result

    def test_parent_priority_missing(self, complete_issue, complete_comment):
        """Parent issue priority key missing."""
        del complete_issue["fields"]["priority"]
        result = compose_comment_document(complete_issue, complete_comment)

        # Should default to None
        assert "None" in result


class TestCommentAuthor:
    """Test comment author field handling."""

    def test_author_display_name(self, complete_issue, complete_comment):
        """Author displayName extracted correctly."""
        complete_comment["author"] = {"displayName": "David"}
        result = compose_comment_document(complete_issue, complete_comment)

        assert "Comment by David" in result

    def test_author_missing_display_name(self, complete_issue, complete_comment):
        """Author object missing displayName."""
        complete_comment["author"] = {}
        result = compose_comment_document(complete_issue, complete_comment)

        # Should default to Unknown
        assert "Comment by Unknown" in result

    def test_author_missing_key(self, complete_issue, complete_comment):
        """Author key missing entirely."""
        del complete_comment["author"]
        result = compose_comment_document(complete_issue, complete_comment)

        # Should default to Unknown
        assert "Comment by Unknown" in result


class TestCommentDateFormatting:
    """Test comment date formatting."""

    def test_created_date_formatting(self, complete_issue, complete_comment):
        """Comment created date formatted as YYYY-MM-DD."""
        complete_comment["created"] = "2026-02-10T08:15:30.456+0000"
        result = compose_comment_document(complete_issue, complete_comment)

        # Should extract just the date part
        assert "(2026-02-10)" in result

    def test_short_date_string(self, complete_issue, complete_comment):
        """Date string shorter than 10 chars handled gracefully."""
        complete_comment["created"] = "2026"
        result = compose_comment_document(complete_issue, complete_comment)

        # Should not crash
        assert "Comment by" in result


class TestEmptyCommentBody:
    """Test empty/null comment body handling."""

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_body_none(self, mock_adf, complete_issue, complete_comment):
        """Comment body is None."""
        complete_comment["body"] = None
        result = compose_comment_document(complete_issue, complete_comment)

        # Should show "(Empty comment)"
        assert "(Empty comment)" in result
        # adf_to_text should NOT be called
        mock_adf.assert_not_called()

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_body_empty_adf(self, mock_adf, complete_issue, complete_comment):
        """Comment body is empty ADF."""
        mock_adf.return_value = ""
        complete_comment["body"] = {"type": "doc", "content": []}
        compose_comment_document(complete_issue, complete_comment)

        # Should call adf_to_text
        mock_adf.assert_called_once()

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_body_missing_key(self, mock_adf, complete_issue, complete_comment):
        """Comment body key missing entirely."""
        del complete_comment["body"]
        result = compose_comment_document(complete_issue, complete_comment)

        # Should show "(Empty comment)"
        assert "(Empty comment)" in result
        mock_adf.assert_not_called()


class TestCommentADFIntegration:
    """Test ADF converter integration for comments."""

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_adf_converter_called(self, mock_adf, complete_issue, complete_comment):
        """adf_to_text called with comment body ADF."""
        mock_adf.return_value = "Converted comment"
        complete_comment["body"] = {"type": "doc", "content": []}

        result = compose_comment_document(complete_issue, complete_comment)

        # Should call adf_to_text with body
        mock_adf.assert_called_once_with({"type": "doc", "content": []})
        assert "Converted comment" in result

    @patch("src.memory.connectors.jira.composer.adf_to_text")
    def test_adf_result_included(self, mock_adf, complete_issue, complete_comment):
        """ADF conversion result included in comment document."""
        mock_adf.return_value = "This is a multi-line\ncomment body\nwith details"

        result = compose_comment_document(complete_issue, complete_comment)

        assert "This is a multi-line" in result
        assert "comment body" in result
        assert "with details" in result


# =============================================================================
# Field Extraction Edge Cases
# =============================================================================


class TestFieldExtraction:
    """Test field extraction edge cases."""

    def test_missing_key(self, complete_issue):
        """Issue missing key field."""
        del complete_issue["key"]
        result = compose_issue_document(complete_issue)

        # Should default to UNKNOWN
        assert "[UNKNOWN]" in result

    def test_missing_fields_object(self, complete_issue):
        """Issue missing fields object."""
        del complete_issue["fields"]
        result = compose_issue_document(complete_issue)

        # Should handle with defaults
        assert "No summary" in result
        assert "Unknown" in result

    def test_missing_summary(self, complete_issue):
        """Issue missing summary field."""
        del complete_issue["fields"]["summary"]
        result = compose_issue_document(complete_issue)

        # Should default to "No summary"
        assert "No summary" in result

    def test_nested_field_missing(self, complete_issue):
        """Nested field (issuetype.name) missing."""
        complete_issue["fields"]["issuetype"] = {}
        result = compose_issue_document(complete_issue)

        # Should default to Unknown
        assert "Type: Unknown" in result
