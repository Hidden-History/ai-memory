# GitHub Repository Setup Guide

This guide provides step-by-step instructions for configuring the BMAD Memory Module public repository on GitHub. These are **manual settings** that cannot be configured via Git files alone.

---

## Prerequisites

- [ ] Administrative access to `https://github.com/wbsolutions-ca/bmad-memory`
- [ ] GitHub CLI installed (optional but recommended): `gh --version`
- [ ] v1.0.0 release already published

---

## 1. General Settings

Navigate to: **Settings → General**

### Repository Details

- **Description:**
  ```
  Persistent semantic memory for Claude Code with Qdrant vector storage
  ```

- **Website:**
  ```
  https://github.com/wbsolutions-ca/bmad-memory
  ```

- **Topics:** (Add these tags for discoverability)
  ```
  claude-code, memory, qdrant, vector-database, python, docker, claude, semantic-search, embeddings, hooks
  ```

### Features

- [ ] ✅ **Issues** - Enabled
- [ ] ❌ **Wikis** - Disabled (use `docs/` instead)
- [ ] ✅ **Discussions** - **ENABLE THIS**
- [ ] ✅ **Projects** - Enabled
- [ ] ✅ **Sponsorships** - Enabled (shows sponsor button from `.github/FUNDING.yml`)

### Pull Requests

- [ ] ✅ **Allow merge commits**
- [ ] ✅ **Allow squash merging** (default)
- [ ] ❌ **Allow rebase merging**
- [ ] ✅ **Always suggest updating pull request branches**
- [ ] ✅ **Automatically delete head branches** after PR merge

---

## 2. Collaborators & Teams

Navigate to: **Settings → Collaborators and teams**

### Create Teams (Organization Settings)

Create these teams in your organization:

```bash
# Via GitHub CLI
gh api orgs/wbsolutions-ca/teams -f name='bmad-maintainers' -f description='BMAD Memory Module core maintainers' -f privacy='closed'
gh api orgs/wbsolutions-ca/teams -f name='docker-experts' -f description='Docker and infrastructure specialists' -f privacy='closed'
gh api orgs/wbsolutions-ca/teams -f name='python-core' -f description='Python core development team' -f privacy='closed'
gh api orgs/wbsolutions-ca/teams -f name='monitoring-team' -f description='Monitoring experts' -f privacy='closed'
gh api orgs/wbsolutions-ca/teams -f name='security-team' -f description='Security review team' -f privacy='closed'
```

### Assign Team Permissions

| Team | Permission | Purpose |
|------|------------|---------|
| `@wbsolutions-ca/bmad-maintainers` | **Admin** | Full repo access |
| `@wbsolutions-ca/docker-experts` | **Write** | Docker/infrastructure PRs |
| `@wbsolutions-ca/python-core` | **Write** | Python core PRs |
| `@wbsolutions-ca/monitoring-team` | **Write** | Monitoring PRs |
| `@wbsolutions-ca/security-team` | **Write** | Security reviews |

---

## 3. Branch Protection Rules

Navigate to: **Settings → Branches → Add branch protection rule**

### Protected Branch: `main`

**Branch name pattern:** `main`

#### Protect matching branches

- [ ] ✅ **Require a pull request before merging**
  - [ ] ✅ Require approvals: **1**
  - [ ] ✅ Dismiss stale pull request approvals when new commits are pushed
  - [ ] ✅ Require approval of the most recent reviewable push

- [ ] ✅ **Require status checks to pass before merging**
  - [ ] ✅ Require branches to be up to date before merging

#### Rules applied to everyone including administrators

- [ ] ✅ **Include administrators**
- [ ] ❌ **Allow force pushes** (NEVER enable)
- [ ] ❌ **Allow deletions** (NEVER enable)

---

## 4. GitHub Labels

Run the label creation script from `.github/LABELS.md`:

```bash
# Copy the script from the "Label Creation Script" section in .github/LABELS.md
# Or run directly from repository root:
# (Extract script section and run, or execute commands individually)
```

Or manually create labels via **Issues → Labels → New label**

**Verify:** You should have 32 labels across 5 categories.

---

## 5. GitHub Milestones

Create milestones from `.github/MILESTONES.md`:

```bash
# Copy the script from the "GitHub CLI Script" section in .github/MILESTONES.md
# Or run directly from repository root:
# (Extract script section and run, or execute commands individually)
```

**Expected Milestones:**
1. `v1.1.0 - Performance & Stability` (Due: 2026-03-31)
2. `v1.2.0 - Advanced Features` (Due: 2026-06-30)
3. `v2.0.0 - Major Architectural Improvements` (Due: TBD)

---

## 6. GitHub Discussions

Navigate to: **Settings → General → Features → Discussions → Set up discussions**

### Create Discussion Categories

| Category | Format | Description |
|----------|--------|-------------|
| **💬 General** | Open-ended | General discussions |
| **💡 Ideas** | Open-ended | Feature suggestions |
| **🙏 Q&A** | Q&A | Questions (enable Answer marking) |
| **📢 Announcements** | Announcement | Updates (maintainers only) |
| **🐛 Troubleshooting** | Open-ended | Help with issues |
| **🎉 Show and Tell** | Open-ended | Share your setups |

---

## 7. GitHub Actions Permissions

Navigate to: **Settings → Actions → General**

### Actions permissions
- [ ] ✅ **Allow all actions and reusable workflows**

### Workflow permissions
- [ ] ✅ **Read and write permissions**
- [ ] ✅ **Allow GitHub Actions to create and approve pull requests**

---

## 8. Verification Checklist

### Repository Settings
- [ ] Description and topics set
- [ ] Discussions enabled
- [ ] Sponsor button visible

### Access Control
- [ ] Teams created and assigned
- [ ] Branch protection on `main` active

### Issue Management
- [ ] All labels created
- [ ] Milestones created
- [ ] Issue templates load correctly

### Community
- [ ] Discussions categories created
- [ ] SECURITY.md visible

---

**Setup Completed:** _[Date]_
**Completed By:** _[Name]_
**Last Updated:** 2026-01-14
