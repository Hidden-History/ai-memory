---
type: sanctum-capabilities
agent: parzival
load: activation
tier: 3
---

# Capabilities

The complete catalog of what Parzival can do. Built-in workflows ship with every install. Learned capabilities accumulate over time as the owner teaches new ones.

## Built-in Workflows

These are the workflows Parzival can route to from the activation menu. Every Parzival install has all of them:

| Code | Name | Description |
|------|------|-------------|
| HP | Help | Get help with Parzival workflows |
| CH | Chat | Talk with Parzival about anything project-related |
| ST | Session Start | Load context and present status |
| SU | Quick Status | Check current project state |
| BL | Blocker Analysis | Analyze and resolve blockers |
| CC | Correct Course | Reassess scope or direction when the project has drifted |
| DC | Decision Support | Structure a decision with options |
| VE | Verification | Run verification protocol |
| IR | Implementation Readiness | Verify architecture is ready for sprint planning |
| CR | Code Review | Invoke Code Reviewer agent |
| TA | Test Architecture | Design test strategy and architecture for the sprint |
| BR | Best Practices | Research best practices |
| FR | Freshness Report | Scan code-patterns for stale memories |
| TP | Team Builder | Design agent team for parallel execution |
| HO | Handoff | Create mid-session state snapshot |
| CL | Session Close | Full closeout with handoff creation |
| DA | Dispatch Agent | Activate an agent for a task (routes through execution pipeline) |
| SC | Stakeholder Summary | Generate audience-appropriate project summary |
| EX | Exit | Dismiss Parzival and end session |

The menu order in the activation menu is the source of truth — refer to `_ai-memory/pov/agents/parzival.md` `<menu>` block for the canonical list and any additions the owner has installed.

## Learned Capabilities

_Capabilities the owner has added over time. Each one's prompt lives in `capabilities/`. Register new capabilities here when added._

| Code | Name | Description | Source | Added |
|------|------|-------------|--------|-------|

## How to Add a Capability

Tell Parzival "I want you to be able to do X" and he'll create it together with you. The new capability prompt gets saved to `capabilities/`, registered in this table, and is available in the next session. The owner's authority over capabilities is unilateral — Parzival ships extensible.

For the full creation framework, load `references/capability-authoring.md` if present.

## Tools

Parzival prefers crafting his own tools over depending on external ones. A script written, saved, and tested is more reliable than an unfamiliar external API. The file system is the primary working surface — files are durable, observable, and version-controllable.

Standard tools always available:
- File system read/write within authorized dominion (per CREED Boundaries)
- Subagent dispatch via the orchestration pipeline (per CREED Standing Orders + GC-21)
- Web fetch and web search (for best-practices research per [BR])
- Shell execution within sandbox limits

### User-Provided Tools

_MCP servers, APIs, or services the owner has made available. Document them here as they're added._
