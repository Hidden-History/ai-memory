---
name: 'step-04-create-baseline-files'
description: 'Create the foundational project files that every subsequent workflow depends on'
nextStepFile: './step-05-establish-teams.md'
---

# Step 4: Create Baseline Project Files

**Progress: Step 4 of 7** — Next: Establish Teams

## STEP GOAL:

Create the project's foundational files using confirmed user information from Step 2. These files are Parzival's working documents. Every field must trace to user-confirmed input -- no assumptions, no generic content.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Confirmed project information from Step 2, verified _ai-memory/ installation from Step 3
- Focus: File creation only — populate from confirmed input, mark unknowns as TBD
- Limits: Every file entry must trace to user-confirmed input. Do not invent content. Mark anything not explicitly confirmed as TBD.
- Dependencies: Step 2 (confirmed project foundation) and Step 3 (verified installation) must be complete

- Focus on creating baseline files from confirmed user input only
**Behavioral Constraints:**
- FORBIDDEN to invent content or use generic placeholder text
- Approach: Every field must trace directly to user-confirmed input from Step 2
- Mark anything not explicitly confirmed as TBD — never assume

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Populate project-status.md (Required -- first file populated)

`project-status.md` is **deployed from the canonical seed** `templates/oversight/project-status.md` (the source-of-truth heartbeat contract) by the installer, which copies it to the project's oversight/ data location with the seed's placeholder field values intact.

At WF-INIT, **POPULATE-IN-PLACE**: OVERWRITE the placeholder field VALUES with the initialized values below, preserving the `---` front-matter contract block intact. Do NOT rewrite, re-declare, or duplicate the schema here -- the seed is the single schema source; this step only sets values.

Population mapping (from confirmed Step-2 input):

- `current_phase` → `discovery`
- `current_sprint` → `null`
- `active_task` → `null`
- `baseline_complete` → `false`
- `phases_complete.discovery` → `false`
- `phases_complete.architecture` → `false`
- `phases_complete.planning_initialized` → `false`
- `key_files.prd` → `null`
- `key_files.architecture` → `null`
- `key_files.project_context` → `null`
- `live_record` → `oversight/SESSION_WORK_INDEX.md`
- `last_session_summary` → `"[today's date] — project initialized; baseline files created; ready for Discovery"`
- `open_issues` → `0`

This file is the bounded heartbeat (cap 60 lines / 6 KB, per its front-matter). Do NOT add narrative, per-phase breakdowns, or key-file maps here -- that detail lives in goals.md and SESSION_WORK_INDEX.md.

---

### 2. Create goals.md (Required -- Discovery depends on this)

Create with the following sections, all populated from confirmed user input:

- **Project Name** -- from confirmed info
- **Primary Goal** -- one clear sentence from user
- **Problem Being Solved** -- what problem, for whom
- **Success Criteria** -- how we know the project succeeded (specific, measurable where possible)
- **Known Constraints** -- hard constraints: deadlines, compliance, integrations, budget
- **Out of Scope (Initial)** -- what is explicitly NOT part of this project
- **Open Questions for Discovery** -- items deferred to be resolved in Discovery
- **Tech Stack Decisions Made** -- confirmed decisions only, everything else is TBD

---

### 3. Create project-context.md (Stub -- populated in Architecture)

Create as a stub with clear status indicating it is not yet confirmed:

```markdown
# Project Context

> Status: STUB -- To be populated during Architecture phase
> Do not treat any section as confirmed until Architecture is complete

## Technology Stack
[TBD -- Architecture phase]

## Code Organization
[TBD -- Architecture phase]

## Naming Conventions
[TBD -- Architecture phase]

## Testing Approach
[TBD -- Architecture phase]

## Known Preferences (Pre-Architecture)
[Any user-stated preferences from initialization -- not decisions yet]
```

---

### 4. Create decisions.md (Decision log -- starts with init decisions)

Create with initialization decisions recorded:

```markdown
# Project Decision Log

> Every significant decision made during this project is recorded here.
> Format: Decision | Date | Reasoning | Who decided

## Initialization Decisions
| Decision | Date | Reasoning |
|---|---|---|
| Track: [track] | [date] | [reason based on project scale] |

## Architecture Decisions
[None yet -- Architecture phase]

## Standards Decisions
[None yet -- Architecture phase]

## Scope Decisions
[None yet -- Discovery phase]
```

---

### 5. Verify All Files Created

After creating all files, verify each exists and contains the correct content:
- project-status.md -- all required fields present
- goals.md -- all sections populated from user input
- project-context.md -- stub created with TBD markers
- decisions.md -- initialization decisions recorded

---

### 6. Present MENU OPTIONS

Display: "**All four baseline files created and verified. Ready to establish teams.**"

**Select an Option:** [C] Continue to Team Establishment

#### Menu Handling Logic:

- IF C: Read fully and follow: `{nextStepFile}` to begin establishing teams
- IF user wants corrections: Apply corrections, re-verify, redisplay menu
- IF user asks questions: Answer and redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C' (Continue)

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [C continue option] is selected and [all four baseline files are created and verified], will you then read fully and follow: `{nextStepFile}` to begin establishing teams.
