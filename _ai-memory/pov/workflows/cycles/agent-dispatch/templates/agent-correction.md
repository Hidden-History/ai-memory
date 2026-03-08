---
name: 'agent-correction'
description: 'Template for sending correction instructions back to an agent when output review fails'
---

# Agent Correction Template

Use this template when building a correction instruction in step-07.

```
PARZIVAL -> [AGENT NAME] CORRECTION

REVIEW RESULT: Issues found -- do not proceed

ISSUE 1: [specific description]
  Location: [file, function, line if applicable]
  Problem:  [what is wrong]
  Required: [what it should be -- cite source if possible]

ISSUE 2: [specific description]
  Location: [file, function, line if applicable]
  Problem:  [what is wrong]
  Required: [what it should be -- cite source if possible]

[Continue for all legitimate issues]

ACTION REQUIRED:
Fix all issues listed above. Re-review your work after fixing.
Report back when complete with zero issues remaining.

DO NOT:
- Fix only some issues and report back
- Introduce new changes outside the scope of these fixes
- Proceed to other tasks
```
