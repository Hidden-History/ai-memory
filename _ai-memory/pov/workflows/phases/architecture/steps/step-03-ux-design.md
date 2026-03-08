---
name: 'step-03-ux-design'
description: 'Activate UX Designer agent if the project has a user interface requiring design work (optional step)'
nextStepFile: './step-04-parzival-reviews-architecture.md'
---

# Step 3: UX Design (If Applicable)

## STEP GOAL
Activate the UX Designer agent if the project has a user interface requiring design work. Skip this step if the project is API-only, CLI, or the user has stated UX design is not needed.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: PRD.md, architecture.md draft
- Limits: UX Designer creates design artifacts. Parzival reviews architecture in the next step.

## MANDATORY SEQUENCE

### 1. Determine If UX Design Is Needed

**Activate UX Designer when:**
- Project has a user interface (web, mobile, desktop)
- New UI patterns or screens are being designed
- PRD includes UX-related acceptance criteria that need design definition

**Skip UX Designer when:**
- Project is API-only or CLI
- Only simple updates to existing UI screens
- User explicitly states UX design is not needed for this phase

**IF SKIPPING:** Proceed directly to {nextStepFile}

### 2. Prepare UX Design Instruction
UX design must cover:
- User flows for all Must Have features in PRD
- Screen/component inventory
- Key interaction patterns
- Responsive design considerations (if web)
- Accessibility requirements (if specified in PRD)

### 3. Dispatch UX Designer via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the UX Designer with the prepared instruction. Provide PRD.md and architecture.md as context.

### 4. Receive UX Design Artifacts
Receive the UX design output. This will inform story creation in Step 6.

## CRITICAL STEP COMPLETION NOTE
Whether UX design was performed or skipped, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Correct decision made about whether UX design is needed
- If activated, UX Designer dispatched through agent-dispatch workflow
- Design artifacts reference PRD acceptance criteria
- If skipped, clear justification recorded

### FAILURE:
- Activating UX Designer for API-only projects
- Skipping UX design for a UI-heavy project without justification
- UX Designer dispatched directly instead of through agent-dispatch
