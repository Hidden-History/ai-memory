---
name: 'step-06-cycle-tracking'
description: 'Maintain and update the review cycle pass record for reporting and approval gate handoff'
type: reference
---

# Step 6: Cycle Tracking

## STEP GOAL
Parzival tracks every pass through the review cycle using a structured pass record. This data feeds the user summary and project-status update. This step is called inline from other steps — it is a reference for the tracking format, not a sequential gate.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All pass data accumulated during the review cycle
- Limits: This step defines the tracking format. Actual tracking happens inline during steps 3-5.

## MANDATORY SEQUENCE

### 1. Maintain Pass Record
For each pass through the review cycle, record:

**First Pass:**
- Issues found (total count)
- Legitimate (count with priority breakdown)
- Non-issues (count)
- Uncertain (count)
- Sent to DEV (session marker)
- Fix report received (yes/no)

**Subsequent Passes:**
- Issues found (total count)
- New issues (introduced by fixes)
- Resolved from prior pass (count)
- Still open (count)
- Uncertain resolved (count)

**Final Pass:**
- Issues found: 0
- Cycle complete: YES
- Total passes (count)
- Total issues fixed (count)
- Pre-existing fixes (count)

### 2. Pass Record Format
```
REVIEW CYCLE -- [Task name]

Pass 1:
  Issues found:      [N]
  Legitimate:        [N] ([priorities breakdown])
  Non-issues:        [N]
  Uncertain:         [N]
  Sent to DEV:       [session marker]
  Fix report received: [yes/no]

Pass 2:
  Issues found:      [N]
  New issues:        [N] (introduced by fixes)
  Resolved from P1:  [N]
  Still open:        [N]
  Uncertain resolved: [N]

[Continue for each pass]

Final Pass:
  Issues found:      0
  Cycle complete:    YES
  Total passes:      [N]
  Total issues fixed: [N]
  Pre-existing fixes: [N]
```

### 3. Feed Data Forward
This data feeds into:
- The user summary at task completion
- The project-status.md update
- The approval package for WF-APPROVAL-GATE

## CRITICAL STEP COMPLETION NOTE
This step is a reference step. It does not gate progression. The exit step (step-07) is loaded when step-03 determines zero legitimate issues remain.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every pass is recorded with accurate counts
- Priority breakdowns are tracked for legitimate issues
- New issues from fixes are counted separately
- Pre-existing fixes are counted separately
- Data is available for the approval gate summary

### FAILURE:
- Missing pass records
- Inaccurate issue counts
- Not tracking new issues introduced by fixes
- Not distinguishing pre-existing fixes from current-task fixes
