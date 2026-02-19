# Oversight Document Sharding Strategy

**Version**: 1.0
**Last Updated**: 2026-01-21
**Status**: Active

---

## Purpose

This document defines when and how to shard (split) oversight documents to maintain performance, readability, and maintainability as projects grow.

---

## When to Shard

### Threshold Triggers

Shard a document when ANY of these conditions are met:

| Metric | Threshold | Reason |
|--------|-----------|--------|
| **Line Count** | > 500 lines | File becomes unwieldy to navigate |
| **Item Count** | > 50 items | Too many items to scan quickly |
| **File Size** | > 100KB | Performance degradation in editors |
| **Load Time** | > 2 seconds | Poor user experience |
| **Status Distribution** | 80% in one state | Most content is archived/complete |

### Logical Boundaries

Consider sharding when natural boundaries exist:

- **Time-based**: Quarterly, monthly, or by sprint
- **Status-based**: Active vs. archived/complete
- **Component-based**: By module, service, or feature area
- **Priority-based**: Critical/high vs. medium/low
- **Phase-based**: Planning vs. implementation vs. complete

---

## Sharding Strategies

### Strategy 1: Status-Based Sharding

**Best For**: Task trackers, bug logs, validation reports

**Structure**:
```
tracking/
├── tasks/
│   ├── INDEX.md              # Quick reference
│   ├── active.md             # In Progress + Not Started
│   ├── review.md             # In Review
│   ├── completed.md          # Done (last 30 days)
│   └── archive/
│       ├── 2026-Q1.md        # Archived by quarter
│       └── 2025-Q4.md
```

**Naming Convention**:
- `active.md` - Currently active items
- `completed.md` - Recently completed (rolling window)
- `archive/YYYY-QN.md` - Archived by quarter

**When to Archive**:
- Move completed items to archive after 30 days
- OR when completed.md exceeds 50 items
- Keep index updated with counts

---

### Strategy 2: Date-Based Sharding

**Best For**: Session logs, decisions, blockers

**Structure**:
```
session-logs/
├── INDEX.md                  # Navigation index
├── 2026/
│   ├── 2026-01/
│   │   ├── SESSION_2026-01-15.md
│   │   ├── SESSION_2026-01-18.md
│   │   └── SESSION_2026-01-21.md
│   └── 2026-02/
│       └── SESSION_2026-02-01.md
└── 2025/
    └── 2025-12/
        └── SESSION_2025-12-20.md
```

**Naming Convention**:
- `YYYY/YYYY-MM/SESSION_YYYY-MM-DD.md`
- `YYYY/YYYY-MM/DECISION_YYYY-MM-DD.md`
- ISO 8601 date format (YYYY-MM-DD)

**When to Shard**:
- One document per session/decision
- Group by year/month for navigation
- Never exceeds thresholds (one item per file)

---

### Strategy 3: Component-Based Sharding

**Best For**: Bugs, specs, technical debt

**Structure**:
```
bugs/
├── INDEX.md                  # Master index
├── authentication/
│   ├── BUG-001.md
│   ├── BUG-015.md
│   └── BUG-027.md
├── database/
│   ├── BUG-003.md
│   └── BUG-012.md
├── api/
│   ├── BUG-005.md
│   └── BUG-008.md
└── archive/
    └── resolved-2025-Q4.md
```

**Naming Convention**:
- `{component-name}/BUG-XXX.md`
- Component names: lowercase, hyphenated
- Preserve sequential IDs across components

**When to Shard**:
- When a component has > 20 bugs
- OR when bugs.md exceeds 500 lines
- Create component directory, move related bugs

---

### Strategy 4: Priority-Based Sharding

**Best For**: Risks, audits, validation

**Structure**:
```
audits/
├── INDEX.md                  # Cross-reference
├── critical/
│   ├── AUDIT-001-security.md
│   └── AUDIT-004-performance.md
├── high/
│   ├── AUDIT-002-code-quality.md
│   └── AUDIT-005-architecture.md
├── medium/
│   └── AUDIT-003-documentation.md
└── archive/
    └── completed-2025.md
```

**Naming Convention**:
- `{priority}/AUDIT-XXX-{topic}.md`
- Priority: critical, high, medium, low
- Topic: brief slug (1-3 words)

