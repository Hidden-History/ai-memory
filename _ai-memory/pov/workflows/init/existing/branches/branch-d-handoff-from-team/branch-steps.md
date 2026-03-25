---
name: 'branch-d-handoff-from-team'
description: 'Onboarding steps for a project handed off from another team or system. Trust nothing without verification.'
---

# Branch D: Team Handoff

## BRANCH GOAL:
Build a complete, verified understanding of the project from scratch. Trust nothing without verification. Every claim in documentation must be verified against the actual code.

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Read All Documentation with Skepticism
- Read everything but verify everything
- Note every claim in documentation that needs verification
- Do not use any documented decision without confirming it reflects reality in the code

---

### 2. Run Deep Analyst Audit
Activate Analyst via {workflows_path}/cycles/agent-dispatch/workflow.md for a deeper audit beyond the standard Phase 2 audit. Additional areas for handoff:
- Are there undocumented architectural decisions visible in code?
- Are there patterns the documentation does not explain?
- Are there TODO/FIXME/HACK comments that reveal known issues?
- Is there dead code or experimental branches that need clarification?
- Are there environment-specific configurations that need documenting?

---

### 3. Identify Knowledge Gaps
Compile what Parzival needs to know that no file explains:
- Decisions made that have no documented rationale
- Parts of the codebase with no tests or documentation
- Patterns or conventions that are implicit rather than explicit

---

### 4. Prepare Knowledge Gap Questions for User
Group gaps by priority:

**BLOCKING (need answers before any work begins):**
1. [Question] -- Context: [why this matters]
2. [Question] -- Context: [why this matters]

**IMPORTANT (need answers soon):**
3. [Question]

**INFORMATIONAL (can be addressed as we go):**
4. [Question]

Present to user and wait for answers to blocking questions before proceeding.

---

### 5. Document All Answers in decisions.md
Every answer from the user becomes a documented decision:
- Include rationale even if brief
- This prevents the same questions being asked again

---

### 6. Verify Project Management Setup
- Check _ai-memory/ exists and is configured correctly
- Verify workflow files are accessible
- Note any setup needed

---

### 7. Determine Exit Route
On knowledge gaps resolved and state verified:
- If PRD and architecture both verified and sprint was in progress: exit route is WF-EXECUTION (pick up active task)
- If PRD and architecture both verified but no active sprint: exit route is WF-PLANNING
- If PRD exists but architecture is missing or invalid: exit route is WF-ARCHITECTURE
- If PRD is missing or requirements are incomplete: exit route is WF-DISCOVERY
- Document routing decision in decisions.md

Record the confirmed exit route for use in step-06 approval package.

## BRANCH COMPLETION
When all branch steps are complete, return to the common path: step-04-establish-baseline.md

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All documentation verified against actual code (not trusted blindly)
- Knowledge gaps identified, blocking ones resolved and documented in decisions.md
- Answers from user documented in decisions.md for future reference
- Exit route is clearly determined and recorded

### ❌ SYSTEM FAILURE:

- Trusting inherited documentation without verifying claims against the actual code
- Proceeding with unresolved blocking knowledge gaps
- Proceeding without confirming findings with user

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
