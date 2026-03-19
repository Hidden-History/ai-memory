# Model-Dispatch Skill — User Guide

Model-Dispatch lets you offload tasks to remote model-powered Claude Code instances while your main session stays free. Each dispatched agent runs in a visible tmux pane — you see the full Claude TUI in real time.

**How it works:** You say "dispatch to [backend]" with a task description. The skill opens a tmux pane, launches the appropriate wrapper, sends your prompt, and starts a background monitor. When the agent finishes, the result is captured automatically.

**What you need:** Wrapper scripts installed at `~/.local/bin/`, API tokens stored securely, and `tmux`. Run `validate-setup.sh` to verify.

---

## Trigger Phrases

Say any of these to activate the skill from within Claude Code:

- `dispatch to claude` / `use native claude` / `claude-dispatch`
- `dispatch to openrouter` / `use openrouter` / `300 models`
- `dispatch to ollama` / `use ollama` / `remote model`
- `dispatch to api` / `openrouter api` / `multimodal task`
- `dispatch to vertex-ai` / `use vertex-ai` / `vertex ai`
- `dispatch to siliconflow` / `use siliconflow`
- `dispatch to gemini` / `use gemini` / `google model`
- `dispatch to deepseek` / `use deepseek`
- `dispatch to groq` / `use groq` / `llama on groq`
- `dispatch to cerebras` / `use cerebras`
- `dispatch to mistral` / `use mistral` / `codestral`
- `dispatch to openai` / `use openai` / `gpt-4o`

---

## 1. Backend Selection

### Claude Native (Anthropic API)

Use for tasks requiring direct Anthropic API access.

```
dispatch to claude: Analyze the auth module for security issues
```

**Environment:** Uses your `ANTHROPIC_API_KEY` from environment.

**Wrapper:** `claude-dispatch`

---

### OpenRouter

Use for access to 300+ models across providers.

```
dispatch to openrouter with openai/gpt-4o: Implement the user service
dispatch to openrouter with anthropic/claude-opus-4-6: Do deep architecture analysis
```

**Environment:** Reads from `~/.openrouter-token` or `OPENROUTER_API_KEY` env.

**Wrapper:** `provider-dispatch openrouter`

**Model Format:** `provider/model-name` (e.g., `openai/gpt-4o`, `anthropic/claude-sonnet-4-6`)

---

### Ollama

Use for Ollama-compatible endpoints.

```
dispatch to ollama with qwen3-coder-next:cloud: Write test cases
```

**Environment:** Reads from `~/.ollama-token` or `ANTHROPIC_AUTH_TOKEN` env.

**Wrapper:** `provider-dispatch ollama`

**Model Format:** `model-name:tag` (e.g., `glm-5:cloud`, `qwen3-coder-next:cloud`)

---

### Vertex AI

Use for Google Cloud Vertex AI models.

```
dispatch to vertex-ai with claude-sonnet-4-5@anthropic: Analyze the codebase
```

**Environment:** Reads from `~/.vertex-token`.

**Wrapper:** `provider-dispatch vertex-ai`

**Model Format:** `model-name@provider` (e.g., `claude-sonnet-4-5@anthropic`, `gemini-2.0-flash@google`)

---

### SiliconFlow

Use for SiliconFlow-hosted open models.

```
dispatch to siliconflow with Qwen/Qwen2.5-72B-Instruct: Generate documentation
```

**Environment:** Reads from `~/.siliconflow-token`.

**Wrapper:** `provider-dispatch siliconflow`

**Model Format:** `Provider/ModelName` (e.g., `Qwen/Qwen2.5-72B-Instruct`, `deepseek-ai/DeepSeek-V3`)

---

### Gemini

Use for Google Gemini models via OpenAI-compatible API.

```
dispatch to gemini: Analyze the architecture for scalability issues
dispatch to gemini with gemini-2.0-flash-exp: Write the OpenAPI spec
```

**Environment:** Reads from `~/.gemini-token`.

**Wrapper:** `provider-dispatch gemini`

**Model Format:** `gemini-model-name` (e.g., `gemini-2.0-flash`, `gemini-2.5-pro`)

---

### DeepSeek

Use for DeepSeek reasoning and coding models.

```
dispatch to deepseek: Implement the payment processing service
dispatch to deepseek with deepseek-reasoner: Analyze this complex algorithm
```

**Environment:** Reads from `~/.deepseek-token`.

**Wrapper:** `provider-dispatch deepseek`

**Model Format:** `model-name` (e.g., `deepseek-chat`, `deepseek-reasoner`)

---

### Groq

Use for ultra-fast inference via Groq hardware.

```
dispatch to groq: Quick code review of the auth module
dispatch to groq with llama-4-maverick-17b-128e-instruct: Fast prototype review
```

