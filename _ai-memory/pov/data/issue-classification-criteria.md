---
name: Issue Classification Criteria
description: Standalone reference for classifying issues as Legitimate, Non-Issue, or Uncertain. Extracted from the legitimacy check workflow.
---

# Issue Classification Criteria

Every issue surfaced during a code review, audit, or maintenance report must be classified before any action is taken. This reference defines the three categories and their criteria.

---

## Category A -- LEGITIMATE ISSUE (Must Fix)

An issue is legitimate if it meets **any one** of the following criteria:

| ID | Type | Description |
|---|---|---|
| A1 | **Bug** | Causes incorrect behavior. The code does not do what it is supposed to do. Observable failure, wrong output, broken functionality. |
| A2 | **Security** | Any vulnerability, any severity. Authentication bypass, injection risk, exposed secrets, improper authorization, insecure data handling. Severity does not matter -- all security issues are legitimate. |
| A3 | **Architecture Violation** | Contradicts architecture.md. Uses a pattern explicitly ruled out. Bypasses a structural decision. Creates coupling that the architecture prohibits. |
| A4 | **Standards Violation** | Contradicts project-context.md. Violates a documented coding standard. Breaks a naming convention. Contradicts an implementation rule. |
| A5 | **Requirements Violation** | Contradicts PRD or story acceptance criteria. Does not satisfy a stated requirement. Implements behavior that contradicts the PRD. |
| A6 | **Future Breakage** | Will cause problems later. Creates a dependency that will break on foreseeable change. Hardcodes something that must be configurable. Leaves an unhandled edge case that will surface in production. |
| A7 | **Tech Debt** | Blocks or complicates future work. Makes future implementation significantly harder. Creates complexity that will need to be undone. Deviates from established patterns in a way that will compound. |
| A8 | **Pre-Existing** | Was present before this task but meets any of the criteria above (A1-A7). Age does not exempt it from being legitimate. |

**Rule**: If the issue meets ANY single A criterion, it is LEGITIMATE. It goes on the fix list.

---

## Category B -- NON-ISSUE (Document, Do Not Fix)

An issue is a non-issue if it meets **ALL** of the following criteria:

| ID | Criterion | Description |
|---|---|---|
| B1 | Not Category A | Cannot be classified as bug, security risk, architecture violation, standards violation, requirements violation, future breakage, or tech debt. |
| B2 | Stylistic only | A preference for a different but equally valid approach. Not prohibited by project-context.md. Not required by any project document. |
| B3 | No measurable impact | Does not affect functionality, performance, security, or maintainability in any demonstrable way. |
| B4 | Not scope creep | Is not a new feature disguised as a bug fix. Is not an enhancement pretending to be a requirement. |

**Rule**: The issue must meet ALL four B criteria to be a non-issue. If even one fails, the issue is likely legitimate or uncertain.

### Common Non-Issue Examples
- "I would have used a different variable name" (not in standards)
- "This could theoretically be written more elegantly"
- "I prefer a different library for this" (no architectural basis)
- "This function is longer than I'd typically write" (no standard violated)

### Non-Issue Does NOT Mean Ignored
Non-issues are documented, not dismissed. The record shows:
- What was found
- Why it was classified as a non-issue
- Which criterion it failed to meet for legitimacy

---

## Category C -- UNCERTAIN (Trigger Research)

An issue is uncertain when:

| ID | Condition |
|---|---|
| C1 | Project files do not clearly address whether this is correct behavior |
| C2 | The issue could be legitimate under some interpretations but not others |
| C3 | The fix is unclear -- multiple approaches exist with different trade-offs |
| C4 | The issue involves third-party behavior, external APIs, or environmental factors |
| C5 | The issue is in an undocumented area where project intent is unclear |

**Rule**: If uncertain, do not guess the classification. Trigger the research protocol immediately.

---

## Priority Assignment for Legitimate Issues

All legitimate issues go on the fix list. Priority determines fix order within the current cycle.

| Priority | Criteria | Examples |
|---|---|---|
| **CRITICAL** | Fix immediately before anything else | Security vulnerabilities (any severity), bugs that break core functionality, issues that block the current task |
| **HIGH** | Fix in current cycle, before task closes | Architecture violations, requirements violations, issues that will cause breakage |
| **MEDIUM** | Fix in current cycle, after CRITICAL and HIGH | Standards violations, tech debt that complicates near-term work, pre-existing bugs not blocking current task |
| **LOW** | Fix in current cycle, last | Tech debt with longer-term impact, pre-existing issues with minimal immediate risk |

**All priorities get fixed. Priority only determines the order within the cycle. LOW priority does not mean "maybe later." It means "last in this cycle."**

---

## Special Cases

### Performance Issues
- **Legitimate if**: Measurably affects user experience, violates a stated performance requirement, or will compound significantly at scale based on architecture decisions.
- **Non-issue if**: Theoretical optimization with no measurable real-world impact, micro-optimization preference without benchmarking basis, or premature optimization not required by current requirements.

### Third-Party / External Issues
- Classify based on impact to the project, not on the external cause.
- If it causes incorrect behavior in the project, it is legitimate.
- If no resolution is possible without external change: document clearly, notify user, escalate appropriately.

### Agent Disagrees With Classification
- Listen to the agent's reasoning.
- If the agent provides a valid project file citation that contradicts the classification, revise it.
- If the agent provides only opinion without project file basis, maintain classification.
- Never change a classification based on agent preference alone.

---

## Classification Record Format

Every classified issue is recorded with:

```
ISSUE ID:       [sequential number]
LOCATION:       [file + function + line]
DESCRIPTION:    [clear description]
ORIGIN:         [new | pre-existing]
CLASSIFICATION: [LEGITIMATE | NON-ISSUE | UNCERTAIN]
BASIS:          [criterion ID + project file citation]
RESOLUTION:     [fix list priority | documented exclusion | pending research]
```

---

## Workflow Reference

Full legitimacy check workflow: `{workflows_path}/cycles/legitimacy-check/workflow.md`
Related constraints: GC-6 (distinguish issues), GC-7 (never pass known issues), GC-8 (never carry debt)
