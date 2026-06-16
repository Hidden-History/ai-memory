---
class: append-only-log
read_path: qdrant-or-cold
owns: "decision records (DEC-*)"
cap_lines: 150
cap_kb: 50
rotation_trigger: on-close-over-cap
archive_target: tracking/archive/decision-log-ARCHIVE-{YYYY-MM}.md
index_file: tracking/decision-log-INDEX.md
reconciliation: "ONE manifest (DEC-id→title→shard→status) updated in the SAME close that appends/rotates; header = ONE datestamp line, never a narrative diary"
---
# Decision Log

**Last Updated**: [YYYY-MM-DD]
**Format**: Append-only — add new entries at the top, newest first

---

## How to Use

- Quick decisions go here (1-3 lines per entry)
- Architectural decisions that need full analysis go in `oversight/decisions/DEC-XXX.md` using the full ADR template
- Reference this log in the task tracker when a decision affects a task
- Use the entry format in the "## Entry Format" section below

## Entry Format

### DEC-[ID]: [Decision Topic]
- **Date**: [YYYY-MM-DD]
- **Context**: [Why this decision was needed — 1 sentence]
- **Options Considered**: [brief list]
- **Decision**: [What was chosen]
- **Rationale**: [Why — 1-2 sentences]
- **Confidence**: [Verified/Informed/Inferred]
- **Reversibility**: [Easy/Moderate/Difficult/Irreversible]
- **Status**: [Active/Superseded]

---

## Decisions

*No decisions logged yet.*
