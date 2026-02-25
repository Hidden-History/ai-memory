"""Unit tests for sprint-status updater script.

Tests pattern matching, YAML updating, and edge case handling for ACT-002.
"""

import subprocess

# Import functions to test
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.update_sprint_status import (
    get_git_commits,
    parse_story_updates,
    update_sprint_status_yaml,
)

# Fixtures


@pytest.fixture
def sample_commits():
    """Sample git commit messages for testing."""
    return [
        "a1b2c3d Story 6.5: Complete retrieval session logs",
        "e4f5g6h Story 6.6 complete - collection statistics",
        "i7j8k9l WIP Story 7.1 implementation started",
        "m0n1o2p [WIP] Story 7.2 hook configuration",
        "q3r4s5t Regular commit without story pattern",
        "u6v7w8x Story 6.4: Streamlit browser feature",
        "y9z0a1b Story 6.3 complete",
    ]


@pytest.fixture
def sample_yaml_content():
    """Sample sprint-status.yaml structure."""
    return """# Sprint Status Tracking
# Project: AI Memory Module
# Generated: 2026-01-10

epics:
  epic-6:
    title: "Monitoring & Observability"
    status: in-progress
    stories:
      6-3-pre-built-grafana-dashboards:
        title: "Pre-built Grafana Dashboards"
        status: review
        complexity: Medium
        frs: [FR26]
      6-4-streamlit-memory-browser:
        title: "Streamlit Memory Browser"
        status: in-progress
        complexity: Medium
        frs: [FR24, FR28]
      6-5-retrieval-session-logs:
        title: "Retrieval Session Logs"
        status: ready-for-dev
        complexity: Low
        frs: [FR29]
      6-6-collection-statistics-and-warnings:
        title: "Collection Statistics & Warnings"
        status: ready-for-dev
        complexity: Low
        frs: [FR28, FR46a]

  epic-7:
    title: "One-Command Installation"
    status: backlog
    stories:
      7-1-single-command-installer-script:
        title: "Single-Command Installer Script"
        status: backlog
        complexity: High
        frs: [FR18, FR22, FR23]
      7-2-hook-auto-configuration:
        title: "Hook Auto-Configuration"
        status: backlog
        complexity: Medium
        frs: [FR20]
"""


@pytest.fixture
def temp_yaml_file(tmp_path, sample_yaml_content):
    """Create temporary YAML file for testing."""
    yaml_file = tmp_path / "sprint-status.yaml"
    yaml_file.write_text(sample_yaml_content)
    return yaml_file


# Pattern Matching Tests


def test_parse_story_done_at_start(sample_commits):
    """Test 'Story X.Y:' pattern at start marks as done (AC 1)."""
    updates = parse_story_updates([sample_commits[0]])  # "Story 6.5: Complete..."

    assert "6-5" in updates
    assert updates["6-5"] == "done"


def test_parse_story_complete_anywhere(sample_commits):
    """Test 'Story X.Y complete' pattern anywhere marks as done (AC 2)."""
    updates = parse_story_updates([sample_commits[1]])  # "Story 6.6 complete"

    assert "6-6" in updates
    assert updates["6-6"] == "done"


def test_parse_story_wip(sample_commits):
    """Test 'WIP Story X.Y' pattern marks as in-progress (AC 3)."""
    updates = parse_story_updates([sample_commits[2]])  # "WIP Story 7.1"

    assert "7-1" in updates
    assert updates["7-1"] == "in-progress"


def test_parse_story_wip_brackets(sample_commits):
    """Test '[WIP] Story X.Y' pattern marks as in-progress (AC 3)."""
    updates = parse_story_updates([sample_commits[3]])  # "[WIP] Story 7.2"

    assert "7-2" in updates
    assert updates["7-2"] == "in-progress"


def test_parse_no_pattern_match(sample_commits):
    """Test commits without story patterns are ignored."""
    updates = parse_story_updates([sample_commits[4]])  # "Regular commit..."

    assert len(updates) == 0


def test_parse_multiple_commits(sample_commits):
    """Test parsing multiple commits returns all matches."""
    updates = parse_story_updates(sample_commits)

    # Should find: 6.5, 6.6, 7.1, 7.2, 6.4, 6.3
    assert len(updates) >= 6
    assert "6-5" in updates
    assert "6-6" in updates
    assert "7-1" in updates
    assert "7-2" in updates


def test_parse_case_insensitive():
    """Test pattern matching is case-insensitive."""
    commits = [
        "abc123 STORY 6.5: Feature complete",
        "def456 story 6.6 COMPLETE",
        "ghi789 wip STORY 7.1 implementation",
    ]
    updates = parse_story_updates(commits)

    assert "6-5" in updates
    assert updates["6-5"] == "done"
    assert "6-6" in updates
    assert updates["6-6"] == "done"
    assert "7-1" in updates
    assert updates["7-1"] == "in-progress"


