---
name: 'step-06-document-answer'
description: 'Document the research answer in project files and record the research log entry'
---

# Step 6: Document the Answer

## STEP GOAL
Every answer found through this protocol must be documented so it does not need to be researched again. Record the answer in the appropriate project file and maintain the research log.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The research question, the verified answer, the source layer, the confidence level, the user decision (if escalated)
- Limits: Document factually. Do not add interpretation beyond what was determined.

## MANDATORY SEQUENCE

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

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step of the research protocol. When the answer is documented and the research log entry is recorded, return to the calling workflow with the verified answer and confidence level.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Answer is documented in the appropriate project file
- Documentation includes source, reasoning, and applicability
- Confidence level is assigned correctly
- Research log entry is complete
- User decisions are confirmed as accurately documented

### FAILURE:
- Not documenting the answer after finding it
- Documenting in the wrong project file
- Missing source or reasoning in documentation
- Not recording the research log entry
- Not confirming user decision documentation accuracy
