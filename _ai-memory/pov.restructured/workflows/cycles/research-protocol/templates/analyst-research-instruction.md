---
name: 'analyst-research-instruction'
description: 'Template for dispatching research instructions to the Analyst agent'
---

# Analyst Research Instruction Template

Use this template when activating the Analyst agent for Layer 3 deep codebase research in step-04.

```
PARZIVAL -> ANALYST RESEARCH INSTRUCTION

RESEARCH QUESTION:
[The precise question from the Question Definition Template]

CONTEXT:
[Why this needs to be answered -- what decision depends on it]

ALREADY CHECKED:
Layer 1 -- Project files:
  [What was found or not found in each file]

Layer 2 -- External documentation:
  [What sources were checked and what they said]

RESEARCH SCOPE:
  Focus on: [specific files, modules, or patterns to examine]
  Look for: [what to search for -- patterns, implementations, decisions]
  Avoid:    [what is out of scope for this research]

OUTPUT REQUIRED:
  1. What does the codebase currently do in this area?
  2. Are there existing patterns that address this question?
  3. What is the recommended approach given what you found?
  4. Cite specific files and line numbers for all findings.

DONE WHEN:
  [ ] Question is answered with specific codebase evidence
  [ ] All findings are cited with file paths and line numbers
  [ ] A recommendation is provided with reasoning
  [ ] No assumptions made -- only documented findings reported
```
