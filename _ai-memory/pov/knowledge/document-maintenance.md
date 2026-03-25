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

## Local Document Archival

> Use this for archiving local documents within a project subdirectory (e.g., sprint plans, phase docs).

Archive a document when:
- Work is complete and verified
- Document is superseded by a newer version
- Content is no longer actively referenced
- Document serves only historical reference

### Archival Rules
- Move to `archive/` subdirectory within the same parent
- Retain all content (never delete archived documents)
- Include archive date: `{original-name}-archived-{YYYY-MM-DD}.md`
- Update any index files that referenced the archived document
- Add a one-line note in the parent index pointing to the archive location

## Session Index Archival

| Trigger | Action |
|---------|--------|
| SESSION_WORK_INDEX > 80 lines | Append each archived session as a new row in `{oversight_path}/session-index/INDEX.md` |
| Quarter ends (Mar/Jun/Sep/Dec) | Consolidate quarter's weeks into `session-index/archive/{YYYY}-Q{N}.md` |
| After quarterly archive | After confirming all data is present in the quarterly archive, delete individual week files for that quarter, update INDEX.md |

## Staleness Indicators

Flag a document for review when:
- Referenced file paths no longer exist
- Task IDs reference completed/archived sprints
- Risk entries have been "Open" for > 30 days without update
- Blocker entries have been "Active" for > 14 days without update

## Document Sharding

### When to Shard

Apply document sharding when ANY of these thresholds are exceeded:

| Trigger | Threshold |
|---------|-----------|
| Line count | > 500 lines |
| Item count | > 50 items (tasks, bugs, decisions, entries) |
| Performance | File load time visibly impacts session responsiveness |
| Logical boundaries | Content naturally separates into distinct domains or time periods |

### Sharding Strategies

Choose the strategy that best fits the document type:

| Strategy | Use When | Example |
|----------|----------|---------|
| **Status-based** | Document has active/done/archived items | `active/`, `done/`, `archive/` subdirectories |
| **Date-based** | Document grows chronologically | `{YYYY-MM}/` subdirectories |
| **Component-based** | Content maps to distinct features or domains | `auth/`, `api/`, `frontend/` subdirectories |

### How to Shard

1. Create the target subdirectory within the same parent as the original document
2. Move content into shard files following the chosen strategy
3. Create an `INDEX.md` in the subdirectory listing all shards with brief descriptions
4. Update the original document to reference the index: "See `{subdirectory}/INDEX.md` for archived/completed entries"
5. Update `{oversight_path}/SESSION_WORK_INDEX.md` quick links if the sharded document was referenced there
6. Verify: no content was lost, all references updated, original file under threshold

### What NOT to Shard

- Active tracking files with < 50 entries (premature sharding adds navigation overhead)
- Template files (these are reference, not growing documents)
- Config files (these have their own schema management)

## Document Review Schedule

| Document Type | Review Trigger | Review Action |
|---------------|----------------|---------------|
| Tracking docs (task-tracker, blockers-log, risk-register) | Every session close | Verify status accuracy, close resolved items |
| Workflow/step files | On structural changes only | Confirm step sequences are correct, paths valid |
| Plans and specs | When status changes to "Complete" | Mark complete, archive if no longer referenced |
| Templates | Monthly or when a gap is found | Check for staleness, update if process changed |
| Constraint files | On version release or after a constraint violation | Verify constraints are current, add missing ones |
| Architecture docs | Quarterly | Review for drift against implementation |

## General Archival Policy

### When to Archive

Archive a document when:
- Work is complete and verified
- Document is superseded by a newer version
- Content is no longer actively referenced
- Document serves only historical reference

### Archive Process

1. Move the document to `{oversight_path}/archive/`
2. Rename with archive date: `{ORIGINAL-NAME}-archived-{YYYY-MM-DD}.md`
3. Retain ALL content — never delete archived documents
4. Update any index files or SESSION_WORK_INDEX.md quick links that referenced the original
5. Add a one-line note in the parent directory pointing to the archive location

### Archive Naming Convention

`{oversight_path}/archive/{ORIGINAL-NAME}-archived-{YYYY-MM-DD}.md`

Example: `oversight/archive/PLAN-010-archived-2026-03-15.md`
