---
name: 'step-02-layer1-project-files'
description: 'Layer 1 research: Search project files as the highest-authority source'
nextStepFile: './step-03-layer2-documentation.md'
---

# Step 2: Layer 1 -- Project Files (Always First)

**Progress: Step 2 of 6** — Next: Layer 2 – Official Documentation

## STEP GOAL:

The project's own files are the highest-authority source. If they contain the answer, no further research is needed. Search project files systematically in the defined order.

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

- 🎯 Search all five project file categories in order before evaluating results
- 🚫 FORBIDDEN to consult external sources during this step
- 💬 Approach: Systematic search with recorded findings or "no direct guidance" for each file
- 📋 Record citations for all findings before proceeding to evaluation

## EXECUTION PROTOCOLS:

- 🎯 Search all project file categories in the defined priority order
- 💾 Record findings with specific citations for each file searched
- 📖 Load next step only after all files are searched and results evaluated
- 🚫 FORBIDDEN to skip to external sources without exhausting project files

## CONTEXT BOUNDARIES:

- Available context: The precise research question from Step 1, all project files
- Focus: Project files only — do not consult external sources in this step
- Limits: Only search project files in this step. Do not consult external sources yet.
- Dependencies: Precise research question and completed template from Step 1

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Search PRD.md

Search for: requirements, acceptance criteria, behavioral specifications
Question: Does any requirement directly answer this?
Record finding or "no direct guidance"

---

### 2. Search architecture.md

Search for: technical decisions, pattern choices, constraints, rationale
Question: Was this decision already made and documented?
Record finding or "no direct guidance"

---

### 3. Search project-context.md

Search for: coding standards, implementation rules, conventions
Question: Is there a rule that governs this situation?
Record finding or "no direct guidance"

---

### 4. Search Story/Epic Files

Search for: acceptance criteria, implementation notes, edge cases
Question: Was this scenario addressed in planning?
Record finding or "no direct guidance"

---

### 5. Search Previous Session Notes/Decisions Log (if exists)

Search for: past decisions on similar questions
Question: Has this come up before and been resolved?
Record finding or "no direct guidance"

---

### 6. Evaluate Layer 1 Results

**FOUND -- clear, direct answer:**
- Record the citation
- Confirm the answer fits the current context
- Proceed with confidence level: VERIFIED
- No further research needed. Skip to step-06 (document answer) if documentation is needed, otherwise return to calling workflow.

**FOUND -- partial answer or indirect guidance:**
- Record what was found
- Determine if it is sufficient to proceed
- If sufficient: proceed with confidence level: INFORMED. Return to calling workflow.
- If not sufficient: continue to Layer 2

**NOT FOUND:**
- Document what was searched and what was missing
- Continue to Layer 2

---

## CRITICAL STEP COMPLETION NOTE

ONLY when all project files have been searched and results evaluated, will you then either return to calling workflow (if answer found) or read fully and follow: `{nextStepFile}` to begin Layer 2 documentation research.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All five file categories searched in order
- Findings recorded with specific citations
- Clear determination of FOUND / PARTIAL / NOT FOUND
- No skipping ahead to external sources

### ❌ SYSTEM FAILURE:

- Skipping project files and going to external docs
- Not searching all file categories
- Not recording citations for findings
- Accepting partial answers without evaluating sufficiency

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
