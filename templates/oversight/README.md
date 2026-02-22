# Parzival Oversight System

This directory contains Parzival's documentation and tracking system for maintaining project context across sessions.

## Directory Structure

```
oversight/
├── README.md                    # This file
├── SESSION_WORK_INDEX.md        # Lightweight session history
├── tracking/                    # Current state
│   ├── task-tracker.md
│   ├── risk-register.md
│   ├── blockers-log.md
│   ├── dependencies.md
│   ├── scope-change-log.md
│   └── technical-debt.md
├── decisions/                   # Decision records (DEC-###)
├── learning/                    # Accumulated knowledge
│   └── failure-pattern-library.md
├── knowledge/                   # Confidence map, assumptions
│   ├── confidence-map.md
│   └── assumption-registry.md
├── research/                    # Best practices research
│   └── best-practices-log.md
├── session-logs/                # Handoffs and state snapshots
├── prompts/                     # Reusable prompts
├── uncertainty/                 # Questions needing resolution
└── verification/                # Checklists and quality criteria
    └── checklists/
```

## How to Use

### Starting a Session
Run `/pov:commands:parzival-start` to load context and get status.

### Ending a Session
Run `/pov:commands:parzival-closeout` to create a handoff document.

### Quick Status
Run `/pov:commands:parzival-status` for a quick status check.

## Key Principles

1. **Write for Future Parzival**: Every document should be readable by a Claude instance with no context from the current session.

2. **Explicit State**: Don't assume context carries over. State everything explicitly.

3. **Evidence-Based**: Link to files, quote logs, reference specific lines.

4. **Living Documents**: Keep documents updated as the project evolves.

## Core Rule

**Parzival recommends. The user decides.**
