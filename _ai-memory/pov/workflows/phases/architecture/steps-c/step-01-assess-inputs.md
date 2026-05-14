---
name: 'step-01-assess-inputs'
description: 'Read and verify all inputs, resolve ambiguities that would force the Architect to guess'
nextStepFile: './step-02-architect-designs.md'
---

# Step 1: Assess Inputs and Prepare

**Progress: Step 1 of 9** — Next: Architect Designs Architecture

## STEP GOAL:

Read and verify all inputs before activating any agent. Resolve any ambiguities that would force the Architect to guess or assume.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: PRD.md, goals.md, project-context.md, Analyst audit findings (if from init-existing)
- Focus: Input verification only — do not activate any agents
- Limits: Do not activate any agents. Only read, verify, and resolve questions.
- Dependencies: Completed Discovery phase — PRD.md and goals.md must exist

- Focus on reading and verifying inputs — no agents activated
**Behavioral Constraints:**
- FORBIDDEN to activate any agent before all inputs are read and ambiguities resolved
- Approach: Systematic file review, resolve all ambiguities before proceeding
- If ambiguities exist, resolve from files first, then ask user before activating agents

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Read PRD.md in Full

Note all Must Have features, non-functional requirements, integration requirements, and scale expectations. Do not rely on Discovery summaries.

---

### 2. Read goals.md

Confirm constraints that affect architecture decisions. Deadline constraints affect complexity choices. Team size affects architectural patterns.

---

### 3. Read project-context.md

Note pre-existing technology preferences confirmed by user. Note constraints (hosting, compliance, existing systems).

---

### 4. Read Existing Codebase Context (if from init-existing)

If an existing codebase was audited:
- What tech is already in use?
- Cannot choose conflicting tech without strong justification
- Existing patterns must be respected unless changing them is in scope

---

### 5. Resolve Pre-Architecture Questions

Common questions to resolve before Architect begins:
- Is there an existing tech stack that must be continued?
- Are there hosting or infrastructure constraints?
- Are there compliance requirements that constrain tech choices?
- Is there a team with existing expertise in specific technologies?
- Are there budget constraints on licensing or services?
- Are there performance SLAs beyond what is in the PRD?

If unresolved: check project files first, then ask user. Document answers in goals.md or decisions.md.

## CRITICAL STEP COMPLETION NOTE

ONLY when all inputs are read and ambiguities resolved, load and read fully {nextStepFile}
