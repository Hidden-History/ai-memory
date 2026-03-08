---
name: 'step-03-pm-creates-prd'
description: 'Activate PM agent to create the Product Requirements Document from gathered inputs'
nextStepFile: './step-04-parzival-reviews-prd.md'
---

# Step 3: PM Creates PRD Draft

## STEP GOAL
Activate the PM agent to create a complete Product Requirements Document (PRD.md) from the gathered inputs. The track determines the workflow depth.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: goals.md, Analyst research output (if from Step 2), any existing briefs/specs
- Limits: PM creates the PRD. Parzival reviews it in the next step. PM does NOT approve its own work.

## MANDATORY SEQUENCE

### 1. Determine Workflow by Track

**Quick Flow track:**
- PM uses quick-spec workflow
- Output: tech-spec (not full PRD)

**Standard Method track:**
- PM uses PRD creation workflow
- Output: Full PRD.md

**Enterprise track:**
- PM uses PRD creation workflow
- Output: PRD.md with additional compliance/security sections

### 2. Prepare PM PRD Creation Instruction
Provide the PM with all necessary inputs:

- goals.md content
- Analyst research findings (if from Step 2)
- Any existing briefs or specs provided by user

PRD must include:
1. Project overview and primary goal
2. User personas / user types
3. Functional requirements -- complete feature list with acceptance criteria and priority (Must Have / Should Have / Nice to Have)
4. Non-functional requirements -- performance, scale, security, compliance
5. Integration requirements -- external systems, APIs, data sources
6. Out of scope -- explicit list
7. Success metrics -- how success is measured
8. Open questions -- anything still unresolved

Requirements must be:
- Specific enough to implement without ambiguity
- Verifiable -- can be confirmed done or not done
- Implementation-free -- WHAT, not HOW
- Non-contradictory

### 3. Dispatch PM via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the PM with the prepared instruction.

### 4. Receive PRD Draft
Receive the completed PRD.md from the PM agent. Do not present to user yet -- Parzival reviews first.

## CRITICAL STEP COMPLETION NOTE
ONLY when the PM has delivered the PRD draft, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- PM dispatched through agent-dispatch workflow
- All required PRD sections were requested in the instruction
- Track-appropriate depth was specified
- PRD draft received without presenting to user

### FAILURE:
- Presenting PRD to user before Parzival reviews
- Not specifying all required PRD sections
- Using wrong track workflow
- PM dispatched directly instead of through agent-dispatch
