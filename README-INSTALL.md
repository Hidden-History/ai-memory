# Parzival 2.1 — Install & Reference

**Date**: 2026-03-14
**Version**: 2.1.1 (Dispatch Integration Build)

---

## What This Is

Parzival is an AI Project Oversight Agent — a Technical PM & Quality Gatekeeper that manages project execution through specialized agents. Parzival plans, designs teams, dispatches agents, reviews all output, and ensures quality. He never implements directly.

Version 2.1 separates agent dispatch mechanics from Parzival's core identity (Layer 1) into dedicated skills (Layers 3-4), and adds multi-provider support via the model-dispatch skill.

---

## Architecture Overview

### Execution Pipeline

When Parzival executes work, 3 skills are used in sequence:

```
1. Team Builder     — WHAT can run in parallel, agent instructions
2. Agent Dispatch   — HOW each agent is activated and instructed
3. Model Dispatch   — WHAT model/provider to use, terminal operations
```

### Core Rules

1. **All agents are teammates in parallel** — spawned via Agent tool with `team_name`
2. **BMAD agents follow their own workflow** — persona activation, menu, two-phase interaction
3. **Regular agents receive direct instructions** — full instruction template, one-shot execution
4. **Non-Claude providers** — when the user specifies a provider (e.g., "use openrouter"), the model-dispatch skill handles provider routing and terminal launch via tmux
5. **All reviews go to Parzival** — only Parzival determines issue legitimacy

### Layer Architecture

```
Layer 1 — Parzival Core (always active)
  Agent identity, global constraints, workflow routing, session management
  Files: parzival.md, global constraints, WORKFLOW-MAP.md

Layer 2 — Phase Workflows (loaded per phase)
  Discovery, Architecture, Planning, Execution, Integration, Release, Maintenance
  Files: workflows/phases/*/workflow.md + phase constraints

Layer 3 — Dispatch Skills (loaded on-demand during agent work)
  aim-parzival-team-builder — Team design and parallelization (presets, fast path, token optimization)
  aim-agent-dispatch        — Generic agent instruction + activation
  aim-bmad-dispatch         — BMAD agent selection + persona activation
  aim-agent-lifecycle       — Shared lifecycle: send, monitor, review, accept/loop, shutdown

Layer 4 — Model & Provider Selection (loaded on-demand)
  aim-model-dispatch   — Model tier selection (Opus/Sonnet/Haiku) by complexity and role
  model-dispatch       — Multi-provider terminal launch (standalone skill)
```

---

## Skills Reference

### aim-parzival-team-builder

**Purpose**: Analyze work to be parallelized, design the appropriate team structure, and produce agent instructions.

**When used**: User selects [TP] Team Builder from the menu, or Parzival determines parallel execution is needed.

**What it does**:
- Checks if work matches a **preset** (sprint-dev, story-prep, test-automation, architecture-review, research) — if so, skips full design and produces compact output
- If no preset matches, runs the **6-step design process**: preflight analysis, team composition, file ownership map, context block assembly, conflict avoidance strategy, pre-delivery review
- **Single-agent fast path**: for one task, skips team design entirely and routes directly to dispatch

**Key features**:
- 5 team presets with workflow commands and model defaults
- Compact assignment list format for file ownership (not sparse matrices)
- Domain-named AI_MEMORY_AGENT_IDs for cross-session memory
- Context blocks without redundant forbidden file lists — ownership map is the source of truth
- Does NOT assemble copy-paste prompts — dispatch handles prompt assembly

**Output**: Team design document with context blocks, ready for dispatch.

---

### aim-bmad-dispatch

**Purpose**: Select the correct BMAD agent, determine activation method, and manage the dispatch.

**When used**: Task requires a BMAD agent role (Analyst, PM, Architect, DEV, SM, UX Designer).

**What it does**:
- Selects the correct agent using the Quick Selection Matrix and agent-selection-guide
- Determines **dispatch mode**:
  - **Execution mode**: one-shot instruction (DEV implementing, DEV reviewing, SM creating stories)
  - **Planning mode**: interactive relay protocol (PM creating PRD, Architect designing, Analyst researching)
