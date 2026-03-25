---
name: 'session-decision-instructions'
description: 'Decision support: structure options with tradeoffs, facilitate user choice, record to decision log'
---

# session-decision — Instructions

## Prerequisites

- An active Parzival oversight session
- `decision-log.md` exists in the oversight workspace
- A decision has been identified that requires structured options and user approval

## Workflow Overview

Session-decision structures a decision clearly — with context, options, tradeoffs, and a recommendation — so the user can make an informed choice. The workflow enforces that decisions are never made on behalf of the user and that all relevant options (including "do nothing" when viable) are presented.

After the user decides, the outcome is logged with a DEC-ID for future reference. Decisions logged here become part of the project's decision history and inform future Parzival sessions through memory retrieval.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-structure-decision.md` | Define the decision context, enumerate all viable options with tradeoffs, identify constraints |
| 2 | `step-02-present-decision.md` | Present structured decision to user with Parzival's recommendation and reasoning; halt for user choice |
| 3 | `step-03-log-decision.md` | Assign DEC-ID, record the user's decision and rationale in `decision-log.md` |

## Key Decisions

- **Option completeness**: Must include at least two options; "do nothing" must be listed when it is a valid choice
- **Tradeoff transparency**: Tradeoffs must not be hidden or minimized to steer toward a preferred option
- **Decision authority**: Parzival recommends; the user decides — never the reverse
- **DEC-ID assignment**: Sequential; Parzival reads existing log to determine the next ID

## Outputs

- Structured decision presented to the user with options, tradeoffs, and recommendation
- Decision outcome logged in `decision-log.md` with assigned DEC-ID

## Exit Conditions

The workflow exits when:
- The user has made an explicit decision
- The decision has been written to `decision-log.md` with a DEC-ID
