---
name: 'step-02-architect-designs'
description: 'Activate Architect agent to design the complete technical architecture'
nextStepFile: './step-03-ux-design.md'
---

# Step 2: Architect Designs Architecture

## STEP GOAL
Activate the Architect agent to design the complete technical architecture. The track determines depth. Architecture must cover all eight required sections with rationale for every decision.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: PRD.md, goals.md, project-context.md, resolved pre-architecture questions
- Limits: Architect designs. Parzival reviews in a later step. Architect does NOT self-approve.

## MANDATORY SEQUENCE

### 1. Determine Depth by Track

**Quick Flow:** Architecture step is simplified. Architect reviews tech-spec and confirms feasibility. No full architecture document required. Skip to Step 6 (stories only, no epics).

**Standard Method:** Full architecture.md required. All eight sections.

**Enterprise:** Full architecture.md with additional security, compliance, and DevOps layers.

### 2. Prepare Architect Design Instruction
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

### 3. Dispatch Architect via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Architect with the prepared instruction.

### 4. Receive Architecture Draft
Receive architecture.md from the Architect. Do not present to user yet.

## CRITICAL STEP COMPLETION NOTE
ONLY when Architect has delivered the architecture draft, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Architect dispatched through agent-dispatch workflow
- All eight sections requested in instruction
- Track-appropriate depth specified
- Architecture draft received without presenting to user

### FAILURE:
- Presenting architecture to user before Parzival reviews
- Not specifying all eight required sections
- Gold-plating beyond project scale
- Architect dispatched directly instead of through agent-dispatch
