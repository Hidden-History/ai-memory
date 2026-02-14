"""Content composition for GitHub API responses.

Transforms raw GitHub API responses into embeddable text documents.
The composed document is what gets embedded and searched -- composition
quality directly impacts retrieval quality.

IMPORTANT: content_hash (SPEC-005 Section 6) is computed on the composed
document output, NOT the raw API response. Changing composition logic
triggers re-embedding (intentional).
"""


def compose_issue(issue: dict) -> str:
    """Compose an issue into embeddable text.

    Args:
        issue: GitHub Issues API response dict

    Returns:
        Composed text for embedding
    """
    labels = ", ".join(l["name"] for l in issue.get("labels", []))
    assignees = ", ".join(a["login"] for a in issue.get("assignees", []))
    milestone = (issue.get("milestone") or {}).get("title", "")

    parts = [f"Issue #{issue.get('number', 0)}: {issue.get('title', 'Untitled')}"]

    if issue.get("body"):
        parts.append(f"\n{issue['body']}")

    meta = []
    if labels:
        meta.append(f"Labels: {labels}")
    if assignees:
        meta.append(f"Assignees: {assignees}")
    if milestone:
        meta.append(f"Milestone: {milestone}")
    meta.append(f"State: {issue.get('state', 'unknown')}")

    if meta:
        parts.append("\n" + " | ".join(meta))

    return "\n".join(parts)


def compose_issue_comment(comment: dict, issue_number: int) -> str:
    """Compose an issue comment into embeddable text.

    Args:
        comment: GitHub Issue Comments API response dict
        issue_number: Parent issue number for context

    Returns:
        Composed text for embedding
    """
    author = (comment.get("user") or {}).get("login", "unknown")
    parts = [
        f"Comment on Issue #{issue_number} by {author}:",
        f"\n{comment.get('body', '')}",
    ]
    return "\n".join(parts)


def compose_pr(pr: dict, files: list[dict]) -> str:
    """Compose a pull request into embeddable text.

    Args:
        pr: GitHub PRs API response dict
        files: List of file dicts from get_pr_files()

    Returns:
        Composed text for embedding
    """
    state = "merged" if pr.get("merged_at") else pr.get("state", "open")
    labels = ", ".join(l["name"] for l in pr.get("labels", []))
    file_list = ", ".join(f["filename"] for f in files[:20])  # Cap at 20 files
    if len(files) > 20:
        file_list += f" (+{len(files) - 20} more)"

    parts = [f"PR #{pr.get('number', 0)}: {pr.get('title', 'Untitled')}"]

    if pr.get("body"):
        parts.append(f"\n{pr['body']}")

    meta = [
        f"State: {state}",
        f"Branch: {(pr.get('base') or {}).get('ref', 'unknown')} <- {(pr.get('head') or {}).get('ref', 'unknown')}",
    ]
    if labels:
        meta.append(f"Labels: {labels}")
    if file_list:
        meta.append(f"Files changed: {file_list}")

    parts.append("\n" + " | ".join(meta))
    return "\n".join(parts)


def compose_pr_diff(pr_number: int, file_entry: dict) -> str:
    """Compose a PR file diff into embeddable text.

    Args:
        pr_number: Parent PR number
        file_entry: File dict from get_pr_files()

    Returns:
        Composed text for embedding
    """
    additions = file_entry.get("additions", 0)
    deletions = file_entry.get("deletions", 0)
    patch = file_entry.get("patch", "")

    parts = [
        f"Diff for PR #{pr_number}: {file_entry.get('filename', 'unknown')}",
        f"Change: {file_entry.get('status', 'modified')} (+{additions} -{deletions})",
    ]

    if patch:
        # Limit patch to first 2000 chars to keep chunk reasonable
        truncated = patch[:2000]
        if len(patch) > 2000:
            truncated += "\n... (diff truncated for embedding)"
        parts.append(f"\n{truncated}")

    return "\n".join(parts)


def compose_pr_review(review: dict, pr_number: int) -> str:
    """Compose a PR review into embeddable text.

    Args:
        review: GitHub PR Reviews API response dict
        pr_number: Parent PR number

    Returns:
        Composed text for embedding
    """
    reviewer = (review.get("user") or {}).get("login", "unknown")
    state = review.get("state", "commented").lower()

    parts = [
        f"Review on PR #{pr_number} by {reviewer} ({state}):",
        f"\n{review.get('body', '')}",
    ]
    return "\n".join(parts)


def compose_commit(commit: dict) -> str:
    """Compose a commit into embeddable text.

    Args:
        commit: GitHub Commits API response dict (full or summary)

    Returns:
        Composed text for embedding
    """
    sha = commit.get("sha", "unknown")[:8]
    message = (commit.get("commit") or {}).get("message", "No message")
    author = (commit.get("author") or {}).get("login", ((commit.get("commit") or {}).get("author") or {}).get("name", "unknown"))

    parts = [f"Commit {sha}: {message}"]

    files = commit.get("files", [])
    stats = commit.get("stats", {})

    if stats:
        parts.append(
            f"\nStats: {stats.get('total', 0)} changes "
            f"(+{stats.get('additions', 0)} -{stats.get('deletions', 0)})"
        )

    if files:
        file_list = ", ".join(f["filename"] for f in files[:15])
        if len(files) > 15:
            file_list += f" (+{len(files) - 15} more)"
        parts.append(f"Files: {file_list}")

    parts.append(f"Author: {author}")
    return "\n".join(parts)


def compose_ci_result(run: dict) -> str:
    """Compose a CI workflow run into embeddable text.

    Args:
        run: GitHub Actions workflow runs API response dict

    Returns:
        Composed text for embedding
    """
    conclusion = run.get("conclusion", run.get("status", "unknown"))
    sha = run.get("head_sha", "")[:8]
    workflow = run.get("name", "unknown")
    branch = run.get("head_branch", "unknown")

    parts = [
        f"CI {workflow}: {conclusion}",
        f"Branch: {branch} | Commit: {sha}",
    ]

    if conclusion == "failure":
        parts.append("Status: FAILED -- check workflow logs for details")

    return "\n".join(parts)
