# Agent Context Injection System

**Version**: 1.0
**Status**: Active
**Purpose**: Prevent agent drift and ensure consistent behavior across sessions

---

## Overview

The Agent Context Injection System allows you to inject persistent constraints and rules into agent sessions. This prevents "agent drift" - when agents gradually deviate from expected behavior across multiple sessions.

**Key Concept**: Instead of reminding agents of important rules every session, embed them as constraint files that get loaded automatically at session start.

---

## Why This Exists

### Problem: Agent Drift

Without persistent constraints:
1. ✗ Agent forgets project-specific rules between sessions
2. ✗ Must manually remind agent of constraints each time
3. ✗ Inconsistent behavior across sessions
4. ✗ Agent makes mistakes it previously learned to avoid

### Solution: Context Injection

With constraint files:
1. ✓ Rules persist across all sessions
2. ✓ Automatic loading at session start
3. ✓ Consistent agent behavior
4. ✓ Project-specific guidelines always followed

---

## How It Works

### 1. Create Constraint File

Create a constraint file for a specific agent:

```
agent-constraints/
└── parzival-coding-standards.md
```

### 2. Agent Loads at Session Start

When Parzival starts a session, it:
1. Checks `oversight/agent-constraints/` directory
2. Loads all `.md` files
3. Injects constraints into context
4. Applies rules to all subsequent actions

### 3. Agent Follows Constraints

Agent behavior is guided by loaded constraints throughout the session.

---

## When to Use

### Create Agent Constraints For:

1. **Project-Specific Rules**
   - Coding standards unique to this project
   - Naming conventions
   - File organization patterns

2. **Learned Lessons**
   - Mistakes that were made and shouldn't be repeated
   - Edge cases that tripped up agents before
   - Specific gotchas in your codebase

3. **Workflow Requirements**
   - Must-follow procedures
   - Review requirements
   - Testing standards

4. **Domain-Specific Knowledge**
   - Business logic rules
   - Regulatory requirements
   - Security requirements

5. **Tool Constraints**
   - How to use specific tools/libraries
   - Framework-specific patterns
   - API usage guidelines

### Don't Use For:

- ✗ General coding best practices (already in agent base knowledge)
- ✗ Language syntax (agent already knows)
- ✗ One-off instructions (use regular prompts instead)
- ✗ Constantly changing requirements (use task descriptions)

---

## File Structure

```
agent-constraints/
├── README.md                           # This file
├── CONSTRAINT_TEMPLATE.md              # Template for new constraints
├── parzival-quality-gates.md           # Example constraint
├── dev-testing-requirements.md         # Another constraint
└── architect-design-principles.md      # Agent-specific constraint
```

---

## Naming Convention

**Format**: `{agent-name}-{constraint-topic}.md`

**Examples**:
- `parzival-review-protocol.md` - Parzival's review requirements
- `dev-error-handling.md` - Dev agent error handling rules
- `architect-scalability.md` - Architect's scalability requirements
- `tea-test-coverage.md` - TEA's test coverage standards

**Guidelines**:
- Use lowercase with hyphens
- Start with agent name if agent-specific
- Be descriptive but concise
- Use `.md` extension

---

## Constraint Template

Use `CONSTRAINT_TEMPLATE.md` as starting point.

**Minimum Structure**:
```markdown
# {Constraint Title}

**Agent**: {Agent name or "All"}
**Type**: {Rule|Guideline|Standard|Process}
**Priority**: {Critical|High|Medium|Low}
**Status**: {Active|Draft|Deprecated}

## Rule

[Clear, actionable rule statement]

## Rationale

[Why this constraint exists]

## Examples

### ✓ Correct
[Good example]

### ✗ Incorrect
[Bad example]

## Exceptions

[When this rule doesn't apply]
```

---

## Example: Preventing Past Mistakes

### Scenario

Agent repeatedly created files without checking if they already existed, overwriting important configs.

### Solution

Create constraint file:

**File**: `agent-constraints/dev-file-safety.md`

```markdown
# File Creation Safety Protocol

**Agent**: dev, quick-flow-solo-dev
**Type**: Rule
**Priority**: Critical
**Status**: Active

## Rule

ALWAYS check if file exists before creating a new file using Write tool.
Use Read tool first to verify. If file exists, use Edit instead.

## Rationale

Multiple incidents where agents overwrote critical config files:
- BUG-042: Overwrote database config
- BUG-055: Lost environment variables
- BUG-071: Erased deployment settings

## Implementation

1. Before using Write tool: Call Read tool on path
2. If Read succeeds: Use Edit tool instead
3. If Read fails (file doesn't exist): Proceed with Write
4. For config files: ALWAYS use Edit, never Write

## Exceptions

- Deliberately creating new files in empty directories
- Generating files from templates
- User explicitly says "overwrite"
```

Now every dev session loads this rule - no more overwrites.

---

## Example: Project-Specific Standards

### Scenario

Project uses specific naming pattern for test files that agents kept forgetting.

### Solution

**File**: `agent-constraints/tea-test-naming.md`

