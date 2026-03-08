---
name: 'step-02-prepare-instruction'
description: 'Build the precise implementation instruction that translates the story into an executable task for DEV'
nextStepFile: './step-03-activate-dev.md'
---

# Step 2: Prepare DEV Implementation Instruction

## STEP GOAL
Build the implementation instruction -- the most important document Parzival produces per story. This translates the story file into a precise, executable instruction for the DEV agent. Every field must be specific enough that DEV can implement with no other context.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Verified story file, architecture.md, project-context.md
- Limits: Instruction must be complete and self-contained. DEV should not need to read other files.

## MANDATORY SEQUENCE

### 1. Build Implementation Instruction
Include all of the following sections:

**Task:** Implement [Story Title] as specified.

**User story:** Copy from story file verbatim.

**Acceptance criteria:** Copy all criteria. These are the definition of done.

**Technical implementation:**
- Files to CREATE: each new file with its purpose
- Files to MODIFY: each file with what changes and why
- Architectural patterns to follow: cite architecture.md section and pattern name
- Standards to follow: cite project-context.md section and rule name
- Database work (if applicable): models, relationships, migrations
- API work (if applicable): endpoints, request/response format, authentication
- Testing requirements: test type, what to test, coverage expectation

**Scope:**
- IN SCOPE: explicit list
- OUT OF SCOPE: explicit exclusions, adjacent functionality belonging to other stories

**Security requirements:** Input validation, authorization checks, data protection

**Implementation notes:** Guidance from architecture, known edge cases, prior decisions

**Done when:** All acceptance criteria satisfied, all files created/modified correctly, tests written and passing, no code outside scope changed, self-review completed

**Report back with:** Files created/modified, implementation approach, any unavoidable decisions, any blockers

### 2. Run Instruction Quality Check
Before dispatching:
- Is every acceptance criterion reflected in DONE WHEN?
- Are files specifically named (not "the relevant files")?
- Are architecture references specific (section numbers, pattern names)?
- Are standards references specific (section numbers, rule names)?
- Is scope unambiguous?
- Are security requirements addressed for user input, auth, data storage, external APIs?
- Are testing requirements specific enough to implement?
- Is the instruction complete -- could DEV implement with no other context?

**IF ANY CHECK FAILS:** Fix the instruction before dispatching.

## CRITICAL STEP COMPLETION NOTE
ONLY when the instruction passes the quality check, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Instruction includes all required sections
- Every field is specific (not vague)
- Quality check passes
- DEV could implement with this instruction alone

### FAILURE:
- Sending story file directly instead of building instruction
- Vague file references ("the relevant files")
- Missing security requirements
- Quality check not run before dispatch
