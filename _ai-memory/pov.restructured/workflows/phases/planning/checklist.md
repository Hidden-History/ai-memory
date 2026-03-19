---
name: 'phases-planning-checklist'
description: 'Quality gate rubric for phases-planning'
---

# Phases Planning — Validation Checklist

## Pre-Execution Checks

- [ ] Architecture phase is complete (user approval recorded)
- [ ] architecture.md and epics/stories exist

## Step Completion Checks

### Step 1: Review Project State (step-01-review-project-state)
- [ ] All relevant files read and assessed
- [ ] State summary is specific and quantified
- [ ] First sprint vs subsequent sprint correctly identified

### Step 2: Retrospective (step-02-retrospective)
- [ ] Retrospective ran for subsequent sprints (correctly skipped for first sprint)
- [ ] Velocity data is accurate
- [ ] Recommendations are specific and inform next sprint
- [ ] User acknowledged before planning begins

### Step 3: SM Sprint Planning (step-03-sm-sprint-planning)
- [ ] SM dispatched through agent-dispatch workflow
- [ ] Sprint mode (first vs subsequent) correctly determined
- [ ] Sprint scope is realistic given velocity (or conservative for first sprint)
- [ ] All selected stories have ready status

### Step 4: SM Creates Story Files (step-04-sm-creates-story-files)
- [ ] All sprint stories have complete story files
- [ ] All seven sections present in each story
- [ ] Technical context references architecture.md and project-context.md
- [ ] Acceptance criteria are specific and testable

### Step 5: Parzival Reviews Sprint (step-05-parzival-reviews-sprint)
- [ ] Sprint-status.yaml reviewed for coherence
- [ ] Every story file reviewed individually
- [ ] Implementation-ready test applied to each story
- [ ] Issues batched and corrected
- [ ] All stories pass before user presentation

### Step 6: User Review Approval (step-06-user-review-approval)
- [ ] Sprint presented with clear execution order
- [ ] All user feedback addressed
- [ ] Re-reviewed after changes
- [ ] User explicitly confirmed satisfaction

### Step 7: Approval Gate (step-07-approval-gate)
- [ ] Approval gate invoked with complete package
- [ ] First story clearly identified
- [ ] User explicitly approved before execution began
- [ ] Project status updated
- [ ] Clean handoff to WF-EXECUTION

## Workflow-Level Checks

- [ ] sprint-status.yaml exists and is coherent
- [ ] All story files pass implementation-ready test
- [ ] User approved sprint before execution began
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT skip state review and go directly to planning
- [ ] Did NOT skip retrospective without justification (subsequent sprints)
- [ ] Did NOT run retrospective for first sprint
- [ ] Did NOT dispatch SM directly instead of through agent-dispatch
- [ ] Did NOT plan more stories than velocity supports
- [ ] Did NOT include stories with unmet dependencies
- [ ] Did NOT present stories with known issues to user
- [ ] Did NOT accept vague acceptance criteria
- [ ] Did NOT create stories without architecture as input
- [ ] Did NOT start execution before sprint is approved
- [ ] Did NOT let stories leave implementation decisions to DEV
- [ ] Did NOT accept oversized stories that cannot be reviewed in one cycle
- [ ] Did NOT present sprint to user without reviewing story files first
- [ ] Did NOT: Not reading architecture.md for updates since last sprint
- [ ] Did NOT: Not identifying carryover stories
- [ ] Did NOT: Accepting vague recommendations
- [ ] Did NOT: Not presenting to user before planning
- [ ] Did NOT: Not distinguishing first sprint from subsequent
- [ ] Did NOT: Missing story files for sprint stories
- [ ] Did NOT: Incomplete sections in story files
- [ ] Did NOT: Not applying implementation-ready test
- [ ] Did NOT: Not reviewing sprint-status.yaml
- [ ] Did NOT: Not re-reviewing after changes
- [ ] Did NOT: Assuming user is satisfied without confirmation
- [ ] Did NOT: Not identifying first story

_Validated by: Parzival Quality Gate on {date}_
