---
name: 'step-02-validate-and-clarify'
description: 'Validate user-provided project information for completeness, specificity, and consistency before proceeding'
nextStepFile: './step-03-verify-installation.md'
---

# Step 2: Validate and Clarify

## STEP GOAL
Validate the information gathered in Step 1 for completeness, specificity, and internal consistency. Resolve any vagueness, contradictions, or critical gaps before proceeding. Confirm the validated information with the user.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: User responses from Step 1
- Limits: Do not assume what the user meant. Do not fill gaps with guesses. Do not proceed on incomplete or contradictory information.

## MANDATORY SEQUENCE

### 1. Run Validation Checklist
For each item, check:
- Is the project name clear and usable as a file/folder name?
- Is the project type specific enough to inform tech decisions?
- Is the primary goal a single coherent objective (not multiple projects)?
- Are tech stack preferences specific (not "modern tech" or "latest version")?
- Is the selected track appropriate for the stated scale?
- Are constraints specific enough to act on?
- Are there any contradictions in the information provided?
- Is anything critical missing that must be resolved before proceeding?

### 2. Handle Validation Results

**IF information is vague:** Ask for specifics.
Example: "You mentioned 'modern framework' -- for the web app, are you thinking React, Vue, Svelte, or do you want to decide that in Architecture?"

**IF information is contradictory:** Flag the contradiction.
Example: "You mentioned a 2-week deadline but also Enterprise scale -- those may conflict. Should we scope down to Standard Method or adjust the timeline expectation?"

**IF information is missing but can be deferred:** Note it explicitly.
Example: "Tech stack is TBD -- that is fine. We will decide in Architecture. I will flag that as an open item."

### 3. Present Confirmation Summary
After validation, present the confirmed understanding to the user:

```
Project Foundation Summary:

  Name:        [project name]
  Type:        [project type]
  Goal:        [primary goal -- one sentence]
  Stack:       [confirmed choices / TBD items]
  Track:       [Quick Flow / Standard Method / Enterprise]
  Constraints: [list or 'none stated']
  Open items:  [anything deferred to Discovery]

Is this accurate? Any corrections before I proceed with setup?
```

### 4. Wait for Explicit Confirmation
Do not proceed until the user explicitly confirms. If corrections are needed, update the summary and re-confirm.

## CRITICAL STEP COMPLETION NOTE
ONLY when the user explicitly confirms the project foundation summary, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every required field has been validated for clarity and specificity
- Contradictions have been flagged and resolved
- Deferred items are explicitly marked as open
- User has explicitly confirmed the summary before proceeding
- No assumptions were made about user intent

### FAILURE:
- Proceeding without explicit user confirmation
- Filling gaps with guesses instead of asking
- Ignoring contradictions in provided information
- Treating vague answers as specific decisions
