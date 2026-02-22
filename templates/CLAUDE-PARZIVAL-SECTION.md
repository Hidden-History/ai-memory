# Parzival — Technical PM & Quality Gatekeeper

> **Note**: This section is added automatically by the ai-memory installer when you
> enable Parzival. To enable, run `./scripts/install.sh` and choose the Parzival option,
> or set `PARZIVAL_ENABLED=true` in `docker/.env` and re-run setup.

---

## Agent Configuration

Parzival reads these environment variables from `docker/.env` (set by the installer):

| Variable | Default | Description |
|----------|---------|-------------|
| `PARZIVAL_ENABLED` | `false` | Enable Parzival session agent |
| `PARZIVAL_USER_NAME` | `Developer` | Your display name for greetings and handoffs |
| `PARZIVAL_LANGUAGE` | `English` | Communication language |
| `PARZIVAL_DOC_LANGUAGE` | `English` | Language for generated documents |
| `PARZIVAL_OVERSIGHT_FOLDER` | `oversight` | Project-relative path to oversight directory |
| `PARZIVAL_HANDOFF_RETENTION` | `10` | Number of recent handoff files to keep |

To update settings, edit `docker/.env` directly. Changes take effect at next session start.

---

## Oversight Folder

All Parzival session data lives in `{PARZIVAL_OVERSIGHT_FOLDER}/` (default: `oversight/`):

```
oversight/
├── session-logs/          # Session handoffs (dual-written to file + Qdrant)
├── session-index/         # Weekly session index and archive
├── tracking/              # task-tracker, blockers-log, risk-register, etc.
├── plans/                 # PLAN_NNN directories with specs
├── specs/                 # Standalone specs
├── bugs/                  # Bug reports and root cause analyses
├── decisions/             # Architectural decision records
├── knowledge/             # Best practices, confidence map, assumption registry
├── learning/              # Failure pattern library
├── standards/             # Global and project-specific standards
├── verification/          # Completion checklists
├── validation/            # Validation records
└── audits/                # Audit reports
```

Parzival can freely read and write within this folder. It does **not** modify application
code — that is always done by developer agents at your direction.

---

## Session Management Commands

Invoke Parzival from Claude Code by loading the agent:

```
> use agent parzival
```

Once active, Parzival displays a numbered menu. Key commands:

| Cmd | Trigger | Description |
|-----|---------|-------------|
| `PS` | `start`, `session` | Start session — load context from Qdrant, show status |
| `PC` | `close`, `end` | Closeout session — create handoff, persist to Qdrant |
| `ST` | `status` | Quick status check without full session startup |
| `HO` | `handoff` | Create mid-session handoff (state snapshot) |
| `BL` | `blocker` | Analyze a blocker and present resolution options |
| `DC` | `decision` | Request decision support with options and tradeoffs |
| `VR` | `verify` | Run verification checklist on completed work |
| `TM` | `team` | Build a 3-tier agent team prompt |
| `CR` | `code-review` | Invoke code reviewer subagent |
| `VI` | `verify-implementation` | Invoke verify-implementation subagent |
| `DA` | `exit`, `goodbye` | Dismiss Parzival |

Commands are installed at `.claude/commands/parzival/` in this project.

### Quick Skills (no agent session required)

```bash
# Save a session handoff directly to Qdrant
/parzival-save-handoff "PM #55: Completed Phase 1d implementation"
/parzival-save-handoff --file oversight/session-logs/SESSION_HANDOFF_2026-02-16.md

# Save an insight or learning
/parzival-save-insight "Qdrant tenant index reduces query time by ~40% on agent_id filter"
```

---

## Cross-Session Memory

When Parzival starts a session (`PS`), it bootstraps from Qdrant:
- Loads the 3 most recent handoffs for current project context
- Retrieves relevant agent memories and insights
- Displays project status with risk and blocker summary

On closeout (`PC`), it dual-writes:
1. Handoff file → `oversight/session-logs/SESSION_HANDOFF_{date}.md`
2. Handoff content → Qdrant `discussions` collection (`agent_id=parzival`)

This ensures continuity even if the oversight folder is wiped or moved.
