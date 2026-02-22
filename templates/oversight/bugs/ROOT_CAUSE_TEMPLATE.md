# Root Cause Analysis

**Bug ID**: BUG-XXX
**Date**: [YYYY-MM-DD]
**Analyst**: [Name]
**Status**: [Draft|Under Review|Complete]

---

## Executive Summary

[One-paragraph summary of the root cause and its impact]

---

## Symptom Description

### What Was Observed

[Detailed description of the symptoms - what users/systems experienced]

**Observable Behaviors**:
- [Behavior 1]
- [Behavior 2]
- [Behavior 3]

**Error Messages**:
```
[Exact error messages or log excerpts]
```

**When It Occurred**:
- **Frequency**: [Always|Intermittent|Rare]
- **First Observed**: [YYYY-MM-DD]
- **Pattern**: [Describe any pattern - time of day, specific actions, etc.]

---

## Investigation Process

### Step 1: Initial Triage
**Date**: [YYYY-MM-DD]
**Investigator**: [Name]

**Actions Taken**:
1. [Action 1 - e.g., Reviewed error logs]
2. [Action 2 - e.g., Attempted to reproduce]
3. [Action 3 - e.g., Checked recent changes]

**Findings**:
- [Finding 1]
- [Finding 2]

---

### Step 2: Hypothesis Formation
**Date**: [YYYY-MM-DD]

**Initial Hypotheses**:
1. **Hypothesis 1**: [Description]
   - **Evidence For**: [Supporting evidence]
   - **Evidence Against**: [Contradicting evidence]
   - **Result**: ✅ Confirmed / ❌ Ruled Out / ⚠️ Uncertain

2. **Hypothesis 2**: [Description]
   - **Evidence For**: [Supporting evidence]
   - **Evidence Against**: [Contradicting evidence]
   - **Result**: ✅ Confirmed / ❌ Ruled Out / ⚠️ Uncertain

---

### Step 3: Deep Dive Investigation
**Date**: [YYYY-MM-DD]

**Code Analysis**:
- **Files Examined**:
  - `[file/path/1.py]` - [What was found]
  - `[file/path/2.js]` - [What was found]

**Data Analysis**:
- **Queries Run**: [Database queries or data analysis performed]
- **Findings**: [What the data revealed]

**Timeline Analysis**:
| Time/Event | Observation | Significance |
|------------|-------------|--------------|
| [Timestamp] | [What happened] | [Why it matters] |
| [Timestamp] | [What happened] | [Why it matters] |

**Environment Analysis**:
- **Configuration**: [Relevant config settings]
- **Dependencies**: [Library versions, external services]
- **Resources**: [CPU, memory, disk, network conditions]

---

### Step 4: Reproduction
**Date**: [YYYY-MM-DD]

**Reproduction Steps**:
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Success Rate**: [X out of Y attempts]
**Environment**: [Where it was reproduced]

**Minimal Reproducible Example**:
```
[Code or commands that reliably trigger the issue]
```

---

## Root Cause Identified

### Primary Cause

[Clear, specific statement of the root cause - what actually caused the issue]

**Component**: `[file/path/component]`
**Code Location**: [Line numbers or function names]

**Problematic Code**:
```
[Relevant code snippet showing the issue]
```

**Why This Caused the Problem**:
[Detailed explanation of the causal mechanism]

---

### Contributing Factors

Beyond the primary cause, these factors contributed:

1. **Factor 1**: [Description]
   - **How it contributed**: [Explanation]
   - **Severity**: Critical / Major / Minor

2. **Factor 2**: [Description]
   - **How it contributed**: [Explanation]
   - **Severity**: Critical / Major / Minor

3. **Factor 3**: [Description]
   - **How it contributed**: [Explanation]
   - **Severity**: Critical / Major / Minor

---

## Why It Wasn't Caught Earlier

### Missing Safeguards

| Safeguard | Present? | Effectiveness | Notes |
|-----------|----------|---------------|-------|
| Input validation | ❌ | N/A | Not implemented |
| Unit tests | ⚠️ | Partial | Missed edge case |
| Integration tests | ❌ | N/A | Not covered |
| Code review | ✅ | Low | Subtle issue missed |
| Monitoring/Alerting | ⚠️ | Partial | Alert threshold too high |

### Gap Analysis

[Explanation of what gaps in process, testing, or safeguards allowed this to slip through]

---

## Impact Analysis

### Direct Impact

**Affected Users**: [Who was impacted]
**Affected Systems**: [What systems/components were affected]
**Severity**: [Critical|High|Medium|Low]

**Quantitative Impact**:
- **Duration**: [How long the issue persisted]
- **Frequency**: [How often it occurred]
- **User Impact**: [Number of users affected]
- **Data Impact**: [Any data corruption/loss]
- **Financial Impact**: [If applicable]

