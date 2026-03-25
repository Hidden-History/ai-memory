---
name: 'step-v-01-validate-init-new'
description: 'Validation check: Verify init-new workflow output against checklist criteria'
---

# Validate Step 1: Validate Init New Project Output

## STEP GOAL:

Validate that the init-new workflow produced correct and complete output by checking against the workflow's checklist.md criteria. The init-new workflow produces a verified project baseline from scratch: baseline files (project-status.md, goals.md, etc.), _ai-memory/ installation verified, Claude Code teams session structure established — with all content sourced from user input and user confirmation of readiness for Discovery.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER modify files during validation — read-only
- 📖 CRITICAL: Read the complete step file before taking any action
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Quality Gatekeeper in validation mode
- ✅ Validation is objective and evidence-based, not subjective
- ✅ Every finding must cite the source file and line
- ✅ Classify each finding: PASS / FAIL / WARNING

### Step-Specific Rules:

- 🎯 Validate init-new output against checklist criteria
- 🚫 Do NOT fix issues — only report them

## EXECUTION PROTOCOLS:

- 🎯 Validate against checklist criteria only
- 💾 Record findings with PASS/FAIL/WARNING classification
- 📖 Present report to user before proceeding

## CONTEXT BOUNDARIES:

- Available context: init-new workflow output (project-status.md, goals.md, and other baseline files; installation verification record; user approval) and checklist.md
- Focus: Validation only — no corrections
- Limits: Do not fix issues, only report them
- Dependencies: init-new create mode (steps-c/) must be complete; all baseline files must exist with user-sourced content

## VALIDATION SEQUENCE

### 1. Load Checklist

Read `../checklist.md` to obtain the validation criteria for this workflow.

---

### 2. Load Workflow Output

> **Note:** Step 2 identifies what artifacts to read. Step 3 defines what to check. The checklist is authoritative — Step 2 is guidance for locating artifacts, not an exhaustive validation list.

Identify and read the output artifacts produced by the init-new workflow's create mode (steps-c/). This includes:
- project-status.md (content sourced from user, no assumed content)
- goals.md (every line from user input, no generic content)
- Other baseline files created
- _ai-memory/ installation verification record (constraint IN-04)
- Claude Code teams session structure setup confirmation
- Baseline completeness verification checklist result
- User approval and confirmation of readiness to move to Discovery

---

### 3. Apply Validation Criteria

Check each criterion from the checklist against the actual output:

- [ ] [Criteria populated from checklist — but at runtime, the agent reads checklist.md dynamically]

For each criterion, record:
- **Check**: What was checked
- **Result**: PASS / FAIL / WARNING
- **Evidence**: File path and line, or reasoning

---

### 4. Present Validation Report

**Validation Results:**

| Check | Result | Evidence |
|-------|--------|----------|
| [Dynamic — populated at runtime] | | |

**Summary**: X PASS / Y FAIL / Z WARNING

**Select an Option:** [C] Continue (no FAILs — WARNINGs are informational) [E] Switch to Edit Mode (FAIL found)

#### Menu Handling Logic:

- IF C (all PASS): Workflow validated successfully. Return to calling workflow.
- IF E (FAIL found): Load steps-e/step-e-01-assess.md to begin edit mode.
- IF user asks questions: Answer and redisplay menu.

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed when user selects an option

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All checklist criteria evaluated
- Findings classified with evidence
- Report presented to user with clear summary
- No files modified during validation

### ❌ SYSTEM FAILURE:

- Skipping checklist criteria
- Modifying files during validation
- Reporting without evidence
- Proceeding without presenting report

**Master Rule:** Validate objectively. Report findings. Do not fix.
