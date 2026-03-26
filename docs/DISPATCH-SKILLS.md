# Parzival Dispatch Skills

Multi-LLM agent dispatch for Claude Code -- design teams, activate agents across providers, and manage the full agent lifecycle.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Skills Reference](#skills-reference)
- [Quick Start](#quick-start)
- [Multi-Provider Setup](#multi-provider-setup)
- [Adding Providers Later](#adding-providers-later)
- [Requirements](#requirements)
- [Detailed Documentation](#detailed-documentation)

---

## Overview

The Parzival dispatch skill suite is a set of 7 skills that enable multi-agent orchestration within Claude Code. Together, they allow Parzival to:

- **Design parallel agent teams** with file ownership isolation and conflict avoidance
- **Activate agents** using either generic or BMAD (Build Measure Analyze Design) personas
- **Route tasks to different LLM providers** -- Claude (native), Ollama, OpenRouter, and 8 additional backends
- **Manage the full agent lifecycle** -- instruction delivery, progress monitoring, output review, correction loops, and shutdown

Each dispatched agent runs in a visible tmux pane with the full Claude Code TUI, so you can watch progress in real time. Results are delivered automatically to the team inbox.

Model Dispatch is entirely optional. Claude Code works perfectly without it. It adds value when you want to use non-Claude models, run agents on cheaper backends, access multimodal capabilities (image/audio/video), or use ultra-fast inference providers for simple tasks.

---

## Architecture

```
User Request
    |
    v
[aim-parzival-team-builder]     Designs team structure for parallel work
    |                            (presets, tier selection, file ownership)
    |
    +-- [aim-parzival-bootstrap]     Loads cross-session memory from Qdrant
    +-- [aim-parzival-constraints]   Loads behavioral constraints
    |
    v
[aim-model-dispatch]            Selects model per agent
    |                            (complexity, role, provider routing)
    |
    +------+------+
    |      |      |
    v      v      v
 [aim-    [aim-   [aim-
  agent-   bmad-   agent-        Activate agents and dispatch instructions
  dispatch dispatch dispatch]    (generic or BMAD persona)
    ]      ]
    |      |      |
    +------+------+
           |
           v
[aim-agent-lifecycle]           Shared lifecycle management
                                 (send, monitor, review, accept/loop,
                                  shutdown, summary)
```

### Pipeline Summary

1. **Team Builder** analyzes the work request, selects a team structure (single agent, 2-tier flat, or 3-tier hierarchical), assigns file ownership, and produces a team design for user approval.
2. **Bootstrap** and **Constraints** load Parzival's cross-session memory and behavioral rules.
3. **Model Dispatch** selects the appropriate LLM model for each agent based on task complexity and role defaults. Routes to the correct provider backend.
4. **Agent Dispatch** (generic) or **BMAD Dispatch** (persona-based) prepares instructions and spawns agents as teammates.
5. **Agent Lifecycle** manages the running agents through a 9-step cycle: prepare, verify, spawn, send, monitor, review, accept/loop, shutdown, summary.

---

## Skills Reference

| Skill | Purpose | When Used |
|-------|---------|-----------|
| `aim-parzival-team-builder` | Designs parallel agent teams (2-tier or 3-tier), assigns file ownership, selects conflict avoidance strategy | When work can be decomposed into independent parallel units |
| `aim-agent-dispatch` | Prepares precise file-referenced instructions and activates generic (non-BMAD) agents | For agents that do not need a BMAD persona (code-reviewer, verify-implementation, skill-creator) |
| `aim-bmad-dispatch` | Selects the correct BMAD agent role, handles two-phase activation (persona load then instruction) | For BMAD roles: Analyst, PM, Architect, DEV, Scrum Master, UX Designer, and others |
| `aim-model-dispatch` | Selects LLM model based on task complexity and agent role; routes to provider backend | Every agent dispatch -- determines whether to use Sonnet, Opus, or a non-Claude model |
| `aim-agent-lifecycle` | Manages running agents: send instruction, monitor progress, review output, accept or loop corrections, shutdown, summary | After any agent is spawned -- shared across both dispatch paths |
| `aim-parzival-bootstrap` | Retrieves cross-session memory from Qdrant (session summaries, decisions, conventions, patterns) | On Parzival activation and after context compaction |
| `aim-parzival-constraints` | Loads the 20-constraint behavioral enforcement system as a context reminder | On Parzival activation and post-compact to prevent behavioral drift |

---

## Quick Start

The dispatch skills are used through Parzival. You do not invoke them directly.

### Starting a Parzival Session

```
/pov:parzival
```

### Designing a Team (TP menu)

From the Parzival menu, use the **TP** (Team Planner) option to design an agent team:

```
You: TP -- I need to implement stories S-101, S-102, and S-103 in parallel
```

Parzival analyzes the work, checks for preset matches, designs the team structure, assigns file ownership, and presents the plan for your approval.

### Dispatching Agents (DA menu)

After approving the team design, use the **DA** (Dispatch Agent) option:

```
You: DA -- dispatch the approved team
```

Parzival activates agents, selects models, and begins the lifecycle loop for each agent.

### Dispatching to a Specific Provider

```
dispatch to openrouter: Write unit tests for the auth module
dispatch to ollama with qwen3-coder-next:cloud: Refactor the user service
dispatch to claude: Analyze the auth module for security issues
```

### Monitoring Agents

```
check on the ollama agent
status of all dispatched agents
```

---

## Multi-Provider Setup

By default, dispatched agents use Claude (native Anthropic API). To enable additional providers, run the interactive installer.

### Running the Installer

```bash
bash _ai-memory/pov/skills/aim-model-dispatch/scripts/install.sh
```

The installer will:

1. Check prerequisites (tmux, python3, jq)
2. Detect any existing provider configuration
3. Present an interactive menu to select which providers to configure
4. Prompt for each provider's API key and store it securely (chmod 600)
5. Confirm or override the default model for each provider
6. Write configuration to `~/.config/claude-code-router/providers.json`
7. Install wrapper scripts (`provider-dispatch`, `claude-dispatch`) to `~/.local/bin/`
8. Install Python dependencies for API scripts
9. Run validation to confirm everything works

### Verifying the Setup

```bash
bash _ai-memory/pov/skills/aim-model-dispatch/scripts/validate-setup.sh
```

All critical checks should pass. Warnings (such as missing `inotify-tools`) are non-blocking.

### Provider Chain

| Provider | What It Offers | Cost |
|----------|---------------|------|
| **Claude** (native) | Deepest reasoning, native Claude Code integration | Anthropic API pricing |
| **Ollama** (local) | Run models on your own hardware, no API costs | Free (local GPU required) |
| **Ollama** (cloud) | Large open models without local GPU | Ollama cloud pricing |
| **OpenRouter** | 300+ models across all major providers through one API | Per-model pricing |
| **Gemini** | Google Gemini models, also supports native Gemini CLI | Google API pricing |
| **DeepSeek** | Strong coding and chain-of-thought reasoning | DeepSeek pricing |
| **Groq** | Ultra-fast inference via dedicated hardware | Groq pricing |
| **Cerebras** | Ultra-fast inference via wafer-scale chips | Cerebras pricing |
| **Mistral** | Codestral for code-focused tasks | Mistral pricing |
| **OpenAI** | GPT-4o, o1, o3-mini | OpenAI pricing |
| **Vertex AI** | Enterprise Google Cloud billing, Claude models via Google | Google Cloud pricing |
| **SiliconFlow** | Chinese and open-source models | SiliconFlow pricing |

### Complexity-Based Model Selection

Parzival automatically assesses task complexity and maps it to a model tier:

| Complexity | Default Tier | Example |
|------------|-------------|---------|
| Straightforward | Sonnet | Clear implementation tasks, simple reviews |
| Moderate | Sonnet | Most development work |
| Significant | Opus | Complex refactoring, architectural changes |
| Complex / architectural | Opus | Deep reasoning, multi-system coordination |

When dispatching to a non-Claude provider, the complexity tier maps to an equivalent model on that provider. A "Sonnet-tier" task on OpenRouter might use `openai/gpt-4o`; an "Opus-tier" task might use `openai/o1`.

---

## Adding Providers Later

To add a new provider to an existing setup:

### Option A: Re-run the Installer

```bash
bash _ai-memory/pov/skills/aim-model-dispatch/scripts/install.sh
```

The installer detects existing configuration and lets you add new providers without reconfiguring existing ones.

### Option B: Manual Configuration

1. Add an entry to `~/.config/claude-code-router/providers.json`:

```json
{
  "newprovider": {
    "baseUrl": "https://api.newprovider.com/v1",
    "keyFile": ".newprovider-token",
    "defaultModel": "model-name",
    "emptyApiKey": false
  }
}
```

2. Create the token file:

```bash
echo "YOUR_API_KEY" > ~/.newprovider-token
chmod 600 ~/.newprovider-token
```

3. Validate:

```bash
bash _ai-memory/pov/skills/aim-model-dispatch/scripts/validate-setup.sh
```

### Adding the Skill to Another Project

If Model Dispatch is already installed system-wide and you want to add it to an additional project:

```bash
bash _ai-memory/pov/skills/aim-model-dispatch/scripts/install.sh /path/to/other-project
```

This skips system-level setup and only copies the skill directory into the project.

---

## Requirements

### Required

| Software | Purpose |
|----------|---------|
| Claude Code | The CLI that agents dispatch to |
| tmux | Pane management for isolated agent sessions |
| python3 | Inbox injection and API scripts |
| jq | JSON parsing in shell scripts |

### Optional

| Software | Purpose |
|----------|---------|
| inotify-tools | Faster file change detection for completion monitoring |
| Gemini CLI | Native Google Gemini dispatch (`npm install -g @google/gemini-cli`) |

### API Keys

Each provider requires its own API key, stored in `~/.<provider>-token` with chmod 600 permissions. The installer handles token storage automatically. See the [setup guide](../_ai-memory/pov/skills/aim-model-dispatch/references/setup-guide.md) for manual token configuration.

### PATH

`~/.local/bin` must be in your PATH for the dispatch wrappers to work. Most Linux distributions include this by default. If missing:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## Detailed Documentation

| Document | Description |
|----------|-------------|
| [docs/parzival/TEAM-BUILDER-GUIDE.md](parzival/TEAM-BUILDER-GUIDE.md) | Team design process, presets, tier selection, file ownership, conflict avoidance |
| [docs/parzival/AGENT-DISPATCH-GUIDE.md](parzival/AGENT-DISPATCH-GUIDE.md) | Generic agent dispatch cycle, instruction template, quality checklist |
| [docs/parzival/BMAD-DISPATCH-GUIDE.md](parzival/BMAD-DISPATCH-GUIDE.md) | BMAD agent selection, activation sequences, role selection matrix |
| [docs/parzival/MODEL-DISPATCH-GUIDE.md](parzival/MODEL-DISPATCH-GUIDE.md) | Multi-provider LLM routing, provider reference, dispatch modes, multimodal API dispatch |
| [Model Dispatch Setup Guide](_ai-memory/pov/skills/aim-model-dispatch/references/setup-guide.md) | Step-by-step installation and configuration |
| [Model Dispatch User Guide](_ai-memory/pov/skills/aim-model-dispatch/references/user-guide.md) | Trigger phrases, backend selection, dispatch examples |
| [Provider Reference](_ai-memory/pov/skills/aim-model-dispatch/references/providers.md) | All supported providers with base URLs, token files, and model formats |
