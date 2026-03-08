---
name: 'step-01c-parzival-constraints'
description: 'Load behavioral constraints via aim-parzival-constraints skill'
nextStepFile: './step-02-compile-status.md'
---

# Step 1c: Load Parzival Behavioral Constraints

## STEP GOAL
Load and internalize behavioral constraints as active rules for this session. This ensures GC-01 through GC-13 are actively enforced.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: File and Qdrant context from Steps 1 and 1b
- Limits: Constraints are behavioral rules, not data — they govern how Parzival acts, not what information is available

## MANDATORY SEQUENCE

### 1. Invoke Constraint Loading

Run the constraints skill with phase if known:

/aim-parzival-constraints --phase {current_phase}

If no phase is known from context, run without --phase:

/aim-parzival-constraints

### 2. Internalize Constraints

**If skill returns constraints**: Read and internalize each constraint as an active behavioral rule for this session. These supplement the global constraints already loaded at Parzival activation.

**If skill reports no constraints found**: Note and continue — the global constraints loaded during Parzival activation (from _ai-memory/pov/constraints/global/constraints.md) provide the baseline. The skill adds phase-specific constraints on top.

**If skill fails**: Note the failure and continue with activation-loaded constraints only.

[NOTE] Constraint skill unavailable — using activation-loaded global constraints.

### 3. Confirm Active Constraint Set

Briefly note which constraint sets are active:
- Global constraints (GC-01 through GC-13): Always active from activation
- Phase constraints: Active if loaded by skill, or N/A if no phase determined

## CRITICAL STEP COMPLETION NOTE
ONLY when constraints are loaded (or gracefully degraded), load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Constraint skill was invoked
- Constraints were internalized or fallback was noted
- Active constraint set is documented
- No blocking on skill failures

### FAILURE:
- Skipping constraint loading entirely
- Blocking session start because skill failed
- Not noting which constraints are active
- Overriding global constraints with phase constraints (they are additive)
