# Parzival Escalation Adoption Guide

This guide explains how to integrate the Parzival Escalation Protocol into BMAD agents across all modules.

---

## Overview

The Parzival Escalation Protocol provides a universal pattern for BMAD agents to request project-specific guidance when they encounter blockers. Instead of guessing or making assumptions, agents generate a structured question that users copy to their Parzival session.

**Key Principle**: Agents should escalate rather than assume when project-specific knowledge is required.

---

## Which Agents Should Adopt This

### Already Integrated (POV Module)

| Agent | Status |
|-------|--------|
| `parzival` | N/A (receives escalations) |
| `code-reviewer` | ✅ Integrated |
| `best-practices-researcher` | ✅ Integrated |
| `verify-implementation` | ✅ Integrated |

### Recommended for Integration

#### BMM Module (Software Development)

| Agent | Priority | Reason |
|-------|----------|--------|
| `dev` | **HIGH** | Makes implementation decisions |
| `architect` | **HIGH** | Makes architectural decisions |
| `analyst` | MEDIUM | Requirements interpretation |
| `pm` | MEDIUM | Product decisions |
| `tea` | MEDIUM | Test strategy decisions |
| `sm` | LOW | Process decisions |
| `tech-writer` | LOW | Documentation decisions |
| `ux-designer` | LOW | Design decisions |
| `quick-flow-solo-dev` | **HIGH** | All-in-one, many decision points |

#### BMGD Module (Game Development)

| Agent | Priority | Reason |
|-------|----------|--------|
| `game-dev` | **HIGH** | Implementation decisions |
| `game-architect` | **HIGH** | Technical architecture |
| `game-designer` | MEDIUM | Design decisions |
| `game-qa` | MEDIUM | Test strategy |
| `game-scrum-master` | LOW | Process |
| `game-solo-dev` | **HIGH** | All-in-one |

#### CIS Module (Creative & Innovation)

| Agent | Priority | Reason |
|-------|----------|--------|
| All agents | LOW | Less project-specific technical context needed |

#### BMB Module (BMAD Builders)

| Agent | Priority | Reason |
|-------|----------|--------|
| `agent-builder` | MEDIUM | May need project conventions |
| `workflow-builder` | MEDIUM | May need project conventions |
| `module-builder` | LOW | Framework-level work |

---

## Integration Steps

### Step 1: Add the Escalation Section

Add this section to the agent's markdown file, typically after the main instructions and before examples:

```markdown
## Escalation to Parzival

When you encounter an issue requiring project-specific knowledge you don't have:

1. **STOP** current work
2. **Generate** a question using this format:

═══════════════════════════════════════════════════════════════════════
QUESTION FOR PARZIVAL
═══════════════════════════════════════════════════════════════════════

**Agent**: [your-agent-name]
**Task**: [what you're working on]
**Blocker**: [what you don't know / can't determine]
**Considered**: [options you've ruled out and why]
**Need**: [specific information required to proceed]

═══════════════════════════════════════════════════════════════════════

3. **Instruct** the user: "Copy this question and paste it into your Parzival terminal. Parzival has full project context and can answer this. Return with the response to continue."
4. **Wait** for the user to return with Parzival's response
5. **Continue** work using Parzival's guidance
```

### Step 2: Add Escalation Triggers

In the agent's decision-making sections, add explicit triggers. Example for `dev` agent:

```markdown
### When to Escalate (Not Guess)

Escalate to Parzival instead of guessing when:
- Choosing between architectural patterns not specified in docs
- Unsure which existing pattern to follow
- Constraint conflicts (e.g., version requirements)
- Performance vs. simplicity tradeoffs without clear guidance
- Security decisions without explicit requirements
- Integration approach with external services
```

### Step 3: Update Agent Behaviors

Add to the agent's "Always Do" or key behaviors:

```markdown
- **Escalate uncertainty** - When project-specific knowledge is needed, use the Parzival Escalation Protocol rather than making assumptions
```

---

## Example: Dev Agent Integration

Here's how the `dev` agent would look after integration:

```markdown
# Dev Agent

## Key Behaviors

### Always Do
- Follow existing patterns in the codebase
- Write tests for new functionality
- **Escalate uncertainty** - Use Parzival Escalation Protocol when project-specific knowledge is needed

### Never Do
- Guess at architectural decisions
- Assume conventions not documented
- Make security decisions without guidance

## Escalation to Parzival

When you encounter an issue requiring project-specific knowledge you don't have:

1. **STOP** current work
2. **Generate** a question using this format:

═══════════════════════════════════════════════════════════════════════
QUESTION FOR PARZIVAL
═══════════════════════════════════════════════════════════════════════

**Agent**: dev
**Task**: [what you're implementing]
**Blocker**: [what you don't know]
**Considered**: [options ruled out]
**Need**: [specific information needed]

═══════════════════════════════════════════════════════════════════════

3. **Instruct** the user to copy and paste into Parzival terminal
4. **Wait** for response
5. **Continue** with Parzival's guidance

### When to Escalate (Not Guess)

- Architectural pattern selection
- Integration approach decisions
- Performance vs. simplicity tradeoffs
- Security implementation choices
- Convention questions not in docs
```

---

## Testing the Integration

After adding the escalation pattern to an agent:

1. **Invoke the agent** on a task with ambiguous requirements
2. **Verify** the agent generates the escalation block correctly
3. **Check** the user instructions are clear
4. **Confirm** the agent waits appropriately

### Test Scenarios

| Scenario | Expected Behavior |
|----------|-------------------|
| Clear requirements in docs | Agent proceeds without escalation |
| Ambiguous architectural choice | Agent escalates with options considered |
| Constraint conflict | Agent escalates with conflict details |
| Missing convention | Agent escalates asking for guidance |

---

## Benefits of Adoption

| Benefit | Description |
|---------|-------------|
| **Reduced errors** | Fewer wrong assumptions in implementations |
| **Better decisions** | Parzival has project context agents lack |
| **User visibility** | Users see exactly what agents don't know |
| **Audit trail** | Escalations document decision points |
| **Faster resolution** | Clear format makes answering efficient |

---

## Upstream PR Template

When submitting a PR to add escalation to a BMAD agent:

```markdown
## Summary
Adds Parzival Escalation Protocol to [agent-name] agent

## Changes
- Added "Escalation to Parzival" section with standard format
- Added escalation triggers to decision points
- Added "Escalate uncertainty" to key behaviors

## Testing
- [ ] Agent generates escalation block on ambiguous input
- [ ] User instructions are clear
- [ ] Agent waits for response before continuing
- [ ] Agent applies Parzival guidance correctly

## References
- ESCALATION-PROTOCOL.md in parzival-module
- ESCALATION-ADOPTION-GUIDE.md for integration pattern
```

---

## Questions?

The Parzival Escalation Protocol is part of the Parzival Oversight Module (POV).

For issues or improvements, update:
- `pov/includes/ESCALATION-PROTOCOL.md` - The shared protocol
- `ESCALATION-ADOPTION-GUIDE.md` - This guide
- `pov/templates/oversight/PARZIVAL_AGENT_IMPROVEMENTS.md` - Track improvements

---

*Last updated: 2026-01-13*
