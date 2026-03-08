---
name: 'classification-criteria'
description: 'Complete classification criteria reference for issue triage (Categories A, B, C)'
---

# Classification Criteria Reference

## Category A -- LEGITIMATE ISSUE (Must Fix)

An issue is legitimate if it meets **any one** of the following criteria:

### A1. BUG -- Causes incorrect behavior
The code does not do what it is supposed to do. Observable failure, wrong output, broken functionality.

### A2. SECURITY -- Any vulnerability, any severity
Authentication bypass, injection risk, exposed secrets, improper authorization, insecure data handling. Severity does not matter -- all security issues are legitimate.

### A3. ARCHITECTURE VIOLATION -- Contradicts architecture.md
Uses a pattern explicitly ruled out by the architecture. Bypasses a structural decision documented in architecture.md. Creates coupling that the architecture prohibits.

### A4. STANDARDS VIOLATION -- Contradicts project-context.md
Violates a documented coding standard. Breaks a naming convention. Contradicts an implementation rule.

### A5. REQUIREMENTS VIOLATION -- Contradicts PRD or story criteria
Does not satisfy a stated requirement. Fails an acceptance criterion. Implements behavior that contradicts the PRD.

### A6. FUTURE BREAKAGE -- Will cause problems later
Creates a dependency that will break on foreseeable change. Hardcodes something that must be configurable. Leaves an unhandled edge case that will surface in production.

### A7. TECH DEBT -- Blocks or complicates future work
Makes future implementation significantly harder. Creates complexity that will need to be undone. Deviates from established patterns in a way that will compound.

### A8. PRE-EXISTING LEGITIMATE ISSUE
Was present before this task. Meets any of the criteria above (A1-A7). Age does not exempt it from being legitimate.

**Rule: If the issue meets any A criterion, it is LEGITIMATE. It goes on the fix list.**

---

## Category B -- NON-ISSUE (Document, Do Not Fix)

An issue is a non-issue if it meets **all four** of the following criteria:

### B1. Does NOT meet any Category A criterion
Cannot be classified as bug, security risk, architecture violation, standards violation, requirements violation, future breakage, or tech debt.

### B2. Is a stylistic preference NOT covered by project standards
A preference for a different but equally valid approach. Not prohibited by project-context.md. Not required by any project document.

### B3. Has no measurable impact
Does not affect functionality, performance, security, or maintainability in any demonstrable way.

### B4. Is not scope creep
Is not a new feature disguised as a bug fix. Is not an enhancement pretending to be a requirement.

**Rule: The issue must meet ALL four B criteria to be a non-issue. If even one criterion fails, the issue is likely legitimate or uncertain.**

### Common Non-Issue Examples
- "I would have used a different variable name" (not in standards)
- "This could theoretically be written more elegantly"
- "I prefer a different library for this" (no architectural basis)
- "This function is longer than I'd typically write" (no standard violated)

### Non-Issue Does NOT Mean Ignored
Non-issues are documented, not dismissed. The record shows what was found, why it was classified as a non-issue, and which criterion it failed to meet for legitimacy.

---

## Category C -- UNCERTAIN (Trigger Research)

An issue is uncertain when:

### C1. Project files do not clearly address whether this is correct behavior

### C2. The issue could be legitimate under some interpretations but not others

### C3. The fix is unclear -- multiple approaches exist with different trade-offs

### C4. The issue involves third-party behavior, external APIs, or environmental factors

### C5. The issue is in an undocumented area where project intent is unclear

**Rule: If uncertain, do not guess the classification. Trigger WF-RESEARCH-PROTOCOL immediately.**
