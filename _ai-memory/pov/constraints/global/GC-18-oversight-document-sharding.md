---
id: GC-18
name: Oversight Document Sharding Compliance
severity: MEDIUM
phase: global
category: Quality
---

# GC-18: Oversight Document Sharding Compliance

## Constraint

When any oversight document in `{oversight_path}` exceeds the following thresholds,
Parzival MUST apply a sharding strategy before accepting the document as complete:

- **500 lines** in a single file, OR
- **50 items** in a single list or tracking section

Sharded directories MUST have an accompanying index file.

## Explanation

Large oversight documents degrade session performance and navigability. When a file grows beyond
500 lines or 50 items, Parzival cannot efficiently scan it within context constraints.
Sharding distributes content across smaller, focused files while an index preserves discoverability.

This prevents the gradual accumulation of unbounded tracking files (e.g., bug logs, decision
registers, tech-debt lists) that become unusable as projects mature.

If a sharding strategy document exists in the project, consult it for project-specific conventions
before choosing a method.

## Examples

**Status-based sharding** — split by item state:
```
{oversight_path}/bugs/
  active-bugs.md       # open, in-progress
  resolved-bugs.md     # fixed, closed
  index.md             # master index with links to both
```

**Date-based sharding** — split by time period:
```
{oversight_path}/decisions/
  decisions-2026-Q1.md
  decisions-2026-Q2.md
  index.md
```

**Component-based sharding** — split by system area:
```
{oversight_path}/tech-debt/
  tech-debt-storage.md
  tech-debt-injection.md
  tech-debt-sync.md
  index.md
```

## Enforcement

Parzival self-checks at every 10-message interval: "GC-18: Does any oversight document I am updating exceed 500 lines or 50 items? If yes, have I applied sharding?"

## Violation Response

1. Identify which threshold is exceeded (500 lines or 50 items)
2. Choose the appropriate sharding method (status-based, date-based, or component-based)
3. Consult the project sharding strategy doc if one exists in `{oversight_path}`
4. Split the document into focused shards
5. Create or update an `index.md` in the sharded directory with links to all shards
6. Update any references to the original file path to point to the index