def test_parse_done_overrides_wip():
    """Test 'done' pattern takes precedence over 'wip' for same story."""
    commits = [
        "abc123 WIP Story 6.5 started",
        "def456 Story 6.5: Complete implementation",
    ]
    updates = parse_story_updates(commits)

    # Should be marked as done, not in-progress
    assert updates["6-5"] == "done"


# YAML Update Tests


def test_update_yaml_marks_story_done(temp_yaml_file):
    """Test updating story status to 'done' (AC 4)."""
    updates = {"6-5": "done"}
    updated, not_found = update_sprint_status_yaml(temp_yaml_file, updates)

    assert updated == 1
    assert not_found == 0

    # Verify YAML was updated
    from ruamel.yaml import YAML

    yaml = YAML()
    with open(temp_yaml_file) as f:
        data = yaml.load(f)

    assert (
        data["epics"]["epic-6"]["stories"]["6-5-retrieval-session-logs"]["status"]
        == "done"
    )


def test_update_yaml_marks_story_in_progress(temp_yaml_file):
    """Test updating story status to 'in-progress' (AC 5)."""
    updates = {"7-1": "in-progress"}
    updated, not_found = update_sprint_status_yaml(temp_yaml_file, updates)

    assert updated == 1
    assert not_found == 0

    # Verify YAML was updated
    from ruamel.yaml import YAML

    yaml = YAML()
    with open(temp_yaml_file) as f:
        data = yaml.load(f)

    assert (
        data["epics"]["epic-7"]["stories"]["7-1-single-command-installer-script"][
            "status"
        ]
        == "in-progress"
    )


def test_update_yaml_preserves_comments(temp_yaml_file):
    """Test YAML comments are preserved after update (AC 6)."""
    temp_yaml_file.read_text()

    updates = {"6-5": "done"}
    update_sprint_status_yaml(temp_yaml_file, updates)

    updated_content = temp_yaml_file.read_text()

    # Check that header comments are preserved
    assert "# Sprint Status Tracking" in updated_content
    assert "# Project: AI Memory Module" in updated_content
    assert "# Generated: 2026-01-10" in updated_content


def test_update_yaml_preserves_structure(temp_yaml_file):
    """Test YAML structure is preserved after update (AC 7)."""
    from ruamel.yaml import YAML

    yaml = YAML()

    # Load original structure
    with open(temp_yaml_file) as f:
        original_data = yaml.load(f)

    updates = {"6-5": "done", "6-6": "done"}
    update_sprint_status_yaml(temp_yaml_file, updates)

    # Load updated structure
    with open(temp_yaml_file) as f:
        updated_data = yaml.load(f)

    # Verify structure is identical (except for updated statuses)
    assert (
        updated_data["epics"]["epic-6"]["title"]
        == original_data["epics"]["epic-6"]["title"]
    )
    assert (
        updated_data["epics"]["epic-6"]["stories"]["6-5-retrieval-session-logs"][
            "title"
        ]
        == original_data["epics"]["epic-6"]["stories"]["6-5-retrieval-session-logs"][
            "title"
        ]
    )


def test_update_yaml_multiple_stories(temp_yaml_file):
    """Test updating multiple stories in one pass."""
    updates = {
        "6-3": "done",
        "6-4": "done",
        "6-5": "done",
        "6-6": "done",
    }
    updated, not_found = update_sprint_status_yaml(temp_yaml_file, updates)

    assert updated == 4
    assert not_found == 0


# Edge Case Tests


def test_update_yaml_story_not_found(temp_yaml_file):
    """Test handling of story ID not in YAML (AC 8)."""
    updates = {"99-99": "done"}  # Non-existent story
    updated, not_found = update_sprint_status_yaml(temp_yaml_file, updates)

    assert updated == 0
    assert not_found == 1


def test_update_yaml_epic_not_found(temp_yaml_file):
    """Test handling of epic not in YAML."""
    updates = {"99-1": "done"}  # Non-existent epic
    updated, not_found = update_sprint_status_yaml(temp_yaml_file, updates)

    assert updated == 0
    assert not_found == 1


def test_update_yaml_already_done_idempotent(temp_yaml_file):
    """Test updating already-done story is idempotent (AC 9)."""
    # First update
    updates = {"6-5": "done"}
    updated1, _ = update_sprint_status_yaml(temp_yaml_file, updates)
    assert updated1 == 1

    # Second update (same story)
    updated2, _ = update_sprint_status_yaml(temp_yaml_file, updates)
    assert updated2 == 0  # No change


