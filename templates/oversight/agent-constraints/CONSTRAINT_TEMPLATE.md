# {Constraint Title}

**Agent**: [Agent name (e.g., parzival, dev, tea, architect) or "All"]
**Type**: [Rule|Guideline|Standard|Process]
**Priority**: [Critical|High|Medium|Low]
**Status**: [Active|Draft|Deprecated]
**Created**: [YYYY-MM-DD]
**Last Updated**: [YYYY-MM-DD]

---

## Rule

[Clear, actionable statement of the constraint. Be specific. Use imperative language.]

**Format**:
- ALWAYS/NEVER statements for rules
- SHOULD/PREFER statements for guidelines
- MUST USE statements for standards
- FOLLOW THESE STEPS for processes

---

## Rationale

[Explain WHY this constraint exists]

**Background**:
[Context that led to creating this constraint]

**Problems It Solves**:
- [Problem 1 - link to bug/incident if applicable]
- [Problem 2]
- [Problem 3]

**Benefits**:
- [Benefit 1]
- [Benefit 2]

---

## Scope

**Applies To**:
- [Component/module/feature where this applies]
- [File patterns, e.g., `src/**/*.py`]
- [Specific scenarios]

**Does NOT Apply To**:
- [Exceptions or exclusions]
- [Areas where this doesn't matter]

---

## Implementation

[Step-by-step guidance on how to follow this constraint]

1. [Step 1 - what to do first]
2. [Step 2 - what to do next]
3. [Step 3 - final verification]

---

## Examples

### ✓ Correct Usage

**Example 1**:
```
[Code, file structure, or process example showing CORRECT behavior]
```

**Why This Is Good**:
[Explanation of why this follows the constraint]

**Example 2**:
```
[Another good example]
```

---

### ✗ Incorrect Usage

**Example 1**:
```
[Code, file structure, or process example showing INCORRECT behavior]
```

**Why This Is Bad**:
[Explanation of what's wrong]

**How to Fix**:
[Specific fix]

**Example 2**:
```
[Another bad example]
```

---

## Verification

[How to verify the constraint is being followed]

### Manual Check

- [ ] [Check 1]
- [ ] [Check 2]
- [ ] [Check 3]

### Automated Check (if applicable)

```bash
# Command to verify constraint
[e.g., lint rule, test command, grep pattern]
```

---

## Exceptions

[When is it OK to break this constraint?]

### Valid Exceptions

1. **Exception 1**: [Description]
   - **When**: [Specific scenario]
   - **Approval Required**: [Yes/No, from whom]

2. **Exception 2**: [Description]
   - **When**: [Specific scenario]
   - **Approval Required**: [Yes/No, from whom]

### How to Document Exceptions

If breaking this constraint:
1. Add comment explaining why: `# CONSTRAINT-EXCEPTION: {reason}`
2. Reference this constraint: `# See agent-constraints/{filename}.md`
3. Get review approval if priority is High or Critical
4. Document in code review or session log

---

## Related

### Related Bugs/Issues
- BUG-XXX: [Bug that led to this constraint]
- BUG-XXX: [Another related bug]

### Related Decisions
- DEC-XXX: [Decision that established this constraint]
- DEC-XXX: [Another related decision]

### Related Constraints
- [{other-constraint}.md]: [Related constraint]

### Related Documentation
- [Link to relevant docs]
- [Link to architecture docs]

---

## Enforcement

### Priority Level: [Critical|High|Medium|Low]

**Critical**:
- Agent MUST stop if constraint violated
- Require user confirmation to proceed
- Log as critical error

**High**:
- Agent SHOULD warn before proceeding
- Request user review
- Document in session log

**Medium**:
- Agent notes violation in response
- Continue with caution
- Mention in session summary

**Low**:
- Agent silently tries to follow
- No explicit notification
- Guideline only

---

## Monitoring

[How to track compliance with this constraint]

### Metrics (if applicable)

- [Metric 1]: [How to measure]
- [Metric 2]: [How to measure]

### Review Schedule

- **Review Frequency**: [Daily|Weekly|Monthly|Quarterly]
- **Owner**: [Who monitors compliance]
- **Action on Violation**: [What happens]

---

## History

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | [YYYY-MM-DD] | Initial constraint created | [Name] |

### Deprecation (if applicable)

**Deprecated**: [YYYY-MM-DD]
**Reason**: [Why constraint is no longer needed]
**Replacement**: [Link to new constraint if applicable]
**Archive Date**: [When to move to archive/]

---

## Notes

[Any additional context, observations, or future considerations]

### Future Considerations

[Things to watch for or revisit later]

### Lessons Learned

[What we learned from implementing this constraint]

---

## Quick Reference

**TL;DR**: [One-sentence summary of constraint]

**Key Takeaway**: [Most important thing to remember]

**Common Mistakes**:
1. [Mistake 1]
2. [Mistake 2]

**Quick Checks**:
- [ ] [Quick verification 1]
- [ ] [Quick verification 2]
