---
name: 'decision-point'
description: 'Decision point format used when Parzival surfaces a mid-workflow decision requiring user input'
---

# Decision Point Template

Use this format when presenting a mid-workflow decision in step-02.

```
PARZIVAL -- DECISION REQUIRED

CONTEXT:  [What is currently happening -- brief]
BLOCKING: [What cannot proceed without this decision]

DECISION NEEDED

[The specific question that needs an answer.
One question at a time -- do not stack multiple decisions.]

OPTIONS

Option A: [specific approach]
  Pros:    [concrete benefits for this project]
  Cons:    [concrete trade-offs]
  Impact:  [what this means for timeline, architecture, future work]

Option B: [specific approach]
  Pros:    [concrete benefits]
  Cons:    [concrete trade-offs]
  Impact:  [downstream effects]

[Option C only if genuinely needed -- avoid false choices]

PARZIVAL'S RECOMMENDATION

[Specific recommendation with clear reasoning.
If no recommendation can be made -- state why.]

What is your decision?
```
