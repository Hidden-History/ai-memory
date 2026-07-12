---
name: aim-best-practices-researcher
description: Research current best practices for any technology, pattern, or coding standard. Use when asking about best practices, conventions, coding standards, recommended approaches, or how should I questions. Searches local knowledge first, then web for current sources (prioritizing the last ~6 months relative to today). Evaluates if findings warrant a reusable skill.
allowed-tools: Read, Write, Grep, Glob, WebSearch, WebFetch, Bash(python3:*), Skill
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
    limit=5,
    attach_raw_cosine=True,  # BP-058/#317: needed for the relevance gate below
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
- [ ] Phase 3: Save to file (BP-XXX.md) + append INDEX row
- [ ] Phase 4: Store to database
- [ ] Phase 5: Evaluate skill-worthiness
```

**Write scope (this skill writes ONLY these):** the BP file
(`oversight/knowledge/best-practices/BP-XXX-[topic].md`), its INDEX row
(`oversight/knowledge/best-practices/index.md`, appended in
Phase 3), and the conventions-collection store (Phase 4). Do NOT edit
roadmaps, SoT files, or any other oversight file.

### Phase 1: Check Database

Query conventions collection via semantic search. Gate on `raw_score` not
`score` — see RESEARCH-METHODOLOGY.md ("Phase 1"). Decision rules:
- `raw_score` ≥0.7 AND content addresses the query AND <6 months old → Use it, skip to Phase 5
- `raw_score` ≥0.7 AND content addresses the query AND 6-12 months old → Mark "needs refresh", proceed to Phase 2
- `raw_score` ≥0.7 AND content addresses the query AND >12 months old → Mark "outdated", proceed to Phase 2
- `raw_score` <0.7, OR content doesn't address the query, OR not found → Proceed to Phase 2

### Phase 2: Web Research

Search for current best practices, prioritizing sources published within the last ~6 months relative to today's date (flag an older source only when it remains the authoritative current standard). Source prioritization:
1. Official documentation
2. GitHub repositories
3. Established tech blogs
4. Community discussions

When presenting each finding, state why it is the current gold standard and cite the source's publication recency.

### Phase 3: Save to File

1. Generate the next BP-ID by scanning existing files with **Glob**
   (`oversight/knowledge/best-practices/BP-*.md`) — take the highest ID + 1.
2. **Write** `oversight/knowledge/best-practices/BP-XXX-[topic].md` using the
   format from [OUTPUT-FORMAT.md](OUTPUT-FORMAT.md).
3. Update the INDEX from disk:

   ```bash
   "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python" \
       "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-best-practices-researcher/scripts/bp_index.py" \
       --write oversight/knowledge/best-practices
   ```

   `bp_index.py` appends any `BP-*.md` file missing from `index.md` (matched
   by BP-ID) without touching existing rows — idempotent, non-destructive.
   Swap `--write` for `--check` to verify every BP file has a matching
   INDEX row (silent when all present; non-zero and lists offenders when not).

   `index.md`'s table is wrapped in a `<!-- BEGIN bp-index (...) -->` /
   `<!-- END bp-index -->` marker pair; `--write`/`--check` key canonical-table
   selection off this region, so a renamed header or a second top-level table
   doesn't break selection. Markers absent → falls back to header-sniffing and
   refuses (writes/reports nothing) on ambiguity. Never remove the markers by hand.

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
- [ ] If exit code 3 / WARNING (stored but embedding incomplete): the finding
      IS stored but not yet semantically searchable — run
      `backfill_pending_embeddings.py`, don't re-run store (it would just
      report "Duplicate skipped")

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
