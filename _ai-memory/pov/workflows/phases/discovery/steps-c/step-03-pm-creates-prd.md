---
name: 'step-03-pm-creates-prd'
description: 'Define PRD requirements and dispatch PM via agent-dispatch cycle'
nextStepFile: './step-04-parzival-reviews-prd.md'
---

# Step 3: PM Creates PRD Draft

**Progress: Step 3 of 7** — Next: Parzival Reviews PRD Draft

## STEP GOAL:

Define the PRD structure requirements and dispatch the PM agent via the agent-dispatch cycle to create a complete Product Requirements Document (PRD.md) from the gathered inputs. The track determines the workflow depth.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus on preparing PM instruction and dispatching via agent-dispatch cycle
- 🚫 FORBIDDEN to present PRD to user before Parzival reviews it
- 💬 Track-appropriate instruction: specify correct depth (Quick Flow / Standard / Enterprise)
- 📋 PM does NOT approve its own work — Parzival reviews in the next step

## EXECUTION PROTOCOLS:

- 🎯 Determine track and prepare complete PRD creation instruction for PM
- 💾 Receive PRD draft without presenting to user — Parzival reviews first
- 📖 Load next step only after PM has delivered complete PRD draft
- 🚫 FORBIDDEN to present PRD to user or skip Parzival review

## CONTEXT BOUNDARIES:

- Available context: goals.md, Analyst research output (if from Step 2), any existing briefs/specs
- Focus: PM PRD creation and dispatch — Parzival receives the draft only
- Limits: PM creates the PRD. Parzival reviews it in the next step. PM does NOT approve its own work.
- Dependencies: Scenario classification from Step 1, Analyst research output (if Step 2 was executed)

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- PM dispatched through agent-dispatch workflow
- All required PRD sections were requested in the instruction
- Track-appropriate depth was specified
- PRD draft received without presenting to user

### ❌ SYSTEM FAILURE:

- Presenting PRD to user before Parzival reviews
- Not specifying all required PRD sections
- Using wrong track workflow
- PM dispatched directly instead of through agent-dispatch

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
