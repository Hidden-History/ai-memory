---
name: 'step-v-01-validate-architecture'
description: 'Validation check: Verify architecture workflow output against checklist criteria'
---

# Validate Step 1: Validate Architecture Phase Output

## STEP GOAL:

Validate that the architecture workflow produced correct and complete output by checking against the workflow's checklist.md criteria. The architecture workflow produces an approved architecture document (architecture.md) with all technical decisions documented, plus epics and implementation-ready stories — confirmed as implementation-ready by the Architect.

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

- 🎯 Validate architecture output against checklist criteria
- 🚫 Do NOT fix issues — only report them

## EXECUTION PROTOCOLS:

- 🎯 Validate against checklist criteria only
- 💾 Record findings with PASS/FAIL/WARNING classification
- 📖 Present report to user before proceeding

## CONTEXT BOUNDARIES:

- Available context: architecture workflow output (architecture.md, epics, stories) and checklist.md
- Focus: Validation only — no corrections
- Limits: Do not fix issues, only report them
- Dependencies: architecture create mode (steps-c/) must be complete; architecture.md, epics, and stories must exist with user approval

## VALIDATION SEQUENCE

### 1. Load Checklist

Read `../checklist.md` to obtain the validation criteria for this workflow.

---

### 2. Load Workflow Output

> **Note:** Step 2 identifies what artifacts to read. Step 3 defines what to check. The checklist is authoritative — Step 2 is guidance for locating artifacts, not an exhaustive validation list.

Identify and read the output artifacts produced by the architecture workflow's create mode (steps-c/). This includes:
- The architecture.md document with all stack, pattern, data model, API, and infrastructure decisions
- Epics and stories documents
- Evidence of Parzival's architecture review
- Implementation readiness check result from Architect
- Evidence of PRD alignment (no architecture decisions violating PRD constraints)
- User approval record

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
