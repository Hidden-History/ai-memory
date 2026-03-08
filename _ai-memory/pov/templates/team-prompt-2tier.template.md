---
name: "team-prompt-2tier"
description: "Output format for assembling a 2-tier (flat) agent team prompt — Lead coordinates Workers (teammates) directly via Agent tool + team_name"
---

# 2-Tier Team Prompt Assembly Format

Use this template when assembling the final copy-pasteable prompt for a 2-tier team.

**Claude Code tool mapping**:
- **Lead** uses `TeamCreate` to create the team, then `Agent` tool with `team_name` + `name` to spawn each worker as a **teammate**
- **Communication** uses `SendMessage` (type: "message" for DMs, "shutdown_request" for shutdown)
- **Task coordination** uses `TaskCreate`, `TaskUpdate`, `TaskList`
- **Cleanup** uses `TeamDelete` (after all teammates shut down)

```
Create a team called "{team_name}" with the description "{team_objective}".
Then spawn {teammate_count} teammates to {team_objective}.
Use {default_model} for each teammate.
{plan_approval_instruction}
{delegate_mode_instruction}
Wait for all teammates to complete their tasks before synthesizing results.

Teammate 1: {teammate_1_name}
Spawn a teammate using the Agent tool with these parameters:
  name: "{teammate_1_name}"
  model: "{teammate_1_model}"
  subagent_type: "general-purpose"
  {teammate_1_mode}
  prompt: (below)
"
TEAMMATE 1: {teammate_1_name}

1. ROLE: {teammate_1_role}

2. OBJECTIVE: {teammate_1_objective}

3. SCOPE -- Files you own:
   {teammate_1_file_list}
   DO NOT modify any files outside this list.

4. CONSTRAINTS:
   - DO NOT touch files owned by other teammates: {teammate_1_forbidden_files}
   - Follow these project patterns: {teammate_1_patterns}
   {teammate_1_extra_constraints}

5. BACKGROUND:
   {teammate_1_context}

6. DELIVERABLE:
   {teammate_1_deliverable}

7. COORDINATION:
   - Use SendMessage (type: 'message', recipient: lead) when done with a summary
   - If blocked, use SendMessage to message the lead with what you need
   {teammate_1_coordination_notes}

8. SELF-VALIDATION:
   Before reporting done, run these checks and fix any failures:
   {teammate_1_validation_checks}
   Do NOT report done until all checks pass.
"

Teammate 2: {teammate_2_name}
Spawn a teammate using the Agent tool with:
  name: "{teammate_2_name}"
  model: "{teammate_2_model}"
  subagent_type: "general-purpose"
  {teammate_2_mode}
  prompt: (below)
"{same_8_element_structure}"

{repeat_for_each_teammate}

Shared Task List:
Create these tasks (using TaskCreate) for the team:
{numbered_task_list_with_assignments}

Lead Instructions:
- Monitor teammate progress via TaskList. If a teammate appears stuck, redirect via SendMessage.
{plan_approval_lead_instructions}
- When all teammates finish, synthesize their results into {synthesis_deliverable}.
- Report back with: {summary_format}.
- After synthesis, shut down all teammates using SendMessage (type: 'shutdown_request') to each.
- After all teammates confirm shutdown, clean up the team using TeamDelete.

{contract_first_addendum}
```

## Worktree Isolation (optional — include if Git Worktree Isolation is selected)

Add `isolation: "worktree"` to each teammate's Agent tool spawn to give each an independent filesystem copy:

```
Spawn a teammate using the Agent tool with:
  name: "{teammate_name}"
  model: "{model}"
  subagent_type: "general-purpose"
  isolation: "worktree"
  prompt: "..."
```

## Plan Approval (optional — include if plan approval is required)

Add `mode: "plan"` to each teammate's Agent tool spawn:

```
Spawn a teammate using the Agent tool with:
  name: "{teammate_name}"
  model: "{model}"
  subagent_type: "general-purpose"
  mode: "plan"
  prompt: "..."
```

The lead reviews and approves plans using `SendMessage` (type: 'plan_approval_response').

## Contract-First Build Addendum (include only if Contract-First pattern selected)

```
Contract Chain:
{producer} -> {contract_type} -> {consumer}
{producer} -> {contract_type} -> {consumer}

Spawn Order:
Phase 1: Spawn {upstream_agent}. Their first task is publishing their contract to you via SendMessage.
Phase 2: After verifying Phase 1 contract, spawn {middle_agent} with the verified contract. Their first task is publishing their own contract to you via SendMessage.
Phase 3: After verifying Phase 2 contract, spawn {downstream_agent} with the verified contract.

Contract Relay Protocol:
You are the contract relay. Do NOT tell agents to share contracts directly.
1. Receive contract from producing agent (via their SendMessage)
2. Verify: exact URLs (trailing slashes?), exact JSON shapes, all status codes, error format, no ambiguity
3. If unclear, send back with questions via SendMessage
4. Once verified, forward to consuming agent via SendMessage: "Build to this contract exactly. Do not deviate."

Pre-Integration Contract Diff:
Before integration testing, ask each agent via SendMessage:
- "What exact commands/calls test your interface?"
Compare producer's published interface against consumer's implemented calls. Flag any mismatch.

Execution Phases:
Phase 1 -- Contracts: Sequential, lead-orchestrated. Each agent publishes, lead verifies and relays.
Phase 2 -- Implementation: Parallel where safe. Agents build to locked contracts.
Phase 3 -- Contract Diff: Lead compares what producers serve vs what consumers call.
Phase 4 -- Cross-Review: Each agent reviews another's work at integration points.
```