- Spawns agent as teammate in parallel (Agent tool with team_name)
- Activates BMAD persona with the correct command (e.g., `/bmad-agent-bmm-dev`)
- For planning mode, follows the **Relay Protocol**: agent asks questions, Parzival researches answers from project files, presents recommendations with confidence levels to user, relays confirmed answers back to agent
- For non-Claude providers, delegates terminal launch to the model-dispatch skill

**Activation commands**:

| Agent | Command | Planning Mode Workflows |
|-------|---------|------------------------|
| Analyst | /bmad-agent-bmm-analyst | /bmad-bmm-market-research, /bmad-bmm-domain-research, /bmad-bmm-technical-research, /bmad-bmm-create-product-brief |
| PM | /bmad-agent-bmm-pm | /bmad-bmm-create-prd, /bmad-bmm-create-epics-and-stories |
| Architect | /bmad-agent-bmm-architect | /bmad-bmm-create-architecture, /bmad-bmm-check-implementation-readiness |
| DEV | /bmad-agent-bmm-dev | /bmad-bmm-dev-story (execution), /bmad-bmm-code-review (execution) |
| SM | /bmad-agent-bmm-sm | /bmad-bmm-sprint-planning, /bmad-bmm-create-story |
| UX Designer | /bmad-agent-bmm-ux-designer | /bmad-bmm-create-ux-design |

**Key constraint**: DC-08 — Analyst research MUST precede PM when input is thin.

---

### aim-agent-dispatch

**Purpose**: Prepare instructions and activate generic agents (non-BMAD).

**When used**: Task requires a generic agent (code-reviewer, verify-implementation, skill-creator, or any non-BMAD worker).

**What it does**:
- Prepares the full instruction using the **instruction template** with 8 sections: TASK, CONTEXT, REQUIREMENTS, SCOPE (IN/OUT), OUTPUT EXPECTED, DONE WHEN, STANDARDS, BLOCKERS
- Verifies instruction quality: complete, unambiguous, scoped, cited (references project files), measurable
- Spawns agent as **teammate in parallel** (Agent tool with team_name)
- For non-Claude providers, delegates terminal launch to the model-dispatch skill

**Key constraints**:
- EC-02: MUST use instruction template for every dispatch
- GC-11: Every requirement must cite a project file, every DONE WHEN must be objectively measurable

---

### aim-agent-lifecycle

**Purpose**: Manage the full agent lifecycle after activation — send, monitor, review, accept/loop, shutdown, summary.

**When used**: After any agent (BMAD or generic) is activated and ready to receive work.

**What it does**:
- **Mode check**: determines execution mode (one-shot instruction) vs planning mode (relay protocol) vs non-Claude provider (tmux monitoring)
- **Step 4 — Send instruction**: complete instruction via SendMessage, handle clarification requests
- **Step 5 — Monitor**: track progress via TaskList/SendMessage (teammates) or capture-pane (tmux agents)
- **Step 6 — Review**: run output review checklist against DONE WHEN criteria and project requirements
- **Step 7 — Accept or loop**: accept when all criteria met, or send correction with specific fix instructions. Hard cap at 3 correction loops, then escalate to user
- **Step 8 — Shutdown**: SendMessage shutdown_request (teammates) or close tmux pane (non-Claude)
- **Step 9 — Summary**: write summary in Parzival's words — never copy-paste agent output

**Key constraints**:
- GC-09: ALWAYS review agent output before accepting
- GC-10: ALWAYS present summaries, never raw agent output
- GC-12: ALWAYS loop dev-review until zero legitimate issues

---

### aim-model-dispatch

**Purpose**: Select the appropriate model tier for each agent based on task complexity and role.

**When used**: Called by aim-agent-dispatch and aim-bmad-dispatch before agent activation.

