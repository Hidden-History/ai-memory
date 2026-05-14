---
name: 'step-02-create-changelog'
description: 'Define changelog requirements and dispatch SM via agent-dispatch cycle'
nextStepFile: './step-03-deployment-checklist.md'
---

# Step 2: SM Creates Release Notes and Changelog

**Progress: Step 2 of 7** — Next: Build Deployment Checklist

## STEP GOAL:

Define the changelog requirements and dispatch the SM agent via the agent-dispatch cycle to create release notes and update CHANGELOG.md. Every changelog entry must trace to a completed story. Nothing implemented is omitted. Nothing not implemented is included.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Release summary from Step 1, completed story files, PRD.md, existing CHANGELOG.md
- Focus: Changelog and release notes creation — not deployment planning
- Limits: SM creates. Parzival reviews in Step 6.
- Dependencies: Release summary from Step 1

- Focus on scoping the SM dispatch and receiving accurate changelog and release notes
**Behavioral Constraints:**
- FORBIDDEN to include non-implemented features or omit implemented ones
- Approach: Every changelog entry traces to a completed story
- Breaking changes must be prominently flagged

## Sequence of Instructions (Do not deviate, skip, or optimize)

### Parzival's Responsibility (Layer 1)

#### 1. Prepare Changelog Instruction

SM must create or update CHANGELOG.md following Keep a Changelog convention:

- **Added:** New features (user-facing language)
- **Changed:** Changes to existing functionality
- **Fixed:** Bug fixes
- **Security:** Security improvements (if applicable)
- **Internal:** Non-user-facing improvements

SM must also create release notes:
- Written for user/stakeholder audience
- Plain language, no technical jargon
- Focus on what users can now do
- Note changes to existing workflows
- Note any required user actions

Accuracy requirements:
- Every item traces to a completed story
- Nothing not implemented is included
- Nothing implemented is omitted
- Existing behavior changes explicitly documented
- Breaking changes prominently flagged

---

### Execution (via agent-dispatch cycle)

#### 2. Dispatch SM via Agent Dispatch

Invoke `{workflows_path}/cycles/agent-dispatch/workflow.md` to activate the SM.

---

### Parzival's Responsibility (Layer 1)

#### 3. Receive Changelog and Release Notes

Receive CHANGELOG.md and release notes. Parzival reviews in Step 6.

## CRITICAL STEP COMPLETION NOTE

ONLY when changelog and release notes are received, load and read fully `{nextStepFile}`
