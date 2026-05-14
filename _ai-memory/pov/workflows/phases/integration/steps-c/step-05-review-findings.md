---
name: 'step-05-review-findings'
description: 'Parzival reviews and classifies all findings from DEV review and Architect cohesion check'
nextStepFile: './step-06-fix-cycle.md'
---

# Step 5: Parzival Reviews All Findings

**Progress: Step 5 of 8** — Next: Fix Cycle

## STEP GOAL:

Compile and classify all findings from DEV review and Architect cohesion check. Build a consolidated fix priority list. Apply special classification rules for integration findings.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: DEV integration review report, Architect cohesion check, test plan results
- Focus: Classification and prioritization only — no fixes yet
- Limits: Parzival classifies. No fixes yet -- classification first.
- Dependencies: DEV review report (Step 3) and Architect cohesion check (Step 4) are required

- Classify all findings from DEV and Architect — apply integration-specific classification rules
**Behavioral Constraints:**
- FORBIDDEN to begin fixing issues — classification comes before any fix action
- Approach: Systematic compilation and classification with priority assignment
- Test plan failures are automatically CRITICAL — do not downgrade

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Compile All Findings

Gather findings from:
- DEV integration review report (Step 3)
- Architect cohesion check (Step 4)
- Test plan pass/fail results

---

### 2. Classify Each Finding

For each finding, determine:
- LEGITIMATE / NON-ISSUE / UNCERTAIN
- Priority: CRITICAL / HIGH / MEDIUM / LOW
- Source: DEV review / Architect / test failure

---

### 3. Apply Integration-Specific Classification Rules

**Test plan failures are automatically CRITICAL:**
- Any FAIL = legitimate issue (bug)
- Not classified -- automatically CRITICAL
- Must be resolved before integration passes

**Architecture cohesion issues are HIGH minimum:**
- Violations found by Architect = Category A3 minimum
- If violation affects multiple components: elevate to CRITICAL

**Cross-feature consistency issues:**
- Inconsistent patterns across features = standards violation
- Priority based on impact scope

---

### 4. Build Consolidated Fix Priority List

**CRITICAL:** Test plan failures + critical violations
**HIGH:** Architecture violations, security gaps, requirements gaps
**MEDIUM:** Standards violations, consistency issues, performance concerns
**LOW:** Architectural debt, non-blocking improvements

---

### 5. Determine If Fixes Are Needed

If zero legitimate issues across all sources: skip to step-07 (final verification).
If legitimate issues exist: proceed to fix cycle.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all findings are classified and consolidated fix list is built, will you then read fully and follow: `{nextStepFile}` (if issues exist) or step-07-final-verification.md (if zero issues) to proceed.
