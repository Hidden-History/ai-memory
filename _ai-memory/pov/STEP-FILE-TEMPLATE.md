# Parzival POV — Canonical Step File Template

> **Authority**: This template defines the required structure for ALL step files in the POV module.
> **Based on**: BMAD BMM canonical step file pattern (create-prd, create-product-brief workflows).
> **Adapted for**: Parzival's Technical PM & Quality Gatekeeper role.
> **Date**: 2026-03-18

---

## Template: Create Mode Step (steps-c/)

```markdown
---
name: 'step-NN-descriptive-name'
description: 'One-line purpose of this step'

# File References (only variables used in THIS step)
nextStepFile: './step-NN+1-name.md'
outputFile: '{oversight_path}/tracking/[relevant-file]'      # Optional: if step produces output
# templateRef: '../templates/[template-name].template.md'    # Optional: if step uses a template
# knowledgeRef: '../../knowledge/[fragment].md'              # Optional: if step loads knowledge
---

# Step N: Human-Readable Title

**Progress: Step N of X** — Next: [Next Step Title]

## STEP GOAL:

[1-2 sentences describing what this step accomplishes. Specific and measurable.]

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

- 🎯 [Focus area for this specific step]
- 🚫 [What is FORBIDDEN in this step]
- 💬 [Approach: e.g., Systematic analysis with clear reporting]
- 📋 [Key behavioral constraint for this step]

## EXECUTION PROTOCOLS:

- 🎯 [Primary action for this step]
- 💾 [What to record/save before proceeding]
- 📖 [When/how to load the next step]
- 🚫 [What must NOT happen before proceeding]

## CONTEXT BOUNDARIES:

- Available context: [What prior steps provide, what files are loaded]
- Focus: [This step's goal only — do not execute future steps]
- Limits: [What this step does NOT do]
- Dependencies: [Prior steps' outputs required for this step]

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. First Task

[Description of first mandatory task]

---

### 2. Second Task

[Description of second mandatory task]

---

### 3. Third Task (etc.)

[Description]

---

### N. Present MENU OPTIONS

[Present results/findings to user]

**Select an Option:** [C] Continue [other options as needed]

#### Menu Handling Logic:

- IF C: [Update tracking], then read fully and follow: `{nextStepFile}`
- IF [other]: [Handle and redisplay menu]
- IF user asks questions: Answer and redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C' (Continue)

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN [specific completion condition] is met and [user confirms], will you then read fully and follow: `{nextStepFile}` to begin [next step description].

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- [Specific, measurable success criterion 1]
- [Specific, measurable success criterion 2]
- Menu presented and user input handled correctly
- [Output saved/tracking updated as needed]

### ❌ SYSTEM FAILURE:

- [Specific failure mode 1]
- [Specific failure mode 2]
- Proceeding without user confirming via menu
- [Step-specific failure mode]

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
```

---

## Template: Validate Mode Step (steps-v/)

```markdown
---
name: 'step-v-NN-descriptive-name'
description: 'Validation check: [what is being validated]'

# File References
nextStepFile: './step-v-NN+1-name.md'    # Or null if single validate step
# outputFile: '{pov_output_folder}/validation-report.md'
---

# Validate Step N: [Validation Title]

## STEP GOAL:

[What is being validated and against what criteria]

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER modify files during validation — read-only
- 📖 CRITICAL: Read the complete step file before taking any action
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Quality Gatekeeper in validation mode
- ✅ Validation is objective and evidence-based, not subjective
- ✅ Every finding must cite the source file and line
- ✅ Classify each finding: PASS / FAIL / WARNING

### Step-Specific Rules:

- 🎯 [What to validate]
- 🚫 [What NOT to validate — scope limits]

## EXECUTION PROTOCOLS:

- 🎯 Validate against checklist criteria only
- 💾 Record findings with PASS/FAIL/WARNING classification
- 📖 Present report to user before proceeding

## CONTEXT BOUNDARIES:

- Available context: [Output files from create mode to validate]
- Focus: Validation only — no corrections
- Limits: Do not fix issues, only report them
- Dependencies: [Create mode must be complete]

## VALIDATION SEQUENCE

### 1. Load Artifacts to Validate

[What files to load and check]

---

### 2. Apply Validation Criteria

[Specific checks to run — checklist format]

- [ ] [Check 1]
- [ ] [Check 2]
- [ ] [Check 3]

---

### 3. Present Validation Report

**Validation Results:**

| Check | Result | Evidence |
|-------|--------|----------|
| [Check 1] | PASS/FAIL | [File:line or reasoning] |

**Select an Option:** [C] Continue [E] Switch to Edit Mode

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All validation checks executed
- Findings classified with evidence
- Report presented to user

### ❌ SYSTEM FAILURE:

- Skipping validation checks
- Modifying files during validation
- Reporting without evidence

**Master Rule:** Validate objectively. Report findings. Do not fix.
```

