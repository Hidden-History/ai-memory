---
name: aim-parzival-constraints
description: Load Parzival behavioral constraints as context reminder
allowed-tools: Bash
---

# Parzival Constraints — Active Reminder

Load Parzival's behavioral constraints from `_ai-memory/pov/constraints/`. Used during session activation, after compaction, or when Parzival seems to be drifting.

## Steps

1. Run the constraints script via `run-with-env.sh`:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/pov/skills/aim-parzival-constraints/scripts/constraints.py" \
  --phase <phase>
```

Note: `--phase <phase>` is optional — omit if no phase context is available.

2. Internalize the constraints as active behavioral rules for the remainder of this session.

3. If no constraints are found or the skill fails to load, STOP and report to the user immediately. Do not continue the session without constraints active — the constraint system is a mandatory safety layer, not optional context.
