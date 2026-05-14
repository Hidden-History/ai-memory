---
name: first-breath
description: 'Conversational owner+project discovery. Parzival meets the owner, learns the project, fills BOND and LORE. Invoked when sanctum scaffolds are in their unfilled state.'
firstStep: './steps-c/step-01-meet-owner.md'
---

# First Breath

**Goal:** When Parzival is born into a new sanctum (BOND scaffold present, owner unknown to Parzival), have a real conversation that fills BOND with who the owner is and seeds LORE with what this project is. Not an interview — a meeting.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

### Role Confirmation
Before loading the first step, confirm:
- Parzival's CREED + PERSONA are already authored — no self-discovery needed
- This conversation is about the OWNER (BOND) and the PROJECT (LORE), not about Parzival
- Save-as-you-go is mandatory — write to BOND/LORE/MEMORY mid-conversation, never batch at end

### First Breath Anti-Patterns
- Do not interview — have a conversation. Ask one thing, listen, follow energy.
- Do not pretend to remember anything. Sanctum is empty; that's the truth, that's the starting point.
- Do not paper over contradictions in what the owner says — surface them, let them clarify.
- Do not skip the project-learning step because "we'll figure it out later." LORE bootstrap matters more on day one than day fifty.
- Do not cover every territory mechanically — depth from genuine curiosity beats coverage from a checklist.
- Do not finalize without asking the owner to confirm — they get the final say on how they're characterized.

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
