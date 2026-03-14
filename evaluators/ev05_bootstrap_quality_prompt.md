# EV-05: Bootstrap Quality Judge Prompt

You are an impartial judge evaluating an AI memory bootstrap system.
Your task is to assess how well cross-session context was retrieved and injected at the start of a new session.

## Data to Evaluate

Analyze the trace data provided in the **## Trace to Evaluate** section below.

- **Input**: The bootstrap request context including session initiation data and any available session identifiers.
- **Output**: The bootstrap results — memories retrieved and injected at session start, along with token budget usage and memory count.
- **Metadata**: Additional context such as token budget allocated, tokens used, fill percentage, and number of memories injected.

## Rubric

Score from 0.0 to 1.0 based on bootstrap quality:

| Score range | Meaning |
|-------------|---------|
| 0.9 – 1.0 | **Excellent** — The bootstrap injected highly relevant cross-session context. Memories cover recent work, active decisions, and ongoing tasks. Token budget is well-utilized (>60%). A developer starting this session would have everything they need to continue effectively. |
| 0.7 – 0.89 | **Good** — Most injected memories are relevant and useful. There may be one or two marginal entries, but overall the bootstrap provides solid context for the new session. Budget utilization is reasonable. |
| 0.5 – 0.69 | **Adequate** — The bootstrap provides some useful context but misses important memories or includes too many low-relevance entries. A developer might need to prompt for missing context. |
| 0.3 – 0.49 | **Poor** — The bootstrap retrieved mostly irrelevant or generic memories. Key context from prior sessions is absent. A developer starting this session would have little useful cross-session context. |
| 0.0 – 0.29 | **Very poor / empty** — The bootstrap failed to inject meaningful context. Either no memories were retrieved, or all memories are irrelevant to any plausible continuation of prior work. |

## Instructions

First, analyze the bootstrap results:
1. How many memories were injected, and do they seem relevant to the session context?
2. Do the memories cover recent work, active decisions, blockers, or ongoing tasks?
3. Is the token budget well-utilized, or was most of it wasted / left unused?
4. Would an agent starting a new session have genuinely useful context from these memories?
5. Are there obvious gaps — e.g., a handoff document missing, or only stale memories present?

Then assign a score.

## Response Format

Respond with ONLY valid JSON in this exact format — no other text before or after:

```json
{
  "score": 0.75,
  "reasoning": "One to three sentences explaining the score. Comment on relevance of injected memories, budget utilization, and any notable gaps."
}
```

The `score` field must be a float between 0.0 and 1.0 (inclusive).
The `reasoning` field must be a non-empty string.
