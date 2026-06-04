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

DEC bodies are multi-line by convention (`Decision: ...\nRationale: ...`)
and frequently contain embedded `"`, `$`, and newlines. Use the
single-quoted heredoc pattern below — single-line `--content "..."` quoting
silently truncates past the first embedded `"`, corrupts the SHA-256
`content_hash`, and defeats the per-DEC dedup contract with no error
signal:

```bash
DEC_BODY=$(cat <<'PARZIVAL_DEC_END'
Decision: <full decision text>
Rationale: <full rationale text, may contain "quotes", $signs, and
multiple lines>
PARZIVAL_DEC_END
)
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" parzival_save_decision.py \
    --dec-id PM285-D2 \
    --content "$DEC_BODY" \
    --pm-number 285
```

The single-quoted terminator (`'PARZIVAL_DEC_END'`) preserves the body
verbatim with no shell variable expansion. The terminator string is
namespace-distinctive — `EOF` is too common a token and could legitimately
appear at column 0 within a DEC body — so accidental early termination is
vanishingly unlikely. The terminator must not appear at column 0 on its
own line within the body.

Alternative (write DEC body to a temp file first):

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