**What it does**:
- Assesses task complexity (Straightforward / Moderate / Significant / Complex)
- Maps complexity + role to model tier:
  - **Opus**: Architect (default), complex/architectural tasks, significant coordination
  - **Sonnet**: DEV, Analyst, PM, SM, UX (default), moderate tasks
  - **Haiku**: Simple high-volume parallel tasks only
- For Claude-native agents: returns model parameter for Agent tool
- For non-Claude providers: model tier informs provider model selection — defers to model-dispatch skill for provider routing and terminal launch

**Override rules**:
1. User override always wins
2. Failed fix escalation — consider Opus after failed correction loop
3. Haiku — never for implementation, review, or planning
4. Cost awareness — Opus only when reasoning depth justifies cost
5. Non-Claude providers — model-dispatch skill handles provider selection, model ID resolution, and terminal launch

---

### aim-parzival-bootstrap (Core)

**Purpose**: Cross-session memory system. Enables Parzival to persist and recall context across sessions.

**When used**: Loaded at activation (Step 5).

---

### aim-parzival-constraints (Core)

**Purpose**: Constraint loading system. Manages global and phase-specific constraint activation.

**When used**: Loaded at activation (Step 5).

---

## Team Presets

Pre-validated team configurations for common patterns. Presets skip the full 6-step design process.

### sprint-dev
**When**: 2-3 stories need parallel implementation with code review
**Structure**: SM Lead (Opus) + 2 DEV workers (Sonnet) + 1 DEV reviewer (Opus)
**Commands**: Workers: `/bmad-bmm-dev-story`, Reviewer: `/bmad-bmm-code-review`

### story-prep
**When**: Multiple stories need to be created from epics in bulk
**Structure**: PM Lead (Opus) + 2-3 SM story creators (Sonnet)
**Commands**: Workers: `/bmad-bmm-create-story`

### test-automation
**When**: Completed stories need automated test coverage
**Structure**: TEA Lead (Opus) + 2 QA workers (Sonnet)
**Commands**: Workers: `/bmad-bmm-qa-automate`

### architecture-review
**When**: Pre-sprint architecture work with parallel research
**Structure**: Architect Lead (Opus) + Analyst worker (Sonnet) + UX Designer worker (Sonnet)
**Commands**: Analyst: `/bmad-bmm-technical-research`, UX: `/bmad-bmm-create-ux-design`

### research
**When**: Phase 1 parallel research across market, domain, and technical
**Structure**: Analyst Lead (Opus) + 3 Analyst workers (Sonnet)
**Commands**: `/bmad-bmm-market-research`, `/bmad-bmm-domain-research`, `/bmad-bmm-technical-research`

---

## Multi-Provider Support

When the user specifies a non-Claude provider (e.g., "use openrouter", "use ollama"), the model-dispatch skill handles:
- Provider routing and model ID resolution
- tmux terminal launch with backend-specific wrapper scripts
- Two-phase BMAD activation in tmux
- Monitoring via tmux capture-pane

**Configured providers** (from `~/.config/claude-code-router/providers.json`):
- **openrouter** — 300+ models, default: anthropic/claude-sonnet-4-6
- **ollama** — Cloud and local models, default: glm-5:cloud
- **gemini** — Native Gemini CLI, default: gemini-2.0-flash

Additional providers can be added: deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow.

---

## What Changed in 2.1

### New Skills (4)
- `aim-agent-dispatch` — Generic agent instruction prep + activation (Layer 3a)
- `aim-bmad-dispatch` — BMAD agent selection + activation commands (Layer 3b)
- `aim-agent-lifecycle` — Shared lifecycle: send, monitor, review, accept/loop, shutdown, summary (Layer 3 shared)
- `aim-model-dispatch` — Model selection criteria by complexity and role (Layer 4)

### Skills Retained (3)
- `aim-parzival-bootstrap` — name kept (aim-parzival-* prefix retained, not renamed to shorter form)
- `aim-parzival-constraints` — name kept
- `aim-parzival-team-builder` — significantly enhanced (+ presets, fast path, token optimization), name kept

