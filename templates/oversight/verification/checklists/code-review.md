# Code Review Checklist

**Purpose**: Comprehensive code review for quality, security, and maintainability.

---

## Review Information

- **Files/PR**: [What's being reviewed]
- **Review Date**: [Date]
- **Reviewer**: Parzival

---

## Critical (Must Fix)

### Security

| Check | Status | Notes |
|-------|--------|-------|
| [ ] No hardcoded secrets or credentials | | |
| [ ] Input validation on external data | | |
| [ ] SQL injection prevention | | |
| [ ] XSS prevention | | |
| [ ] Authentication/authorization | | |
| [ ] Sensitive data handling | | |

### Data Safety

| Check | Status | Notes |
|-------|--------|-------|
| [ ] No data loss risk | | |
| [ ] Transactions where needed | | |
| [ ] Backup/rollback considered | | |

---

## High Priority (Strongly Recommend)

### Correctness

| Check | Status | Notes |
|-------|--------|-------|
| [ ] Logic matches requirements | | |
| [ ] Edge cases handled | | |
| [ ] Error conditions handled | | |
| [ ] Null/undefined checks | | |
| [ ] Type safety maintained | | |

### Performance

| Check | Status | Notes |
|-------|--------|-------|
| [ ] No N+1 query patterns | | |
| [ ] Appropriate data structures | | |
| [ ] No unnecessary loops | | |
| [ ] Resource cleanup | | |

---

## Medium Priority (Consider)

### Maintainability

| Check | Status | Notes |
|-------|--------|-------|
| [ ] Functions do one thing | | |
| [ ] Clear naming | | |
| [ ] Appropriate abstraction | | |
| [ ] No magic numbers | | |
| [ ] Comments explain "why" | | |

### Testing

| Check | Status | Notes |
|-------|--------|-------|
| [ ] Tests exist | | |
| [ ] Tests are meaningful | | |
| [ ] Edge cases tested | | |
| [ ] Error paths tested | | |

---

## Low Priority (Optional)

### Style

| Check | Status | Notes |
|-------|--------|-------|
| [ ] Consistent formatting | | |
| [ ] Follows project conventions | | |
| [ ] No dead code | | |

---

## Summary

| Priority | Passed | Failed |
|----------|--------|--------|
| Critical | 0 | 0 |
| High | 0 | 0 |
| Medium | 0 | 0 |
| Low | 0 | 0 |

**Verdict**: [ ] APPROVED / [ ] NEEDS REVISION / [ ] BLOCKED

---

## Issues Found

### Critical Issues
1. [Issue description with file:line reference]

### High Priority Issues
1. [Issue description with file:line reference]

### Medium Priority Issues
1. [Issue description with file:line reference]

### Low Priority Issues
1. [Issue description with file:line reference]

---

## Positive Observations

- [Good patterns noted]
- [Well-written code]

---

## Recommendation

[Parzival's recommendation]

**Decision Needed**: [What user needs to decide]
