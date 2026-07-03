---
name: 'step-02-compile-status'
description: 'Compile all loaded context into a structured session status report'
nextStepFile: './step-02b-plan-bearings.md'
---

# Step 2: Compile Status Report

**Progress: Step 2 of 5** — Next: Plan Bearings

## STEP GOAL:

Take the context loaded in Steps 1 and 1b and compile it into a structured status report ready for presentation to the user.

**Scope:**
- Available context: All context loaded and organized in Steps 1 and 1b
- Focus: Status compilation only — recommendations are added in Step 3 based on this compiled data
- Limits: Compile status facts only — do not present or act on the report
- Dependencies: Organized context from Steps 1 and 1b

- Compile status fields factually from loaded context — no recommendations or interpretations
**Behavioral Constraints:**
- FORBIDDEN to add recommendations or opinions to the compiled report
- Approach: Factual compilation — flag anomalies but do not resolve them
- All loaded context from Steps 1 and 1b must be reflected in the report

## Sequence

### 1. Determine Session Continuity

Based on the loaded context, classify this session:
- **Continuation**: Previous handoff exists, work was in progress
- **Fresh start**: No handoff exists, or previous work was completed
- **Recovery**: Previous session ended unexpectedly (no handoff, but work was in progress)

---

### 2. Build Status Fields

Compile each field from the loaded context:

**Last Session**:
- Date: from handoff or SESSION_WORK_INDEX
- Summary: 1-sentence description of what was accomplished

**Current Task**:
- ID: from task-tracker (the task marked as "doing" or most recently active)
- Title: task title
- Status: doing / blocked / review / backlog

**Active Blockers**:
- Count of unresolved blockers
- Brief description of each (1 line per blocker)

**Risks**:
- Count of high/critical risks
- Brief description of each (1 line per risk)

**Tracking Totals** (from the bug/TD INDEX `## Quick Stats` loaded in Step 1):
- Bugs: N open / M closed
- Tech-Debt: N open / M closed
- If an INDEX was missing, note that here instead of counts

**SOT Drift** (aim-sot ambient surface — the `[ST]` channel; only when `<project-root>/.sot/registry.yaml` exists):
- Read-only digest: `bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_consult.py" digest --json --registry <project-root>/.sot/registry.yaml`
- Surface the one-line rollup from the output: `drift: <clean> clean, <stale> stale, <unverified> unverified, <changed> changed, <docs_stale> docs-stale` (the `changed` / `docs-stale` counts come from `drift_rollup`)
- If no `.sot/registry.yaml` exists, surface the one-line G3 bootstrap nudge instead ("no SOT registry — run `aim-sot detect-propose` to start tracking") — do not fabricate counts

**Continuation Point**:
- Where work should resume based on handoff "Next Steps" or current task status

---

### 3. Identify Gaps or Anomalies

Flag if:
- Task tracker shows a task as "doing" but handoff says it was completed
- Blockers reference tasks that are marked as done
- Risk register has not been updated recently
- Any tracking file was missing
- A bug/TD INDEX `**Last Updated**` date is well behind the current session — stale INDEX; flag it (run `/aim-tracking-freshness` to refresh)

Note these as items to mention during presentation, not as recommendations.

---

### 4. Check Shared Task List (Informational)

Call TaskList to display current Claude Code task state:
- If tasks exist: include count, in-progress items, and blocked items in the status report
- If empty: note "Task list is empty -- no in-progress CC tasks"
- If CLAUDE_CODE_TASK_LIST_ID is not configured: note "Cross-session task persistence
  requires CLAUDE_CODE_TASK_LIST_ID -- tracking via oversight docs only"

**Note**: TaskList is an informational read-only check. It provides supplemental visibility into
active Claude Code tasks but does not replace the project-status.md and oversight tracking
files as the authoritative source of project state.

Include task list state alongside project-status.md summary in the compiled report.

---

### 5. Format the Report

Structure the compiled data using the presentation format defined in the next step. Do not present yet -- just prepare the content.

## CRITICAL STEP COMPLETION NOTE

ONLY when the status report is fully compiled, load and read fully {nextStepFile}
