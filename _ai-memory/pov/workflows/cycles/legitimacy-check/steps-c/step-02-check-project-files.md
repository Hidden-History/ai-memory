---
name: 'step-02-check-project-files'
description: 'Check project files for requirements that directly address the issue before applying classification criteria'
nextStepFile: './step-03-classify-issue.md'
---

# Step 2: Check Project Files

**Progress: Step 2 of 5** — Next: Apply Classification Criteria

## STEP GOAL:

Before applying classification criteria, check whether project files speak directly to this issue. The classification must be grounded in project file citations, not in Parzival's opinion.

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

- 🎯 Focus only on checking project files — no classification yet
- 🚫 FORBIDDEN to perform a general project file audit — check only for direct relevance to the specific issue
- 💬 Approach: Systematic file-by-file check with citations recorded
- 📋 Every finding must be recorded with specific file and section reference

## EXECUTION PROTOCOLS:

- 🎯 Check each project file category in order: PRD, architecture, project-context, story/epic
- 💾 Record findings with specific file and section citations before proceeding
- 📖 Load next step only after all four file categories are checked
- 🚫 FORBIDDEN to skip project file checks or classify without completing this step

## CONTEXT BOUNDARIES:

- Available context: The fully understood issue from step-01, project files (PRD.md, architecture.md, project-context.md, story/epic files)
- Focus: Project file citation only — do not apply classification criteria yet
- Limits: Only check for direct relevance to the specific issue. Do not perform a general project file audit.
- Dependencies: Understanding checklist from step-01 — all items must be answered

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Check PRD.md

- Does a requirement directly address this behavior?
- Does this issue violate an acceptance criterion?
- Record finding or "no direct guidance"

---

### 2. Check architecture.md

- Does this violate an architectural decision?
- Does this contradict a documented pattern or constraint?
- Record finding or "no direct guidance"

---

### 3. Check project-context.md

- Does this violate a coding standard or naming convention?
- Does this contradict an implementation rule?
- Record finding or "no direct guidance"

---

### 4. Check Story/Epic File (if applicable)

- Does this violate a story's acceptance criteria?
- Was this behavior explicitly specified?
- Record finding or "no direct guidance"

---

### 5. Record All Citations

If a project file speaks directly to the issue, record the specific file and section. This citation will ground the classification in the next step.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all relevant project files have been checked and findings recorded, will you then read fully and follow: `{nextStepFile}` to begin applying classification criteria.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All four file categories checked in order
- Findings recorded with specific file and section citations
- Direct relevance to the specific issue identified where it exists

### ❌ SYSTEM FAILURE:

- Skipping project file checks
- Checking files out of order
- Not recording specific citations
- Classifying without completing this step

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
