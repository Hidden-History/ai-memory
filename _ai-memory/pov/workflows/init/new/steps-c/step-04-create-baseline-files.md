---
name: 'step-04-create-baseline-files'
description: 'Create the foundational project files that every subsequent workflow depends on'
nextStepFile: './step-05-establish-teams.md'
---

# Step 4: Create Baseline Project Files

**Progress: Step 4 of 7** — Next: Establish Teams

## STEP GOAL:

Create the project's foundational files using confirmed user information from Step 2. These files are Parzival's working documents. Every field must trace to user-confirmed input -- no assumptions, no generic content.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus on creating baseline files from confirmed user input only
- 🚫 FORBIDDEN to invent content or use generic placeholder text
- 💬 Approach: Every field must trace directly to user-confirmed input from Step 2
- 📋 Mark anything not explicitly confirmed as TBD — never assume

## EXECUTION PROTOCOLS:

- 🎯 Create all four baseline files using confirmed user input
- 💾 Verify each file exists and contains correct content after creation
- 📖 Load next step only after all files are created and verified
- 🚫 FORBIDDEN to proceed with missing or incomplete baseline files

## CONTEXT BOUNDARIES:

- Available context: Confirmed project information from Step 2, verified _ai-memory/ installation from Step 3
- Focus: File creation only — populate from confirmed input, mark unknowns as TBD
- Limits: Every file entry must trace to user-confirmed input. Do not invent content. Mark anything not explicitly confirmed as TBD.
- Dependencies: Step 2 (confirmed project foundation) and Step 3 (verified installation) must be complete

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Create project-status.md (Required -- first file created)

Create at the project data location with all required fields:

```yaml
project_name: [confirmed name]
created: [current date]
last_updated: [current date]
current_phase: discovery
current_sprint: null
active_task: null
baseline_complete: false
track: [quick-flow | standard-method | enterprise]

phases_complete:
  discovery: false
  architecture: false
  planning_initialized: false

key_files:
  prd: null
  architecture: null
  project_context: null
  sprint_status: null

last_session_summary: |
  Project initialized. Baseline files being created.
  Ready to begin Discovery phase.

open_issues: 0
notes: |
  [Any constraints or open items noted during initialization]
```

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All four files created with correct content
- Every field traces to user-confirmed input
- TBD items are clearly marked
- No assumptions or generic content in any file
- Open items from Step 2 are reflected in goals.md
- Menu presented and user input handled correctly

### ❌ SYSTEM FAILURE:

- Creating files with assumed content
- Filling goals.md with generic placeholder text
- Missing required fields in project-status.md
- Not marking TBD items clearly in project-context.md
- Proceeding without user selecting 'C' (Continue)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
