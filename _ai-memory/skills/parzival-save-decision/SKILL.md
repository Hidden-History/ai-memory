---
name: parzival-save-decision
description: "Save a Parzival session decision to Qdrant for cross-session memory and L2 retrieval"
allowed-tools: Bash
---

Save a Parzival session decision (DEC-PMxxx-D#) to Qdrant for cross-session
retrieval. Closes the long-standing TD-519 / F-002 gap where decisions were
file-only — bootstrap L2 retrieval (`memory_type=["decision"]`) was permanently
empty.

## Canonical Execution

Always run the real script through `run-with-env.sh` so the skill uses the
installed ai-memory virtualenv and the standard local service defaults.

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" parzival_save_decision.py \
    --dec-id PM285-D2 \
    --content "Decision: ... Rationale: ..." \
    --pm-number 285
```

Optional flags:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" parzival_save_decision.py \
    --dec-id PM285-D3 \
    --content "$(cat /tmp/dec.txt)" \
    --rationale "Cited BP-157 §primitive 4" \
    --session-id PM285 \
    --pm-number 285
```

When working from an `ai-memory` repo checkout, `./scripts/memory/run-with-env.sh ...`
is an equivalent contributor shortcut.

## Implementation

- Script: `scripts/memory/parzival_save_decision.py`
- Memory type: `decision` (allowlist extension D-2-A in `src/memory/storage.py`)
- Agent ID: `parzival`
- Storage shape: WHOLE, 1 vector, no chunking, no thresholds, no truncation
  (Chunking-Strategy-V2 §3.3 + §7; guaranteed by content_type_map NOT mapping
  `MemoryType.DECISION` — unmapped types skip the chunker)
- Dedup: SHA-256 `content_hash` via `compute_content_hash()` — re-emit is idempotent
- Failure mode: warn and continue; `decision-log.md` is the primary record
- Per-DEC invocation from session-close `step-04-save-and-confirm.md`

## References

- TECH-DEBT-519 §"Locked design decisions D-1..D-7"
- LEAD-DEV-NOTE-SESSION-45-VERIFICATION-2026-05-07.md §F-002
- Chunking-Strategy-V2 §3.3 (decisions whole-store)
