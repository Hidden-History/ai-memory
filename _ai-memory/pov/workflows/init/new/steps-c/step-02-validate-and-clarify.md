---
name: 'step-02-validate-and-clarify'
description: 'Validate user-provided project information for completeness, specificity, and consistency before proceeding'
nextStepFile: './step-03-verify-installation.md'
---

# Step 2: Validate and Clarify

**Progress: Step 2 of 7** — Next: Verify Installation

## STEP GOAL:

Validate the information gathered in Step 1 for completeness, specificity, and internal consistency. Resolve any vagueness, contradictions, or critical gaps before proceeding. Confirm the validated information with the user.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: User responses from Step 1
- Focus: Validation and clarification only — do not begin creating files
- Limits: Do not assume what the user meant. Do not fill gaps with guesses. Do not proceed on incomplete or contradictory information.
- Dependencies: Step 1 must be complete with user responses recorded

- Focus only on validating and clarifying gathered information — no file creation yet
**Behavioral Constraints:**
- FORBIDDEN to assume what the user meant or fill gaps with guesses
- Approach: Systematic validation with clear flagging of issues
- Do not proceed on incomplete or contradictory information

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Handle Validation Results

**IF information is vague:** Ask for specifics.
Example: "You mentioned 'modern framework' -- for the web app, are you thinking React, Vue, Svelte, or do you want to decide that in Architecture?"

**IF information is contradictory:** Flag the contradiction.
Example: "You mentioned a 2-week deadline but also Enterprise scale -- those may conflict. Should we scope down to Standard Method or adjust the timeline expectation?"

**IF information is missing but can be deferred:** Note it explicitly.
Example: "Tech stack is TBD -- that is fine. We will decide in Architecture. I will flag that as an open item."

---

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

---

### 4. Wait for Explicit Confirmation

Do not proceed until the user explicitly confirms. If corrections are needed, update the summary and re-confirm.

---

### 5. Present MENU OPTIONS

Display: "**Project foundation validated and confirmed. Ready to verify installation.**"

**Select an Option:** [C] Continue to Installation Verification

#### Menu Handling Logic:

- IF C: Read fully and follow: `{nextStepFile}` to begin installation verification
- IF user provides corrections: Update summary, re-validate, redisplay menu
- IF user asks questions: Answer and redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C' (Continue)

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [C continue option] is selected and [user has explicitly confirmed the project foundation summary], will you then read fully and follow: `{nextStepFile}` to begin installation verification.
