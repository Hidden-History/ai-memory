---
name: 'step-03-create-handoff'
description: 'Create the session handoff document and update the SESSION_WORK_INDEX'
nextStepFile: './step-04-save-and-confirm.md'
handoffTemplate: '{project-root}/_ai-memory/pov/templates/session-handoff.template.md'
---

# Step 3: Create Handoff Document

**Progress: Step 3 of 4** — Next: Save and Confirm

## STEP GOAL:

Write the session handoff document for the next Parzival session and update the SESSION_WORK_INDEX with a reference to it.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Session summary from Step 1, updated tracking from Step 2
- Focus: Handoff document creation and SESSION_WORK_INDEX update only
- Limits: Write the handoff and update the index — Qdrant save is in the next step
- Dependencies: Session summary from Step 1 and updated tracking from Step 2

- Focus on writing the handoff document and updating SESSION_WORK_INDEX
**Behavioral Constraints:**
- FORBIDDEN to save to Qdrant in this step — that is Step 4
- Approach: Load template if available, write document, verify, then update index
- Verify the written handoff by reading it back before marking complete

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Load Template (If Available)

If `{handoffTemplate}` exists, use it as the format guide. Otherwise, use the format below.

---

### 1b. Capture Branch State Empirically (TD-500 Discipline)

**MANDATORY** — before writing the handoff body, capture branch state with empirical commands. Do NOT extrapolate from prior session counts.

For git-backed projects with a tracked upstream:

```bash
# Commits ahead of base (typically origin/main):
git rev-list --count origin/main..HEAD
# Current HEAD short SHA:
git rev-parse --short HEAD
# Branch name:
git branch --show-current
```

Record the empirical output of each command. Cite the exact integer + SHA + branch name in the handoff body. **NEVER** write "X commits ahead" by adding the previous handoff's count to a session-delta estimate — that is the off-by-one drift pattern TD-500 was logged to prevent (PM #277 said 22, actual was 47; PM #278 said 47, actual was 48).

For non-git projects or when no upstream is configured, note "branch state: N/A (no upstream)" and skip.

**Why this matters**: future Parzival relies on the commits-ahead stat for "how big is this branch" sanity checks. Drift compounds across sessions if each handoff extrapolates rather than empirically re-counts. Per `feedback_multi_session_plan_handoff_protocol` §10 mandate.

---

### 2. Write Handoff Document

Create file: `{oversight_path}/session-logs/SESSION_HANDOFF_{date}.md`

Where `{date}` is today's date in YYYY-MM-DD format.

```markdown
# Session Handoff: [Primary Topic]

**Date**: [YYYY-MM-DD]
**Session Duration**: [Approximate time]

## Executive Summary
[2-3 sentences: What was accomplished, current state, what is next]

## Work Completed
- [Task ID]: [Description of what was done]
- [Include all completed items with IDs]

## Current Status
- **Active Task**: [ID] [Title] - [Status]
- **Blockers**: [List or "None"]
- **In Progress**: [What is partially done]

## Branch State (TD-500: empirically measured, never extrapolated)
- **Branch**: [output of `git branch --show-current`]
- **Head**: [output of `git rev-parse --short HEAD`]
- **Commits ahead of base**: [output of `git rev-list --count origin/main..HEAD`] (verified via `git rev-list`, NOT extrapolated from prior session)

## Issues Encountered
[For each issue:]
- **Issue**: [Description]
- **Resolution**: [How it was resolved OR "Pending"]
- **Learning**: [What to remember for next time]

## Files Modified
- `[path/to/file]` - [What changed]
- [List all modified files]

## Decisions Made
- [Decision]: [Rationale]
- [List any decisions from this session]

## Next Steps (Recommended)
1. [Most important next action]
2. [Second priority]
3. [Third priority]

## Open Questions
- [Any unresolved questions]
- [Things that need user input]

## Context for Future Parzival
[Anything a new instance would need to know that is not captured above.
Write as if the reader has never seen this project.]

---
*Handoff created by session closeout protocol*
```

---

### 3. Verify Handoff

Read the written file back and verify:
- No sections are empty
- Executive summary is accurate
- Next steps are specific and actionable
- "Context for Future Parzival" contains substantive information

---

### 4. Update SESSION_WORK_INDEX

Add entry to `{oversight_path}/SESSION_WORK_INDEX.md`:

```markdown
### [YYYY-MM-DD]: [Brief Topic]
- **Task**: [Task title]
- **Task ID**: [ID]
- **Status**: [In Progress/Complete/Blocked]
- **Progress**: [One sentence on what was accomplished]
- **Handoff**: `session-logs/SESSION_HANDOFF_{date}.md`
```

## CRITICAL STEP COMPLETION NOTE

ONLY when the handoff is written, verified, and the index is updated, load and read fully {nextStepFile}
