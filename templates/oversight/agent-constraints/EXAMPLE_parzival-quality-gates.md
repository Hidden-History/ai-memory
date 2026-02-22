# Quality Gate Requirements for Code Reviews

**Agent**: parzival
**Type**: Process
**Priority**: Critical
**Status**: Active
**Created**: 2026-01-21
**Last Updated**: 2026-01-21

---

## Rule

NEVER mark code as "ready to ship" or "looks good" without running through the complete quality gate checklist. ALWAYS provide specific findings - minimum 3 issues per review, or explicitly state "Zero issues found after thorough review" with evidence.

---

## Rationale

**Background**:
Early in project, Parzival would give quick approvals like "This looks good to merge" without thorough analysis, leading to bugs slipping into production.

**Problems It Solves**:
- BUG-023: Authentication bypass missed in quick review
- BUG-041: Performance regression not caught
- BUG-067: Security vulnerability approved without analysis

**Benefits**:
- Catches issues before they reach production
- Forces systematic analysis of all code
- Creates documentation of what was checked
- Builds quality culture

---

## Scope

**Applies To**:
- All code review tasks
- Pull request reviews
- Story completion verification
- Pre-deployment checks

**Does NOT Apply To**:
- Documentation-only changes (unless docs have security implications)
- Configuration files with < 5 lines changed
- Reverts to known-good state

---

## Implementation

When reviewing code, follow these steps:

1. **Read the entire change** - don't skim
2. **Run through quality gate checklist** (see below)
3. **Document specific findings** - minimum 3, or state "Zero issues found"
4. **Provide evidence** - line numbers, examples, test results
5. **Create BUG-XXX** for any critical issues found
6. **Recommend next steps** - fix now, defer, or accept risk

---

## Quality Gate Checklist

### Functional Correctness
- [ ] Code does what it claims to do
- [ ] Edge cases handled
- [ ] Error conditions covered
- [ ] Input validation present

### Code Quality
- [ ] Follows project coding standards
- [ ] No code duplication
- [ ] Functions are focused and testable
- [ ] Variable names are clear
- [ ] Comments explain "why" not "what"

### Testing
- [ ] Unit tests present and passing
- [ ] Integration tests cover main flows
- [ ] Edge cases have tests
- [ ] Test coverage maintained or improved

### Security
- [ ] No SQL injection vulnerabilities
- [ ] No XSS vulnerabilities
- [ ] Authentication/authorization correct
- [ ] Sensitive data not logged
- [ ] Input sanitization present

### Performance
- [ ] No obvious performance issues
- [ ] Database queries optimized
- [ ] No N+1 query problems
- [ ] Resource cleanup present

### Architecture
- [ ] Follows architecture decisions
- [ ] Doesn't violate constraints
- [ ] Dependencies are appropriate
- [ ] Separation of concerns maintained

---

## Examples

### ✓ Correct Review

**Example**:
```markdown
## Code Review: Story 3.2 - Add User Logout

I've completed a thorough review. Here are my findings:

### Issues Found (3)

1. **CRITICAL - Security Issue (Line 45)**
   - Session token not invalidated server-side
   - Only client-side logout - token still valid
   - **Fix**: Add server-side session invalidation
   - Reference: OWASP Session Management Guidelines

2. **HIGH - Missing Test Coverage**
   - No test for logout with expired session
   - Edge case: what if session already expired?
   - **Fix**: Add test case `test_logout_with_expired_session()`

3. **MEDIUM - Code Quality (Lines 52-58)**
   - Duplicated error handling code
   - Same pattern used in login/signup
   - **Fix**: Extract to `handle_auth_error()` helper

### Quality Gates Checked
- ✓ Functional correctness: Works for happy path
- ✗ Security: Critical issue found (issue #1)
- ✗ Testing: Missing edge case test (issue #2)
- ⚠️ Code quality: Duplication (issue #3)
- ✓ Performance: No issues
- ✓ Architecture: Follows patterns

### Recommendation
**DO NOT MERGE** until issue #1 is fixed. Issues #2 and #3 can be addressed
in follow-up story if needed, but #1 is a security risk.

Next steps:
1. Fix server-side session invalidation
2. Add test for expired session
3. Re-review after fixes
```

**Why This Is Good**:
- Specific findings with line numbers
- Severity levels assigned
- Clear fix recommendations
- Quality gates documented
- Explicit decision: DO NOT MERGE

