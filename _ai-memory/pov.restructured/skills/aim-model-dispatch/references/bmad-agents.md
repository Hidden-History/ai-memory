# BMAD Agent Reference

## Agent Command Reference

| Agent Type | Activation Command |
|---|---|
| Developer | `/bmad-agent-bmm-dev` |
| PM (Product Manager) | `/bmad-agent-bmm-pm` |
| Analyst | `/bmad-agent-bmm-analyst` |
| Architect | `/bmad-agent-bmm-architect` |
| Scrum Master | `/bmad-agent-bmm-sm` |
| QA Engineer | `/bmad-agent-bmm-qa` |
| UX Designer | `/bmad-agent-bmm-ux-designer` |
| Tech Writer | `/bmad-agent-bmm-tech-writer` |
| Quick Flow Solo Dev | `/bmad-agent-bmm-quick-flow-solo-dev` |
| BMAD Master | `/bmad-agent-bmad-master` |
| Agent Builder | `/bmad-agent-bmb-agent-builder` |
| Module Builder | `/bmad-agent-bmb-module-builder` |
| Workflow Builder | `/bmad-agent-bmb-workflow-builder` |
| Brainstorming Coach | `/bmad-agent-cis-brainstorming-coach` |
| Creative Problem Solver | `/bmad-agent-cis-creative-problem-solver` |
| Design Thinking Coach | `/bmad-agent-cis-design-thinking-coach` |
| Innovation Strategist | `/bmad-agent-cis-innovation-strategist` |
| Presentation Master | `/bmad-agent-cis-presentation-master` |
| Storyteller | `/bmad-agent-cis-storyteller` |
| Test Architect (TEA) | `/bmad-agent-tea-tea` |

## Task-to-Agent Selection Guide

When the task description does not specify an agent:

| Task Type | Agent | Menu Code |
|---|---|---|
| Research / analyze codebase | Analyst | Use menu |
| Create or update PRD | PM | `CP` |
| Validate a PRD | PM | `VP` |
| Break down features into stories | PM | `CE` |
| Design system architecture | Architect | Use menu |
| Sprint planning | SM | Use menu |
| Write code / implement a story | DEV | `DS` |
| Review implemented code | DEV | `CR` |
| Design user flows | UX Designer | Use menu |
| Write or review documentation | Tech Writer | `WD` |
| Validate documentation | Tech Writer | `VD` |
| Write and run tests | QA | Use menu |
| Build new BMAD agents | Agent Builder | Use menu |
| Build new BMAD modules | Module Builder | Use menu |
| Build new BMAD workflows | Workflow Builder | Use menu |

## Direct Command to Agent Mapping

When the user specifies a direct workflow command, map it to two-phase activation:

| Direct Command | Activate Agent | Menu Code |
|---|---|---|
| `/bmad-bmm-code-review` | `/bmad-agent-bmm-dev` | `CR` |
| `/bmad-bmm-dev-story` | `/bmad-agent-bmm-dev` | `DS` |
| `/bmad-bmm-create-prd` | `/bmad-agent-bmm-pm` | `CP` |
| `/bmad-bmm-validate-prd` | `/bmad-agent-bmm-pm` | `VP` |
| `/bmad-bmm-create-epics-and-stories` | `/bmad-agent-bmm-pm` | `CE` |
| `/bmad-bmm-create-architecture` | `/bmad-agent-bmm-architect` | Use menu |
| `/bmad-bmm-sprint-planning` | `/bmad-agent-bmm-sm` | Use menu |
| `/bmad-bmm-create-ux-design` | `/bmad-agent-bmm-ux-designer` | Use menu |