---

## Template: Edit Mode Step (steps-e/)

```markdown
---
name: 'step-e-NN-descriptive-name'
description: 'Edit mode: [what is being assessed or edited]'

# File References
nextStepFile: './step-e-NN+1-name.md'    # Or null if final edit step
---

# Edit Step N: [Edit Title]

## STEP GOAL:

[What is being assessed for editing, or what edit is being applied]

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER edit without understanding the current state first
- 📖 CRITICAL: Read the complete step file before taking any action
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — editing oversight artifacts
- ✅ Understand before editing — assess first, then propose changes
- ✅ User approves all edits before they are applied
- ✅ Cite what changed and why

### Step-Specific Rules:

- 🎯 [What to assess or edit]
- 🚫 [What NOT to change]

## EXECUTION PROTOCOLS:

- 🎯 Assess current state before proposing changes
- 💾 Show proposed changes to user before applying
- 📖 Apply only approved changes
- 🚫 FORBIDDEN to apply changes without user approval

## CONTEXT BOUNDARIES:

- Available context: [Existing output file to edit, validation report if available]
- Focus: [Specific section or aspect to edit]
- Limits: [What is out of scope for this edit]
- Dependencies: [Validation report or user request that drives this edit]

## EDIT SEQUENCE

### 1. Assess Current State

[Load the file, understand what exists]

---

### 2. Propose Changes

[Present proposed edits to user with reasoning]

---

### 3. Apply Approved Changes

[Apply only what user approved]

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Current state understood before edits proposed
- Changes shown to user before applying
- Only approved changes applied
- File properly saved after edits

### ❌ SYSTEM FAILURE:

- Editing without assessing current state
- Applying changes without user approval
- Modifying out-of-scope sections

**Master Rule:** Understand before editing. Propose before applying. User approves all changes.
```

---

## Template: Terminal Step (final step in any mode)

Terminal steps have NO `nextStepFile` and include workflow completion logic:

```markdown
---
name: 'step-NN-completion-or-approval-gate'
description: 'Final step: [completion or approval gate]'

# File References — no nextStepFile (terminal)
# outputFile: '{oversight_path}/tracking/[file]'
---

# Step N: [Completion Title]

**Final Step — [Workflow Name] Complete**

[... standard sections ...]

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- Update tracking files with completion information
- Suggest next workflows or phase transitions
- Mark workflow as complete in project-status.md

[... completion sequence ...]
```

---

## Section Reference (Quick Checklist)

Every steps-c/ file MUST have these sections in this order:

1. `---` YAML frontmatter (name, description, nextStepFile, + optional refs)
2. `# Step N: Title` + `**Progress: Step N of X**`
3. `## STEP GOAL:`
4. `## MANDATORY EXECUTION RULES (READ FIRST):` with 3 sub-sections (Universal, Role, Step-Specific)
5. `## EXECUTION PROTOCOLS:`
6. `## CONTEXT BOUNDARIES:` with 4 items (Available, Focus, Limits, Dependencies)
7. `## Sequence of Instructions (Do not deviate, skip, or optimize)` with `### N.` numbered tasks separated by `---`
8. `### N. Present MENU OPTIONS` (or CRITICAL STEP COMPLETION NOTE for auto-proceed steps)
9. `## 🚨 SYSTEM SUCCESS/FAILURE METRICS` with `### ✅ SUCCESS:` and `### ❌ SYSTEM FAILURE:` + Master Rule

---

## Naming Conventions

| Mode | Directory | File Prefix | Example |
|------|-----------|-------------|---------|
| Create | steps-c/ | `step-NN-` | `step-01-gather-project-info.md` |
| Validate | steps-v/ | `step-v-NN-` | `step-v-01-validate-baseline.md` |
| Edit | steps-e/ | `step-e-NN-` | `step-e-01-assess-baseline.md` |
| Subprocess | steps-c/ | `step-NNa-` | `step-01b-parzival-bootstrap.md` |

## Variable References

| Variable | Source | Example |
|----------|--------|---------|
| `{communication_language}` | pov/config.yaml | English |
| `{oversight_path}` | pov/config.yaml | {project-root}/oversight |
| `{workflows_path}` | pov/config.yaml | {project-root}/_ai-memory/pov/workflows |
| `{constraints_path}` | pov/config.yaml | {project-root}/_ai-memory/pov/constraints |
| `{pov_output_folder}` | pov/config.yaml | {project-root}/_ai-memory-output/pov |
| `{user_name}` | pov/config.yaml | {USER_NAME} |
| `{project-root}` | Runtime | Project root directory |
