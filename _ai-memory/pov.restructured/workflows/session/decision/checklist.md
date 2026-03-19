---
name: 'session-decision-checklist'
description: 'Quality gate rubric for session-decision'
---

# Session Decision — Validation Checklist

## Pre-Execution Checks

- [ ] Decision trigger is clearly identified (not a blocker — use blocker workflow for those)
- [ ] Decision requires user input before work can proceed

## Step Completion Checks

### Step 1: Structure Decision (step-01-structure-decision)
- [ ] Decision is framed with clear context and trigger
- [ ] At least 2 options are generated with full tradeoff analysis
- [ ] Applicable constraints are identified and referenced
- [ ] Comparison matrix enables side-by-side evaluation
- [ ] Recommendation includes confidence level and unknowns

### Step 2: Present Decision (step-02-present-decision)
- [ ] Decision is presented in the defined approval gate format
- [ ] User makes the decision, not Parzival
- [ ] User's choice and rationale are recorded
- [ ] Additional information is provided when requested

### Step 3: Log Decision (step-03-log-decision)
- [ ] Decision is logged with all required fields
- [ ] Entry accurately reflects the user's choice
- [ ] Related tracking files are noted for update
- [ ] User is informed of the logged entry

## Workflow-Level Checks

- [ ] User explicitly chose an option
- [ ] Decision logged to decision log
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT present only one option
- [ ] Did NOT omit tradeoffs or constraint analysis
- [ ] Did NOT hide unknowns that could affect the decision
- [ ] Did NOT pre-decide by presenting options with obvious bias
- [ ] Did NOT present without stating confidence level
- [ ] Did NOT skip the "do nothing" option when viable
- [ ] Did NOT present in a non-standard format
- [ ] Did NOT execute an option without user approval
- [ ] Did NOT steer the user toward a specific option beyond the stated recommendation
- [ ] Did NOT proceed without a clear user decision
- [ ] Did NOT log a decision the user did not make
- [ ] Did NOT omit options that were considered from the log
- [ ] Did NOT fail to confirm the logged entry with the user
- [ ] Did NOT make the decision on behalf of the user
- [ ] Did NOT fail to append to the decision log

_Validated by: Parzival Quality Gate on {date}_
