---
name: 'step-01-summarize-session'
description: 'Summarize all session work including tasks completed, decisions made, and blockers logged'
nextStepFile: './step-02-update-tracking.md'
---

# Step 1: Summarize Session Work

**Progress: Step 1 of 5** — Next: Update Tracking Files

## STEP GOAL:

Create a comprehensive summary of everything accomplished during this session: tasks completed, decisions made, blockers encountered, issues resolved, and files modified.

**Scope:**
- Available context: Full conversation history from this session, task tracker at `{oversight_path}/tracking/task-tracker.md`, decision log, blockers log
- Focus: Session summarization only — do not begin tracking file updates
- Limits: Summarize what happened — do not add commentary or planning
- Dependencies: None — this is the first step of the session close workflow

- Focus on summarizing what happened — no planning or forward actions
**Behavioral Constraints:**
- FORBIDDEN to add commentary, assumptions, or future recommendations
- Approach: Systematic cataloging of completed work, decisions, blockers, and learnings
- Session index maintenance must be checked before compiling executive summary

## Sequence

### 1. Catalog Completed Work

List every task or work item that was completed (or progressed) during this session:
- Task ID and title
- What specifically was done
- Whether it is fully complete or partially done
- Evidence of completion (files created, tests passing, etc.)

---

### 2. Catalog Decisions Made

List every decision made during this session:
- What was decided
- What options were considered
- What was chosen and why
- Whether it was logged to the decision log (if not, flag for Step 2)

---

### 3. Catalog Blockers Encountered

List every blocker encountered during this session:
- What was blocked
- How it was resolved (or if it is still open)
- Whether it was logged to the blockers log (if not, flag for Step 2)

---

### 4. Catalog Issues and Resolutions

For each issue encountered:
- What the issue was
- How it was resolved (or "Pending" if unresolved)
- What to remember for future sessions (learning)

---

### 5. Catalog Files Modified

List every file that was created, modified, or deleted during this session:
- File path
- What changed
- Current state

---

### 6. Identify Pending Items

Items that need attention before closeout is complete:
- Unlogged decisions
- Unlogged blockers
- Tasks that need status updates
- Documentation that should be updated

---

### 7. Capture Learnings

Document insights from this session for future reference:
- **What worked well**: Process improvements, effective patterns, tools that helped
- **What didn't work**: Approaches that failed, time sinks, antipatterns encountered
- **What should change**: Process adjustments, template updates, workflow improvements
- **Action items**: Specific improvements to implement (update in `{oversight_path}/learning/` if significant)

If no notable learnings this session, state "No significant learnings this session" and proceed.

---

### 8. Check Session Index Maintenance

Before proceeding to the next step, check if `{oversight_path}/SESSION_WORK_INDEX.md` needs sharding:

**Threshold checks** (perform both):
1. Line count: Is the file > 80 lines?
2. Session count: Are there more than 5 sessions in the "Last 5 Sessions" table?

**If EITHER threshold is exceeded**:
1. Identify sessions older than the 5 most recent
2. Append each archived session as a new table row in the correct month/week section of `{oversight_path}/session-index/INDEX.md`:
   `| {date} | {session topic} | {TASK-ID} | {1-sentence summary} | \`session-logs/SESSION_HANDOFF_{date}.md\` |`
   If the current week section does not exist yet in INDEX.md, add it following the existing table format.
3. Remove archived entries from SESSION_WORK_INDEX.md
4. Verify: SESSION_WORK_INDEX.md < 80 lines, exactly 5 sessions remain in "Last 5 Sessions", no session data was lost

**If thresholds are NOT exceeded**: Note "Index maintenance not needed" and proceed.

**DO NOT**: Delete session data without archiving. Let the file exceed 100 lines. Skip index updates.

---

### 9. Compile Executive Summary

Write a 2-3 sentence summary:
- What was accomplished
- Current state of the project
- What should happen next

### 10. Update Sanctum Files

After creating the session handoff, update the Parzival sanctum:

1. **LORE.md** — If this session produced new high-value project knowledge (architectural decisions, validated patterns, key learnings), append a curated entry to `{project-root}/_ai-memory/sanctum/parzival/LORE.md`. Keep under 200 lines total — if approaching the limit, consolidate older entries.

2. **BOND.md** — If the user provided new feedback about how Parzival should work (corrections, preferences, confirmed approaches), update the relevant section in `{project-root}/_ai-memory/sanctum/parzival/BOND.md`.

3. **CREED.md frontmatter** — Increment `sessions_completed` and update `last_session` date in the YAML frontmatter.

4. **PERSONA.md evolution log** — Append a one-line session entry to the evolution log if identity-relevant changes occurred this session.

If sanctum files don't exist (not yet initialized), skip this section silently.

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the complete session summary is compiled, load and read fully {nextStepFile}
