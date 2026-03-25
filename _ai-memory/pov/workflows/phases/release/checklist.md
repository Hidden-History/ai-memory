---
name: 'phases-release-checklist'
description: 'Quality gate rubric for phases-release'
---

# Phases Release — Validation Checklist

## Pre-Execution Checks

- [ ] Integration phase is complete (user approval recorded)
- [ ] All milestone story files are accessible

## Step Completion Checks

### Step 1: Compile Release (step-01-compile-release)
- [ ] All stories read in full (not summarized from memory)
- [ ] Changes to existing behavior explicitly identified
- [ ] Database and configuration changes captured
- [ ] PRD coverage documented

### Step 2: Create Changelog (step-02-create-changelog)
- [ ] SM dispatched through agent-dispatch workflow
- [ ] Keep a Changelog format followed
- [ ] Release notes in plain language (not technical jargon)
- [ ] Every entry traces to a story

### Step 3: Deployment Checklist (step-03-deployment-checklist)
- [ ] Checklist is specific to this release (not a generic guide)
- [ ] Database steps account for all migrations
- [ ] Post-deployment verification is meaningful
- [ ] Rollback triggers are defined

### Step 4: Rollback Plan (step-04-rollback-plan)
- [ ] Rollback steps are specific (not "revert the deployment")
- [ ] Irreversible changes explicitly flagged
- [ ] Impact of rollback clearly stated
- [ ] Time estimate is realistic
- [ ] Rollback is actually achievable

### Step 5: DEV Deployment Verification (step-05-dev-deployment-verification)
- [ ] All five verification areas checked
- [ ] DEPLOYMENT READY confirmed
- [ ] Any issues found were fixed and re-verified
- [ ] DEV dispatched through agent-dispatch workflow

### Step 6: Parzival Reviews Artifacts (step-06-parzival-reviews-artifacts)
- [ ] All four artifact categories reviewed
- [ ] Issues corrected before user presentation
- [ ] Artifacts are consistent with each other
- [ ] Language is appropriate for audience

### Step 7: Approval Gate (step-07-approval-gate)
- [ ] Approval gate invoked with complete package
- [ ] Deployment authorization implications communicated
- [ ] Correct next workflow loaded
- [ ] Post-release monitoring noted

## Workflow-Level Checks

- [ ] CHANGELOG.md is complete and traces to stories
- [ ] Deployment checklist and rollback plan exist
- [ ] DEV confirmed DEPLOYMENT READY
- [ ] User explicitly signed off on release
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT create changelog from memory instead of story records
- [ ] Did NOT write deployment checklist as a generic guide
- [ ] Did NOT skip rollback plan because of confidence
- [ ] Did NOT mark irreversible changes as reversible
- [ ] Did NOT skip DEV deployment verification
- [ ] Did NOT proceed with NOT READY assessment
- [ ] Did NOT dispatch DEV directly instead of through agent-dispatch
- [ ] Did NOT present artifacts with known issues
- [ ] Did NOT deploy without explicit user sign-off
- [ ] Did NOT omit behavior changes from changelog
- [ ] Did NOT write release notes in technical language for stakeholders
- [ ] Did NOT omit irreversible changes from release communication
- [ ] Did NOT skip post-deployment verification reminder
- [ ] Did NOT: Not identifying database migrations
- [ ] Did NOT: Not checking PRD coverage
- [ ] Did NOT: Missing implemented features
- [ ] Did NOT: Including non-implemented features
- [ ] Did NOT: Missing database migration steps
- [ ] Did NOT: Vague verification ('check it works')
- [ ] Did NOT: Vague rollback steps
- [ ] Did NOT: No time estimate
- [ ] Did NOT: Aspirational rollback (not actually achievable)
- [ ] Did NOT: Not re-verifying after fixes
- [ ] Did NOT: Not reviewing all four categories
- [ ] Did NOT: Inconsistencies between artifacts

_Validated by: Parzival Quality Gate on {date}_
