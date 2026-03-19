---
name: 'init-new-checklist'
description: 'Quality gate rubric for init-new'
---

# Init New — Validation Checklist

## Pre-Execution Checks

- [ ] User has initiated a new project (no existing project files)
- [ ] Framework installation is accessible

## Step Completion Checks

### Step 1: Gather Project Info (step-01-gather-project-info)
- [ ] All required fields were requested in a single structured message
- [ ] User responses are recorded verbatim without interpretation
- [ ] Existing documents (if provided) were read before asking questions
- [ ] Only genuinely missing information was asked for
- [ ] Menu presented and user input handled correctly

### Step 2: Validate and Clarify (step-02-validate-and-clarify)
- [ ] Every required field has been validated for clarity and specificity
- [ ] Contradictions have been flagged and resolved
- [ ] Deferred items are explicitly marked as open
- [ ] User has explicitly confirmed the summary before proceeding
- [ ] No assumptions were made about user intent

### Step 3: Verify Installation (step-03-verify-installation)
- [ ] Every installation check was individually verified
- [ ] Missing items were specifically identified (not vague)
- [ ] Verification completed before any project files are created
- [ ] Track-appropriate configuration is confirmed

### Step 4: Create Baseline Files (step-04-create-baseline-files)
- [ ] All four files created with correct content
- [ ] Every field traces to user-confirmed input
- [ ] TBD items are clearly marked
- [ ] No assumptions or generic content in any file
- [ ] Open items from Step 2 are reflected in goals.md

### Step 5: Establish Teams (step-05-establish-teams)
- [ ] Agent dispatch capability is verified as available
- [ ] Agent dispatch workflow accessibility is confirmed
- [ ] No agents were prematurely activated
- [ ] Configuration is recorded for subsequent workflows

### Step 6: Verify Baseline (step-06-verify-baseline)
- [ ] Every verification item was individually checked
- [ ] All files are consistent with each other
- [ ] All content traces to user-confirmed input
- [ ] No assumptions are being carried forward
- [ ] Any issues found were fixed before proceeding
- [ ] Best practices research completed for confirmed tech stack

### Step 7: Present and Approve (step-07-present-and-approve)
- [ ] Complete approval package presented with all required sections
- [ ] Approval gate was invoked (not bypassed)
- [ ] User explicitly approved before any Discovery work began
- [ ] Project status updated accurately on approval
- [ ] Clean handoff to WF-DISCOVERY

## Workflow-Level Checks

- [ ] All four baseline files exist with correct content
- [ ] Installation verified before file creation
- [ ] User approved exit to Discovery phase
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT ask questions piecemeal across multiple exchanges
- [ ] Did NOT pre-fill any fields with assumptions
- [ ] Did NOT ask for information already provided in an existing document
- [ ] Did NOT proceed without receiving user response
- [ ] Did NOT proceed without user selecting 'C' (Continue) at each step
- [ ] Did NOT proceed without explicit user confirmation at Step 2
- [ ] Did NOT fill gaps with guesses instead of asking
- [ ] Did NOT ignore contradictions in provided information
- [ ] Did NOT skip installation verification
- [ ] Did NOT create project files before installation is verified
- [ ] Did NOT create files with assumed content
- [ ] Did NOT fill goals.md with generic placeholder text
- [ ] Did NOT mark TBD items unclearly in project-context.md
- [ ] Did NOT activate agents during initialization (too early)
- [ ] Did NOT skip best practices research for the tech stack
- [ ] Did NOT carry assumptions into the next step
- [ ] Did NOT begin Discovery without explicit user approval
- [ ] Did NOT bypass the approval gate
- [ ] Did NOT start Discovery before baseline is verified

_Validated by: Parzival Quality Gate on {date}_
