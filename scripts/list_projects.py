#!/usr/bin/env python3
"""CLI utility to list all registered projects from projects.d/ config directory.

Usage:
    python3 scripts/list_projects.py
    python3 scripts/list_projects.py --config-dir /path/to/projects.d
    python3 scripts/list_projects.py --json
    python3 scripts/list_projects.py --count

No virtualenv required — uses only stdlib plus PyYAML.

Part of PLAN-009: Multi-project sync infrastructure.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml")
    sys.exit(1)


# SYNC: keep in sync with src/memory/config.py:ProjectSyncConfig
@dataclass
class ProjectSyncConfig:
    """Per-project sync configuration loaded from projects.d/ YAML."""

    project_id: str
    source_directory: Path | None = None
    github_repo: str | None = None
    github_branch: str = "main"
    github_enabled: bool = True
    jira_enabled: bool = False
    jira_instance_url: str | None = None
    jira_projects: list[str] = dataclass_field(default_factory=list)


def discover_projects(config_dir: Path | None = None) -> dict[str, ProjectSyncConfig]:
    """Scan projects.d/ for per-project YAML configs.

    Resolution order for config_dir:
    1. Explicit ``config_dir`` argument.
    2. ``AI_MEMORY_PROJECTS_DIR`` environment variable.
    3. ``~/.ai-memory/config/projects.d`` — host default.

    Falls back to legacy GITHUB_REPO env var if the resolved directory yields
    no valid configs.

    Note: AI_MEMORY_PROJECTS_DIR is needed because Path.home() inside Docker
    containers resolves to /root, not /config where projects.d/ lives.
    """
    if config_dir is None:
        env_dir = os.environ.get("AI_MEMORY_PROJECTS_DIR")
        if env_dir:
            config_dir = Path(env_dir)
        else:
            config_dir = Path.home() / ".ai-memory" / "config" / "projects.d"

    projects: dict[str, ProjectSyncConfig] = {}

    if config_dir.is_dir():
        yaml_files = sorted(
            list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml"))
        )
        seen_stems: set[str] = set()
        for path in yaml_files:
            if path.stem in seen_stems:
                print(
                    f"Warning: skipping duplicate project config {path.name} (stem already loaded)",
                    file=sys.stderr,
                )
                continue
            seen_stems.add(path.stem)
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not raw or not raw.get("project_id"):
                    print(
                        f"Warning: skipping {path.name}: missing project_id",
                        file=sys.stderr,
                    )
                    continue
                github = raw.get("github") or {}
                jira = raw.get("jira", {})
                jira_proj_raw = jira.get("projects", [])
                if isinstance(jira_proj_raw, str):
                    jira_proj_raw = [jira_proj_raw] if jira_proj_raw else []
                projects[raw["project_id"]] = ProjectSyncConfig(
                    project_id=raw["project_id"],
                    source_directory=(
                        Path(raw["source_directory"])
                        if raw.get("source_directory")
                        else None
                    ),
                    github_repo=github.get("repo"),
                    github_branch=github.get("branch", "main"),
                    github_enabled=github.get("enabled", True),
                    jira_enabled=jira.get("enabled", False),
                    jira_instance_url=jira.get("instance_url"),
                    jira_projects=jira_proj_raw,
                )
            except (yaml.YAMLError, KeyError, TypeError, ValueError) as e:
                print(
                    f"Warning: skipping malformed config {path.name}: {e}",
                    file=sys.stderr,
                )
            except OSError as e:
                print(f"Error: cannot read config {path.name}: {e}", file=sys.stderr)

    if not projects:
        legacy_repo = os.environ.get("GITHUB_REPO")
        if legacy_repo:
            print(
                "Warning: using legacy GITHUB_REPO env var. Migrate to projects.d/. See: docs/multi-project.md",
                file=sys.stderr,
            )
            projects[legacy_repo] = ProjectSyncConfig(
                project_id=legacy_repo,
                github_repo=legacy_repo,
            )

    return projects


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
            "source_directory": (
                str(cfg.source_directory) if cfg.source_directory else None
            ),
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
  python3 scripts/list_projects.py
  python3 scripts/list_projects.py --json
  python3 scripts/list_projects.py --config-dir /custom/path/projects.d

Run via: python3 scripts/list_projects.py (no venv required)

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
