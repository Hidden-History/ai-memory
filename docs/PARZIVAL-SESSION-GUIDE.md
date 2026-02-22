# 🧭 Parzival Session Agent Guide

Parzival is an optional session agent for the AI Memory Module. It provides cross-session memory, project knowledge persistence, and GitHub-enriched session awareness — all backed by Qdrant vector search. If you work on a project across multiple Claude Code sessions, Parzival picks up where you left off.

---

## What is Parzival?

Parzival acts as a Technical PM and quality gatekeeper that persists across sessions. At the start of each session, it loads your last handoff, active insights, and recent GitHub activity. At the end, it saves a handoff document so the next session starts with full context.

Without Parzival, you manually orient Claude Code each session ("we were working on X, last we did Y"). With Parzival, context is loaded automatically from Qdrant.

Parzival is an optional feature — all other AI Memory capabilities (decay scoring, freshness detection, GitHub sync, search skills) work independently of it.

---

## Enabling Parzival

### During Install

The installer prompts for Parzival setup:

```
Enable Parzival session agent? [y/N]
Your name (for handoffs and oversight docs): Parzival
Preferred language [English]:
```

On confirmation, the installer deploys:
- Commands to `.claude/commands/parzival/`
- Agent files to `.claude/agents/parzival/`
- Oversight directory templates to `oversight/`

### Manual Enable

If you skipped Parzival during install, add these to your `.env`:

```bash
PARZIVAL_ENABLED=true
PARZIVAL_USER_NAME=YourName
PARZIVAL_LANGUAGE=English
```

Then re-run the installer targeting the Parzival component:

```bash
bash install.sh --component parzival
```

---

## Session Start — What Gets Loaded

When you run `/parzival-start`, Parzival performs a Tier 1 bootstrap (see [TEMPORAL-FEATURES.md](TEMPORAL-FEATURES.md)) within a ~2–3K token budget:

### 1. Latest Handoff

```
Qdrant query: agent_id=parzival, type=agent_handoff, limit=1
Sort: created_at DESC
```

Loads the session state from your last closeout: what was completed, what's in progress, blockers, next steps.

### 2. Active Insights

```
Qdrant query: agent_id=parzival, type=agent_insight
Sort: decay-ranked (semantic + temporal)
Limit: top 5
```

Surfaced learned knowledge — architectural decisions made, patterns discovered, recurring issues resolved.

### 3. GitHub Enrichment

If `GITHUB_SYNC_ENABLED=true`, Parzival also queries:
- Merged PRs since `last_session_end`
- New issues opened since `last_session_end`
- CI failures on the default branch

This appears as a "What changed since last session" summary at the start of `/parzival-start` output.

### Fallback (Qdrant Unavailable)

If Qdrant is offline at session start:

1. Read `oversight/SESSION_WORK_INDEX.md` for current sprint state
2. Read the latest handoff file from `oversight/session-logs/` (sorted by filename date)
3. Log a warning that Qdrant-backed enrichment was skipped

---

## Session End — Closeout

When you run `/parzival-closeout`, Parzival:

### 1. Creates a Handoff File

Saves a structured markdown file to `oversight/session-logs/`:

```
oversight/session-logs/YYYY-MM-DD-HH-MM-session-handoff.md
```

Contents include:
- Session summary (what was accomplished)
- In-progress work (tasks started but not finished)
- Active blockers
- Recommended next steps
- Key decisions made

### 2. Dual-Write to Qdrant

The handoff is also stored as a vector in Qdrant:

```
collection: discussions
type: agent_handoff
agent_id: parzival
content: <full handoff markdown>
created_at: <ISO 8601 timestamp>
```

This enables semantic search across past handoffs and decay-ranked retrieval at next session start.

### 3. Updates SESSION_WORK_INDEX.md

Appends a summary line to `oversight/SESSION_WORK_INDEX.md`:

