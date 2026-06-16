---
name: 'step-03-log-decision'
description: 'Log the decision outcome to the decision tracking log'
decisionLogTemplate: '{project-root}/_ai-memory/pov/templates/decision-log.template.md'
---

# Step 3: Log Decision

**Final Step — Decision Support Complete**

## STEP GOAL:

Record the decision, the options considered, and the user's choice in the decision log for future reference and traceability.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Structured decision from Step 1, user's choice from Step 2
- Focus: Decision logging only — no further analysis
- Limits: Log the facts — do not editorialize
- Dependencies: Decision structure from Step 1 and user's explicit choice from Step 2

- Focus on accurate logging of the decision and all options considered
**Behavioral Constraints:**
- FORBIDDEN to log a decision the user did not explicitly make
- Approach: Factual logging with full field completion; note related tracking impacts
- Reference decision in related tracking files where applicable

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Load Decision Log Template

If `{decisionLogTemplate}` exists, use it as the format for the entry. Otherwise, use the format below.

---

### 2. Write Decision Entry

**Prepend** the new entry at the TOP of the `## Decisions` section (newest-first) of `{oversight_path}/tracking/decision-log.md` — the seed contract and the `aim-tracking-rotate` skill both require newest-at-top; appending at the bottom would cause rotation to archive the newest decisions:

```markdown
### DEC-[next sequential number]: [Decision Topic]
- **Date**: [YYYY-MM-DD]
- **Context**: [Why this decision was needed]
- **Options Considered**: [Brief list of all options]
- **Decision**: [Which option was chosen]
- **Rationale**: [User's reasoning, or Parzival's recommendation rationale if user did not state one]
- **Confidence**: [Verified/Informed/Inferred]
- **Reversibility**: [Easy/Moderate/Difficult/Irreversible]
- **Status**: [Active/Superseded]
```

---

### 3. Update Related Tracking (If Applicable)

If the decision affects:
- **A task**: Note the decision ID in the task tracker entry
- **Architecture**: Note that an architecture decision record may be needed at `{oversight_path}/decisions/`
- **A blocker**: Reference the decision in the blocker log entry

---

### 4. Confirm Logging

Present confirmation to the user:

```
Decision logged: DEC-[ID] in `{oversight_path}/tracking/decision-log.md`
Decision: [Option chosen]

[If architectural]: Consider creating a full architecture decision record.

Continue with current work?
```

---

### 5. Schedule Follow-Up Review

Every decision must have a closed feedback loop. Before completing this step:

1. **Set follow-up trigger**: Choose the review point — next milestone, after [N] sessions (default: 3), or at a specific sprint close
2. **Append to DEC-[ID] entry**: Add these lines to the log entry:
   - `Follow-Up Scheduled:` [trigger — e.g., "Sprint 4 close" or "after 3 sessions"]
   - `Outcome:` pending — fill at follow-up time
   - `Status:` Active
3. **Note in handoff**: Include the follow-up trigger in the session handoff/close notes so it survives session boundaries
4. **At follow-up time** (future session): Update the DEC-[ID] entry:
   - `Outcome:` [what actually happened — did the expected result materialize?]
   - `Status:` Validated | Superseded | Revised (with date and brief note)

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- Prepend decision entry to the top of decision-log.md with all required fields before confirming
- Follow-up trigger MUST be set in the entry (Section 5) before step completes
- Note any related tracking updates (task tracker, architecture decisions, blocker log)
- Present confirmation to user and await their direction to continue work
