# OpenRouter Models

Top 30 models available via OpenRouter API, organized by category.

---

## Coding Models

Best for code generation, review, and programming tasks.

| Model ID | Provider | Notes |
|----------|----------|-------|
| `anthropic/claude-sonnet-4` | Anthropic | Best coding model, 200K context |
| `openai/gpt-4o` | OpenAI | Strong multi-language support |
| `google/gemini-2.0-flash-8b` | Google | Fast, efficient coding |
| `deepseek/deepseek-coder-v3` | DeepSeek | Dedicated coding model |
| `x-ai/grok-beta` | xAI | Strong reasoning and coding |

---

## Reasoning Models

Best for complex analysis, math, and multi-step problems.

| Model ID | Provider | Notes |
|----------|----------|-------|
| `openai/o1` | OpenAI | Advanced reasoning chain |
| `openai/o1-preview` | OpenAI | Preview version of o1 |
| `anthropic/claude-opus-4` | Anthropic | Most capable reasoning |
| `google/gemini-2.0-flash-exp` | Google | Experimental reasoning |
| `mistralai/mistral-large-2411` | Mistral | Large reasoning model |

---

## Multimodal / Vision Models

Best for image analysis and visual understanding.

| Model ID | Provider | Notes |
|----------|----------|-------|
| `openai/gpt-4o` | OpenAI | Excellent multimodal |
| `anthropic/claude-sonnet-4` | Anthropic | Strong vision capabilities |
| `google/gemini-2.0-flash-exp` | Google | Fast multimodal |
| `meta-llama/llama-3.2-90b-vision-instruct` | Meta | Llama vision model |

---

## Fast / Cheap Models

Best for quick tasks and high-volume operations.

| Model ID | Provider | Notes |
|----------|----------|-------|
| `openai/gpt-4o-mini` | OpenAI | Fast and cost-effective |
| `google/gemini-2.0-flash-8b` | Google | Lightweight and fast |
| `anthropic/claude-haiku-3-5` | Anthropic | Fastest Claude |
| `mistralai/mistral-7b-instruct` | Mistral | Small, fast model |

---

## Image Generation Models

Best for creating images from text prompts. These use the chat completions API (not the legacy images API).

| Model ID | Provider | Notes |
|----------|----------|-------|
| `openai/gpt-5-image` | OpenAI | GPT-5 with native image generation |
| `openai/gpt-5-image-mini` | OpenAI | Smaller, faster GPT-5 image model |
| `google/gemini-3-pro-image-preview` | Google | Gemini Pro image generation |
| `google/gemini-3.1-flash-image-preview` | Google | Fast Gemini image generation |

---

## Audio / Speech Models

Best for transcription and speech processing.

| Model ID | Provider | Notes |
|----------|----------|-------|
| `openai/whisper-1` | OpenAI | Industry-standard transcription |
| `openai/tts-1` | OpenAI | Text-to-speech |
| `microsoft/speech-t5` | Microsoft | Speech synthesis |

---

## General Purpose Models

Best for general tasks where specialized models aren't needed.

| Model ID | Provider | Notes |
|----------|----------|-------|
| `openai/gpt-4o` | OpenAI | Most capable general model |
| `anthropic/claude-sonnet-4` | Anthropic | Balanced capabilities |
| `google/gemini-2.0-flash` | Google | General purpose from Google |
| `mistralai/mistral-large-2411` | Mistral | Large general model |

---

## Model Selection Guide

| Task Type | Recommended Category | Top Picks |
|-----------|---------------------|-----------|
| Code generation | Coding | `anthropic/claude-sonnet-4`, `openai/gpt-4o` |
| Code review | Coding | `anthropic/claude-sonnet-4`, `deepseek/deepseek-coder-v3` |
| Complex analysis | Reasoning | `openai/o1`, `anthropic/claude-opus-4` |
| Math problems | Reasoning | `openai/o1`, `google/gemini-2.0-flash-exp` |
| Image analysis | Multimodal | `openai/gpt-4o`, `anthropic/claude-sonnet-4` |
| Image creation | Image Gen | `openai/gpt-5-image`, `google/gemini-3-pro-image-preview` |
| Transcription | Audio | `openai/whisper-1` |
| Quick tasks | Fast/Cheap | `openai/gpt-4o-mini`, `google/gemini-2.0-flash-8b` |
| General work | General | `openai/gpt-4o`, `anthropic/claude-sonnet-4` |

---

## Default Model

When using OpenRouter API scripts without specifying `--model`:
- **Default:** `openai/gpt-4o-mini` (fast and cost-effective)

---

## API Usage

All OpenRouter models are accessible via the OpenAI-compatible API:
- Base URL: `https://openrouter.ai/api/v1`
- Authentication: API key from `~/.openrouter-token` or `OPENROUTER_API_KEY` env
