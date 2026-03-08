---
name: 'step-04-parzival-reviews-prd'
description: 'Parzival performs thorough review of the PRD draft before user sees it'
nextStepFile: './step-05-user-review-iteration.md'
---

# Step 4: Parzival Reviews PRD Draft

## STEP GOAL
Before the user sees the PRD, Parzival reviews it thoroughly against completeness, quality, accuracy, and alignment checklists. Return to PM for corrections if needed.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: PRD.md draft from PM, goals.md, Analyst research, track selection
- Limits: Parzival reviews only. User has not seen the PRD yet. Do not send corrections piecemeal -- batch them.

## MANDATORY SEQUENCE

### 1. Run Completeness Check
- All required sections are present
- Every feature has acceptance criteria
- Out of scope is explicitly stated
- Success metrics are measurable
- Open questions are listed

### 2. Run Quality Check
- Requirements are specific -- no "the system should be fast"
- Requirements are verifiable -- can be confirmed done or not done
- Requirements are implementation-free -- WHAT, not HOW
- No contradictions between requirements
- No scope creep -- features that were not in goals.md or research

### 3. Run Accuracy Check
- All requirements trace back to goals.md or user-confirmed input
- No invented requirements
- Constraints from goals.md are reflected
- Open items from goals.md are addressed or listed as open

### 4. Run Alignment Check
- PRD matches the selected track
- Scope is appropriate for the stated project scale
- Priorities are realistic given stated constraints

### 5. Handle Issues Found

**IF PRD has issues:**
Compile all issues into a single correction instruction for the PM:

For each issue:
- Section: [section name]
- Problem: [what is wrong]
- Required: [what it should be]

Dispatch correction instruction to PM via {workflows_path}/cycles/agent-dispatch/workflow.md.

After PM returns corrected PRD, re-run the full review checklist. Repeat until all checks pass.

**IF PRD passes all checks:**
Proceed to user review.

## CRITICAL STEP COMPLETION NOTE
ONLY when the PRD passes all review checks, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All four checklists run completely
- Issues batched into a single correction instruction (not piecemeal)
- Corrected PRD re-reviewed from scratch
- PRD passes all checks before user sees it

### FAILURE:
- Presenting PRD to user with known issues
- Sending corrections piecemeal instead of batched
- Not re-reviewing after corrections
- Skipping any of the four checklists
