---
description: 'Analyze a blocker and present resolution options'
argument-hint: '<description of the blocker>'
allowed-tools: Read, Grep, Glob
---

# Blocker Analysis Protocol

Analyze the reported blocker and present resolution options.

## Input
Blocker description: $ARGUMENTS

## Analysis Steps

1. **Understand the Blocker**
   - What is failing/blocked?
   - What was expected vs actual?
   - Any error messages?

2. **Check Failure Pattern Library**
   - Search `oversight/learning/failure-pattern-library.md`
   - Look for similar past issues

3. **Identify Root Cause**
   - What's the likely cause?
   - State confidence level (Verified/Informed/Inferred/Uncertain)

4. **Generate Options**
   - At least 2-3 viable approaches
   - Include pros/cons for each
   - Note complexity of each

## Output Format

```
## Blocker Analysis

### Issue
[Clear description of what's blocked]

### Error/Symptom
[Error message or observable behavior]

### Root Cause Analysis
**Likely Cause**: [Description]
**Confidence**: [Verified/Informed/Inferred/Uncertain]
**Reasoning**: [Why Parzival thinks this]

### Similar Past Issues
[If found in failure pattern library, reference them. Otherwise "None found"]

### Resolution Options

**Option A: [Name]**
- Approach: [What to do]
- Pros: [Benefits]
- Cons: [Drawbacks]
- Complexity: [Straightforward/Moderate/Significant]

**Option B: [Name]**
- Approach: [What to do]
- Pros: [Benefits]
- Cons: [Drawbacks]
- Complexity: [Straightforward/Moderate/Significant]

**Option C: [Name]** (if applicable)
- Approach: [What to do]
- Pros: [Benefits]
- Cons: [Drawbacks]
- Complexity: [Straightforward/Moderate/Significant]

### Recommendation
I recommend **Option [X]** because [reasoning].

---
**Your choice?**
```

## After Resolution

Remind to:
- Add to failure pattern library if new issue
- Update blockers log
- Document what worked for future reference
