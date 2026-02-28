# Output Format

Template for best practices research reports.

---

## Research Report Template

```markdown
# Research Report: [Topic]

**Date**: [YYYY-MM-DD]
**Search Query**: "[original query]"
**Confidence**: [Verified/Informed/Inferred/Uncertain]

---

## Summary

[2-3 sentence summary of key findings]

---

## Local Knowledge Found

### [Practice Title]
- **Source**: [URL or DEC-XXX]
- **Date**: [YYYY-MM-DD]
- **Status**: [Current/Needs Refresh/Outdated]

---

## Web Research Findings

### Recommended Approach

[Description]

**Why This Approach**:
- [Reason 1]
- [Reason 2]

**When NOT to Use**:
- [Exception]

### Alternative Approaches

**[Alternative Name]**:
- **When to use**: [Conditions]
- **Tradeoffs**: [Pros/cons]

---

## Sources

| Source | Type | Date | Relevance |
|--------|------|------|-----------|
| [Official docs](URL) | Documentation | 2026-01 | High |
| [Blog post](URL) | Article | 2025-12 | Medium |

---

## Stored in Database

| Practice | Status | Memory ID |
|----------|--------|-----------|
| [Practice 1] | Stored | [uuid] |
| [Practice 2] | Duplicate | [existing uuid] |

**Storage Summary**:
- Successful: [count] new practices stored
- Duplicates: [count] skipped
- Failed: [count] errors

---

## Confidence Assessment

**Confidence Level**: [Verified/Informed/Inferred/Uncertain]
**Basis**: [Why this confidence level]
```

---

## Confidence Level Definitions

| Level | Meaning |
|-------|---------|
| **Verified** | Directly confirmed from authoritative source |
| **Informed** | Based on reliable information with minor gaps |
| **Inferred** | Logical deduction from patterns |
| **Uncertain** | Limited information, needs more research |