**When to Shard**:
- When audits.md exceeds 30 findings
- OR when critical items need visibility
- Move to priority-based structure

---

## Index File Requirements

Every sharded directory MUST have an `INDEX.md` file.

### Minimum Index Structure

```markdown
# [Document Type] Index

**Last Updated**: [YYYY-MM-DD]
**Total Items**: [Count]

---

## Quick Stats

| Status/Category | Count | Location |
|-----------------|-------|----------|
| Active | X | [Link to file] |
| Archived | Y | [Link to archive] |

---

## Navigation

### By Status
- [Active Items](active.md) - X items
- [Completed Items](completed.md) - Y items
- [Archive](archive/) - Z items

### By Date
- [2026-01](2026/2026-01/) - X items
- [2025-12](2025/2025-12/) - Y items

### By Component
- [Authentication](authentication/) - X items
- [Database](database/) - Y items

---

## Search Tips

[How to find specific items in this shard]

---

## Maintenance

- **Last Sharded**: [YYYY-MM-DD]
- **Next Review**: [YYYY-MM-DD]
- **Archive Policy**: [Description]
```

---

## Sharding Process

### Step 1: Assess Need

- [ ] Check document metrics (lines, items, size)
- [ ] Identify natural sharding boundaries
- [ ] Choose appropriate sharding strategy
- [ ] Plan directory structure

---

### Step 2: Prepare Structure

```bash
# Example: Status-based sharding for tasks
mkdir -p tracking/tasks/archive
touch tracking/tasks/INDEX.md
touch tracking/tasks/active.md
touch tracking/tasks/completed.md
```

---

### Step 3: Split Content

**CRITICAL**: Don't break mid-item. Always keep related content together.

**Good Split**:
```markdown
# active.md
## Task 1
[Complete task content]

## Task 2
[Complete task content]

# completed.md
## Task 3
[Complete task content]
```

