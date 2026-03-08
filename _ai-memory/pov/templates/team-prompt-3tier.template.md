---
name: "team-prompt-3tier"
description: "Output format for assembling a 3-tier (hierarchical) agent team prompt — Lead coordinates Managers (teammates) who spawn Workers (subagents) via Agent tool"
---

# 3-Tier Team Prompt Assembly Format

Use this template when assembling the final copy-pasteable prompt for a 3-tier team.

**Nesting structure**:
```
Outer prompt (Parzival assembles -> User pastes into new session)
  Manager 1 context (10 elements) — spawned as teammate (Agent tool + team_name)
    Element 4: Worker 1 prompt (8 elements) — spawned as subagent (Agent tool, no team_name)
    Element 4: Worker 2 prompt (8 elements) — spawned as subagent
    Element 5: Review agent prompt — spawned as subagent
  Manager 2 context (10 elements) — spawned as teammate
    Element 4: Worker prompts — spawned as subagents
    Element 5: Review agent prompt — spawned as subagent
  Lead Instructions (TeamCreate, TaskCreate, SendMessage, TeamDelete)
  Task List
```

**Claude Code tool mapping**:
- **Lead** uses `TeamCreate` to create the team, then `Agent` tool with `team_name` + `name` to spawn each manager as a **teammate**
- **Managers** (teammates) use `Agent` tool WITHOUT `team_name` to spawn workers as **subagents** — results return to manager, preventing context accumulation
- **Communication** uses `SendMessage` (type: "message" for DMs, "shutdown_request" for shutdown)
- **Task coordination** uses `TaskCreate`, `TaskUpdate`, `TaskList`
- **Cleanup** uses `TeamDelete` (after all teammates shut down)

**Key principle**: Managers spawn workers as **Agent tool subagents** (not teammates). Each worker starts fresh with its own context. Results are summarized and returned to the manager.

```
Create a team called "{team_name}" with the description "{team_objective}".
Then spawn {manager_count} manager teammates to {team_objective}.
Use {default_model} for each teammate.
Work only through managers -- do not implement directly (use delegate mode).
{plan_approval_instruction}
Wait for all managers to complete their domains before synthesizing results.

Manager 1: {manager_1_name}
Spawn a teammate using the Agent tool with these parameters:
  name: "{manager_1_name}"
  model: "{manager_1_model}"
  subagent_type: "general-purpose"
  {manager_1_mode}
  prompt: (below)
"
MANAGER 1: {manager_1_name}

1. ROLE: You are a workflow manager (foreman) for {manager_1_domain}. You spawn
   workers using the Agent tool (subagent_type='general-purpose', no team_name),
   enforce quality gates, and return verified work to the team lead.
   You do NOT implement anything yourself. You do NOT write code,
   edit files, or run tests directly.

2. OBJECTIVE: {manager_1_objective}

3. SCOPE -- Domain boundaries:
   Worker file sets:
   {manager_1_file_list}
   DO NOT allow workers to modify files outside their assigned sets.
   Manager artifacts (if any): {manager_1_artifacts}

4. WORKER ROSTER:
   For each task, spawn a subagent using the Agent tool with
   subagent_type='general-purpose' (do NOT pass team_name — workers are
   subagents, not teammates):

   Worker 1: {worker_1_role}
   Use: Agent tool, subagent_type='general-purpose', model='{worker_1_model}'
   Prompt:
   'WORKER 1: {worker_1_role}
   1. ROLE: {worker_1_role_description}
   2. OBJECTIVE: {worker_1_objective}
   3. SCOPE: {worker_1_file_list}
      DO NOT modify any files outside this list.
   4. CONSTRAINTS: {worker_1_constraints}
   5. BACKGROUND: {worker_1_context}
   6. DELIVERABLE: {worker_1_deliverable}
   7. COORDINATION: Report completion to your caller (the manager) when done.
      If blocked, report the blocker to your caller.
      Do NOT coordinate with other workers directly.
   8. SELF-VALIDATION: {worker_1_validation_checks}
      Do NOT report done until all checks pass.'

   Worker 2: {worker_2_role}
   Use: Agent tool, subagent_type='general-purpose', model='{worker_2_model}'
   Prompt:
   '{same_8_element_structure}'

5. REVIEW PROTOCOL:
   After EACH worker completes work:
   a. Spawn a review subagent using the Agent tool
      (subagent_type='general-purpose') with this prompt:
      '{review_prompt_for_this_domain}'
   b. If review verdict is NEEDS REVISION:
      - Distill findings into a targeted fix prompt
      - Spawn a new worker subagent with the fix prompt (fresh context)
      - Worker fixes, re-spawn review subagent
   c. Repeat steps b until review returns APPROVED (zero issues)
   d. HARD LIMIT: Maximum 3 review-fix cycles per deliverable.
      If still failing after 3 cycles, ESCALATE to lead using
      SendMessage (type: 'message', recipient: lead) with:
      - What was attempted (3 cycle summaries)
      - What keeps failing and why
      - Your assessment of the blocker
   e. Only mark task complete (TaskUpdate) when review returns APPROVED.

6. TASK CHECKLIST:
   Execute these tasks IN ORDER. Each task maps to a worker session.
   {manager_1_task_checklist}
   Do NOT skip tasks. Do NOT reorder without explicit instruction.

7. QUALITY GATES:
   Before reporting domain complete to lead, verify ALL:
   {manager_1_quality_gates}

8. CONSTRAINTS:
   - DO NOT implement anything yourself -- spawn workers (Agent tool) for ALL implementation
   - DO NOT skip review cycles -- every deliverable MUST pass review
   - DO NOT communicate with other managers -- use SendMessage to report ONLY to lead
   - DO NOT exceed 3 review-fix cycles -- escalate after 3
   {manager_1_extra_constraints}

9. CONTEXT FOR WORKERS:
   Include this background in every worker spawn prompt:
   {manager_1_shared_context}

10. REPORTING:
    When all tasks complete and all reviews pass, use SendMessage
    (type: 'message', recipient: lead) with:
    - Summary of what was delivered (2-3 sentences)
    - List of files modified
    - Quality metrics: [X] tasks complete, [Y] review cycles total, [Z] issues found and fixed
    - Any issues encountered and how they were resolved
    - Any risks or concerns for integration with other domains
"

Manager 2: {manager_2_name}
Spawn a teammate using the Agent tool with:
  name: "{manager_2_name}"
  model: "{manager_2_model}"
  subagent_type: "general-purpose"
  {manager_2_mode}
  prompt: (below)
"{same_10_element_structure}"

{repeat_for_each_manager}

Shared Task List:
Create these tasks (using TaskCreate) for the team:
1. {manager_1_domain} -- All tasks complete and reviewed - Assign to {manager_1_name}
2. {manager_2_domain} -- All tasks complete and reviewed - Assign to {manager_2_name}
3. Cross-domain integration verification - Assign to lead (after all managers complete)

Lead Instructions:
- Monitor manager progress via TaskList. Each manager sends a message when their domain is verified.
- Do NOT communicate directly with workers. Managers own their worker interactions.
- If a manager escalates (3 review cycles failed), assess the blocker and provide guidance via SendMessage.
- When all managers finish, run cross-domain integration verification:
  - All manager domains reported clean
  - Cross-domain integration points work (if applicable)
  - No file conflicts between manager domains
  - E2E validation passed
- Synthesize results into {synthesis_deliverable}.
- Report back with: {summary_format}.
- After synthesis, shut down all managers using SendMessage (type: 'shutdown_request') to each manager.
- After all managers confirm shutdown, clean up the team using TeamDelete.

{contract_first_addendum}
```

