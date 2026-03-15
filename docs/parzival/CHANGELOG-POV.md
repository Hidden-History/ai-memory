> **Note**: This is preserved reference documentation from the standalone POV Oversight Agent repository. Paths and commands shown may reference the original standalone structure. For current ai-memory installation, see [INSTALL.md](../INSTALL.md).

# Changelog

All notable changes to the Parzival Oversight Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-03-15

### Added

- **Shim architecture** -- Skills live in `_ai-memory/pov/skills/` with thin shims in `.claude/skills/` that load the full definitions on demand (DEC-114)
- **Dispatch skills** -- Five new skills for the execution pipeline (DEC-115):
  - `aim-agent-dispatch` -- Generic agent instruction preparation and activation (Layer 3a)
  - `aim-agent-lifecycle` -- Shared agent lifecycle management (send, monitor, review, accept/loop, shutdown, summary)
  - `aim-bmad-dispatch` -- BMAD agent selection, activation commands, and persona loading (Layer 3b)
  - `aim-model-dispatch` -- Model selection based on task complexity and role
  - `aim-parzival-team-builder` -- Design agent team structure for parallel execution
- **GC-19: Spawn Agents as Teammates** -- All agents must be spawned with `team_name` via Claude Code teams, never as standalone subagents (DEC-118)
- **GC-20: No Instruction in BMAD Activation Message** -- Activation command and instruction must be sent as separate messages (DEC-119)
- **GC-13 through GC-15** -- Best practices research before acting on new tech (GC-13), similar issue detection before creating bug reports (GC-14), template usage for oversight documents (GC-15) (DEC-117)
- **Menu items** -- HP (Help), CH (Chat), BR (Best Practices), FR (Freshness Report), TP (Team Builder), DA (Dispatch Agent) added to Parzival menu (DEC-116)
- **Config field** -- Module paths (`constraints_path`, `workflows_path`, `oversight_path`, `pov_output_folder`) consolidated in config.yaml
- **Dispatch quick-reference** -- Inline fast-path reference in parzival.md for single-agent dispatches without loading all 5 skill files

### Changed

- **Parzival identity** -- Now "boss of all worker agents" who manages agents via Claude Code teams; delegates all implementation through structured execution pipeline (DEC-114)
- **GC-04 redefined** -- Was "Always Let User Decide", now "User Manages Parzival Only -- Parzival Manages All Agents" -- user no longer runs agents directly (DEC-120)
- **GC-09 scope** -- "Review Agent Output" (was "Review External Input") -- focused on agent output review during dispatch cycles
- **GC-11 scope** -- "Give Agents Precise Instructions" (was "Communicate With Precision") -- focused on instruction quality for dispatched agents
- **GC-13 scope** -- "Before Dispatching" (was "Before Acting") -- research requirement before dispatching agents on unfamiliar tech
- **Menu reduced to 15 items** -- HP, CH, ST, SU, BL, DC, VE, CR, BR, FR, TP, HO, CL, DA, EX (VI removed)
- **Constraint count** -- 17 global constraints (GC-01 through GC-15 + GC-19 + GC-20), up from 12 (GC-01 through GC-12)
- **Self-check expanded** -- Now covers all 17 constraints across Layer 1 (always active) and Layer 3 (during agent work)

### Removed

- **teams/ directory** -- Team management moved to Claude Code native teams (DEC-118)
- **team-prompt workflow** -- Replaced by aim-parzival-team-builder skill
- **instruction.template** -- Replaced by agent-instruction.template.md in aim-agent-dispatch skill
- **PROCEDURES.md** -- Procedures decomposed into workflow step files
- **CONSTRAINTS.md** (agents/parzival/) -- Replaced by `constraints/global/constraints.md` + individual GC-*.md files
- **VI (Verify Implementation) menu item** -- Consolidated into VE (Verification) workflow

---

## [1.1.0] - 2026-01-27

### Added

