---
name: 'cycles-research-protocol-instructions'
description: 'Research protocol: define question, check project files, search docs, dispatch analyst, escalate to user, document answer'
---

# cycles-research-protocol — Instructions

## Prerequisites

- A specific research question has been identified
- Project documentation, specification files, and oversight workspace are accessible
- Analyst agent (`bmad-bmm-analyst`) is available for layer 3 research

## Workflow Overview

The research-protocol cycle answers a specific technical or product question using a layered approach: project files first, documentation second, then Analyst agent research if the first two layers are insufficient. Escalation to the user occurs only when the research question cannot be answered from available sources.

The cycle is designed to be exhaustive before escalating and to always produce a documented answer. Research conducted here is recorded for future reference, preventing repeated work on the same questions.

## Step Summary

| Step | File | Purpose |
|------|------|---------|
| 1 | `step-01-define-question.md` | State the research question precisely; define what a satisfactory answer looks like |
| 2 | `step-02-layer1-project-files.md` | Search project files, specs, and oversight docs for an existing answer |
| 3 | `step-03-layer2-documentation.md` | Search external documentation, API references, and knowledge base |
| 4 | `step-04-layer3-analyst-research.md` | Dispatch Analyst agent for deeper structured research if layers 1–2 are insufficient |
| 5 | `step-05-escalate-to-user.md` | Escalate to user only if all three layers cannot produce a satisfactory answer |
| 6 | `step-06-document-answer.md` | Record the answer and its source in the appropriate oversight or project file |

## Key Decisions

- **Layer sequencing**: Layers must be attempted in order (1 → 2 → 3 → escalation); skipping layers is not permitted
- **Escalation threshold**: User escalation in step 5 is only triggered when all three research layers are exhausted
- **Documentation requirement**: Every research cycle must produce a documented answer in step 6 — no undocumented research results

## Outputs

- Research answer documented in the oversight workspace
- Source of the answer recorded

## Exit Conditions

The workflow exits when:
- A satisfactory answer has been documented in step 6
- Or: the question has been escalated to the user in step 5 and the user's response has been recorded