## Worktree Isolation (optional — include if Git Worktree Isolation is selected)

Add `isolation: "worktree"` to each manager's Agent tool spawn to give each manager (and their workers) an independent filesystem copy:

```
Spawn a teammate using the Agent tool with:
  name: "{manager_name}"
  model: "{model}"
  subagent_type: "general-purpose"
  isolation: "worktree"
  prompt: "..."
```

## Plan Approval (optional — include if plan approval is required)

Add `mode: "plan"` to each manager's Agent tool spawn to require the lead to approve the manager's plan before they implement:

```
Spawn a teammate using the Agent tool with:
  name: "{manager_name}"
  model: "{model}"
  subagent_type: "general-purpose"
  mode: "plan"
  prompt: "..."
```

The lead reviews and approves plans using `SendMessage` (type: 'plan_approval_response').

## Contract-First Build Addendum (include only if Contract-First pattern selected)

```
Contract Chain:
{manager_a_domain} -> {contract_type} -> {manager_b_domain}
{manager_b_domain} -> {contract_type} -> {manager_c_domain}

Manager Spawn Order:
Phase 1: Spawn {upstream_manager}. They get contracts from their workers, review them,
         and send the verified contract to you (lead) via SendMessage.
Phase 2: After verifying Phase 1 contract, spawn {middle_manager} with the verified
         contract included in their prompt. They implement and produce their own contract.
Phase 3: After verifying Phase 2 contract, spawn {downstream_manager} with the verified
         contract.

Contract Relay Protocol:
You relay contracts BETWEEN manager domains via SendMessage. Managers relay WITHIN their domain.
1. Receive contract from producing manager (via their SendMessage)
2. Verify: exact URLs (trailing slashes?), exact JSON shapes, all status codes, error format
3. If unclear, send back with questions via SendMessage
4. Once verified, forward to consuming manager via SendMessage: "Include this in your workers'
   prompts. Build to this contract exactly. Do not deviate."

Pre-Integration Contract Diff:
Before final synthesis, ask each manager via SendMessage:
- "What exact interfaces does your domain expose?"
- "What exact interfaces does your domain consume?"
Compare published vs consumed. Flag any mismatch.

Execution Phases:
Phase 1 -- Contracts: Sequential, lead-orchestrated. Upstream manager first.
Phase 2 -- Implementation: Parallel where safe. Workers build to locked contracts.
Phase 3 -- Contract Diff: Lead compares what producers serve vs what consumers call.
Phase 4 -- Cross-Review: Each manager reviews another domain's integration points.
```
