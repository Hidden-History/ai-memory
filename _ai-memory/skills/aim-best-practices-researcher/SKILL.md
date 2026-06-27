---
name: aim-best-practices-researcher
description: Research current best practices for any technology, pattern, or coding standard. Use when asking about best practices, conventions, coding standards, recommended approaches, or how should I questions. Searches local knowledge first, then web for current sources (prioritizing the last ~6 months relative to today). Evaluates if findings warrant a reusable skill.
allowed-tools: Read, Grep, Glob, WebSearch, WebFetch, Bash(python3:*), Skill
context: fork
---

# Best Practices Researcher

Research specialist for current best practices. Checks local database first, then web if needed. Stores findings and evaluates skill-worthiness.

## Quick Start

```python
# Phase 1: Check database
import os
import sys
sys.path.insert(0, os.path.join(os.path.expanduser("~/.ai-memory"), "src"))
from memory.search import search_memories

# The 'conventions' collection is project-scoped (PLAN-028 P1, DEC-PM298-D4).
# Resolve the project from AI_MEMORY_PROJECT_ID — never from os.getcwd(), which
# is unreliable for this forked skill subprocess. Fail loud if it is not set.
project_id = os.environ.get("AI_MEMORY_PROJECT_ID")
if not project_id:
    raise RuntimeError(
        "AI_MEMORY_PROJECT_ID is not set — cannot search the project-scoped "
        "'conventions' collection. Set AI_MEMORY_PROJECT_ID and retry."
    )
results = search_memories(
    query="your topic",
    collection="conventions",
    group_id=project_id,
    memory_type=["guideline", "rule"],
    limit=5
)
```

```bash
# Phase 4: Store findings
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" store_best_practice.py \
    --content "Best practice description" \
    --session-id "current-session" \
    --domain "python" \
    --tags topic \
    --source "https://source-url.com" \
    --source-date "2026-01-29" \
    --group-id "$AI_MEMORY_PROJECT_ID"
```

## 5-Phase Workflow

Copy this checklist and track progress:

```
Research Progress:
- [ ] Phase 1: Check database (conventions collection)
- [ ] Phase 2: Web research (if needed)
- [ ] Phase 3: Save to file (BP-XXX.md)
- [ ] Phase 4: Store to database
- [ ] Phase 5: Evaluate skill-worthiness
```

### Phase 1: Check Database

Query conventions collection via semantic search. Decision rules:
- Score >0.7 and <6 months old → Use it, skip to Phase 5
- Score >0.7 and >6 months old → Mark "needs refresh", proceed to Phase 2
- Score <0.7 or not found → Proceed to Phase 2

### Phase 2: Web Research

Search for current best practices, prioritizing sources published within the last ~6 months relative to today's date (flag an older source only when it remains the authoritative current standard). Source prioritization:
1. Official documentation
2. GitHub repositories
3. Established tech blogs
4. Community discussions

When presenting each finding, state why it is the current gold standard and cite the source's publication recency.

### Phase 3: Save to File

Generate next BP-ID and create `oversight/knowledge/best-practices/BP-XXX-[topic].md`

### Phase 4: Store to Database (MANDATORY)

**CRITICAL**: You MUST run this command to store findings to the database.
Without this step, research is lost and BUG-048 occurs.

```bash
# MANDATORY - Run this command to store findings
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" store_best_practice.py \
    --content "YOUR_FINDING_CONTENT_HERE" \
    --session-id "YOUR_SESSION_ID" \
    --domain "YOUR_DOMAIN" \
    --tags YOUR TAGS \
    --source "SOURCE_URL" \
    --source-date "2026-05-30" \
    --group-id "$AI_MEMORY_PROJECT_ID"
```

**Checklist before moving to Phase 5**:
- [ ] Ran store_best_practice.py via run-with-env.sh
- [ ] Received "Stored: <id>" or "Duplicate skipped" confirmation
- [ ] If duplicate, that's OK - finding already exists

### Phase 5: Skill Evaluation

Evaluate findings against criteria from [SKILL-EVALUATION.md](SKILL-EVALUATION.md):

**Decision rule**: (Process-oriented AND Reusable) OR Stack Pain Point → recommend skill

If skill-worthy, prompt user. If user confirms, invoke Skill Creator.

## Detailed Methodology

See [RESEARCH-METHODOLOGY.md](RESEARCH-METHODOLOGY.md)

## Skill Evaluation Criteria

See [SKILL-EVALUATION.md](SKILL-EVALUATION.md)

## Output Format

See [OUTPUT-FORMAT.md](OUTPUT-FORMAT.md)
