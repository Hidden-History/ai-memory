---
name: 'step-06-review-and-present'
description: 'Run pre-delivery review, define acceptance criteria, build verification plan, and present the complete prompt to the user'
---

# Step 6: Review and Present

## STEP GOAL
Run the full pre-delivery review checklist, define acceptance criteria, build the post-team verification plan, then present the complete team prompt to the user with execution instructions.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Assembled prompt from Step 5, all design decisions from Steps 1-4
- Limits: Present only — Parzival NEVER executes the team. User pastes the prompt.

## MANDATORY SEQUENCE

### 1. Pre-Delivery Review Checklist

Verify EVERY item before presenting. Organize by category:

**Pre-flight:**
- [ ] All available project context files were read (Step 1)

**Structure:**
- [ ] Manager/teammate count is justified (each domain has 2+ tasks)
- [ ] Each manager has full standalone context (all 10 elements)
- [ ] Each manager's worker prompts are complete (all 8 elements per worker)
- [ ] Review protocol is explicit in each manager's prompt (3-cycle cap, escalation)

**Quality:**
- [ ] Each worker's self-validation checks are domain-specific (not generic "run tests")
- [ ] 3-cycle review cap is stated in each manager's constraints
- [ ] Quality gates are specific to each manager's domain

**Ownership:**
- [ ] Manager-to-manager file ownership has ZERO overlap
- [ ] Worker-to-worker file ownership has ZERO overlap within each manager
- [ ] Hub-and-spoke communication is enforced (no cross-manager or cross-worker communication)

**Sizing:**
- [ ] Tasks per manager: 3-6 range (embed max 4 prompts, batch remainder sequentially)
- [ ] Task checklists are ordered and complete for each manager

**Decisions:**
- [ ] Plan approval decision is justified and recorded
- [ ] Model is specified for all managers/teammates
- [ ] Delegate mode is recommended (3-tier) or decision recorded (2-tier)

**Completeness:**
- [ ] The prompt is copy-pasteable — no `[placeholder]` or `TBD` values remain
- [ ] Acceptance criteria exist for the overall team output (see section 2)
- [ ] Post-team verification plan is included (see section 3)
- [ ] Lead instructions include synthesis deliverable and shutdown protocol

**Conditional (if applicable):**
- [ ] Contract-First Build: contract chain mapped, spawn order staggered, relay protocol included
- [ ] Cross-cutting concerns: all identified concerns assigned to one owner
- [ ] Context token budgets approximately respected

**IF ANY ITEM IS UNCHECKED**: Fix it before presenting. Do not proceed with an incomplete prompt.

### 2. Define Acceptance Criteria

Define what "done" looks like for the overall team output:
- All manager/teammate domains passed their quality gates before reporting complete
- Review-fix-review cycle completed for every worker deliverable (max 3 cycles each)
- All deliverables integrate without conflicts
- Tests pass after combining all changes
- No regressions introduced
- Contract alignment verified — no interface mismatches (if Contract-First)
- Each worker's self-validation passed before reporting done
- Cross-domain integration verification passed (E2E, not just per-domain)
- Cross-cutting concerns verified (URL conventions, error shapes, etc. are consistent)

### 3. Build Post-Team Verification Plan

Define what Parzival will check after the team completes:

**3a. Worker Self-Validation (Tier 3)**:
- Each worker reported their validation results
- No worker reported done with failing checks
- Domain-specific validations are relevant

**3b. Manager Domain Verification (Tier 2)**:
- All workers in domain passed review with zero issues
- Total review cycles logged per worker
- No worker required unresolved escalation
- Domain-level integration works (if workers within domain interact)
- Quality gates all passed

**3c. Parzival Cross-Domain Verification (Tier 1)**:
- All domains reported clean
- Cross-domain integration points work
- E2E validation passed (system works end-to-end)
- No file conflicts between domains (`git status`)
- Contract alignment verified (if Contract-First)
- Cross-cutting concerns consistent across all domains

**3d. Pre-Integration Contract Diff (Contract-First only)**:
- Ask each producing domain: "What exact interfaces do you expose?"
- Ask each consuming domain: "What exact interfaces do you call?"
- Compare: URLs match, request bodies match, response shapes match
- Flag any mismatches before integration testing

**3e. Quality Verification**:
- Run project tests
- Check for file conflicts between domains
- All shared task list items marked complete
- Lead's synthesis is coherent and complete

**3f. Cleanup**:
- All worker sessions completed (managers handled this)
- All manager/teammate sessions shut down (lead sends shutdown requests)
- Team cleaned up (via lead, not directly)
- No orphaned sessions remain
- Results documented

**3g. User Decision**:
- Approve combined output?
- Request fixes on specific issues?
- Run additional review cycle?

### 4. Present to User

**For 3-tier teams:**
```
## Agent Team Prompt Ready

**Structure**: [N] managers, [M] total workers
**Coordination Pattern**: [pattern]
**Model**: [model selection]
**Plan Approval**: [Required/Not Required]
**Delegate Mode**: Recommended (Shift+Tab after team starts)

### Team Overview

| Manager | Domain | Workers | Key Deliverable |
|---------|--------|---------|-----------------|

### File Ownership Summary
[Brief summary of who owns what — verified ZERO overlap]

### The Prompt
[Complete copy-pasteable prompt — no placeholders]

### After the Team Finishes
[Post-team verification plan — what Parzival will check]

---
**Instructions**: Copy the prompt above and paste it into a new Claude Code session.
After the team starts, press Shift+Tab to enable delegate mode.
Parzival will verify the output when the team completes.
```

**For 2-tier teams:**
```
## Agent Team Prompt Ready

**Structure**: [N] teammates
**Coordination Pattern**: [pattern]
**Model**: [model selection]
**Plan Approval**: [Required/Not Required]
**Delegate Mode**: [Recommended/Not Needed]

### Team Overview

| Teammate | Role | File Set | Key Deliverable |
|----------|------|----------|-----------------|

### File Ownership Summary
[Brief summary — verified ZERO overlap]

### The Prompt
[Complete copy-pasteable prompt — no placeholders]

### After the Team Finishes
[Post-team verification plan]

---
**Instructions**: Copy the prompt above and paste it into a new Claude Code session.
Parzival will verify the output when the team completes.
```

### 5. Wait for User Action

After presenting:
- Do NOT execute the team prompt
- If the user requests changes, return to the appropriate step
- If the user approves, remind them to paste it into a new session
- Parzival's role resumes when the team completes and verification is needed

Post-team verification is handled by `{workflows_path}/session/verify/workflow.md`.

## CRITICAL STEP COMPLETION NOTE
This is a **terminal step**. The workflow is complete once the prompt is presented and the user has the copy-pasteable output.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Pre-delivery review passes ALL checks (zero unchecked items)
- Acceptance criteria are defined for overall team output
- Post-team verification plan covers all tiers
- Prompt is fully copy-pasteable with zero placeholders
- Presentation format matches the selected tier (3-tier or 2-tier)
- User receives clear execution instructions

### FAILURE:
- Presenting a prompt that fails any pre-delivery review item
- Not defining acceptance criteria
- Omitting the post-team verification plan
- Executing the team prompt instead of presenting it
- Using 3-tier presentation format for a 2-tier team
- Presenting a prompt with placeholders
