---
name: 'step-02-architect-designs'
description: 'Define architecture requirements and dispatch Architect via agent-dispatch cycle'
nextStepFile: './step-03-ux-design.md'
---

# Step 2: Architect Designs Architecture

**Progress: Step 2 of 9** — Next: UX Design (If Applicable)

## STEP GOAL:

Define the architecture requirements and dispatch the Architect agent via the agent-dispatch cycle to design the complete technical architecture. The track determines depth. Architecture must cover all eight required sections with rationale for every decision.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: PRD.md, goals.md, project-context.md, resolved pre-architecture questions
- Focus: Dispatching Architect and receiving architecture draft — no user review yet
- Limits: Architect designs. Parzival reviews in a later step. Architect does NOT self-approve.
- Dependencies: Step 1 complete — all inputs verified and ambiguities resolved

- Focus on preparing the Architect instruction and dispatching via agent-dispatch cycle
**Behavioral Constraints:**
- FORBIDDEN to present architecture to user before Parzival reviews it (Step 4)
- Approach: Track-appropriate depth, all eight required sections, explicit rationale for every decision
- Architecture draft is received but held — do not present to user yet

## Sequence of Instructions (Do not deviate, skip, or optimize)

### Parzival's Responsibility (Layer 1)

#### 1. Determine Depth by Track

**Quick Flow:** Architecture step is simplified. Architect reviews tech-spec and confirms feasibility. No full architecture document required. Skip to Step 6 (`./step-06-pm-creates-epics-stories.md`) (stories only, no epics).

**Standard Method:** Full architecture.md required. All eight sections.

**Enterprise:** Full architecture.md with additional security, compliance, and DevOps layers.

---

#### 2. Prepare Architect Design Instruction

Architecture must cover eight sections:

1. **Technology stack** -- with rationale for every choice (language, runtime, framework, database, caching, third-party services)
2. **System design** -- component diagram, interactions, data flow, API design approach with rationale
3. **Data architecture** -- core data models, relationships, storage approach, access patterns
4. **Security architecture** -- authentication, authorization, data protection
5. **Infrastructure and deployment** -- hosting, deployment strategy, environments, CI/CD
6. **Code organization** -- directory structure, module boundaries, naming conventions
7. **Performance and scale** -- how architecture handles PRD scale requirements, bottleneck mitigation
8. **Technical constraints and trade-offs** -- what was considered and rejected with reasoning, known limitations

Requirements:
- Every tech decision must have explicit rationale
- Rationale must reference specific PRD requirements it satisfies
- No gold-plating -- architecture must fit project scale
- Existing tech (if any) must be respected unless explicitly changing

### Execution (via agent-dispatch cycle)

---

#### 3. Dispatch Architect via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Architect with the prepared instruction.

### Parzival's Responsibility (Layer 1)

---

#### 4. Receive Architecture Draft

Receive architecture.md from the Architect. Do not present to user yet.

## CRITICAL STEP COMPLETION NOTE

ONLY when Architect has delivered the architecture draft, load and read fully {nextStepFile}
