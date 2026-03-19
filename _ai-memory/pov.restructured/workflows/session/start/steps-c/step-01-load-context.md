---
name: 'step-01-load-context'
description: 'Load all session context from oversight tracking files and most recent handoff'
nextStepFile: './step-01b-parzival-bootstrap.md'
---

# Step 1: Load Context

**Progress: Step 1 of 5** — Next: Parzival Cross-Session Memory Bootstrap

## STEP GOAL:

Load all relevant project context so Parzival has a complete picture of the current state before compiling a status report.

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

- 🎯 Focus on reading all available oversight files — do not modify or analyze yet
- 🚫 FORBIDDEN to skip any context file that exists
- 💬 Approach: Read-only pass, organized by category
- 📋 Missing files are noted but do not block execution

## EXECUTION PROTOCOLS:

- 🎯 Read all oversight tracking files in defined sequence
- 💾 Record loaded context organized by category (last session, task, blockers, risks)
- 📖 Load next step only after all available files have been read
- 🚫 FORBIDDEN to modify any file during context loading

## CONTEXT BOUNDARIES:

- Available context: All files under `{oversight_path}/`
- Focus: Context loading only — do not compile status or make recommendations yet
- Limits: Read only — do not modify any files during context loading
- Dependencies: None — this is the first step of the session/start workflow

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Read Session Work Index

Read `{oversight_path}/SESSION_WORK_INDEX.md` to understand the current project state and most recent session entry.

If the file does not exist, note this as a first-session scenario and proceed with available files.

---

### 2. Read Most Recent Handoff

Find and read the most recent `{oversight_path}/session-logs/SESSION_HANDOFF_*.md` file (sorted by date in filename).

Extract:
- Date and topic of last session
- What was accomplished
- What was in progress
- Recommended next steps
- Open questions

If no handoff files exist, note this as a first-session scenario.

---

### 3. Read Task Tracker

Read `{oversight_path}/tracking/task-tracker.md` to understand:
- Current sprint and its tasks
- Status of each task (backlog, doing, blocked, review, done)
- Any tasks that were in-progress at last session end

---

### 4. Read Blockers Log

Read `{oversight_path}/tracking/blockers-log.md` to identify:
- Any active (unresolved) blockers
- Severity of each active blocker
- Impact on current work

---

### 5. Read Risk Register

Read `{oversight_path}/tracking/risk-register.md` to identify:
- High or critical risks
- Any risks that have changed status since last session

---

### 6. Compile Loaded Context

Organize the loaded information into these categories:
- **Last session**: date, topic, outcome
- **Current task**: ID, title, status
- **Blockers**: count and brief descriptions
- **Risks**: count of high/critical, brief descriptions
- **Continuation point**: where work should resume

## CRITICAL STEP COMPLETION NOTE

ONLY when all available context files have been read, load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All existing context files were read in full
- Missing files were noted but did not block execution
- Context is organized by category for status compilation
- No files were modified

### ❌ SYSTEM FAILURE:

- Skipping context files that exist
- Failing to note missing files
- Modifying any files during context load
- Proceeding before reading all available files

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