### Added in 2.1.1
- Planning mode + Relay Protocol in aim-bmad-dispatch
- Workflow commands table (maps phases to BMAD slash commands)
- 5 team presets in aim-parzival-team-builder (sprint-dev, story-prep, test-automation, architecture-review, research)
- Compact output formats (fast path, assignment lists, no prompt duplication)
- Non-Claude provider delegation to model-dispatch skill
- Teammates in parallel enforcement across all dispatch skills
- Config alignment (core/config.yaml user_name fixed)

### Moved Files
- `instruction.template.md` -> `aim-agent-dispatch/templates/`
- `agent-correction.md` -> `aim-agent-lifecycle/templates/`
- `team-prompt-2tier.template.md` -> `aim-parzival-team-builder/templates/`
- `team-prompt-3tier.template.md` -> `aim-parzival-team-builder/templates/`
- `agent-selection-guide.md` -> `aim-bmad-dispatch/data/`

### Deleted
- `session/team-prompt/` workflow (7 files) — superseded by aim-parzival-team-builder skill
- `teams_enabled` from config.yaml — team infrastructure is implicit

---

## Install Steps

### 1. Backup Current State
```bash
cp -r _ai-memory/ _ai-memory.backup.$(date +%Y%m%d)/
cp -r .claude/ .claude.backup.$(date +%Y%m%d)/
```

### 2. Copy New Files
```bash
cp -r Parzival_2.1/_ai-memory/* _ai-memory/
cp -r Parzival_2.1/.claude/* .claude/
```

### 3. Remove Deleted Workflow
```bash
rm -rf _ai-memory/pov/workflows/session/team-prompt/
```

### 4. Remove Moved Files from Old Locations
```bash
rm -f _ai-memory/pov/templates/instruction.template.md
rm -f _ai-memory/pov/templates/team-prompt-2tier.template.md
rm -f _ai-memory/pov/templates/team-prompt-3tier.template.md
rm -f _ai-memory/pov/data/agent-selection-guide.md
rm -f _ai-memory/pov/constraints/execution/EC-02-use-instruction-template.md
rm -f _ai-memory/pov/constraints/discovery/DC-08-analyst-before-pm-thin-input.md
```

## Verify

```bash
# Should return 0 matches
grep -r "teams_enabled" _ai-memory/ --include="*.yaml"

# Should not exist
ls _ai-memory/pov/workflows/session/team-prompt/ 2>/dev/null

# New skills should exist
ls .claude/skills/aim-agent-dispatch/SKILL.md
ls .claude/skills/aim-bmad-dispatch/SKILL.md
ls .claude/skills/aim-agent-lifecycle/SKILL.md
ls .claude/skills/aim-model-dispatch/SKILL.md
ls .claude/skills/aim-parzival-team-builder/SKILL.md

# Retained skills should still exist (aim-parzival-* names were NOT changed)
ls .claude/skills/aim-parzival-bootstrap/
ls .claude/skills/aim-parzival-constraints/
ls .claude/skills/aim-parzival-team-builder/
```

## Rollback

If anything goes wrong:
```bash
rm -rf _ai-memory/ .claude/
mv _ai-memory.backup.*/ _ai-memory/
mv .claude.backup.*/ .claude/
```

The system continues working as-is with no changes.

---

## Model Dispatch — Multi-Provider Setup

The `aim-model-dispatch` skill enables dispatching agents to 11 different LLM backends (Claude native, OpenRouter, Ollama, Gemini, DeepSeek, Groq, Cerebras, Mistral, OpenAI, Vertex AI, SiliconFlow). This section covers the full installation for multi-provider support.

### Prerequisites

```bash
tmux -V            # Required — pane management for all dispatch
python3 --version  # Required — API scripts and inbox injection
jq --version       # Required — JSON parsing in shell scripts
claude --version   # Required — Claude Code CLI
```

Optional but recommended:
```bash
which inotifywait  # Faster completion detection (~2s vs ~10s polling)
# Install: sudo apt install inotify-tools
```

