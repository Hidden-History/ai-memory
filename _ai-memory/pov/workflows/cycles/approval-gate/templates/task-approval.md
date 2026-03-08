---
name: 'task-approval'
description: 'Standard task approval format used after every completed task (WF-REVIEW-CYCLE exit)'
---

# Task Approval Template

Use this format when presenting task completion for approval in step-02.

```
PARZIVAL -- TASK COMPLETE | Approval Required

TASK:    [task/story name]
SPRINT:  [sprint number if applicable]
STATUS:  Zero legitimate issues -- ready for approval

COMPLETED

[Plain language description of what was built or done.
Specific, concrete, accurate. 2-4 sentences.]

REVIEW SUMMARY

Review passes:        [N]
Issues found:         [N total]
  Legitimate (fixed): [N]
  Non-issues:         [N]
  Pre-existing fixed: [N]
Final status:         Zero legitimate issues confirmed

[If notable issues were found and fixed -- briefly describe them here.
If clean from pass 1 -- state that.]

FIXED (if applicable)

[Only include if issues were found and resolved.
List each significant fix with a one-line description.
Skip this section if pass 1 was clean.]

DECISION NEEDED (if applicable)

[Only include if a decision is required.
State the question clearly.
Present options with trade-offs.
State Parzival's recommendation.
Skip this section if no decision is needed.]

NEXT STEP

Recommended: [specific next action]
Alternative: [if a different direction is reasonable]

Do you approve this task?
  [A] Approve -- proceed to next step
  [R] Reject -- provide feedback below
  [H] Hold -- pause, I'll confirm when ready
```
