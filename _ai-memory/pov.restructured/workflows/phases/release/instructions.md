---
name: 'phases-release-instructions'
description: 'Release phase: compile changelog, deployment checklist, rollback plan, verification, final approval'
---

# phases-release — Instructions

## Prerequisites

- Sprint integration has been approved through the integration phase
- All sprint stories are in a complete state
- Release artifacts (changelog template, deployment checklist) are accessible
- Dev agent (`bmad-bmm-dev`) is available for deployment verification

## Workflow Overview

The release phase prepares and executes the delivery of completed sprint work. It compiles the release package, creates the changelog, produces deployment and rollback plans, and dispatches the Dev agent to verify the deployment. Parzival reviews all release artifacts before the user approves.

The workflow exits through the approval gate, which is the final gate before work is considered released. No release occurs without user approval of the complete release package.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-compile-release.md` | Compile all sprint stories, changes, and artifacts into a release package |
| 2 | `step-02-create-changelog.md` | Create the changelog entry documenting all changes in this release |
| 3 | `step-03-deployment-checklist.md` | Generate the deployment checklist with all required steps and verification criteria |
| 4 | `step-04-rollback-plan.md` | Document the rollback plan: trigger conditions, steps, and recovery verification |
| 5 | `step-05-dev-deployment-verification.md` | Dispatch Dev agent to verify deployment scripts and configurations are correct |
| 6 | `step-06-parzival-reviews-artifacts.md` | Parzival reviews the full release package: changelog, checklist, rollback plan, and verification results |
| 7 | `step-07-approval-gate.md` | Run approval-gate cycle; confirm release is approved and ready to deploy |

## Key Decisions

- **Rollback plan is mandatory**: Step 4 is never skipped — every release must have a documented rollback path
- **Parzival review scope**: Step 6 checks the complete release package, not individual artifacts
- **Deployment authority**: Approval gate requires explicit user approval; Parzival cannot self-approve a release

## Outputs

- Release package (compiled sprint work)
- Changelog entry
- Deployment checklist
- Rollback plan
- Dev deployment verification results
- Release approval logged in tracking

## Exit Conditions

The workflow exits when:
- The full release package has been approved through the approval gate
- Release status is updated in tracking
