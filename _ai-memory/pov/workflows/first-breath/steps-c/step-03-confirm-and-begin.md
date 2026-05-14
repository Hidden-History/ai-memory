---
name: 'step-03-confirm-and-begin'
description: 'Summarize what was captured into BOND and LORE. Confirm with owner. Write first session log. Mark First Breath complete.'
scaffold: '{workflows_path}/STEP-SCAFFOLD.md'
---

# Step 3: Confirm and Begin

**Progress: Step 3 of 3** — TERMINAL STEP. Workflow ends here.

## STEP GOAL:

Close the loop on First Breath. Show the owner what Parzival captured, get correction on anything that's wrong, write the first session log, and transition to normal Parzival operation.

**Scope:**
- Available context: BOND.md (filled in Step 1), LORE.md (filled in Step 2), MEMORY.md (still scaffold), sessions/ directory
- Focus: confirmation + transition — no new discovery here
- Forbidden: ending First Breath without owner confirmation; leaving any literal `{}` placeholder text in BOND or LORE

## Summarize the Captures

Present what Parzival learned, organized:

**About them (BOND):**
- Name and how they're addressed
- Role
- Working style (1-2 sentences)
- What success looks like for them
- Things they've explicitly asked Parzival to remember (if any)
- Things to avoid (if any)

**About the project (LORE):**
- System Architecture (1-2 sentences)
- Key Design Decisions (top 3-5)
- Patterns & Conventions (top 3 if known)
- Things Learned the Hard Way (top 3 if surfaced from bugs/)

Frame the summary as observations the owner can correct, not assertions of fact:

> "Here's what I picked up. Push back on anything that's off."

## Capture Corrections

Update BOND.md and LORE.md with any corrections. Don't argue — the owner is the authority on themselves and their project. Write what they say, not what you inferred.

## Clean Up Placeholder Text

Scan BOND.md and LORE.md for any remaining `_italic-prompt-text_` markers from the scaffolds. Either:
- Replace with real content learned during the conversation
- Replace with a clean note like *"Not yet discovered — explore in early sessions."*

Don't leave template scaffolding in living files.

## Write the First Session Log

Create `sessions/YYYY-MM-DD-first-breath.md` with:
- Date and duration
- Who you met (name, role, the brief)
- What was captured into BOND (high-level summary, not full content — that lives in BOND.md)
- What was captured into LORE (high-level summary)
- Open questions to explore in early sessions (these become the seed for MEMORY.md `Pending Items`)
- Any boundaries or trust limits discussed (becomes the seed for BOND `Trust Boundaries`)

## Update MEMORY.md

Seed MEMORY.md `Pending Items` table with the open questions from the session log. These are natural threads for early sessions instead of starting from scratch.

## Mark First Breath Complete

Confirm to the owner: "I've got enough to be useful. Anything else you want me to know before we shift into normal mode?" If they have something, capture it. If they're ready, transition.

The next time activation step 5 runs, it will detect BOND has substantive content (no scaffold markers) and skip First Breath. From this point forward, Parzival operates normally — interactive sessions with the owner, occasional Pulse if enabled.

## TERMINAL STEP

This is the final step of the First Breath workflow. After completion, return to parzival.md activation step 5. Activation then proceeds to step 6 (load WORKFLOW-MAP) and step 7 (greet the owner and present menu).
