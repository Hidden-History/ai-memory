---
name: 'step-06-receive-output'
description: 'Receive and review agent output against task criteria before accepting or routing to review cycle'
nextStepFile: './step-07-accept-or-loop.md'
---

# Step 6: Receive and Review Output

**Progress: Step 6 of 9** — Next: Accept or Loop

## STEP GOAL:

When the agent signals completion, Parzival reviews the output before anything else happens. Verify against all DONE WHEN criteria, OUTPUT EXPECTED specifications, requirements, and standards. Route implementation output to WF-REVIEW-CYCLE.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The agent's output, the original instruction (DONE WHEN criteria, OUTPUT EXPECTED, requirements, scope), project files
- Focus: Output review and routing only — do not accept or present output to user until all checks pass
- Limits: Do not accept output that fails any check. Do not present incomplete output to user.
- Dependencies: Agent output signal from step-05 and original instruction from step-01

- Focus on reviewing output against all DONE WHEN criteria and routing correctly
**Behavioral Constraints:**
- FORBIDDEN to accept incomplete output or skip any checklist item
- Approach: Systematic checklist verification before any routing decision
- Implementation output ALWAYS routes to WF-REVIEW-CYCLE — no exceptions

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Run Output Review Checklist

For the agent's output, verify:
- Did the agent complete everything listed in DONE WHEN criteria?
- Does the output match the OUTPUT EXPECTED specification?
- Does the output comply with all cited requirements?
- Does the output follow the specified standards?
- Are there any issues in the output that need classification?
- Did the agent stay within scope?
- Is the output complete -- no partial implementations?

IF ANY CHECK FAILS:
- Do not accept output
- Identify specifically what is missing or incorrect
- Route to step-07 for correction loop

---

### 2. Route Based on Output Type

**For Implementation Output (code, configuration, implementation artifacts):**
- Always trigger WF-REVIEW-CYCLE
- Never accept implementation output without full review cycle

**For Planning/Documentation Output:**
- Review against project requirements manually
- Check for completeness against instruction criteria
- Check for accuracy -- no unverified claims
- Check for internal consistency -- no contradictions
- If issues found: route to step-07 for correction loop

---

### 3. Record Output Review Result

Document the review result:
- Checklist items passed/failed
- Output type and routing decision
- Any issues identified for correction

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the output has been reviewed and a routing decision is made (accept, correct, or WF-REVIEW-CYCLE), load and read fully {nextStepFile}
