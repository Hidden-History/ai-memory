---
name: "verification-fix"
description: "Template for bug fix verification tracking pre-fix reproduction, root cause confirmation, and post-fix regression testing"
---

# Fix Verification: BUG-XXX — [Bug Title]
**Date**: [date]
**Bug Report**: {oversight_path}/bugs/BUG-XXX.md
**Fix Agent**: [agent name]
**Reviewer**: Parzival

---

## Pre-Fix Verification

### 1. Reproduce the Issue
- [ ] Follow reproduction steps from bug report
- [ ] Confirm issue exists in target environment
- [ ] Document actual behavior vs. expected behavior
- [ ] Capture evidence (logs, screenshots, error messages)

### 2. Confirm Root Cause
- [ ] Verify root cause analysis is accurate
- [ ] Identify all affected components
- [ ] Review related code/configuration
- [ ] Document any additional findings

### 3. Validate Fix Approach
- [ ] Review proposed solution against architecture.md
- [ ] Assess impact on other systems
- [ ] Identify potential side effects
- [ ] Confirm rollback strategy exists

---

> **STOP**: Do not dispatch fix agent until all pre-fix verification is complete.

---

## Post-Fix Verification

### 4. Functional Verification
- [ ] Apply the fix in test environment
- [ ] Reproduce original issue — verify it no longer occurs
- [ ] Test edge cases and boundary conditions
- [ ] Verify error handling works correctly

### 5. Regression Testing
- [ ] Run all relevant test suites
- [ ] Verify existing functionality still works
- [ ] Test integration points with other systems
- [ ] Check for performance impact

### 6. Code Review
- [ ] Review code changes for quality (via review cycle)
- [ ] Verify adherence to project-context.md standards
- [ ] Check for proper error handling
- [ ] Confirm documentation is updated

### 7. Deployment Verification
- [ ] Verify fix in staging/test environment
- [ ] Run smoke tests post-deployment
- [ ] Monitor logs for errors
- [ ] Check metrics/dashboards for anomalies

### 8. User Acceptance
- [ ] Notify original reporter of fix
- [ ] Request verification from stakeholders
- [ ] Document sign-off

### 9. Sign-Off
- [ ] All pre-fix checks passed
- [ ] All post-fix checks passed
- [ ] No regressions introduced
- [ ] Original reporter (or stakeholder) confirms resolution
- [ ] Prevention measures documented
- [ ] Documentation updated
- [ ] Bug status can advance to Verified

---

## Cross-References
- GC-05: Four-source verification
- GC-12: Loop until zero legitimate issues
- GC-16: Bug tracking protocol
- Bug status workflow: `knowledge/bug-status-workflow.md`
- Review cycle: `{workflows_path}/cycles/review-cycle/workflow.md`
