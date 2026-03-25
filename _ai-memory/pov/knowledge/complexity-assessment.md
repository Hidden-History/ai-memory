---
name: Complexity Assessment
description: Reference for the 4 complexity levels Parzival uses to assess tasks and determine appropriate handling depth.
---

# Complexity Assessment

Before taking action on any task, Parzival assesses its complexity. Complexity determines the depth of analysis, the number of verification steps, and how many agents may need to be involved. This is not about time estimation -- it is about understanding the scope of risk and the rigor required.

## The Four Levels

### Straightforward

**Definition**: A task with a clear, well-defined scope that maps directly to existing patterns, standards, or documented requirements. There are no ambiguities, no competing approaches, and no architectural implications.

**Characteristics**:
- Single file or single module scope
- Existing patterns in the codebase already address this type of work
- Requirements are explicit and unambiguous in project files
- No architectural decisions needed
- No cross-module dependencies affected

**When to use**: Bug fixes with obvious root causes. Small feature additions that follow established patterns. Documentation updates. Configuration changes.

**Handling**: Standard agent dispatch with concise instructions. Single review pass is usually sufficient. Low risk of rework.

---

### Moderate

**Definition**: A task that is well-defined but touches multiple areas, requires some judgment calls, or involves patterns that need adaptation rather than direct replication.

**Characteristics**:
- Affects 2-3 files or modules
- Requires reading and cross-referencing multiple project files
- Some judgment required on implementation approach
- May need to verify that the approach fits existing architecture
- Minor risk of side effects in related modules

**When to use**: Feature additions that extend existing patterns to new areas. Refactoring tasks that affect multiple files. Bug fixes where the root cause spans multiple modules. Story implementations of moderate scope.

**Handling**: Agent dispatch with detailed instructions including citations from multiple project files. Explicit scope boundaries required. Review pass should check for cross-module side effects. May require a brief architecture check.

---

### Significant

**Definition**: A task that involves multiple modules, requires architectural awareness, and may need input from multiple agent types. There are non-obvious implications and the risk of cascading changes.

**Characteristics**:
- Affects 4+ files or modules
- Requires understanding of system-wide architectural patterns
- Multiple valid approaches exist with different trade-offs
- Risk of cascading changes to other parts of the system
- May require coordination between multiple agents (e.g., Architect + DEV)
- Some requirements may need clarification or interpretation

**When to use**: New features that introduce new patterns. Architectural changes that affect multiple modules. Integration work across feature boundaries. Migration tasks. Tasks where the story's acceptance criteria require interpretation.

**Handling**: Full architecture review before agent dispatch. Multiple agents may be involved sequentially. Instructions must include explicit trade-off analysis. Review pass should include cohesion check. User decision points likely at the beginning. Expect at least 2 review passes.

---

### Complex

**Definition**: A task that fundamentally affects the system architecture, involves high uncertainty, requires multiple agent types working in sequence, and has a high risk of unintended consequences. The full scope may not be clear at the start.

**Characteristics**:
- System-wide impact across many modules
- Architectural decisions that constrain future development
- High uncertainty -- multiple valid approaches with significant trade-offs
- Requires research protocol for at least some aspects
- Multiple agents required, possibly in multiple cycles
- Risk of discovering additional scope during implementation
- User decisions required at multiple points

**When to use**: Major architectural refactoring. New system capabilities that do not fit existing patterns. Performance overhauls. Security model changes. Tasks where the PRD requirements are broad and implementation strategy is not obvious.

**Handling**: Mandatory Architect review before any implementation. Full research protocol for uncertain areas. Break into sub-tasks before dispatching to DEV. Multiple review passes expected. User approval gates at each sub-task boundary. Document all decisions made during implementation.

---

## Assessment Process

When Parzival receives or identifies a task:

```
1. Read the task requirements in full
2. Identify all files and modules that will be affected
3. Check if existing patterns cover this type of work
4. Assess whether architectural decisions are needed
5. Determine if requirements are clear or need interpretation
6. Count the number of agents that will need to be involved
7. Assign the complexity level
8. Communicate the assessment to the user before proceeding
```

## Complexity Can Change

If a task initially assessed as Moderate reveals unexpected cross-module dependencies during implementation, Parzival re-assesses and escalates the complexity level. The assessment is a living evaluation, not a fixed label.

**Never downgrade complexity to save time. Upgrade complexity the moment evidence warrants it.**
