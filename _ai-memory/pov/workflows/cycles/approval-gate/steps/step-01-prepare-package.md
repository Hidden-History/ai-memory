---
name: 'step-01-prepare-package'
description: 'Assemble a complete, structured approval package before presenting anything to the user'
nextStepFile: './step-02-present-to-user.md'
---

# Step 1: Prepare the Approval Package

## STEP GOAL
Before presenting anything to the user, Parzival assembles a complete approval package. This is never improvised -- it is always structured. The package contains what was done, how it was verified, what was found, what requires a decision, and what comes next.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Review cycle summary, task output, phase status, all pass records, all classification records
- Limits: Write in Parzival's own words. Never copy agent output directly.

## MANDATORY SEQUENCE

### 1. Assemble Package Contents

**WHAT WAS DONE:**
Clear, plain-language description of what was completed. Written by Parzival -- not copied from agent output. No technical jargon unless the user is technical and it adds clarity.

**HOW IT WAS VERIFIED:**
How many review passes ran. How many issues were found and resolved. Confirmation that zero legitimate issues remain.

**WHAT WAS FOUND (if anything notable):**
Pre-existing issues discovered and fixed. Decisions made during implementation. Anything the user should be aware of even if it did not block completion.

**WHAT REQUIRES THE USER'S DECISION (if anything):**
Specific questions that need an answer. Options presented with trade-offs. Parzival's recommendation clearly stated.

**WHAT COMES NEXT:**
The recommended next step. Alternatives if the user wants to change direction. What Parzival will do once approved.

### 2. Run Package Quality Check
Before presenting, verify:
- Is this written in Parzival's words -- not copied from agent output?
- Is it complete -- nothing important left out?
- Is it accurate -- no unverified claims?
- Is it concise -- no unnecessary padding or repetition?
- Are decisions clearly separated from information?
- Is the recommended next step specific and actionable?
- Would a non-technical user understand this summary?

### 3. Determine Presentation Format
Based on the type of approval:
- **Task completion:** Use task approval format (see step-02)
- **Phase milestone:** Use phase milestone format (see step-02)
- **Decision point:** Use decision point format (see step-02)

## CRITICAL STEP COMPLETION NOTE
ONLY when the approval package is assembled and quality-checked, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Package contains all five sections
- Written in Parzival's own words
- Quality check passes all items
- Appropriate format identified

### FAILURE:
- Copying agent output instead of writing summary
- Missing sections in the package
- Including unverified claims
- Presenting without quality check
