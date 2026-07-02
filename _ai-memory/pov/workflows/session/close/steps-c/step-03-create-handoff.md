---
name: 'step-03-create-handoff'
description: 'Create the session handoff document and update the SESSION_WORK_INDEX'
nextStepFile: './step-04-enforce-caps.md'
handoffTemplate: '{project-root}/_ai-memory/pov/templates/session-handoff.template.md'
---

# Step 3: Create Handoff Document

**Progress: Step 3 of 6** — Next: Enforce Caps

## STEP GOAL:

Write the session handoff document for the next Parzival session and update the SESSION_WORK_INDEX with a reference to it.

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

## Sequence

### 0. Pre-condition: Verify Handoff Template Exists (TD-520 / TD-500)

Before composing handoff content, confirm the handoff template exists at its
canonical location. The template is the binding site for the TD-500 empirical
commits-ahead capture mandate; the §1 fallback ("use the format below") MUST
NOT silently fire when the template is missing — that path produces a handoff
without the Branch State block.

Check: `_ai-memory/pov/templates/session-handoff.template.md` exists.

**If missing — HALT session-close** with the explicit error:

> Handoff template missing — cannot enforce TD-500 empirical commits-ahead
> capture. Restore template before continuing:
> `_ai-memory/pov/templates/session-handoff.template.md`.

Do NOT degrade to the §1 fallback. Do NOT auto-recover. Operator must restore
the template (e.g., `git checkout _ai-memory/pov/templates/session-handoff.template.md`
or re-run installer) before resuming session-close.

This check is a belt-and-suspenders companion to the same check at step-02
entry — covers any future workflow refactor that bypasses step-02 directly to
step-03.

---

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

**Cap: 60 lines / 8 KB** (detail-record; checked by the Step 4 gate). Keep the
handoff thin: **omit** any section that has nothing to say (do not pad it), and
where something is unchanged from the prior handoff write a **one-line pointer**
to it rather than re-essaying it. The full narrative lives in Qdrant + the
SESSION_WORK_INDEX, never re-stated at length here.

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
- Non-applicable sections are **omitted**, not padded — a section with nothing to say is dropped, never filled with filler
- Where a section is unchanged from the prior handoff it is a **one-line pointer**, not a re-essay
- Executive summary is accurate
- Next steps are specific and actionable
- "Context for Future Parzival" contains substantive information
- The handoff is within its cap (≤60 lines / ≤8 KB) — the Step 4 gate blocks save otherwise

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

---

### 5. Archive Prior Handoffs (Anti-Bloat)

`session-logs/` accumulates one handoff per session and was never pruned. On
close, prune so the live directory stays scannable and only the latest handoff
remains as the whole-file fallback the next session reads:

- Move every prior `SESSION_HANDOFF_*.md` (all but the one just written) into
  `{oversight_path}/session-logs/archive/{YYYY-MM}/`, bucketed by the handoff's
  own date.
- Append a one-line entry per archived handoff to
  `{oversight_path}/session-logs/archive/INDEX.md` (date → topic → path), so the
  history stays greppable in O(1).

The latest handoff stays live; its 60-line / 8-KB cap is enforced by the Step 4
gate.

## CRITICAL STEP COMPLETION NOTE

ONLY when the handoff is written, verified, and the index is updated, load and read fully {nextStepFile}
