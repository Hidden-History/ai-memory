---
name: 'step-v-01-validate-cycles-approval-gate'
description: 'Validation check: Verify approval-gate workflow output against checklist criteria'
---

# Validate Step 1: Validate Approval Gate Output

## STEP GOAL:

Validate that the approval-gate workflow produced correct and complete output by checking against the workflow's checklist.md criteria. The approval-gate workflow produces an explicit user decision (Approve, Reject with feedback, or Hold) — reached after presenting a verified, reviewed, summarized work package written in Parzival's own words with project-status.md updated after the response.

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

- 🎯 Validate approval-gate output against checklist criteria
- 🚫 Do NOT fix issues — only report them

## EXECUTION PROTOCOLS:

- 🎯 Validate against checklist criteria only
- 💾 Record findings with PASS/FAIL/WARNING classification
- 📖 Present report to user before proceeding

## CONTEXT BOUNDARIES:

- Available context: approval-gate workflow output (work package summary, user decision, project-status.md update) and checklist.md
- Focus: Validation only — no corrections
- Limits: Do not fix issues, only report them
- Dependencies: approval-gate create mode (steps-c/) must be complete; user decision must be recorded and project-status.md updated

## VALIDATION SEQUENCE

### 1. Load Checklist

Read `../checklist.md` to obtain the validation criteria for this workflow.

---

### 2. Load Workflow Output

> **Note:** Step 2 identifies what artifacts to read. Step 3 defines what to check. The checklist is authoritative — Step 2 is guidance for locating artifacts, not an exhaustive validation list.

Identify and read the output artifacts produced by the approval-gate workflow's create mode (steps-c/). This includes:
- The work package summary (in Parzival's words, not raw agent output)
- Review statistics (passes, issues found, issues fixed)
- The recommended next step stated with specifics
- The user's explicit decision (Approve/Reject/Hold)
- Updated project-status.md after the decision
- Evidence that only one decision was presented (not stacked)

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
