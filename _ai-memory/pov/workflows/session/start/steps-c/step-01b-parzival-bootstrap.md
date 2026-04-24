---
name: 'step-01b-parzival-bootstrap'
description: 'Retrieve cross-session memory from Qdrant via aim-parzival-bootstrap skill'
nextStepFile: './step-02-compile-status.md'
---

# Step 1b: Parzival Cross-Session Memory Bootstrap

**Progress: Step 1b of 4** — Next: Compile Status Report

## STEP GOAL:

Retrieve cross-session memory from Qdrant to enrich the file-based context loaded in Step 1. This invokes the L1-L4 layered priority retrieval defined in Pipeline-V2 spec.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: File-based context from Step 1
- Focus: Cross-session memory enrichment only — do not compile status yet
- Limits: Qdrant retrieval is supplementary — file context from Step 1 is the primary record
- Dependencies: Organized context from Step 1

- Invoke the bootstrap skill and merge Qdrant results with file-based context
**Behavioral Constraints:**
- FORBIDDEN to block session start on Qdrant unavailability
- Approach: Graceful degradation — file context is primary, Qdrant is supplementary
- All Qdrant-retrieved results must be tagged [Qdrant] to distinguish from file-sourced context

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

### 1b. L1 Handoff Gate

After bootstrap returns, apply the handoff load control-flow. The L1 result from the bootstrap determines whether the handoff is loaded from Qdrant (primary) or from the file system (fallback).

**Pre-gate**: Identify the most recent `SESSION_HANDOFF_*.md` filename under `{oversight_path}/session-logs/` (filename-date extraction only — no file read). Record the date for the staleness check below.

**CASE A — L1 contains `type=agent_handoff, agent_id=parzival`**:
1. Take the record with the most recent timestamp from the L1 results.
2. Compare the L1 record date against the most recent `SESSION_HANDOFF_*.md` filename date.
3. If L1 date ≥ filename date → tag result `[Qdrant:L1-HANDOFF — primary]`. Do NOT read the handoff file. Log that ~4,000 tokens were saved.
4. If L1 date < filename date → signal **FALLBACK-NEEDED** (Qdrant record is stale).

**CASE B — L1 returns no handoff record OR Qdrant is unavailable/error** → signal **FALLBACK-NEEDED**.

**If FALLBACK-NEEDED**: Read the most recent `{oversight_path}/session-logs/SESSION_HANDOFF_*.md` file. Tag its content `[FILE-HANDOFF — fallback]`.

> **Design note (audit Q5 line 576)**: A `MINIMUM_HANDOFF_BYTES` threshold can extend the fallback trigger if L1 truncation omits critical sections (e.g., "Next Steps", "Open Questions"): `OR L1 content_length < MINIMUM_HANDOFF_BYTES → FALLBACK-NEEDED`. This threshold is not wired in this patch; it is a documented future extension.

---

### 2. Process Results

**If skill returns results**: Incorporate the returned context alongside the oversight file context from Step 1. Results are in LAYER ORDER, not score-sorted — present them in that order.

**If skill reports Qdrant unavailable**: Note this and continue. The oversight files loaded in Step 1 are the primary record — Qdrant enrichment is supplementary.

[NOTE] Qdrant unavailable — continuing with file-based context only.

**If skill reports Parzival disabled**: Note this and continue.

[NOTE] Parzival memory disabled — continuing with file-based context only.

---

### 3. Merge Context

Add all retrieved context to the compiled session context. Use the following tags to distinguish sources:
- `[Qdrant:L1-HANDOFF — primary]` — handoff loaded from Qdrant L1 (file read skipped)
- `[FILE-HANDOFF — fallback]` — handoff loaded from filesystem (Qdrant unavailable or stale)
- `[Qdrant]` — all other Qdrant-sourced content (decisions, insights, GitHub enrichment)

Do not duplicate information already present from file context.

---

### 4. Load Sanctum Tier B Files

Load the sanctum files designated for session-start (Tier B):

1. **LORE.md** — Read `{project-root}/_ai-memory/sanctum/parzival/LORE.md`. Internalize as earned project knowledge: architecture, design decisions, validated patterns, project-specific idioms. This supplements Qdrant context with curated, distilled understanding.

2. **BOND.md** — Read `{project-root}/_ai-memory/sanctum/parzival/BOND.md`. Internalize as the system-wide user preference authority: how the user prefers to work, what to avoid, what earns trust. Apply these preferences for the remainder of the session.

**If files not found** (sanctum not yet initialized): Note and continue silently. Sanctum Tier B is supplementary — session-start proceeds without it.

## CRITICAL STEP COMPLETION NOTE

ONLY when cross-session memory retrieval is complete (or gracefully degraded), load and read fully {nextStepFile}