**Environment:** Reads from `~/.groq-token`.

**Wrapper:** `provider-dispatch groq`

**Model Format:** `model-name` (e.g., `llama-4-scout-17b-16e-instruct`, `llama-4-maverick-17b-128e-instruct`)

---

### Cerebras

Use for ultra-fast inference via Cerebras chip architecture.

```
dispatch to cerebras: Generate boilerplate for the user service
dispatch to cerebras with llama3.1-70b: Fast code generation task
```

**Environment:** Reads from `~/.cerebras-token`.

**Wrapper:** `provider-dispatch cerebras`

**Model Format:** `model-name` (e.g., `llama3.1-70b`, `llama3.3-70b`)

---

### Mistral

Use for Mistral and Codestral models, especially for code tasks.

```
dispatch to mistral: Review this Python function for bugs
dispatch to mistral with codestral-latest: Implement the data pipeline
```

**Environment:** Reads from `~/.mistral-token`.

**Wrapper:** `provider-dispatch mistral`

**Model Format:** `model-name` (e.g., `mistral-large-2411`, `codestral-latest`)

---

### OpenAI

Use for GPT-4o, o1, and other OpenAI models.

```
dispatch to openai: Design the system architecture
dispatch to openai with o1: Solve this complex algorithmic problem
```

**Environment:** Reads from `~/.openai-token`.

**Wrapper:** `provider-dispatch openai`

**Model Format:** `model-name` (e.g., `gpt-4o`, `o1`, `gpt-4o-mini`)

---

### OpenRouter Direct API

Use for multimodal tasks (image analysis, image generation, audio) that bypass tmux.

```
dispatch to api: Analyze this image https://example.com/screenshot.png
dispatch to api with dall-e-3: Generate a logo for my startup
dispatch to api: Transcribe this audio file
```

**Backend:** Direct OpenRouter API via Python scripts

**No tmux involved** — scripts run inline

---

## 2. Model Selection

### Specify a Model

```
dispatch to openrouter with openai/gpt-4o: Implement the feature
dispatch to ollama with qwen3-vl:235b-cloud: Analyze the UI screenshot
dispatch to claude with claude-opus-4-6: Write the architecture doc
```

### Request a Model Category

```
dispatch to openrouter using a coding model: Refactor the service
dispatch to ollama with a vision model: Analyze the design
dispatch to openrouter using a fast model: Quick code review
```

### Use Default (No Model Specified)

```
dispatch to openrouter: Write unit tests for the auth module
```

Default models:
- **Claude native:** Your default Claude settings
- **OpenRouter:** `anthropic/claude-sonnet-4-6`
- **Ollama:** `glm-5:cloud`

---

## 3. Generic Task Dispatch

Send any task to a remote instance. The agent works in a visible tmux pane.

```
dispatch to ollama: List all TypeScript files in src/ and summarize each
run this on ollama: Analyze package.json for outdated dependencies
send to openrouter with openai/gpt-4o: Design the database schema
```

**What happens:**
1. A tmux pane opens with Claude TUI visible
2. Agent receives prompt and starts working
3. You can watch in real time in the split pane
4. Result delivered to inbox automatically on completion

---

## 4. BMAD Task Dispatch (Two-Phase)

All BMAD tasks use two-phase activation: first the agent persona loads, then you give directions.

### Code Review

```
dispatch to ollama: Activate /bmad-agent-bmm-dev, then CR to review auth module
send to openrouter with claude-sonnet-4-6: Activate dev agent, run CR on api/
```

### Implement a Story

```
dispatch to ollama: Activate /bmad-agent-bmm-dev, then DS for story 1.5
use openrouter with openai/gpt-4o: Activate dev agent, DS story-1-6.md
```

### Create PRD

```
dispatch to claude: Activate /bmad-agent-bmm-pm, then CP for notification system
send to ollama: Activate PM agent, CP to create PRD for billing
```

### Validate Documentation

```
dispatch to openrouter: Activate tech-writer, VD to validate docs/
use ollama: Activate tech-writer agent, validate the SKILL.md
```

### Sprint Planning

```
dispatch to claude: Activate /bmad-agent-bmm-sm for sprint planning on epic 2
send to ollama: Activate SM agent, run sprint status check
```

### All Available BMAD Agents

