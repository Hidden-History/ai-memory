---
name: session-decision
description: 'Structure a decision with options, tradeoffs, and recommendation. Present using approval gate format and log the outcome.'
firstStep: './steps-c/step-01-structure-decision.md'
decisionLogTemplate: '{project-root}/_ai-memory/pov/templates/decision-log.template.md'
---

# Decision Request

**Goal:** When a decision is needed, structure it clearly with context, options, tradeoffs, and a recommendation so the user can make an informed choice. Log the outcome for future reference.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

### Decision Anti-Patterns
- Never present a decision with only one option
- Never hide tradeoffs to steer toward a preferred option
- Never skip the "do nothing" option when it is viable
- Never make the decision on behalf of the user
- Never log a decision outcome the user did not explicitly choose
- Never present a decision without stating what constraints apply

---

## Follow-Up Review Protocol

Decisions are not fire-and-forget. Every logged decision must include a scheduled follow-up to close the feedback loop:

- **Schedule**: At the next milestone, after N sessions (default: 3 sessions), or at sprint close — whichever comes first
- **Verify**: Did the expected outcome materialize? Was the rationale sound in hindsight?
- **Update record**: Change `Status` from `Active` to one of: `Validated` (outcome matched expectation), `Superseded` (replaced by a later decision), or `Revised` (outcome required course correction)
- **Log result**: Append outcome note to the original DEC-[ID] entry with date

Follow-up scheduling is enforced at Step 3 (log-decision): every new entry gets a follow-up trigger before the step completes.

---

## Supporting References

- Decision lifecycle states and transitions: `knowledge/decision-status-workflow.md`
- Decision log template: `{project-root}/_ai-memory/pov/templates/decision-log.template.md`
- Multi-perspective consultation: `{project-root}/.claude/skills/bmad-party-mode/SKILL.md` — invoke when a decision benefits from multiple expert viewpoints (complex tradeoffs, architectural choices, risk assessment requiring diverse perspectives)

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}

<!-- ai-memory:degraded-declaration
capability: cap:session-decision
depends_on: bmad
degraded_behaviour: Records the decision normally and reports the BMAD multi-perspective consultation skill as unavailable.
degraded_test: not-yet-enforced
ai-memory:end-degraded-declaration -->
