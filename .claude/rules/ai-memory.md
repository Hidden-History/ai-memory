# AI Memory — Agent Guidance

This file ships with the **AI-Memory** module and is loaded into every Claude Code session in this project. It explains how to work with the memory system, plus the general engineering conduct AI-Memory expects. (Your own project's `CLAUDE.md` is separate and untouched.)

## Using AI Memory

AI Memory is a persistent context layer: it captures decisions, code patterns, and conventions as you work, and surfaces the relevant past context automatically — at session start and per turn — so you don't re-explain prior work.

- **Recall is automatic.** Relevant memory is injected on session resume and as you work; you rarely need to ask for it.
- **Search on demand** with the `aim-search` skill. Check system health with `aim-status`; deliberately store something with `aim-save`; view configuration with `aim-settings`.
- **Memory is project-scoped** — each project's memory is isolated. The project id is auto-detected; override it with the `AI_MEMORY_PROJECT_ID` environment variable (or in `.claude/settings.json`). If you work across multiple repos, confirm the active project with `aim-status`.
- **Capture runs in the background** via hooks — no action needed. For throwaway or experimental work where you don't want it recorded, toggle capture with `aim-pause-updates`.
- **Trust but verify recalled facts.** Injected memories describe what was true when written. If a recalled fact names a file, flag, or function, confirm it still exists before relying on it.

## If something's off

AI-Memory is actively developed. If an `aim-*` skill, hook, or piece of guidance is confusing, behaves unexpectedly, or looks stale, **surface it** — tell the person you're working with, or open an issue on the AI-Memory repository (https://github.com/Hidden-History/ai-memory/issues). That feedback shapes the product. Don't silently work around a broken skill.

---

# General engineering conduct

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
