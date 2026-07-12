---
name: "team-prompt-2tier"
description: "Output format for assembling a 2-tier (flat) agent team prompt — Lead coordinates Workers (teammates) directly via the Agent tool with a unique name"
---

# 2-Tier Team Prompt Assembly Format

Use this template when assembling the final copy-pasteable prompt for a 2-tier team.

**Claude Code tool mapping**:
- **Lead** spawns each worker as a **teammate** via the `Agent` tool with a unique `name`
- **Communication** uses `SendMessage` (type: "message" for DMs, "shutdown_request" for shutdown)
- **Task coordination** uses `TaskCreate`, `TaskUpdate`, `TaskList`
- **Cleanup** uses the `shutdown_request` handshake, one per teammate (from the lead session)

**Two-phase BMAD activation (GC-20):** each teammate's spawn `prompt` carries ONLY its BMAD activation
+ the report-to-team-lead one-line — never the task. `{teammate_N_activation}` is the Skill-tool-load
form: `Use the Skill tool to load bmad-<role> (the BMAD <role> persona).` (a bare `/bmad-*` at spawn
activates Parzival, not the persona). After the teammate replies with its greeting/menu, send the
8-section task block as ONE SendMessage.

```
Spawn each teammate via the `Agent` tool (below).
Then spawn {teammate_count} teammates to {team_objective}.
Use {default_model} for each teammate.
{plan_approval_instruction}
{delegate_mode_instruction}
Wait for all teammates to complete their tasks before synthesizing results.

Teammate 1: {teammate_1_name}
Spawn a teammate using the Agent tool with these parameters:
  name: "{teammate_1_name}"
  model: "{teammate_1_model}"
  subagent_type: "{teammate_1_subagent_type}"
  mode: "auto"
  prompt: "{teammate_1_activation}
You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."

Wait for {teammate_1_name}'s activation reply (greeting + menu). Then send the task as ONE SendMessage — the 8-section block below, never bundled into the spawn prompt (GC-20):
"
TEAMMATE 1: {teammate_1_name}

1. ROLE: {teammate_1_role}

2. OBJECTIVE: {teammate_1_objective}

3. SCOPE -- Files you own:
   {teammate_1_file_list}
   DO NOT modify any files outside this list.

4. CONSTRAINTS:
   - DO NOT modify any files outside your SCOPE list (Section 3 above)
   - Follow these project patterns: {teammate_1_patterns}
   {teammate_1_extra_constraints}

5. BACKGROUND:
   {teammate_1_context}

6. DELIVERABLE:
   {teammate_1_deliverable}

7. COORDINATION:
   - SendMessage to team-lead (by name; never "main") when done with a summary
   - One message, then wait for the reply
   - If blocked, SendMessage the lead with what you need
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
  subagent_type: "{teammate_2_subagent_type}"
  mode: "auto"
  prompt: "{teammate_2_activation}
You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply to team-lead, then wait for my instructions before doing any work."

Wait for the activation reply, then send the task as ONE SendMessage (same 8-section structure as Teammate 1):
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
- After all teammates confirm shutdown, cleanup is complete.

{contract_first_addendum}
```

## Worktree Isolation (optional — include if Git Worktree Isolation is selected)

Add `isolation: "worktree"` to each teammate's Agent tool spawn to give each an independent filesystem copy:

```
Spawn a teammate using the Agent tool with:
  name: "{teammate_name}"
  model: "{model}"
  subagent_type: "{teammate_subagent_type}"
  isolation: "worktree"
  prompt: "..."
```

## Plan Approval (optional — include if plan approval is required)

Add `mode: "plan"` to each teammate's Agent tool spawn:

```
Spawn a teammate using the Agent tool with:
  name: "{teammate_name}"
  model: "{model}"
  subagent_type: "{teammate_subagent_type}"
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
