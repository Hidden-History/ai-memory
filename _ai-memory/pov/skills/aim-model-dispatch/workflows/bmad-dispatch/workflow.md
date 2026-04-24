---
name: bmad-dispatch
description: 'Two-phase BMAD agent dispatch via tmux panes. Supports all backends (claude/openrouter/ollama/gemini/deepseek/groq/cerebras/mistral/openai/vertex-ai/siliconflow) with backend-aware wrapper commands.'
firstStep: './steps/step-01-resolve-agent.md'
---

# BMAD Agent Dispatch (Enhanced)

Dispatch tasks to BMAD agents running in tmux panes via any Claude Code backend. This enhanced version supports claude, openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, and siliconflow backends with appropriate wrapper commands.

BMAD agents require a two-phase activation: first the persona loads and presents a menu, then task directions are sent. This workflow handles that sequencing plus multi-turn interaction monitoring.

---

## When This Workflow Applies

**ALL BMAD tasks dispatched via tmux MUST use this workflow.** Single-phase dispatch breaks the BMAD persona system.

Use this workflow when the task involves ANY BMAD functionality:
- Code review, story implementation, PRD creation, doc validation, sprint planning, etc.
- Any task that would use a `/bmad-*` command in a normal Claude Code session

The workflow maps tasks to the correct parent agent and menu code.

---

## Backend Selection

| User Says | Backend | Wrapper |
|---|---|---|
| "dispatch to claude" / "use native claude" | `claude` | `claude-dispatch` |
| "dispatch to openrouter" / "use 300 models" | `openrouter` | `provider-dispatch openrouter` |
| "dispatch to ollama" / "use ollama" / "remote model" | `ollama` | `provider-dispatch ollama` |
| "use gemini" / "google model" | `gemini` | `provider-dispatch gemini` |
| "use deepseek" | `deepseek` | `provider-dispatch deepseek` |
| "use groq" | `groq` | `provider-dispatch groq` |
| "use cerebras" | `cerebras` | `provider-dispatch cerebras` |
| "use mistral" / "codestral" | `mistral` | `provider-dispatch mistral` |
| "use openai" / "gpt-4o" | `openai` | `provider-dispatch openai` |
| "use vertex-ai" / "vertex ai" / "google vertex" | `vertex-ai` | `provider-dispatch vertex-ai` |
| "use siliconflow" / "silicon flow" | `siliconflow` | `provider-dispatch siliconflow` |
| No backend specified | `claude` | `claude-dispatch` |

The backend selection affects:
1. **WRAPPER_CMD**: Which command launches Claude
2. **MODEL**: Model ID (only relevant for ollama)

---

## Two-Phase Activation

**Phase 1 (Activation):** Sending `/bmad-agent-{type}` causes the Claude instance to load its persona and present a menu.

**Phase 2 (Task):** After the menu appears, send the menu selection code (e.g., `DS` for Dev Story) or direct task text.

Sending both phases in a single prompt breaks the activation pattern — the agent never loads its persona.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Step Processing Rules
1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute numbered sections in order
3. **WAIT FOR INPUT**: Halt at decision points and wait for user direction
4. **LOAD NEXT**: When directed, load and execute the next step file

### Critical Rules
- NEVER load multiple step files simultaneously
- ALWAYS read entire step file before execution
- NEVER skip steps unless explicitly optional
- ALWAYS follow exact instructions in step files
- ALWAYS wait for user input at model selection gates before proceeding

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
