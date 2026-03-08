---
name: 'step-04-establish-baseline'
description: 'Establish or update all baseline files to be current and accurate after branch-specific work'
nextStepFile: './step-05-verify-understanding.md'
---

# Step 4: Establish or Update Baseline Files

## STEP GOAL
Regardless of which branch ran, all baseline files must be current and accurate before exiting. Verify each file against the findings from the audit and branch work. Create any missing files.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All findings from Steps 1-3, branch-specific work output, confirmed exit route
- Limits: Every update must trace to verified findings. Do not insert assumed content.

## MANDATORY SEQUENCE

### 1. Audit project-status.md
Verify or create with accurate values:
- current_phase reflects the actual confirmed phase
- active_task reflects actual in-progress work (or null)
- baseline_complete is accurate
- key_files paths are all accurate and existing
- open_issues count reflects known legitimate issues
- last_session_summary captures what was found in this audit

### 2. Audit goals.md
Verify or create:
- Exists and reflects confirmed project goals
- Constraints are accurate and current
- Open questions are listed if any remain

### 3. Audit project-context.md
Verify or create:
- Exists (at minimum as a stub)
- If populated, reflects actual codebase patterns (verified by Analyst)
- Not treated as confirmed until verified against code

### 4. Audit decisions.md
Verify or create:
- Exists
- Contains any decisions surfaced during this onboarding
- Knowledge gap answers (from Branch D) are recorded

### 5. Create Missing Files
If any required files are missing, create them using the appropriate templates. Reference the baseline file formats from the init-new workflow.

### 6. Cross-Check Consistency
Verify all baseline files are consistent with each other:
- No contradictions between files
- All files reflect the same confirmed project state
- Open items are consistently noted across files

## CRITICAL STEP COMPLETION NOTE
ONLY when all baseline files are verified as current and accurate, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every baseline file was individually verified or created
- All content traces to verified findings (not assumptions)
- Cross-file consistency is confirmed
- Missing files were created from appropriate templates
- Open items are consistently reflected

### FAILURE:
- Leaving baseline files outdated or inconsistent
- Creating files with assumed content
- Not cross-checking consistency between files
- Skipping file creation for missing required files
