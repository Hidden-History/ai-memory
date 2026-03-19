---
name: 'step-05-review-findings'
description: 'Parzival reviews and classifies all findings from DEV review and Architect cohesion check'
nextStepFile: './step-06-fix-cycle.md'
---

# Step 5: Parzival Reviews All Findings

**Progress: Step 5 of 8** — Next: Fix Cycle

## STEP GOAL:

Compile and classify all findings from DEV review and Architect cohesion check. Build a consolidated fix priority list. Apply special classification rules for integration findings.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Classify all findings from DEV and Architect — apply integration-specific classification rules
- 🚫 FORBIDDEN to begin fixing issues — classification comes before any fix action
- 💬 Approach: Systematic compilation and classification with priority assignment
- 📋 Test plan failures are automatically CRITICAL — do not downgrade

## EXECUTION PROTOCOLS:

- 🎯 Compile and classify all findings from both DEV report and Architect assessment
- 💾 Record consolidated fix priority list with priorities before routing
- 📖 Route to step-06 if issues exist, or skip to step-07 if zero issues
- 🚫 FORBIDDEN to begin fixes or proceed to fix cycle before classification is complete

## CONTEXT BOUNDARIES:

- Available context: DEV integration review report, Architect cohesion check, test plan results
- Focus: Classification and prioritization only — no fixes yet
- Limits: Parzival classifies. No fixes yet -- classification first.
- Dependencies: DEV review report (Step 3) and Architect cohesion check (Step 4) are required

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All findings from both sources classified
- Integration-specific rules applied
- Consolidated fix list built with clear priorities
- Correct routing based on whether fixes are needed

### ❌ SYSTEM FAILURE:

- Missing findings from either source
- Not applying integration-specific classification rules
- Test failures not classified as CRITICAL
- Routing to fix cycle with zero issues

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
