---
name: 'step-03-verify-prompt'
description: 'HITL gate — present final prompt to user before API call'
nextStepFile: './step-04-execute.md'
---

# Step 3: Verify Prompt

## STEP GOAL
Present the generation prompt to the user for review and approval before any API call is made.
The user can approve as-is, edit, or cancel. This step MUST NOT be skipped.

## MANDATORY EXECUTION RULES
- Never skip this step, even if the user already provided a detailed prompt
- Never call the API before receiving explicit approval
- A revised prompt from the user replaces INPUT_SOURCE entirely

## CONTEXT BOUNDARIES
- Available context: TASK_TYPE, MODEL, and INPUT_SOURCE from previous steps
- Limits: Do not make any API calls in this step. Gate only.

## MANDATORY SEQUENCE

### 1. Display Prompt and Model

Present clearly:

> **Task:** Video Generation
> **Model:** [MODEL]
>
> **Prompt to send:**
> ```
> [INPUT_SOURCE]
> ```
>
> **Options:**
> - **[A] Approve** — send this prompt as-is
> - **[E] Edit** — revise the prompt before sending
> - **[C] Cancel** — abort the workflow

### 2. Wait for Response

Halt completely. Do not proceed until the user responds with A, E, or C (or equivalent text).

### 3. Handle Response

**User approves (A):**
- Keep INPUT_SOURCE unchanged
- Proceed to execute step

**User edits (E):**
- Display the current prompt in an editable form
- Wait for the user to provide the revised prompt
- Replace INPUT_SOURCE with the revised text
- Confirm: "Using revised prompt. Proceeding to execution."
- Proceed to execute step

**User cancels (C):**
- Display: "Workflow cancelled. No API call was made."
- Halt. Do not load next step.

### 4. Record Final Prompt

After approval or edit:
- **INPUT_SOURCE**: Final approved/revised prompt (may be unchanged or updated)
- **PROMPT_APPROVED**: true

## CRITICAL STEP COMPLETION NOTE
ONLY when the user has explicitly approved or revised the prompt (PROMPT_APPROVED = true),
load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Prompt displayed clearly with model and task type
- User explicitly responded (A/E/C)
- Final prompt recorded before proceeding
- Workflow aborted cleanly on cancel

### FAILURE:
- Proceeding to API call without user approval
- Using stale prompt after user edited it
- Silently skipping this step for any reason
- Treating absence of response as approval
