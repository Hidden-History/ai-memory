---
name: 'step-02-present-decision'
description: 'Present the structured decision to the user in approval gate format and wait for their choice'
nextStepFile: './step-03-log-decision.md'
---

# Step 2: Present Decision

## STEP GOAL
Present the fully structured decision to the user in the approval gate format and wait for their explicit choice.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The structured decision from Step 1
- Limits: Present and wait -- do not execute any option until the user decides

## MANDATORY SEQUENCE

### 1. Present Decision in Approval Gate Format

Use this exact format:

```
## Decision Request: [Topic]

### Context
[Why this decision is needed now. What triggered it.]

### Constraints
- [Relevant constraints that apply]
- [From constraint files or architecture decisions]

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

### Recommendation
I recommend **Option [X]** because:
- [Primary reason]
- [Secondary reason]

**Confidence**: [Verified/Informed/Inferred]

### What I Don't Know
[Uncertainties that might affect this decision]

---
**Your decision?**
```

### 2. Wait for User Decision
- Do NOT execute any option until the user explicitly chooses
- If the user asks for more information, provide it
- If the user proposes a new option not listed, evaluate it against the same criteria
- Record the user's choice and their stated rationale (if given) for logging

## CRITICAL STEP COMPLETION NOTE
ONLY when the user has made an explicit decision (including "defer" or "none of the above"), load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Decision is presented in the defined approval gate format
- User makes the decision, not Parzival
- User's choice and rationale are recorded
- Additional information is provided when requested

### FAILURE:
- Presenting in a non-standard format
- Executing an option without user approval
- Steering the user toward a specific option beyond the stated recommendation
- Proceeding without a clear user decision
