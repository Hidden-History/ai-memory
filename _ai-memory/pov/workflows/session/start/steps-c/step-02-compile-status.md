---
name: 'step-02-compile-status'
description: 'Compile all loaded context into a structured session status report'
nextStepFile: './step-03-present-and-wait.md'
---

# Step 2: Compile Status Report

**Progress: Step 2 of 5** — Next: Present and Wait for Direction

## STEP GOAL:

Take the context loaded in Steps 1, 1b, and 1c and compile it into a structured status report ready for presentation to the user.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Compile status fields factually from loaded context — no recommendations or interpretations
- 🚫 FORBIDDEN to add recommendations or opinions to the compiled report
- 💬 Approach: Factual compilation — flag anomalies but do not resolve them
- 📋 All loaded context from Steps 1, 1b, and 1c must be reflected in the report

## EXECUTION PROTOCOLS:

- 🎯 Compile all loaded context into structured status report fields
- 💾 Format report for presentation but do NOT present — Step 3 handles presentation
- 📖 Load next step only after the full report is compiled and formatted
- 🚫 FORBIDDEN to present the report or start work during compilation

## CONTEXT BOUNDARIES:

- Available context: All context loaded and organized in Steps 1, 1b, and 1c
- Focus: Status compilation only — recommendations are added in Step 3 based on this compiled data
- Limits: Compile status facts only — do not present or act on the report
- Dependencies: Organized context from Steps 1, 1b, and 1c

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

**Continuation Point**:
- Where work should resume based on handoff "Next Steps" or current task status

---

### 3. Identify Gaps or Anomalies

Flag if:
- Task tracker shows a task as "doing" but handoff says it was completed
- Blockers reference tasks that are marked as done
- Risk register has not been updated recently
- Any tracking file was missing

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All loaded context is reflected in the status report
- Status fields are factual, not interpretive
- Anomalies are noted without recommendations
- Report is ready for presentation

### ❌ SYSTEM FAILURE:

- Omitting loaded context from the report
- Adding recommendations or opinions to the compiled report
- Presenting the report before it is fully compiled
- Ignoring anomalies between tracking files

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
