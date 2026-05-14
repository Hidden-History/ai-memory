---
name: 'step-05-escalate-to-user'
description: 'Escalate to user when all three research layers fail to produce a verified answer'
nextStepFile: './step-06-document-answer.md'
---

# Step 5: Escalation -- User Decision Required

**Progress: Step 5 of 6** — Next: Document the Answer

## STEP GOAL:

When all three layers fail to produce a verified answer, escalate to the user. This is not a failure -- it means a genuine decision needs to be made and documented. Present full context, options with trade-offs, and Parzival's recommendation.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The research question, all three layer results, options identified during research
- Focus: User decision escalation only — present options, not implementation
- Limits: All three layers must be genuinely exhausted before escalating. Do not escalate prematurely.
- Dependencies: Research question from Step 1, Layer 1 results from Step 2, Layer 2 results from Step 3, Layer 3 results from Step 4

- Confirm all three layers are genuinely exhausted before escalating
**Behavioral Constraints:**
- FORBIDDEN to escalate prematurely or present vague options without specific trade-offs
- Approach: Structured escalation with complete research trail and clear recommendation
- Always include Parzival's recommendation or explicitly explain why one cannot be made

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Verify Escalation is Warranted

Confirm that all three layers have been genuinely exhausted or that this is a genuine decision that only the user can make.

---

### 2. Build Escalation Message

Present to user using this format:

**RESEARCH ESCALATION -- Decision Required**

**QUESTION:**
[The precise question that needs an answer]

**WHY THIS MATTERS:**
[What depends on this decision -- current task, future work, architecture]

**WHAT WAS RESEARCHED:**

Layer 1 -- Project files:
  Checked: [files checked]
  Found: [what was found or "No direct guidance"]

Layer 2 -- Official documentation:
  Checked: [sources checked, versions]
  Found: [what was found or "Not applicable to this project's context"]

Layer 3 -- Codebase research (Analyst):
  Checked: [areas of codebase researched]
  Found: [what was found or "No existing pattern found"]

**OPTIONS:**
  Option A: [specific approach]
    Pros: [concrete benefits for this project]
    Cons: [concrete trade-offs for this project]

  Option B: [specific approach]
    Pros: [concrete benefits for this project]
    Cons: [concrete trade-offs for this project]

  [Add Option C only if genuinely needed -- avoid false choices]

**PARZIVAL'S RECOMMENDATION:**
[Specific recommendation with reasoning -- or state if no recommendation can be made without more information]

**WHAT IS NEEDED FROM YOU:**
[Specific decision or information -- be precise]

**AFTER YOUR DECISION:**
This will be documented in [architecture.md / project-context.md] so this question does not need to be researched again.

---

### 3. Wait for User Decision

Halt and wait for the user's response. Do not proceed on assumptions.

---

### 4. Process User Decision

When the user provides their decision:
- Record the decision and reasoning
- Proceed to `{nextStepFile}` to document the answer in project files

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the user has provided a decision and it has been recorded, will you then read fully and follow: `{nextStepFile}` to begin documenting the answer.
