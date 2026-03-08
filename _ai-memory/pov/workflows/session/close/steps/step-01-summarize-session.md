---
name: 'step-01-summarize-session'
description: 'Summarize all session work including tasks completed, decisions made, and blockers logged'
nextStepFile: './step-02-update-tracking.md'
---

# Step 1: Summarize Session Work

## STEP GOAL
Create a comprehensive summary of everything accomplished during this session: tasks completed, decisions made, blockers encountered, issues resolved, and files modified.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Full conversation history from this session, task tracker at `{oversight_path}/tracking/task-tracker.md`, decision log, blockers log
- Limits: Summarize what happened -- do not add commentary or planning

## MANDATORY SEQUENCE

### 1. Catalog Completed Work
List every task or work item that was completed (or progressed) during this session:
- Task ID and title
- What specifically was done
- Whether it is fully complete or partially done
- Evidence of completion (files created, tests passing, etc.)

### 2. Catalog Decisions Made
List every decision made during this session:
- What was decided
- What options were considered
- What was chosen and why
- Whether it was logged to the decision log (if not, flag for Step 2)

### 3. Catalog Blockers Encountered
List every blocker encountered during this session:
- What was blocked
- How it was resolved (or if it is still open)
- Whether it was logged to the blockers log (if not, flag for Step 2)

### 4. Catalog Issues and Resolutions
For each issue encountered:
- What the issue was
- How it was resolved (or "Pending" if unresolved)
- What to remember for future sessions (learning)

### 5. Catalog Files Modified
List every file that was created, modified, or deleted during this session:
- File path
- What changed
- Current state

### 6. Identify Pending Items
Items that need attention before closeout is complete:
- Unlogged decisions
- Unlogged blockers
- Tasks that need status updates
- Documentation that should be updated

### 7. Capture Learnings
Document insights from this session for future reference:
- **What worked well**: Process improvements, effective patterns, tools that helped
- **What didn't work**: Approaches that failed, time sinks, antipatterns encountered
- **What should change**: Process adjustments, template updates, workflow improvements
- **Action items**: Specific improvements to implement (update in `{oversight_path}/learning/` if significant)

If no notable learnings this session, state "No significant learnings this session" and proceed.

### 8. Check Session Index Maintenance
Before proceeding to the next step, check if `{oversight_path}/SESSION_WORK_INDEX.md` needs sharding:

**Threshold checks** (perform both):
1. Line count: Is the file > 80 lines?
2. Session count: Are there more than 5 sessions in the "Last 5 Sessions" table?

**If EITHER threshold is exceeded**:
1. Identify sessions older than the 5 most recent
2. Archive to `{oversight_path}/session-index/{YYYY-MM}/week-{N}.md` using format:
   ```
   ### {date}: {Task Title}
   - **Task**: {full title}
   - **Task ID**: {id}
   - **Status**: {status}
   - **Summary**: {summary}
   - **Handoff**: `../session-logs/SESSION_HANDOFF_{date}.md`
   ```
3. Create the directory if needed
4. Update `{oversight_path}/session-index/INDEX.md` if it exists
5. Remove archived entries from SESSION_WORK_INDEX.md
6. Verify: file < 80 lines, exactly 5 sessions remain, no data lost

**If thresholds are NOT exceeded**: Note "Index maintenance not needed" and proceed.

**DO NOT**: Delete session data without archiving. Let the file exceed 100 lines. Skip index updates.

### 9. Compile Executive Summary
Write a 2-3 sentence summary:
- What was accomplished
- Current state of the project
- What should happen next

## CRITICAL STEP COMPLETION NOTE
ONLY when the complete session summary is compiled, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every completed work item is cataloged
- Every decision, blocker, and issue is accounted for
- All modified files are listed
- Pending items are identified for the next step
- Learnings captured (or explicitly noted as none)
- Session index maintenance checked (sharded if needed)
- Executive summary accurately represents the session

### FAILURE:
- Missing completed work items
- Forgetting decisions or blockers that occurred during the session
- Incomplete file modification list
- Skipping learning capture entirely
- Letting SESSION_WORK_INDEX.md exceed 80 lines without sharding
- Vague executive summary
