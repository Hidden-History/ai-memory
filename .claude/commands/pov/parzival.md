---
description: 'Activate Parzival oversight agent with interactive menu'
allowed-tools: Read, Grep, Glob, AskUserQuestion, Write, Edit, Bash
---

# Activate Parzival

Read and fully embody the agent defined at: `_ai-memory/pov/agents/parzival.md`

Follow ALL activation instructions exactly as specified:
1. Load config from `_ai-memory/pov/config.yaml`
2. Load global constraints from the constraints path
3. Load the workflow map
4. Check for current phase via project-status.md
5. Greet user with current phase + project status
6. Display the interactive menu
7. WAIT for user input — do NOT auto-proceed

This is the full Parzival agent with interactive menu. For individual workflow shortcuts, use the specific commands (parzival-start, parzival-team, etc.).
