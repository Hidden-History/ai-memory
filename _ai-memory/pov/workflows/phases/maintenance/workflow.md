---
name: maintenance
description: 'Maintenance phase. Handles bugs, performance issues, security vulnerabilities, and minor enhancements after release. Reactive, tightly scoped.'
firstStep: './steps/step-01-triage-issue.md'
---

# Maintenance Phase

**Goal:** Handle everything that arises after production: bugs, performance degradations, security vulnerabilities, minor enhancements, and technical debt. Maintenance is reactive -- it responds to reality. Every maintenance task has a tight scope boundary and exits through the same review cycle. The standard does not change: zero legitimate issues before anything closes.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Step Processing Rules
1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute numbered sections in order
3. **WAIT FOR INPUT**: Halt at decision points and wait for user direction
4. **LOAD NEXT**: When directed, load and execute the next step file

### Critical Rules
- NEVER load multiple step files simultaneously
- ALWAYS read entire step file before execution
- NEVER skip steps unless explicitly optional
- ALWAYS follow exact instructions in step files

### Step Chain Overview
1. **step-01** -- Triage the issue
2. **step-02** -- Classify: maintenance fix or new feature?
3. **step-03** -- Analyst diagnosis (if needed)
4. **step-04** -- Create maintenance task
5. **step-05** -- DEV implements fix
6. **step-06** -- Review cycle
7. **step-07** -- Approval gate and route to next issue or exit

### Maintenance Anti-Patterns
These apply across ALL steps in this workflow:
- Never expand a bug fix into a refactor without user approval
- Never skip Analyst diagnosis for complex or unclear bugs
- Never treat a new feature request as a maintenance fix
- Never relax the review cycle because "it is just a small fix"
- Never fix multiple issues in one DEV dispatch
- Never approve a CRITICAL fix without a deployment plan
- Never skip updating CHANGELOG.md after fixes
- Never silently defer LOW priority issues indefinitely

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-MAINTENANCE
- Drop on exit: CONSTRAINTS-MAINTENANCE
- Exit to: WF-PLANNING (new feature) or WF-EXECUTION (hotfix) or remains in Maintenance

---

## OPERATIONAL PROTOCOLS

### Issue Queue Management
When multiple issues are reported:
1. Triage ALL reported issues before fixing any (unless CRITICAL)
2. CRITICAL issues take absolute priority — interrupt current work
3. HIGH issues are next in queue after current fix completes
4. MEDIUM and LOW are queued in order of report
5. Priority override: user can reorder the queue at any time
6. After each fix: check queue for next issue before going idle

### Health Monitoring Checklist
Run at session start when in maintenance phase:
- Check project-status.md for open_issues count
- Check CHANGELOG.md for pending unreleased fixes
- Check if any CRITICAL issues are in the queue
- Report health summary to user before proceeding

### Patch Release Escalation
If multiple maintenance fixes accumulate and warrant a patch release:
1. Group fixes into a patch release
2. Update CHANGELOG.md with all fixes
3. Create abbreviated deployment checklist (no new features — simpler)
4. Create rollback plan
5. Run abbreviated WF-RELEASE (skip story compilation — use fix list)
6. User approves patch release
7. Deploy

Abbreviated release is appropriate when:
- 3+ maintenance fixes are ready to deploy together
- A HIGH severity fix needs a structured deployment with rollback plan
- User requests a formal patch release

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
