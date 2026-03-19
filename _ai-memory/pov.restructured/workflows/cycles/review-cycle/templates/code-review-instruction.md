---
name: 'code-review-instruction'
description: 'Template for instructing DEV to run a thorough code review'
---

# Code Review Instruction Template

Use this template when triggering a DEV code review in step-02.

```
PARZIVAL -> DEV -- CODE REVIEW INSTRUCTION

TASK: Run a thorough code review on the implementation just completed.

IMPLEMENTATION SCOPE:
  Files changed: [list all files modified or created]
  Task reference: [task/story name]

REVIEW AGAINST:
  Requirements:  [PRD.md section -- specific requirements]
  Architecture:  [architecture.md section -- patterns and constraints]
  Standards:     [project-context.md section -- coding standards]
  Story criteria: [story file -- acceptance criteria]

REVIEW MUST COVER:
  [ ] Correctness -- does the code do what it is supposed to do?
  [ ] Security -- any vulnerabilities, exposed data, improper auth?
  [ ] Architecture compliance -- follows documented patterns?
  [ ] Standards compliance -- follows project-context.md rules?
  [ ] Requirements compliance -- satisfies all acceptance criteria?
  [ ] Edge cases -- unhandled scenarios that will cause failures?
  [ ] Error handling -- failures handled appropriately?
  [ ] Pre-existing issues -- any problems found in surrounding code?
  [ ] Test coverage -- tests present and meaningful where required?
  [ ] Future risk -- anything that will break on foreseeable change?

OUTPUT REQUIRED:
  For every issue found:
    - Location: [file + function + line number]
    - Description: [clear description of the issue]
    - Severity: [your assessment -- critical/high/medium/low]
    - Suggested fix: [what should be done]

  If zero issues found:
    State explicitly: "Code review complete -- zero issues found."

DO NOT:
  - Summarize or skip issues to keep the list short
  - Combine multiple issues into one
  - Report stylistic preferences as issues without standards basis
  - Mark the review as clean if any issue exists

DONE WHEN:
  [ ] Every area listed above has been reviewed
  [ ] All issues are reported with location and description
  [ ] A clear zero-issues or issues-found conclusion is stated
```
