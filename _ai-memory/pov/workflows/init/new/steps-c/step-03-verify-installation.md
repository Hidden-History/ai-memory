---
name: 'step-03-verify-installation'
description: 'Verify _ai-memory/ installation completeness using constraint IN-04 checklist'
nextStepFile: './step-04-create-baseline-files.md'
---

# Step 3: Verify _ai-memory/ Installation Completeness

**Progress: Step 3 of 7** — Next: Create Baseline Files

## STEP GOAL:

Verify that the _ai-memory/ directory structure is fully installed and all required components are present. This step validates the installation against constraint IN-04 requirements. No files are created here -- only verification.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus only on verifying installation completeness — no file creation
- 🚫 FORBIDDEN to create or modify any _ai-memory/ framework files
- 💬 Approach: Systematic verification against IN-04 checklist with specific pass/fail reporting
- 📋 Every check must be individually verified — no vague "looks fine" assessments

## EXECUTION PROTOCOLS:

- 🎯 Verify every installation item against the IN-04 constraint checklist
- 💾 Record verification results with specific pass/fail per item
- 📖 Load next step only after all checks pass and user confirms
- 🚫 FORBIDDEN to proceed with missing framework files

## CONTEXT BOUNDARIES:

- Available context: The _ai-memory/ directory in {project-root}, constraint IN-04 installation checklist, confirmed project track from Step 2
- Focus: Installation verification only — do not create any files
- Limits: Do not create or modify any _ai-memory/ framework files. Only verify their presence. Project-specific files are created in the next step.
- Dependencies: Step 2 must be complete with confirmed project foundation

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Load Constraint IN-04

Read {constraints_path}/init/IN-04-validate-installation.md for the complete installation verification checklist.

---

### 2. Verify Directory Structure

Confirm the following directories exist under {project-root}/_ai-memory/:
- _config/ (framework configuration)
- _memory/ (memory storage)
- agents/ (agent definitions)
- core/ (core framework files)
- pov/ (point-of-view agent directory)
- pov/workflows/ (workflow definitions)
- pov/workflows/cycles/ (cycle workflows)
- pov/workflows/init/ (initialization workflows)
- pov/workflows/phases/ (phase workflows)
- pov/constraints/ (constraint files)
- skills/ (skill definitions)

---

### 3. Verify Core Configuration Files

Confirm these files exist and are readable:
- _ai-memory/core/config.yaml (core configuration)
- _ai-memory/pov/config.yaml (POV agent configuration)
- _ai-memory/pov/workflows/WORKFLOW-MAP.md (workflow routing map)

---

### 4. Verify Workflow Files Present

Confirm key workflow files exist:
- Cycle workflows (agent-dispatch, review-cycle, approval-gate)
- Init workflows (new, existing)
- Phase workflows (discovery through maintenance)

---

### 5. Verify Constraint Files Present

Confirm constraint files exist:
- Global constraints
- Phase-specific constraints (init, discovery, architecture, planning, execution, integration, release, maintenance)

---

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

---

### 7. Record Track Configuration

Based on the confirmed project track (from Step 2), verify the configuration supports:
- Quick Flow: simplified workflow paths available
- Standard Method: full workflow paths available
- Enterprise: full workflow paths + additional compliance/security layers available

---

### 8. Present MENU OPTIONS

Display: "**Installation verification complete. All checks passed. Ready to create baseline files.**"

**Select an Option:** [C] Continue to Baseline File Creation

#### Menu Handling Logic:

- IF C: Read fully and follow: `{nextStepFile}` to begin creating baseline files
- IF verification failed: Do not offer Continue — guide user to resolve missing items, then re-verify
- IF user asks questions: Answer and redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C' (Continue)

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [C continue option] is selected and [all installation verification checks pass], will you then read fully and follow: `{nextStepFile}` to begin creating baseline project files.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Every installation check was individually verified
- Missing items were specifically identified (not vague)
- Verification completed before any project files are created
- Track-appropriate configuration is confirmed
- Menu presented and user input handled correctly

### ❌ SYSTEM FAILURE:

- Skipping installation verification
- Proceeding with missing framework files
- Creating project files before installation is verified
- Reporting vague "looks fine" instead of specific checks
- Proceeding without user selecting 'C' (Continue)

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
