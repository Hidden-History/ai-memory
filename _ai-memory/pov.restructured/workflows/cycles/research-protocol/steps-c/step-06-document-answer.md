---
name: 'step-06-document-answer'
description: 'Document the research answer in project files and record the research log entry'
---

# Step 6: Document the Answer

**Final Step — Research Protocol Complete**

## STEP GOAL:

Every answer found through this protocol must be documented so it does not need to be researched again. Record the answer in the appropriate project file and maintain the research log.

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

- 🎯 Determine the correct documentation target based on the source layer
- 🚫 FORBIDDEN to add interpretation beyond what was determined in research
- 💬 Approach: Factual documentation with source, reasoning, and confidence level
- 📋 Confirm user decision documentation accuracy before completing this step

## EXECUTION PROTOCOLS:

- 🎯 Document the answer in the appropriate project file using the standard format
- 💾 Record the complete research log entry with all required fields
- 📖 Return to calling workflow with the verified answer and confidence level
- 🚫 FORBIDDEN to complete this step without confirmed documentation

## CONTEXT BOUNDARIES:

- Available context: The research question, the verified answer, the source layer, the confidence level, the user decision (if escalated)
- Focus: Documentation only — do not re-litigate research decisions
- Limits: Document factually. Do not add interpretation beyond what was determined.
- Dependencies: Verified answer, source layer, confidence level, and user decision (if escalated) from Steps 1–5

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Determine Documentation Target

**ANSWER FOUND IN PROJECT FILES (Layer 1):**
- No additional documentation needed -- it was already there
- Ensure the relevant team members know where to find it

**ANSWER FOUND IN EXTERNAL DOCUMENTATION (Layer 2):**
- If it represents a decision for this project: add to architecture.md
- If it represents a standard for this project: add to project-context.md
- Include: the answer, the source, why it applies to this project

**ANSWER FROM ANALYST CODEBASE RESEARCH (Layer 3):**
- If it reveals an existing undocumented pattern: document in architecture.md
- If it reveals a gap or inconsistency: log as legitimate issue

**ANSWER FROM USER DECISION (Escalation):**
- Always document in the appropriate project file
- architecture.md for architectural decisions
- project-context.md for standards and implementation rules
- Include: the decision, the reasoning, the date
- Confirm with user that documentation is accurate before proceeding

---

### 2. Documentation Format for New Decisions

When adding a new decision to project files:

```
## [Decision Topic]
**Decided**: [date]
**Decision**: [what was decided]
**Reasoning**: [why this approach was chosen]
**Source**: [what informed the decision -- project needs, official docs, user input]
**Applies to**: [where this decision applies in the codebase]
```

---

### 3. Assign Confidence Level

**VERIFIED:**
- Source: Direct citation from project file OR official documentation
- Usage: Can be stated as fact with citation

**INFORMED:**
- Source: Strong Tier 3-4 community standard OR codebase pattern evidence
- Usage: Can be stated as a well-grounded recommendation

**INFERRED:**
- Source: Logical conclusion from available evidence -- not directly stated
- Usage: Must be flagged as inference -- not presented as fact

---

### 4. Record Research Log Entry

```
RESEARCH LOG -- [date/task reference]
Question:    [precise question]
Layer 1:     [found / not found -- what was checked]
Layer 2:     [found / not found -- sources checked]
Layer 3:     [activated / not needed -- findings]
Resolution:  [verified answer / escalated to user]
Confidence:  [VERIFIED / INFORMED / INFERRED]
Documented:  [where the answer was added to project files]
```

---

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — research protocol workflow completion required
- Return to the calling workflow with the verified answer and confidence level
- All documentation must be complete and confirmed before returning
- Research log entry must be recorded before returning

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Answer is documented in the appropriate project file
- Documentation includes source, reasoning, and applicability
- Confidence level is assigned correctly
- Research log entry is complete
- User decisions are confirmed as accurately documented

### ❌ SYSTEM FAILURE:

- Not documenting the answer after finding it
- Documenting in the wrong project file
- Missing source or reasoning in documentation
- Not recording the research log entry
- Not confirming user decision documentation accuracy

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
