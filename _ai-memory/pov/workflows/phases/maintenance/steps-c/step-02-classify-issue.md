---
name: 'step-02-classify-issue'
description: 'Classify whether the issue is a maintenance fix or a new feature requiring sprint planning'
nextStepFile: './step-03-analyst-diagnosis.md'
---

# Step 2: Classify -- Maintenance Fix or New Feature?

**Progress: Step 2 of 7** — Next: Analyst Diagnosis

## STEP GOAL:

Not everything that arrives as an "issue" is a maintenance fix. Classify to prevent Maintenance from becoming unplanned development. New features route to Planning.

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

- 🎯 Focus on classification decision — maintenance fix or new feature
- 🚫 FORBIDDEN to treat new features as maintenance fixes
- 💬 Approach: Apply decision tree honestly, document reasoning
- 📋 New features route to WF-PLANNING, not maintenance queue

## EXECUTION PROTOCOLS:

- 🎯 Apply classification decision tree against triage summary and PRD.md
- 💾 Record classification with reasoning before proceeding
- 📖 Load next step only if classified as maintenance fix
- 🚫 FORBIDDEN to proceed with maintenance steps if issue is a new feature

## CONTEXT BOUNDARIES:

- Available context: Triage summary from Step 1, PRD.md
- Focus: Classification decision — maintenance fix or new feature routing
- Limits: Classification determines routing only. Be honest about fix vs feature.
- Dependencies: Triage summary from Step 1

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Apply Classification Decision Tree

**Is this a bug -- system fails to do what it was designed to do?**
YES -> Maintenance fix

**Is this a performance regression from a known baseline?**
YES -> Maintenance fix

**Is this a security vulnerability in existing functionality?**
YES -> Maintenance fix (CRITICAL priority)

**Is this a request for new behavior not in the PRD?**
YES -> New feature -> route to WF-PLANNING

**Is this a significant enhancement that changes product scope?**
YES -> New feature -> route to WF-PLANNING

**Is this a minor UX improvement or small enhancement to existing behavior?**
-> Maintenance fix (LOW priority)

**Is this tech debt that has become blocking?**
-> Maintenance fix (priority based on impact)

---

### 2. Handle New Feature Classification

If classified as new feature:
- Inform user: "This request introduces new behavior not in the current PRD. It will be treated as a new feature rather than a maintenance fix."
- Create a story for it in the backlog
- Route to WF-PLANNING when appropriate
- Continue with maintenance queue

**IF NEW FEATURE:** Do not continue to step-03. Route appropriately and process next maintenance issue.

---

### 3. Confirm Maintenance Fix Classification

Record the classification with reasoning. Proceed to diagnosis or fix.

## CRITICAL STEP COMPLETION NOTE

If classified as new feature: route to WF-PLANNING and stop this chain.
If classified as maintenance fix: load and read fully `{nextStepFile}`

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Decision tree applied honestly
- New features correctly identified and routed
- Maintenance scope stays tight
- Classification reasoning documented

### ❌ SYSTEM FAILURE:

- Treating new features as maintenance fixes
- Expanding maintenance scope without user approval
- Not routing new features to Planning

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
