---
name: 'step-01-resolve-task'
description: 'Classify task type and prepare for model selection'
nextStepFile: './step-02-select-model-and-script.md'
---

# Step 1: Resolve Task and Classify Type

## STEP GOAL
Analyze the user's task to classify it into one of four categories (text-generate, image-analyze, image-generate, audio-process) and identify any input sources.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: User's task description, any input text or file paths
- Limits: Do not make API calls yet. This step is classification only.

## MANDATORY SEQUENCE

### 1. Classify Task Type

Analyze the task description for keywords:

| Task Type | Keywords | Model Category |
|---|---|---|
| **image-analyze** | "analyze", "describe", "read", "explain", "vision", "caption" | Vision (claude-sonnet-4-6, gpt-4o) |
| **image-generate** | "generate", "create", "draw", "design", "dall-e", "flux", "image" | Image Gen (dall-e-3, flux) |
| **audio-process** | "transcribe", "audio", "voice", "whisper", "speech", "sound" | Audio (whisper-1) |

**Note:** Text-only tasks ("write", "code", "summarize", etc.) are NOT handled by api-dispatch.
Route text tasks to tmux-dispatch instead. If only text keywords are present with no multimodal
signals, do not proceed — inform the user to use tmux-dispatch.

**Priority order:** Check in this order — image-generate first (most specific), then audio-process, then image-analyze.

### 2. Identify Input Sources

Determine what input the task needs:

**Text input:**
- Direct prompt in user message
- File path (e.g., `analyze.txt`, `prompt.md`)

**Image input:**
- File path to image (e.g., `screenshot.png`, `diagram.jpg`)
- URL to image (e.g., `https://example.com/image.png`)

**Audio input:**
- File path to audio (e.g., `recording.mp3`, `podcast.wav`)

### 3. Check for Model Specification

User may specify a model:
- "use claude-sonnet-4-6" → anthropic/claude-sonnet-4-6
- "use gpt-4o" → openai/gpt-4o
- "use dall-e-3" → openai/dall-e-3
- "use whisper-1" → openai/whisper-1

If no model specified, leave MODEL empty — interactive selection happens in step-02.

### 4. Record Resolution

Store these values:
- **TASK_TYPE**: text-generate, image-analyze, image-generate, or audio-process
- **INPUT_TYPE**: text, image, or audio
- **INPUT_SOURCE**: The input text or file path
- **MODEL**: Resolved model ID (or empty, will be determined in step-02)

## CRITICAL STEP COMPLETION NOTE
ONLY when task type and input are classified, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Task type correctly classified
- Input type and source identified
- Model resolved (explicit or will be determined)
- All resolution values recorded

### FAILURE:
- Ambiguous task type (multiple conflicting keywords)
- No input provided for the task
- Proceeding without complete classification
