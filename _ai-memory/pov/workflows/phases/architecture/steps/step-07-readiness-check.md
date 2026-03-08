---
name: 'step-07-readiness-check'
description: 'Architect runs implementation readiness check across PRD, architecture, and epics'
nextStepFile: './step-08-finalize.md'
---

# Step 7: Implementation Readiness Check

## STEP GOAL
After architecture and epics are complete, activate the Architect to run a readiness check. Validate that all planning documents are cohesive and implementation can begin without unresolved blockers.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: PRD.md, architecture.md, all epic files
- Limits: Architect checks cohesion across all three document sets. If NOT READY, gaps must be fixed before proceeding.

## MANDATORY SEQUENCE

### 1. Prepare Readiness Check Instruction
Architect must check:
- PRD requirements fully covered by epics and stories
- Architecture decisions sufficient for all story technical contexts
- No stories require decisions not made in architecture
- No contradictions between PRD, architecture, and stories
- Dependencies are sequenced correctly
- No implementation blockers that would stop a DEV agent

### 2. Dispatch Architect via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Architect. Provide PRD.md, architecture.md, and all epic files.

### 3. Receive Readiness Assessment
Architect returns: **READY** or **NOT READY** with specific gaps.

### 4. Handle NOT READY Result
If Architect returns NOT READY:
- Parzival reviews each gap
- Routes fixes to appropriate agent:
  - Gap in PRD coverage: PM updates epics/stories
  - Gap in architecture: Architect updates architecture.md
  - Contradiction between docs: determine correct version, update both
- Re-run readiness check after fixes
- Repeat until READY

### 5. Confirm READY Assessment
When Architect returns READY:
- Parzival independently verifies the assessment is plausible
- Confirm no obvious gaps were missed
- Record readiness confirmation

## CRITICAL STEP COMPLETION NOTE
ONLY when readiness check returns READY and Parzival confirms, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Readiness check covered all three document sets
- NOT READY gaps were individually addressed and re-checked
- READY assessment was verified by Parzival (not just accepted)
- All document sets are cohesive

### FAILURE:
- Skipping the readiness check
- Accepting NOT READY without fixing gaps
- Accepting READY without Parzival verification
- Leaving contradictions between documents