**Bad Split** (DON'T DO THIS):
```markdown
# active.md
## Task 1
[First half of content...]

# completed.md
[...second half of content]
```

---

### Step 4: Create Index

1. **Count items** in each shard
2. **Create navigation links** to all shards
3. **Add metadata** (last updated, totals)
4. **Include search tips** for finding items
5. **Document archive policy**

---

### Step 5: Update References

Search and update references in:
- [ ] Other oversight documents
- [ ] Agent instructions
- [ ] Procedure documents
- [ ] README files
- [ ] Task tracker

**Example Reference Updates**:
```markdown
# Before
See bugs.md for all open bugs

# After
See bugs/INDEX.md for bug navigation
Active bugs: bugs/active.md
```

---

### Step 6: Archive Old Version

```bash
# Keep original as backup for 30 days
mv task-tracker.md task-tracker.md.backup-YYYY-MM-DD

# After 30 days and verification
rm task-tracker.md.backup-YYYY-MM-DD
```

---

## Sharding Examples

### Example 1: Bug Log (50+ bugs)

**Before**:
```
bugs.md (800 lines, 52 bugs)
```

**After** (Status-based):
```
bugs/
├── INDEX.md (50 lines)
├── active.md (200 lines, 15 bugs)
├── in-progress.md (150 lines, 8 bugs)
├── fixed-pending-verification.md (100 lines, 5 bugs)
└── archive/
    └── resolved-2025-Q4.md (300 lines, 24 bugs)
```

**Benefits**:
- Active bugs easy to find
- Archived bugs separated
- Each file < 300 lines
- Fast to load and navigate

---

### Example 2: Decision Log (100+ decisions)

**Before**:
```
decisions-log.md (1500 lines, 103 decisions)
```

**After** (Date-based):
```
decisions/
├── INDEX.md (100 lines)
├── 2026/
│   ├── 2026-01/
│   │   ├── DEC-103-authentication.md
│   │   ├── DEC-102-api-versioning.md
│   │   └── DEC-101-database-sharding.md
│   └── 2026-02/
└── 2025/
    ├── 2025-11/
    │   └── [...decisions...]
    └── 2025-12/
        └── [...decisions...]
```

**Benefits**:
- One decision per file (easy to reference)
- Chronological organization
- Quick to find recent decisions
- Unlimited scalability

---

### Example 3: Task Tracker (Active Project)

**Before**:
```
task-tracker.md (600 lines, 67 tasks)
```

**After** (Status-based):
```
tracking/
├── task-tracker/
│   ├── INDEX.md
│   ├── active.md (12 tasks)
│   ├── in-review.md (8 tasks)
│   ├── blocked.md (3 tasks)
│   ├── completed-recent.md (20 tasks, last 30 days)
│   └── archive/
│       ├── 2026-Q1.md (24 tasks)
│       └── 2025-Q4.md (...)
```

**Benefits**:
- Active work visible at top
- Blockers separated for attention
- Recent completions for reference
- Historical archive preserved

---

## Maintenance Procedures

### Weekly Maintenance

For active shards:
- [ ] Update item counts in INDEX.md
- [ ] Move completed items to appropriate shard
- [ ] Check for items to archive
- [ ] Update "Last Updated" dates

### Monthly Maintenance

- [ ] Review shard sizes
- [ ] Archive items > 30 days old
- [ ] Update INDEX.md stats
- [ ] Check for new sharding needs

### Quarterly Maintenance

- [ ] Review sharding strategy effectiveness
- [ ] Consolidate small shards if needed
- [ ] Archive old quarters
- [ ] Update documentation

---

## Anti-Patterns (Don't Do This)

### ❌ Over-Sharding

**Problem**: Creating too many small shards
```
bugs/
├── critical/
│   └── BUG-001.md (only 1 bug)
├── high/
│   └── BUG-002.md (only 1 bug)
└── medium/
    └── BUG-003.md (only 1 bug)
```

**Better**: Keep in single file until threshold reached

---

### ❌ Inconsistent Naming

**Problem**: Mixed naming conventions
```
bugs/
├── BUG-001-auth-issue.md
├── bug_002.md
├── Bug-003.MD
└── authentication-bug.md
```

**Better**: Consistent naming: `BUG-XXX-short-description.md`

---

### ❌ Breaking Items Mid-Content

**Problem**: Splitting related content
```
# active.md
## BUG-001: Authentication Failure
**Status**: In Progress
**Priority**: High

# another-file.md
[...rest of BUG-001 content]
```

**Better**: Keep entire item together

---

### ❌ No Index File

**Problem**: Sharded directory with no navigation
```
bugs/
├── BUG-001.md
├── BUG-002.md
├── BUG-003.md
[...50 more files...]
```

**Better**: Always create INDEX.md for navigation

---

### ❌ Forgetting to Update References

**Problem**: Links break after sharding
```
Other docs still reference: See bugs.md
But file is now: bugs/INDEX.md
```

**Better**: Search and update all references

---

## Migration Checklist

When sharding an existing document:

### Pre-Migration
- [ ] Back up original file
- [ ] Choose sharding strategy
- [ ] Plan directory structure
- [ ] Create INDEX.md template

### Migration
- [ ] Create directory structure
- [ ] Split content logically
- [ ] Preserve all item IDs
- [ ] Create INDEX.md
- [ ] Verify no content lost

### Post-Migration
- [ ] Update all references
- [ ] Update procedures if needed
- [ ] Test navigation
- [ ] Archive original (keep 30 days)
- [ ] Document in session log

### Verification
- [ ] All items accounted for
- [ ] INDEX.md has correct counts
- [ ] Links work correctly
- [ ] Load times improved
- [ ] User can navigate easily

---

## Tools and Scripts

### Count Items in Directory

```bash
# Count markdown files
find bugs/ -name "*.md" | wc -l

# Count specific pattern (e.g., BUG-XXX)
grep -r "^## BUG-" bugs/ | wc -l
```

### Check File Sizes

```bash
# Find large files (>100KB)
find oversight/ -name "*.md" -size +100k -ls
```

### Audit Line Counts

```bash
# Count lines in all md files
wc -l oversight/**/*.md | sort -n
```

---

## References

- Parzival Procedures: `bmad-parzival-module/pov/procedures/PROCEDURES.md`
- Template Directory: `bmad-parzival-module/pov/templates/oversight/`
- Agent Instructions: `bmad-parzival-module/pov/agents/parzival.md`

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-21 | 1.0 | Initial sharding strategy document |

---

## Notes

- Sharding is a tool, not a requirement. Only shard when it improves usability.
- Preserve all content - never delete when sharding
- Consistency matters more than perfect organization
- INDEX.md is mandatory for all sharded directories
- Test navigation before finalizing sharding