### Step 1: Run the Interactive Installer

```bash
bash .claude/skills/aim-model-dispatch/scripts/install.sh
```

The installer will:
1. Check all prerequisites
2. Import existing config from `~/.config/claude-code-router/config.json` if present
3. Prompt you to select which providers to configure
4. Collect API keys for each selected provider
5. Create `~/.config/claude-code-router/providers.json`
6. Install wrapper scripts to `~/.local/bin/`
7. Run validation checks

### Step 2: Create API Token Files

For each provider you want to use, create a token file with strict permissions:

```bash
# Example for OpenRouter
echo "sk-or-your-key-here" > ~/.openrouter-token && chmod 600 ~/.openrouter-token

# Example for Anthropic (Claude native)
echo "sk-ant-your-key-here" > ~/.anthropic-token && chmod 600 ~/.anthropic-token
```

**All supported token files** (chmod 600 required for each):

| Provider | Token File | Get Key From |
|----------|-----------|-------------|
| Claude | `~/.anthropic-token` | console.anthropic.com |
| OpenRouter | `~/.openrouter-token` | openrouter.ai/settings/keys |
| Ollama | `~/.ollama-token` | Local or cloud endpoint |
| Gemini | `~/.gemini-token` | Google AI Studio |
| DeepSeek | `~/.deepseek-token` | api.deepseek.com |
| Groq | `~/.groq-token` | api.groq.com |
| Cerebras | `~/.cerebras-token` | api.cerebras.ai |
| Mistral | `~/.mistral-token` | api.mistral.ai |
| OpenAI | `~/.openai-token` | api.openai.com |
| Vertex AI | `~/.vertex-token` | Google Cloud Console |
| SiliconFlow | `~/.siliconflow-token` | api.siliconflow.cn |

### Step 3: Verify PATH

The wrapper scripts are installed to `~/.local/bin/`. Ensure this is in your PATH:

```bash
echo $PATH | grep -q "$HOME/.local/bin" && echo "OK" || echo "NEEDS FIXING"
```

If not in PATH, add to `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then reload: `source ~/.bashrc`

### Step 4: Verify Wrapper Installation

```bash
which provider-dispatch   # Should show ~/.local/bin/provider-dispatch
which claude-dispatch      # Should show ~/.local/bin/claude-dispatch
```

**What the wrappers do:**
- `claude-dispatch` — Clean native Anthropic API routing. Unsets provider overrides, launches fresh Claude Code session.
- `provider-dispatch <provider> [args]` — Reads providers.json, sets ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN from the provider config, launches Claude Code with provider routing.

### Step 5: Install Python Dependencies (for API dispatch)

Required for direct OpenRouter API calls (image/audio/video generation):

```bash
pip3 install openai>=1.0.0 requests>=2.28.0
```

### Step 6: Verify providers.json

The provider config must be at this exact path (hardcoded):

```bash
cat ~/.config/claude-code-router/providers.json | jq .
```

Expected format:
```json
{
  "providers": {
    "openrouter": {
      "baseUrl": "https://openrouter.ai/api",
      "keyFile": "~/.openrouter-token",
      "defaultModel": "anthropic/claude-sonnet-4-6",
      "emptyApiKey": true
    },
    "ollama": {
      "baseUrl": "https://ollama.com",
      "keyFile": "~/.ollama-token",
      "defaultModel": "glm-5:cloud",
      "emptyApiKey": false
    }
  }
}
```

**Key fields:**
- `baseUrl` — API endpoint (set as ANTHROPIC_BASE_URL when dispatching)
- `keyFile` — Path to token file (must be chmod 600)
- `defaultModel` — Used when user doesn't specify a model
- `emptyApiKey` — Only OpenRouter requires this (set to true)

### Step 7: Run Full Validation

```bash
bash .claude/skills/aim-model-dispatch/scripts/validate-setup.sh
```

Expected output on success:
```
=== model-dispatch Validation Suite ===
[PASS] provider-dispatch in PATH
[PASS] claude-dispatch in PATH
[PASS] providers.json found
[PASS] providers.json is valid JSON
[PASS] Provider openrouter: token file exists (chmod 600)
...
=== Summary ===
Passed: 10
Failed: 0
Warnings: 1
All critical checks passed!
```

### Step 8 (Optional): Gemini Native CLI

For native Google Gemini dispatch (bypasses OpenRouter):

```bash
npm install -g @google/gemini-cli
```

### Step 9 (Optional): Auto-Approve Hook

For supervised agent sessions where you want to auto-approve tool permissions:

Add to `.claude/settings.local.json`:
```json
{
  "hooks": {
    "PermissionRequest": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "/absolute/path/to/.claude/skills/aim-model-dispatch/scripts/auto-approve-hook.sh"
      }]
    }]
  }
}
```

**Warning**: This auto-approves ALL permission requests. Use only for supervised agent sessions.

### Verify Model Dispatch

Test a dispatch to confirm everything works:

```bash
# Test native Claude dispatch
claude-dispatch -p "Hello, what model are you?"

