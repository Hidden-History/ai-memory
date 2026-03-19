---
name: 'step-06-prepare-summary'
description: 'Compile the story completion summary from review cycle records for user presentation'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: Prepare User Summary

**Progress: Step 6 of 7** — Next: Approval Gate

## STEP GOAL:

After verification passes, compile the story completion summary. This summarizes what was built, how the review cycle went, and confirms all acceptance criteria are satisfied.

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

- 🎯 Focus only on compiling the accurate story completion summary
- 🚫 FORBIDDEN to copy DEV output directly into the summary
- 💬 Approach: Compile in Parzival's words with all required fields accurate
- 📋 Verify summary accuracy against actual review cycle records before proceeding

## EXECUTION PROTOCOLS:

- 🎯 Compile the story completion summary from review cycle records
- 💾 Confirm all acceptance criteria are listed and marked satisfied
- 📖 Load next step only after summary is complete and verified for accuracy
- 🚫 FORBIDDEN to proceed with summary containing copied DEV output or missing criteria

## CONTEXT BOUNDARIES:

- Available context: Review cycle records, implementation details, acceptance criteria
- Focus: Summary compilation only — do not present or request approval yet
- Limits: Summary is in Parzival's words, not copied from DEV output.
- Dependencies: All four-source verification passed from Step 5

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Compile Story Completion Summary

**Story:** [Story ID] -- [Title]
**Sprint:** [N]

**Implementation:**
- What was built (concrete description)
- Files created: [list]
- Files modified: [list]
- Implementation approach (key decisions made, if any)

**Review cycle:**
- Total passes: [N]
- Total issues found: [N]
- Legitimate issues fixed: [N]
- Non-issues documented: [N]
- Pre-existing issues fixed: [N]
- Final status: Zero legitimate issues confirmed

**Acceptance criteria status:**
- [Criterion 1]: Satisfied
- [Criterion 2]: Satisfied
- [Criterion N]: Satisfied
(All criteria must show satisfied)

**Notable findings:**
- Significant pre-existing issues fixed
- Implementation decisions affecting architecture.md
- decisions.md updates made

---

### 2. Verify Summary Accuracy

- Does the summary accurately reflect what happened?
- Are all acceptance criteria listed and confirmed?
- Is the review cycle data accurate?
- Are notable findings genuinely notable (not noise)?

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the summary is complete and verified, will you then read fully and follow: `{nextStepFile}` to begin the approval gate.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Summary is in Parzival's words (not DEV output copy)
- All acceptance criteria confirmed satisfied
- Review cycle metrics are accurate
- Notable findings are genuinely notable

### ❌ SYSTEM FAILURE:

- Copying DEV output into summary
- Missing acceptance criteria in status list
- Inaccurate review cycle metrics
- Including non-notable items as findings

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
