---
name: 'cycles-agent-dispatch-instructions'
description: 'Agent dispatch lifecycle: prepare instruction, create team, dispatch, monitor, review, accept or correct, shutdown'
---

# cycles-agent-dispatch — Instructions

## Prerequisites

- Parzival oversight session active
- The target BMAD agent is identified and available
- A task instruction has been prepared (or is being prepared in step 1)
- TeamCreate capability is available (required for teammate-based dispatch)

## Workflow Overview

The agent-dispatch cycle is the standard mechanism for Parzival to delegate work to BMAD agents. It covers the full lifecycle from instruction preparation through output acceptance: composing a clear instruction, creating the agent team, activating the agent, sending the instruction, monitoring progress, receiving output, deciding whether to accept or loop for corrections, shutting down the teammate, and summarizing the result.

This cycle enforces that no agent is dispatched without a complete instruction and that all agent output passes through Parzival's accept-or-loop gate before being used downstream. The cycle may repeat steps 3–7 if the output requires revision.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-prepare-instruction.md` | Compose a complete, unambiguous instruction for the target agent |
| 2 | `step-02-create-team.md` | Create the agent team using TeamCreate with the target agent configuration |
| 3 | `step-03-activate-agent.md` | Activate the agent within the team context |
| 4 | `step-04-send-instruction.md` | Send the prepared instruction to the active agent via SendMessage |
| 5 | `step-05-monitor-progress.md` | Monitor agent progress; intervene if the agent stalls or deviates |
| 6 | `step-06-receive-output.md` | Receive and read the agent's completed output |
| 7 | `step-07-accept-or-loop.md` | Assess output quality; accept if satisfactory or compose correction and loop back to step 4 |
| 8 | `step-08-shutdown-teammate.md` | Shut down the agent teammate cleanly after output is accepted |
| 9 | `step-09-prepare-summary.md` | Summarize the agent's output for use by the calling workflow |

## Key Decisions

- **Instruction completeness**: Step 1 must produce a self-contained instruction; ambiguous instructions are never sent
- **Accept vs. loop**: Step 7 may send the agent back for corrections — corrections are always specific, never vague
- **Shutdown discipline**: Step 8 is always executed; teammates are never left running after their work is complete

## Outputs

- Accepted agent output (artifact, document, or analysis)
- Agent summary prepared for the calling workflow
- Teammate shut down cleanly

## Exit Conditions

The workflow exits when:
- Agent output has been accepted in step 7
- The teammate has been shut down in step 8
- The summary has been prepared in step 9
