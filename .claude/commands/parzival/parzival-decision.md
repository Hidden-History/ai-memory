---
description: 'Present a decision request with options and tradeoffs'
argument-hint: '<topic requiring decision>'
allowed-tools: Read, Grep, Glob
---

# Decision Request Protocol

Structure a decision for the user with clear options and tradeoffs.

## Input
Decision topic: $ARGUMENTS

## Analysis Steps

1. **Frame the Decision**
   - What needs to be decided?
   - Why now? What triggered this?
   - What's the impact of not deciding?

2. **Research Context**
   - Check relevant architecture decisions
   - Check constraints that apply
   - Check best practices (with sources)

3. **Generate Options**
   - At least 2-3 viable options
   - Include "do nothing" if applicable
   - Note constraints each option respects/violates

4. **Assess Tradeoffs**
   - Complexity of each option
   - Risk level of each option
   - Reversibility of each option

## Output Format

```
## Decision Request: [Topic]

### Context
[Why this decision is needed now. What triggered it.]

### Constraints
- [Relevant constraints that apply]
- [From CONSTRAINTS.md or architecture decisions]

### Options

**Option A: [Name]**
| Aspect | Assessment |
|--------|------------|
| Description | [What this option means] |
| Complexity | [Straightforward/Moderate/Significant/Complex] |
| Risk | [Low/Medium/High] |
| Reversibility | [Easy/Moderate/Difficult/Irreversible] |
| Pros | [Benefits] |
| Cons | [Drawbacks] |

**Option B: [Name]**
| Aspect | Assessment |
|--------|------------|
| Description | [What this option means] |
| Complexity | [Straightforward/Moderate/Significant/Complex] |
| Risk | [Low/Medium/High] |
| Reversibility | [Easy/Moderate/Difficult/Irreversible] |
| Pros | [Benefits] |
| Cons | [Drawbacks] |

**Option C: [Name]** (if applicable)
[Same format]

### Comparison Matrix

| Criterion | Option A | Option B | Option C |
|-----------|----------|----------|----------|
| Complexity | [rating] | [rating] | [rating] |
| Risk | [rating] | [rating] | [rating] |
| Reversibility | [rating] | [rating] | [rating] |
| Alignment with goals | [rating] | [rating] | [rating] |

### Parzival's Recommendation
I recommend **Option [X]** because:
- [Primary reason]
- [Secondary reason]

**Confidence**: [Verified/Informed/Inferred]

### What Parzival Doesn't Know
[Any uncertainties that might affect this decision]

---
**Your decision?**
```

## After Decision

- Document in `oversight/decisions/` if architectural
- Update relevant tracking documents
- Note decision rationale for future reference