### Ripple Effects

[Secondary impacts or downstream effects]

---

## The "5 Whys" Analysis

Drill down to the root cause by asking "why" repeatedly:

1. **Why did [symptom] occur?**
   - Answer: [Reason 1]

2. **Why did [Reason 1] happen?**
   - Answer: [Reason 2]

3. **Why did [Reason 2] happen?**
   - Answer: [Reason 3]

4. **Why did [Reason 3] happen?**
   - Answer: [Reason 4]

5. **Why did [Reason 4] happen?**
   - Answer: [Root Cause]

---

## Lessons Learned

### What We Learned

1. [Lesson 1]
2. [Lesson 2]
3. [Lesson 3]

### Similar Issues in Codebase

**Potential Similar Problems**:
- `[location/file]` - [Similar pattern identified]
- `[another/location]` - [Similar pattern identified]

**Proactive Scan Results**: [What was found when looking for similar issues]

---

## Prevention Measures

### Immediate Fixes

What must be fixed NOW:

1. **Fix 1**: [Description]
   - **Location**: `[file/path]`
   - **Action**: [Specific fix]
   - **Priority**: Critical

2. **Fix 2**: [Description]
   - **Location**: `[file/path]`
   - **Action**: [Specific fix]
   - **Priority**: High

---

### Short-Term Prevention (1-4 weeks)

Actions to prevent recurrence:

1. **Action 1**: [Description]
   - **Type**: [Code|Test|Documentation|Process]
   - **Owner**: [Name]
   - **Due**: [YYYY-MM-DD]

2. **Action 2**: [Description]
   - **Type**: [Code|Test|Documentation|Process]
   - **Owner**: [Name]
   - **Due**: [YYYY-MM-DD]

---

### Long-Term Prevention (1-3 months)

Systemic improvements:

1. **Improvement 1**: [Description]
   - **Type**: [Architecture|Process|Tooling|Training]
   - **Rationale**: [Why this prevents recurrence]
   - **Owner**: [Name]
   - **Target**: [YYYY-MM-DD]

2. **Improvement 2**: [Description]
   - **Type**: [Architecture|Process|Tooling|Training]
   - **Rationale**: [Why this prevents recurrence]
   - **Owner**: [Name]
   - **Target**: [YYYY-MM-DD]

---

### Process Improvements

| Area | Current State | Proposed Change | Expected Benefit |
|------|---------------|-----------------|------------------|
| [Area 1] | [Current] | [Proposed] | [Benefit] |
| [Area 2] | [Current] | [Proposed] | [Benefit] |

---

### Testing Improvements

**New Tests to Add**:
- [ ] Unit test: `[test_name]` - [What it tests]
- [ ] Integration test: `[test_name]` - [What it tests]
- [ ] Regression test: `[test_name]` - [What it tests]

**Test Coverage Gaps Identified**:
- [Gap 1]
- [Gap 2]

---

### Monitoring Improvements

**New Alerts/Metrics**:
- [ ] Alert: `[alert_name]` - [When it triggers]
- [ ] Metric: `[metric_name]` - [What it tracks]
- [ ] Dashboard: `[dashboard_name]` - [What it shows]

---

## Verification

### How to Verify Fix

**Pre-Fix State**:
- [ ] Reproduce issue using original reproduction steps
- [ ] Confirm root cause is present

**Post-Fix State**:
- [ ] Apply fix
- [ ] Verify issue no longer occurs
- [ ] Test edge cases
- [ ] Run regression tests
- [ ] Deploy to staging
- [ ] Monitor for 24-48 hours
- [ ] Get sign-off from stakeholders

---

## Related Issues

### Related Bugs
- BUG-XXX: [Description]
- BUG-XXX: [Description]

### Related Decisions
- DEC-XXX: [Decision that's relevant]

### Related Technical Debt
- DEBT-XXX: [Debt item that contributed]

---

## Documentation Updates Required

- [ ] Architecture documentation
- [ ] API documentation
- [ ] User documentation
- [ ] Runbooks/playbooks
- [ ] Code comments
- [ ] README files

---

## Metadata

- **Created**: [YYYY-MM-DD]
- **Modified**: [YYYY-MM-DD]
- **Primary Analyst**: [Name]
- **Review Team**: [Names]
- **Confidence Level**: [Verified|Informed|Inferred]
- **Review Status**: [Draft|Reviewed|Approved]

---

## Appendices

### Appendix A: Detailed Logs

```
[Relevant log excerpts]
```

### Appendix B: Code Diffs

```diff
[Relevant code changes or comparisons]
```

### Appendix C: Database Queries

```sql
-- Queries used during investigation
```

### Appendix D: Test Results

[Detailed test results or screenshots]

---

## Notes

[Any additional context, observations, or information that doesn't fit in other sections]
