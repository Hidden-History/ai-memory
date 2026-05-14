---
name: 'step-01-read-routing-files'
description: 'Read routing-critical project files to determine onboarding branch — defer deep audit to Analyst in Step 2'
nextStepFile: './step-02-run-analyst-audit.md'
---

# Step 1: Read Routing-Critical Files

**Progress: Step 1 of 6** — Next: Run Analyst Audit

## STEP GOAL:

Read ONLY the files needed to determine project state and routing branch. The Analyst agent in Step 2 performs the deep audit — Parzival should NOT read the full codebase here. Context budget matters.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Routing-critical files only (project-status.md, sprint-status.yaml, README.md)
- Focus: Determine branch signal for Step 3 routing
- Limits: Do NOT read PRD, architecture, epics, stories, or source code. The Analyst agent in Step 2 does the deep audit.
- Dependencies: None — this is the first step of the init-existing workflow

- Focus on reading ROUTING files only — deep audit is the Analyst's job in Step 2
**Behavioral Constraints:**
- FORBIDDEN to activate any agents or modify any files during this step
- FORBIDDEN to read the full codebase, all docs, or all config files — that wastes context
- Approach: Targeted reads of routing-critical files, existence checks for the rest
- Treat all documentation as "possibly outdated until verified by Analyst"

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Read Routing-Critical Files (3 files max)

Read these files IN FULL if they exist:

- **project-status.md** — Current phase, active task, baseline status, last updated date
- **sprint-status.yaml** — Sprint state, story assignments (if exists, indicates active development)
- **README.md** — High-level overview, stack evidence, project purpose

---

### 2. Quick Existence Checks (DO NOT read content)

Check whether these files/directories exist. Note present or absent — do NOT read their content:

- PRD.md
- architecture.md
- project-context.md
- epics/ or stories/ directories
- goals.md
- docs/ directory
- Package files (package.json, requirements.txt, pyproject.toml)

---

### 3. Record Routing Findings

For the 3 routing files read:
- What it contains (brief summary)
- When it was last updated (if datestamped)
- Whether it appears current or stale

For the existence checks:
- Present or absent — this determines branch routing in Step 3

---

### 4. Determine Initial Branch Signal

Based on findings, note the likely branch (confirmed in Step 3):

- **Branch A signal**: sprint-status.yaml exists with incomplete stories → Active mid-sprint
- **Branch B signal**: Code/README exists but PRD, architecture, or project-context missing → Legacy/undocumented
- **Branch C signal**: project-status.md shows stale last_updated, work incomplete → Paused/restarting
- **Branch D signal**: Documentation exists but Parzival has no prior context → Handoff from team

---

### 5. Apply Reading Rules

- NEVER assume a file is accurate because it exists
- NEVER read the full codebase — that is the Analyst's job in Step 2
- NEVER load files beyond routing-critical — context budget matters
- ALWAYS treat documentation as "possibly outdated until verified by Analyst"
- ALWAYS note obvious contradictions between the routing files

## CRITICAL STEP COMPLETION NOTE

ONLY when routing files have been read and branch signal identified, load and read fully {nextStepFile}