- **Public release** of Parzival Oversight Agent to [pov-oversight-agent](https://github.com/Hidden-History/pov-oversight-agent)
- **C7: Observability Requirements** - New constraint for metrics/logging/Grafana at script creation
- **Task Tracking Integration** - TaskCreate/TaskUpdate/TaskList for complex operations (3+ steps)
- **Ecosystem Documentation** - Cross-references to [AI Memory Module](https://github.com/Hidden-History/ai-memory)
- **Banner Image** - Professional banner for README

### Changed

- **Three-script architecture** for data safety (install.sh, init-oversight.sh, update-templates.sh)
- **Five-layer constraint system** for behavioral drift prevention
- **CONSTRAINTS.md rewrite** (390 lines) with self-check system
- **Critical constraints** added to parzival.md (lines 46-70)

### Fixed

- Arithmetic syntax for `set -e` compatibility in scripts
- EOF handling in update-templates.sh
- Removed oversight init from install.sh (data safety - prevents overwrites)
- Placeholder URLs replaced with actual repository links

---

## [1.0.0] - 2026-01-18

### Added

- **Initial release** of Parzival Oversight Agent
- **Core Agent** (`parzival.md`) - Technical PM & Quality Gatekeeper persona
- **7 Commands**:
  - `/parzival-start` - Initialize session with context loading
  - `/parzival-closeout` - Create comprehensive handoff documentation
  - `/parzival-status` - Quick project status check
  - `/parzival-handoff` - Mid-session state snapshot
  - `/parzival-blocker` - Analyze and resolve blockers
  - `/parzival-decision` - Decision support with options analysis
  - `/parzival-verify` - Run verification checklists
- **2 Subagents**:
  - `code-reviewer.md` - Adversarial code review (3-10 issues per file)
  - `verify-implementation.md` - Story/acceptance criteria verification
- **6 Operational Constraints** (C1-C6):
  - C1: Mandatory Bug Tracking Protocol
  - C2: Similar Issue Detection
  - C3: Fix Verification Protocol
  - C4: Complex Bug Unified Spec Requirement
  - C5: Template Usage
  - C6: Sharding Compliance
- **5 Behavioral Constraints** (Core Rules):
  - Never do implementation work
  - Always review until zero issues
  - Always check project files first
  - Never guess - admit uncertainty
  - Always let user decide
- **13 Oversight Templates**:
  - Bug tracking (BUG_TEMPLATE.md, ROOT_CAUSE_TEMPLATE.md)
  - Decisions (DECISION_TEMPLATE.md)
  - Specifications (SPEC_TEMPLATE.md, FIX_SPEC_TEMPLATE.md)
  - Session management (SESSION_SNAPSHOT_TEMPLATE.md, SESSION_WORK_INDEX.md)
  - Tracking (task-tracker.md, blockers-log.md, risk-register.md, technical-debt.md)
  - Validation (VALIDATION_TEMPLATE.md)
  - Audits (AUDIT_TEMPLATE.md)
- **Skill Definition** (`SKILL.md`) - Claude Code skill integration
- **Procedures** (`PROCEDURES.md`) - Step-by-step execution procedures
- **Codebase Model** (`CODEBASE-MODEL.md`) - System architecture understanding
- **Confidence Levels** - Verified/Informed/Inferred/Uncertain/Unknown
- **Complexity Assessments** - Straightforward/Moderate/Significant/Complex
- **Escalation Protocol** - Critical/High/Medium/Low severity handling
- **Documentation**:
  - README.md with installation guide
  - INSTALL-GUIDE.md with detailed setup
  - SHARDING_STRATEGY.md for document management
  - CONSTRAINT-ENFORCEMENT-SYSTEM.md

### Changed

- N/A (initial release)

### Deprecated

- N/A (initial release)

### Removed

- N/A (initial release)

### Fixed

- N/A (initial release)

### Security

- N/A (initial release)

---

## [Unreleased]

### Planned

- Monitoring/metrics integration (TECH-DEBT-084)
- CHANGELOG.md automation

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 2.1.0 | 2026-03-15 | Shim architecture, dispatch skills, GC-19/GC-20, 15-item menu, agent management identity |
| 1.1.0 | 2026-01-27 | Public release, C7 observability, task tracking, ecosystem docs |
| 1.0.0 | 2026-01-18 | Initial release with 7 commands, 2 subagents, 13 templates |

---

## Upgrade Guide

### From 1.1.0 to 2.1.0

1. Skills now live in `_ai-memory/pov/skills/` with thin shims in `.claude/skills/`
2. Constraints moved from `pov/agents/parzival/CONSTRAINTS.md` to `_ai-memory/pov/constraints/global/constraints.md` + individual GC-*.md files
3. PROCEDURES.md removed -- procedures are now decomposed into workflow step files in `_ai-memory/pov/workflows/`
4. teams/ directory removed -- agent teams managed via Claude Code native teams (GC-19)
5. instruction.template removed -- replaced by `agent-instruction.template.md` in aim-agent-dispatch skill
6. Menu item VI removed, DA (Dispatch Agent) and TP (Team Builder) added

### From 1.0.0 to 1.1.0

1. Run `./install.sh /path/to/project` to update module code
2. Optionally run `./scripts/update-templates.sh /path/to/project` for new templates
3. Your existing `oversight/` directory is preserved automatically

### From Development Version

If you were using the development version from `bmad-memory-module` private repo:

1. Remove old files from your project's `.claude/` directory
2. Follow the [INSTALL-GUIDE.md](INSTALL-GUIDE.md) for fresh installation
3. Your existing `oversight/` directory is compatible - no migration needed

---

## Links

- [GitHub Repository](https://github.com/Hidden-History/pov-oversight-agent)
- [AI Memory Module](https://github.com/Hidden-History/ai-memory) - Companion module for persistent semantic memory
- [Issue Tracker](https://github.com/Hidden-History/pov-oversight-agent/issues)
