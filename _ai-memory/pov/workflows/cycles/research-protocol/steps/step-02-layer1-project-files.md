---
name: 'step-02-layer1-project-files'
description: 'Layer 1 research: Search project files as the highest-authority source'
nextStepFile: './step-03-layer2-documentation.md'
---

# Step 2: Layer 1 -- Project Files (Always First)

## STEP GOAL
The project's own files are the highest-authority source. If they contain the answer, no further research is needed. Search project files systematically in the defined order.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The precise research question from step-01, all project files
- Limits: Only search project files in this step. Do not consult external sources yet.

## MANDATORY SEQUENCE

### 1. Search PRD.md
Search for: requirements, acceptance criteria, behavioral specifications
Question: Does any requirement directly answer this?
Record finding or "no direct guidance"

### 2. Search architecture.md
Search for: technical decisions, pattern choices, constraints, rationale
Question: Was this decision already made and documented?
Record finding or "no direct guidance"

### 3. Search project-context.md
Search for: coding standards, implementation rules, conventions
Question: Is there a rule that governs this situation?
Record finding or "no direct guidance"

### 4. Search Story/Epic Files
Search for: acceptance criteria, implementation notes, edge cases
Question: Was this scenario addressed in planning?
Record finding or "no direct guidance"

### 5. Search Previous Session Notes/Decisions Log (if exists)
Search for: past decisions on similar questions
Question: Has this come up before and been resolved?
Record finding or "no direct guidance"

### 6. Evaluate Layer 1 Results

**FOUND -- clear, direct answer:**
- Record the citation
- Confirm the answer fits the current context
- Proceed with confidence level: VERIFIED
- No further research needed. Skip to step-05 (document answer) if documentation is needed, otherwise return to calling workflow.

**FOUND -- partial answer or indirect guidance:**
- Record what was found
- Determine if it is sufficient to proceed
- If sufficient: proceed with confidence level: INFORMED. Return to calling workflow.
- If not sufficient: continue to Layer 2

**NOT FOUND:**
- Document what was searched and what was missing
- Continue to Layer 2

## CRITICAL STEP COMPLETION NOTE
ONLY when all project files have been searched and results evaluated, either return to calling workflow (if answer found) or load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All five file categories searched in order
- Findings recorded with specific citations
- Clear determination of FOUND / PARTIAL / NOT FOUND
- No skipping ahead to external sources

### FAILURE:
- Skipping project files and going to external docs
- Not searching all file categories
- Not recording citations for findings
- Accepting partial answers without evaluating sufficiency