```markdown
# Test File Naming Convention

**Agent**: tea
**Type**: Standard
**Priority**: High
**Status**: Active

## Rule

Test files MUST follow this pattern:
- Unit tests: `test_{component}_unit.py`
- Integration tests: `test_{component}_integration.py`
- E2E tests: `test_{workflow}_e2e.py`

## Rationale

Consistent naming allows CI/CD to run test categories separately:
- Unit: Runs on every commit (fast)
- Integration: Runs on PR (moderate)
- E2E: Runs before deploy (slow)

Pattern established in DEC-015.

## Examples

✓ Correct:
- `test_authentication_unit.py`
- `test_database_integration.py`
- `test_checkout_flow_e2e.py`

✗ Incorrect:
- `test_auth.py` (missing category)
- `authentication_test.py` (wrong order)
- `test_auth_e2e_final.py` (extra suffix)

## Exceptions

None. All test files must follow this pattern.
```

---

## Loading Constraints in Agents

### Method 1: Automatic (Recommended)

Add to agent activation steps:

```xml
<step n="X">
  Load all constraint files from {oversight_folder}/agent-constraints/
  Apply constraints with {agent-name} or "All" in Agent field
</step>
```

### Method 2: Manual

Load constraints explicitly when starting agent:

```markdown
Load and apply these constraints:
- oversight/agent-constraints/parzival-quality-gates.md
- oversight/agent-constraints/dev-testing-requirements.md
```

---

## Constraint Priority Levels

| Priority | Meaning | Behavior When Violated |
|----------|---------|------------------------|
| **Critical** | Must never be violated | Stop and alert user immediately |
| **High** | Should strongly avoid | Warn user before proceeding |
| **Medium** | Good practice to follow | Note in session log |
| **Low** | Helpful guideline | Silent - just try to follow |

---

## Constraint Types

### Rule
Strict requirement that must be followed.
**Example**: "NEVER delete production database"

### Guideline
Strong recommendation but has exceptions.
**Example**: "Prefer composition over inheritance"

### Standard
Project convention for consistency.
**Example**: "Use snake_case for Python variables"

### Process
Procedural step that should be followed.
**Example**: "Run tests before committing"

---

## Maintenance

### Review Schedule

- **Weekly**: Review active constraints for relevance
- **After bugs**: Add constraint if bug reveals gap
- **After reviews**: Add constraint if pattern emerges
- **Monthly**: Check for outdated/deprecated constraints

### Deprecation Process

When constraint is no longer needed:

1. Change **Status** to "Deprecated"
2. Add **Deprecated Date** and **Reason**
3. Leave file for 30 days (for sessions that reference it)
4. After 30 days: Move to `archive/` subdirectory
5. Update any references in procedures or other constraints

### Updating Constraints

When modifying constraints:

1. Add version number or date to constraint
2. Document what changed and why
3. Notify team if it affects workflows
4. Update examples to reflect changes

---

## Best Practices

### Do:

✓ Be specific and actionable
✓ Include examples (good and bad)
✓ Explain the "why" (rationale)
✓ Reference related bugs/decisions
✓ Keep constraints focused (one topic per file)
✓ Update when patterns change

### Don't:

✗ Write vague or subjective rules
✗ Include general coding advice (agent knows basics)
✗ Make constraints too long (>200 lines)
✗ Forget to update status when deprecated
✗ Create redundant constraints
✗ Leave outdated constraints active

---

## Troubleshooting

### Agent Isn't Following Constraint

**Possible Causes**:
1. Constraint file not in `agent-constraints/` directory
2. Agent name doesn't match Agent field in constraint
3. Constraint marked as Draft or Deprecated
4. Constraint is too vague or not actionable
5. Agent loaded but context was lost (restart session)

**Solutions**:
- Verify file location and naming
- Check Agent field matches agent being used
- Set Status to Active
- Rewrite constraint to be more specific
- Reload agent with constraints

### Too Many Constraints Slowing Agent

**Symptoms**:
- Agent takes long time to respond
- Context overflow warnings
- Agent forgets earlier conversation

**Solutions**:
- Consolidate related constraints
- Remove outdated constraints
- Make constraints more concise
- Archive low-priority constraints
- Use priority levels to focus on critical ones

---

## Integration with Other Systems

### With Bug Tracking

When fixing bugs:
1. Document root cause
2. Check if pattern can be prevented
3. If yes: Create agent constraint
4. Reference bug in constraint rationale

### With Decision Log

When making architectural decisions:
1. Document decision in DEC-XXX
2. If decision affects agent behavior: Create constraint
3. Reference decision in constraint
4. Constraint enforces decision automatically

### With Code Review

During code reviews:
1. Note repeated issues
2. If pattern emerges: Create constraint
3. Constraint prevents future occurrences
4. Less time spent on same issues

---

## Examples

See these example constraint files:

1. **CONSTRAINT_TEMPLATE.md** - Base template
2. **EXAMPLE_parzival-quality-gates.md** - Quality gate requirements
3. **EXAMPLE_dev-testing-requirements.md** - Testing standards

---

## Related Documentation

- Parzival Agent: `bmad-parzival-module/pov/agents/parzival.md`
- Procedures: `bmad-parzival-module/pov/procedures/PROCEDURES.md`
- Bug Template: `oversight/bugs/BUG_TEMPLATE.md`
- Decision Template: `oversight/decisions/DECISION_TEMPLATE.md`

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-21 | 1.0 | Initial agent constraints system documentation |

---

## Notes

This system is experimental. Adjust based on what works for your team and project. The goal is consistency and reduced cognitive load - not bureaucracy.

Start with 2-3 critical constraints. Add more as patterns emerge. Remove constraints that aren't helping.
