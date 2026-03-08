---
name: 'step-06-fix-cycle'
description: 'Fix all legitimate issues found during integration, re-run test plan after each fix pass'
nextStepFile: './step-07-final-verification.md'
---

# Step 6: Fix Cycle

## STEP GOAL
Fix all legitimate issues from the consolidated fix list. Integration fix cycles are more complex than story fix cycles because issues may span multiple components. Re-run the test plan after each fix pass.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Consolidated fix priority list, all project files
- Limits: All legitimate issues must be resolved. No "fix it in the next sprint" for integration findings.

## MANDATORY SEQUENCE

### 1. Route Fixes by Type

**Single-component fixes:**
- Route to DEV via {workflows_path}/cycles/agent-dispatch/workflow.md
- Standard correction instruction format
- Review the fixed component

**Cross-component fixes:**
- Route to DEV with full cross-component context
- Explicit guidance for each component involved
- After fix: verify BOTH components together (not in isolation)

**Fixes requiring architecture decisions:**
- STOP -- do not implement until architecture question is resolved
- Research protocol or user escalation
- Document new architectural decision in architecture.md
- Implement after decision is documented

**Test plan failures:**
- Identify root cause: code bug vs. test gap vs. missing implementation
- Code bug: fix via review cycle
- Test gap: add tests via targeted DEV instruction
- Missing implementation: return to WF-EXECUTION for that story

### 2. Re-Run Test Plan After Each Fix Pass
After each round of fixes:
1. DEV re-runs affected test plan sections
2. DEV re-reviews fixed components
3. If test failures remain: continue fix cycle
4. If new issues surface from fixes: classify and add to fix list
5. Integration does not exit until ALL test plan items PASS

### 3. Repeat Until All Issues Resolved
Continue until:
- All legitimate issues from the consolidated list are fixed
- All test plan items pass
- No new issues remain from fixes

## CRITICAL STEP COMPLETION NOTE
ONLY when all issues are resolved and all test plan items pass, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Fixes routed correctly by type
- Cross-component fixes verified together
- Architecture decisions documented before implementation
- Test plan re-run after every fix pass
- All test plan items pass at exit

### FAILURE:
- Implementing without resolving architecture questions
- Not re-running test plan after fixes
- Verifying cross-component fixes in isolation
- Exiting with test failures remaining
