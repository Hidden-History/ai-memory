---
name: 'step-04-save-and-confirm'
description: 'Attempt Qdrant save with graceful degradation, then present final closeout confirmation'
---

# Step 4: Save to Qdrant and Confirm Closeout

**Final Step — Session Close Complete**

## STEP GOAL:

Attempt to save the handoff and task state to Qdrant for cross-session AI-searchable retrieval. If Qdrant is unavailable, log and continue -- file writes are the primary record. Then present the final closeout confirmation.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Handoff document from Step 3, session summary from Step 1
- Focus: Qdrant save attempts and final closeout confirmation
- Limits: Qdrant save is secondary — NEVER block closeout because Qdrant is unavailable
- Dependencies: Handoff document from Step 3 is required

- Focus on Qdrant save attempts and final closeout confirmation
**Behavioral Constraints:**
- FORBIDDEN to block closeout because Qdrant is unavailable
- Approach: Attempt saves gracefully, present final checklist, handle user requests
- File writes are the primary record — Qdrant is secondary and optional

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

### 3. Emit Decisions to Qdrant (TD-519)

For each DEC entry logged in this session's `PMxxx-D#` block in
`{oversight_path}/tracking/decision-log.md`, invoke the decision save skill
once per DEC:

/parzival-save-decision --dec-id PMxxx-D# --content "<full DEC text>" --pm-number xxx

Optional flags: `--rationale "<separate rationale text>"`, `--session-id <id>`.

**If skill succeeds (per DEC)**: Note Qdrant memory ID in the closeout checklist.

**If Qdrant is unavailable / per-DEC failure**: Log warning, continue —
`decision-log.md` is the primary record. Do NOT retry. Do NOT block. The
script returns 0 even on failure for closeout-continues semantics.

**Storage contract** (Chunking-Strategy-V2 §3.3): decisions store WHOLE
(1 vector, no chunking, no thresholds, no truncation). Re-emit is idempotent
via SHA-256 `content_hash` dedup.

---

### 4. Present Final Closeout Confirmation

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
- [x] Qdrant handoff save: [Success / Skipped -- unavailable]
- [x] Qdrant decision emit: [N saved / Skipped -- unavailable / No new decisions]

Ready for next session. Anything else before we close?
```

---

### 5. Handle Final User Requests

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