# Test OpenRouter dispatch
provider-dispatch openrouter -p "Hello, what model are you?" --model anthropic/claude-sonnet-4-6

# Test Ollama dispatch (if configured)
provider-dispatch ollama -p "Hello, what model are you?"
```

### Critical Configuration Notes

1. **providers.json path is hardcoded** — Must be `~/.config/claude-code-router/providers.json`
2. **Token files must be chmod 600** — Validation will fail otherwise
3. **OpenRouter requires empty API key** — `provider-dispatch` handles this automatically via the `emptyApiKey` flag
4. **SKILL_DIR is not persistent across Bash calls** — Every script sets it inline:
   ```bash
   SKILL_DIR="$(pwd)/.claude/skills/aim-model-dispatch" && bash "${SKILL_DIR}/scripts/..."
   ```
5. **Nesting protection** — All wrappers unset `CLAUDECODE` to prevent recursive launches
6. **BMAD dispatch is two-phase** — Activation command first, wait for menu, then send task. Generic dispatch is single-phase.
7. **WSL2 note** — In-process mode recommended for WSL2. tmux works best on macOS.

### Supported API Scripts (OpenRouter Direct)

For multimodal tasks that bypass tmux and call OpenRouter API directly:

| Script | Purpose | Example |
|--------|---------|---------|
| `text-generate.py` | Chat completions | Text generation without tmux |
| `image-analyze.py` | Vision model | Analyze screenshots/photos |
| `image-generate.py` | DALL-E 3, Flux | Create images from prompts |
| `audio-process.py` | Whisper | Transcribe audio to text |
| `audio-generate.py` | TTS, Suno | Narration, music generation |
| `video-generate.py` | Runway, Kling, Pika | Generate video from prompts |
| `list-models.py` | Model catalog | Query available models |

**Usage example:**
```bash
SKILL_DIR="$(pwd)/.claude/skills/aim-model-dispatch"
python3 "${SKILL_DIR}/scripts/openrouter-api/image-analyze.py" \
  --model openai/gpt-4o \
  --input "path/to/screenshot.png" \
  --output -
```

### Troubleshooting

| Issue | Solution |
|-------|---------|
| `provider-dispatch: command not found` | Add `~/.local/bin` to PATH and reload shell |
| `providers.json not found` | Run `install.sh` or create manually at `~/.config/claude-code-router/providers.json` |
| `Token file not found` | Create with `echo "key" > ~/.provider-token && chmod 600 ~/.provider-token` |
| `Permission denied on token` | `chmod 600 ~/.provider-token` |
| tmux pane closes immediately | Check wrapper script for errors: `bash -x ~/.local/bin/provider-dispatch openrouter` |
| Completion detection slow | Install `inotify-tools`: `sudo apt install inotify-tools` |
| OpenRouter returns 401 | Verify `emptyApiKey: true` in providers.json for openrouter entry |
