---
name: release
description: 'Release phase. Final gate before production -- documents changes, verifies deployment, ensures rollback capability.'
firstStep: './steps-c/step-01-compile-release.md'
---

# Release Phase

**Goal:** Ensure nothing is left implicit before work reaches production. Every change is documented. Every deployment step is verified. Every risk is surfaced. Release does not exit until: changelog is complete and accurate, rollback plan exists and is understood, deployment is verified, and the user explicitly signs off.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

### Step Chain Overview
1. **step-01** -- Compile what is being released
2. **step-02** -- SM creates release notes and changelog — for a comprehensive documentation pass, dispatch `bmad-agent-tech-writer` via `{project-root}/.claude/skills/bmad-agent-tech-writer/SKILL.md`
3. **step-03** -- Build deployment checklist
4. **step-04** -- Build rollback plan
5. **step-05** -- DEV deployment verification
6. **step-06** -- Parzival reviews all release artifacts
7. **step-07** -- Approval gate and route to Maintenance or Planning

### Release Anti-Patterns
These apply across ALL steps in this workflow:
- Never create changelog from memory instead of story records
- Never write deployment checklist as a generic guide
- Never skip rollback plan because of confidence
- Never mark irreversible changes as reversible
- Never skip DEV deployment verification
- Never release without explicit user sign-off
- Never omit behavior changes from changelog
- Never write release notes in technical language for stakeholders

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-RELEASE
- Drop on exit: CONSTRAINTS-RELEASE
- Exit to: WF-MAINTENANCE or WF-PLANNING

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}

<!-- ai-memory:degraded-declaration
capability: cap:phase-release
depends_on: bmad
degraded_behaviour: Runs release without the BMAD dev and tech-writer personas and reports each as unavailable.
degraded_test: not-yet-enforced
ai-memory:end-degraded-declaration -->
