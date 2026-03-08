---
name: 'step-05-escalate-to-user'
description: 'Escalate to user when all three research layers fail to produce a verified answer'
nextStepFile: './step-06-document-answer.md'
---

# Step 5: Escalation -- User Decision Required

## STEP GOAL
When all three layers fail to produce a verified answer, escalate to the user. This is not a failure -- it means a genuine decision needs to be made and documented. Present full context, options with trade-offs, and Parzival's recommendation.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The research question, all three layer results, options identified during research
- Limits: All three layers must be genuinely exhausted before escalating. Do not escalate prematurely.

## MANDATORY SEQUENCE

### 1. Verify Escalation is Warranted
Confirm that all three layers have been genuinely exhausted or that this is a genuine decision that only the user can make.

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

### 3. Wait for User Decision
Halt and wait for the user's response. Do not proceed on assumptions.

### 4. Process User Decision
When the user provides their decision:
- Record the decision and reasoning
- Proceed to {nextStepFile} to document the answer in project files

## CRITICAL STEP COMPLETION NOTE
ONLY when the user has provided a decision and it has been recorded, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Escalation includes complete research trail from all three layers
- Options are presented with concrete trade-offs specific to this project
- Parzival's recommendation is stated (or absence of recommendation is explained)
- User decision is recorded with reasoning
- Decision will be documented in project files

### FAILURE:
- Escalating before exhausting all three layers
- Presenting vague options without specific trade-offs
- Not including a recommendation
- Proceeding without user decision
- Not documenting the decision
