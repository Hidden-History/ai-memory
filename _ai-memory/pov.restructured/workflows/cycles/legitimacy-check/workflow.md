---
name: legitimacy-check
description: 'Issue triage and classification. Every issue surfaced during review, audit, or maintenance is classified as LEGITIMATE, NON-ISSUE, or UNCERTAIN before any action is taken.'
firstStep: './steps-c/step-01-read-issue.md'
---

# Legitimacy Check

**Goal:** Classify every issue surfaced during a code review, audit, or maintenance report into LEGITIMATE, NON-ISSUE, or UNCERTAIN before any action is taken — no issue is skipped, no issue is assumed.

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

### Classification Error Prevention
These rules apply across ALL steps:

| Error | Prevention |
|---|---|
| Classifying before fully reading the issue | Always complete Step 1 before Step 3 |
| Classifying without checking project files | Always complete Step 2 before Step 3 |
| Treating opinion as legitimate issue | Check: which A criterion does this meet? If none, non-issue |
| Treating legitimate issue as non-issue due to age | Pre-existing does not exempt from legitimacy |
| Guessing when uncertain | Trigger WF-RESEARCH-PROTOCOL immediately |
| Deferring low-priority legitimate issues | All priorities fix in current cycle |
| Skipping classification for "obvious" issues | Every issue gets classified, no exceptions |
| Letting agent push back change classification without basis | Require project file citation for any reclassification |

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
