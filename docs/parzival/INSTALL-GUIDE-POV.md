> **Note**: This is preserved reference documentation from the standalone POV Oversight Agent repository. Paths and commands shown may reference the original standalone structure. For current ai-memory installation, see [README-INSTALL.md](../../README-INSTALL.md).

# 🎯 Parzival Agent - Installation Guide

<div align="center">

[![Version](https://img.shields.io/badge/version-2.1.0-green.svg)](https://github.com/Hidden-History/pov-oversight-agent)
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
- [CONSTRAINT-ENFORCEMENT-SYSTEM.md](./CONSTRAINT-ENFORCEMENT-SYSTEM.md) - Behavioral constraint architecture
- [constraints.md](../../_ai-memory/pov/constraints/global/constraints.md) - Global constraint index (GC-01 through GC-20)
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

**Already have the AI Memory system?** Two steps to get started:

```bash
# 1. Install Parzival module
./scripts/install.sh

# 2. Start using Parzival
claude
```

Then in Claude Code:
```
/pov:parzival-start
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

# Verify AI Memory system (check for _ai-memory folder in your project)
ls -la _ai-memory/   # Should show core/, pov/, and other modules
```

---

## 🚀 Installation

Parzival is installed via the unified **`scripts/install.sh`** installer, which handles all setup in a single run:

| Function | Purpose |
|----------|---------|
| Core install | Copies module files, commands, agents, skills |
| `generate_parzival_skill_shims()` | Creates thin shim files in `.claude/skills/` pointing to `_ai-memory/pov/skills/` |
| `sync_parzival_config_yaml()` | Writes `PARZIVAL_USER_NAME` from `.env` into `pov/config.yaml` |
| *(inline v2.1 cleanup)* | Removes old 2.0 files that were moved or renamed in 2.1 (inline in installer, not a named function) |
| `setup_model_dispatch()` | Optional prompt for multi-provider model dispatch (system-level: `~/.config/`, `~/.local/bin/`) |

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
- Copies module files to `_ai-memory/pov/`
- Installs slash commands to `.claude/commands/pov/`
- Installs agent definition to `.claude/agents/pov/`
- Generates thin skill shims in `.claude/skills/` that point to `_ai-memory/pov/skills/`
- Syncs `PARZIVAL_USER_NAME` from `.env` into `pov/config.yaml`
- Cleans up stale 2.0 files inline (moved templates, deleted workflows, renamed constraints)
- Optionally configures multi-provider model dispatch

#### Step 3: Configure Parzival

The installer sets `user_name` automatically from the `PARZIVAL_USER_NAME` environment variable in `.env`. To change it manually:

```bash
# Open config file
nano _ai-memory/pov/config.yaml

# Key fields:
user_name: Your Name                # Set automatically by installer from .env
communication_language: English     # Preferred language
```

#### Step 4: Test Your Installation

```bash
# Start Claude Code
cd /path/to/your/project
claude
```

In Claude Code, run:
```
/pov:parzival-start
```

You should see Parzival introduce itself and scan for context! 🎉

### Existing Projects

If you already have Parzival installed and want to update:

#### Step 1: Update Module Code

```bash
./scripts/install.sh
```

This safely updates all module code, regenerates skill shims, cleans up stale 2.0 files, and syncs config — without touching your oversight data.

---

## 🔄 Updating Parzival

### Update Workflow

```bash
# Update module code (safe - never touches your data)
./scripts/install.sh
```

### What Gets Updated

| Component | Update Method | Your Data Safe? |
|-----------|---------------|-----------------|
| Module code (`_ai-memory/pov/`) | Overwritten | N/A (no user data) |
| Commands (`.claude/commands/pov/`) | Overwritten | N/A (no user data) |
| Agent def (`.claude/agents/pov/`) | Overwritten | N/A (no user data) |
| Skill shims (`.claude/skills/aim-*`) | Regenerated from `_ai-memory/pov/skills/` | N/A (auto-generated) |
| Config (`_ai-memory/pov/config.yaml`) | `user_name` synced from `.env` | ✅ Other fields preserved |
| Stale 2.0 files | Removed automatically | N/A (obsolete files) |
| Oversight data (`oversight/`) | **NEVER touched** | ✅ Always safe |

### Pre-Update Checklist

Before updating, backup your config if you have customized it beyond `user_name`:

```bash
# Backup your config
cp _ai-memory/pov/config.yaml _ai-memory/pov/config.yaml.backup

# Your oversight data is ALWAYS safe - install.sh never touches it!
```

---

## 💡 Using Parzival

### Available Commands

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `/pov:parzival` | Activate Parzival with interactive menu | General oversight interaction |
| `/pov:parzival-start` | Start session | Beginning of work session |
| `/pov:parzival-status` | Quick status | Check current state |
| `/pov:parzival-closeout` | End session | End of work session |
| `/pov:parzival-handoff` | Mid-session save | Taking a break |
| `/pov:parzival-blocker` | Analyze blocker | Stuck on something |
| `/pov:parzival-decision` | Decision support | Need to choose between options |
| `/pov:parzival-verify` | Run checklist | Quality verification |
| [TP] Team Builder | Design agent team | Parallel work execution |

### Typical Workflow

```bash
# Morning - Start your session
/pov:parzival-start

# Parzival loads previous context and shows:
# - Recent decisions
# - Open tasks
# - Known risks
# - Session continuity

# During work - hit a blocker?
/pov:parzival-blocker
# Parzival analyzes and presents resolution options

# During work - need to make a decision?
/pov:parzival-decision
# Parzival presents options with tradeoffs

# Taking a break?
/pov:parzival-handoff
# Creates a mid-session snapshot

# End of day
/pov:parzival-closeout
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
Via Parzival menu item **[CR]**, or invoke `/pov:parzival` and select CR:
- Adversarial review (finds 3-10 issues minimum)
- Checks quality, security, architecture compliance
- Severity-ranked issues with file:line references

#### Verification Agent
Via Parzival menu item **[VE]**, or invoke `/pov:parzival` and select VE:
- Validates against acceptance criteria
- Evidence-based pass/fail per criterion
- Runs automated tests if available

#### Best Practices Researcher
Via Parzival menu item **[BR]**, or invoke `/pov:parzival` and select BR:
- Researches current (2024-2026) standards
- Caches findings to avoid repeat research
- Sources citations for recommendations

---

## 🛡️ Safety Features

### 🔐 Data Protection

The unified `install.sh` guarantees your data is never accidentally lost:

```
┌─────────────────────────────────────────────────────────────┐
│  install.sh                                                  │
│  - Updates module code in _ai-memory/pov/                   │
│  - Regenerates skill shims in .claude/skills/               │
│  - Syncs config from .env (user_name only)                  │
│  - Cleans up stale 2.0 files automatically                  │
│  - Deploys oversight templates (no-clobber — never          │
│    overwrites existing files)                               │
│  - NEVER touches existing oversight/ data                   │
│  - Safe to run on existing installations                    │
└─────────────────────────────────────────────────────────────┘
```

### ✅ Idempotency

The installer is safe to run multiple times:

- **install.sh**: Overwrites module code, regenerates shims, deploys templates with no-clobber (skips existing files), cleans up stale files idempotently

### 🚨 Safety Guarantees

| Scenario | What Happens | Your Data |
|----------|--------------|-----------|
| Run `install.sh` on existing installation | Module code updated, shims regenerated | ✅ Preserved |
| Run `install.sh` with existing oversight/ | Templates deployed with no-clobber (existing files skipped) | ✅ Preserved |
| Accidental re-run of installer | Safe behavior, no data loss | ✅ Preserved |
| `install.sh` fails mid-execution | Partial update, no oversight data touched | ✅ Preserved |

---

## 🗂️ Project Structure

After installation, your project will have this structure:

```
my-project/
├── _ai-memory/                     # AI Memory System
│   └── pov/                        # Parzival Oversight Module
│       ├── config.yaml             # Module config (user_name synced from .env)
│       ├── agents/
│       │   └── parzival.md         # Main agent definition
│       ├── constraints/            # Global + phase constraints
│       ├── data/                   # Reference data (complexity, confidence, escalation, etc.)
│       ├── workflows/              # Phase workflows
│       ├── skills/                 # 7 Parzival skills (source of truth)
│       │   ├── aim-parzival-bootstrap/
│       │   ├── aim-parzival-constraints/
│       │   ├── aim-parzival-team-builder/
│       │   ├── aim-agent-dispatch/
│       │   ├── aim-bmad-dispatch/
│       │   ├── aim-agent-lifecycle/
│       │   └── aim-model-dispatch/
│       └── templates/              # Oversight templates
│
├── .claude/                        # Claude Code integration
│   ├── agents/
│   │   └── pov/
│   │       └── parzival.md         # Agent definition (shim)
│   ├── commands/
│   │   └── pov/                    # 8 slash commands
│   │       ├── parzival.md
│   │       ├── parzival-start.md
│   │       ├── parzival-status.md
│   │       ├── parzival-closeout.md
│   │       ├── parzival-handoff.md
│   │       ├── parzival-blocker.md
│   │       ├── parzival-decision.md
│   │       └── parzival-verify.md
│   └── skills/
│       ├── aim-parzival-bootstrap/   # Thin shims (auto-generated)
│       ├── aim-parzival-constraints/ # Each contains SKILL.md with
│       ├── aim-parzival-team-builder/# **LOAD** pointer to _ai-memory/pov/skills/
│       ├── aim-agent-dispatch/
│       ├── aim-bmad-dispatch/
│       ├── aim-agent-lifecycle/
│       ├── aim-model-dispatch/
│       ├── aim-search/               # Non-Parzival skills (full content, not shims)
│       ├── aim-save/
│       ├── aim-status/
│       └── ...                       # Other aim-* skills
│
└── oversight/                      # Your Session Data (NEVER overwritten)
    ├── README.md                   # Oversight system guide
    ├── SESSION_WORK_INDEX.md       # Quick context (~2K tokens)
    ├── tracking/                   # Project Tracking
    ├── decisions/                  # Decision Log
    ├── session-logs/               # Session History
    ├── knowledge/                  # Knowledge Base
    ├── standards/                  # Standards (Sharded)
    ├── verification/               # Quality Checklists
    └── ...                         # Additional folders
```

### Key Directories Explained

| Directory | Purpose | Updated By |
|-----------|---------|-----------|
| `_ai-memory/pov/` | Module code + skill source | `install.sh` |
| `_ai-memory/pov/skills/` | Parzival skill definitions (source of truth) | `install.sh` |
| `.claude/commands/pov/` | Slash commands | `install.sh` |
| `.claude/agents/pov/` | Agent definition | `install.sh` |
| `.claude/skills/aim-*` | Skill shims (Parzival) + full skills (non-Parzival) | `generate_parzival_skill_shims()` |
| `oversight/` | **Your session data** | **You + Parzival** |
| `oversight/session-logs/` | Session handoffs | Parzival (auto) |
| `oversight/tracking/` | Project tracking | You + Parzival |
| `oversight/decisions/` | Decision records | Parzival (when you decide) |
| `oversight/knowledge/` | Knowledge accumulation | Parzival + agents |

---

## 🔧 Configuration

### Basic Configuration

Edit `_ai-memory/pov/config.yaml`:

```yaml
# Module-specific paths
pov_output_folder: "{project-root}/_ai-memory-output/pov"
constraints_path: "{project-root}/_ai-memory/pov/constraints"
workflows_path: "{project-root}/_ai-memory/pov/workflows"
oversight_path: "{project-root}/oversight"

# Core Configuration Values
user_name: "{USER_NAME}"            # Auto-set by installer from PARZIVAL_USER_NAME env var
communication_language: English     # Preferred language
document_output_language: English
output_folder: "{project-root}/_ai-memory-output"
```

Note: `user_name` is parameterized as `{USER_NAME}` and substituted by `sync_parzival_config_yaml()` from the `PARZIVAL_USER_NAME` variable in your `.env` file.

### Advanced Customization

Create custom agent behavior by editing the customization template (if available in your project):

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
<summary><b>🚫 "Command not found" when running `/pov:parzival-start`</b></summary>

**Cause:** Slash commands not installed correctly.

**Fix:**
```bash
# Verify commands exist
ls .claude/commands/pov/

# If missing, re-run installer
./scripts/install.sh

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

# If missing or empty, re-run installer (deploys oversight templates)
./scripts/install.sh

# Or manually copy templates
cp -r _ai-memory/pov/templates/oversight/* oversight/
```
</details>

<details>
<summary><b>⚠️ "Module 'pov' not found" error</b></summary>

**Cause:** Module files not deployed correctly.

**Fix:**
```bash
# Verify module files exist
ls _ai-memory/pov/config.yaml
ls _ai-memory/pov/agents/parzival.md

# If missing, re-run installer
./scripts/install.sh
```
</details>

<details>
<summary><b>🐧 "Permission denied" on Linux/Mac</b></summary>

**Cause:** Script doesn't have execute permission.

**Fix:**
```bash
chmod +x scripts/install.sh

# Then run the script
./scripts/install.sh
```
</details>

<details>
<summary><b>📁 "oversight/" folder exists but templates are outdated</b></summary>

**Cause:** Templates were updated in a new version.

**Fix:**
```bash
# Re-run installer — it deploys oversight templates without overwriting existing files
./scripts/install.sh
```
</details>

<details>
<summary><b>🔍 Best practices research not caching</b></summary>

**Cause:** `oversight/knowledge/best-practices/` folder missing.

**Fix:**
```bash
# Create the folder
mkdir -p oversight/knowledge/best-practices/

# Copy templates if available
cp _ai-memory/pov/templates/oversight/knowledge/best-practices/_TEMPLATE.md \
   oversight/knowledge/best-practices/
cp _ai-memory/pov/templates/oversight/knowledge/best-practices/index.md \
   oversight/knowledge/best-practices/
```
</details>

<details>
<summary><b>🎯 BMAD commands work but Parzival doesn't load</b></summary>

**Cause:** Agent definition not deployed to `.claude/agents/pov/`.

**Fix:**
```bash
# Check agent definition exists
ls .claude/agents/pov/parzival.md

# If missing, re-run installer
./scripts/install.sh
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
- **[CONSTRAINT-ENFORCEMENT-SYSTEM.md](./CONSTRAINT-ENFORCEMENT-SYSTEM.md)** - Behavioral constraint architecture
- **[constraints.md](../../_ai-memory/pov/constraints/global/constraints.md)** - Global constraint index (GC-01 through GC-20)
- **[Workflows](../../_ai-memory/pov/workflows/)** - Step-by-step workflow definitions

### External Resources
- [BMAD Method Documentation](https://bmad-method.org/docs)
- [Claude Code Documentation](https://docs.anthropic.com/claude/docs/claude-code)

---

## 🎯 Quick Reference Card

```
╔════════════════════════════════════════════════════════════════════╗
║                   PARZIVAL QUICK REFERENCE                         ║
╠════════════════════════════════════════════════════════════════════╣
║  SLASH COMMANDS                                                    ║
║  ─────────────────────────────────────────────────────────────    ║
║  /pov:parzival           Interactive menu                          ║
║  /pov:parzival-start     Start session                             ║
║  /pov:parzival-status    Check status                              ║
║  /pov:parzival-closeout  End session                               ║
║  /pov:parzival-handoff   Mid-session save                          ║
║  /pov:parzival-blocker   Analyze blocker                           ║
║  /pov:parzival-decision  Decision support                          ║
║  /pov:parzival-verify    Run verification                          ║
║                                                                    ║
║  MENU ITEMS (inside Parzival session)                              ║
║  ─────────────────────────────────────────────────────────────    ║
║  [TP] Team Builder       Design agent team                         ║
║  [CR] Code Review        🔍 Adversarial code review               ║
║  [VE] Verification       ✓  Verify acceptance criteria            ║
║  [BR] Best Practices     📚 Research current standards            ║
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
