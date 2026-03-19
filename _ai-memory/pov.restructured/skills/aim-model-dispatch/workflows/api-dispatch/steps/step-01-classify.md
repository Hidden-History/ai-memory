---
name: 'step-01-classify'
description: 'Classify task type (image-analyze, image-generate, audio-process, audio-generate, video-generate) and route to type-specific step chain'
nextStepFile: null
---

# Step 1: Classify Task and Route to Chain

## STEP GOAL
Analyze the user's task to classify it into one of five categories (image-analyze, image-generate, audio-process, audio-generate, video-generate) and identify any input sources. Text-only tasks are not handled here.

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
| **image-generate** | "generate", "create", "draw", "design", "dall-e", "flux", "generate image", "create image" | Image Gen (gpt-5-image, flux) |
| **audio-process** | "transcribe", "audio", "voice", "whisper", "speech to text", "sound" | Audio (whisper-1) |
| **audio-generate** | "tts", "text to speech", "narration", "create audio", "generate audio", "elevenlabs", "suno", "music" | Audio Gen (tts-1-hd, elevenlabs) |
| **video-generate** | "generate video", "create video", "runway", "kling", "pika", "luma", "dream machine", "video" | Video Gen (runway, kling) |

**Note:** Text-only tasks ("write", "code", "summarize", etc.) are NOT handled by api-dispatch.
Route text tasks to tmux-dispatch instead. If only text keywords are present with no multimodal
signals, do not proceed — inform the user to use tmux-dispatch.

**Priority order:** Check in this order — video-generate first (most specific), then audio-generate, then image-generate, then audio-process, then image-analyze.

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
- "use tts-1-hd" → openai/tts-1-hd
- "use runway" → runway/gen-4-turbo
- "use kling" → kling-ai/kling-v2-master

If no model specified, leave MODEL empty — interactive selection happens in the chain's step-02.

### 4. Record Resolution

Store these values:
- **TASK_TYPE**: image-analyze, image-generate, audio-process, audio-generate, or video-generate
- **INPUT_TYPE**: text, image, or audio
- **INPUT_SOURCE**: The input text or file path
- **MODEL**: Resolved model ID (or empty, will be determined in step-02)

### 5. Route to Type-Specific Step Chain

Based on TASK_TYPE, load the first step of the corresponding chain:

| TASK_TYPE | Load This File |
|---|---|
| image-analyze | `./image-analyze/step-02-select-model.md` |
| image-generate | `./image-generate/step-02-select-model.md` |
| audio-process | `./audio-process/step-02-select-model.md` |
| audio-generate | `./audio-generate/step-02-select-model.md` |
| video-generate | `./video-generate/step-02-select-model.md` |

Do not proceed in this step file — load and follow the chain file completely.

## CRITICAL STEP COMPLETION NOTE
ONLY when task type and input are classified, route to the type-specific chain per Section 5.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Task type correctly classified
- Input type and source identified
- Model resolved (explicit or will be determined)
- All resolution values recorded
- Correct chain file loaded per routing table

### FAILURE:
- Ambiguous task type (multiple conflicting keywords)
- No input provided for the task
- Proceeding without complete classification
- Loading wrong chain for the task type
