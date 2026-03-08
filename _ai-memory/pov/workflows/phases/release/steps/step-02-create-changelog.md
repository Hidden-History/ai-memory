---
name: 'step-02-create-changelog'
description: 'Activate SM to create release notes and update CHANGELOG.md'
nextStepFile: './step-03-deployment-checklist.md'
---

# Step 2: SM Creates Release Notes and Changelog

## STEP GOAL
Activate the SM agent to create release notes and update CHANGELOG.md. Every changelog entry must trace to a completed story. Nothing implemented is omitted. Nothing not implemented is included.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Release summary from Step 1, completed story files, PRD.md, existing CHANGELOG.md
- Limits: SM creates. Parzival reviews in Step 6.

## MANDATORY SEQUENCE

### 1. Prepare Changelog Instruction
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

### 2. Dispatch SM via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the SM.

### 3. Receive Changelog and Release Notes
Receive CHANGELOG.md and release notes. Parzival reviews in Step 6.

## CRITICAL STEP COMPLETION NOTE
ONLY when changelog and release notes are received, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- SM dispatched through agent-dispatch workflow
- Keep a Changelog format followed
- Release notes in plain language
- Every entry traces to a story

### FAILURE:
- Changelog created from memory
- Technical jargon in release notes
- Missing implemented features
- Including non-implemented features