```markdown
## 2026-02-16 Session
- Completed: SPEC-018 AC-20, AC-21, AC-22 documentation
- In progress: —
- Next: Integration testing for GitHub sync
```

### 4. Stores Active Task State

Any in-progress tasks tracked during the session are stored to Qdrant:

```
type: agent_task
agent_id: parzival
status: in_progress | blocked | completed
```

These are loaded at next session start as part of context injection.

---

## Commands Reference

Commands live in `.claude/commands/parzival/` and are invoked with `/`.

| Command | Description |
|---|---|
| `/parzival-start` | Load context from Qdrant, display session status, show GitHub enrichment summary |
| `/parzival-closeout` | Create handoff file, dual-write to Qdrant, update work index, end session |
| `/parzival-status` | Quick status check: active tasks, blockers, recent handoff summary |
| `/parzival-handoff` | Mid-session state snapshot (does not end the session) |
| `/parzival-blocker` | Analyze a blocker and present resolution options |
| `/parzival-decision` | Present a decision request with options and tradeoffs |
| `/parzival-verify` | Run verification checklist on completed work |
| `/parzival-team` | Build a 3-tier agent team prompt using the V3 hierarchical template |

### Usage Examples

```bash
# Start a new session
/parzival-start

# Check status mid-session without full reload
/parzival-status

# Capture a snapshot without ending the session
/parzival-handoff

# Analyze a blocker
/parzival-blocker "GitHub sync is failing with 403 after the token refresh"

# Support a decision
/parzival-decision "Should we use incremental or full sync for the first GitHub run?"

# Verify completed work
/parzival-verify "SPEC-018 documentation complete"

# End the session
/parzival-closeout
```

---

## Skills Reference

Skills live in `.claude/commands/` and provide direct Qdrant storage operations.

| Skill | Description |
|---|---|
| `/parzival-save-handoff` | Manually store handoff content to Qdrant (used internally by `/parzival-closeout`) |
| `/parzival-save-insight` | Store a learned insight to Qdrant for future retrieval |

### Saving an Insight Manually

Use `/parzival-save-insight` to capture important knowledge mid-session:

```bash
/parzival-save-insight "Qdrant requires the api-key header on ALL endpoints including /health — not just mutation endpoints"
```

Stored with:
```
type: agent_insight
agent_id: parzival
half_life_days: 180  (long-lived learned knowledge)
```

---

## Without Parzival

All core AI Memory features work independently of Parzival:

| Feature | Without Parzival |
|---|---|
| Decay scoring | Available |
| Freshness detection | Available |
| GitHub sync | Available |
| `/search-memory`, `/search-jira`, `/search-github` | Available |
| `/freshness-report`, `/memory-refresh` | Available |
| Session continuity via Qdrant | **Not available** |
| `agent_handoff` / `agent_insight` namespace | **Not available** |
| GitHub-enriched session start | **Not available** |
| Automatic session state persistence | **Not available** |

If you do not need cross-session continuity, you can skip Parzival entirely and rely on manual context-setting at the start of each session.

---

## Oversight Directory Structure

The installer deploys a set of template directories to `oversight/` that Parzival uses for tracking and documentation:

```
oversight/
├── SESSION_WORK_INDEX.md       ← Running log of sessions and sprint state
├── session-logs/               ← Handoff files (one per session closeout)
│   └── YYYY-MM-DD-HH-MM-session-handoff.md
├── plans/                      ← Sprint and project plans (PLAN-NNN-*.md)
├── specs/                      ← Technical specifications (SPEC-NNN-*.md)
├── tracking/                   ← Issue and bug tracking documents
├── knowledge/                  ← Best practices, research notes
│   └── best-practices/         ← BP-NNN-*.md files
└── audits/                     ← Audit logs and review outcomes
```

The `session-logs/` directory grows over time. Parzival's closeout always creates a new file rather than overwriting, so you have a complete history of session handoffs. Old handoffs in Qdrant are subject to decay scoring (180-day half-life) and can be archived with `/memory-purge` if the directory grows large.
