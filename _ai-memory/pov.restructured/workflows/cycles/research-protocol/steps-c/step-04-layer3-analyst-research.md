---
name: 'step-04-layer3-analyst-research'
description: 'Layer 3 research: Activate the Analyst agent for deep codebase research when Layers 1-2 are exhausted'
nextStepFile: './step-05-escalate-to-user.md'
analystInstructionTemplate: '../templates/analyst-research-instruction.md'
---

# Step 4: Layer 3 -- Analyst Agent Deep Research

**Progress: Step 4 of 6** — Next: Escalate to User

## STEP GOAL:

When project files and official documentation do not provide a clear, project-appropriate answer, activate the Analyst agent for deep codebase research. The Analyst examines the current codebase to find patterns, implementations, and evidence that address the research question.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Activate Analyst only after both Layer 1 and Layer 2 are genuinely exhausted
- 🚫 FORBIDDEN to accept Analyst output without independent verification
- 💬 Approach: Structured instruction to Analyst with all prior layer findings included
- 📋 Return to Analyst with specific correction if any verification check fails

## EXECUTION PROTOCOLS:

- 🎯 Build comprehensive research instruction using `{analystInstructionTemplate}`
- 💾 Record all Analyst findings with specific file paths and line numbers
- 📖 Load next step only after Layer 3 results are fully evaluated
- 🚫 FORBIDDEN to activate Analyst before exhausting Layers 1 and 2

## CONTEXT BOUNDARIES:

- Available context: The research question, Layer 1 results, Layer 2 results, the project codebase
- Focus: Codebase research only — this is not a general knowledge query
- Limits: Analyst researches the codebase only. Both Layer 1 and Layer 2 must be exhausted before activating Analyst.
- Dependencies: Research question from Step 1, Layer 1 results from Step 2, Layer 2 results from Step 3

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Confirm Analyst Activation is Warranted

Activate Analyst when:
- The question requires reading and understanding the current codebase
- The question requires cross-referencing multiple files or modules
- The question involves undocumented behavior that must be inferred from code
- The question requires understanding how the project currently implements something similar
- Layer 1 and Layer 2 have both been exhausted

---

### 2. Build Analyst Research Instruction

Using `{analystInstructionTemplate}`, construct the instruction with:
- The precise research question
- Context: why this needs to be answered
- Layer 1 findings: what was found or not found in project files
- Layer 2 findings: what external sources were checked and what they said
- Research scope: specific files, modules, or patterns to examine
- Output required: current codebase behavior, existing patterns, recommendation with file/line citations

---

### 3. Dispatch Analyst via WF-AGENT-DISPATCH

Send the research instruction to the Analyst agent through the standard dispatch workflow.

---

### 4. Review Analyst Research Output

Before accepting Analyst research output, verify:
- Are all findings cited with specific file paths and line numbers?
- Does the recommendation follow logically from the findings?
- Are there any unsupported assumptions in the output?
- Does the answer actually resolve the original question?
- Does the recommended approach fit the project's architecture?
- Are there any contradictions with known project decisions?

If any check fails: return to Analyst with specific correction. Do not accept partially verified research.

---

### 5. Evaluate Layer 3 Results

**FOUND -- verified answer from codebase research:**
- Record all citations
- Confirm the answer resolves the original question
- Proceed with confidence level: INFORMED (codebase evidence)
- Skip to step-06 (document answer) or return to calling workflow

**FOUND -- conflicting patterns in codebase:**
- Document the conflict precisely
- This likely indicates tech debt or inconsistency
- Escalate to user with full context via `{nextStepFile}` -- do not pick one arbitrarily

**NOT FOUND -- codebase does not address this:**
- Document what was searched and what gaps exist
- This is now a genuine decision that must be made
- Escalate to user via `{nextStepFile}`

---

## CRITICAL STEP COMPLETION NOTE

ONLY when Layer 3 research is complete and results evaluated, will you then either return to calling workflow (if answer found) or read fully and follow: `{nextStepFile}` for user escalation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Analyst was activated only after Layers 1-2 were exhausted
- Research instruction included all prior layer findings
- Analyst output was independently verified before acceptance
- All findings include specific file paths and line numbers
- Answer resolves the original research question

### ❌ SYSTEM FAILURE:

- Activating Analyst before exhausting Layers 1-2
- Accepting Analyst output without verification
- Accepting output with unsupported assumptions
- Not returning to Analyst when verification checks fail

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
