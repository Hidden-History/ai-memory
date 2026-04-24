---
name: session-blocker
description: 'Analyze a blocker, propose resolution options, and log it to the blockers tracking file.'
firstStep: './steps-c/step-01-capture-blocker.md'
---

# Blocker Analysis

**Goal:** When a blocker is encountered, capture it precisely, analyze root cause with resolution options, and log it to tracking so it is visible across sessions.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

### Blocker Analysis Anti-Patterns
- Never log a blocker without attempting root cause analysis
- Never propose only one resolution option (minimum 2)
- Never skip logging because "the blocker will be resolved soon"
- Never mark a blocker as resolved without user confirmation
- Never log vague blocker descriptions (must be specific and actionable)
- Never skip the prior-issues check (Step 1.4) — GC-14 requires checking oversight/bugs/ and oversight/tracking/blockers-log.md BEFORE analysis, even when the blocker seems novel

### Scope Change Branch
If root-cause analysis (Step 1) determines the blocker is a **scope change** rather than a technical blocker:
- Do not continue through standard blocker resolution steps
- Route directly to `[CC] Correct Course` via `{project-root}/.claude/skills/bmad-correct-course/SKILL.md`
- Scope changes require course correction, not blocker resolution

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
