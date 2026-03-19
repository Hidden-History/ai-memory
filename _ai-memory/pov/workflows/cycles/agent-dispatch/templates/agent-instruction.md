---
name: 'agent-instruction'
description: 'Template for every instruction sent to a BMAD agent'
---

# Agent Instruction Template

Use this template when building an instruction in step-01. Every instruction sent to a BMAD agent must follow this exact format.

```
PARZIVAL -> [AGENT NAME] INSTRUCTION

TASK:
[Single, specific, unambiguous description of what to do.
One task per instruction. Never combine multiple tasks.]

CONTEXT:
[Relevant background the agent needs -- only what is necessary.
Do not dump the entire project history. Be precise.]

REQUIREMENTS:
[Cite specific files and sections:]
- PRD.md [section]: [requirement]
- architecture.md [section]: [constraint]
- project-context.md [section]: [standard]
- [story file]: [acceptance criteria]

SCOPE:
  IN SCOPE:
  - [exactly what the agent should work on]
  - [specific files, functions, modules]

  OUT OF SCOPE:
  - [explicitly what the agent must not touch]
  - [adjacent areas to avoid]

OUTPUT EXPECTED:
[Exactly what the agent should produce -- file names, formats, contents]

DONE WHEN:
[Measurable, specific criteria. Agent must be able to self-assess completion.]
- [ ] [criterion 1]
- [ ] [criterion 2]
- [ ] [criterion 3]

STANDARDS TO FOLLOW:
[Specific coding standards, patterns, naming conventions from project-context.md]

IF YOU ENCOUNTER A BLOCKER:
Stop immediately. Do not guess or proceed on assumptions.

Escalate when you encounter ANY of these situations:
- Architectural decisions not covered in documentation
- Constraint conflicts you cannot resolve (e.g., version incompatibilities)
- Pattern choices that would affect multiple components
- Uncertainty about project conventions or naming
- Need to verify against project history or past decisions
- Missing context required to make a correct decision

Report using this exact format:

  BLOCKER REPORT
  Agent: [your agent name]
  Task: [what you are currently working on]
  Blocker: [what you do not know or cannot determine]
  Considered: [options you evaluated and why each was insufficient]
  Need: [specific information or decision required to proceed]

Do not continue work until the blocker is resolved.
```
