---
name: 'step-02-learn-project'
description: 'Learn the project. Read available bootstrap files. Ask the owner about architecture, stage, what they need from Parzival. Capture into LORE.'
nextStepFile: './step-03-confirm-and-begin.md'
scaffold: '{workflows_path}/STEP-SCAFFOLD.md'
---

# Step 2: Learn the Project

**Progress: Step 2 of 3** — Next: Confirm and Begin

## STEP GOAL:

Bootstrap LORE for this project. Read what's available, ask the owner to fill the gaps, distill it into LORE. By end of step, LORE should have substantive content in System Architecture and Key Design Decisions sections.

**Scope:**
- Available context: project files at `{project_root}/`, BOND.md (just-filled in Step 1), LORE.md scaffold
- Focus: project discovery only — your own self-discovery was skipped (CREED+PERSONA pre-authored)
- Save-as-you-go: write to LORE.md as understanding builds
- Forbidden: skipping bootstrap reading because "the owner will tell me everything" — read first, ask second; the owner shouldn't have to explain what's already documented

## Read Bootstrap Files (Self-Service First)

LORE.md `## Bootstrapping LORE for a New Project` section lists the standard files to check. Do this BEFORE asking the owner — don't waste their time explaining what's in `README.md`.

For each file that exists, distill the signal into LORE.md:
- `README.md` → System Architecture section: what this project does, who it's for, how it runs
- `CHANGELOG.md` → Key Design Decisions section: notable shifts, version history hints at trajectory
- `oversight/tracking/decision-log.md` → Key Design Decisions: copy the WHY of major decisions, not the what
- `oversight/plans/` → Key Design Decisions: what's been planned, what's in flight, what's deferred
- `oversight/bugs/` → Things Learned the Hard Way: recurring failure modes, classes of bugs the project has fought
- `docs/` → System Architecture, Patterns & Conventions: architecture diagrams, design specs
- `package.json` / `pyproject.toml` / equivalent → System Architecture: language, framework, key deps
- `.github/workflows/` → Patterns & Conventions: CI gates, what's enforced

If a file doesn't exist, note its absence in LORE if it would normally be expected (e.g., "no oversight/ pattern in use" tells future Parzival how to think about tracking).

## Ask the Owner to Fill the Gaps

Now you have a baseline. Surface what you understand, ask them to correct or expand. Open with what you learned, not what you don't know:

> "I read through README and CHANGELOG. It looks like this project [your understanding]. A few things I want to check: [specific questions, not 'tell me about your project']."

Good follow-ups:
- What's the most recent meaningful change, and what was the reasoning?
- What patterns or conventions matter enough that you'd want me to flag a violation?
- Where are the parts of the codebase you'd describe as "stable and trusted" vs "evolving" vs "load-bearing but fragile"?
- What's the failure mode you most want to avoid?
- What's the next 1-2 things on your roadmap?

Capture answers into the appropriate LORE section as they arrive.

## Distill, Don't Paste

LORE is for what Parzival USES, not what Parzival has SEEN. After capturing, look at each section:
- Is every line earning its place?
- Could two bullets become one?
- Is there generic advice that doesn't help on THIS project? Cut it.

Target a LORE that a fresh Parzival could read in 60 seconds and feel oriented enough to be useful immediately.

## Save-As-You-Go Discipline

Update LORE.md every few exchanges:
- `## System Architecture` — what this project is, how its pieces connect
- `## Key Design Decisions` — major decisions that shape ongoing work
- `## Patterns & Conventions` — what the owner cares about enough to correct
- `## Things Learned the Hard Way` — recurring failure modes (often surfaced from bugs/ reading)

## When to Move On

When LORE has substantive content in at least System Architecture and Key Design Decisions, move to Step 3. Patterns & Conventions and Things Learned the Hard Way will keep growing through ongoing sessions — don't try to complete them now.

## CRITICAL STEP COMPLETION NOTE

When LORE.md has substantive content in core sections, load and read fully {nextStepFile}.
