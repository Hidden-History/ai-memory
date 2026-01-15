# GitHub Milestones Setup

This document provides the configuration for GitHub milestones to track progress on planned releases.

## How to Create Milestones

Navigate to: `https://github.com/wbsolutions-ca/bmad-memory/milestones/new`

Or use the GitHub CLI:

```bash
gh milestone create "TITLE" --repo wbsolutions-ca/bmad-memory --due-date YYYY-MM-DD --description "DESCRIPTION"
```

---

## Milestone 1: v1.1.0 - Performance & Stability

**Title:** `v1.1.0 - Performance & Stability`

**Due Date:** `2026-03-31` (Q1 2026)

**Description:**
```
Production hardening and performance optimization release.

Focus Areas:
- Query optimization for large collections (>100k memories)
- Enhanced error recovery and stability
- Developer experience improvements (CLI, VS Code extension)
- Memory usage reduction in hooks

See ROADMAP.md for detailed feature list.
```

**State:** Open

---

## Milestone 2: v1.2.0 - Advanced Features

**Title:** `v1.2.0 - Advanced Features`

**Due Date:** `2026-06-30` (Q2 2026)

**Description:**
```
Intelligence and integration enhancements.

Focus Areas:
- Context-aware memory ranking
- Temporal memory decay
- GitHub Copilot integration
- Slack notifications
- Loki log aggregation
- Advanced monitoring dashboards

See ROADMAP.md for detailed feature list.
```

**State:** Open

---

## Milestone 3: v2.0.0 - Major Enhancements

**Title:** `v2.0.0 - Major Architectural Improvements`

**Due Date:** TBD (Based on community demand)

**Description:**
```
Major architectural improvements and enterprise features.

Focus Areas:
- Plugin system for custom extractors
- Distributed deployment support
- Alternative vector DB support (Milvus, Weaviate)
- Team collaboration features
- SSO and RBAC

See ROADMAP.md for detailed feature list.

Note: This is a BREAKING CHANGE release - backward compatibility not guaranteed.
```

**State:** Open

---

## GitHub CLI Script

To create all milestones at once:

```bash
#!/usr/bin/env bash
# create-milestones.sh

REPO="wbsolutions-ca/bmad-memory"

echo "Creating v1.1.0 milestone..."
gh milestone create "v1.1.0 - Performance & Stability" \
  --repo "$REPO" \
  --due-date 2026-03-31 \
  --description "Production hardening and performance optimization release. Focus: Query optimization, error recovery, developer experience. See ROADMAP.md for details."

echo "Creating v1.2.0 milestone..."
gh milestone create "v1.2.0 - Advanced Features" \
  --repo "$REPO" \
  --due-date 2026-06-30 \
  --description "Intelligence and integration enhancements. Focus: Context-aware ranking, temporal decay, integrations (Copilot, Slack), Loki logging. See ROADMAP.md for details."

echo "Creating v2.0.0 milestone..."
gh milestone create "v2.0.0 - Major Architectural Improvements" \
  --repo "$REPO" \
  --description "Major architectural improvements and enterprise features. Focus: Plugin system, distributed deployment, alternative DBs, team features, SSO/RBAC. BREAKING CHANGES. See ROADMAP.md for details."

echo "✅ Milestones created successfully!"
```

---

## Milestone Management

### Linking Issues to Milestones
When creating or triaging issues, assign them to the appropriate milestone:

```bash
gh issue edit ISSUE_NUMBER --milestone "v1.1.0 - Performance & Stability" --repo wbsolutions-ca/bmad-memory
```

### Checking Progress
View milestone progress:

```bash
gh milestone view "v1.1.0 - Performance & Stability" --repo wbsolutions-ca/bmad-memory
```

### Updating Due Dates
If a milestone needs to be delayed:

```bash
gh api repos/wbsolutions-ca/bmad-memory/milestones/MILESTONE_NUMBER \
  --method PATCH \
  -f due_on='2026-04-30T00:00:00Z'
```

### Closing Milestones
When all issues are resolved and the release is published:

```bash
gh api repos/wbsolutions-ca/bmad-memory/milestones/MILESTONE_NUMBER \
  --method PATCH \
  -f state='closed'
```

---

## Best Practices

1. **Keep milestones focused** - Don't overload with too many issues
2. **Review regularly** - Check progress weekly and adjust priorities
3. **Move issues when needed** - If an issue won't make the milestone, move it to the next one
4. **Communicate changes** - Update ROADMAP.md when milestone dates shift
5. **Celebrate completions** - When a milestone closes, create a GitHub Release and share progress

---

**See Also:**
- [ROADMAP.md](../ROADMAP.md) - Detailed feature roadmap
- [GitHub Milestones](https://github.com/wbsolutions-ca/bmad-memory/milestones) - Live milestone tracking
