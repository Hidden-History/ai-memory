---
name: 'step-03-update-index'
description: 'Update the SESSION_WORK_INDEX with a reference to the new handoff and confirm to the user'
---

# Step 3: Update Index and Confirm

**Final Step — Handoff Complete**

## STEP GOAL:

Add a reference to the new handoff in the SESSION_WORK_INDEX and confirm to the user that the snapshot is complete. The session continues after this.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The handoff file path and content from Step 2
- Focus: Saving to Qdrant, updating the index, and confirming the snapshot to the user
- Limits: Update the index and confirm — do not end the session
- Dependencies: Step 2 must be complete — handoff file written and verified

- Focus on saving to Qdrant, updating the index, and confirming to the user
**Behavioral Constraints:**
- FORBIDDEN to run closeout procedures or treat this as a session end
- Approach: Update index then confirm to user — session continues after snapshot
- This is a snapshot, not a session termination — work resumes after confirmation

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Save Handoff to Qdrant

Run `/parzival-save-handoff --file {handoff_path}` where `{handoff_path}` is the path to the handoff document created in Step 2.

The skill handles:
- Storing the handoff as `agent_handoff` type with `agent_id=parzival`
- Graceful degradation if Qdrant is unavailable (logs warning, does not block)
- Prometheus metrics and Langfuse tracing

**If the skill reports Qdrant unavailable**: Note the warning and continue. The file write from Step 2 is the primary record. Qdrant is supplementary enrichment for cross-session semantic search.

---

### 2. Update SESSION_WORK_INDEX

Add or update entry in `{oversight_path}/SESSION_WORK_INDEX.md`:

```markdown
### [YYYY-MM-DD]: [Brief Topic] (Snapshot)
- **Task**: [Task title]
- **Task ID**: [ID]
- **Status**: In Progress
- **Progress**: [One sentence on current state]
- **Snapshot**: `session-logs/SESSION_HANDOFF_{date}.md`
```

---

### 3. Confirm to User

Present:

```
State snapshot created: `{oversight_path}/session-logs/SESSION_HANDOFF_{date}.md`
Index updated: `{oversight_path}/SESSION_WORK_INDEX.md`

Session continues. This snapshot can be used to:
- Recover if context degrades
- Resume if session is interrupted
- Reference what has been established so far

Continue with current work?
```

---

### 4. Session Continues

This is NOT a session end. The session continues after the snapshot.
- Do not run closeout procedures
- Do not update task statuses
- Do not ask about documentation updates
- Resume working on whatever was in progress

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- Update SESSION_WORK_INDEX with snapshot reference
- Confirm snapshot location to user
- Resume session — do NOT run closeout or terminate the session
