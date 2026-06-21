# Embedding Service Sizing

The embedding service is **shared across every project on one install**. All projects (and any co-tenant such as a document-ingest pipeline) send their embed requests to the same container, so its memory limit must be sized for your **combined** load, not a single project.

> **Status: provisional.** The numbers below are sized from observed live behaviour and a forthcoming controlled soak (BUG-324). They will be refined; treat them as safe starting points, not final tuning.

## How the service behaves under load

The service degrades gracefully instead of dropping data or crashing:

- **Bounded-queue backpressure** — concurrent inferences are capped by `EMBEDDING_MAX_CONCURRENCY`; excess requests **wait** in a bounded queue (`EMBEDDING_MAX_WAITERS`) rather than being dropped. Only a full queue or an exceeded admission timeout returns a last-resort `503 + Retry-After`, which clients honour and retry — so a transient shed never loses a memory.
- **Memory-aware self-throttle (AIMD)** — a background controller watches cgroup-v2 memory signals and **collapses effective concurrency toward 1** as the container approaches its memory cap, recovering when pressure clears. This prevents the OOM-kill/restart loop.

The practical consequence: if the container is undersized, the service **stays alive but runs slowly** (serialised), because AIMD pins concurrency low to avoid OOM. Sizing memory correctly is what buys you concurrency.

## Memory footprint reality

The two ONNX models are ~3 GB resident, but **anon-RSS climbs well above that under real, diverse payloads** — observed up to ~6 GB on a 2-project shared install. The driver is glibc allocator **arena retention/fragmentation**: freed memory is not promptly returned to the OS, so the footprint climbs and **holds** (it does not fall back at idle). A container **restart** releases it. `MALLOC_ARENA_MAX=2` (set in the image) reduces but does not eliminate this.

## Sizing guidance

Set `EMBEDDING_MEMORY_LIMIT` (in `docker/.env`) by how many projects embed **concurrently** on this install:

| Concurrent projects on the install | `EMBEDDING_MEMORY_LIMIT` | Notes |
|---|---|---|
| 1, light/uniform load | `4G` (unverified) | May suffice, but the footprint above was not validated for diverse payloads — monitor and raise if you see AIMD pinning. |
| 2–3 (multi-repo shared, incl. a doc-ingest co-tenant) | **`6G` (default)** | Survives observed real mixed load; expect AIMD to throttle toward serial under bursts. |
| Many / heavy / large code files | `8G`+ **or isolate** | Either raise the cap, or run a dedicated embedding service per heavy project. |

If you routinely see `embedding_effective_concurrency_limit` pinned at `1` and `embedding_memory_headroom_bytes` near zero (Prometheus), the cap is too low for your load — raise it or reduce `EMBEDDING_MAX_CONCURRENCY`.

## Related knobs (`docker/.env`)

- `EMBEDDING_MEMORY_LIMIT` — container memory cap (this doc).
- `EMBEDDING_MAX_CONCURRENCY` — peak simultaneous inferences (default 4).
- `EMBEDDING_MAX_WAITERS` — bounded admission queue depth before a 503 shed (default 64).
- `EMBEDDING_RETRY_AFTER` — `Retry-After` seconds returned on a shed (default 5).
- `EMBEDDING_INFERENCE_THREADS` / `OMP_NUM_THREADS` — intra-op thread bounds (footprint control).

## Applying a change

`EMBEDDING_MEMORY_LIMIT` is a Compose value, **not** baked into the image — to change it, edit `docker/.env` and restart the stack; **no image rebuild is needed**:

```
# edit docker/.env: EMBEDDING_MEMORY_LIMIT=8G
~/.ai-memory/scripts/stack.sh restart
```

(Changes to embedding *code or dependencies* do require a rebuild — see the v2.8.0 upgrade instructions in CHANGELOG.md.)
