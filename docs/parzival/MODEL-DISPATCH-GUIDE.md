# Model Dispatch Guide

**Optional multi-provider LLM routing for Parzival and Claude Code agents**

Model Dispatch is a skill that lets Parzival select different LLM backends — Claude (native), Ollama, OpenRouter, and seven additional providers — based on task complexity, agent role, and user preference. Each dispatched agent runs in a visible tmux pane with full Claude Code TUI, and results are delivered automatically to the team inbox.

**This capability is entirely optional.** Claude Code works perfectly without it. Model Dispatch adds value when you want to use non-Claude models, run agents on cheaper backends, access multimodal capabilities (image/audio/video), or leverage ultra-fast inference providers for simple tasks.

---

## Table of Contents

- [Architecture](#architecture)
- [Setup](#setup)
- [Provider Reference](#provider-reference)
- [Model Selection](#model-selection)
- [Dispatch Modes](#dispatch-modes)
- [BMAD Agent Dispatch](#bmad-agent-dispatch)
- [Multimodal API Dispatch](#multimodal-api-dispatch)
- [When to Use Each Provider](#when-to-use-each-provider)
- [Troubleshooting](#troubleshooting)

---

## Architecture

Model Dispatch operates in three layers:

```
User Request
    |
    v
[1. Model Selection]  -- Assess complexity, check role defaults, apply overrides
    |
    v
[2. Provider Routing] -- Route to correct backend (Claude / Ollama / OpenRouter / etc.)
    |
    v
[3. Dispatch]         -- Launch agent via tmux pane or direct API call
    |
    v
[4. Result Capture]   -- Monitor completion, deliver to team inbox + /tmp file
```

### Dispatch Backends

| Backend | Mechanism | Use Case |
|---------|-----------|----------|
| Claude native | `claude-dispatch` wrapper | Direct Anthropic API access |
| Provider (tmux) | `provider-dispatch <name>` wrapper | Any OpenAI-compatible API routed through Claude Code in a tmux pane |
| API direct | Python scripts (no tmux) | Multimodal tasks: image analysis/generation, audio, video |

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `provider-dispatch` | `~/.local/bin/provider-dispatch` | Unified wrapper for all non-native providers |
| `claude-dispatch` | `~/.local/bin/claude-dispatch` | Native Anthropic API wrapper |
| `providers.json` | `~/.config/claude-code-router/providers.json` | Provider configuration (base URLs, token paths, default models) |
| Token files | `~/.<provider>-token` | API keys, chmod 600 |
| API scripts | `scripts/openrouter-api/*.py` | Direct API access for multimodal tasks |

All provider wrappers unset the `CLAUDECODE` environment variable before launching to prevent nesting errors.

---

## Setup

### Prerequisites

| Software | Purpose | Install |
|----------|---------|---------|
| Claude Code | The CLI that agents dispatch to | `npm install -g @anthropic-ai/claude-code` |
| tmux | Pane management for isolated sessions | `sudo apt install tmux` / `brew install tmux` |
| python3 | Inbox injection and API scripts | Usually pre-installed |
| jq | JSON parsing in shell scripts | `sudo apt install jq` / `brew install jq` |

Optional:

| Software | Purpose | Install |
|----------|---------|---------|
| inotify-tools | Faster file change detection | `sudo apt install inotify-tools` |
| Gemini CLI | Native Google Gemini dispatch | `npm install -g @google/gemini-cli` |

### Installation

Run the interactive installer:

```bash
bash /path/to/model-dispatch/scripts/install.sh
```

The installer performs these steps:

1. **Check prerequisites** -- Verifies tmux, python3, jq are available.
2. **Detect existing config** -- Imports providers from any existing Claude Code Router configuration.
3. **Select providers** -- Interactive menu to choose which backends to configure.
4. **Collect API tokens** -- Prompts for each provider's API key and stores it securely (chmod 600).
5. **Set default models** -- Confirms or overrides the default model for each provider.
6. **Write providers.json** -- Saves configuration to `~/.config/claude-code-router/providers.json`.
7. **Install wrappers** -- Copies `provider-dispatch` and `claude-dispatch` to `~/.local/bin/`.
8. **Install Python dependencies** -- Ensures `openai` and `requests` libraries are available.
9. **Copy skill to project** -- Optionally installs the skill into a project's `.claude/skills/` directory.
10. **Run validation** -- Executes `validate-setup.sh` to confirm everything works.

To add the skill to an additional project after initial setup:

```bash
bash /path/to/model-dispatch/scripts/install.sh /path/to/project
```

This skips system-level setup (providers, wrappers) and only copies the skill directory.

### Manual Token Setup

If you prefer to configure tokens manually rather than through the installer:

```bash
# Example: OpenRouter
echo "YOUR_API_KEY" > ~/.openrouter-token
chmod 600 ~/.openrouter-token
```

Each provider stores its token in `~/.<provider>-token`. All token files must have permissions set to `600`.

### PATH Configuration

Ensure `~/.local/bin` is in your PATH:

```bash
echo $PATH | tr ':' '\n' | grep local/bin
```

If missing:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Validation

Run the validation suite at any time to confirm setup:

```bash
bash /path/to/model-dispatch/scripts/validate-setup.sh
```

The validator checks: wrappers in PATH, providers.json validity, token file existence and permissions, CLAUDECODE unset protection, tmux/python3/jq availability, and optional inotify-tools.

---

## Provider Reference

### Supported Providers

| Provider | Base URL | Default Model | Token File | Notes |
|----------|----------|---------------|------------|-------|
| Claude (native) | Anthropic API | Your default settings | `~/.anthropic-token` | Always available |
| OpenRouter | `https://openrouter.ai/api` | `anthropic/claude-sonnet-4-6` | `~/.openrouter-token` | 300+ models across providers |
| Ollama | `https://ollama.com` (cloud) or `http://localhost:11434` (local) | `glm-5:cloud` | `~/.ollama-token` | Cloud-hosted or self-hosted models |
| Gemini | Google Gemini API | `gemini-2.0-flash` | `~/.gemini-token` | Also supports native Gemini CLI |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` | `~/.deepseek-token` | Strong coding and reasoning |
| Groq | `https://api.groq.com/openai` | `llama-4-scout-17b-16e-instruct` | `~/.groq-token` | Ultra-fast inference |
| Cerebras | `https://api.cerebras.ai/v1` | `llama3.1-70b` | `~/.cerebras-token` | Ultra-fast inference |
| Mistral | `https://api.mistral.ai/v1` | `mistral-large-2411` | `~/.mistral-token` | Codestral for code tasks |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` | `~/.openai-token` | GPT-4o, o1, o3-mini |
| Vertex AI | `https://aiplatform.googleapis.com/v1/publishers/google/models` | `claude-sonnet-4-5@anthropic` | `~/.vertex-token` | Requires gcloud auth |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-72B-Instruct` | `~/.siliconflow-token` | Chinese and open models |

### Model ID Formats

Each provider uses a specific model ID format:

| Provider | Format | Example |
|----------|--------|---------|
| OpenRouter | `provider/model-name` | `openai/gpt-4o` |
| Ollama | `model-name:tag` | `qwen3-coder-next:cloud` |
| Vertex AI | `model-name@provider` | `claude-sonnet-4-5@anthropic` |
| SiliconFlow | `Provider/ModelName` | `Qwen/Qwen2.5-72B-Instruct` |
| All others | `model-name` | `deepseek-chat`, `gpt-4o`, `llama3.1-70b` |

### Adding a Custom Provider

1. Add an entry to `~/.config/claude-code-router/providers.json` with `baseUrl`, `keyFile`, `defaultModel`, and `emptyApiKey` fields.
2. Create the token file at the specified path.
3. Run `validate-setup.sh` to confirm detection.

---

## Model Selection

### Complexity-Based Selection

Parzival assesses task complexity and maps it to a model tier:

| Complexity | Default Tier | Reasoning |
|------------|-------------|-----------|
| Straightforward | Sonnet | Fast, cost-effective for clear tasks |
| Moderate | Sonnet | Good balance for most work |
| Significant | Opus | Deeper reasoning for complex coordination |
| Complex / architectural | Opus | Full reasoning depth required |

When dispatching to a non-Claude provider, the complexity tier maps to an equivalent model on that provider. A "Sonnet-tier" task on OpenRouter might use `openai/gpt-4o`; an "Opus-tier" task might use `openai/o1`.

### Role-Based Defaults

| Agent Role | Default Tier | Upgrade to Opus When |
|------------|-------------|----------------------|
| DEV (implementation) | Sonnet | Architectural changes or complex refactoring |
| DEV (code review) | Sonnet | Reviewing architectural decisions |
| Analyst (research) | Sonnet | Deep architectural analysis |
| PM (PRD creation) | Sonnet | Complex domain modeling |
| Architect (design) | Opus | Already at highest tier |
| SM (sprint planning) | Sonnet | Complex dependency resolution |
| UX Designer | Sonnet | Standard for all UX work |

### Override Rules

1. **User override** -- User preference always wins. If the user specifies a model, use it.
2. **Failed fix escalation** -- After a failed correction loop (loop count > 1), consider upgrading to Opus for deeper reasoning.
3. **Haiku** -- Reserved for simple, high-volume parallel tasks (file scanning, simple grep-and-report). Never for implementation, review, or planning.
4. **Cost awareness** -- Opus costs significantly more than Sonnet. Use it when reasoning depth justifies the cost.

### Task Category Detection

The system detects task categories from request signals:

| Signal | Category |
|--------|----------|
| "review code", "implement", "write function" | `coding` |
| "analyze", "reason", "explain why", "compare" | `reasoning` |
| "analyze image", "describe photo" | `vision` |
| "generate image", "create picture", "draw" | `image-gen` |
| "transcribe", "audio", "speech" | `audio` |
| "text to speech", "tts", "narration", "generate audio", "suno", "music" | `audio-gen` |
| "generate video", "create video", "runway", "kling", "pika", "luma" | `video-gen` |
| "quick", "fast", "summarize briefly" | `fast` |
| No clear signal | `general` |

### Model Confirmation Gate

After selecting a model, the system presents its recommendation and waits for explicit user confirmation before proceeding. Silence is not treated as approval.

---

## Dispatch Modes

### Tmux Dispatch (All Providers)

The primary dispatch mode. Launches a Claude Code instance in a tmux pane with the selected provider's API configuration.

**Trigger phrases:**

```
dispatch to <provider>: <task description>
dispatch to <provider> with <model>: <task description>
use <provider>: <task description>
```

**Examples:**

```
dispatch to openrouter: Write unit tests for the auth module
dispatch to ollama with qwen3-coder-next:cloud: Refactor the user service
dispatch to claude: Analyze the auth module for security issues
```

**What happens:**

1. A tmux pane opens with the Claude Code TUI visible.
2. The agent receives the prompt and begins working.
3. You can watch progress in real time in the split pane.
4. On completion, the result is delivered to the team inbox and saved to `/tmp/model-dispatch-result-{agent-name}.txt`.

### Specifying Models

Three ways to specify which model to use:

```
# Explicit model
dispatch to openrouter with openai/gpt-4o: Implement the feature

# Category request
dispatch to openrouter using a coding model: Refactor the service

# Default (no model specified -- uses provider's default)
dispatch to openrouter: Write unit tests
```

### Multi-Agent Parallel Dispatch

Launch multiple agents simultaneously, each in its own tmux pane:

```
dispatch to ollama: Launch 3 agents in parallel --
  Agent 1 (dev): Analyze auth module security
  Agent 2 (dev): Write unit tests for user service
  Agent 3 (tech-writer): Review API docs for gaps
```

Backends can be mixed across agents:

```
dispatch: Launch 2 agents --
  Agent 1 (openrouter with claude-sonnet-4-6): Code review frontend
  Agent 2 (ollama with qwen3-coder): Code review backend
```

### Follow-Up Prompts

Send additional prompts to a running agent session:

```
send follow-up to the agent: Now fix the issues found in code review
dispatch to same agent: What tests would you add next?
```

Conversation context is preserved within the tmux pane.

### Monitoring

Check on dispatched agents:

```
check on the ollama agent
what is the openrouter agent doing?
status of all dispatched agents
```

You can also switch to any agent's tmux pane to watch output in real time.

---

## BMAD Agent Dispatch

BMAD tasks use two-phase activation: first the agent persona loads, then you give directions. This applies to all providers.

### Pattern

```
dispatch to <provider>: Activate <persona>, then <command>
```

### Examples by Role

**Code Review (Dev agent):**

```
dispatch to ollama: Activate /bmad-agent-bmm-dev, then CR to review auth module
send to openrouter with claude-sonnet-4-6: Activate dev agent, run CR on api/
```

**Implement Story (Dev agent):**

```
dispatch to ollama: Activate /bmad-agent-bmm-dev, then DS for story 1.5
use openrouter with openai/gpt-4o: Activate dev agent, DS story-1-6.md
```

**Create PRD (PM agent):**

```
dispatch to claude: Activate /bmad-agent-bmm-pm, then CP for notification system
```

**Architecture Design (Architect agent):**

```
dispatch to claude: Activate /bmad-agent-bmm-architect, design the payment service
```

**Sprint Planning (Scrum Master agent):**

```
dispatch to claude: Activate /bmad-agent-bmm-sm for sprint planning on epic 2
```

**Documentation (Tech Writer agent):**

```
dispatch to openrouter: Activate tech-writer, VD to validate docs/
```

### Available BMAD Agents

| Agent | Activation Command | Primary Use |
|-------|-------------------|-------------|
| Dev | `/bmad-agent-bmm-dev` | Code, review, implementation |
| PM | `/bmad-agent-bmm-pm` | PRD, epics, planning |
| Architect | `/bmad-agent-bmm-architect` | System design, architecture |
| Analyst | `/bmad-agent-bmm-analyst` | Research, analysis |
| Tech Writer | `/bmad-agent-bmm-tech-writer` | Documentation |
| Scrum Master | `/bmad-agent-bmm-sm` | Sprint planning, retrospectives |
| QA | `/bmad-agent-bmm-qa` | Tests, automation |
| UX Designer | `/bmad-agent-bmm-ux-designer` | User flow, design |
| Quick Flow Solo Dev | `/bmad-agent-bmm-quick-flow-solo-dev` | Fast implementation |
| TEA (Test Architect) | `/bmad-agent-tea-tea` | Test architecture |
| Agent Builder | `/bmad-agent-bmb-agent-builder` | Create new agents |
| Module Builder | `/bmad-agent-bmb-module-builder` | Build modules |
| Workflow Builder | `/bmad-agent-bmb-workflow-builder` | Build workflows |
| Brainstorming Coach | `/bmad-agent-cis-brainstorming-coach` | Ideation |
| Creative Problem Solver | `/bmad-agent-cis-creative-problem-solver` | Problem solving |
| Design Thinking Coach | `/bmad-agent-cis-design-thinking-coach` | Design thinking |
| Innovation Strategist | `/bmad-agent-cis-innovation-strategist` | Innovation |
| Presentation Master | `/bmad-agent-cis-presentation-master` | Presentations |
| Storyteller | `/bmad-agent-cis-storyteller` | Narrative |

---

## Multimodal API Dispatch

Direct API access for tasks that bypass tmux entirely. These use Python scripts that call the OpenRouter API directly.

**Trigger:** `dispatch to api: <task>`

### Image Analysis

```
dispatch to api: Analyze https://example.com/screenshot.png with vision model
```

Script: `image-analyze.py --model openai/gpt-4o --input "path/to/image.png" --output -`

### Image Generation

```
dispatch to api: Generate a logo with dall-e-3 for "TechStartup Inc"
```

Script: `image-generate.py --model openai/dall-e-3 --input "logo prompt" --output logo.png`

### Audio Transcription

```
dispatch to api: Transcribe this audio file
```

Script: `audio-process.py --model openai/whisper-1 --input audio.mp3 --output transcript.txt`

### Audio Generation (TTS / Music)

```
dispatch to api: Generate a narration using ElevenLabs
dispatch to api with suno/chirp-v3-5: Create background music
```

Script: `audio-generate.py`

### Video Generation

```
dispatch to api: Generate a 5-second product demo video
dispatch to api with runway/gen-4-turbo: Create a cinematic intro clip
```

Script: `video-generate.py`

### Text Generation (Direct API)

For simple text generation without a full Claude Code session:

```
text-generate.py --model openai/gpt-4o-mini --input "Explain quantum computing" --output -
```

For text tasks that require a full Claude Code session, use tmux dispatch instead.

### API Script Dependencies

Install with:

```bash
pip3 install -r /path/to/model-dispatch/scripts/openrouter-api/requirements.txt
```

---

## When to Use Each Provider

| Scenario | Recommended Provider | Why |
|----------|---------------------|-----|
| Complex architecture or high-stakes analysis | Claude native (Opus) | Deepest reasoning, native integration |
| General development work | Claude native (Sonnet) | Best coding balance, no extra setup |
| Access to non-Claude models (GPT-4o, Llama, Gemini) | OpenRouter | 300+ models through one API |
| Free or low-cost experimentation | Ollama (local) | No API costs, runs on your hardware |
| Cloud-hosted open models | Ollama (cloud) | Large open models without local GPU |
| Ultra-fast inference for simple tasks | Groq or Cerebras | Hardware-accelerated, very low latency |
| Strong coding with Codestral | Mistral | Dedicated coding model |
| Deep reasoning tasks | DeepSeek | DeepSeek-Reasoner excels at chain-of-thought |
| Google Cloud integration | Vertex AI | Enterprise billing, Google ecosystem |
| Image analysis or generation | OpenRouter API (direct) | Multimodal models via API scripts |
| Audio transcription or TTS | OpenRouter API (direct) | Whisper, ElevenLabs, Suno via API scripts |
| Video generation | OpenRouter API (direct) | Runway, Kling, Pika via API scripts |

---

## Troubleshooting

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| `command not found: provider-dispatch` | Wrapper not installed or `~/.local/bin` not in PATH | Run `install.sh` or add `~/.local/bin` to PATH |
| `command not found: claude-dispatch` | Same as above | Same as above |
| `401 unauthorized` | Token missing, empty, or incorrect | Check `~/.<provider>-token` contents and verify chmod 600 |
| `model does not exist` | Wrong base URL or invalid model ID | Verify provider config in `providers.json` |
| Nesting error | `CLAUDECODE` env var inherited by child process | Verify wrapper includes `unset CLAUDECODE` |
| Prompt not submitted in tmux | Enter key pressed before prompt was fully sent | Wait 2 seconds after text appears, then press Enter once |
| Blank pane after launch | Claude Code init wait too short | Increase sleep to 8-10 seconds to allow project context and MCP servers to load |
| Permission dialogs blocking agent | Tools not pre-approved | Use `--allowedTools` flags on the dispatch command |
| Result not delivered | Completion monitor missed the signal | Check `/tmp/model-dispatch-result-*.txt` for captured output |
| `providers.json is not valid JSON` | Malformed config | Re-run `install.sh` to regenerate, or manually fix with `jq` |

### Validation

Run the validation suite to diagnose issues:

```bash
bash /path/to/model-dispatch/scripts/validate-setup.sh
```

All critical checks should pass. Warnings (like missing `inotify-tools`) are non-blocking.

### File Locations Reference

| File | Purpose |
|------|---------|
| `~/.local/bin/claude-dispatch` | Native Claude wrapper |
| `~/.local/bin/provider-dispatch` | Unified provider wrapper (all non-native providers) |
| `~/.config/claude-code-router/providers.json` | Provider configuration |
| `~/.<provider>-token` | API tokens (one per provider, chmod 600) |
| `.claude/skills/model-dispatch/` | Skill directory in your project |
| `.claude/skills/model-dispatch/scripts/` | Support scripts |
| `.claude/skills/model-dispatch/scripts/openrouter-api/` | Direct API Python scripts |
| `/tmp/model-dispatch-result-*.txt` | Captured agent outputs |

### Permissions

Three options for tool permissions on dispatched agents:

**Option A: CLI flags (recommended)**

```bash
provider-dispatch openrouter --model <model> \
  --allowedTools "Edit" "Write" "Read" "Glob" "Grep" "Bash(*)"
```

**Option B: PermissionRequest hook** -- Configure an auto-approve hook in `.claude/settings.local.json`.

**Option C: Project permissions** -- Add tmux and python3 bash patterns to your project's permission allow list.
