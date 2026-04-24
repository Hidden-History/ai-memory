---
name: 'step-03-pm-creates-prd'
description: 'Define PRD requirements and dispatch PM via agent-dispatch cycle'
nextStepFile: './step-04-parzival-reviews-prd.md'
---

# Step 3: PM Creates PRD Draft

**Progress: Step 3 of 7** — Next: Parzival Reviews PRD Draft

## STEP GOAL:

Define the PRD structure requirements and dispatch the PM agent via the agent-dispatch cycle to create a complete Product Requirements Document (PRD.md) from the gathered inputs. The track determines the workflow depth.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: goals.md, Analyst research output (if from Step 2), any existing briefs/specs
- Focus: PM PRD creation and dispatch — Parzival receives the draft only
- Limits: PM creates the PRD. Parzival reviews it in the next step. PM does NOT approve its own work.
- Dependencies: Scenario classification from Step 1, Analyst research output (if Step 2 was executed)

- Focus on preparing PM instruction and dispatching via agent-dispatch cycle
**Behavioral Constraints:**
- FORBIDDEN to present PRD to user before Parzival reviews it
- Track-appropriate instruction: specify correct depth (Quick Flow / Standard / Enterprise)
- PM does NOT approve its own work — Parzival reviews in the next step

## Sequence of Instructions (Do not deviate, skip, or optimize)

### Parzival's Responsibility (Layer 1)

#### 1. Determine Workflow by Track

**Quick Flow track:**
- PM uses quick-spec workflow
- Output: tech-spec (not full PRD)

**Standard Method track:**
- PM uses PRD creation workflow
- Output: Full PRD.md

**Enterprise track:**
- PM uses PRD creation workflow
- Output: PRD.md with additional compliance/security sections

---

#### 2. Prepare PM PRD Creation Instruction

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

---

### Execution (via agent-dispatch cycle)

#### 3. Dispatch PM via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the PM with the prepared instruction.

---

### Parzival's Responsibility (Layer 1)

#### 4. Receive PRD Draft

Receive the completed PRD.md from the PM agent. Do not present to user yet -- Parzival reviews first.

## CRITICAL STEP COMPLETION NOTE

ONLY when the PM has delivered the PRD draft, load and read fully {nextStepFile}
