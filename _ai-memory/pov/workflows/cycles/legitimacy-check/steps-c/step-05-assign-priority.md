---
name: 'step-05-assign-priority'
description: 'Assign priority to legitimate issues to determine fix order within the current cycle'
---

# Step 5: Priority Assignment for Legitimate Issues

**Final Step — Legitimacy Check Complete**

## STEP GOAL:

All legitimate issues go on the fix list. Priority determines the fix order within the current cycle. All priorities get fixed -- LOW priority does not mean "maybe later," it means "last in this cycle."

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The classification record from step-04, the issue details from steps 01-03
- Focus: Priority assignment only — do not modify classification or re-assess legitimacy
- Limits: Priority only determines order within the cycle. All priorities are fixed. Do not defer any legitimate issue.
- Dependencies: Complete classification record from step-04

- Focus only on priority assignment — do not modify the classification
**Behavioral Constraints:**
- FORBIDDEN to defer any legitimate issue regardless of assigned priority
- Approach: Apply criteria in order — security first, then functional impact, then standards
- Classify batch issues independently before prioritizing the full list

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Determine Priority Level

**CRITICAL -- Fix immediately before anything else**
- Security vulnerabilities (any severity)
- Bugs that break core functionality
- Issues that block the current task from completing

**HIGH -- Fix in current cycle, before task closes**
- Architecture violations
- Requirements violations
- Issues that will cause breakage

**MEDIUM -- Fix in current cycle, after CRITICAL and HIGH**
- Standards violations
- Tech debt that complicates near-term work
- Pre-existing bugs not blocking current task

**LOW -- Fix in current cycle, last**
- Tech debt with longer-term impact
- Pre-existing issues with minimal immediate risk

---

### 2. Handle Pre-Existing Issue Priority

When a legitimate issue predates the current task:
- Blocks current task: CRITICAL priority, fix first
- Does not block: assign appropriate priority based on criteria above, fix in cycle

---

### 3. Update Classification Record

Add the assigned priority to the classification record's RESOLUTION field.

---

### 4. Handle Batch Classification

When classifying multiple issues simultaneously:
1. List all issues first -- do not classify while listing
2. Classify each issue individually using the full criteria
3. Do not let one issue's classification influence another's
4. Record all classifications before sending any to fix list
5. Prioritize the fix list after all classifications are complete
6. Present the full classified list in one correction instruction

## TERMINATION STEP PROTOCOLS:

- This is the FINAL step — Legitimacy Check workflow is complete after priority is assigned
- Update the classification record's RESOLUTION field with the assigned priority before returning
- Return to the calling workflow with the complete classification record
- Batch processing: finalize all classifications and priorities before returning to calling workflow
