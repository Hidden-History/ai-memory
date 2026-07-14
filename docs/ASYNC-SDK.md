# AsyncSDKWrapper — Agent SDK Integration

The `AsyncSDKWrapper` provides full async/await support for building custom Agent SDK agents with persistent memory backed by AI Memory.

**Source:** `src/memory/async_sdk_wrapper.py`
**Examples:** `examples/async_sdk_basic.py`, `examples/async_sdk_streaming.py`, `examples/async_sdk_rate_limiting.py`

---

## Features

- Full async/await support compatible with Agent SDK
- Rate limiting with token bucket algorithm (Tier 1 default: 50 RPM, 30K TPM)
- Exponential backoff retry with jitter (3 retries: 1s, 2s, 4s ±20%)
- Automatic conversation capture to `discussions` collection
- Background storage (fire-and-forget)
- Prometheus metrics integration

---

## Prerequisites

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

Python 3.11+ required.

---

## Basic Usage

```python
import asyncio
from src.memory import AsyncSDKWrapper

async def main():
    async with AsyncSDKWrapper(cwd="/path/to/project") as wrapper:
        result = await wrapper.send_message(
            prompt="What is async/await?",
            model="claude-sonnet-4-5-20250929",
            max_tokens=500
        )
        print(f"Response: {result['content']}")
        print(f"Session ID: {result['session_id']}")

asyncio.run(main())
```

## Streaming Responses (Buffered)

> **Note**: Current implementation buffers the full response for retry reliability. True progressive streaming is planned for a future release.

```python
async with AsyncSDKWrapper(cwd="/path/to/project") as wrapper:
    async for chunk in wrapper.send_message_buffered(
        prompt="Explain Python async",
        model="claude-sonnet-4-5-20250929",
        max_tokens=800
    ):
        print(chunk, end='', flush=True)
```

## Custom Rate Limits

```python
async with AsyncSDKWrapper(
    cwd="/path/to/project",
    requests_per_minute=100,   # Tier 2
    tokens_per_minute=100000   # Tier 2
) as wrapper:
    result = await wrapper.send_message("Hello!")
```

---

## Rate Limiting

Implements token bucket algorithm matching Anthropic's rate limits:

| Tier | Requests/Min | Tokens/Min |
|------|-------------|------------|
| Free | 5 | 10,000 |
| Tier 1 (default) | 50 | 30,000 |
| Tier 2 | 100 | 100,000 |
| Tier 3+ | 1,000+ | 400,000+ |

Circuit breaker protections:
- Max queue depth: 100 requests
- Queue timeout: 60 seconds
- Raises `QueueTimeoutError` or `QueueDepthExceededError` if exceeded

---

## Retry Strategy

Automatic exponential backoff retry:

- Max retries: 3
- Delays: 1s, 2s, 4s (±20% jitter)
- Retries on: 429 (rate limit), 529 (overload), network errors
- No retry on: 4xx client errors (except 429), auth failures
- Respects `retry-after` header when provided

---

## Memory Capture

All messages are automatically captured to the `discussions` collection:

- User messages → `user_message` type
- Agent responses → `agent_response` type
- Background storage (non-blocking)
- Session-based grouping with turn numbers

---

## See Also

- `src/memory/async_sdk_wrapper.py` — complete API documentation
- [COMMANDS.md](COMMANDS.md) — slash commands and skills reference
