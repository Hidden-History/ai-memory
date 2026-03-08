---
name: 'step-05-review-findings'
description: 'Parzival reviews and classifies all findings from DEV review and Architect cohesion check'
nextStepFile: './step-06-fix-cycle.md'
---

# Step 5: Parzival Reviews All Findings

## STEP GOAL
Compile and classify all findings from DEV review and Architect cohesion check. Build a consolidated fix priority list. Apply special classification rules for integration findings.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: DEV integration review report, Architect cohesion check, test plan results
- Limits: Parzival classifies. No fixes yet -- classification first.

## MANDATORY SEQUENCE

### 1. Compile All Findings
Gather findings from:
- DEV integration review report (Step 3)
- Architect cohesion check (Step 4)
- Test plan pass/fail results

### 2. Classify Each Finding
For each finding, determine:
- LEGITIMATE / NON-ISSUE / UNCERTAIN
- Priority: CRITICAL / HIGH / MEDIUM / LOW
- Source: DEV review / Architect / test failure

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

### 4. Build Consolidated Fix Priority List

**CRITICAL:** Test plan failures + critical violations
**HIGH:** Architecture violations, security gaps, requirements gaps
**MEDIUM:** Standards violations, consistency issues, performance concerns
**LOW:** Architectural debt, non-blocking improvements

### 5. Determine If Fixes Are Needed
If zero legitimate issues across all sources: skip to step-07 (final verification).
If legitimate issues exist: proceed to fix cycle.

## CRITICAL STEP COMPLETION NOTE
If zero issues: skip step-06 and load step-07-final-verification.md.
If issues exist: load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All findings from both sources classified
- Integration-specific rules applied
- Consolidated fix list built with clear priorities
- Correct routing based on whether fixes are needed

### FAILURE:
- Missing findings from either source
- Not applying integration-specific classification rules
- Test failures not classified as CRITICAL
- Routing to fix cycle with zero issues
