# Research Methodology

Detailed instructions for Phases 1-4 of best practices research.

---

## Phase 1: Check Database

### Steps

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))

from memory.search import search_memories

results = search_memories(
    query="topic keywords",
    collection="conventions",
    memory_type=["guideline", "rule"],
    limit=5
)
```

### Decision Matrix

| Score | Age | Action |
|-------|-----|--------|
| >0.7 | <6 months | Use it, skip to Phase 5 |
| >0.7 | 6-12 months | Mark "needs refresh", proceed to Phase 2 |
| >0.7 | >12 months | Mark "outdated", proceed to Phase 2 |
| <0.7 | Any | Proceed to Phase 2 |

---

## Phase 2: Web Research

### Search Queries

```
WebSearch: "[topic] best practices 2026"
WebSearch: "[topic] official documentation 2026"
```

### Source Prioritization

1. **Official Documentation** - Vendor/author docs
2. **GitHub / Official Repositories** - README, examples
3. **Established Tech Blogs** - Company engineering blogs
4. **Community Discussions** - Stack Overflow (highly voted)

### Freshness Thresholds

| Age | Status | Action |
|-----|--------|--------|
| <6 months | Current | Use as primary source |
| 6-12 months | Needs review | Verify with newer sources |
| >12 months | Outdated | Research for updates |

---

## Phase 3: Save to File

### Steps

1. Generate BP-ID: `ls oversight/knowledge/best-practices/BP-*.md | sort -V | tail -1`
2. Create file: `oversight/knowledge/best-practices/BP-XXX-[topic].md`
3. Use format from OUTPUT-FORMAT.md

---

## Phase 4: Store to Database

```python
from memory.storage import store_best_practice

result = store_best_practice(
    content="Concise best practice description",
    session_id="current-session-id",
    source_hook="manual",
    domain="topic-domain",
    tags=["topic", "keywords"],
    source="https://source-url.com",
    source_date="2026-01-29",
    auto_seeded=True
)

if result.get("status") == "stored":
    print(f"Stored: {result['memory_id']}")
elif result.get("status") == "duplicate":
    print(f"Duplicate skipped")
```

### Valid source_hook Values

- PostToolUse, Stop, SessionStart
- UserPromptSubmit, PreCompact, PreToolUse
- seed_script, manual
