---
name: 'step-06-fix-cycle'
description: 'Fix all legitimate issues found during integration, re-run test plan after each fix pass'
nextStepFile: './step-07-final-verification.md'
---

# Step 6: Fix Cycle

**Progress: Step 6 of 8** — Next: Final Verification Pass

## STEP GOAL:

Fix all legitimate issues from the consolidated fix list. Integration fix cycles are more complex than story fix cycles because issues may span multiple components. Re-run the test plan after each fix pass.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Consolidated fix priority list, all project files
- Focus: Fix routing and test plan re-verification — iterate until all pass
- Limits: All legitimate issues must be resolved. No "fix it in the next sprint" for integration findings.
- Dependencies: Consolidated fix priority list from Step 5 is required

- Route fixes by type and re-run test plan after every fix pass until all issues resolved
**Behavioral Constraints:**
- FORBIDDEN to exit fix cycle with any test plan failures or unresolved legitimate issues
- Approach: Type-based routing, cross-component verification, iterative test plan re-run
- Architecture decision required before implementing architectural fixes

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Re-Run Test Plan After Each Fix Pass

After each round of fixes:
1. DEV re-runs affected test plan sections
2. DEV re-reviews fixed components
3. If test failures remain: continue fix cycle
4. If new issues surface from fixes: classify and add to fix list
5. Integration does not exit until ALL test plan items PASS

---

### 3. Repeat Until All Issues Resolved

Continue until:
- All legitimate issues from the consolidated list are fixed
- All test plan items pass
- No new issues remain from fixes

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all issues are resolved and all test plan items pass, will you then read fully and follow: `{nextStepFile}` to begin final verification.