| Agent | Command | Use |
|-------|---------|-----|
| Dev | `/bmad-agent-bmm-dev` | Code, review, implementation |
| PM | `/bmad-agent-bmm-pm` | PRD, epics, planning |
| Tech Writer | `/bmad-agent-bmm-tech-writer` | Docs, explanation |
| Analyst | `/bmad-agent-bmm-analyst` | Research, analysis |
| Architect | `/bmad-agent-bmm-architect` | Design, architecture |
| Scrum Master | `/bmad-agent-bmm-sm` | Sprint, retrospectives |
| QA | `/bmad-agent-bmm-qa` | Tests, automation |
| UX Designer | `/bmad-agent-bmm-ux-designer` | User flow, design |
| Quick Flow Solo Dev | `/bmad-agent-bmm-quick-flow-solo-dev` | Fast implementation |
| Agent Builder | `/bmad-agent-bmb-agent-builder` | Create new agents |
| Module Builder | `/bmad-agent-bmb-module-builder` | Build modules |
| Workflow Builder | `/bmad-agent-bmb-workflow-builder` | Build workflows |
| Brainstorming Coach | `/bmad-agent-cis-brainstorming-coach` | Ideation |
| Creative Problem Solver | `/bmad-agent-cis-creative-problem-solver` | Problem solving |
| Design Thinking Coach | `/bmad-agent-cis-design-thinking-coach` | Design thinking |
| Innovation Strategist | `/bmad-agent-cis-innovation-strategist` | Innovation |
| Presentation Master | `/bmad-agent-cis-presentation-master` | Presentations |
| Storyteller | `/bmad-agent-cis-storyteller` | Narrative |
| Tea | `/bmad-agent-tea-tea` | Test Architect (TEA) |

---

## 5. Multi-Agent Parallel Dispatch

Launch multiple agents at once for parallel work.

```
dispatch to ollama: Launch 3 agents in parallel —
  Agent 1 (dev): Analyze auth module security
  Agent 2 (dev): Write unit tests for user service
  Agent 3 (tech-writer): Review API docs for gaps
```

Each agent runs in its own visible tmux pane. Results delivered to inbox as they complete.

**Backend mixing:** You can use different backends for different agents:

```
dispatch: Launch 2 agents —
  Agent 1 (openrouter with claude-sonnet-4-6): Code review frontend
  Agent 2 (ollama with qwen3-coder): Code review backend
```

---

## 6. Follow-Up Prompts

After completion, send follow-up prompts to the same session.

```
send follow-up to the agent: Now fix the issues found in code review
dispatch to same agent: What tests would you add next?
```

Conversation context is preserved within the tmux pane.

---

## 7. Monitoring

Check agent progress:

```
check on the ollama agent
what is the openrouter agent doing?
status of all dispatched agents
```

The tmux pane is always visible — switch to it directly to watch in real time.

---

## 8. Results

Results delivered two ways:

1. **Team inbox** — Appears as teammate messages (~1 second delivery)
2. **File** — Saved to `/tmp/model-dispatch-result-{agent-name}.txt`

---

## 9. OpenRouter API Scripts

Direct model access without tmux for multimodal tasks.

### Image Analysis

```
dispatch to api: Analyze https://example.com/image.png with vision model
image-analyze.py --model openai/gpt-4o --input "path/to/image.png" --output -
```

### Image Generation

```
dispatch to api: Generate a logo with dall-e-3 for "TechStartup Inc"
image-generate.py --model openai/dall-e-3 --input "logo for TechStartup Inc" --output logo.png
```

### Audio Transcription

```
dispatch to api: Transcribe this audio file
audio-process.py --model openai/whisper-1 --input audio.mp3 --output transcript.txt
```

### Audio Generation (TTS / Music)

```
dispatch to api: Generate a narration for my presentation using ElevenLabs
dispatch to api with suno/chirp-v3-5: Create background music for the intro scene
```

### Video Generation

```
dispatch to api: Generate a 5-second product demo video
dispatch to api with runway/gen-4-turbo: Create a cinematic intro clip from this prompt
```

### Text Generation

> **Note:** For text-only tasks requiring a full Claude Code session, use tmux-dispatch instead (e.g., `dispatch to openrouter: Write unit tests`). This script is for direct API text generation without a Claude Code session.

```
text-generate.py --model openai/gpt-4o-mini --input "Explain量子 computing" --output -
```

---

## 10. Tips

- **Be specific** — The more detail you give, the better the agent performs
- **BMAD agents always need two-phase** — Activate persona first, then give directions
- **Watch the pane** — You can see everything in real time
- **One Enter only** — Never hit Enter twice when submitting prompts
- **Wait for init** — Claude Code loads project context and MCP servers before accepting prompts
- **Use API mode for multimodal** — Image/audio tasks bypass tmux with direct API calls
- **Track costs** — OpenRouter provides usage analytics at [openrouter.ai/activity](https://openrouter.ai/activity)

---

## Troubleshooting

| Issue | Quick Fix |
|-------|-----------|
| Agent not responding | Wait longer init (8-10 seconds) |
| Permission dialog blocking | Use `--allowedTools` flags |
| Prompt not submitted | Wait 2s after text, then Enter once |
| Result not delivered | Check `/tmp/model-dispatch-result-*.txt` |
