---
name: 'session-start-checklist'
description: 'Quality gate rubric for session-start'
---

# Session Start — Validation Checklist

## Pre-Execution Checks

- [ ] Context files are available at the expected oversight path
- [ ] Session is not resuming mid-task without context loading

## Step Completion Checks

### Step 1: Load Context (step-01-load-context)
- [ ] All existing context files were read in full (not skimmed)
- [ ] Missing files were noted but did not block execution
- [ ] Context is organized by category for status compilation
- [ ] No files were modified during context load

### Step 1b: Parzival Bootstrap (step-01b-parzival-bootstrap)
- [ ] Bootstrap skill was invoked
- [ ] Results were incorporated or unavailability was noted
- [ ] Session was not blocked due to Qdrant failures
- [ ] File-based context from Step 1 was preserved

### Step 1c: Parzival Constraints (step-01c-parzival-constraints)
- [ ] Constraint skill was invoked
- [ ] Constraints were internalized or fallback was noted
- [ ] Active constraint set is documented
- [ ] Session was not blocked due to skill failures

### Step 2: Compile Status (step-02-compile-status)
- [ ] All loaded context is reflected in the status report
- [ ] Status fields are factual, not interpretive
- [ ] Anomalies are noted without recommendations
- [ ] Report is ready for presentation before presenting

### Step 3: Present and Wait (step-03-present-and-wait)
- [ ] Status report is presented in the defined format
- [ ] Anomalies are noted factually
- [ ] A clear recommendation with reasoning is provided
- [ ] User is asked for direction
- [ ] No work begins until user confirms

## Workflow-Level Checks

- [ ] All context files read before compiling status
- [ ] No SYSTEM FAILURE conditions triggered in any step
- [ ] User gave direction before any execution began

## Anti-Pattern Checks

- [ ] Did NOT skip context files that exist
- [ ] Did NOT fail to note missing files
- [ ] Did NOT modify any files during context load
- [ ] Did NOT proceed before reading all available files
- [ ] Did NOT block on bootstrap or constraint skill failures
- [ ] Did NOT retry Qdrant in a loop
- [ ] Did NOT skip bootstrap entirely without attempting
- [ ] Did NOT lose file-based context from Step 1
- [ ] Did NOT skip constraint loading entirely
- [ ] Did NOT override global constraints with phase constraints
- [ ] Did NOT omit loaded context from the status report
- [ ] Did NOT add recommendations or opinions to the compiled report
- [ ] Did NOT present the report before it is fully compiled
- [ ] Did NOT ignore anomalies between tracking files
- [ ] Did NOT present status without any recommendation or guidance
- [ ] Did NOT start executing tasks before the user gave direction
- [ ] Did NOT assume which option the user would choose
- [ ] Did NOT skip context loading because "nothing has changed"
- [ ] Did NOT say "What would you like to do?" without first explaining recommendation and why
- [ ] Did NOT provide a recommendation without checking project state first

_Validated by: Parzival Quality Gate on {date}_
