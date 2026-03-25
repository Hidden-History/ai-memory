---
name: 'step-e-01-assess-session-close'
description: 'Edit mode: Assess session-close output and propose changes'
nextStepFile: './step-e-02-apply-edit.md'
---

# Edit Step 1: Assess Session Close Output

## STEP GOAL:

Assess the current state of session-close output, identify what needs to change, and propose specific edits for user approval.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER edit without understanding the current state first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — editing oversight artifacts
- ✅ Understand before editing — assess first, then propose changes
- ✅ User approves all edits before they are applied
- ✅ Cite what changed and why

### Step-Specific Rules:

- 🎯 Assess session-close output for issues identified in validation
- 🚫 FORBIDDEN to apply any changes in this step — assessment only
- 💬 Approach: Analytical — present findings with specific file:line references
- 📋 All proposed changes require user approval before proceeding

## EXECUTION PROTOCOLS:

- 🎯 Assess current state before proposing changes
- 💾 Document all proposed changes with reasoning
- 📖 Present proposals to user and wait for approval
- 🚫 FORBIDDEN to apply changes without user approval

## CONTEXT BOUNDARIES:

- Available context: session-close output files, validation report (if available)
- Focus: Assessment and proposal only — no modifications
- Limits: Do not apply changes, only propose them
- Dependencies: Validation report from session-close validation, or user-identified issues that drive this edit

## EDIT ASSESSMENT SEQUENCE

### 1. Load Current Output

Read the session-close output files that need editing. If a validation report exists, load it to understand what failed.

---

### 2. Identify Required Changes

For each issue found:
- **File**: Which file needs changing
- **Location**: Specific section or line
- **Current**: What exists now
- **Proposed**: What it should be changed to
- **Reason**: Why this change is needed

---

### 3. Present Change Proposal

**Proposed Changes for Session Close:**

| # | File | Change | Reason |
|---|------|--------|--------|
| 1 | [file] | [current → proposed] | [reason] |

**Select an Option:** [C] Approve and Continue to Apply [R] Revise Proposals [X] Cancel Edit

#### Menu Handling Logic:

- IF C: Record approved changes, then read fully and follow: `{nextStepFile}`
- IF R: Revise proposals based on user feedback, redisplay menu
- IF X: Cancel edit mode, return to calling workflow
- IF user asks questions: Answer and redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to apply step when user selects 'C'

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN user approves the change proposals will you then read fully and follow: `{nextStepFile}` to begin applying edits.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Current state assessed completely
- All proposed changes documented with reasoning
- User reviewed and approved proposals
- No files modified during assessment

### ❌ SYSTEM FAILURE:

- Applying changes without user approval
- Proposing changes without understanding current state
- Skipping the approval gate
- Modifying files during assessment step

**Master Rule:** Understand before editing. Propose before applying. User approves all changes.
