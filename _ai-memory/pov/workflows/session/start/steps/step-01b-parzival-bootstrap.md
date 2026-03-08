---
name: 'step-01b-parzival-bootstrap'
description: 'Retrieve cross-session memory from Qdrant via aim-parzival-bootstrap skill'
nextStepFile: './step-01c-parzival-constraints.md'
---

# Step 1b: Parzival Cross-Session Memory Bootstrap

## STEP GOAL
Retrieve cross-session memory from Qdrant to enrich the file-based context loaded in Step 1. This invokes the L1-L4 layered priority retrieval defined in Pipeline-V2 spec.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: File-based context from Step 1
- Limits: Qdrant retrieval is supplementary — file context from Step 1 is the primary record

## MANDATORY SEQUENCE

### 1. Invoke Cross-Session Memory Retrieval

Run the bootstrap skill:

/aim-parzival-bootstrap

This retrieves (in layer order):
- L1 [DETERMINISTIC]: Last handoff (1) — agent_id=parzival
- L2 [DETERMINISTIC]: Recent decisions (5)
- L3 [SEMANTIC]: Recent insights (3) — agent_id=parzival
- L4 [SEMANTIC]: GitHub enrichment (10) — since last handoff

### 2. Process Results

**If skill returns results**: Incorporate the returned context alongside the oversight file context from Step 1. Results are in LAYER ORDER, not score-sorted — present them in that order.

**If skill reports Qdrant unavailable**: Note this and continue. The oversight files loaded in Step 1 are the primary record — Qdrant enrichment is supplementary.

[NOTE] Qdrant unavailable — continuing with file-based context only.

**If skill reports Parzival disabled**: Note this and continue.

[NOTE] Parzival memory disabled — continuing with file-based context only.

### 3. Merge Context

Add any Qdrant-retrieved context to the compiled context from Step 1, tagged as [Qdrant] to distinguish from file-sourced context. Do not duplicate information already present from file context.

## CRITICAL STEP COMPLETION NOTE
ONLY when cross-session memory retrieval is complete (or gracefully degraded), load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Bootstrap skill was invoked
- Results were incorporated or unavailability was noted
- No blocking on Qdrant failures
- Context is ready for constraint loading

### FAILURE:
- Skipping bootstrap entirely without attempting
- Blocking session start because Qdrant is unavailable
- Retrying Qdrant in a loop
- Losing file-based context from Step 1
