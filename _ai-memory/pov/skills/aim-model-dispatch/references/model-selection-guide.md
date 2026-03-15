# Model Selection Guide

Shared reference used by tmux-dispatch and bmad-dispatch step-01 files.
Update this file when models change — do NOT duplicate this content in step files.

---

## Task Category Detection

Determine task category from the user's request signals:

| User request signals | Category |
|---------------------|----------|
| "review code", "implement", "write function", programming terms | `coding` |
| "analyze", "reason", "explain why", "compare" | `reasoning` |
| "analyze image", "describe photo", "what's in this image" | `vision` |
| "generate image", "create picture", "draw" | `image-gen` |
| "transcribe", "audio", "speech" | `audio` |
| "text to speech", "tts", "narration", "generate audio", "suno", "music" | `audio-gen` |
| "generate video", "create video", "runway", "kling", "pika", "luma" | `video-gen` |
| "quick", "fast", "summarize briefly" | `fast` |
| No clear signal | `general` |

---

## Model Options by Backend

### Claude (native)

Present these 3 options to the user. Suggest based on task complexity.

- **Opus 4.6** (`claude-opus-4-6`) — Complex analysis, architecture, high-stakes tasks
- **Sonnet 4.6** (`claude-sonnet-4-6`) — General coding, dev work, balanced performance
- **Haiku 4.5** (`claude-haiku-4-5-20251001`) — Quick/simple tasks, fastest and cheapest

### Provider (non-native)

Applies when BACKEND is: openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, or siliconflow.

**Step 1:** Read the install-time default for the selected provider from providers.json:
```bash
PROVIDER="<selected-provider>"
DEFAULT_MODEL=$(jq -r ".providers[\"${PROVIDER}\"].defaultModel // empty" \
  "${HOME}/.config/claude-code-router/providers.json" 2>/dev/null)
```

**Step 2:** If a default model is found, present it as the recommendation:
> "Default for **[provider]**: `[defaultModel]`. Accept this model, or specify a different one?"

**Step 3:** For OpenRouter only — also offer a live model query:
```bash
SKILL_DIR="$(pwd)/.claude/skills/model-dispatch" && \
python3 "${SKILL_DIR}/scripts/openrouter-api/list-models.py" \
  --category [detected-category] --query "[user's task]" --limit 10
```

**Step 4:** Wait for user confirmation. Record confirmed choice as MODEL.

**Provider default model reference** (fallback if providers.json missing):

| Provider   | Default Model                        | Notes                          |
|---|---|---|
| openrouter | anthropic/claude-sonnet-4-6          | Or run live query              |
| ollama     | glm-5:cloud                          | :cloud = hosted Ollama         |
| gemini     | gemini-2.0-flash                     | Fast, cost-effective           |
| deepseek   | deepseek-chat                        | Strong coding model            |
| groq       | llama-4-scout-17b-16e-instruct       | Fastest inference              |
| cerebras   | llama3.1-70b                         | Ultra-fast inference           |
| mistral    | mistral-large-2411                   | Strong European model          |
| openai     | gpt-4o                               | General purpose                |
| vertex-ai  | claude-sonnet-4-5@anthropic           | Google Cloud Vertex            |
| siliconflow| Qwen/Qwen2.5-72B-Instruct            | SiliconFlow hosted             |

For detailed model lists per provider, see `references/providers.md`.

---

## Model Confirmation Gate

After presenting options, ask:
> "Recommended: **[model]**. Accept this model, or pick a different one from the list above?"

**Halt and wait.** Do not proceed without the user's explicit response. Do not interpret silence as approval.
Record the confirmed choice as MODEL.
