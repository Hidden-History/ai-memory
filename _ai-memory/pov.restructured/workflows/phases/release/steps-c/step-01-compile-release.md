---
name: 'step-01-compile-release'
description: 'Compile the complete picture of what is changing in this release'
nextStepFile: './step-02-create-changelog.md'
---

# Step 1: Compile What Is Being Released

**Progress: Step 1 of 7** — Next: SM Creates Release Notes and Changelog

## STEP GOAL:

Before any release artifact is created, compile the complete picture of what is changing. Read all sources and produce a comprehensive release summary.

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

- 🎯 Focus on reading and compiling from actual story files, not memory
- 🚫 FORBIDDEN to compile release summary from memory or estimates
- 💬 Approach: Read every source document before producing the summary
- 📋 PRD coverage must be documented — requirements fulfilled and remaining

## EXECUTION PROTOCOLS:

- 🎯 Read all story files, integration findings, PRD, and architecture before compiling
- 💾 Record complete release summary with all required sections
- 📖 Load next step only after release summary is complete
- 🚫 FORBIDDEN to create release artifacts without a complete release summary

## CONTEXT BOUNDARIES:

- Available context: sprint-status.yaml, story files, integration findings, PRD.md, architecture.md
- Focus: Compilation only — do not create release artifacts yet
- Limits: Only compile. Do not create artifacts yet.
- Dependencies: Sprint completion confirmation and all completed story files

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Verify Sprint Completion

From sprint-status.yaml:
- All stories confirmed complete
- No stories in IN-PROGRESS or IN-REVIEW state

---

### 2. Read All Completed Story Files

For each story:
- What feature/behavior does it implement?
- What files were created or modified?
- Any implementation decisions that affect behavior?

---

### 3. Read Integration Findings

From WF-INTEGRATION:
- Pre-existing issues fixed during integration
- Architectural improvements made
- Notable behavior changes from test results

---

### 4. Read PRD for Coverage

- Which PRD requirements are fulfilled by this release?
- Which requirements remain for future releases?

---

### 5. Read Architecture Deployment Section

- Deployment process for this stack
- Environment variables or config changes needed
- Database migrations required
- Infrastructure changes required

---

### 6. Produce Release Summary

Compile:
- Features being released (each with one-line description)
- Changes to existing behavior
- Files changed (created count, modified count)
- Database changes (migrations, schema changes, data migrations)
- Configuration changes (new env vars, changed config, infrastructure)
- PRD coverage (requirements fulfilled, requirements remaining)

## CRITICAL STEP COMPLETION NOTE

ONLY when release summary is compiled, load and read fully `{nextStepFile}`

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All stories read (not summarized from memory)
- Changes to existing behavior explicitly identified
- Database and configuration changes captured
- PRD coverage documented

### ❌ SYSTEM FAILURE:

- Compiling from memory instead of reading story files
- Missing behavior changes to existing features
- Not identifying database migrations
- Not checking PRD coverage

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
