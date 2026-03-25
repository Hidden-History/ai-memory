---
name: 'step-01b-parzival-bootstrap'
description: 'Retrieve cross-session memory from Qdrant via aim-parzival-bootstrap skill'
nextStepFile: './step-01c-parzival-constraints.md'
---

# Step 1b: Parzival Cross-Session Memory Bootstrap

**Progress: Step 1b of 5** — Next: Load Parzival Behavioral Constraints

## STEP GOAL:

Retrieve cross-session memory from Qdrant to enrich the file-based context loaded in Step 1. This invokes the L1-L4 layered priority retrieval defined in Pipeline-V2 spec.

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

- 🎯 Invoke the bootstrap skill and merge Qdrant results with file-based context
- 🚫 FORBIDDEN to block session start on Qdrant unavailability
- 💬 Approach: Graceful degradation — file context is primary, Qdrant is supplementary
- 📋 All Qdrant-retrieved results must be tagged [Qdrant] to distinguish from file-sourced context

## EXECUTION PROTOCOLS:

- 🎯 Invoke /aim-parzival-bootstrap skill exactly once
- 💾 Tag all Qdrant-retrieved content as [Qdrant] and merge with Step 1 context
- 📖 Load next step only after retrieval is complete or gracefully degraded
- 🚫 FORBIDDEN to retry Qdrant in a loop or block on failure

## CONTEXT BOUNDARIES:

- Available context: File-based context from Step 1
- Focus: Cross-session memory enrichment only — do not compile status yet
- Limits: Qdrant retrieval is supplementary — file context from Step 1 is the primary record
- Dependencies: Organized context from Step 1

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Invoke Cross-Session Memory Retrieval

Run the bootstrap skill:

/aim-parzival-bootstrap

This retrieves (in layer order):
- L1 [DETERMINISTIC]: Last handoff (1) — agent_id=parzival
- L2 [DETERMINISTIC]: Recent decisions (5)
- L3 [SEMANTIC]: Recent insights (3) — agent_id=parzival
- L4 [SEMANTIC]: GitHub enrichment (10) — since last handoff

---

### 2. Process Results

**If skill returns results**: Incorporate the returned context alongside the oversight file context from Step 1. Results are in LAYER ORDER, not score-sorted — present them in that order.

**If skill reports Qdrant unavailable**: Note this and continue. The oversight files loaded in Step 1 are the primary record — Qdrant enrichment is supplementary.

[NOTE] Qdrant unavailable — continuing with file-based context only.

**If skill reports Parzival disabled**: Note this and continue.

[NOTE] Parzival memory disabled — continuing with file-based context only.

---

### 3. Merge Context

Add any Qdrant-retrieved context to the compiled context from Step 1, tagged as [Qdrant] to distinguish from file-sourced context. Do not duplicate information already present from file context.

## CRITICAL STEP COMPLETION NOTE

ONLY when cross-session memory retrieval is complete (or gracefully degraded), load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Bootstrap skill was invoked
- Results were incorporated or unavailability was noted
- No blocking on Qdrant failures
- Context is ready for constraint loading

### ❌ SYSTEM FAILURE:

- Skipping bootstrap entirely without attempting
- Blocking session start because Qdrant is unavailable
- Retrying Qdrant in a loop
- Losing file-based context from Step 1

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