def test_update_yaml_no_backward_transition(temp_yaml_file):
    """Test done stories don't transition back to in-progress (AC 10)."""
    # Mark as done
    updates_done = {"6-5": "done"}
    update_sprint_status_yaml(temp_yaml_file, updates_done)

    # Try to mark as in-progress
    updates_wip = {"6-5": "in-progress"}
    updated, _ = update_sprint_status_yaml(temp_yaml_file, updates_wip)

    assert updated == 0  # Should not update

    # Verify still marked as done
    from ruamel.yaml import YAML

    yaml = YAML()
    with open(temp_yaml_file) as f:
        data = yaml.load(f)

    assert (
        data["epics"]["epic-6"]["stories"]["6-5-retrieval-session-logs"]["status"]
        == "done"
    )


def test_update_yaml_file_not_found():
    """Test graceful handling when YAML file doesn't exist (AC 11)."""
    fake_path = Path("/nonexistent/path/sprint-status.yaml")
    updates = {"6-5": "done"}

    with pytest.raises(FileNotFoundError):
        update_sprint_status_yaml(fake_path, updates)


def test_update_yaml_malformed_content(tmp_path):
    """Test graceful handling of malformed YAML (AC 12)."""
    malformed_yaml = tmp_path / "malformed.yaml"
    malformed_yaml.write_text("epic:\n  - invalid: [unclosed")

    updates = {"6-5": "done"}

    with pytest.raises(ValueError):
        update_sprint_status_yaml(malformed_yaml, updates)


def test_update_yaml_missing_epics_key(tmp_path):
    """Test handling of YAML without 'epics' key."""
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("stories:\n  6-5:\n    status: done")

    updates = {"6-5": "done"}

    with pytest.raises(ValueError, match="missing 'epics' key"):
        update_sprint_status_yaml(invalid_yaml, updates)


def test_update_yaml_dry_run(temp_yaml_file):
    """Test dry-run mode doesn't modify file (AC 13)."""
    original_content = temp_yaml_file.read_text()

    updates = {"6-5": "done"}
    updated, _ = update_sprint_status_yaml(temp_yaml_file, updates, dry_run=True)

    assert updated == 1  # Would have updated

    # File should be unchanged
    assert temp_yaml_file.read_text() == original_content


# Git Integration Tests


@patch("subprocess.Popen")
def test_get_git_commits_success(mock_popen):
    """Test successful git log execution."""
    mock_process = Mock()
    mock_process.stdout = ["abc123 Commit 1\n", "def456 Commit 2\n"]
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    commits = get_git_commits(num_commits=2)

    assert len(commits) == 2
    assert commits[0] == "abc123 Commit 1"
    assert commits[1] == "def456 Commit 2"

    mock_popen.assert_called_once_with(
        ["git", "log", "--oneline", "-2"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@patch("subprocess.Popen")
def test_get_git_commits_failure(mock_popen):
    """Test git command failure handling."""
    mock_process = Mock()
    mock_process.stdout = []
    mock_process.wait.return_value = 1
    mock_process.stderr.read.return_value = "fatal: git error"
    mock_popen.return_value = mock_process

    with pytest.raises(subprocess.CalledProcessError):
        get_git_commits()


# Integration Test


def test_end_to_end_workflow(temp_yaml_file):
    """Test complete workflow: parse commits → update YAML (AC 14)."""
    commits = [
        "a1b2c3d Story 6.3: Grafana dashboards complete",
        "e4f5g6h Story 6.4 complete",
        "i7j8k9l Story 6.5 complete",
        "m0n1o2p WIP Story 7.1 installer started",
    ]

    # Parse commits
    updates = parse_story_updates(commits)

    assert len(updates) == 4
    assert updates["6-3"] == "done"
    assert updates["6-4"] == "done"
    assert updates["6-5"] == "done"
    assert updates["7-1"] == "in-progress"

    # Update YAML
    updated, not_found = update_sprint_status_yaml(temp_yaml_file, updates)

    assert updated == 4
    assert not_found == 0

    # Verify final state
    from ruamel.yaml import YAML

    yaml = YAML()
    with open(temp_yaml_file) as f:
        data = yaml.load(f)

    assert (
        data["epics"]["epic-6"]["stories"]["6-3-pre-built-grafana-dashboards"]["status"]
        == "done"
    )
    assert (
        data["epics"]["epic-6"]["stories"]["6-4-streamlit-memory-browser"]["status"]
        == "done"
    )
    assert (
        data["epics"]["epic-6"]["stories"]["6-5-retrieval-session-logs"]["status"]
        == "done"
    )
    assert (
        data["epics"]["epic-7"]["stories"]["7-1-single-command-installer-script"][
            "status"
        ]
        == "in-progress"
    )
