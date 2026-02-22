# Assumption Registry

**Purpose**: Track assumptions made during development and their verification status.

**Last Updated**: [DATE]

---

## Assumption States

| State | Meaning |
|-------|---------|
| **Active** | Currently being relied upon |
| **Verified** | Confirmed to be true |
| **Invalidated** | Found to be false |
| **Superseded** | Replaced by new information |

---

## Active Assumptions

### A-001: [Assumption Title]

**Made**: [Date]
**Status**: Active
**Criticality**: [High/Medium/Low]

**Assumption**:
[Clear statement of what is being assumed]

**Why Made**:
[Why this assumption was necessary]

**Impact If Wrong**:
[What happens if this assumption is false]

**Verification Plan**:
[How and when to verify this assumption]

**Dependencies**:
- Tasks relying on this: [Task IDs]
- Other assumptions: [Assumption IDs]

---

## Assumptions by Category

### Technical Assumptions

| ID | Assumption | Status | Criticality | Verified Date |
|----|------------|--------|-------------|---------------|
| A-001 | [Brief description] | [Status] | [Level] | [Date or "-"] |

### Business Assumptions

| ID | Assumption | Status | Criticality | Verified Date |
|----|------------|--------|-------------|---------------|
| A-002 | [Brief description] | [Status] | [Level] | [Date or "-"] |

### Environmental Assumptions

| ID | Assumption | Status | Criticality | Verified Date |
|----|------------|--------|-------------|---------------|
| A-003 | [Brief description] | [Status] | [Level] | [Date or "-"] |

---

## Verified Assumptions

| ID | Assumption | Verified Date | Method | Notes |
|----|------------|---------------|--------|-------|
| A-000 | [Description] | [Date] | [How verified] | [Notes] |

---

## Invalidated Assumptions

| ID | Assumption | Invalidated Date | Impact | Resolution |
|----|------------|------------------|--------|------------|
| A-000 | [Description] | [Date] | [What was affected] | [How we adapted] |

---

## Assumption Review Schedule

- **Weekly**: Review high-criticality assumptions
- **Sprint End**: Review all active assumptions
- **Before Release**: Verify critical path assumptions

---

## Questions to Ask

Before proceeding on an assumption:
1. Is this assumption documented?
2. What's the criticality?
3. Can we verify it now?
4. What happens if it's wrong?
