---
name: 'step-06-verify-baseline'
description: 'Verify the complete project baseline before presenting to user for approval'
nextStepFile: './step-07-present-and-approve.md'
---

# Step 6: Verify Baseline Is Complete

## STEP GOAL
Before presenting to the user, verify that everything established in prior steps is in place, accurate, and consistent. Do not present an incomplete baseline.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All files created in Steps 3-5, user-confirmed information from Step 2
- Limits: Do not create new files here. Only verify what already exists. Fix any issues found before proceeding.

## MANDATORY SEQUENCE

### 1. Verify Installation
- _ai-memory/ directory structure is intact (verified in Step 3)
- Core configuration files are present and readable
- Workflow files are accessible

### 2. Verify Project Files
**project-status.md:**
- All required fields are present
- current_phase is set to "discovery"
- baseline_complete is set to false (will be set to true on approval)
- Track reflects confirmed selection
- key_files paths are accurate (or null for files not yet created)

**goals.md:**
- All sections populated from user input
- No generic placeholder content
- Constraints are specific and actionable
- Open questions are listed if any remain
- Tech stack decisions are accurately recorded (confirmed vs TBD)

**project-context.md:**
- Stub exists with clear TBD markers
- Known preferences section reflects any user-stated preferences
- No section is treated as confirmed

**decisions.md:**
- Exists with initialization decisions recorded
- Track selection decision is documented with reasoning

### 3. Verify Teams Session Structure
- Claude Code teams capability verified (from Step 5)
- Agent dispatch workflow is accessible
- Session naming convention is documented

### 4. Verify Information Accuracy
Cross-check across all files:
- All files reflect confirmed user information -- no assumptions
- Open items are clearly marked as TBD or deferred to Discovery
- No contradictions between files
- Track selection is consistent across all files

### 5. Handle Verification Failures
**IF ANY CHECK FAILS:**
- Fix the specific issue before proceeding
- Do not present an incomplete or inconsistent baseline to the user
- Re-verify the fixed item

### 6. Research Initial Best Practices

Once all verification checks pass, seed the project's knowledge base with best practices for the confirmed technology stack.

Run `/aim-best-practices-researcher` for each major technology in the confirmed stack (from goals.md "Tech Stack Decisions Made" section). For example:
- If the project uses React: research "React 2026 best practices"
- If the project uses Python + FastAPI: research "Python FastAPI best practices 2026"
- If the project uses Docker: research "Docker containerization best practices 2026"

**Why now**: Best practices must be in Qdrant BEFORE Discovery begins. When the PM agent creates the PRD and the Architect designs the system, they will receive these best practices via Tier 2 context injection — ensuring the project starts with current knowledge, not outdated patterns.

**Minimum**: Research at least the primary language/framework and the primary infrastructure pattern.

**If Qdrant is unavailable**: Note the gap. Best practices will be file-only (in `oversight/knowledge/best-practices/`). Flag this for the user — Qdrant storage is needed for agent injection.

## CRITICAL STEP COMPLETION NOTE
ONLY when all verification checks pass with zero failures AND initial best practices research is complete, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every verification item was individually checked
- All files are consistent with each other
- All content traces to user-confirmed input
- No assumptions are being carried forward
- Any issues found were fixed before proceeding

### FAILURE:
- Presenting baseline with known issues
- Skipping verification checks to save time
- Not cross-checking consistency between files
- Carrying assumptions into the next step
