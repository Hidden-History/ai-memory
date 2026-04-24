---
name: 'step-01-prepare-package'
description: 'Assemble a complete, structured approval package before presenting anything to the user'
nextStepFile: './step-02-present-to-user.md'
---

# Step 1: Prepare the Approval Package

**Progress: Step 1 of 4** — Next: Present to User

## STEP GOAL:

Before presenting anything to the user, Parzival assembles a complete approval package. This is never improvised -- it is always structured. The package contains what was done, how it was verified, what was found, what requires a decision, and what comes next.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Review cycle summary, task output, phase status, all pass records, all classification records
- Focus: Package assembly only — do not begin presenting to user
- Limits: Write in Parzival's own words. Never copy agent output directly.
- Dependencies: Completed WF-REVIEW-CYCLE or WF-EXECUTION phase output

- Focus on assembling a complete approval package — do not begin presenting yet
**Behavioral Constraints:**
- FORBIDDEN to copy agent output directly — write in Parzival's own words
- Approach: Systematic assembly with quality check before advancing
- Package must contain all five sections before marking step complete

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Run Package Quality Check

Before presenting, verify:
- Is this written in Parzival's words -- not copied from agent output?
- Is it complete -- nothing important left out?
- Is it accurate -- no unverified claims?
- Is it concise -- no unnecessary padding or repetition?
- Are decisions clearly separated from information?
- Is the recommended next step specific and actionable?
- Would a non-technical user understand this summary?

---

### 3. Determine Presentation Format

Based on the type of approval:
- **Task completion:** Use task approval format (see step-02)
- **Phase milestone:** Use phase milestone format (see step-02)
- **Decision point:** Use decision point format (see step-02)

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the approval package is assembled and quality-checked, load and read fully `{nextStepFile}`
