---
class: live-index
read_path: whole-file
owns: "live session narrative + recent-session window"
cap_lines: 80
cap_kb: 12
rotation_trigger: on-close-over-cap
archive_target: session-index/INDEX.md
index_file: N/A
reconciliation: "bounded window, shed oldest sessions → session-index/, header = one datestamp line"
---
# Session Work Index

**Purpose**: Quick context loading for session start (~400 tokens max)
**Updated**: [YYYY-MM-DD]

---

## Current Sprint

**Sprint**: [Sprint Name/ID]
**Goal**: [One sentence goal]
**Status**: In Progress | Complete | Blocked

---

## Active Task

| Field | Value |
|-------|-------|
| ID | [TASK-XXX] |
| Title | [Task title] |
| Status | In Progress | Blocked |
| Spec | `specs/[spec-file.md]` (if applicable) |

---

## Last 5 Sessions

<!-- Keep ONLY last 5. Move older to session-index/[YYYY-MM]/week-N.md -->

| Date | Task ID | Summary | Status |
|------|---------|---------|--------|
| [YYYY-MM-DD] | [ID] | [One sentence] | ✅ |
| [YYYY-MM-DD] | [ID] | [One sentence] | ✅ |

---

## Active Blockers

<!-- List only ACTIVE blockers. Resolved blockers go to blockers-log.md -->

| ID | Description | Status |
|----|-------------|--------|
| [BLK-XXX] | [Brief] | Awaiting X |

_None_ (if no active blockers)

---

## High Priority Risks

<!-- List only HIGH priority. Others in risk-register.md -->

| ID | Risk | Mitigation |
|----|------|------------|
| [RISK-XXX] | [Brief] | [Action] |

_None_ (if no high risks)

---

## Quick Links

- **Session history**: `session-index/INDEX.md`
- **Task tracker**: `tracking/task-tracker.md`
- **Decisions**: `tracking/decision-log.md`
- **Blockers**: `tracking/blockers-log.md`
- **Risks**: `tracking/risk-register.md`
