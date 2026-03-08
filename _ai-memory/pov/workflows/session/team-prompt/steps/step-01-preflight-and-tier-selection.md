---
name: 'step-01-preflight-and-tier-selection'
description: 'Read project context, analyze work, and select 2-tier or 3-tier team structure'
nextStepFile: './step-02-design-team-composition.md'
---

# Step 1: Pre-Flight and Tier Selection

## STEP GOAL
Read mandatory project context files, analyze the work description, and determine whether a team is justified — and if so, whether 2-tier (flat) or 3-tier (hierarchical) is appropriate.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: User's work description ($ARGUMENTS), project files for verification
- Limits: Analysis only — do not begin designing the team until tier is confirmed by user

## MANDATORY SEQUENCE

### 1. Read Project Context (Pre-Flight)

Read ALL of these that exist before analyzing the work:
- `CLAUDE.md` or project README — rules and context all agents inherit
- Architecture docs (`_bmad-output/planning-artifacts/architecture.md`, `docs/project-context.md`)
- PRD (`_bmad-output/planning-artifacts/prd.md`)
- Tech stack files (`package.json`, `requirements.txt`, `pyproject.toml`) — versions, frameworks
- `.claude/settings.json` — permissions and hooks all agents inherit
- `{oversight_path}/PROJECT_STANDARDS.yaml` — coding standards
- Current story/task file — if the work is tracked
- BMAD workflow catalog (`_bmad/_config/bmad-help.csv`) — available agents, workflows, phase routing. Query `/bmad-help` for guidance on which BMAD agents and workflows are relevant to the work

Check off each file read. Note key constraints, patterns, and standards discovered.

### 2. Understand the Work

From the user's input, extract:
- **What** work needs to be done (objectives)
- **What** the deliverables are (outputs)
- **Which** files or areas of the codebase are involved (scope)

If the description is insufficient, ask the user for clarification. Do not proceed with vague descriptions.

### 3. Run Quick Decision Flow

Evaluate in order using the full decision matrix:

| Criteria | Subagent | 2-Tier | 3-Tier |
|----------|----------|--------|--------|
| Single task, self-contained | Yes | — | — |
| Only the result matters, no coordination needed | Yes | — | — |
| All work touches the same files | Yes | — | — |
| Tasks are sequential (each depends on prior) | Yes | — | — |
| 2-6 parallel tasks, independent file sets | — | Yes | — |
| Teammates need to communicate or debate | — | Yes | — |
| Work scope exceeds a single session | — | Yes | — |
| Single review cycle at end suffices | — | Yes | — |
| 3+ independent domains, each with multiple tasks | — | — | Yes |
| Domain-level quality gates needed (not just end) | — | — | Yes |
| Total tasks exceed 10-12 (single lead cannot manage) | — | — | Yes |
| Multiple review-fix-review cycles needed per domain | — | — | Yes |

**If subagent suffices**: STOP. Recommend using a single subagent, not a team. Explain why.

### 4. Run Parallelizability Check

Verify ALL items:
- [ ] Work can split into 2+ groups that touch **different** file sets
- [ ] Tasks within each group do NOT depend on another group's output (or dependencies are mapped)
- [ ] No single file needs modification by workers in different groups
- [ ] The total scope justifies multi-agent coordination overhead
- [ ] Each group contains 2+ tasks (for 3-tier: required per domain)

**IF ANY CHECK FAILS**: Present the issue to the user with restructuring options. Do not force a team structure.

### 5. Run Manager Decomposition Check (3-Tier Only)

If 3-tier is selected, additionally verify:
- [ ] Each proposed manager domain has at least 2 worker sessions
- [ ] Each manager domain has clear boundaries (files, modules, or subsystems)
- [ ] Total number of managers is 2-6
- [ ] Each manager can operate independently until reporting back to lead

**IF ANY CHECK FAILS**: Recommend 2-tier or restructure domains. Present options to user.

### 6. Confirm Tier Selection

Present recommendation:
```
## Team Structure Recommendation

**Tier**: [2-Tier / 3-Tier]
**Reasoning**: [Why this tier is appropriate]
**Domains**: [List of identified domains or work groups]
**Estimated workers**: [Count]

Proceed with this structure?
```

Wait for user confirmation before proceeding.

## CRITICAL STEP COMPLETION NOTE
ONLY when the tier selection is confirmed by the user, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All available project context files are read before analysis
- Work is analyzed before selecting a tier
- Parallelizability is verified with all 5 checks
- Simple work is NOT forced into a team structure
- User confirms the tier selection

### FAILURE:
- Skipping the pre-flight file reading
- Not reading project context before analyzing the work
- Forcing 3-tier when 2-tier suffices
- Not verifying file ownership boundaries
- Proceeding without user confirmation of tier
