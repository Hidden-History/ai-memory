---
class: live-index
read_path: qdrant-or-cold
owns: "per-session archive roster"
cap_lines: 120
cap_kb: 10
rotation_trigger: on-close-over-cap  # auto-rotation deferred to TD-655; rotate manually until then
archive_target: session-index/archive/{YYYY-Q#}.md
index_file: N/A
reconciliation: "1 row/session, header = 1 line, quarterly shards over cap"
---
# Session Index

**Purpose**: Navigate historical sessions (keeps SESSION_WORK_INDEX.md lean)
**Updated**: [YYYY-MM-DD]

---

## How This Works

SESSION_WORK_INDEX.md shows only the last 5 sessions (summary).
Full session details are archived here by month/week.

---

## Current Year: [YYYY]

### [Month YYYY]

| Week | Dates | Sessions | Key Work |
|------|-------|----------|----------|
| Week N | Mon DD - Sun DD | X | [Brief summary] |

**Details**: See `[YYYY-MM]/week-N.md`

---

## Archive

Sessions older than 90 days are archived quarterly.

| Quarter | Sessions | Location |
|---------|----------|----------|
| [YYYY]-Q[N] | X | `archive/[YYYY]-Q[N].md` |

---

## Maintenance

- **Weekly**: Add new sessions to current week file
- **Monthly**: Create new month folder at month start
- **Quarterly**: Archive old sessions to quarterly file
