---
name: 'step-01-assess-existing-inputs'
description: 'Assess all available inputs to determine whether Analyst research is needed before PRD creation'
nextStepFile: './step-02-analyst-research.md'
---

# Step 1: Assess What Already Exists

## STEP GOAL
Before activating any agent, Parzival reads all available inputs and determines the scenario: rich input exists (skip research), thin input (research needed), or existing codebase (document reality first).

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: goals.md, any existing product briefs, specs, prior PRD drafts, Analyst audit findings (if from init-existing)
- Limits: Do not activate any agents in this step. Only read and assess.

## MANDATORY SEQUENCE

### 1. Read goals.md
Assess:
- Is the primary goal clear and specific?
- Are success criteria measurable?
- Are constraints documented?
- Are open items flagged?

### 2. Read Any Existing Product Briefs or Specs
If the user has prior documentation:
- Is it specific enough to feed into PRD creation directly?
- Or does it need research to fill gaps?

### 3. Read Any Existing PRD (Partial or Outdated)
If a PRD draft exists:
- Is it current?
- What is valid? What needs updating?
- Do not start from scratch if usable material exists

### 4. Read Analyst Audit Findings
If from init-existing workflow:
- What did the audit reveal about existing functionality?
- Does existing code represent requirements that need documenting?

### 5. Determine Scenario

**SCENARIO A -- Rich input exists** (brief, spec, or partial PRD):
- Activate PM directly with existing material as input
- Analyst research may not be needed
- Skip step-02, proceed directly to step-03

**SCENARIO B -- Thin input** (goals.md only, minimal detail):
- Activate Analyst for research before PM begins PRD
- Research phase fills gaps before PRD drafting starts
- Proceed to step-02

**SCENARIO C -- Existing codebase** (from init-existing Branch B):
- Analyst must document what exists before PRD captures requirements
- PRD must reflect current reality, not idealized requirements
- Proceed to step-02

### 6. Record Scenario Decision
Document which scenario applies and why, including what input will be provided to the PM agent when PRD creation begins.

## CRITICAL STEP COMPLETION NOTE
If Scenario A: skip step-02 and load step-03-pm-creates-prd.md directly.
If Scenario B or C: load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All available inputs were read (not skimmed)
- Scenario classification is based on specific assessment of input quality
- Decision to skip or require research is justified
- No agents were activated prematurely

### FAILURE:
- Skipping input assessment and going straight to research
- Classifying as Scenario A when input is actually thin
- Activating agents before assessment is complete
