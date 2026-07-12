## TECH-DEBT-{number}: {title}

| Field | Value |
|-------|-------|
| **ID** | TECH-DEBT-{number} |
| **Severity** | {severity: Critical / High / Medium / Low} |
| **Status** | {status: New / In Progress / Resolved / Closed / Won't Fix / Reopened} |
| **Surfaced** | {when/how it was found} |
| **Found By** | {agent_or_reviewer} |
| **Date Found** | {date} |
| **Related Issues** | {linked_bugs_td_decisions} |

### Summary
{one paragraph — what is sub-optimal}

### Evidence
{file paths, code references — concrete proof the debt exists}

### Impact
{what the debt costs — risk, maintenance burden, performance, correctness — and how it degrades}

### Suggested Fix
{remediation, or options if a decision is needed first}

### Disposition
{severity rationale, scheduling — addressed now / deferred / batched, and any prerequisite}

---

### Tech-Debt ID Convention
Assign sequential IDs: TECH-DEBT-001, TECH-DEBT-002, etc. Check `{oversight_path}/tech-debt/` for the highest existing ID before assigning.

**Filename**: save the record as `TECH-DEBT-NNN.md` or, optionally, `TECH-DEBT-NNN-<short-slug>.md` (a few kebab-case words). The slug is optional — both forms are valid. The `**Status**` header inside the file is authoritative for tracking, never the filename.

### Status Workflow
```
New → In Progress → Resolved → Closed
                       ↓
                   Reopened (if the debt resurfaces) → In Progress

Won't Fix (accepted — permanent, or not worth fixing)
```
Closed-class statuses: Resolved, Closed, Won't Fix. Open-class: New, In Progress, Reopened.

### Severity Guide
- **Critical**: Actively causing failures or blocking work; must fix
- **High**: Significant risk or recurring cost; fix soon
- **Medium**: Real cost, manageable; schedule it
- **Low**: Minor; fix opportunistically
