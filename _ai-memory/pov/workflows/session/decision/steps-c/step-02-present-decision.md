---
name: 'step-02-present-decision'
description: 'Present the structured decision to the user in approval gate format and wait for their choice'
nextStepFile: './step-03-log-decision.md'
---

# Step 2: Present Decision

**Progress: Step 2 of 3** — Next: Log Decision

## STEP GOAL:

Present the fully structured decision to the user in the approval gate format and wait for their explicit choice.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The structured decision from Step 1
- Focus: Present the decision and wait for user input — no execution
- Limits: Present and wait — do not execute any option until the user decides
- Dependencies: Fully structured decision with options and recommendation from Step 1

- Focus on presenting the structured decision in approval gate format and waiting for user's choice
**Behavioral Constraints:**
- FORBIDDEN to execute any option — present and wait only
- Approach: Use the exact approval gate format; evaluate user-proposed options against the same criteria
- Record user's choice and stated rationale for logging in the next step

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Wait for User Decision

- Do NOT execute any option until the user explicitly chooses
- If the user asks for more information, provide it
- If the user proposes a new option not listed, evaluate it against the same criteria
- Record the user's choice and their stated rationale (if given) for logging

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user has made an explicit decision (including "defer" or "none of the above"), will you then read fully and follow: `{nextStepFile}` to begin logging the decision.
