---
name: 'cycles-legitimacy-check-checklist'
description: 'Quality gate rubric for cycles-legitimacy-check'
---

# Cycles Legitimacy Check — Validation Checklist

## Pre-Execution Checks

- [ ] Issue to classify is clearly described
- [ ] Project files (PRD, architecture, project-context, decisions) are accessible

## Step Completion Checks

### Step 1: Read Issue (step-01-read-issue)
- [ ] Every understanding checklist item is answered
- [ ] The specific problem is identified, not just summarized
- [ ] Location is precisely identified
- [ ] Current vs expected behavior is clear
- [ ] Origin (new vs pre-existing) is determined

### Step 2: Check Project Files (step-02-check-project-files)
- [ ] All four file categories checked in order
- [ ] Findings recorded with specific file and section citations
- [ ] Direct relevance to the specific issue identified where it exists

### Step 3: Classify Issue (step-03-classify-issue)
- [ ] Classification is one of exactly three values: LEGITIMATE, NON-ISSUE, UNCERTAIN
- [ ] Classification is grounded in specific criteria (A1-A8, B1-B4, or C1-C5)
- [ ] Classification is supported by project file citations from step-02
- [ ] Special cases are handled per documented rules

### Step 4: Record Classification (step-04-record-classification)
- [ ] Every field in the record is populated
- [ ] Classification matches the determination from step-03
- [ ] Basis includes specific criteria and project file citations
- [ ] Resolution action is clear and specific

### Step 5: Assign Priority (step-05-assign-priority)
- [ ] Priority is assigned from exactly one of: CRITICAL, HIGH, MEDIUM, LOW
- [ ] Priority assignment follows the defined criteria
- [ ] Pre-existing issues are prioritized based on impact, not age
- [ ] Classification record is updated with the priority
- [ ] Each issue in a batch is classified independently

## Workflow-Level Checks

- [ ] Classification is one of the three valid values
- [ ] Record is complete with all fields populated
- [ ] WF-RESEARCH-PROTOCOL triggered for UNCERTAIN classifications
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT proceed to classification without full understanding
- [ ] Did NOT skip checklist items
- [ ] Did NOT summarize instead of understanding the specific problem
- [ ] Did NOT fail to determine issue origin
- [ ] Did NOT skip project file checks
- [ ] Did NOT check files out of order
- [ ] Did NOT classify without completing project file review
- [ ] Did NOT record citations in vague form ("see architecture.md")
- [ ] Did NOT classify without criteria basis
- [ ] Did NOT treat opinion as a legitimate issue
- [ ] Did NOT treat a legitimate issue as non-issue due to age
- [ ] Did NOT guess when uncertain instead of triggering WF-RESEARCH-PROTOCOL
- [ ] Did NOT change classification based on agent preference without project file basis
- [ ] Did NOT omit project file citations for LEGITIMATE classifications
- [ ] Did NOT record incomplete classification (blank fields)
- [ ] Did NOT assign priority based on opinion rather than criteria
- [ ] Did NOT fail to update the classification record with priority
- [ ] Did NOT let one issue's classification influence another in batch processing
- [ ] Did NOT defer any legitimate issue regardless of priority

_Validated by: Parzival Quality Gate on {date}_
