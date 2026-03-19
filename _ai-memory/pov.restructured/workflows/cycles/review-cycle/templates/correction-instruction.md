---
name: 'correction-instruction'
description: 'Template for sending classified issues to DEV for correction'
---

# Correction Instruction Template

Use this template when building a correction instruction in step-04.

```
PARZIVAL -> DEV -- CORRECTION INSTRUCTION
Pass: [N] of review cycle

REVIEW RESULT: [N] legitimate issues found -- fixes required before proceeding

REVIEW SUMMARY:
  Total issues found:      [N]
  Legitimate (must fix):   [N]
  Non-issues (excluded):   [N]
  Uncertain (pending):     [N]

FIXES REQUIRED -- In priority order:

[CRITICAL]
Issue 1:
  Location:    [file + function + line]
  Problem:     [clear description]
  Required:    [what it must be -- cite PRD/architecture/standards]
  Basis:       [Criterion A1-A8 + project file citation]

[HIGH]
Issue 2:
  Location:    [file + function + line]
  Problem:     [clear description]
  Required:    [what it must be -- cite source]
  Basis:       [Criterion + citation]

[MEDIUM]
Issue 3:
  [same format]

[LOW]
Issue 4:
  [same format]

NON-ISSUES -- No fix required (documented):

Issue 5:
  [description] -- Excluded: [B1-B4 reasoning]

UNCERTAIN -- Pending resolution:

Issue 6:
  [description] -- WF-RESEARCH-PROTOCOL in progress / Awaiting user decision
  [Hold this issue -- do not attempt to fix until resolution provided]

ACTION REQUIRED:

1. Fix ALL legitimate issues listed above in priority order
2. Run your own code review after all fixes are applied
3. Report back with:
   - Confirmation each issue was fixed
   - How each fix was implemented
   - Your review result after fixes (zero issues, or new issues found)

DO NOT:
  - Fix only some issues and report back
  - Introduce changes beyond the scope of these specific fixes
  - Proceed to any other task
  - Mark complete if any legitimate issue remains unresolved
```
