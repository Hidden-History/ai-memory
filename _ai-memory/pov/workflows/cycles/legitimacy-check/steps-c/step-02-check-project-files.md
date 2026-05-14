---
name: 'step-02-check-project-files'
description: 'Check project files for requirements that directly address the issue before applying classification criteria'
nextStepFile: './step-03-classify-issue.md'
---

# Step 2: Check Project Files

**Progress: Step 2 of 5** — Next: Apply Classification Criteria

## STEP GOAL:

Before applying classification criteria, check whether project files speak directly to this issue. The classification must be grounded in project file citations, not in Parzival's opinion.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The fully understood issue from step-01, project files (PRD.md, architecture.md, project-context.md, story/epic files)
- Focus: Project file citation only — do not apply classification criteria yet
- Limits: Only check for direct relevance to the specific issue. Do not perform a general project file audit.
- Dependencies: Understanding checklist from step-01 — all items must be answered

- Focus only on checking project files — no classification yet
**Behavioral Constraints:**
- FORBIDDEN to perform a general project file audit — check only for direct relevance to the specific issue
- Approach: Systematic file-by-file check with citations recorded
- Every finding must be recorded with specific file and section reference

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Check PRD.md

- Does a requirement directly address this behavior?
- Does this issue violate an acceptance criterion?
- Record finding or "no direct guidance"

---

### 2. Check architecture.md

- Does this violate an architectural decision?
- Does this contradict a documented pattern or constraint?
- Record finding or "no direct guidance"

---

### 3. Check project-context.md

- Does this violate a coding standard or naming convention?
- Does this contradict an implementation rule?
- Record finding or "no direct guidance"

---

### 4. Check Story/Epic File (if applicable)

- Does this violate a story's acceptance criteria?
- Was this behavior explicitly specified?
- Record finding or "no direct guidance"

---

### 5. Record All Citations

If a project file speaks directly to the issue, record the specific file and section. This citation will ground the classification in the next step.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all relevant project files have been checked and findings recorded, will you then read fully and follow: `{nextStepFile}` to begin applying classification criteria.
