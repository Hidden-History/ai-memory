# Changelog

All notable changes to the Parzival Oversight Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Unified installation script with ai-memory (TECH-DEBT-083)
- CHANGELOG.md automation

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 1.1.0 | 2026-01-27 | Public release, C7 observability, task tracking, ecosystem docs |
| 1.0.0 | 2026-01-18 | Initial release with 7 commands, 2 subagents, 13 templates |

---

## Upgrade Guide

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
