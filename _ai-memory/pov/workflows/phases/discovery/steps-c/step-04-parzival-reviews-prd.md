---
name: 'step-04-parzival-reviews-prd'
description: 'Parzival performs thorough review of the PRD draft before user sees it'
nextStepFile: './step-05-user-review-iteration.md'
---

# Step 4: Parzival Reviews PRD Draft

**Progress: Step 4 of 7** — Next: User Review and Iteration

## STEP GOAL:

Before the user sees the PRD, Parzival reviews it thoroughly against completeness, quality, accuracy, and alignment checklists. Return to PM for corrections if needed.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: PRD.md draft from PM, goals.md, Analyst research, track selection
- Focus: Parzival review only — user has not seen the PRD yet
- Limits: Parzival reviews only. User has not seen the PRD yet. Do not send corrections piecemeal -- batch them.
- Dependencies: PRD.md draft delivered by PM agent in Step 3

- Focus on running all four review checklists before user sees the PRD
**Behavioral Constraints:**
- FORBIDDEN to send corrections piecemeal — batch all issues into a single correction instruction
- Systematic checklist approach: completeness, quality, accuracy, alignment
- Re-review from scratch after every correction cycle

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Run Completeness Check

- All required sections are present
- Every feature has acceptance criteria
- Out of scope is explicitly stated
- Success metrics are measurable
- Open questions are listed

---

### 2. Run Quality Check

- Requirements are specific -- no "the system should be fast"
- Requirements are verifiable -- can be confirmed done or not done
- Requirements are implementation-free -- WHAT, not HOW
- No contradictions between requirements
- No scope creep -- features that were not in goals.md or research

---

### 3. Run Accuracy Check

- All requirements trace back to goals.md or user-confirmed input
- No invented requirements
- Constraints from goals.md are reflected
- Open items from goals.md are addressed or listed as open

---

### 4. Run Alignment Check

- PRD matches the selected track
- Scope is appropriate for the stated project scale
- Priorities are realistic given stated constraints

---

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
