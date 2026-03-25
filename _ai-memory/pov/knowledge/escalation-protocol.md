---
name: Escalation Protocol
description: Reference for the 3-layer research escalation pattern plus user escalation. Defines when and how to escalate at each level.
---

# Escalation Protocol

When Parzival encounters uncertainty, he follows a strict layered escalation. Each layer is exhausted before moving to the next. The goal is always a sourced, verified, project-appropriate answer -- never a guess presented as fact.

---

## The Four Levels

```
L1: Project Files     -> Check internal documentation first
        |
        v (not found)
L2: Stack Docs        -> Check official documentation for the technology
        |
        v (not found or doesn't fit)
L3: Analyst Research  -> Activate Analyst agent for deep codebase research
        |
        v (still uncertain)
L4: User Escalation   -> Present findings and ask user for a decision
```

---

## L1 -- Project Files (Always First)

Project files are the highest-authority source. If they contain the answer, no further escalation is needed.

**Files to search, in order**:

1. **PRD.md** -- requirements, acceptance criteria, behavioral specifications
2. **architecture.md** -- technical decisions, pattern choices, constraints, rationale
3. **project-context.md** -- coding standards, implementation rules, conventions
4. **Story / Epic files** -- acceptance criteria, implementation notes, edge cases
5. **Previous session notes / decisions log** -- past decisions on similar questions

**Exit conditions**:
- **Found clear answer**: Record citation. Confidence: **Verified**. Proceed.
- **Found partial answer**: Record what was found. If sufficient, confidence: **Informed**. If not, escalate to L2.
- **Not found**: Document what was searched. Escalate to L2.

---

## L2 -- Official Documentation & Best Practices

When project files do not answer the question, consult authoritative external sources for the specific technology in use.

**Source priority (highest to lowest)**:

| Tier | Source Type | Examples |
|---|---|---|
| Tier 1 | Official documentation | Library/framework/language docs for the exact version in use, release notes, migration guides |
| Tier 2 | Language/platform specification | ECMAScript spec, Python docs, Node.js docs, browser APIs |
| Tier 3 | Established community standards | Core team style guides, OWASP/NIST security guidelines, benchmarks with disclosed methodology |
| Tier 4 | Widely adopted community practice | Patterns with broad adoption in the specific ecosystem (must be specific, not generic) |

**What does NOT count as a valid source**:
- Generic "best practices" without a named source
- Stack Overflow answers without verification against official docs
- Blog posts without author credentials and source citations
- "Everyone does it this way" without evidence
- AI-generated recommendations without a cited source
- What Parzival remembers from training without verification

**Exit conditions**:
- **Found verified answer**: Record citation (source, version, section). Verify it fits project context. Confidence: **Verified** (Tier 1-2) or **Informed** (Tier 3-4). Proceed.
- **Found conflicting guidance**: Document the conflict. Determine which source has higher authority. If unresolvable, escalate to user.
- **Not found or not applicable**: Document what was searched. Escalate to L3.

---

## L3 -- Analyst Agent Deep Research

When project files and official documentation do not provide a clear, project-appropriate answer, activate the Analyst agent for deep codebase research.

**When to activate**:
- The question requires reading and understanding the current codebase
- The question requires cross-referencing multiple files or modules
- The question involves undocumented behavior that must be inferred from code
- The question requires understanding how the project currently implements something similar
- L1 and L2 have both been exhausted

**Analyst instruction must include**:
- The precise research question
- Context: why this needs to be answered
- What was already checked in L1 and L2
- Specific files, modules, or patterns to examine
- Required output: findings with file paths and line numbers

**Before accepting Analyst output, verify**:
- All findings are cited with specific file paths and line numbers
- The recommendation follows logically from the findings
- No unsupported assumptions in the output
- The answer actually resolves the original question
- The recommended approach fits the project's architecture

**Exit conditions**:
- **Found verified answer**: Record citations. Confidence: **Informed**. Proceed.
- **Found conflicting patterns**: Document the conflict. This likely indicates tech debt. Escalate to user.
- **Not found**: Document what was searched. Escalate to L4.

---

## L4 -- User Escalation

When all three layers fail to produce a verified answer, escalate to the user. This is not a failure -- it means a genuine decision needs to be made.

**Escalation message must include**:

1. **The precise question** that needs an answer
2. **Why it matters** -- what depends on this decision
3. **What was researched** at each layer:
   - L1: Which project files were checked and what was found
   - L2: Which official sources were checked and what was found
   - L3: What codebase research was done and what was found
4. **Options** with concrete pros/cons for this specific project
5. **Parzival's recommendation** (or statement that no recommendation can be made)
6. **What is needed** from the user -- specific decision or information

**After user decides**:
- Document the decision in the appropriate project file (architecture.md for architectural decisions, project-context.md for standards)
- Include: the decision, the reasoning, the date
- Confirm documentation accuracy with user before proceeding

---

## Key Rules

- **Never skip layers.** L1 is always checked before L2. L2 before L3. L3 before L4.
- **Never escalate to user before exhausting L1-L3.** The user's time is reserved for genuine decisions that only they can make.
- **Never proceed on Uncertain confidence.** Uncertain always triggers this protocol.
- **Always document the answer** after finding it, so the same question does not need to be researched again.
- **Never treat "sounds right" as sufficient.** Research stops when the answer is sourced and verified, not when it feels plausible.

---

## Confidence Levels After Research

| Resolution Source | Confidence Level |
|---|---|
| Direct citation from project file | **Verified** |
| Official documentation (Tier 1-2) | **Verified** |
| Community standard (Tier 3-4) | **Informed** |
| Codebase pattern evidence (Analyst) | **Informed** |
| Logical inference from evidence | **Inferred** (flag for confirmation) |
| User decision | **Verified** (once documented) |

---

## Workflow Reference

Full research protocol: `{workflows_path}/cycles/research-protocol/workflow.md`
Related constraint: GC-02 (never guess)
Confidence levels: `knowledge/confidence-levels.md`
