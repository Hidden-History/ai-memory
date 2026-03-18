---
name: api-dispatch
description: 'OpenRouter direct API dispatch for multimodal tasks (image/audio/video). No tmux, runs Python scripts directly.'
firstStep: './steps/step-01-classify.md'
---

# API Dispatch (Direct OpenRouter API)

Dispatch multimodal tasks directly to OpenRouter API endpoints. No tmux involved — this runs Python scripts that call the OpenRouter API directly.

This workflow handles:
- Image analysis (vision models)
- Image generation (DALL-E, flux, etc.)
- Audio processing (whisper transcription)
- Audio generation (TTS, music generation)
- Video generation (runway, kling, pika, etc.)

---

## When This Workflow Applies

Use api-dispatch for:
- **Analyze image** — Vision models like claude-sonnet-4-6, gpt-4o
- **Generate image** — Image models like dall-e-3, flux
- **Process audio** — Whisper transcription
- **Generate audio** — TTS models like tts-1-hd, elevenlabs; music generation via suno
- **Generate video** — Video models like runway/gen-4-turbo, kling, pika, luma
- **Multimodal prompts** — Tasks combining text and images

Do NOT use for:
- Text-only prompts (use tmux-dispatch instead)
- BMAD agent tasks (use bmad-dispatch)
- Native Claude Code session (use tmux-dispatch)

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
