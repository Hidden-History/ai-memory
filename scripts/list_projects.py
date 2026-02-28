#!/usr/bin/env python3
"""CLI utility to list all registered projects from projects.d/ config directory.

Usage:
    python scripts/list_projects.py
    python scripts/list_projects.py --config-dir /path/to/projects.d
    python scripts/list_projects.py --json

Part of PLAN-009: Multi-project sync infrastructure.
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.config import ProjectSyncConfig, discover_projects


def format_project_table(projects: dict[str, ProjectSyncConfig]) -> str:
    """Format projects as a human-readable table."""
    if not projects:
        return "No projects registered.\n\nTo register a project, create a YAML file in:\n  ~/.ai-memory/config/projects.d/\n\nSee: docs/multi-project.md"

    lines = []
    lines.append(
        f"{'PROJECT ID':<40}  {'GITHUB REPO':<40}  {'BRANCH':<10}  {'ENABLED'}"
    )
    lines.append("-" * 105)

    for project_id, cfg in sorted(projects.items()):
        github_repo = cfg.github_repo or "(none)"
        branch = cfg.github_branch
        enabled = "yes" if cfg.github_enabled else "no"
        lines.append(f"{project_id:<40}  {github_repo:<40}  {branch:<10}  {enabled}")

        if cfg.source_directory:
            lines.append(f"  {'source:':<10} {cfg.source_directory}")
        if cfg.jira_enabled:
            jira_info = cfg.jira_instance_url or "(url not set)"
            jira_projects = (
                ", ".join(cfg.jira_projects) if cfg.jira_projects else "(none)"
            )
            lines.append(f"  {'jira:':<10} {jira_info}  projects={jira_projects}")

    return "\n".join(lines)


def format_project_json(projects: dict[str, ProjectSyncConfig]) -> str:
    """Format projects as JSON output."""
    data = {}
    for project_id, cfg in projects.items():
        data[project_id] = {
            "project_id": cfg.project_id,
            "source_directory": cfg.source_directory,
            "github": {
                "repo": cfg.github_repo,
                "branch": cfg.github_branch,
                "enabled": cfg.github_enabled,
            },
            "jira": {
                "enabled": cfg.jira_enabled,
                "instance_url": cfg.jira_instance_url,
                "projects": cfg.jira_projects,
            },
        }
    return json.dumps(data, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List registered AI Memory projects from projects.d/ config directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/list_projects.py
  python scripts/list_projects.py --json
  python scripts/list_projects.py --config-dir /custom/path/projects.d

See docs/multi-project.md for configuration details.
        """,
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Path to projects.d directory (default: ~/.ai-memory/config/projects.d)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output as JSON instead of table format",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        default=False,
        help="Print only the number of registered projects",
    )

    args = parser.parse_args()

    projects = discover_projects(config_dir=args.config_dir)

    if args.count:
        print(len(projects))
        return 0

    if args.json:
        print(format_project_json(projects))
    else:
        print(format_project_table(projects))

    return 0


if __name__ == "__main__":
    sys.exit(main())
