---
name: session-team-prompt
description: 'Build agent team prompts (2-tier or 3-tier) for parallel work execution via Claude Code teams.'
status: deprecated
deprecatedBy: aim-parzival-team-builder skill (PLAN-017, 2026-03-10)
firstStep: './steps/step-01-preflight-and-tier-selection.md'
twoTierTemplate: '{project-root}/_ai-memory/pov/templates/team-prompt-2tier.template.md'
threeTierTemplate: '{project-root}/_ai-memory/pov/templates/team-prompt-3tier.template.md'
---

> **DEPRECATED** (2026-03-10 / PLAN-017): Converted to `aim-parzival-team-builder` skill.
> Use `.claude/skills/aim-parzival-team-builder/SKILL.md` instead.
> Step files preserved for reference. Do not invoke this workflow.

# Team Prompt Builder

**Goal:** Analyze work to be parallelized, design the appropriate team structure (2-tier or 3-tier), assemble a complete copy-pasteable prompt, and present it to the user for execution.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Step Processing Rules
1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute numbered sections in order
3. **WAIT FOR INPUT**: Halt at decision points and wait for user direction
4. **LOAD NEXT**: When directed, load and execute the next step file

### Critical Rules
- NEVER load multiple step files simultaneously
- ALWAYS read entire step file before execution
- NEVER skip steps unless explicitly optional
- ALWAYS follow exact instructions in step files

### Team Hierarchy Mental Model
- **Parzival** = General Contractor (designs the team, does not execute)
- **Lead** = Orchestrator (coordinates managers or workers)
- **Managers** = Foremen (3-tier only; each manages a domain of workers)
- **Workers** = Crew (do the actual implementation work)

### Tier Selection Guide

| Scenario | Tier | Reasoning |
|----------|------|-----------|
| Single task | Subagent (no team) | Overhead not justified |
| 2-6 parallel tasks, single review | 2-Tier | Simple coordination |
| 3+ domains, multi-task per domain, domain-level review | 3-Tier | Complex coordination |
| Investigation or debugging with competing theories | 2-Tier (Competing Hypotheses) | Agents debate and disprove |

### Step Chain Overview

1. **Step 01** — Pre-flight and tier selection (read project context, analyze work, confirm tier)
2. **Step 02** — Team composition design (coordination pattern, models, plan approval, roster, sizing)
3. **Step 03** — File ownership map (ownership, conflicts, cross-cutting concerns, contracts, design approval)
4. **Step 04** — Context block assembly (10-element manager blocks, 8-element worker blocks, quality gates)
5. **Step 05** — Prompt assembly (load template, two-stage assembly, lead instructions, placeholder scan)
6. **Step 06** — Pre-delivery review and present (23-item checklist, acceptance criteria, verification plan)

### Parallel Conflict Avoidance Strategies

Ranked by effectiveness (from multi-agent orchestration research):

1. **Git Worktree Isolation** (Highest) — Each worker gets independent filesystem copy
2. **Exclusive File Ownership** (High) — Enforced by Step 3 ownership map
3. **Directory Partitioning** (High) — Workers own directories, not individual files
4. **Interface Contracts** (Medium) — For workers producing compatible code
5. **Merge-on-Green** (Medium) — Code merges to main only when all tests pass

**AVOID**: File locking — collapsed 20 agents to throughput of 2-3 in production testing.

### Team Prompt Anti-Patterns
- Never force 3-tier hierarchy when 2-tier suffices
- Never allow file ownership overlap between agents at any level
- Never create teams without reading the codebase to verify boundaries
- Never send placeholders or TBD values in the final prompt
- Never skip the pre-delivery review checklist
- Never have Parzival execute the team directly (user pastes the prompt)
- Never let managers implement anything — they orchestrate workers only
- Never let managers communicate with each other directly — hub-and-spoke only through lead
- Never let the lead communicate directly with workers in 3-tier — managers own worker interactions
- Never skip the manager review cycle — every worker deliverable must be reviewed
- Never create managers for domains with only 1 task — use direct subagent instead
- Never embed more than 4 worker prompts in a single manager context — split into sequential batches if 5-6 tasks exist
- Never allow unbounded review loops — hard cap at 3 cycles, then escalate
- Never flood context downward — each tier compresses for the next

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
