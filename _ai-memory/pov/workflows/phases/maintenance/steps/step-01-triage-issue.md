---
name: 'step-01-triage-issue'
description: 'Triage the incoming issue to determine urgency, scope, and severity before any action'
nextStepFile: './step-02-classify-issue.md'
---

# Step 1: Triage the Issue

## STEP GOAL
Every issue entering Maintenance is triaged before any action is taken. Triage determines urgency, scope, severity, and the correct workflow.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Issue report (from user, monitoring, or internal)
- Limits: Only triage. Do not begin diagnosis or fixing. Do not activate agents.

## MANDATORY SEQUENCE

### 1. Read Issue Report in Full
Answer:

**WHAT:**
- What exactly is the problem? (specific behavior, not "it is broken")
- What is the expected behavior?
- What is the actual behavior?
- Where does it occur? (which feature, user flow, environment)

**WHEN:**
- When did this start? (always / regression / intermittent)
- Is this a regression? (worked before, now broken)
- Is this affecting users right now? (production impact)

**SCOPE:**
- How many users are affected? (all / some / one)
- Is this blocking any critical user flow?
- Is there a workaround available?

### 2. Assign Severity

**CRITICAL:** Production down, data corruption, security breach, all users affected, no workaround

**HIGH:** Core feature broken, significant users affected, workaround exists but painful

**MEDIUM:** Non-core feature broken, limited users affected, workaround available

**LOW:** Minor issue, cosmetic, edge case, enhancement request

### 3. Produce Triage Summary
```
ISSUE: [brief title]
REPORTED BY: [user / monitoring / internal]
SEVERITY: [CRITICAL / HIGH / MEDIUM / LOW]
AFFECTED: [which feature, which users, production impact]
REGRESSION: [yes / no / unknown]
WORKAROUND: [exists / none]
INITIAL ASSESSMENT: [likely cause if known]
RECOMMENDED ACTION: [fix immediately / schedule fix / route to planning]
```

### 4. Handle Issue Queue
If multiple issues are present:
- Triage all before fixing any
- Order by severity: CRITICAL first
- Fix in order, one at a time
- CRITICAL arriving during lower-priority fix: pause and handle CRITICAL first

## CRITICAL STEP COMPLETION NOTE
ONLY when triage is complete, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Issue fully understood before any action
- Severity correctly assigned based on impact
- Triage summary produced with all fields
- Queue management applied if multiple issues

### FAILURE:
- Starting to fix before triaging
- Incorrect severity assignment
- Vague triage ("it is broken")
- Not managing queue priority
