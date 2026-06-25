# BMAD Agent Reference

## Agent Command Reference

| Agent Type | Activation Command |
|---|---|
| Developer | `/bmad-agent-dev` |
| PM (Product Manager) | `/bmad-agent-pm` |
| Analyst | `/bmad-agent-analyst` |
| Architect | `/bmad-agent-architect` |
| UX Designer | `/bmad-agent-ux-designer` |
| Tech Writer | `/bmad-agent-tech-writer` |

## Task-to-Agent Selection Guide

When the task description does not specify an agent:

| Task Type | Agent | Menu Code |
|---|---|---|
| Research / analyze codebase | Analyst | Use menu |
| Create or update PRD | PM | `CP` |
| Validate a PRD | PM | `VP` |
| Break down features into stories | PM | `CE` |
| Design system architecture | Architect | Use menu |
| Write code / implement a story | DEV | `/bmad-dev-story` (or `DS`) |
| Review implemented code | Code Review (NOT the dev agent) | `/bmad-code-review` |
| Design user flows | UX Designer | Use menu |
| Write or review documentation | Tech Writer | `WD` |
| Validate documentation | Tech Writer | `VD` |
| Build new BMAD agents | Agent Builder | Use menu |
| Build new BMAD modules | Module Builder | Use menu |
| Build new BMAD workflows | Workflow Builder | Use menu |

## Direct Command to Agent Mapping

When the user specifies a direct workflow command, map it to two-phase activation:

| Direct Command | Activate Agent | Menu Code |
|---|---|---|
| `/bmad-code-review` | (direct review workflow — no dev-agent activation) | — |
| `/bmad-dev-story` | `/bmad-agent-dev` | `DS` |
| `/bmad-create-prd` | `/bmad-agent-pm` | `CP` |
| `/bmad-validate-prd` | `/bmad-agent-pm` | `VP` |
| `/bmad-create-epics-and-stories` | `/bmad-agent-pm` | `CE` |
| `/bmad-create-architecture` | `/bmad-agent-architect` | Use menu |
| `/bmad-ux` | `/bmad-agent-ux-designer` | Use menu |
