---
name: 'step-03-log-decision'
description: 'Log the decision outcome to the decision tracking log'
decisionLogTemplate: '{project-root}/_ai-memory/pov/templates/decision-log.template.md'
---

# Step 3: Log Decision

## STEP GOAL
Record the decision, the options considered, and the user's choice in the decision log for future reference and traceability.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Structured decision from Step 1, user's choice from Step 2
- Limits: Log the facts -- do not editorialize

## MANDATORY SEQUENCE

### 1. Load Decision Log Template

If `{decisionLogTemplate}` exists, use it as the format for the entry. Otherwise, use the format below.

### 2. Write Decision Entry

Append to `{oversight_path}/tracking/decision-log.md`:

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

### 3. Update Related Tracking (If Applicable)

If the decision affects:
- **A task**: Note the decision ID in the task tracker entry
- **Architecture**: Note that an architecture decision record may be needed at `{oversight_path}/decisions/`
- **A blocker**: Reference the decision in the blocker log entry

### 4. Confirm Logging

Present confirmation to the user:

```
Decision logged: DEC-[ID] in `{oversight_path}/tracking/decision-log.md`
Decision: [Option chosen]

[If architectural]: Consider creating a full architecture decision record.

Continue with current work?
```

## CRITICAL STEP COMPLETION NOTE
This is a **terminal step**. The workflow is complete once the decision is logged and confirmed.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Decision is logged with all required fields
- Entry accurately reflects the user's choice
- Related tracking files are noted for update
- User is informed of the logged entry

### FAILURE:
- Logging a decision the user did not make
- Omitting options that were considered
- Failing to append to the decision log
- Not confirming the logged entry with the user
