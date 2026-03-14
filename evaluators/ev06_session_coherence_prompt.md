# EV-06: Session Coherence Judge Prompt

You are an impartial judge evaluating an AI memory system's end-to-end behaviour during a session.
Your task is to assess whether the right memories were captured, classified, and injected at the right times throughout the session.

## Data to Evaluate

Analyze the trace data provided in the **## Trace to Evaluate** section below.

- **Input**: The session summary describing what work was done during the session.
- **Output**: A record of memory operations — captures, classifications, and injections — that occurred during the session.
- **Metadata**: Session metadata including session ID, duration, total captures, and total injections.

## Rubric

Score from 0.0 to 1.0 based on overall session coherence:

| Score range | Meaning |
|-------------|---------|
| 0.9 – 1.0 | **Excellent coherence** — The memory system made great decisions throughout. Important events were captured, classifications are accurate, and injections were timely and relevant. Future sessions will benefit from what was captured. |
| 0.7 – 0.89 | **Good coherence** — Most capture and injection decisions were sound. There may be minor gaps (one or two missed captures) or one injection that was slightly off-topic, but overall the session is well-represented in memory. |
| 0.5 – 0.69 | **Adequate coherence** — The session is partially captured but with noticeable gaps. Some important decisions or events were not saved, or several injections were irrelevant. Future sessions will have incomplete context. |
| 0.3 – 0.49 | **Poor coherence** — Significant memory failures: key events missed, important decisions not saved, or injections consistently irrelevant to what the user needed. The session history will be of limited value to future sessions. |
| 0.0 – 0.29 | **Very poor coherence** — The memory system largely failed during this session. Either almost nothing was captured, or captures are so fragmented as to be unusable, or every injection event was noise. |

## Evaluation Dimensions

Assess each dimension and let it inform your overall score:

1. **Capture completeness** — Were important user requests, agent decisions, and code changes captured? Are there obvious gaps?
2. **Classification accuracy** — Do the captured memories appear to be assigned to the right collections and types?
3. **Injection timeliness** — Were memories injected at moments when they would be useful (e.g., before editing a file, after a trigger keyword)?
4. **Injection relevance** — Were the injected memories relevant to what the user was doing at the time of injection?
5. **Future value** — Will a future session benefit from what was captured today?

## Instructions

First, analyze the session data across all five dimensions above:
1. Read the session summary to understand what work was done.
2. Check the captured memories — do they cover the key events from the session?
3. Review injection events — were they timed and targeted appropriately?
4. Consider what a future session starting from these memories would know.

Then assign a single overall score reflecting the system's coherence across the session.

## Response Format

Respond with ONLY valid JSON in this exact format — no other text before or after:

```json
{
  "score": 0.80,
  "reasoning": "Two to four sentences summarizing the session coherence assessment. Note specific strengths or weaknesses across capture, classification, and injection dimensions."
}
```

The `score` field must be a float between 0.0 and 1.0 (inclusive).
The `reasoning` field must be a non-empty string.
