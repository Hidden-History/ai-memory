---
name: 'STEP-SCAFFOLD'
description: 'Shared step-file scaffolding — standard section formats and reference frame used by steps-c/ step files. Referenced by each step file to avoid copy-maintained boilerplate.'
---

# Shared Step-File Scaffold

This file defines the standard **frame** for steps-c/ step files: the preamble reference, scope-block structure, and completion-note format. Step files reference this frame rather than repeating it. Workflow-specific content (step goal, scope values, sequence, completion condition) lives in each step file.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

---

## Scope Block Format

Every step file provides these four scope values after its STEP GOAL:

```
**Scope:**
- Available context: [what prior steps provide, what files are loaded]
- Focus: [this step's goal only]
- Limits: [what this step does NOT do]
- Dependencies: [prior steps' outputs required]
```

Plus workflow-specific behavioral constraints as additional bullets (typically 1–3).

---

## Completion Note Format

**Auto-proceed step** (directs to next step unconditionally on outcome):
```
## CRITICAL STEP COMPLETION NOTE

ONLY when [specific completion condition], load and read fully {nextStepFile}
```

**Menu step** (user picks an option before proceeding):
```
### N. Present Options

[Summary of what this step produced]

**Select an Option:**
- **[C]** Continue to next step
- **[other]** [Description of other option]

#### Handling:
- IF C: [update tracking if needed], then read fully and follow: `{nextStepFile}`
- IF [other]: [handle and redisplay menu]
- IF user asks questions: answer and redisplay menu

ALWAYS halt and wait for user input after presenting options.
```

**Terminal step** (workflow ends, no nextStepFile):
```
## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- [Workflow-specific closeout actions]
- No nextStepFile — user direction drives all subsequent work
```

---

## Sequence Header Format

Use **one** of the following, matching the step's actual nature:

- **Strict-order step** (tasks have data dependencies or gate each other):
  `## Sequence`

- **Parallel-gather step** (tasks are independent reads or checks):
  `## Context to Load` / `## Sources to Check` / `## Checks to Apply` — followed by a one-sentence outcome statement.

Do not use strict-order framing on a step whose tasks are actually independent.
