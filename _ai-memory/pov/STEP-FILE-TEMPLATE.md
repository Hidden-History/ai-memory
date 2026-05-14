# Parzival POV — Canonical Step File Template

> **Authority**: This template defines the required structure for ALL step files in the POV module.
> **Based on**: De facto standard used by all 119 production step files in `pov/workflows/`.
> **Adapted for**: Parzival's Technical PM & Quality Gatekeeper role.
> **Date**: 2026-04-12

---

## Template: Create Mode Step (steps-c/)

```markdown
---
name: 'step-NN-descriptive-name'
description: 'One-line purpose of this step'
nextStepFile: './step-NN+1-name.md'
# outputFile: '{oversight_path}/tracking/[relevant-file]'      # Optional: if step produces output
# templateRef: '../templates/[template-name].template.md'      # Optional: if step uses a template
# knowledgeRef: '../../knowledge/[fragment].md'                # Optional: if step loads knowledge
---

# Step N: Human-Readable Title

**Progress: Step N of X** — Next: [Next Step Title]

## STEP GOAL:

[1-2 sentences describing what this step accomplishes. Specific and measurable.]

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: [What prior steps provide, what files are loaded]
- Focus: [This step's goal only — do not execute future steps]
- Limits: [What this step does NOT do]
- Dependencies: [Prior steps' outputs required for this step]

- [Primary behavioral constraint for this step]
- FORBIDDEN to [what must not happen in this step]
- Approach: [How to approach this step — e.g., systematic, sequential, additive]
- [Any additional scope rule specific to this step]

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. [First Task Title]

[Description of first mandatory task]

---

### 2. [Second Task Title]

[Description of second mandatory task]

---

### N. [Final Task or Menu]

[For auto-proceed steps: describe completion condition]

## CRITICAL STEP COMPLETION NOTE

ONLY when [specific completion condition], load and read fully {nextStepFile}
```

For steps with a user menu (not auto-proceed), replace the CRITICAL STEP COMPLETION NOTE with:

```markdown
### N. Present Options

[Summary of what was accomplished in this step]

**Select an Option:**
- **[C]** Continue to next step
- **[other]** [Description of other option]

#### Handling:
- IF C: [update tracking if needed], then read fully and follow: `{nextStepFile}`
- IF [other]: [handle and redisplay menu]
- IF user asks questions: answer and redisplay menu

ALWAYS halt and wait for user input after presenting options.
```

---

## Template: Terminal Step (final step — no nextStepFile)

```markdown
---
name: 'step-NN-completion-name'
description: 'Final step: [completion or approval gate]'
# No nextStepFile — terminal step
# outputFile: '{oversight_path}/tracking/[file]'
---

# Step N: [Completion Title]

**Final Step — [Workflow Name] Complete**

## STEP GOAL:

[What this final step accomplishes — usually approval, sign-off, or completion record.]

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: [All outputs from prior steps in this workflow]
- Focus: Completion and handoff only
- Limits: Do not begin next workflow — that is user's choice
- Dependencies: All prior steps complete

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. [Completion Task]

[Final verification, sign-off request, or record update]

---

### 2. Complete Workflow

Update project-status.md with completion. Suggest next workflow or phase transition.

Workflow complete. Await user direction.
```

---

## Section Reference (Mandatory Checklist)

Every steps-c/ file MUST have these sections in this order:

1. `---` YAML frontmatter: `name`, `description`, `nextStepFile` (null if terminal), plus optional refs
2. `# Step N: Title` + `**Progress: Step N of X** — Next: [title]`
3. `## STEP GOAL:` — 1-2 sentences, specific and measurable
4. `> **Preamble**:` — reference line pointing to STEP-PREAMBLE.md
5. `**Scope:**` block — 4 standard items (Available context, Focus, Limits, Dependencies) plus behavioral constraints as additional bullets
6. `## Sequence of Instructions (Do not deviate, skip, or optimize)` — `### N.` numbered tasks separated by `---`
7. `## CRITICAL STEP COMPLETION NOTE` (auto-proceed) OR menu options block (user-input steps)

**What does NOT belong in production step files:**
- `## MANDATORY EXECUTION RULES (READ FIRST):` sections — covered by STEP-PREAMBLE.md reference
- `## EXECUTION PROTOCOLS:` sections — covered by STEP-PREAMBLE.md reference
- `## CONTEXT BOUNDARIES:` sections — replaced by `**Scope:**` block in the STEP GOAL section
- `## 🚨 SYSTEM SUCCESS/FAILURE METRICS` sections — not present in production files

---

## Naming Conventions

| Mode | Directory | File Prefix | Example |
|------|-----------|-------------|---------|
| Create | steps-c/ | `step-NN-` | `step-01-gather-project-info.md` |
| Subprocess | steps-c/ | `step-NNa-` | `step-01b-parzival-bootstrap.md` |
| Validate | steps-v/ | `step-v-NN-` | `step-v-01-validate-baseline.md` |
| Edit | steps-e/ | `step-e-NN-` | `step-e-01-assess-baseline.md` |

## Variable References

| Variable | Source | Example |
|----------|--------|---------|
| `{communication_language}` | pov/config.yaml | English |
| `{oversight_path}` | pov/config.yaml | {project-root}/oversight |
| `{workflows_path}` | pov/config.yaml | {project-root}/_ai-memory/pov/workflows |
| `{constraints_path}` | pov/config.yaml | {project-root}/_ai-memory/pov/constraints |
| `{skills_path}` | pov/config.yaml | {project-root}/_ai-memory/pov/skills |
| `{knowledge_path}` | pov/config.yaml | {project-root}/_ai-memory/pov/knowledge |
| `{sanctum_path}` | pov/config.yaml | {project-root}/_ai-memory/sanctum |
| `{scripts_path}` | pov/config.yaml | {project-root}/_ai-memory/pov/scripts |
| `{pov_output_folder}` | pov/config.yaml | {project-root}/_ai-memory-output/pov |
| `{user_name}` | pov/config.yaml | {USER_NAME} |
| `{project-root}` | Runtime | Project root directory |
