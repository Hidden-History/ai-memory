---
class: heartbeat
read_path: whole-file
owns: "routing-machine state + live_record pointer"
cap_lines: 60
cap_kb: 6
rotation_trigger: none
archive_target: N/A
index_file: N/A
reconciliation: "overwrite-in-place every close; narrative lives in SESSION_WORK_INDEX + handoff, NEVER here"
---
# project-status.md

```yaml
current_phase: {discovery|architecture|planning|execution|integration|release|maintenance}
current_sprint: {n|null}
active_task: {path|null}
baseline_complete: {true|false}
phases_complete:                       # routing-gate state maintained by phase approval-gate steps
  discovery: {true|false}
  architecture: {true|false}
  planning_initialized: {true|false}
key_files:                             # reference pointers maintained by init/verify/finalize steps
  prd: {path|null}
  architecture: {path|null}
  project_context: {path|null}
live_record: oversight/SESSION_WORK_INDEX.md
last_session_summary: "{≤200 chars — date + PM# + what shipped}"
open_issues: {count}
```
