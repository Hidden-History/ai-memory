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

### 1. Load Oversight Context (Session Loader — capped)

Run the session loader, oversight scope — a single consolidated, capped load that replaces the scattered per-file oversight reads:

```bash
python3 {skills_path}/aim-parzival-loader/session_loader.py "{project-root}" --scope oversight
```

It emits, in the approved A2 order: `SESSION_WORK_INDEX.md` (full — already capped), the tracking files' active sections only (`task-tracker.md`, `blockers-log.md`, `risk-register.md` — Resolved / Closed / Previous-Sprint / archive sections dropped), and the `## Quick Stats` table only of `bugs/INDEX.md` and `tech-debt/INDEX.md`. Missing files are noted and do not block. Full files remain on disk at full size.

---

### 2. Identify Most Recent Handoff (Deferred Read)

[HANDOFF-DEFERRED: awaiting Qdrant L1 result in Step 1b]

Do NOT read the handoff file at this step. Qdrant L1 may already contain the most recent handoff — reading the file here would duplicate work and consume ~4,000 tokens unnecessarily.

**Filename identification only**: List `{oversight_path}/session-logs/SESSION_HANDOFF_*.md` filenames and identify the most recent one by filename date. Record the date for the staleness check in Step 1b. No file content is read here.

If no handoff files exist, note this as a first-session scenario and proceed. Step 1b will handle the Qdrant gate.

---

### 3. Oversight Tracking + Bug/TD Summaries

The task tracker (active sections), blockers log (Active Blockers + Severity Definitions), risk register (Active Risks + Severity Matrix), and the `## Quick Stats` tables of `bugs/INDEX.md` + `tech-debt/INDEX.md` are all loaded by the session loader in Section 1 (oversight scope). No additional reads here.

🚫 FORBIDDEN: do NOT read individual `BUG-*.md` or `TECH-DEBT-*.md` record files at startup — there can be hundreds. The compact INDEX `## Quick Stats` table (emitted by the loader) is the only startup-read surface for bug/TD state. If an INDEX is missing, the loader notes it; suggest `/aim-tracking-freshness --write` and proceed. A missing INDEX does not block.

Extract from the loaded oversight block: current sprint + task statuses, active blockers + severities, high/critical risks, open/closed bug + tech-debt totals, and each INDEX's `**Last Updated**` date (for the staleness check in Step 2).

---

### 4. Compile Loaded Context

Organize the loaded information into these categories:
- **Last session**: date, topic, outcome
- **Current task**: ID, title, status
- **Blockers**: count and brief descriptions
- **Risks**: count of high/critical, brief descriptions
- **Continuation point**: where work should resume

## CRITICAL STEP COMPLETION NOTE

ONLY when all available context files have been read, load and read fully {nextStepFile}
