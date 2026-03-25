---
name: 'session-blocker-checklist'
description: 'Quality gate rubric for session-blocker'
---

# Session Blocker — Validation Checklist

## Pre-Execution Checks

- [ ] Blocker is clearly described before analysis begins
- [ ] Blocker is distinct from a decision (use decision workflow for choices)

## Step Completion Checks

### Step 1: Capture Blocker (step-01-capture-blocker)
- [ ] Blocker description is specific and actionable
- [ ] Severity is assigned using the defined scale
- [ ] Impact is assessed with affected task IDs
- [ ] Past issues (oversight/bugs/ and blockers-log.md) were checked before analysis
- [ ] No analysis or resolution was attempted in this step

### Step 2: Analyze and Resolve (step-02-analyze-and-resolve)
- [ ] Root cause analysis includes confidence level
- [ ] At least 2 resolution options are presented
- [ ] Each option has pros, cons, and complexity
- [ ] Recommendation is supported by reasoning
- [ ] User makes the decision, not Parzival

### Step 3: Log Blocker (step-03-log-blocker)
- [ ] Blocker is logged with all required fields
- [ ] Entry accurately reflects the captured details and user's chosen resolution
- [ ] User is informed of the logged entry
- [ ] New patterns are flagged for the failure pattern library

## Workflow-Level Checks

- [ ] Blocker fully captured before analysis began
- [ ] User chose the resolution (Parzival recommended, did not decide)
- [ ] Blocker logged to blockers-log.md
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT accept vague blocker descriptions
- [ ] Did NOT skip severity assessment
- [ ] Did NOT skip prior-issues check (GC-14 requirement — check bugs/ and blockers-log.md)
- [ ] Did NOT attempt to solve the blocker before fully capturing it
- [ ] Did NOT provide only one resolution option
- [ ] Did NOT execute a resolution without user approval
- [ ] Did NOT present options without pros/cons analysis
- [ ] Did NOT give a recommendation without reasoning
- [ ] Did NOT skip root cause analysis
- [ ] Did NOT log a resolution the user did not choose
- [ ] Did NOT log incomplete or vague blocker information
- [ ] Did NOT skip logging because "the blocker will be resolved soon"
- [ ] Did NOT mark a blocker as resolved without user confirmation
- [ ] Did NOT fail to append to the blockers log file
- [ ] Did NOT skip the confirmation step

_Validated by: Parzival Quality Gate on {date}_
