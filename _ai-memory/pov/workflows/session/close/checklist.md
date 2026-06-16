---
name: 'session-close-checklist'
description: 'Quality gate rubric for session-close'
---
> **Note**: This file is a BMAD module quality gate summary. The authoritative execution path is `workflow.md` → step files. If this checklist conflicts with step file content, the step files are canonical.

# Session Close — Validation Checklist

## Pre-Execution Checks

- [ ] Active tasks have been brought to a stable stopping point
- [ ] Closeout is intentional (not triggered mid-task)

## Step Completion Checks

### Step 1: Summarize Session (step-01-summarize-session)
- [ ] Every completed work item is cataloged
- [ ] Every decision, blocker, and issue is accounted for
- [ ] All modified files are listed
- [ ] Pending items are identified for the next step
- [ ] Learnings captured (or explicitly noted as none)
- [ ] Session index maintenance checked (sharded if SESSION_WORK_INDEX.md exceeds 80 lines)
- [ ] Executive summary accurately represents the session

### Step 2: Update Tracking (step-02-update-tracking)
- [ ] Task status changes are confirmed by the user before executing
- [ ] All unlogged decisions and blockers are added
- [ ] Decision log rotated if over cap; manifest updated in the same close
- [ ] Blockers log holds open items only + an accurate reconciliation banner
- [ ] project-status.md heartbeat overwritten in place (one datum, one home)
- [ ] User is asked about documentation updates
- [ ] Tracking files accurately reflect the session outcome

### Step 3: Create Handoff (step-03-create-handoff)
- [ ] Handoff document is created; non-applicable sections omitted (not padded)
- [ ] Unchanged sections are one-line pointers, not re-essays
- [ ] Handoff is within cap (≤60 lines / ≤8 KB)
- [ ] SESSION_WORK_INDEX is updated with a reference to the handoff
- [ ] Prior handoffs archived to `session-logs/archive/{YYYY-MM}/` + INDEX
- [ ] Handoff is verified after writing

### Step 4: Enforce Caps (step-04-enforce-caps)
- [ ] `aim-tracking-rotate --check` run against the oversight root
- [ ] Any over-cap file rotated (`--apply`) until `--check` reports PASS
- [ ] Closeout not advanced to save while any governed file is over cap

### Step 5: Save and Confirm (step-05-save-and-confirm)
- [ ] Qdrant save was attempted (does not block closeout if unavailable)
- [ ] Final confirmation includes accurate checklist
- [ ] User had opportunity to add final items
- [ ] Session ends cleanly with all tracking current

## Workflow-Level Checks

- [ ] Handoff document exists with all sections populated
- [ ] Tracking files are consistent and current
- [ ] User confirmed session close
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT end session without creating a handoff document
- [ ] Did NOT skip tracking file updates
- [ ] Did NOT block closeout because Qdrant is unavailable
- [ ] Did NOT retry Qdrant save in a loop
- [ ] Did NOT leave empty/placeholder handoff sections (omit non-applicable ones)
- [ ] Did NOT update task status without user confirmation
- [ ] Did NOT skip verifying the written handoff
- [ ] Did NOT pad non-applicable handoff sections with filler (omit them instead)
- [ ] Did NOT advance to save while a governed file was over cap
- [ ] Did NOT close without asking about pending decisions and documentation
- [ ] Did NOT miss completed work items in the summary
- [ ] Did NOT forget decisions or blockers that occurred during the session
- [ ] Did NOT let SESSION_WORK_INDEX.md exceed 80 lines without sharding
- [ ] Did NOT leave an incomplete file modification list
- [ ] Did NOT skip learning capture entirely
- [ ] Did NOT write a vague executive summary
- [ ] Did NOT leave tracking files in an inconsistent state
- [ ] Did NOT present incomplete checklist at final confirmation
- [ ] Did NOT end session without user confirmation

_Validated by: Parzival Quality Gate on {date}_
