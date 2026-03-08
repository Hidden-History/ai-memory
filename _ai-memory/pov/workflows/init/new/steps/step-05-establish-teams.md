---
name: 'step-05-establish-teams'
description: 'Establish Claude Code teams session structure for agent management'
nextStepFile: './step-06-verify-baseline.md'
---

# Step 5: Establish Claude Code Teams Session Structure

## STEP GOAL
Set up the Claude Code teams structure that Parzival will use to manage all agents for this project. This uses Claude Code's experimental agent teams capability (TeamCreate, Agent tool spawn, SendMessage) to create and manage agent sessions.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Confirmed project name, track selection, Claude Code teams capability
- Limits: Do not activate any agents yet. Only verify the teams infrastructure is available. Agent activation happens during phase workflows via {workflows_path}/cycles/agent-dispatch/workflow.md.

## MANDATORY SEQUENCE

### 1. Verify Claude Code Teams Capability
Confirm that the Claude Code teams capability is available:
- Check that TeamCreate functionality is accessible
- Check that Agent tool spawn is operational
- Check that SendMessage between agents is functional
- If teams capability is not available, alert the user and document the limitation

### 2. Document Teams Configuration
Record the teams configuration for this project:

**Session naming convention:**
- Project identifier: [project-name-lowercase-hyphenated]
- Agent naming follows dispatch workflow conventions

**Agent roles available for dispatch:**
- Analyst -- research and diagnosis tasks
- PM -- requirements and PRD creation
- Architect -- architecture design and readiness checks
- UX Designer -- user experience design (if UI work in scope)
- SM -- sprint management, story creation, retrospectives
- DEV -- implementation and code review

### 3. Verify Agent Dispatch Workflow Is Accessible
Confirm that the agent dispatch workflow exists and is loadable:
- {workflows_path}/cycles/agent-dispatch/workflow.md must be present
- Agent dispatch steps must be accessible
- This workflow will be invoked whenever Parzival needs to activate an agent

### 4. Record Session Structure in Project Status
Note in project-status.md that the teams session structure is established:
- Teams capability verified
- Agent dispatch workflow accessible
- Ready for agent activation in subsequent phases

## CRITICAL STEP COMPLETION NOTE
ONLY when teams capability is verified and documented, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Claude Code teams capability is verified as available
- Session naming convention is documented
- Agent dispatch workflow accessibility is confirmed
- No agents were prematurely activated
- Configuration is recorded for subsequent workflows

### FAILURE:
- Activating agents during initialization (too early)
- Proceeding without verifying teams capability
- Not documenting the session structure
- Using agent management approaches other than Claude Code teams
