---
name: 'step-02-run-analyst-audit'
description: 'Activate Analyst agent to audit the actual codebase state and verify documentation accuracy'
nextStepFile: './step-03-identify-branch.md'
---

# Step 2: Run Analyst Audit

**Progress: Step 2 of 6** — Next: Identify Branch and Route

## STEP GOAL:

After reading all available files, activate the Analyst agent via {workflows_path}/cycles/agent-dispatch/workflow.md to audit the actual codebase state. The audit verifies documentation against reality and produces a comprehensive picture of the current project state.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: All findings from Step 1, the existing project codebase
- Focus: Dispatching Analyst audit and reviewing output — not conducting the audit yourself
- Limits: The Analyst audits only — no modifications. Parzival reviews the audit output for completeness before proceeding.
- Dependencies: Step 1 reading findings must be complete before Analyst dispatch

- Focus on dispatching and reviewing the Analyst audit — not doing the audit yourself
**Behavioral Constraints:**
- FORBIDDEN to skip the agent-dispatch workflow or bypass Parzival review of output
- Approach: Prepare precise instructions, dispatch via agent-dispatch, review output adversarially
- All six audit areas must be covered with specific findings before proceeding

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare Analyst Audit Instruction

Build the audit instruction covering six areas:

1. **Technology stack** -- What is actually installed and in use? Verify against package files, lock files, actual imports (not just package.json).
2. **Project structure** -- How is the codebase organized? Directory structure (top 3 levels), key files, entry points, configuration files.
3. **Implementation state** -- What is actually built? Features/modules that appear complete, partially implemented, scaffolded but empty, or referenced but missing.
4. **Quality state** -- What is the current condition? Test coverage, obvious bugs, dead code, security concerns visible at a glance.
5. **Documentation accuracy** -- Does documentation match code? Does PRD reflect what is built? Does architecture.md reflect actual implementation? Undocumented features or patterns?
6. **Dependencies** -- What external dependencies exist? Third-party services, external APIs, infrastructure dependencies.

---

### 2. Dispatch Analyst via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Analyst agent with the prepared audit instruction.

Provide findings from Step 1 as context for the Analyst to cross-reference.

---

### 3. Review Analyst Audit Output

Parzival reviews the audit for:
- Are all six areas covered?
- Are findings specific (not vague)?
- Are discrepancies between documentation and code identified?
- Is the health assessment plausible given the findings?
- Are there obvious areas the Analyst missed?

**IF incomplete:** Return to Analyst with specific gaps to fill.
**IF complete:** Proceed to branch identification.

---

### 4. Compile Combined Assessment

Merge Parzival's own reading findings (Step 1) with Analyst audit results into a unified assessment:
- Areas where documentation matches reality
- Areas where documentation is outdated or wrong
- Areas with no documentation at all
- Overall project health: Green / Yellow / Red

## CRITICAL STEP COMPLETION NOTE

ONLY when the Analyst audit is complete and reviewed by Parzival, load and read fully {nextStepFile}
