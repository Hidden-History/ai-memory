---
name: "document-maintenance"
description: "Review cycle schedule and archival policy for oversight documents"
---

# Document Maintenance Reference

## Review Cycle Schedule

| Frequency | Documents | Action |
|-----------|-----------|--------|
| **Every Session End** | SESSION_WORK_INDEX.md | Check line count, shard if > 80 lines |
| **Weekly** | task-tracker.md, blockers-log.md | Verify status accuracy, close resolved items |
| **Monthly** | Templates, risk-register.md | Check for staleness, update if process changed |
| **Quarterly** | Architecture docs, standards | Review for drift, archive old session-index months |

## Archival Policy

Archive a document when:
- Work is complete and verified
- Document is superseded by a newer version
- Content is no longer actively referenced
- Document serves only historical reference

### Archival Rules
- Move to `archive/` subdirectory within the same parent
- Retain all content (never delete archived documents)
- Include archive date: `{original-name}_archived_{YYYY-MM-DD}.md`
- Update any index files that referenced the archived document
- Add a one-line note in the parent index pointing to the archive location

## Session Index Archival

| Trigger | Action |
|---------|--------|
| SESSION_WORK_INDEX > 80 lines | Shard oldest sessions to `session-index/{YYYY-MM}/week-{N}.md` |
| Quarter ends (Mar/Jun/Sep/Dec) | Consolidate quarter's weeks into `session-index/archive/{YYYY}-Q{N}.md` |
| After quarterly archive | After confirming all data is present in the quarterly archive, delete individual week files for that quarter, update INDEX.md |

## Staleness Indicators

Flag a document for review when:
- Referenced file paths no longer exist
- Task IDs reference completed/archived sprints
- Risk entries have been "Open" for > 30 days without update
- Blocker entries have been "Active" for > 14 days without update
