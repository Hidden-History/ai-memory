# 🎯 Parzival Agent - Installation Guide

<div align="center">

[![Version](https://img.shields.io/badge/version-1.1.0-green.svg)](https://github.com/Hidden-History/pov-oversight-agent)
[![BMAD Compatible](https://img.shields.io/badge/BMAD-6.0.0--alpha.22+-green.svg)](https://bmad-method.org)
[![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Your Technical Project Manager & Quality Gatekeeper for Claude Code**

[Quick Start](#-quick-start) •
[Features](#-what-is-parzival) •
[Installation](#-installation) •
[Usage](#-using-parzival) •
[Updating](#-updating-parzival) •
[Troubleshooting](#-troubleshooting)

</div>

---

## 📋 Table of Contents

- [🎯 What is Parzival?](#-what-is-parzival)
- [✨ Key Features](#-key-features)
- [⚡ Quick Start](#-quick-start)
- [📦 Prerequisites](#-prerequisites)
- [🚀 Installation](#-installation)
  - [New Projects](#new-projects)
  - [Existing Projects](#existing-projects)
- [🔄 Updating Parzival](#-updating-parzival)
- [💡 Using Parzival](#-using-parzival)
- [🛡️ Safety Features](#️-safety-features)
- [🗂️ Project Structure](#️-project-structure)
- [🔧 Configuration](#-configuration)
- [❓ Troubleshooting](#-troubleshooting)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

---

## 🎯 What is Parzival?

**Parzival** is a Technical Project Manager & Quality Gatekeeper agent for BMAD Method and Claude Code. Think of Parzival as your radar operator, map reader, and navigator — providing deep project context and guidance while you stay in command.

### 🎭 Core Philosophy

> **"Parzival recommends. You decide."**

Parzival is **advisory only**. It never executes tasks, makes decisions for you, or modifies code. Instead, it:
- 📊 **Tracks** what you're working on across sessions
- 🧠 **Remembers** context between conversations
- 🚨 **Surfaces** risks and blockers before they escalate
- 🎯 **Guides** decisions with clear tradeoffs and confidence levels
- ✅ **Verifies** implementations against requirements

### 🚨 The Five Core Constraints

Parzival operates under **five non-negotiable rules** that prevent behavioral drift:

1. **❌💻 NEVER Do Implementation Work** - Provides prompts for dev agents, never writes code
2. **✅🔁 ALWAYS Review Until Zero Issues** - Continues review→fix→review cycle until clean
3. **📋🔍 ALWAYS Check Project Files First** - Reads architecture.md, PRD, standards before recommending
4. **🎯❓ NEVER Guess** - Admits uncertainty, cites sources, states confidence levels
5. **👤✓ ALWAYS Let User Decide** - Recommends options, never makes final decisions

**Why This Matters:** Over long conversations, AI agents "forget" their core role and start doing implementation work, skipping reviews, and guessing. Parzival uses a **five-layer constraint enforcement system** to maintain consistent oversight behavior even in 50+ message conversations.

📚 **Learn More:**
- [CONSTRAINTS.md](./pov/agents/parzival/CONSTRAINTS.md) - Complete behavioral rules (394 lines)
- [CONSTRAINT-ENFORCEMENT-SYSTEM.md](./docs/CONSTRAINT-ENFORCEMENT-SYSTEM.md) - Behavioral architecture
- [README.md](./README.md) - Source of truth document

---

## ✨ Key Features

### 📝 Session Management
- **Context Persistence**: Never lose track between sessions
- **Handoff Documents**: Detailed session summaries for continuity
- **Work Index**: Quick context loading (~2K tokens)

### 📊 Project Tracking
- **Task Tracker**: Current sprint and story status
- **Risk Register**: Proactive risk identification
- **Blocker Log**: Track and resolve blockers systematically
- **Technical Debt**: Track and prioritize technical debt

### 🎓 Knowledge Management
- **Best Practices Cache**: Avoid repeated web research
- **Confidence Map**: Know what Parzival knows (and doesn't)
- **Decision Log**: Architectural decisions with rationale
- **Assumption Registry**: Track and validate assumptions

### 🤖 Agent Coordination
- **Code Review**: Adversarial review finding 3-10 issues minimum
- **Implementation Verification**: Evidence-based acceptance criteria validation

> **Best Practices Research**: For database-backed best practices research, use the `/bmad:pov:agents:best-practices-researcher` skill from the [AI Memory Module](https://github.com/Hidden-History/ai-memory).

### 🔒 Data Safety
- **Separation of Concerns**: Code updates never touch user data
- **No Overwrites**: Templates never replace existing files without explicit confirmation
- **Idempotent Scripts**: Safe to run multiple times

---

## ⚡ Quick Start

**Already have BMAD installed?** Three commands to get started:

```bash
# 1. Install Parzival module
./install.sh /path/to/your/project

# 2. Initialize oversight folder (NEW PROJECTS ONLY)
./scripts/init-oversight.sh /path/to/your/project

# 3. Start using Parzival
cd /path/to/your/project
claude
```

Then in Claude Code:
```
/parzival-start
```

---

## 📦 Prerequisites

Before installing Parzival, ensure you have:

### Required
- ✅ **Node.js** v18+ ([Download](https://nodejs.org/))
- ✅ **Claude Code** CLI ([Install Guide](https://docs.anthropic.com/claude/docs/claude-code))
- ✅ **BMAD Method** 6.0.0-alpha.22+ ([Install](https://bmad-method.org))
- ✅ **Anthropic API Key** OR **Claude Pro subscription**

### System Requirements
- 💻 Windows, macOS, or Linux
- 🌐 Internet connection (for initial setup and best practices research)
- ⏱️ ~15-20 minutes for complete installation

### Quick Prerequisites Check

```bash
# Verify Node.js
node --version  # Should show v18.0.0 or higher

# Verify npm
npm --version   # Should show 8.0.0 or higher

# Verify Claude Code
claude --version  # Should show version number

# Verify BMAD (check for _bmad folder in your project)
ls -la _bmad/   # Should show core/ and other modules
```

---

## 🚀 Installation

Parzival uses a **three-script architecture** for maximum safety:

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `install.sh` | Install/update module code | Always (new + existing projects) |
| `init-oversight.sh` | Create oversight folder | NEW projects only |
| `update-templates.sh` | Update oversight templates | EXISTING projects only |

### New Projects

Follow these steps for a fresh Parzival installation:

#### Step 1: Install Prerequisites

<details>
<summary><b>📥 Install Node.js</b></summary>

**Windows:**
1. Download from [nodejs.org](https://nodejs.org/)
2. Run the installer (choose LTS version)
3. Follow installation wizard
4. Restart terminal

**macOS:**
```bash
# Using Homebrew (recommended)
brew install node

# Or download from nodejs.org
```

**Linux (Ubuntu/Debian):**
```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**Verify Installation:**
```bash
node --version
npm --version
```
</details>

<details>
<summary><b>🤖 Install Claude Code</b></summary>

```bash
# Install Claude Code globally
npm install -g @anthropic-ai/claude-code

# Verify installation
claude --version

# First-time setup (follow prompts for API key or Claude Pro login)
claude
```
</details>

<details>
<summary><b>🎯 Install BMAD Method</b></summary>

```bash
# Create your project folder
mkdir ~/projects/my-project
cd ~/projects/my-project

# Install BMAD
npx bmad-method@alpha install

# Select modules when prompted:
# - core (required)
# - bmm (recommended)
# - IDE: claude-code
```
</details>

#### Step 2: Install Parzival Module

```bash
# Navigate to the Parzival module folder
cd /path/to/bmad-parzival-module

# Run the installer
./install.sh /path/to/your/project
```

**What this does:**
- ✅ Copies module files to `pov/`
- ✅ Installs slash commands to `.claude/commands/`
- ✅ Installs skills to `.claude/skills/`
- ✅ Updates BMAD manifests
- ✅ Copies customization template

**Expected Output:**
```
========================================
  PARZIVAL MODULE INSTALLER v1.1.0
========================================

[1/6] Copying POV module files...       ✓ Done
[2/6] Copying slash commands...         ✓ Done
[3/6] Copying skills...                 ✓ Done
[4/6] Updating BMAD manifest...         ✓ Added 'pov' to manifest
[5/6] Updating agent manifest...        ✓ Added parzival to agent manifest
[6/6] Copying customization template... ✓ Done

========================================
  INSTALLATION COMPLETE!
========================================
```

#### Step 3: Initialize Oversight Folder

```bash
# Run the oversight initializer
./scripts/init-oversight.sh /path/to/your/project
```

**What this does:**
- ✅ Creates `oversight/` folder structure
- ✅ Copies 22 template files
- ✅ Creates 20 directories for tracking, decisions, knowledge, etc.
- ✅ Never overwrites existing files

**Expected Output:**
```
========================================
  PARZIVAL OVERSIGHT INITIALIZER v1.0.0
========================================

[1/4] Copying template files...    ✓ Copied 22 new files
[2/4] Creating directory structure... ✓ Done
[3/4] Creating .gitkeep files...   ✓ Done
[4/4] Verifying structure...       ✓ Created 20 directories and 26 files

========================================
  INITIALIZATION COMPLETE!
========================================
```

#### Step 4: Configure Parzival

Edit the configuration file with your preferences:

```bash
# Open config file
nano pov/config.yaml

# Update these values:
project_name: my-awesome-project
user_name: Your Name
communication_language: English
```

#### Step 5: Test Your Installation

```bash
# Start Claude Code
cd /path/to/your/project
claude
```

In Claude Code, run:
```
/parzival-start
```

You should see Parzival introduce itself and scan for context! 🎉

### Existing Projects

If you already have Parzival installed and want to update:

#### Step 1: Update Module Code

```bash
cd /path/to/bmad-parzival-module
./install.sh /path/to/your/project
```

This safely updates all module code without touching your oversight data.

#### Step 2: Update Templates (Optional)

```bash
# Run the interactive template updater
./scripts/update-templates.sh /path/to/your/project
```

**What this does:**
- 🔍 Scans for changed templates
- 📋 Shows you a diff for each changed file
- 🤔 Lets you decide: keep, update, or skip

**Interactive Options:**
```
[d] Show diff           - View changes between versions
[k] Keep current        - Skip this file (preserve your version)
[u] Use new template    - Replace with new version
[s] Skip all remaining  - Stop prompting, keep all remaining files
```

**Example Session:**
```
========================================
[CHANGED] README.md
========================================

Options:
  [d] Show diff
  [k] Keep current version (skip update)
  [u] Use new template (replace current)
  [s] Skip all remaining (stop prompting)

Choice [d/k/u/s]: d

--- Current version
+++ New template
@@ -15,3 +15,7 @@

 **Parzival recommends. You decide.**
+
+## New Feature: Standards Sharding
+Standards are now split into topic-specific files...

Choice [d/k/u/s]: u
  ✓ Updated to new template
```

---

## 🔄 Updating Parzival

### Update Workflow

```bash
# 1. Update module code (safe - never touches your data)
./install.sh /path/to/your/project

# 2. Optionally update templates (interactive - you control what changes)
./scripts/update-templates.sh /path/to/your/project
```

### What Gets Updated

| Component | Update Method | Your Data Safe? |
|-----------|---------------|-----------------|
| Module code (`pov/`) | Overwritten | N/A (no user data) |
| Commands (`.claude/commands/`) | Overwritten | N/A (no user data) |
| Skills (`.claude/skills/`) | Overwritten | N/A (no user data) |
| Config (`pov/config.yaml`) | Overwritten | ⚠️ Backup first |
| Oversight data (`oversight/`) | **NEVER touched by install.sh** | ✅ Always safe |
| Templates (via `update-templates.sh`) | Interactive - you choose | ✅ You control |

### Pre-Update Checklist

Before updating, backup these files if you've customized them:

```bash
# Backup your config
cp pov/config.yaml pov/config.yaml.backup

# Backup any custom templates (if you've modified them)
cp oversight/README.md oversight/README.md.backup

# Your oversight data is ALWAYS safe - install.sh never touches it!
```

---

## 💡 Using Parzival

### Available Commands

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `/parzival-start` | 🚀 Start session | Beginning of work session |
| `/parzival-status` | 📊 Quick status | Check current state |
| `/parzival-closeout` | 🏁 End session | End of work session |
| `/parzival-handoff` | 💾 Mid-session save | Taking a break |
| `/parzival-blocker` | 🚧 Analyze blocker | Stuck on something |
| `/parzival-decision` | 🤔 Decision support | Need to choose between options |
| `/parzival-verify` | ✅ Run checklist | Quality verification |

### Typical Workflow

```bash
# Morning - Start your session
/parzival-start

# Parzival loads previous context and shows:
# - Recent decisions
# - Open tasks
# - Known risks
# - Session continuity

# During work - hit a blocker?
/parzival-blocker
# Parzival analyzes and presents resolution options

# During work - need to make a decision?
/parzival-decision
# Parzival presents options with tradeoffs

# Taking a break?
/parzival-handoff
# Creates a mid-session snapshot

# End of day
/parzival-closeout
# Creates comprehensive handoff for next session
```

### Confidence Levels

Every Parzival recommendation includes a confidence level:

| Level | Meaning | Example |
|-------|---------|---------|
| **Verified** ✅ | Directly confirmed from source | "I read the file at line 42" |
| **Informed** 📚 | Based on reliable information | "According to the architecture doc..." |
| **Inferred** 🔍 | Logical deduction from patterns | "Based on similar implementations..." |
| **Uncertain** ❓ | Limited information available | "I don't have enough context to..." |
| **Unknown** ❌ | No basis for assessment | "I haven't seen this before" |

### Agent Coordination

Parzival coordinates specialized agents for specific tasks:

#### Code Review Agent
```
/code-review
```
- Adversarial review (finds 3-10 issues minimum)
- Checks quality, security, architecture compliance
- Severity-ranked issues with file:line references

#### Verification Agent
```
/verify-implementation
```
- Validates against acceptance criteria
- Evidence-based pass/fail per criterion
- Runs automated tests if available

#### Best Practices Researcher
```
/best-practices
```
- Researches current (2024-2026) standards
- Caches findings to avoid repeat research
- Sources citations for recommendations

---

## 🛡️ Safety Features

### 🔐 Data Protection

Parzival's three-script architecture guarantees your data is never accidentally lost:

```
┌─────────────────────────────────────────────────────────────┐
│  install.sh                                                  │
│  - Updates module code only                                 │
│  - NEVER touches oversight/ folder                          │
│  - Safe to run on existing installations                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  init-oversight.sh                                           │
│  - Creates oversight/ structure                             │
│  - NEVER overwrites existing files                          │
│  - Uses no-clobber copy logic                               │
│  - Warns if oversight/ already exists                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  update-templates.sh                                         │
│  - Interactive, per-file decisions                          │
│  - Shows diff before any change                             │
│  - Requires explicit confirmation                           │
│  - Option to skip all remaining files                       │
└─────────────────────────────────────────────────────────────┘
```

### ✅ Idempotency

All scripts are safe to run multiple times:

- **install.sh**: Detects existing manifest entries, skips duplicates
- **init-oversight.sh**: Skips files that already exist
- **update-templates.sh**: Only prompts for changed files

### 🚨 Safety Guarantees

| Scenario | What Happens | Your Data |
|----------|--------------|-----------|
| Run `install.sh` on existing installation | Module code updated | ✅ Preserved |
| Run `init-oversight.sh` on existing oversight/ | Warning shown, files skipped | ✅ Preserved |
| Run `update-templates.sh` | Interactive prompts per file | ✅ You control |
| Accidental re-run of any script | Safe behavior, no data loss | ✅ Preserved |
| `install.sh` fails mid-execution | Partial update, no data touched | ✅ Preserved |

---

## 🗂️ Project Structure

After installation, your project will have this structure:

```
my-project/
├── _bmad/                          # BMAD Method structure
│   ├── _config/
│   │   ├── manifest.yaml           # Module registry
│   │   ├── agent-manifest.csv      # Agent registry
│   │   └── agents/
│   │       └── pov-parzival.customize.yaml  # Customization template
│   ├── core/                       # BMAD core module
│   ├── bmm/                        # Business Method Module (optional)
│   └── pov/                        # 🎯 Parzival Module
│       ├── config.yaml             # Parzival configuration
│       ├── agents/
│       │   └── parzival.md         # Main agent definition
│       ├── includes/               # Reusable agent components
│       ├── templates/              # Oversight templates
│       │   └── oversight/          # Template files
│       └── BMAD-AGENT-INDEX.md     # Complete agent reference
│
├── .claude/                        # Claude Code integration
│   ├── commands/
│   │   └── pov/
│   │       ├── commands/           # 7 slash commands
│   │       │   ├── parzival-start.md
│   │       │   ├── parzival-status.md
│   │       │   ├── parzival-closeout.md
│   │       │   ├── parzival-handoff.md
│   │       │   ├── parzival-blocker.md
│   │       │   ├── parzival-decision.md
│   │       │   └── parzival-verify.md
│   │       └── agents/             # 4 agent invocations
│   │           ├── parzival.md
│   │           ├── code-reviewer.md
│   │           ├── verify-implementation.md
│   │           └── best-practices-researcher.md
│   └── skills/
│       └── parzival-oversight/     # Skill definitions
│           ├── SKILL.md
│           ├── CONSTRAINTS.md
│           ├── PROCEDURES.md
│           └── CODEBASE-MODEL.md
│
└── oversight/                      # 📊 Your Session Data (NEVER overwritten)
    ├── README.md                   # Oversight system guide
    ├── SESSION_WORK_INDEX.md       # Quick context (~2K tokens)
    ├── PARZIVAL_AGENT_IMPROVEMENTS.md  # Agent behavior notes
    ├── PROJECT_IMPROVEMENTS.md     # Project lessons learned
    ├── PROJECT_STANDARDS.yaml      # Standards index
    │
    ├── tracking/                   # 📋 Project Tracking
    │   ├── task-tracker.md         # Current sprint/tasks
    │   ├── risk-register.md        # Risk identification
    │   ├── blockers-log.md         # Active blockers
    │   ├── dependencies.md         # External dependencies
    │   ├── scope-change-log.md     # Scope changes
    │   └── technical-debt.md       # Tech debt tracking
    │
    ├── decisions/                  # 🎯 Decision Log
    │   └── .gitkeep                # (Populated during sessions)
    │
    ├── session-logs/               # 📝 Session History
    │   └── .gitkeep                # (Handoffs stored here)
    │
    ├── knowledge/                  # 🧠 Knowledge Base
    │   ├── assumption-registry.md  # Tracked assumptions
    │   ├── confidence-map.md       # What Parzival knows
    │   └── best-practices/         # Cached research
    │       ├── index.md
    │       └── _TEMPLATE.md
    │
    ├── learning/                   # 📚 Learning & Patterns
    │   └── failure-pattern-library.md
    │
    ├── research/                   # 🔬 Research
    │   └── best-practices-log.md
    │
    ├── standards/                  # 📐 Standards (Sharded)
    │   ├── _global/                # Global standards
    │   │   └── _TEMPLATE.md
    │   └── _project/               # Project-specific standards
    │       └── _TEMPLATE.md
    │
    ├── verification/               # ✅ Quality Checklists
    │   └── checklists/
    │       ├── code-review.md
    │       ├── production-ready.md
    │       └── story-complete.md
    │
    ├── archive/                    # 🗄️ Archived items
    ├── audits/                     # 📊 Quality audits
    ├── plans/                      # 📋 Implementation plans
    ├── prompts/                    # 🤖 Agent prompts
    ├── specs/                      # 📄 Technical specifications
    ├── tasks/                      # ✅ Task breakdowns
    └── uncertainty/                # ❓ Open questions
```

### Key Directories Explained

| Directory | Purpose | Updated By |
|-----------|---------|-----------|
| `pov/` | Module code | `install.sh` |
| `.claude/commands/` | Slash commands | `install.sh` |
| `.claude/skills/` | Skills | `install.sh` |
| `oversight/` | **Your session data** | **You + Parzival** |
| `oversight/session-logs/` | Session handoffs | Parzival (auto) |
| `oversight/tracking/` | Project tracking | You + Parzival |
| `oversight/decisions/` | Decision records | Parzival (when you decide) |
| `oversight/knowledge/` | Knowledge accumulation | Parzival + agents |

---

## 🔧 Configuration

### Basic Configuration

Edit `pov/config.yaml`:

```yaml
# Project settings
project_name: my-awesome-project    # Your project name
user_name: Your Name                # Your name
communication_language: English     # Preferred language

# Parzival settings
oversight_folder: oversight         # Oversight folder location (default: ./oversight)

# Agent behavior (advanced - see documentation)
confidence_levels:
  - verified
  - informed
  - inferred
  - uncertain
  - unknown

escalation_levels:
  - clarifying_question
  - blocking_issue
  - architectural_decision
```

### Advanced Customization

Create custom agent behavior by editing:
```
_bmad/_config/agents/pov-parzival.customize.yaml
```

This allows you to override:
- Agent persona
- Communication style
- Principles
- Critical actions
- Custom menu items

**Example:**
```yaml
agent:
  metadata:
    name: "Parzival"

persona:
  communication_style: "More concise, emoji-heavy responses"

principles:
  - "Always use bullet points"
  - "Prefer tables over prose"

# Add custom prompts, actions, etc.
```

---

## ❓ Troubleshooting

### Common Issues

<details>
<summary><b>🚫 "Command not found" when running `/parzival-start`</b></summary>

**Cause:** Slash commands not installed correctly.

**Fix:**
```bash
# Verify commands exist
ls .claude/commands/pov/commands/

# If missing, re-run installer
./install.sh /path/to/your/project

# Restart Claude Code
exit  # Exit Claude
claude  # Restart
```
</details>

<details>
<summary><b>🔄 Parzival doesn't remember previous sessions</b></summary>

**Cause:** Oversight folder not initialized or `SESSION_WORK_INDEX.md` missing.

**Fix:**
```bash
# Check if oversight folder exists
ls oversight/

# If missing, run initializer
./scripts/init-oversight.sh /path/to/your/project

# If exists but empty
cp -r pov/templates/oversight/* oversight/
```
</details>

<details>
<summary><b>⚠️ "Module 'pov' not found" error</b></summary>

**Cause:** Module not registered in BMAD manifest.

**Fix:**
```bash
# Open manifest
nano _bmad/_config/manifest.yaml

# Add 'pov' to modules list:
modules:
  - core
  - bmm
  - pov    # Add this line

# Save and restart Claude Code
```
</details>

<details>
<summary><b>🐧 "Permission denied" on Linux/Mac</b></summary>

**Cause:** Script doesn't have execute permission.

**Fix:**
```bash
chmod +x install.sh
chmod +x scripts/init-oversight.sh
chmod +x scripts/update-templates.sh

# Then run the script
./install.sh /path/to/your/project
```
</details>

<details>
<summary><b>📁 "oversight/" folder exists but init-oversight.sh shows warning</b></summary>

**Cause:** This is expected behavior - init-oversight.sh is for NEW projects only.

**Fix:**
```bash
# For existing projects, use the template updater instead:
./scripts/update-templates.sh /path/to/your/project

# Or skip if you don't want to update templates
```
</details>

<details>
<summary><b>🔍 Best practices research not caching</b></summary>

**Cause:** `oversight/knowledge/best-practices/` folder missing.

**Fix:**
```bash
# Create the folder
mkdir -p oversight/knowledge/best-practices/

# Copy the template
cp pov/templates/oversight/knowledge/best-practices/_TEMPLATE.md \
   oversight/knowledge/best-practices/

# Copy the index
cp pov/templates/oversight/knowledge/best-practices/index.md \
   oversight/knowledge/best-practices/
```
</details>

<details>
<summary><b>🎯 BMAD commands work but Parzival doesn't load</b></summary>

**Cause:** Agent not registered in agent manifest.

**Fix:**
```bash
# Check agent manifest
cat _bmad/_config/agent-manifest.csv | grep parzival

# If missing, add this line to agent-manifest.csv:
"parzival","Parzival","Technical PM & Quality Gatekeeper","🎯","Technical Project Manager + Quality Gatekeeper","Parzival is the radar, map reader, and navigator. Deep project understanding enables good recommendations - not task execution. Maintains oversight documentation, tracks risks and blockers, provides well-crafted prompts for agents, and validates completed work through explicit checklists.","Advisory and supportive. Uses confidence levels (Verified/Informed/Inferred/Uncertain/Unknown) with every recommendation. Asks clarifying questions rather than assuming. Surfaces risks and scope changes proactively.","- Parzival recommends. The user decides. - Ask when uncertain, never fabricate. - Surface scope changes when detected. - Write for Future Parzival who knows nothing about this session. - Verification is concrete, not vibes-based.","pov","pov/agents/parzival.md"
```
</details>

### Still Having Problems?

1. **Check file locations** - Ensure all files are in exact paths shown in [Project Structure](#️-project-structure)
2. **Restart Claude Code** - Exit and restart your terminal, then run `claude` again
3. **Check for typos** - YAML files are sensitive to indentation and formatting
4. **Review logs** - Check `.claude/logs/` for error messages
5. **Ask for help** - Open an issue on GitHub with:
   - Your OS and version
   - Node.js and Claude Code versions
   - Exact error message
   - Steps to reproduce

---

## 🤝 Contributing

We welcome contributions! Here's how you can help:

### Reporting Bugs

Found a bug? Please open an issue with:
- **Clear title** - "install.sh fails on Windows with path containing spaces"
- **Steps to reproduce** - Exact commands you ran
- **Expected behavior** - What should have happened
- **Actual behavior** - What actually happened
- **Environment** - OS, Node version, BMAD version
- **Logs** - Any error messages

### Suggesting Features

Have an idea? Open an issue with:
- **Use case** - What problem does this solve?
- **Proposed solution** - How would it work?
- **Alternatives** - What other approaches did you consider?

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit with clear messages (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

**PR Guidelines:**
- ✅ Include tests for new features
- ✅ Update documentation
- ✅ Follow existing code style
- ✅ Keep PRs focused (one feature/fix per PR)
- ✅ Describe what changed and why

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **BMAD Method Team** - For the amazing framework
- **Anthropic** - For Claude and Claude Code
- **Contributors** - Everyone who has helped improve Parzival

---

## 📚 Additional Resources

### Official Documentation
- **[README.md](./README.md)** - Complete source of truth (identity, constraints, duties, architecture)
- **[CONSTRAINTS.md](./pov/agents/parzival/CONSTRAINTS.md)** - Core behavioral rules (394 lines)
- **[CONSTRAINT-ENFORCEMENT-SYSTEM.md](./docs/CONSTRAINT-ENFORCEMENT-SYSTEM.md)** - Five-layer behavioral architecture
- **[PROCEDURES.md](./pov/procedures/PROCEDURES.md)** - Step-by-step operational procedures (878 lines)

### External Resources
- [BMAD Method Documentation](https://bmad-method.org/docs)
- [Claude Code Documentation](https://docs.anthropic.com/claude/docs/claude-code)

---

## 🎯 Quick Reference Card

```
╔════════════════════════════════════════════════════════════════════╗
║                   PARZIVAL QUICK REFERENCE                         ║
╠════════════════════════════════════════════════════════════════════╣
║  COMMANDS                                                          ║
║  ─────────────────────────────────────────────────────────────    ║
║  /parzival-start        🚀 Start session                          ║
║  /parzival-status       📊 Check status                           ║
║  /parzival-closeout     🏁 End session                            ║
║  /parzival-handoff      💾 Mid-session save                       ║
║  /parzival-blocker      🚧 Analyze blocker                        ║
║  /parzival-decision     🤔 Decision support                       ║
║  /parzival-verify       ✅ Run verification                       ║
║                                                                    ║
║  AGENTS                                                            ║
║  ─────────────────────────────────────────────────────────────    ║
║  /code-review           🔍 Adversarial code review                ║
║  /verify-implementation ✓  Verify acceptance criteria             ║
║  /best-practices        📚 Research current standards             ║
║                                                                    ║
║  CONFIDENCE LEVELS                                                 ║
║  ─────────────────────────────────────────────────────────────    ║
║  Verified ✅ > Informed 📚 > Inferred 🔍 > Uncertain ❓ > Unknown ❌ ║
║                                                                    ║
║  CORE PRINCIPLE                                                    ║
║  ─────────────────────────────────────────────────────────────    ║
║  "Parzival recommends. You decide."                               ║
╚════════════════════════════════════════════════════════════════════╝
```

---

<div align="center">

**Made with ❤️ by the BMAD Community**

[⬆ Back to Top](#-parzival-agent---installation-guide)

</div>
