---
name: 'step-05-establish-teams'
description: 'Verify agent dispatch infrastructure is available for subsequent phases'
nextStepFile: './step-06-verify-baseline.md'
---

# Step 5: Establish Agent Dispatch Infrastructure

**Progress: Step 5 of 7** — Next: Verify Baseline

## STEP GOAL:

Verify that the agent dispatch infrastructure is available and accessible for subsequent phases. Agent teams are designed on-demand via the aim-parzival-team-builder skill when parallel work is needed -- they are not pre-created during initialization.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus only on verifying dispatch infrastructure -- no agent activation
- 🚫 FORBIDDEN to activate any agents during this step
- 💬 Approach: Systematic capability verification with clear status reporting
- 📋 Verify infrastructure availability only -- agent activation happens in phase workflows

## EXECUTION PROTOCOLS:

- 🎯 Verify agent dispatch capability and workflow accessibility
- 💾 Record dispatch configuration in project-status.md
- 📖 Load next step only after infrastructure is verified and documented
- 🚫 FORBIDDEN to activate agents or begin any Discovery work

## CONTEXT BOUNDARIES:

- Available context: Confirmed project name, track selection, agent dispatch capability
- Focus: Infrastructure verification only -- do not activate agents
- Limits: Do not activate any agents yet. Only verify the dispatch infrastructure is available. Agent activation happens during phase workflows via {workflows_path}/cycles/agent-dispatch/workflow.md.
- Dependencies: Steps 1-4 complete with project baseline files created

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Verify Agent Dispatch Capability

Confirm that the agent dispatch infrastructure is available:
- Check that the Agent tool is accessible for spawning agents
- Check that SendMessage between agents is functional
- If dispatch capability is not available, alert the user and document the limitation

---

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

---

### 3. Verify Agent Dispatch Workflow Is Accessible

Confirm that the agent dispatch workflow exists and is loadable:
- {workflows_path}/cycles/agent-dispatch/workflow.md must be present
- Agent dispatch steps must be accessible
- This workflow will be invoked whenever Parzival needs to activate an agent

---

### 4. Record Configuration in Project Status

Note in project-status.md that the dispatch infrastructure is established:
- Agent dispatch workflow accessible
- Ready for agent activation in subsequent phases

---

### 5. Present MENU OPTIONS

Display: "**Agent dispatch infrastructure verified. Ready to verify baseline.**"

**Select an Option:** [C] Continue to Baseline Verification

#### Menu Handling Logic:

- IF C: Read fully and follow: `{nextStepFile}` to begin baseline verification
- IF user asks questions: Answer and redisplay menu
- IF user reports issues: Document the issue, attempt resolution, redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C' (Continue)

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [C continue option] is selected and [dispatch capability is verified and documented], will you then read fully and follow: `{nextStepFile}` to begin baseline verification.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Agent dispatch capability is verified as available
- Agent dispatch workflow accessibility is confirmed
- No agents were prematurely activated
- Configuration is recorded for subsequent workflows
- Menu presented and user input handled correctly

### ❌ SYSTEM FAILURE:

- Activating agents during initialization (too early)
- Proceeding without verifying dispatch capability
- Not documenting the configuration
- Proceeding without user selecting 'C' (Continue)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
