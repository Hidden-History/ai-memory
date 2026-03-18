---
name: Agent Selection Guide
description: Dynamic guide for how Parzival selects and dispatches agents based on task type, skill match, and available agents.
---

# Agent Selection Guide

Parzival selects agents based on the task at hand, not on a fixed roster. The agent team may vary by project, by module configuration, or by available capabilities. This guide defines the selection logic, common agent roles, and dispatch criteria.

---

## Selection Principles

1. **Task-driven, not agent-driven.** Identify what needs to be done first, then select the agent whose skills match.
2. **One task, one agent.** Each dispatch instruction targets a single agent for a single, well-scoped task. Do not send compound instructions.
3. **Sequential when dependent.** If Agent B needs Agent A's output, dispatch A first and review before dispatching B.
4. **Parallel when independent.** If two agents can work on unrelated tasks simultaneously, dispatch both.
5. **Never dispatch without context.** Every agent instruction includes project file citations, scope boundaries, and measurable completion criteria.

---

## Common Agent Roles

The following roles represent common capabilities. Actual agent names and activation methods depend on the project's module configuration and team setup.

### Analyst

**Strengths**: Research, brainstorming, codebase auditing, context generation, gap analysis.

**When to dispatch**:
- A new project needs its current state assessed
- A codebase has undocumented behavior that needs to be understood
- A research question requires deep investigation across multiple files
- Context for a decision is incomplete and needs to be gathered
- A legacy codebase needs an audit before onboarding

**Typical outputs**: Project context documents, research findings with citations, audit reports, gap analyses.

---

### PM (Product Manager)

**Strengths**: Requirements definition, PRD creation, epic and story decomposition, scope management, acceptance criteria.

**When to dispatch**:
- A new project needs a PRD written from discovery findings
- An existing PRD needs refinement or expansion
- Epics need to be broken down into stories
- Acceptance criteria need to be defined or clarified
- Scope needs to be formally documented

**Typical outputs**: PRD.md, epic definitions, story files with acceptance criteria, scope documents.

---

### Architect

**Strengths**: System design, technology selection rationale, pattern decisions, implementation readiness checks, cohesion reviews.

**When to dispatch**:
- Architecture decisions need to be made and documented
- A proposed implementation needs architectural review before starting
- Integration points between modules need to be defined
- A milestone's completed work needs a cohesion check
- Tech stack decisions need formal evaluation with trade-offs

**Typical outputs**: architecture.md, technology decision records, implementation readiness assessments, cohesion review reports.

---

### DEV (Developer)

**Strengths**: Code implementation, code review, bug fixing, test writing, refactoring.

**When to dispatch**:
- A story is ready for implementation
- Completed code needs a review pass
- Legitimate issues from a review need fixing
- A bug report needs investigation and resolution
- Refactoring is required based on architectural decisions

**Typical outputs**: Implemented code, review reports with issue classifications, test suites, refactored modules.

**Special note**: DEV is the most frequently dispatched agent. The dev-review loop (implement -> review -> fix -> re-review) is the core operating cycle in the Execution phase.

---

### SM (Scrum Master)

**Strengths**: Sprint planning, story creation, sprint tracking, retrospectives, velocity assessment.

**When to dispatch**:
- A new sprint needs to be planned and initialized
- Stories need to be created from epics and prioritized
- A sprint needs a status update or re-prioritization
- A release requires a retrospective
- Sprint velocity needs to be assessed for planning

**Typical outputs**: sprint-status.yaml, story files, sprint plans, retrospective summaries.

---

### UX Designer

**Strengths**: User experience design, wireframing, interaction patterns, accessibility review, user flow definition.

**When to dispatch**:
- A feature has user-facing interfaces that need design
- User flows need to be defined before implementation
- Accessibility requirements need to be assessed
- Interaction patterns need to be specified
- Visual design decisions need to be made

**Typical outputs**: Wireframes, user flow diagrams, interaction specifications, accessibility assessments.

**Special note**: Only dispatched when UI work is in scope. Many projects do not require UX design work.

---

### QA (Quality Assurance)

**Strengths**: Test planning, test execution, regression testing, integration testing, edge case identification.

**When to dispatch**:
- A milestone needs a full test plan
- Integration testing is required across modules
- Regression testing is needed after significant changes
- Edge cases need systematic identification
- A release needs a pre-release test pass

**Typical outputs**: Test plans, test results, regression reports, edge case inventories.

---

## Selection Matrix by Phase

| Phase | Primary Agents | Secondary Agents | Mode | Notes |
|---|---|---|---|---|
| Init | Analyst | -- | Planning | Assess current state, no implementation |
| Discovery | Analyst, PM | -- | Planning | Research first, then requirements |
| Architecture | Architect, PM | Analyst | Planning | Architect designs, PM decomposes into epics |
| Planning | SM | -- | Planning | Sprint initialization and story creation |
| Execution | DEV | Architect (if needed) | Execution | Core loop: implement, review, fix |
| Integration | DEV, Architect | QA | Execution | Full review pass + cohesion check |
| Release | SM | DEV (if fixes needed) | Execution | Retrospective + documentation |
| Maintenance | DEV | Analyst (if research needed) | Execution | Bug fix or improvement implementation |

---

## Dispatch Decision Tree

```
TASK IDENTIFIED
      |
What type of work is this?
      |
      |-- Research / Analysis    -> Analyst
      |-- Requirements / Scope   -> PM
      |-- Design / Architecture  -> Architect
      |-- Sprint / Planning      -> SM
      |-- Implementation / Fix   -> DEV
      |-- UI / UX Design         -> UX Designer
      |-- Testing / QA           -> QA
      |
Is the agent available in current team config?
      |
      |-- YES -> Dispatch with full instruction template
      +-- NO  -> Can Parzival handle this without implementation?
                  |-- YES -> Parzival handles (review, routing, coordination)
                  +-- NO  -> Notify user: required capability not available
```

---

## Agent Instruction Template

Every dispatch, regardless of agent, follows this format:

```
AGENT:        [agent name]
TASK:         [specific, unambiguous description]
CONTEXT:      [relevant background -- only what the agent needs]
REQUIREMENTS: [cite PRD.md section X, story file Y]
STANDARDS:    [cite architecture.md section Z, project-context.md]
SCOPE:        IN:  [what is included]
              OUT: [what is explicitly excluded]
OUTPUT:       [exactly what the agent should produce]
DONE WHEN:    [measurable, specific completion criteria]
```

**Never dispatch without all fields populated. Never send vague or ambiguous instructions.**

---

## Key Rules

- Parzival never does implementation work. If the task requires code, writing, or design output, an agent is dispatched.
- Parzival always reviews agent output before it reaches the user (GC-9).
- Parzival always presents summaries, not raw agent output (GC-10).
- Agent selection is dynamic. New agents can be added to the team configuration without changing this selection logic.
- When uncertain which agent to dispatch, assess the primary skill required by the task, not the phase you are in.

## Agent Selection Help

When uncertain about which agent to dispatch or which workflow to select, use `/bmad-help`. It can answer questions like:
- "Which agent should handle this task?"
- "What workflow should I use for creating a PRD?"
- "Should I dispatch Analyst before PM for this input?"
