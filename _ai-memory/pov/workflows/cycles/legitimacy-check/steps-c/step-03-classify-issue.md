---
name: 'step-03-classify-issue'
description: 'Apply classification criteria to determine LEGITIMATE, NON-ISSUE, or UNCERTAIN'
nextStepFile: './step-04-record-classification.md'
classificationCriteria: '../../../../knowledge/issue-classification-criteria.md'
---

# Step 3: Apply Classification Criteria

**Progress: Step 3 of 5** — Next: Record Classification

## STEP GOAL:

Apply the formal classification criteria to determine whether the issue is LEGITIMATE (must fix), NON-ISSUE (document, do not fix), or UNCERTAIN (trigger research). The classification must be grounded in criteria and project file citations.

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

- 🎯 Focus only on applying formal classification criteria — A, B, or C
- 🚫 FORBIDDEN to classify based on opinion or without project file citations from step-02
- 💬 Approach: Systematic criteria check in order — Category A first, then B, then C
- 📋 Each issue receives its own independent classification pass

## EXECUTION PROTOCOLS:

- 🎯 Apply classification criteria in order: Category A, then B, then C
- 💾 Record the classification basis including specific criteria and project file citations
- 📖 Load next step only after a clear classification is determined
- 🚫 FORBIDDEN to guess when uncertain — trigger WF-RESEARCH-PROTOCOL instead

## CONTEXT BOUNDARIES:

- Available context: The fully understood issue (step-01), project file findings (step-02), classification criteria from `knowledge/issue-classification-criteria.md`
- Focus: Applying classification criteria only — do not build the record or assign priority yet
- Limits: Do not combine multiple issues into one classification. Each issue gets its own pass.
- Dependencies: Fully understood issue (step-01), project file findings with citations (step-02)

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Check Category A -- LEGITIMATE ISSUE (Must Fix)

An issue is legitimate if it meets ANY ONE of the following criteria (see `knowledge/issue-classification-criteria.md` for full definitions):
- A1: BUG -- Causes incorrect behavior
- A2: SECURITY -- Any vulnerability, any severity
- A3: ARCHITECTURE VIOLATION -- Contradicts architecture.md
- A4: STANDARDS VIOLATION -- Contradicts project-context.md
- A5: REQUIREMENTS VIOLATION -- Contradicts PRD or story criteria
- A6: FUTURE BREAKAGE -- Will cause problems later
- A7: TECH DEBT -- Blocks or complicates future work
- A8: PRE-EXISTING LEGITIMATE ISSUE -- Meets any A1-A7 criterion regardless of age

If the issue meets any A criterion: classify as LEGITIMATE. Proceed to step-04.

---

### 2. Check Category B -- NON-ISSUE (Document, Do Not Fix)

An issue is a non-issue ONLY if it meets ALL FOUR of the following criteria:
- B1: Does NOT meet any Category A criterion
- B2: Is a stylistic preference NOT covered by project standards
- B3: Has no measurable impact
- B4: Is not scope creep

The issue must meet ALL four B criteria to be a non-issue. If even one criterion fails, the issue is likely legitimate or uncertain.

If all four B criteria are met: classify as NON-ISSUE. Proceed to step-04.

---

### 3. Check Category C -- UNCERTAIN (Trigger Research)

An issue is uncertain when:
- C1: Project files do not clearly address whether this is correct behavior
- C2: The issue could be legitimate under some interpretations but not others
- C3: The fix is unclear -- multiple approaches exist with different trade-offs
- C4: The issue involves third-party behavior, external APIs, or environmental factors
- C5: The issue is in an undocumented area where project intent is unclear

If uncertain: classify as UNCERTAIN. Do not guess. Trigger WF-RESEARCH-PROTOCOL immediately.

---

### 4. Handle Special Cases

**Agent Disagrees With Classification:**
1. Listen to the agent's reasoning
2. Check if new information changes the assessment
3. If agent provides a valid project file citation that contradicts the classification: revise
4. If agent provides only opinion without project file basis: maintain classification
5. If genuinely uncertain after agent input: trigger WF-RESEARCH-PROTOCOL
6. Never change a classification based on agent preference alone

**Issue Outside Current Scope:**
1. Classify and record it (legitimacy does not depend on scope)
2. Assess: does it affect the current task directly or indirectly?
   - Affects current task: fix in current cycle
   - Completely separate: log separately, notify user, add to backlog
3. Never ignore it because it is "someone else's problem"

**Performance Issues:**
- LEGITIMATE if: measurably affects UX, violates stated performance requirement, or will compound at scale
- NON-ISSUE if: theoretical optimization with no measurable impact, micro-optimization without benchmarks, premature optimization

**Third-Party / External Issues:**
- Classify based on impact to the project, not on the external cause
- If it causes incorrect behavior in the project: legitimate
- If no resolution possible without external change: document, notify user, escalate

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN a clear classification (LEGITIMATE, NON-ISSUE, or UNCERTAIN) has been determined with supporting basis, will you then read fully and follow: `{nextStepFile}` to begin recording the classification.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Classification is one of exactly three values: LEGITIMATE, NON-ISSUE, UNCERTAIN
- Classification is grounded in specific criteria (A1-A8, B1-B4, or C1-C5)
- Classification is supported by project file citations from step-02
- Special cases are handled per documented rules

### ❌ SYSTEM FAILURE:

- Classifying without criteria basis
- Treating opinion as legitimate issue
- Treating legitimate issue as non-issue due to age
- Guessing when uncertain instead of triggering WF-RESEARCH-PROTOCOL
- Changing classification based on agent preference without project file basis

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
