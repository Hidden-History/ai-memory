---
name: 'step-04-save-and-confirm'
description: 'Attempt Qdrant save with graceful degradation, then present final closeout confirmation'
---

# Step 4: Save to Qdrant and Confirm Closeout

**Final Step — Session Close Complete**

## STEP GOAL:

Attempt to save the handoff and task state to Qdrant for cross-session AI-searchable retrieval. If Qdrant is unavailable, log and continue -- file writes are the primary record. Then present the final closeout confirmation.

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

- 🎯 Focus on Qdrant save attempts and final closeout confirmation
- 🚫 FORBIDDEN to block closeout because Qdrant is unavailable
- 💬 Approach: Attempt saves gracefully, present final checklist, handle user requests
- 📋 File writes are the primary record — Qdrant is secondary and optional

## EXECUTION PROTOCOLS:

- 🎯 Attempt both Qdrant saves before presenting final confirmation
- 💾 Present accurate closeout checklist reflecting all session work completed
- 📖 This is a terminal step — no next step to load
- 🚫 FORBIDDEN to retry Qdrant in a loop or block closeout if unavailable

## CONTEXT BOUNDARIES:

- Available context: Handoff document from Step 3, session summary from Step 1
- Focus: Qdrant save attempts and final closeout confirmation
- Limits: Qdrant save is secondary — NEVER block closeout because Qdrant is unavailable
- Dependencies: Handoff document from Step 3 is required

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Attempt Qdrant Handoff Save

Invoke the handoff save skill:

/parzival-save-handoff --file {handoff_path}

Where {handoff_path} is the file created in Step 3 (e.g., `{oversight_path}/session-logs/SESSION_HANDOFF_{date}.md`).

**If skill succeeds**: Note the Qdrant memory ID in the closeout checklist.

**If Qdrant is unavailable**: Log a warning:
```
[WARN] Qdrant unavailable -- handoff NOT saved to vector store. File write is the primary record.
```
Continue with closeout. Do NOT retry. Do NOT block.

---

### 2. Attempt Qdrant Task State Save

Invoke the insight save skill with current task state:

/parzival-save-insight "Active task: [TASK_ID] [TITLE] - [STATUS]. Next: [NEXT_STEP]. Key decisions: [DECISIONS]. Blockers: [BLOCKERS]."

**If skill succeeds**: Note success.

**If Qdrant is unavailable**: Log same warning pattern. Continue.

---

### 3. Present Final Closeout Confirmation

```
## Session Closeout Complete

**Handoff**: `{oversight_path}/session-logs/SESSION_HANDOFF_{date}.md`
**Index Updated**: Yes
**Qdrant**: [Saved / Unavailable -- file is primary record]

### Summary
- [Key accomplishments from this session]
- [Current project state]
- [Recommended next steps]

### Checklist
- [x] Handoff document created
- [x] Session work index updated
- [x] Task status updates: [Applied / Pending user approval]
- [x] Decision log: [Updated / No new decisions]
- [x] Blockers log: [Updated / No new blockers]
- [x] Qdrant save: [Success / Skipped -- unavailable]

Ready for next session. Anything else before we close?
```

---

### 4. Handle Final User Requests

If the user has additional items:
- Address them before confirming closure
- Update handoff if significant new information is added

If the user confirms closure:
- Session is complete
- No further actions unless the user initiates a new workflow

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — session closeout completion required
- Attempt Qdrant save for cross-session memory (graceful degradation if unavailable)
- Present final closeout confirmation with session summary
- File writes are the primary record — Qdrant is supplementary
- Session is formally closed after user confirmation

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Qdrant save is attempted but does not block closeout if unavailable
- Final confirmation includes accurate checklist
- User has opportunity to add final items
- Session ends cleanly with all tracking current

### ❌ SYSTEM FAILURE:

- Blocking closeout because Qdrant is unavailable
- Retrying Qdrant save in a loop
- Presenting incomplete checklist
- Ending session without user confirmation
- Not offering the user a chance for final items

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
