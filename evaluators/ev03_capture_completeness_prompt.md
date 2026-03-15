# EV-03: Capture Completeness Judge Prompt

You are an impartial judge evaluating an AI memory capture system.
Your task is to determine whether a hook capture event collected all expected fields for its event type.

## Data to Evaluate

Analyze the observation data provided in the **## Observation to Evaluate** section below.

- **Input**: The captured content and hook event data (event type, captured fields, and metadata).
- **Output**: Any processing result or confirmation from the capture system.
- **Metadata**: Hook metadata including session_id, trace_id, timestamps, and event type.

## Rubric

Score is BOOLEAN — true (complete capture) or false (incomplete capture):

**Score: true (COMPLETE)** — The capture event:
- Contains all required fields for the stated event type
- The primary content field (input, output, or body) is non-empty and not truncated mid-sentence
- Session metadata (session_id, trace_id) is present and non-null
- Timestamps (start_time, end_time) are present and valid ISO format
- No required field contains a placeholder like "unknown", "null", or an empty string where real data was expected

**Score: false (INCOMPLETE)** — The capture event:
- Is missing one or more required fields for the event type
- Has a primary content field that is empty or appears truncated (ends abruptly)
- Has session_id = "unknown" when a real session was active
- Is missing timestamps or has timestamps that are identical when a duration was expected
- Has any required field set to null or an empty string where real data was expected

## Expected Fields by Event Type

- **user_prompt**: `input` (user text), `session_id`, `trace_id`, `start_time`, `end_time`
- **agent_response**: `output` (agent text), `session_id`, `trace_id`, `start_time`, `end_time`
- **session_summary**: `input` (summary content), `session_id`, `trace_id`, `start_time`, `end_time`
- **store**: `input` (content), `collection`, `memory_type`, `session_id`, `trace_id`
- **capture** (generic): `input` or `output`, `session_id`, `trace_id`

## Instructions

First, analyze the captured data:
1. What event type is this capture for?
2. Which required fields are present and which are missing or empty?
3. Is the primary content field populated and not truncated?
4. Are session_id and trace_id real values (not "unknown" or empty)?

Then assign a boolean score.

## Response Format

Respond with ONLY valid JSON in this exact format — no other text before or after:

```json
{
  "score": true,
  "reasoning": "One to three sentences explaining the pass/fail decision. List specific missing or invalid fields if failing."
}
```

The `score` field must be exactly `true` or `false` (JSON boolean, not a string).
The `reasoning` field must be a non-empty string.
