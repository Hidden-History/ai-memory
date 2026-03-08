---
name: 'step-05-assemble-prompt'
description: 'Assemble the complete team prompt from context blocks using the tier-appropriate template'
nextStepFile: './step-06-review-and-present.md'
twoTierTemplate: '{project-root}/_ai-memory/pov/templates/team-prompt-2tier.template.md'
threeTierTemplate: '{project-root}/_ai-memory/pov/templates/team-prompt-3tier.template.md'
---

# Step 5: Assemble the Prompt

## STEP GOAL
Using the context blocks from Step 4, assemble a complete, copy-pasteable team prompt with zero placeholders or TBD values.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All context blocks from Step 4, approved design from Steps 2-3, templates at `{twoTierTemplate}` and `{threeTierTemplate}`
- Limits: Assembly only — the prompt is reviewed and presented in the next step

## MANDATORY SEQUENCE

### 1. Load Tier-Appropriate Template

**3-tier**: Read `{threeTierTemplate}` in full. Use it as the structural guide.
**2-tier**: Read `{twoTierTemplate}` in full. Use it as the structural guide.

If the template does not exist, use the inline assembly structures in sections 2-5 below.

### 2. Assemble Outer Prompt (Stage 1)

The outer prompt header includes:
- `TeamCreate` instruction (team name and description)
- Team size and objective
- Model selection for each manager/teammate (Agent tool `model` parameter)
- Plan approval instruction (Agent tool `mode: "plan"` parameter, if required)
- Worktree isolation instruction (Agent tool `isolation: "worktree"` parameter, if selected)
- Delegate mode instruction (if recommended)
- Wait-for-completion instruction

**3-tier format**: "Create a team called '[name]' with description '[objective]'. Then spawn [N] manager teammates to [objective]. Use [Model] for each. Work only through managers — do not implement directly."

**2-tier format**: "Create a team called '[name]' with description '[objective]'. Then spawn [N] teammates to [objective]. Use [Model] for each. [plan approval instruction] [delegate mode instruction]"

### 3. Embed Context Blocks (Stage 2)

**For 3-tier** — Each manager's 10-element context block is embedded as a teammate spawn prompt. Within each manager's Element 4 (WORKER ROSTER), the complete 8-element worker prompts are nested:

```
Outer prompt
  Manager 1 spawn prompt (10 elements)
    Element 4: Worker 1 spawn prompt (8 elements)
    Element 4: Worker 2 spawn prompt (8 elements)
    Element 5: Review agent prompt
  Manager 2 spawn prompt (10 elements)
    Element 4: Worker 1 spawn prompt (8 elements)
    Element 5: Review agent prompt
```

**Key architectural principle**: Managers spawn workers as **Agent tool subagents** (`subagent_type='general-purpose'`, no `team_name`), NOT as teammates. This prevents context window accumulation — each worker starts fresh, results are summarized and returned to the manager. Teammates are spawned with `Agent` tool + `team_name` parameter; subagents are spawned with `Agent` tool without `team_name`.

**For 2-tier** — Each teammate's 8-element context block is embedded directly as a teammate spawn prompt. No nesting.

### 4. Add Lead Instructions

Include in the assembled prompt after all manager/teammate blocks:

**3-tier lead instructions**:
- Monitor manager progress via TaskList. Each manager sends a message (SendMessage) when their domain is verified
- Do NOT communicate directly with workers — managers own their worker interactions
- If a manager escalates (3 review cycles failed), assess the blocker and provide guidance via SendMessage
- When all managers finish, run cross-domain integration verification
- Synthesize results into [deliverable format]
- After synthesis, shut down all managers using SendMessage (type: 'shutdown_request') to each
- After all managers confirm shutdown, clean up the team using TeamDelete

**2-tier lead instructions**:
- Monitor teammate progress via TaskList. If a teammate appears stuck, redirect via SendMessage
- When all teammates finish, synthesize their results into [deliverable format]
- After synthesis, shut down all teammates using SendMessage (type: 'shutdown_request') to each
- After all teammates confirm shutdown, clean up the team using TeamDelete

Add the **Shared Task List** (using TaskCreate) after lead instructions, mapping each domain/area to its manager/teammate.

### 5. Add Contract-First Build Addendum (If Applicable)

**Skip if not Contract-First Build pattern.**

Add to lead instructions:
- **Contract Chain**: Producer -> contract type -> Consumer for each interface
- **Spawn Order**: Phased, staggered — upstream first, downstream only after contract verified
- **Contract Relay Protocol**: Lead receives, verifies (exact URLs, JSON shapes, status codes, error format), forwards. Do NOT let agents share contracts directly
- **Pre-Integration Contract Diff**: Before synthesis, ask each domain what it exposes and what it consumes. Compare and flag mismatches
- **Execution Phases**: (1) Contracts — sequential, lead-orchestrated. (2) Implementation — parallel. (3) Contract Diff — lead compares. (4) Cross-Review — each domain reviews another's integration points

### 6. Verify No Placeholders

Scan the entire assembled prompt for:
- `[placeholder]` or `[TBD]` patterns
- `TBD` or `TODO` strings
- `$VARIABLE` references
- `___` unfilled blanks
- Empty fields or sections

**If any are found**: Fill them in from the design decisions or flag to the user for resolution. Do not proceed with placeholders.

## CRITICAL STEP COMPLETION NOTE
ONLY when the prompt is fully assembled with zero placeholders, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Prompt follows the tier-appropriate template structure
- Every context block is self-contained (no conversation references)
- Zero placeholders, TBDs, or empty fields remain
- Nesting structure is correct (3-tier: outer -> manager -> worker)
- Lead instructions are complete with synthesis and shutdown protocol
- Contract-First addendum included (if applicable)

### FAILURE:
- Leaving placeholders in the prompt
- Referencing conversation history in context blocks ("as we discussed")
- Omitting lead instructions or shutdown protocol
- Spawning workers as teammates instead of Agent tool subagents in 3-tier prompt
- Skipping the placeholder verification scan
