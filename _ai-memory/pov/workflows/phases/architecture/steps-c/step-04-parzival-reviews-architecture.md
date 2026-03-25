---
name: 'step-04-parzival-reviews-architecture'
description: 'Parzival performs thorough review of architecture.md before user sees it'
nextStepFile: './step-05-user-review-iteration.md'
---

# Step 4: Parzival Reviews Architecture

**Progress: Step 4 of 9** — Next: User Review and Iteration

## STEP GOAL:

Before the user sees architecture.md, Parzival reviews it against completeness, PRD alignment, internal consistency, appropriateness, and implementability checklists. Return to Architect for corrections if needed.

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

- 🎯 Focus on running all five review checklists before presenting architecture to user
- 🚫 FORBIDDEN to present architecture to user with known issues
- 💬 Approach: Batch all corrections into a single instruction — no piecemeal fixes
- 📋 Re-run the full review from scratch after every round of corrections

## EXECUTION PROTOCOLS:

- 🎯 Run all five checklists completely and independently
- 💾 Compile all issues into a single batched correction instruction per review round
- 📖 Load next step only after architecture passes all five checklists
- 🚫 FORBIDDEN to skip any checklist or send corrections piecemeal

## CONTEXT BOUNDARIES:

- Available context: architecture.md draft, PRD.md, goals.md, project-context.md
- Focus: Parzival review only — user has not seen architecture yet
- Limits: Parzival reviews only. User has not seen architecture yet. Batch corrections.
- Dependencies: Steps 2 and 3 complete — architecture draft and UX artifacts (if applicable) received

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Run Completeness Check

- All 8 required sections are present
- Every major tech decision is documented
- Every decision has rationale
- Trade-offs are acknowledged

---

### 2. Run PRD Alignment Check

- Architecture satisfies all Must Have functional requirements
- Architecture satisfies all non-functional requirements (performance, scale)
- Architecture satisfies all integration requirements
- Architecture satisfies all security requirements
- Architecture respects all stated constraints

---

### 3. Run Internal Consistency Check

- No contradictions between sections
- Component interactions are coherent
- Data models support the described user flows
- Infrastructure supports the stated scale requirements

---

### 4. Run Appropriateness Check

- Architecture fits the project scale (not over-engineered, not under-built)
- Tech choices are appropriate for the team context
- No gold-plating -- complexity is justified by requirements
- Existing tech (if any) is correctly reflected

---

### 5. Run Implementability Check

- DEV agents can implement from this document without guessing
- Component boundaries are clear enough to assign to stories
- No decisions deferred that would block implementation

---

### 6. Handle Issues Found

**IF architecture has issues:**
Compile all issues into a single correction instruction for the Architect:

For each issue:
- Section: [section]
- Problem: [what is missing, contradictory, or insufficient]
- Required: [what it needs to say or include]
- PRD ref: [which PRD requirement this must satisfy, if applicable]

Dispatch to Architect via {workflows_path}/cycles/agent-dispatch/workflow.md.
After corrections, re-run the full review. Repeat until all checks pass.

**IF architecture passes all checks:** Proceed to user review.

## CRITICAL STEP COMPLETION NOTE

ONLY when architecture passes all review checks, load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All five checklists run completely
- Issues batched into single correction instruction
- Corrected architecture re-reviewed from scratch
- Architecture passes all checks before user sees it

### ❌ SYSTEM FAILURE:

- Presenting architecture to user with known issues
- Sending corrections piecemeal
- Not re-reviewing after corrections
- Skipping any checklist

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
