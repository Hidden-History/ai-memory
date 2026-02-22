---
description: 'Create a 3-tier agent team prompt using the V3 hierarchical template'
argument-hint: '<description of the work to parallelize>'
allowed-tools: Read, Grep, Glob, AskUserQuestion
---

# Agent Team Prompt Builder (3-Tier Hierarchical)

Build a copy-pasteable 3-tier agent team prompt following the V3 template.

## Input
Work description: $ARGUMENTS

## Step 1: Load the Template

Read and internalize the full template:
- `oversight/prompts/AGENT_TEAM_PROMPT_TEMPLATE_V3.md` -- the authoritative 3-tier template

**Mental model reminder**: Parzival = General Contractor. Managers = Foremen. Workers = Crew.

## Step 2: Validate Tier Selection

Before proceeding with 3-tier, confirm the work actually needs it.
Run through the Quick Decision Flow (template Section 1):

```
Single task? -----> Subagent (Task tool) -- STOP, don't use this command
2-6 parallel tasks, single review? -----> 2-Tier (use v2.0 template) -- STOP, recommend v2.0
3+ domains, multi-task per domain, domain-level review? -----> Continue with 3-Tier
```

If 3-tier is NOT justified, tell the user why and recommend the simpler approach. Do NOT force hierarchy for hierarchy's sake.

## Step 3: Pre-Flight Checklist (Template Section 2)

Read all project context files listed in Section 2.1 that exist. Check each one off.

Then run the parallelizability check (Section 2.2):
- Can work split into 2+ domains with different file sets?
- Each domain has 2+ tasks?
- No single file needs modification by workers in different domains?

Then run the manager decomposition check (Section 2.3):
- Each domain has 2+ worker sessions?
- Domain boundaries are clear?
- 2-6 managers total?

**If any check fails, STOP and present the issue to the user with options to restructure.**

## Step 4: Gather Work Details

If work description was provided in $ARGUMENTS, analyze it. Otherwise, ask the user:

Present what you understand about the work, then ask:

1. **What are the independent domains?** (e.g., "database layer", "API endpoints", "frontend components")
2. **What tasks exist within each domain?** (e.g., "create schema, write migrations, seed data")
3. **Are there dependencies between domains?** (determines coordination pattern)
4. **Which BMAD agents or roles should do each task?** (or Parzival recommends based on the work)

Use the AskUserQuestion tool if clarification is needed. Do NOT guess at domain boundaries without reading the codebase.

## Step 5: Design the Team Structure

Based on the work details, fill in:

### 5a: Coordination Pattern Selection
Choose from template Section 3.3:
- Parallel Independent
- Parallel with Synthesis
- Plan-then-Execute
- Contract-First Build (triggers Sections 4.5, 4.6, 7.4)

### 5b: Manager Roster (Template Section 3.2)
For each manager: domain, responsibility, worker roles, file set, model.

### 5c: Worker Roster Per Manager (Template Section 3.6)
For each manager's workers: BMAD agent role, task, file set.

### 5d: File Ownership Map (Template Sections 4.1, 4.2)
- Manager-level: ZERO cross-manager overlap
- Worker-level: ZERO cross-worker overlap within each manager

**This is the single most important section. Verify ZERO overlap before proceeding.**

### 5e: Cross-Cutting Concerns (Template Section 4.5)
If applicable, assign each concern to one manager.

### 5f: Contract Chain (Template Section 4.6)
If Contract-First Build selected, map producer -> contract -> consumer chain.

## Step 6: Write Context Blocks

For EACH manager, write all 10 elements (template Section 5.1):
1. ROLE (workflow manager, NOT implementer)
2. OBJECTIVE (specific, measurable)
3. SCOPE (file boundaries)
4. WORKER ROSTER (each worker's complete 8-element prompt)
5. REVIEW PROTOCOL (spawn review agent, 3-cycle cap, escalation)
6. TASK CHECKLIST (ordered, each maps to a worker session)
7. QUALITY GATES (domain-specific)
8. CONSTRAINTS (no implementation, no skip review, hub-and-spoke)
9. CONTEXT FOR WORKERS (shared background)
10. REPORTING (summary format for lead)

For EACH worker within each manager, write all 8 elements (template Section 5.2):
1. ROLE
2. OBJECTIVE
3. SCOPE (file boundaries)
4. CONSTRAINTS
5. BACKGROUND
6. DELIVERABLE
7. COORDINATION
8. SELF-VALIDATION (domain-specific checks)

### Context Quality Gate (Template Section 5.3)
Verify for each manager: Could a fresh agent with ZERO prior context orchestrate this domain?
Verify for each worker: Could a fresh agent with ZERO prior context complete this task?

## Step 7: Assemble the Prompt

Follow the 2-stage assembly (template Section 7):
- Stage 1: Outer prompt with team objective, manager roster, delegate mode, lead instructions
- Stage 2: Each manager's context block embeds worker prompts

Use the template from Section 7.3 as the structure. If Contract-First Build, add Section 7.4 addendum.

**The result must be fully copy-pasteable. No [placeholder] or TBD values.**

## Step 8: Pre-Delivery Review

Run through EVERY item in the pre-delivery checklist (template Section 8).
This includes the new item: "Each worker's self-validation checks are domain-specific."

**If ANY item is unchecked, fix it before presenting.**

## Step 9: Present to User

Format:

```
## Agent Team Prompt Ready

**Structure**: [N] managers, [M] total workers
**Coordination Pattern**: [pattern]
**Delegate Mode**: Recommended (Shift+Tab after team starts)

### Team Overview

| Manager | Domain | Workers | Key Deliverable |
|---------|--------|---------|-----------------|
| 1 | [domain] | [count] | [deliverable] |
| 2 | [domain] | [count] | [deliverable] |

### File Ownership Summary
[Brief summary of who owns what -- verified ZERO overlap]

### The Prompt
[Copy-pasteable prompt here -- complete, no placeholders]

### After the Team Finishes
[Post-team verification plan from Section 10 -- what Parzival will check]

---
**Instructions**: Copy the prompt above and paste it into a new Claude Code session. After the team starts, press Shift+Tab to enable delegate mode. Parzival will verify the output when the team completes.
```

## Important

- Parzival RECOMMENDS the team structure, user APPROVES before execution
- Parzival provides the prompt, user PASTES it into a new session
- Parzival NEVER executes the team directly
- All context blocks must be self-contained -- agents have NO conversation history
- If the work doesn't justify 3-tier, say so and recommend the simpler approach
- Always include the post-team verification plan so the user knows what happens after
