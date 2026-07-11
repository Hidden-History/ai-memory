# Embedding Service Sizing

The embedding service is **shared across every project on one install**. All projects (and any co-tenant such as a document-ingest pipeline) send their embed requests to the same container, so its memory limit must be sized for your **combined** load, not a single project.

> **Status: provisional.** The numbers below are sized from observed live behaviour, now including the BUG-324 idle-watch diagnostic (2026-06-21). Treat them as safe starting points, not final tuning — the active-release fix that would let the memory cap hold indefinitely under sustained load is a tracked follow-up (see *Memory footprint reality*).

## How the service behaves under load

The service degrades gracefully instead of dropping data or crashing:

- **Bounded-queue backpressure** — concurrent inferences are capped by `EMBEDDING_MAX_CONCURRENCY`; excess requests **wait** in a bounded queue (`EMBEDDING_MAX_WAITERS`) rather than being dropped. Only a full queue or an exceeded admission timeout returns a last-resort `503 + Retry-After`, which clients honour and retry — so a transient shed never loses a memory.
- **Memory-aware self-throttle (AIMD)** — a background controller watches cgroup-v2 memory signals and **collapses effective concurrency toward 1** as the container approaches its memory cap, recovering when pressure clears. This prevents the OOM-kill/restart loop. It is a runtime safety net: it throttles *new* work, but it does **not** return memory the allocator already holds (see *Memory footprint reality*).

The practical consequence: if the container is undersized, the service **stays alive but runs slowly** (serialised), because AIMD pins concurrency low to avoid OOM. Sizing memory correctly is what buys you concurrency.

## Memory footprint reality

The two ONNX models are ~3 GB resident, but **anon-RSS climbs well above that under real, diverse payloads** — observed pinned near the 6 GiB cap on a multi-project shared install (an OOM-killed worker was recorded at ~5.92 GiB anon-RSS). The driver is glibc allocator **arena retention**: as concurrent, diverse payloads are embedded, per-thread arenas plus working set grow, and the freed memory is not promptly returned to the OS, so the footprint climbs and **holds** (it does not fall back at idle). `MALLOC_ARENA_MAX=2` (set in the image) reduces but does not eliminate this.

This is **load-induced, not an idle leak** (BUG-324, 2026-06-21). A 7-hour zero-load watch held **flat** at a loaded-idle baseline of ~3.10 GiB — no climb, no OOMs, no restarts — ruling out a leak that grows on its own. What drives the footprint to the cap is *sustained, mixed load* across projects accumulating un-returned arenas across bursts; left unchecked it reaches the cap and triggers the OOM-kill/restart loop. The held memory **is** reclaimable: a container **restart** releases roughly ~2.9 GiB above the loaded-idle baseline, dropping a pinned-at-6-GiB container back to ~3.10 GiB.

Because the residue only releases on a recycle today, an **active-release lever** — periodic `malloc_trim` / a tuned `MALLOC_TRIM_THRESHOLD`, and/or an RSS-threshold worker recycle — is the missing piece. It is a tracked follow-up on BUG-324 and is **not shipped in v2.8.0**; until it lands, a manual `stack.sh restart` is the way to reclaim a pinned container.

## Sizing guidance

`EMBEDDING_MEMORY_LIMIT` (in `docker/.env`) ships at **`10G`, and 10G is also the floor** — it is the design basis of the byte-aware admission envelope, not a value to trim. The envelope is sized against a 10 GiB cap: warm base ~2.35 GiB + ~5.6 GiB in-flight char budget = ~7.95 GiB worst-case peak, leaving ~2 GiB headroom. Shipping (or shrinking to) a smaller cap puts the envelope's designed peak above the limit and re-introduces the exact OOM this sizing prevents, so `EMBEDDING_MAX_INPUT_CHARS` / `EMBEDDING_SAFE_INFLIGHT_CHARS` and the cap must move together.

Raise the cap by how many projects embed **concurrently** on this install:

| Concurrent projects on the install | `EMBEDDING_MEMORY_LIMIT` | Notes |
|---|---|---|
| 1–3 (typical multi-repo shared, incl. a doc-ingest co-tenant) | **`10G` (default — the envelope basis, and the floor)** | The admission envelope is sized against this cap (peak ~7.95 GiB, ~2 GiB headroom). Do not drop below `10G` without lowering the char envelope in lockstep, or the designed peak exceeds the cap. |
| Many / heavy / large code files | `12G`+ **or isolate** | Either raise the cap (and the char envelope with it), or run a dedicated embedding service per heavy project. |

If you routinely see `embedding_effective_concurrency_limit` pinned at `1` and `embedding_memory_headroom_bytes` near zero (Prometheus), the cap is too low for your load — raise it or reduce `EMBEDDING_MAX_CONCURRENCY`.

## Related knobs (`docker/.env`)

- `EMBEDDING_MEMORY_LIMIT` — container memory cap (this doc).
- `EMBEDDING_MAX_CONCURRENCY` — peak simultaneous inferences (default 4).
- `EMBEDDING_MAX_WAITERS` — bounded admission queue depth before a 503 shed (default 64).
- `EMBEDDING_RETRY_AFTER` — `Retry-After` seconds returned on a shed (default 5).
- `EMBEDDING_INFERENCE_THREADS` / `OMP_NUM_THREADS` — intra-op thread bounds (footprint control).

> **Known follow-up:** there is currently **no** knob that *returns* held memory after load. Active release — periodic `malloc_trim` / a tuned `MALLOC_TRIM_THRESHOLD`, or an RSS-threshold worker recycle — is a tracked BUG-324 follow-up, not yet shipped. Until it lands, a `stack.sh restart` is the way to reclaim a pinned container.

## Applying a change

`EMBEDDING_MEMORY_LIMIT` is a Compose value, **not** baked into the image — to change it, edit `docker/.env` and restart the stack; **no image rebuild is needed**:

```
# edit docker/.env: EMBEDDING_MEMORY_LIMIT=8G
~/.ai-memory/scripts/stack.sh restart
```

(Changes to embedding *code or dependencies* do require a rebuild — see the v2.8.0 upgrade instructions in CHANGELOG.md.)
