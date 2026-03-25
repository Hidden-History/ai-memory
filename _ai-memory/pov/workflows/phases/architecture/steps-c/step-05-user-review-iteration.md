---
name: 'step-05-user-review-iteration'
description: 'Present architecture to user for review and iterate until satisfied'
nextStepFile: './step-06-pm-creates-epics-stories.md'
---

# Step 5: User Review and Iteration

**Progress: Step 5 of 9** — Next: PM Creates Epics and Stories

## STEP GOAL:

Present the reviewed architecture to the user for feedback. Iterate until the user has no more changes. Architecture changes cascade -- assess impact on other sections for each change.

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

- 🎯 Focus on presenting architecture clearly and processing every piece of user feedback
- 🚫 FORBIDDEN to present updated architecture without re-running Parzival review first
- 💬 Approach: Present-feedback-correct cycle until user explicitly confirms satisfaction
- 📋 Assess cascade impact for every change — architecture changes are not isolated

## EXECUTION PROTOCOLS:

- 🎯 Present architecture with cascade-change warning before soliciting feedback
- 💾 Batch all corrections into a single instruction per iteration round
- 📖 Load next step only after user explicitly confirms no more changes
- 🚫 FORBIDDEN to proceed without user explicitly confirming satisfaction

## CONTEXT BOUNDARIES:

- Available context: Reviewed architecture.md, PRD.md
- Focus: User review and iteration — present, gather feedback, correct, repeat
- Limits: User feedback drives changes. Architecture changes cascade -- a database change affects data models, API design, and possibly infrastructure.
- Dependencies: Step 4 complete — Parzival has reviewed and architecture passes all checks

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Present Architecture for User Review

Present key decisions to review:
- Stack: [language + framework + database]
- API design: [approach]
- Infrastructure: [hosting + deployment approach]
- Key trade-offs made

Ask user to focus on:
1. Do the technology choices match expectations and constraints?
2. Are there any architectural decisions you disagree with?
3. Are there constraints missed that affect these choices?
4. Does the infrastructure approach fit requirements?
5. Any security or compliance concerns not addressed?

Note: "This document becomes the technical law of the project -- changes after stories are written will cause rework."

---

### 2. Wait for User Feedback

Halt and wait for the user to respond with feedback before proceeding.

---

### 3. Process User Feedback

For each change:
- Understand the feedback specifically
- Confirm interpretation before acting
- Assess impact on other sections (architecture changes cascade)
- Batch all corrections into one instruction

---

### 4. Send Corrections to Architect

Dispatch complete correction list to Architect via {workflows_path}/cycles/agent-dispatch/workflow.md.

---

### 5. Re-Review After Updates

Parzival re-reviews against the same checklists from Step 4. Only then present updated version to user.

---

### 6. Repeat Until Satisfied

Continue the present-feedback-correct cycle until user has no more changes.

## CRITICAL STEP COMPLETION NOTE

ONLY when the user indicates no more changes, load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Architecture presented with cascading-change warning
- Every piece of feedback addressed
- Impact assessment performed for each change
- Corrections batched and re-reviewed
- User explicitly confirmed satisfaction

### ❌ SYSTEM FAILURE:

- Not assessing cascade impact of changes
- Presenting updated architecture without re-review
- Dismissing user feedback

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
