---
name: 'step-01-resolve-backend'
description: 'Route user intent to correct backend: claude/openrouter/ollama/gemini/deepseek/groq/cerebras/mistral/openai/vertex-ai/siliconflow/api'
nextStepFile: null
---

# Step 1: Resolve Backend and Select Workflow

## STEP GOAL
Route user intent to correct backend: claude/openrouter/ollama/gemini/deepseek/groq/cerebras/mistral/openai/vertex-ai/siliconflow/api

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps
- Use holistic judgment on user intent, not just keyword matching

## CONTEXT BOUNDARIES
- Available context: User's dispatch request text, any explicitly mentioned backend or model
- Limits: Do not execute workflows — only determine routing. Do not make panes or API calls.

## MANDATORY SEQUENCE

### 1. Parse User Intent

Analyze the user's request for backend indicators. Look for these signals in order:

**Backend-specific keywords (highest priority):**
- "claude-dispatch" or "use claude" or "native claude" → `claude`
- "openrouter" or "300 models" → `openrouter`
- "ollama" or "remote model" or "glm-5" or "qwen" → `ollama`
- "gemini" or "google model" or "gemini flash" → `gemini`
- "deepseek" or "deepseek-chat" or "deepseek-r1" → `deepseek`
- "groq" or "llama on groq" → `groq`
- "cerebras" or "fast inference" → `cerebras`
- "mistral" or "codestral" → `mistral`
- "openai" or "gpt-4o" or "o1" → `openai`
- "vertex-ai" or "vertex" or "google cloud model" → `vertex-ai`
- "siliconflow" or "silicon flow" → `siliconflow`
- "analyze image" or "describe image" or "vision" → `api`
- "generate image" or "create image" or "dall-e" or "flux" → `api`
- "process audio" or "transcribe" or "whisper" or "speech to text" → `api`
- "generate audio" or "text to speech" or "tts" or "narration" or "elevenlabs" or "suno" or "create music" → `api`
- "generate video" or "create video" or "runway" or "kling" or "pika" or "luma" → `api`

**Model-specific indicators:**
- "claude-opus" or "claude-sonnet" without backend → `claude`
- "glm-5" or "qwen" without backend → `ollama`

**Default behavior:**
- No backend specified, no multimodal task → `claude` (native)

### 2. Select Workflow

| Backend | Workflow | Reason |
|---|---|---|
| claude | tmux-dispatch | Native Claude Code session |
| openrouter | tmux-dispatch | OpenRouter via wrapper |
| ollama | tmux-dispatch | Ollama via wrapper |
| gemini | tmux-dispatch | Native Gemini CLI (Google account auth, not API key) |
| deepseek | tmux-dispatch | DeepSeek via provider-dispatch wrapper |
| groq | tmux-dispatch | Groq via provider-dispatch wrapper |
| cerebras | tmux-dispatch | Cerebras via provider-dispatch wrapper |
| mistral | tmux-dispatch | Mistral via provider-dispatch wrapper |
| openai | tmux-dispatch | OpenAI via provider-dispatch wrapper |
| vertex-ai  | tmux-dispatch | Vertex AI via provider-dispatch wrapper |
| siliconflow | tmux-dispatch | SiliconFlow via provider-dispatch wrapper |
| api | api-dispatch | Direct OpenRouter API (multimodal) |

**BMAD tasks:** All BMAD agent commands route to bmad-dispatch. SKILL.md step 3 enforces this — the route step records bmad-dispatch as WORKFLOW for any BMAD task.

### 3. Determine Backend Details

For tmux-dispatch backends (claude/openrouter/ollama/gemini/deepseek/groq/cerebras/mistral/openai/vertex-ai/siliconflow):
- Extract model if specified (e.g., "ollama with qwen3-coder-next:cloud")
- Default model: each provider has an install-time default stored in providers.json.
  If user says "use gemini" without specifying a model, load defaultModel from providers.json
  and present for confirmation — do NOT silently use it.

For api-dispatch:
- Classify task type: image-analyze, image-generate, audio-process, audio-generate, video-generate
- Do NOT resolve a model here — model selection happens interactively in the api-dispatch workflow

### 4. Record Routing Decision

Store these values:
- **BACKEND**: claude, openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow, or api
- **WORKFLOW**: tmux-dispatch or api-dispatch
- **MODEL**: Resolved model ID (only if user explicitly specified one, otherwise empty)
- **TASK_TYPE**: For api-dispatch, the task category

## CRITICAL STEP COMPLETION NOTE
ONLY when backend and workflow are determined, record all four values (BACKEND, WORKFLOW, MODEL, TASK_TYPE). SKILL.md step 4 automatically loads the correct workflow — do NOT prompt the user to load workflows manually.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Backend correctly identified from user intent
- Workflow correctly selected based on backend
- Model resolved (explicit or default)
- Routing decision clearly communicated to user

### FAILURE:
- Multiple conflicting backends specified (clarify with user)
- Ambiguous intent without fallback
- Incorrect workflow selection
