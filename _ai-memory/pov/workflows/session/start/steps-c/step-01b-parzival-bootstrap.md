---
name: 'step-01b-parzival-bootstrap'
description: 'Retrieve cross-session memory from Qdrant via aim-parzival-bootstrap skill'
nextStepFile: './step-02-compile-status.md'
---

# Step 1b: Parzival Cross-Session Memory Bootstrap

**Progress: Step 1b of 5** — Next: Compile Status Report

## STEP GOAL:

Retrieve cross-session memory from Qdrant to enrich the file-based context loaded in Step 1. This invokes the L1-L4 layered priority retrieval defined in Pipeline-V2 spec.

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

## Sequence

### 1. Invoke Cross-Session Memory Retrieval

Run the bootstrap skill:

/aim-parzival-bootstrap

This retrieves (in layer order, Qdrant only — the L4 GitHub layer was removed from bootstrap in TASK-077 A1):
- L1 [DETERMINISTIC]: Last handoff (1) — agent_id=parzival
- L2 [DETERMINISTIC]: Recent decisions (5)
- L3 [SEMANTIC]: Recent insights (3) — agent_id=parzival

---

### 1b. L1 Handoff Gate

After bootstrap returns, apply the handoff load control-flow. The L1 result from the bootstrap determines whether the handoff is loaded from Qdrant (primary) or from the file system (fallback).

**Pre-gate**: Identify the most recent `SESSION_HANDOFF_*.md` filename under `{oversight_path}/session-logs/` (filename-date extraction only — no file read). Record the date for the staleness check below.

**CASE A — L1 contains `type=agent_handoff, agent_id=parzival`**:
1. Take the record with the most recent timestamp from the L1 results.
2. Compare the L1 record date against the most recent `SESSION_HANDOFF_*.md` filename date.
3. If L1 date ≥ filename date → tag result `[Qdrant:L1-HANDOFF — primary]`. Do NOT read the handoff file. Log that ~4,000 tokens were saved.
4. If L1 date < filename date → signal **FALLBACK-NEEDED** (Qdrant record is stale).

**CASE B — L1 returns no handoff record OR Qdrant is unavailable/error OR bootstrap output contains a `[FALLBACK-NEEDED: ...]` marker as the first line of the Cross-Session Memory section** → signal **FALLBACK-NEEDED**.

The marker is emitted by the bootstrap skill (BUG-297 / BP-158 P2) when a handoff-class result is rejected by either the Layer 1 per-tier ceiling (`reason=ceiling_exceeded`) or the snippet token budget (`reason=budget_exceeded`). Marker format: `[FALLBACK-NEEDED: reason=<R> type=agent_handoff tokens=<N> budget=<B>]`. Treat its presence the same as "no handoff record returned" — proceed to filesystem fallback.

**If FALLBACK-NEEDED**: Read the most recent `{oversight_path}/session-logs/SESSION_HANDOFF_*.md` file. Tag its content `[FILE-HANDOFF — fallback]`.

> **Design note (audit Q5)**: A `MINIMUM_HANDOFF_BYTES` threshold can extend the fallback trigger if L1 truncation omits critical sections (e.g., "Next Steps", "Open Questions"): `OR L1 content_length < MINIMUM_HANDOFF_BYTES → FALLBACK-NEEDED`. This threshold is not wired in this patch; it is a documented future extension.

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

### 4. Load Sanctum Tier B Files (Session Loader — capped)

Run the session loader, sanctum scope — a single consolidated, capped load that runs AFTER the Qdrant section above, per the approved A2 order:

```bash
python3 {skills_path}/aim-parzival-loader/session_loader.py "{project-root}" --scope sanctum
```

It emits, in the approved A2 order:

1. **LORE.md** — a recency-weighted slice: the structural sections (System Architecture + Key Design Decisions + Patterns & Conventions) + the most-recent "Things Learned the Hard Way" lessons up to the 25 KB budget + a pointer to the full LORE.md. Internalize as earned project knowledge.
2. **BOND.md** — full (vital floor: Owner + Things They've Asked Me to Remember + Things to Avoid). Internalize as the system-wide user-preference authority; apply for the remainder of the session.
3. **MEMORY.md** (sanctum) — full (tiny). The Tier-B identity file — NOT the Claude-Code auto-memory `~/.claude/projects/<slug>/memory/MEMORY.md`.

**If files not found** (sanctum not yet initialized): the loader emits `(absent)` markers and continues. Sanctum Tier B is supplementary — session-start proceeds without it.

> **Reference**: For keeping the Claude Code per-project auto-memory directory (`~/.claude/projects/<project>/memory/MEMORY.md`) lean, see the lazy-loaded reference `{project-root}/_ai-memory/pov/references/auto-memory-best-practices.md`.

## CRITICAL STEP COMPLETION NOTE

ONLY when cross-session memory retrieval is complete (or gracefully degraded), load and read fully {nextStepFile}
