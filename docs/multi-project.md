# Multi-Project Sync Configuration (PLAN-009)

AI Memory supports syncing multiple GitHub repositories and Jira projects through
a `projects.d/` directory of YAML configuration files.

## Directory Layout

```
~/.ai-memory/config/projects.d/
    my-org-backend.yaml
    my-org-frontend.yaml
    another-project.yaml
```

Each `.yaml` file describes one project. The filename is cosmetic; the `project_id`
field inside the file is the canonical identifier.

## YAML Schema

```yaml
# Required
project_id: "my-org/backend"          # Unique identifier (owner/repo recommended)

# Optional
source_directory: "/path/to/repo"     # Local checkout path (informational)
registered_at: "2026-01-01T00:00:00Z" # Set automatically by install script

github:
  enabled: true                        # Set false to pause sync for this project
  repo: "my-org/backend"              # GitHub owner/repo
  branch: "main"                       # Branch to sync (default: main)

jira:
  enabled: false                       # Set true to enable Jira sync
  instance_url: "https://my-org.atlassian.net"
  projects:                            # Jira project keys to sync
    - PROJ
    - DEV
```

## Registering a Project

### Option A — Automatic (via install script)

Run the standard install and enable GitHub sync when prompted. The installer
calls `register_project_sync()` after verifying your token and repo, creating
the YAML file automatically.

### Option B — Manual

Create a YAML file following the schema above:

```bash
mkdir -p ~/.ai-memory/config/projects.d
cat > ~/.ai-memory/config/projects.d/my-project.yaml <<'EOF'
project_id: "my-org/my-project"
source_directory: "/home/user/repos/my-project"
registered_at: "2026-01-01T00:00:00Z"

github:
  enabled: true
  repo: "my-org/my-project"
  branch: "main"

jira:
  enabled: false
EOF
```

### Option C — Using the Python API

```python
from memory.config import discover_projects

projects = discover_projects()
for project_id, cfg in projects.items():
    print(f"{project_id}: {cfg.github_repo}")
```

## Listing Registered Projects

```bash
# Human-readable table
python scripts/list_projects.py

# JSON output
python scripts/list_projects.py --json

# Custom config directory
python scripts/list_projects.py --config-dir /path/to/projects.d

# Just the count
python scripts/list_projects.py --count
```

## Migrating from Legacy `GITHUB_REPO` Environment Variable

If you previously used the `GITHUB_REPO` environment variable in `.env`:

1. Create a project YAML file as shown above.
2. Remove or comment out `GITHUB_REPO=` from your `.env` file.
3. Restart the `github-sync` Docker service.

The system automatically falls back to `GITHUB_REPO` if `projects.d/` is empty,
but will log a deprecation warning:

```
WARNING Using legacy GITHUB_REPO env var. Migrate to projects.d/. See: docs/multi-project.md
```

## Docker Integration

The `github-sync` service mounts `projects.d/` read-only and sets
`AI_MEMORY_PROJECTS_DIR` so the Python code finds the mounted path instead of
looking inside the container's home directory:

```yaml
environment:
  - AI_MEMORY_PROJECTS_DIR=/config/projects.d
volumes:
  - ${HOME}/.ai-memory/config/projects.d:/config/projects.d:ro
```

`discover_projects()` resolves its config directory in this order:

1. Explicit `config_dir` argument (tests and CLI tools).
2. `AI_MEMORY_PROJECTS_DIR` environment variable (Docker containers).
3. `~/.ai-memory/config/projects.d` (host default).

No Docker restart is required when adding new project files — the sync service
reads the directory on each sync cycle.

## Field Reference

### YAML fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_id` | string | required | Unique identifier for this project |
| `source_directory` | string | null | Local path to the repository checkout |
| `registered_at` | string | null | ISO 8601 timestamp (set by installer) |
| `github.enabled` | bool | true | Enable GitHub sync for this project |
| `github.repo` | string | null | GitHub `owner/repo` |
| `github.branch` | string | `"main"` | Branch to sync |
| `jira.enabled` | bool | false | Enable Jira sync for this project |
| `jira.instance_url` | string | null | Jira Cloud base URL |
| `jira.projects` | list[string] | [] | Jira project keys |

### Environment variables

| Variable | Description |
|----------|-------------|
| `AI_MEMORY_PROJECTS_DIR` | Override the projects.d directory path. Required in Docker containers where `Path.home()` does not match the mounted volume path. Set automatically by `docker-compose.yml`. |
| `GITHUB_REPO` | Legacy single-repo fallback. Deprecated — migrate to a `projects.d/` YAML file. Ignored once the directory contains at least one valid config. |

## Troubleshooting

**Project not appearing in list:**
- Check that the file has a `.yaml` extension (not `.yml`).
- Verify `project_id` is present in the file.
- Run `python scripts/list_projects.py` to see parse errors in output.

**Legacy fallback warning:**
- Migrate by creating a `projects.d/` YAML as described above.
- Once the directory has at least one valid file, the env var is ignored.

**Permission errors on Docker volume:**
- Ensure `~/.ai-memory/config/projects.d/` is readable by the Docker user.
- The volume is mounted `:ro` (read-only), so write permissions are not needed inside the container.
