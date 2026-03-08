---
name: 'step-03-verify-installation'
description: 'Verify _ai-memory/ installation completeness using constraint IN-04 checklist'
nextStepFile: './step-04-create-baseline-files.md'
---

# Step 3: Verify _ai-memory/ Installation Completeness

## STEP GOAL
Verify that the _ai-memory/ directory structure is fully installed and all required components are present. This step validates the installation against constraint IN-04 requirements. No files are created here -- only verification.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The _ai-memory/ directory in {project-root}, constraint IN-04 installation checklist
- Limits: Do not create or modify any _ai-memory/ framework files. Only verify their presence. Project-specific files (project-status.md, goals.md, etc.) are created in the next step.

## MANDATORY SEQUENCE

### 1. Load Constraint IN-04
Read {constraints_path}/init/IN-04-installation-verification.md for the complete installation verification checklist.

### 2. Verify Directory Structure
Confirm the following directories exist under {project-root}/_ai-memory/:
- pov/ (point-of-view agent directory)
- pov/workflows/ (workflow definitions)
- pov/workflows/cycles/ (cycle workflows)
- pov/workflows/init/ (initialization workflows)
- pov/workflows/phases/ (phase workflows)
- pov/constraints/ (constraint files)
- data/ (project data files)

### 3. Verify Core Configuration Files
Confirm these files exist and are readable:
- _ai-memory/config.yaml (core configuration)
- _ai-memory/pov/pov-config.yaml (POV agent configuration)
- _ai-memory/WORKFLOW-MAP.md (workflow routing map)

### 4. Verify Workflow Files Present
Confirm key workflow files exist:
- Cycle workflows (agent-dispatch, review-cycle, approval-gate)
- Init workflows (new, existing)
- Phase workflows (discovery through maintenance)

### 5. Verify Constraint Files Present
Confirm constraint files exist:
- Global constraints
- Phase-specific constraints (init, discovery, architecture, planning, execution, integration, release, maintenance)

### 6. Report Verification Results

**IF ALL CHECKS PASS:**
- Installation is verified as complete
- Record verification result
- Proceed to next step

**IF ANY CHECK FAILS:**
- List all missing or incomplete items
- Alert user with specific items that need attention:
  "The _ai-memory/ installation is incomplete. The following items are missing:
   [specific list of missing items]
   These must be present before the project baseline can be created."
- Do not proceed until all items are present
- Re-verify from scratch after items are addressed

### 7. Record Track Configuration
Based on the confirmed project track (from Step 2), verify the configuration supports:
- Quick Flow: simplified workflow paths available
- Standard Method: full workflow paths available
- Enterprise: full workflow paths + additional compliance/security layers available

## CRITICAL STEP COMPLETION NOTE
ONLY when all installation verification checks pass, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every installation check was individually verified
- Missing items were specifically identified (not vague)
- Verification completed before any project files are created
- Track-appropriate configuration is confirmed

### FAILURE:
- Skipping installation verification
- Proceeding with missing framework files
- Creating project files before installation is verified
- Reporting vague "looks fine" instead of specific checks
