# GitHub Labels for AI Memory Module

This document defines the label system for organizing issues and pull requests.

## Label Categories

### Type Labels
Labels indicating the nature of the issue or PR.

| Label | Color | Description |
|-------|-------|-------------|
| `type: bug` | `#d73a4a` (red) | Something isn't working correctly |
| `type: feature` | `#0e8a16` (green) | New feature or request |
| `type: docs` | `#0075ca` (blue) | Documentation improvements or additions |
| `type: enhancement` | `#a2eeef` (light cyan) | Enhancement to existing feature |
| `type: refactor` | `#d4c5f9` (light purple) | Code refactoring (no functional changes) |
| `type: performance` | `#fbca04` (yellow) | Performance improvements |
| `type: security` | `#b60205` (dark red) | Security-related issues |
| `type: test` | `#1d76db` (blue) | Testing-related changes |

### Priority Labels
Labels indicating urgency and importance.

| Label | Color | Description |
|-------|-------|-------------|
| `priority: critical` | `#b60205` (dark red) | Blocks production use, needs immediate attention |
| `priority: high` | `#d93f0b` (orange) | Important issue, should be addressed soon |
| `priority: medium` | `#fbca04` (yellow) | Moderate importance |
| `priority: low` | `#c5def5` (light gray) | Nice to have, low priority |

### Component Labels
Labels indicating which part of the system is affected.

| Label | Color | Description |
|-------|-------|-------------|
| `component: hooks` | `#1d76db` (blue) | Claude Code hook scripts |
| `component: docker` | `#0dcaf0` (cyan) | Docker services (Qdrant, Embedding, Streamlit) |
| `component: python-core` | `#7209b7` (purple) | Python core modules (src/memory/) |
| `component: installer` | `#198754` (green) | Installation scripts and setup |
| `component: monitoring` | `#fd7e14` (orange) | Prometheus, Grafana, metrics |
| `component: documentation` | `#0075ca` (blue) | README, INSTALL, TROUBLESHOOTING |
| `component: cli` | `#6f42c1` (purple) | Command-line tools and scripts |

### Status Labels
Labels indicating the current state of an issue or PR.

| Label | Color | Description |
|-------|-------|-------------|
| `status: needs-triage` | `#ededed` (light gray) | Needs initial review and prioritization |
| `status: in-progress` | `#0075ca` (blue) | Actively being worked on |
| `status: blocked` | `#d93f0b` (orange) | Blocked by external dependency or other issue |
| `status: ready-for-review` | `#0e8a16` (green) | Ready for code review (PR only) |
| `status: needs-info` | `#d4c5f9` (light purple) | Waiting for more information from reporter |
| `status: stale` | `#fef2c0` (yellow) | No activity for extended period |

### Special Labels
Special purpose labels.

| Label | Color | Description |
|-------|-------|-------------|
| `good first issue` | `#7057ff` (purple) | Good for newcomers to the project |
| `help wanted` | `#008672` (teal) | Community contributions welcome |
| `question` | `#d876e3` (pink) | Support question (should use Discussions instead) |
| `duplicate` | `#cfd3d7` (gray) | This issue already exists |
| `wontfix` | `#ffffff` (white) | This will not be worked on |
| `invalid` | `#e4e669` (yellow) | This doesn't seem right or is incomplete |
| `breaking change` | `#b60205` (dark red) | Introduces breaking changes to API/behavior |

## Label Usage Guidelines

### For Issue Triagers
1. **New issues** should get `status: needs-triage` automatically
2. Add one `type:` label (required)
3. Add one `component:` label if applicable
4. Add one `priority:` label after assessment
5. Update `status:` label as work progresses

### For Contributors
1. Check labels before starting work to avoid duplicates
2. Look for `good first issue` if you're new to the project
3. Comment on issues labeled `help wanted` if interested

### For Maintainers
1. Use `status: needs-info` and give 7-day grace period before closing
2. Apply `duplicate` with link to original issue
3. Use `wontfix` with clear explanation of reasoning
4. Mark breaking changes clearly with `breaking change` label

## Label Creation Script

For repository administrators, here's a script to create all labels:

```bash
#!/usr/bin/env bash
# create-labels.sh - Create GitHub labels for AI Memory Module

REPO="Hidden-History/ai-memory"

# Type Labels
gh label create "type: bug" --color d73a4a --description "Something isn't working correctly" --repo "$REPO"
gh label create "type: feature" --color 0e8a16 --description "New feature or request" --repo "$REPO"
gh label create "type: docs" --color 0075ca --description "Documentation improvements" --repo "$REPO"
gh label create "type: enhancement" --color a2eeef --description "Enhancement to existing feature" --repo "$REPO"
gh label create "type: refactor" --color d4c5f9 --description "Code refactoring" --repo "$REPO"
gh label create "type: performance" --color fbca04 --description "Performance improvements" --repo "$REPO"
gh label create "type: security" --color b60205 --description "Security-related issues" --repo "$REPO"
gh label create "type: test" --color 1d76db --description "Testing-related changes" --repo "$REPO"

# Priority Labels
gh label create "priority: critical" --color b60205 --description "Blocks production, needs immediate attention" --repo "$REPO"
gh label create "priority: high" --color d93f0b --description "Important, address soon" --repo "$REPO"
gh label create "priority: medium" --color fbca04 --description "Moderate importance" --repo "$REPO"
gh label create "priority: low" --color c5def5 --description "Low priority" --repo "$REPO"

# Component Labels
gh label create "component: hooks" --color 1d76db --description "Hook scripts" --repo "$REPO"
gh label create "component: docker" --color 0dcaf0 --description "Docker services" --repo "$REPO"
gh label create "component: python-core" --color 7209b7 --description "Python core modules" --repo "$REPO"
gh label create "component: installer" --color 198754 --description "Installation scripts" --repo "$REPO"
gh label create "component: monitoring" --color fd7e14 --description "Prometheus, Grafana, metrics" --repo "$REPO"
gh label create "component: documentation" --color 0075ca --description "Documentation" --repo "$REPO"
gh label create "component: cli" --color 6f42c1 --description "CLI tools" --repo "$REPO"

# Status Labels
gh label create "status: needs-triage" --color ededed --description "Needs initial review" --repo "$REPO"
gh label create "status: in-progress" --color 0075ca --description "Being worked on" --repo "$REPO"
gh label create "status: blocked" --color d93f0b --description "Blocked by dependency" --repo "$REPO"
gh label create "status: ready-for-review" --color 0e8a16 --description "Ready for code review" --repo "$REPO"
gh label create "status: needs-info" --color d4c5f9 --description "Waiting for more info" --repo "$REPO"
gh label create "status: stale" --color fef2c0 --description "No activity for extended period" --repo "$REPO"

# Special Labels
gh label create "good first issue" --color 7057ff --description "Good for newcomers" --repo "$REPO"
gh label create "help wanted" --color 008672 --description "Community contributions welcome" --repo "$REPO"
gh label create "question" --color d876e3 --description "Support question" --repo "$REPO"
gh label create "duplicate" --color cfd3d7 --description "Already exists" --repo "$REPO"
gh label create "wontfix" --color ffffff --description "Will not be worked on" --repo "$REPO"
gh label create "invalid" --color e4e669 --description "Incomplete or incorrect" --repo "$REPO"
gh label create "breaking change" --color b60205 --description "Breaking changes" --repo "$REPO"

echo "✅ Labels created successfully!"
```

## Automated Labeling

See `.github/workflows/community.yml` for automated label assignment based on:
- File paths changed in PRs
- Keywords in issue/PR titles
- Issue template selections
