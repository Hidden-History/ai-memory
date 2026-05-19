---
name: 'step-01-load-context'
description: 'Load all session context from oversight tracking files and most recent handoff'
nextStepFile: './step-01b-parzival-bootstrap.md'
scaffold: '{workflows_path}/STEP-SCAFFOLD.md'
---

# Step 1: Load Context

**Progress: Step 1 of 4** — Next: Parzival Cross-Session Memory Bootstrap

## STEP GOAL:

Load all relevant project context so Parzival has a complete picture of the current state before compiling a status report.

**Scope:**
- Available context: All files under `{oversight_path}/`
- Focus: Context loading only — do not compile status or make recommendations yet
- Limits: Read only — do not modify any files during context loading
- Dependencies: None — this is the first step of the session/start workflow
- FORBIDDEN to skip any context file that exists
- Approach: Read-only pass, organized by category; missing files noted but do not block

## Context to Load

Load each of the following so Parzival has the complete current state before Step 2. Order is not significant — any missing file is noted and does not block execution.

### 1. Read Session Work Index

Read `{oversight_path}/SESSION_WORK_INDEX.md` to understand the current project state and most recent session entry.

If the file does not exist, note this as a first-session scenario and proceed with available files.

---

### 2. Identify Most Recent Handoff (Deferred Read)

[HANDOFF-DEFERRED: awaiting Qdrant L1 result in Step 1b]

Do NOT read the handoff file at this step. Qdrant L1 may already contain the most recent handoff — reading the file here would duplicate work and consume ~4,000 tokens unnecessarily.

**Filename identification only**: List `{oversight_path}/session-logs/SESSION_HANDOFF_*.md` filenames and identify the most recent one by filename date. Record the date for the staleness check in Step 1b. No file content is read here.

If no handoff files exist, note this as a first-session scenario and proceed. Step 1b will handle the Qdrant gate.

---

### 3. Read Task Tracker

Read `{oversight_path}/tracking/task-tracker.md` active sections only: Sprint header, Sprint Status, "Not Started", "In Progress", "In Review", last 3 rows of "Done", and "Blocked". Skip "Previous Sprint" archive and older "Done" rows. Verify section headers, not line numbers.

Extract:
- Current sprint and its tasks
- Status of each task (backlog, doing, blocked, review, done)
- Any tasks that were in-progress at last session end

---

### 4. Read Blockers Log

Read `{oversight_path}/tracking/blockers-log.md` active sections only: "Active Blockers", current blocker detail, and "Severity Definitions". Skip "Resolved Blockers" and detail for resolved blockers. Verify section headers, not line numbers.

Extract:
- Any active (unresolved) blockers
- Severity of each active blocker
- Impact on current work

---

### 5. Read Risk Register

Read `{oversight_path}/tracking/risk-register.md` active sections only: "Active Risks" and "Severity Matrix". Skip "Resolved Risks", "Risk Categories", and older bug logs. Verify section headers, not line numbers.

Extract:
- High or critical risks
- Any risks that have changed status since last session

---

### 6. Read Bug / Tech-Debt INDEX Summaries

Read **only** the `## Quick Stats` table of `{oversight_path}/bugs/INDEX.md` and `{oversight_path}/tech-debt/INDEX.md` to obtain open/closed bug and tech-debt totals.

🚫 FORBIDDEN: do NOT read individual `BUG-*.md` or `TECH-DEBT-*.md` record files at startup — there can be hundreds. The compact INDEX `## Quick Stats` table is the only startup-read surface for bug/TD state.

If an INDEX file does not exist (a fresh project, or `aim-tracking-freshness` has not run yet), note "no bug/TD INDEX — run `/aim-tracking-freshness --write` to generate it" and proceed. A missing INDEX does not block.

Extract:
- Open / closed bug totals
- Open / closed tech-debt totals
- Each INDEX's `**Last Updated**` date (for the staleness check in Step 2)

---

### 7. Compile Loaded Context

Organize the loaded information into these categories:
- **Last session**: date, topic, outcome
- **Current task**: ID, title, status
- **Blockers**: count and brief descriptions
- **Risks**: count of high/critical, brief descriptions
- **Continuation point**: where work should resume

## CRITICAL STEP COMPLETION NOTE

ONLY when all available context files have been read, load and read fully {nextStepFile}
