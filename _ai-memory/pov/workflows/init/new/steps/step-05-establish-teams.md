---
name: 'step-05-establish-teams'
description: 'Verify agent dispatch infrastructure is available for subsequent phases'
nextStepFile: './step-06-verify-baseline.md'
---

# Step 5: Establish Agent Dispatch Infrastructure

## STEP GOAL
Verify that the agent dispatch infrastructure is available and accessible for subsequent phases. Agent teams are designed on-demand via the aim-parzival-team-builder skill when parallel work is needed -- they are not pre-created during initialization.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Confirmed project name, track selection, agent dispatch capability
- Limits: Do not activate any agents yet. Only verify the dispatch infrastructure is available. Agent activation happens during phase workflows via {workflows_path}/cycles/agent-dispatch/workflow.md.

## MANDATORY SEQUENCE

### 1. Verify Agent Dispatch Capability
Confirm that the agent dispatch infrastructure is available:
- Check that the Agent tool is accessible for spawning agents
- Check that SendMessage between agents is functional
- If dispatch capability is not available, alert the user and document the limitation

### 2. Document Dispatch Configuration
Record the dispatch configuration for this project:

**Agent roles available for dispatch:**
- Analyst -- research and diagnosis tasks
- PM -- requirements and PRD creation
- Architect -- architecture design and readiness checks
- UX Designer -- user experience design (if UI work in scope)
- SM -- sprint management, story creation, retrospectives
- DEV -- implementation and code review

**Team design on demand:**
- When parallel work is needed, use the aim-parzival-team-builder skill to design the appropriate team structure (single agent, 2-tier, or 3-tier)
- Team design produces context blocks that feed into the agent-dispatch cycle

### 3. Verify Agent Dispatch Workflow Is Accessible
Confirm that the agent dispatch workflow exists and is loadable:
- {workflows_path}/cycles/agent-dispatch/workflow.md must be present
- Agent dispatch steps must be accessible
- This workflow will be invoked whenever Parzival needs to activate an agent

### 4. Record Configuration in Project Status
Note in project-status.md that the dispatch infrastructure is established:
- Agent dispatch workflow accessible
- Ready for agent activation in subsequent phases

## CRITICAL STEP COMPLETION NOTE
ONLY when dispatch capability is verified and documented, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Agent dispatch capability is verified as available
- Agent dispatch workflow accessibility is confirmed
- No agents were prematurely activated
- Configuration is recorded for subsequent workflows

### FAILURE:
- Activating agents during initialization (too early)
- Proceeding without verifying dispatch capability
- Not documenting the configuration
