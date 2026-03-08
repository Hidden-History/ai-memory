---
name: 'step-02-design-team-composition'
description: 'Select coordination pattern, models, plan approval, delegate mode, roster, and task sizing'
nextStepFile: './step-03-build-ownership-map.md'
---

# Step 2: Design Team Composition

## STEP GOAL
Make all team composition decisions: coordination pattern, model selection, plan approval, delegate mode, role roster, and task sizing validation.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Confirmed tier selection and domains from Step 1, project files read in Step 1
- Limits: Composition only — do not build the file ownership map or write context blocks yet

## MANDATORY SEQUENCE

### 1. Select Coordination Pattern

Choose based on the work requirements:

| Pattern | When to Use |
|---------|-------------|
| Parallel Independent | Domains share no state. Lead checks in periodically, synthesizes at end |
| Parallel with Synthesis | Domains are independent but results need merging into a combined deliverable |
| Plan-then-Execute | A planning phase must complete before implementation begins |
| Contract-First Build | Domains depend on shared interfaces, APIs, schemas, or data flows |
| Competing Hypotheses | Investigation or debugging — agents debate via mailbox, disprove each other |

**If Contract-First Build is selected**: Step 3 sections 5-6 become MANDATORY.

### 2. Select Models

For each manager/worker, assign a model. This maps to the Agent tool's `model` parameter:

- **sonnet** (default): All managers and workers. Best cost/performance ratio for implementation, review, and coordination
- **opus**: Reserve for managers handling high-complexity orchestration requiring deep architectural reasoning, or workers doing novel architectural work where correctness is paramount
- **haiku**: Suitable for lightweight workers doing simple, well-defined tasks (formatting, linting, data extraction) where speed matters more than reasoning depth

### 3. Plan Approval Decision

**Require plan approval when ANY of these apply:**
- Changes are architectural (affect multiple systems)
- Changes are irreversible or hard to undo
- Workers modify production configuration
- Work involves security-sensitive code
- Complexity is significant or complex

**Skip plan approval when ALL of these apply:**
- Work is read-only (reviews, audits, research)
- Changes are isolated and easily reversible
- Only test/documentation files affected
- Complexity is straightforward

Record: Decision (Required / Not Required) + Reason. When required, the Agent tool spawn uses `mode: "plan"` and the lead approves plans via `SendMessage` (type: 'plan_approval_response').

### 4. Delegate Mode Decision

**3-tier teams**: Delegate mode is ALWAYS recommended. The lead should NOT implement anything — only coordinate managers.

**2-tier teams**: Recommend delegate mode when the user wants to act purely as coordinator and all work must happen through teammates.

Record: Decision (Recommended / Not Needed).

### 5. Design Roster

When assigning worker roles, reference the BMAD agent catalog for role expertise. Query `/bmad-help` or consult `_bmad/_config/bmad-help.csv` if unsure which agent matches a task domain.

**BMAD Agent Reference Map** (available agents for worker role assignment):

| Worker Domain | BMAD Agent | Key Expertise | Agent File |
|--------------|------------|---------------|------------|
| Backend/implementation | dev (Amelia) | TDD, story execution, strict test discipline | `_bmad/bmm/agents/dev.md` |
| Rapid dev/spec | quick-flow-solo-dev (Barry) | Quick spec + implementation, lean artifacts | `_bmad/bmm/agents/quick-flow-solo-dev.md` |
| Architecture | architect (Winston) | Distributed systems, API design, scalability | `_bmad/bmm/agents/architect.md` |
| QA/testing | qa (Quinn) | Test automation, API/E2E testing | `_bmad/bmm/agents/qa.md` |
| Requirements/analysis | analyst (Mary) | Market research, requirements, competitive analysis | `_bmad/bmm/agents/analyst.md` |
| Project coordination | pm (John) | PRD creation, epics/stories, stakeholder alignment | `_bmad/bmm/agents/pm.md` |
| Sprint management | sm (Bob) | Sprint planning, story prep, retrospectives | `_bmad/bmm/agents/sm.md` |
| UX design | ux-designer (Sally) | User experience, interaction design | `_bmad/bmm/agents/ux-designer.md` |
| Test architecture | tea (Murat) | Test design, framework setup, ATDD, coverage | `_bmad/tea/agents/tea.md` |
| Technical writing | tech-writer (Paige) | Documentation, DITA, mermaid diagrams | `_bmad/bmm/agents/tech-writer/tech-writer.md` |
| Code review | dev (Amelia) | Comprehensive multi-facet code review | `_bmad/bmm/agents/dev.md` |

**For 3-tier — define each manager:**

| # | Manager Domain | Responsibility | Worker Roles | File Set | Model |
|---|----------------|---------------|--------------|----------|-------|

**For each manager — define workers:**

| # | Worker Role (BMAD Agent) | Task | File Set | Model |
|---|-------------------------|------|----------|-------|

**For 2-tier — define each teammate:**

| # | Role Name | Responsibility | File Set | Model |
|---|-----------|---------------|----------|-------|

### 6. Task Sizing Check

Verify all sizing targets:

| Metric | Target | Rationale |
|--------|--------|-----------|
| Managers per team | 2-4 (max 6) | More than 6 = diminishing returns |
| Worker tasks per manager | 3-6 (embed max 4 prompts, batch remainder) | Enough to justify manager overhead |
| Minimum tasks per manager | 2 | If only 1 task, use direct subagent instead |
| Worker task scope | Fits one context window | Overflow = split into sequential sessions |
| 2-tier teammates | 2-6 | Practical coordination limit |
| Tasks per 2-tier teammate | 3-6 | Official Claude Code best practice |

**Critical insight**: If a task would overflow a single agent's context window, break it into multiple sequential worker sessions under the same manager. The manager keeps the overall checklist and spawns new sessions as each completes.

**IF any sizing target is violated**: Restructure before proceeding. Present options to user.

## CRITICAL STEP COMPLETION NOTE
ONLY when all composition decisions are made (pattern, models, plan approval, delegate mode, roster, sizing), load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Coordination pattern matches work requirements
- Model selection is justified for each role
- Plan approval decision is recorded with reason
- Delegate mode decision is recorded
- Roster is complete with all fields filled
- Task sizing targets are verified

### FAILURE:
- Skipping model selection (defaulting without stating it)
- Not recording plan approval decision
- Forcing delegate mode when inappropriate for 2-tier
- Leaving roster fields unfilled (file set, model)
- Proceeding with sizing violations unchecked
