---
class: register
read_path: section-anchored
owns: "risk records (RSK-*)"
cap_lines: 120
cap_kb: 12
rotation_trigger: on-close-over-cap
archive_target: tracking/risk-archive-{YYYY}.md
index_file: N/A
reconciliation: "live = OPEN only + '{N} active as of PM #{X}' banner; on resolve MOVE to archive"
---
# Risk Register

**Last Updated**: [DATE]

---

## Active Risks

### Critical

| ID | Risk | Impact | Likelihood | Mitigation | Owner | Status |
|----|------|--------|------------|------------|-------|--------|
| RSK-001 | [Description] | [Impact if occurs] | High/Med/Low | [Mitigation plan] | [Who] | [Status] |

### High

| ID | Risk | Impact | Likelihood | Mitigation | Owner | Status |
|----|------|--------|------------|------------|-------|--------|
| RSK-002 | [Description] | [Impact if occurs] | High/Med/Low | [Mitigation plan] | [Who] | [Status] |

### Medium

| ID | Risk | Impact | Likelihood | Mitigation | Owner | Status |
|----|------|--------|------------|------------|-------|--------|
| RSK-003 | [Description] | [Impact if occurs] | High/Med/Low | [Mitigation plan] | [Who] | [Status] |

### Low

| ID | Risk | Impact | Likelihood | Mitigation | Owner | Status |
|----|------|--------|------------|------------|-------|--------|
| RSK-004 | [Description] | [Impact if occurs] | High/Med/Low | [Mitigation plan] | [Who] | [Status] |

---

## Resolved Risks

| ID | Risk | Resolution | Date |
|----|------|------------|------|
| RSK-000 | [Description] | [How it was resolved] | [Date] |

---

## Risk Categories

- **Technical**: Code, architecture, performance
- **External**: Dependencies, APIs, third parties
- **Scope**: Requirements changes, feature creep
- **Resource**: Time, skills, availability
- **Quality**: Testing, bugs, technical debt

## Severity Matrix

|              | Low Impact | Medium Impact | High Impact |
|--------------|------------|---------------|-------------|
| High Likelihood | Medium | High | Critical |
| Medium Likelihood | Low | Medium | High |
| Low Likelihood | Low | Low | Medium |
