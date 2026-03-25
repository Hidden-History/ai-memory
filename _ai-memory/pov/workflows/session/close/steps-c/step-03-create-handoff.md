---
name: 'step-03-create-handoff'
description: 'Create the session handoff document and update the SESSION_WORK_INDEX'
nextStepFile: './step-04-save-and-confirm.md'
handoffTemplate: '{project-root}/_ai-memory/pov/templates/session-handoff.template.md'
---

# Step 3: Create Handoff Document

**Progress: Step 3 of 4** — Next: Save and Confirm

## STEP GOAL:

Write the session handoff document for the next Parzival session and update the SESSION_WORK_INDEX with a reference to it.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus on writing the handoff document and updating SESSION_WORK_INDEX
- 🚫 FORBIDDEN to save to Qdrant in this step — that is Step 4
- 💬 Approach: Load template if available, write document, verify, then update index
- 📋 Verify the written handoff by reading it back before marking complete

## EXECUTION PROTOCOLS:

- 🎯 Write a complete handoff with all sections populated — no empty sections allowed
- 💾 Verify handoff by reading file back before updating SESSION_WORK_INDEX
- 📖 Load next step only after handoff is written, verified, and index is updated
- 🚫 FORBIDDEN to proceed if any handoff section is empty or contains only placeholders

## CONTEXT BOUNDARIES:

- Available context: Session summary from Step 1, updated tracking from Step 2
- Focus: Handoff document creation and SESSION_WORK_INDEX update only
- Limits: Write the handoff and update the index — Qdrant save is in the next step
- Dependencies: Session summary from Step 1 and updated tracking from Step 2

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Load Template (If Available)

If `{handoffTemplate}` exists, use it as the format guide. Otherwise, use the format below.

---

### 2. Write Handoff Document

Create file: `{oversight_path}/session-logs/SESSION_HANDOFF_{date}.md`

Where `{date}` is today's date in YYYY-MM-DD format.

```markdown
# Session Handoff: [Primary Topic]

**Date**: [YYYY-MM-DD]
**Session Duration**: [Approximate time]

## Executive Summary
[2-3 sentences: What was accomplished, current state, what is next]

## Work Completed
- [Task ID]: [Description of what was done]
- [Include all completed items with IDs]

## Current Status
- **Active Task**: [ID] [Title] - [Status]
- **Blockers**: [List or "None"]
- **In Progress**: [What is partially done]

## Issues Encountered
[For each issue:]
- **Issue**: [Description]
- **Resolution**: [How it was resolved OR "Pending"]
- **Learning**: [What to remember for next time]

## Files Modified
- `[path/to/file]` - [What changed]
- [List all modified files]

## Decisions Made
- [Decision]: [Rationale]
- [List any decisions from this session]

## Next Steps (Recommended)
1. [Most important next action]
2. [Second priority]
3. [Third priority]

## Open Questions
- [Any unresolved questions]
- [Things that need user input]

## Context for Future Parzival
[Anything a new instance would need to know that is not captured above.
Write as if the reader has never seen this project.]

---
*Handoff created by session closeout protocol*
```

---

### 3. Verify Handoff

Read the written file back and verify:
- No sections are empty
- Executive summary is accurate
- Next steps are specific and actionable
- "Context for Future Parzival" contains substantive information

---

### 4. Update SESSION_WORK_INDEX

Add entry to `{oversight_path}/SESSION_WORK_INDEX.md`:

```markdown
### [YYYY-MM-DD]: [Brief Topic]
- **Task**: [Task title]
- **Task ID**: [ID]
- **Status**: [In Progress/Complete/Blocked]
- **Progress**: [One sentence on what was accomplished]
- **Handoff**: `session-logs/SESSION_HANDOFF_{date}.md`
```

## CRITICAL STEP COMPLETION NOTE

ONLY when the handoff is written, verified, and the index is updated, load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Handoff document is created with all sections populated
- No empty or placeholder sections
- SESSION_WORK_INDEX is updated with a reference to the handoff
- Handoff is verified after writing

### ❌ SYSTEM FAILURE:

- Empty or vague handoff sections
- Not verifying the written handoff
- Not updating SESSION_WORK_INDEX
- "Context for Future Parzival" is empty or generic

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
