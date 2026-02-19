# [Standard Name] Standard

## Metadata

| Field | Value |
|-------|-------|
| **Scope** | PROJECT (this project only) |
| **Project** | [PROJECT_NAME] |
| **Last Updated** | [YYYY-MM-DD] |
| **Source** | [Architecture doc, team decision, etc.] |
| **Hash** | [For drift detection - auto-generated] |

---

## Applies To

| Pattern | Examples |
|---------|----------|
| `[file pattern]` | `src/memory/*.py`, `docker/*.yml` |

---

## Rules

| ID | Rule | Severity | Rationale |
|----|------|----------|-----------|
| P1 | [Rule description] | CRITICAL | [Why this matters for this project] |
| P2 | [Rule description] | HIGH | [Why this matters for this project] |
| P3 | [Rule description] | MEDIUM | [Why this matters for this project] |
| P4 | [Rule description] | LOW | [Why this matters for this project] |

### Severity Legend

| Level | Meaning | Action |
|-------|---------|--------|
| **CRITICAL** | Breaks project constraints | Must fix before merge |
| **HIGH** | Significant deviation | Should fix before merge |
| **MEDIUM** | Minor deviation | Consider fixing |
| **LOW** | Style preference | Optional |

---

## Project Context

[Why this standard exists for this specific project - what makes it different from global standards]

---

## Examples

### Correct

```python
# Example following this project's standard
```

### Incorrect

```python
# Example violating this project's standard
```

---

## Related Standards

- Global: [Link to related global standard if applicable]
- Project: [Link to related project standard if applicable]

---

## Decision Reference

If this standard came from an architectural decision:
- **Decision ID**: [e.g., ADR-001]
- **Decision Log Entry**: [Link to decisions-log.md]

---

## Changelog

| Date | Change |
|------|--------|
| [YYYY-MM-DD] | Initial standard |