---

### ✗ Incorrect Review

**Example**:
```markdown
## Code Review: Story 3.2 - Add User Logout

Looks good! The logout functionality works as expected.
No issues found. Ready to merge.
```

**Why This Is Bad**:
- No specific analysis
- No quality gates checked
- No evidence provided
- Too brief - likely didn't check thoroughly
- Didn't find the critical security issue that was there

**How to Fix**:
Run through complete quality gate checklist, document findings with specifics.

---

## Verification

### Manual Check

Review output must include:
- [ ] List of specific findings with line numbers
- [ ] Severity level for each finding (Critical/High/Med/Low)
- [ ] Fix recommendations for each issue
- [ ] Quality gate checklist results
- [ ] Clear recommendation: MERGE, FIX FIRST, or NEEDS REWORK

### Automated Check

None - this is a process constraint checked by human review of Parzival's output.

---

## Exceptions

### Valid Exceptions

1. **Exception: Emergency Hotfix**
   - **When**: Production is down, hotfix must deploy immediately
   - **Approval Required**: Yes, from tech lead or user
   - **Process**:
     - Do quick safety check (< 5 min)
     - Document "EMERGENCY HOTFIX - expedited review"
     - Full review MUST happen within 24 hours post-deployment

2. **Exception: Revert to Known-Good**
   - **When**: Reverting to previously reviewed code
   - **Approval Required**: No
   - **Process**:
     - Verify revert is to known-good commit
     - State "Revert to {commit}, previously reviewed on {date}"
     - No need for full checklist

---

## Related

### Related Bugs/Issues
- BUG-023: Authentication bypass (missed in quick review)
- BUG-041: Performance regression (not caught)
- BUG-067: Security vulnerability (approved without analysis)

### Related Decisions
- DEC-008: Established quality gate process
- DEC-015: Minimum 3 findings per review requirement

### Related Constraints
- [dev-testing-requirements.md]: Testing standards dev must follow

### Related Documentation
- PROCEDURES.md: Fix Verification Protocol
- oversight/audits/: Audit findings

---

## Enforcement

### Priority Level: Critical

- Parzival MUST run through full checklist
- If < 3 issues found, must explicitly state "Zero issues found after thorough review"
- Must document which quality gates were checked
- User must sign off on any exceptions

---

## Monitoring

### Metrics

- **False Negatives**: Bugs that slipped through reviews
  - Target: < 1 per 10 reviews
  - Track in BUG-XXX logs

- **Review Depth**: Average findings per review
  - Target: 3-5 issues per review
  - Track in session logs

### Review Schedule

- **Review Frequency**: After each code review
- **Owner**: User reviews Parzival's review output
- **Action on Violation**:
  - If Parzival gives quick approval: Reject, demand full checklist
  - If pattern continues: Review this constraint and agent instructions

---

## History

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-01-21 | Initial constraint based on BUG-023, BUG-041, BUG-067 | Parzival |

---

## Notes

This constraint enforces Parzival's role as Quality Gatekeeper. The "minimum 3 issues" requirement forces thorough analysis. If code truly has zero issues, must provide evidence (which quality gates were checked, what was verified).

### Common Resistance

"But what if the code really is perfect?"
- Then document that: "Checked all X quality gates, ran Y tests, found zero issues"
- Provide evidence: test results, what was verified
- "Zero issues found" WITH evidence is acceptable
- "Looks good" WITHOUT evidence is not

### Success Criteria

This constraint is working when:
- Reviews find 3-5 actionable issues per story
- Zero critical bugs slip through reviews
- User trusts Parzival's approval because it's earned through thorough analysis
- Team catches issues in review instead of production

---

## Quick Reference

**TL;DR**: Always run full quality gate checklist. Document specific findings (minimum 3) or state "Zero issues found" with evidence.

**Key Takeaway**: Parzival is Quality Gatekeeper - thoroughness over speed.

**Common Mistakes**:
1. Quick "looks good" approval without analysis
2. Missing security or performance checks
3. Not documenting line numbers
4. Approving with known issues

**Quick Checks**:
- [ ] Ran through complete quality gate checklist?
- [ ] Found and documented specific issues (or explicitly stated zero)?
- [ ] Provided line numbers and fix recommendations?
- [ ] Made clear merge/no-merge recommendation?
