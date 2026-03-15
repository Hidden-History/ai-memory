---
name: tmux-dispatch
description: 'Generic tmux dispatch for any backend (claude/openrouter/ollama/gemini/deepseek/groq/cerebras/mistral/openai/vertex-ai/siliconflow). Launches Claude Code in tmux pane with backend-appropriate wrapper.'
firstStep: './steps/step-01-resolve-task.md'
---

# Tmux Dispatch (Generic)

Dispatch tasks to any Claude Code backend (claude, openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow) via tmux pane. Uses backend-specific wrappers to ensure correct routing.

This is the generic dispatch workflow — for BMAD tasks, use bmad-dispatch instead.

---

## When This Workflow Applies

Use tmux-dispatch for:
- Generic prompts without BMAD involvement
- Non-BMAD tasks (plain code questions, file operations, etc.)
- Any backend dispatch (claude, openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow)

Do NOT use for:
- BMAD agent commands (use bmad-dispatch)
- Multimodal API tasks (use api-dispatch)

---

## Two-Phase Activation

**Phase 1 (Launch):** Send backend wrapper command to launch interactive Claude Code session.

**Phase 2 (Task):** Send the user's task text. The agent processes and responds.

Sending both phases in a single prompt works for tmux-dispatch (unlike BMAD which requires menu detection).

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
