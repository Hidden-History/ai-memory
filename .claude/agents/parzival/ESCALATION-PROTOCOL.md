# Parzival Escalation Protocol

This is the universal escalation pattern for all BMAD agents when they encounter issues requiring project-specific knowledge.

---

## When to Escalate

Escalate to Parzival when you encounter:

| Situation | Example |
|-----------|---------|
| **Architectural decisions not in documentation** | "Should this use sync or async?" |
| **Constraint conflicts you cannot resolve** | "Python 3.10 required but library needs 3.11+" |
| **Pattern choices affecting multiple components** | "Which error handling pattern for this service?" |
| **Uncertainty about project conventions** | "What naming convention for these files?" |
| **Need to verify against project history** | "Was this approach tried before?" |
| **Missing context for decision** | "What's the performance requirement here?" |

---

## Escalation Format

When you hit a blocker requiring Parzival's input, **STOP** and output this block:

```
═══════════════════════════════════════════════════════════════════════
QUESTION FOR PARZIVAL
═══════════════════════════════════════════════════════════════════════

**Agent**: [Your agent name - e.g., code-reviewer, dev, architect]
**Task**: [What you're currently working on]
**Blocker**: [What you don't know / can't determine]
**Considered**: [Options you've ruled out and why]
**Need**: [Specific information required to proceed]

═══════════════════════════════════════════════════════════════════════
```

Then instruct the user:

> **Copy the question above and paste it into your Parzival terminal.**
> Parzival has full project context and can answer this.
> Return here with the response to continue.

---

## After Receiving Response

1. **Apply** Parzival's guidance to your current work
2. **Document** the decision if architecturally significant
3. **Resume** your work with the new information
4. **Reference** the decision in your output (e.g., "Per Parzival guidance...")

---

## Integration Instructions

### For POV Agents (Already Integrated)

The following agents include this protocol:
- `code-reviewer.md`
- `best-practices-researcher.md`
- `verify-implementation.md`

### For Other BMAD Agents

Add this section to your agent definition:

```markdown
## Escalation to Parzival

When you encounter an issue requiring project-specific knowledge you don't have:

1. **STOP** current work
2. **Generate** a question using this format:

═══════════════════════════════════════════════════════════════════════
QUESTION FOR PARZIVAL
═══════════════════════════════════════════════════════════════════════

**Agent**: [agent-name]
**Task**: [current task]
**Blocker**: [what you don't know]
**Considered**: [options ruled out]
**Need**: [specific information needed]

═══════════════════════════════════════════════════════════════════════

3. **Instruct** the user to copy and paste into Parzival terminal
4. **Wait** for user to return with Parzival's response
5. **Continue** work using Parzival's guidance
```

---

## Why This Pattern Works

- **Parzival has context** - It maintains session state, reads project docs, tracks decisions
- **Agents stay focused** - Each agent does its specialty without needing full project knowledge
- **User stays in control** - They see the question, can modify it, and route appropriately
- **No false assumptions** - Better to ask than guess wrong on project-specific details

---

*This protocol is part of the Parzival Oversight Module (POV)*
*See: ESCALATION-ADOPTION-GUIDE.md for upstream BMAD integration*
