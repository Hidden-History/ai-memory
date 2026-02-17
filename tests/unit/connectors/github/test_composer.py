"""Tests for GitHub content composer functions (SPEC-006 Section 3.3)."""

from memory.connectors.github.composer import (
    compose_ci_result,
    compose_commit,
    compose_issue,
    compose_issue_comment,
    compose_pr,
    compose_pr_diff,
    compose_pr_review,
)

# -- Issue Composition ------------------------------------------------


def test_compose_issue_basic():
    """Issue composed with title, body, state."""
    issue = {
        "number": 42,
        "title": "Fix storage bug",
        "body": "The store_memory() function fails",
        "state": "open",
        "labels": [],
        "assignees": [],
        "milestone": None,
    }
    result = compose_issue(issue)
    assert "Issue #42: Fix storage bug" in result
    assert "store_memory()" in result
    assert "State: open" in result


def test_compose_issue_with_labels():
    """Labels included in composition."""
    issue = {
        "number": 1,
        "title": "Test",
        "body": "",
        "state": "open",
        "labels": [{"name": "bug"}, {"name": "priority"}],
        "assignees": [],
        "milestone": None,
    }
    result = compose_issue(issue)
    assert "Labels: bug, priority" in result


def test_compose_issue_with_milestone():
    """Milestone included when present."""
    issue = {
        "number": 1,
        "title": "Test",
        "body": "",
        "state": "open",
        "labels": [],
        "assignees": [],
        "milestone": {"title": "v2.0.6"},
    }
    result = compose_issue(issue)
    assert "Milestone: v2.0.6" in result


def test_compose_issue_no_body():
    """Issue without body still composes."""
    issue = {
        "number": 1,
        "title": "Test",
        "body": None,
        "state": "closed",
        "labels": [],
        "assignees": [],
        "milestone": None,
    }
    result = compose_issue(issue)
    assert "Issue #1: Test" in result


# -- Comment Composition ----------------------------------------------


def test_compose_comment():
    """Comment includes author and issue context."""
    comment = {"body": "Looks good to me", "user": {"login": "reviewer"}}
    result = compose_issue_comment(comment, 42)
    assert "Issue #42" in result
    assert "reviewer" in result
    assert "Looks good to me" in result


# -- PR Composition ---------------------------------------------------


def test_compose_pr_basic():
    """PR composed with title, body, branch info."""
    pr = {
        "number": 15,
        "title": "Add sync",
        "body": "Adds GitHub sync",
        "state": "open",
        "merged_at": None,
        "labels": [],
        "base": {"ref": "main"},
        "head": {"ref": "feature/sync"},
    }
    result = compose_pr(pr, [])
    assert "PR #15: Add sync" in result
    assert "main <- feature/sync" in result
    assert "State: open" in result


def test_compose_pr_merged():
    """Merged PR shows merged state."""
    pr = {
        "number": 15,
        "title": "Test",
        "body": "",
        "state": "closed",
        "merged_at": "2026-02-14T00:00:00Z",
        "labels": [],
        "base": {"ref": "main"},
        "head": {"ref": "feat"},
    }
    result = compose_pr(pr, [])
    assert "State: merged" in result


def test_compose_pr_caps_files():
    """Files list capped at 20 with overflow count."""
    pr = {
        "number": 1,
        "title": "Test",
        "body": "",
        "state": "open",
        "merged_at": None,
        "labels": [],
        "base": {"ref": "main"},
        "head": {"ref": "feat"},
    }
    files = [{"filename": f"file{i}.py"} for i in range(25)]
    result = compose_pr(pr, files)
    assert "+5 more" in result


# -- Diff Composition -------------------------------------------------


def test_compose_diff():
    """Diff includes filename, change type, patch."""
    file_entry = {
        "filename": "storage.py",
        "status": "modified",
        "additions": 12,
        "deletions": 3,
        "patch": "@@ -1,5 +1,6 @@\n+new line",
    }
    result = compose_pr_diff(15, file_entry)
    assert "PR #15" in result
    assert "storage.py" in result
    assert "+12 -3" in result
    assert "new line" in result


# -- Review Composition -----------------------------------------------


