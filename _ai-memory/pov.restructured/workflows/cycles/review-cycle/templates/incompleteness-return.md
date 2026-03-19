---
name: 'incompleteness-return'
description: 'Template for returning incomplete implementation to DEV with specific direction'
---

# Incompleteness Return Instruction Template

Use this template when implementation completeness checks fail in step-01.

```
PARZIVAL -> DEV -- IMPLEMENTATION INCOMPLETE

REVIEW RESULT: Implementation incomplete -- code review not yet triggered

MISSING OR INCOMPLETE:
  1. [Specific item -- what is missing or incomplete]
     Required by: [DONE WHEN criterion / requirement citation]

  2. [Specific item]
     Required by: [criterion / citation]

OUT OF SCOPE CHANGES DETECTED (if applicable):
  - [File or change that was not in scope]
  - Revert this change -- it was not part of this task

ACTION REQUIRED:
Complete all items listed above. Do not add anything beyond what is listed.
Report back when all DONE WHEN criteria are fully met.
```
