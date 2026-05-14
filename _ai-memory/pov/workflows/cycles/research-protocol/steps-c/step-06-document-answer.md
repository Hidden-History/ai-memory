---
name: 'step-06-document-answer'
description: 'Document the research answer in project files and record the research log entry'
---

# Step 6: Document the Answer

**Final Step — Research Protocol Complete**

## STEP GOAL:

Every answer found through this protocol must be documented so it does not need to be researched again. Record the answer in the appropriate project file and maintain the research log.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The research question, the verified answer, the source layer, the confidence level, the user decision (if escalated)
- Focus: Documentation only — do not re-litigate research decisions
- Limits: Document factually. Do not add interpretation beyond what was determined.
- Dependencies: Verified answer, source layer, confidence level, and user decision (if escalated) from Steps 1–5

- Determine the correct documentation target based on the source layer
**Behavioral Constraints:**
- FORBIDDEN to add interpretation beyond what was determined in research
- Approach: Factual documentation with source, reasoning, and confidence level
- Confirm user decision documentation accuracy before completing this step

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
