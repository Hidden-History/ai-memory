---
name: 'step-01-read-existing-files'
description: 'Read all existing project files personally before activating any agent'
nextStepFile: './step-02-run-analyst-audit.md'
---

# Step 1: Read Everything Available

## STEP GOAL
Before activating any agent, Parzival reads all existing project files personally. Build a comprehensive understanding of what exists, what is missing, what appears current, and what appears outdated.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All files in the project workspace
- Limits: Do not activate any agents. Do not modify any files. Only read and record findings.

## MANDATORY SEQUENCE

### 1. Read Project Files in Order
Read and assess each of the following (note what exists and what is missing):

- project-status.md -- Current phase, active task, open issues
- PRD.md -- Requirements, features, acceptance criteria
- architecture.md -- Tech decisions, patterns, stack
- project-context.md -- Coding standards, conventions, rules
- sprint-status.yaml -- Sprint state, story assignments
- epics/ and stories/ -- Current epic and story files
- decisions.md -- Prior decisions and reasoning
- goals.md -- Project goals and constraints
- docs/ -- Any other project documentation
- README.md -- High-level project overview
- Package files -- package.json, requirements.txt, etc. (stack evidence)
- CI/CD config -- workflow files, Dockerfile, etc.
- Test files -- What testing exists

### 2. Record Findings for Each File Found
For each file that exists, record:
- What it contains (summary)
- When it was last updated (if datestamped)
- Whether it appears current, outdated, or contradictory
- Gaps -- what it should contain but does not

### 3. Record Missing Files
For files not found, note:
- File is missing
- Criticality: required for current phase / nice to have / can be generated

### 4. Identify Contradictions
Note any contradictions between documents:
- Documentation vs. what package files suggest about the stack
- PRD requirements vs. what appears to actually be built
- Architecture decisions vs. actual code patterns

### 5. Apply Reading Rules
- NEVER assume a file is accurate because it exists
- NEVER assume documentation reflects current code
- NEVER assume sprint-status.yaml is current
- ALWAYS treat documentation as "possibly outdated until verified"
- ALWAYS note contradictions between documents

## CRITICAL STEP COMPLETION NOTE
ONLY when all available files have been read and findings recorded, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every available project file was read (not skimmed)
- Findings are specific for each file (not vague summaries)
- Missing files are identified with criticality assessment
- Contradictions between documents are explicitly noted
- No agents were activated during this step

### FAILURE:
- Skimming files instead of reading in full
- Activating an agent before reading is complete
- Assuming documentation is accurate without noting it needs verification
- Missing obvious contradictions between files