def test_compose_review():
    """Review includes reviewer, state, body."""
    review = {
        "body": "Needs refactoring",
        "state": "CHANGES_REQUESTED",
        "user": {"login": "lead"},
    }
    result = compose_pr_review(review, 15)
    assert "PR #15" in result
    assert "lead" in result
    assert "changes_requested" in result
    assert "Needs refactoring" in result


# -- Commit Composition -----------------------------------------------


def test_compose_commit_basic():
    """Commit composed with message, stats, author."""
    commit = {
        "sha": "abc12345678",
        "commit": {
            "message": "fix: resolve rate limit",
            "author": {"name": "Dev"},
            "committer": {"date": "2026-02-14T00:00:00Z"},
        },
        "author": {"login": "dev-user"},
        "stats": {"total": 15, "additions": 12, "deletions": 3},
        "files": [{"filename": "client.py"}, {"filename": "test.py"}],
    }
    result = compose_commit(commit)
    assert "abc12345" in result
    assert "fix: resolve rate limit" in result
    assert "+12 -3" in result
    assert "client.py" in result


def test_compose_commit_caps_files():
    """Files list capped at 15."""
    commit = {
        "sha": "abc12345678",
        "commit": {"message": "big change", "author": {"name": "Dev"}},
        "author": {"login": "dev"},
        "stats": {},
        "files": [{"filename": f"f{i}.py"} for i in range(20)],
    }
    result = compose_commit(commit)
    assert "+5 more" in result


# -- CI Result Composition --------------------------------------------


def test_compose_ci_success():
    """Successful CI run composed."""
    run = {
        "name": "test",
        "conclusion": "success",
        "head_sha": "abc12345",
        "head_branch": "main",
    }
    result = compose_ci_result(run)
    assert "CI test: success" in result
    assert "abc12345" in result


def test_compose_ci_failure():
    """Failed CI run includes failure note."""
    run = {
        "name": "lint",
        "conclusion": "failure",
        "head_sha": "abc12345",
        "head_branch": "feature",
    }
    result = compose_ci_result(run)
    assert "FAILED" in result


# -- FIX-10: Defensive Dict Access Tests (FIX-4) ----------------------


def test_compose_issue_missing_title():
    """Issue with missing 'title' key uses fallback."""
    issue = {
        "number": 42,
        "body": "Description",
        "state": "open",
        "labels": [],
        "assignees": [],
        "milestone": None,
    }
    result = compose_issue(issue)
    assert "Issue #42: Untitled" in result
    assert "State: open" in result


def test_compose_issue_missing_number_and_state():
    """Issue with missing 'number' and 'state' uses fallbacks."""
    issue = {
        "title": "Test",
        "body": "",
        "labels": [],
        "assignees": [],
        "milestone": None,
    }
    result = compose_issue(issue)
    assert "Issue #0: Test" in result
    assert "State: unknown" in result


def test_compose_commit_missing_nested_commit():
    """Commit with missing nested 'commit' dict uses fallbacks."""
    commit_data = {
        "sha": "abc12345678",
    }
    result = compose_commit(commit_data)
    assert "abc12345" in result
    assert "No message" in result
    assert "unknown" in result


def test_compose_pr_missing_base_head():
    """PR with missing 'base'/'head' dicts uses fallbacks."""
    pr = {
        "number": 15,
        "title": "Test PR",
        "body": "",
        "state": "open",
        "merged_at": None,
        "labels": [],
    }
    result = compose_pr(pr, [])
    assert "PR #15: Test PR" in result
    assert "unknown <- unknown" in result


def test_compose_pr_missing_number_title():
    """PR with missing 'number' and 'title' uses fallbacks."""
    pr = {
        "body": "",
        "merged_at": None,
        "labels": [],
        "base": {"ref": "main"},
        "head": {"ref": "feat"},
    }
    result = compose_pr(pr, [])
    assert "PR #0: Untitled" in result


def test_compose_pr_diff_missing_filename():
    """Diff with missing 'filename' uses fallback."""
    file_entry = {
        "status": "modified",
        "additions": 1,
        "deletions": 0,
    }
    result = compose_pr_diff(10, file_entry)
    assert "unknown" in result
