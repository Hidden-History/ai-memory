---
name: 'step-02-analyze-and-resolve'
description: 'Analyze root cause, generate resolution options, and present recommendation to user'
nextStepFile: './step-03-log-blocker.md'
---

# Step 2: Analyze and Propose Resolution

## STEP GOAL
Determine the likely root cause of the blocker, generate at least 2 viable resolution options with tradeoffs, and present a recommendation to the user for decision.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Blocker details captured in Step 1, project files, constraint files at `{constraints_path}/`
- Limits: Parzival recommends, user decides -- do not execute a resolution without user approval

## MANDATORY SEQUENCE

### 1. Root Cause Analysis
Investigate the likely cause:
- Examine relevant project files if the blocker involves code or configuration
- Check constraints that may be relevant
- Determine if this is a technical issue, a process issue, or a dependency issue

Document:
- **Likely cause**: Clear description of what is causing the block
- **Confidence level**: Verified (confirmed by evidence) / Informed (strong signals) / Inferred (logical deduction) / Uncertain (best guess)
- **Reasoning**: Why this cause is believed to be correct

### 2. Generate Resolution Options
Produce at least 2 viable options (3 if applicable):

For each option:
- **Name**: Short descriptive label
- **Approach**: What specifically to do
- **Pros**: Benefits of this approach
- **Cons**: Drawbacks or risks
- **Complexity**: Straightforward / Moderate / Significant
- **Reversibility**: Easy / Moderate / Difficult

### 3. Formulate Recommendation
Select the option Parzival recommends and explain why:
- Primary reasoning
- Why other options are less preferred
- Any caveats or conditions

### 4. Present to User

Use this format:

```
## Blocker Analysis

### Issue
[Clear description of what is blocked]

### Error/Symptom
[Error message or observable behavior]

### Root Cause Analysis
**Likely Cause**: [Description]
**Confidence**: [Verified/Informed/Inferred/Uncertain]
**Reasoning**: [Why Parzival thinks this]

### Similar Past Issues
[References from Step 1, or "None found"]

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

### 5. Wait for User Decision
- Do NOT execute any resolution until the user selects an option
- If the user asks for more options or information, provide it
- Record which option the user selects for logging in the next step

## CRITICAL STEP COMPLETION NOTE
ONLY when the user has selected a resolution option (or explicitly decided to defer), load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Root cause analysis includes confidence level
- At least 2 resolution options are presented
- Each option has pros, cons, and complexity
- Recommendation is supported by reasoning
- User makes the decision, not Parzival

### FAILURE:
- Providing only one resolution option
- Executing a resolution without user approval
- Presenting options without pros/cons analysis
- Giving a recommendation without reasoning
- Skipping root cause analysis
