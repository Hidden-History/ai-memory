---
name: 'step-03-log-decision'
description: 'Log the decision outcome to the decision tracking log'
decisionLogTemplate: '{project-root}/_ai-memory/pov/templates/decision-log.template.md'
---

# Step 3: Log Decision

**Final Step — Decision Support Complete**

## STEP GOAL:

Record the decision, the options considered, and the user's choice in the decision log for future reference and traceability.

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

- 🎯 Focus on accurate logging of the decision and all options considered
- 🚫 FORBIDDEN to log a decision the user did not explicitly make
- 💬 Approach: Factual logging with full field completion; note related tracking impacts
- 📋 Reference decision in related tracking files where applicable

## EXECUTION PROTOCOLS:

- 🎯 Append complete decision entry to decision-log.md with all required fields
- 💾 Note related tracking updates (task, architecture, blocker) where applicable
- 📖 Present confirmation to user after logging
- 🚫 FORBIDDEN to editorialize — log the facts only

## CONTEXT BOUNDARIES:

- Available context: Structured decision from Step 1, user's choice from Step 2
- Focus: Decision logging only — no further analysis
- Limits: Log the facts — do not editorialize
- Dependencies: Decision structure from Step 1 and user's explicit choice from Step 2

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Load Decision Log Template

If `{decisionLogTemplate}` exists, use it as the format for the entry. Otherwise, use the format below.

---

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

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- Append decision entry to decision-log.md with all required fields before confirming
- Note any related tracking updates (task tracker, architecture decisions, blocker log)
- Present confirmation to user and await their direction to continue work

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Decision is logged with all required fields
- Entry accurately reflects the user's choice
- Related tracking files are noted for update
- User is informed of the logged entry

### ❌ SYSTEM FAILURE:

- Logging a decision the user did not make
- Omitting options that were considered
- Failing to append to the decision log
- Not confirming the logged entry with the user

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
