# Model-Dispatch Skill — Complete Setup Guide

Install everything needed to dispatch tasks to remote models from within Claude Code.

---

## Quick Start

Already set up? Run the validation script to confirm:

```bash
bash /path/to/model-dispatch/scripts/validate-setup.sh
```

All checks should pass before dispatching.

---

## 1. System Requirements

### Required Software

| Software | Purpose | Install |
|---|---|---|
| **Claude Code** | The CLI this skill dispatches to | `npm install -g @anthropic-ai/claude-code` |
| **tmux** | Pane management for isolated sessions | `sudo apt install tmux` (Linux) / `brew install tmux` (macOS) |
| **python3** | Inbox injection for teammate communication | `sudo apt install python3` (usually pre-installed) |
| **jq** | JSON parsing in shell scripts | `sudo apt install jq` (Linux) / `brew install jq` (macOS) |
| **inotify-tools** | File change detection (optional but recommended) | `sudo apt install inotify-tools` (Linux) / `brew install inotify-tools` (macOS) |

### Optional Software

| Software | Purpose | Install |
|---|---|---|
| **Gemini CLI** | Native Google Gemini dispatch (uses Google account, not API key) | `npm install -g @google/gemini-cli` |

### Required Accounts

- **Claude native:** Anthropic API key at [console.anthropic.com](https://console.anthropic.com)
- **OpenRouter:** API key at [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys)
- **Ollama:** API token from your Ollama endpoint (e.g., `https://ollama.com`)
- **Gemini (CLI):** Google account — run `gemini` and follow the login flow (separate from API key)

### Required Environment

- `~/.local/bin` must be in your PATH (standard on most Linux distros)
- You must be running inside a **tmux session** to dispatch (tmux panes are required for all dispatch operations)

---

## 2. Installation

Follow these steps in order. Each step builds on the previous one.

### 2.1 Install System Dependencies

```bash
# Ubuntu/Debian
sudo apt install tmux python3 jq inotify-tools

# macOS
brew install tmux python3 jq inotify-tools
```

Verify:

```bash
tmux -V && python3 --version && jq --version && inotifywait --version
```

### 2.2 Store API Tokens

**All provider tokens are configured automatically through `bash install.sh`.** The installer prompts for tokens per provider and stores them in the correct token files with secure permissions. You can also set them manually as shown below.

#### Anthropic (Claude Native)

```bash
echo "YOUR_ANTHROPIC_API_KEY_HERE" > ~/.anthropic-token
chmod 600 ~/.anthropic-token
```

#### OpenRouter

```bash
echo "YOUR_OPENROUTER_API_KEY_HERE" > ~/.openrouter-token
chmod 600 ~/.openrouter-token
```

#### Ollama

```bash
echo "YOUR_OLLAMA_API_TOKEN_HERE" > ~/.ollama-token
chmod 600 ~/.ollama-token
```

Verify:

```bash
stat -c '%a' ~/.anthropic-token ~/.openrouter-token ~/.ollama-token  # Should show 600 for all
```

### 2.3 Install Wrappers

Run the interactive install script:

```bash
bash /path/to/model-dispatch/scripts/install.sh
```

This will:
1. Check prerequisites
2. Prompt for API keys (if installing OpenRouter/Ollama)
3. Install wrapper scripts to `~/.local/bin/`
4. Install Python dependencies
5. Run validation

**Note:** The old per-provider wrappers (`openrouter-claude`, `ollama-claude`) have been replaced by the unified `provider-dispatch` wrapper. All providers are now configured through `bash install.sh`. Manual wrapper installation is no longer recommended — run the installer instead:

```bash
bash /path/to/model-dispatch/scripts/install.sh
```

If you need to manually install only the `claude-dispatch` native wrapper:

```bash
# Claude dispatch (native Anthropic API)
cat > ~/.local/bin/claude-dispatch << 'EOF'
#!/bin/bash
unset CLAUDECODE
unset ANTHROPIC_BASE_URL
unset ANTHROPIC_AUTH_TOKEN
exec claude "$@"
EOF
chmod +x ~/.local/bin/claude-dispatch
```

### 2.4 Verify PATH

Confirm `~/.local/bin` is in your PATH:

```bash
echo $PATH | tr ':' '\n' | grep local/bin
```

If missing, add to your shell profile:

```bash
# For bash (~/.bashrc)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# For zsh (~/.zshrc)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 2.5 Verify Wrappers Work

```bash
which claude-dispatch
which provider-dispatch

claude-dispatch --version
provider-dispatch openrouter --version
provider-dispatch ollama --version
```

---

## 3. Skill Installation

The model-dispatch skill must be installed in your Claude Code skills directory.

### 3.1 Install to Skills Directory

Copy or symlink the skill into `.claude/skills/`:

```bash
# Option A: Copy
cp -r /path/to/model-dispatch /path/to/project/.claude/skills/model-dispatch

# Option B: Symlink
ln -s /path/to/model-dispatch /path/to/project/.claude/skills/model-dispatch
```

### 3.2 Verify Scripts Are Executable

```bash
chmod +x /path/to/model-dispatch/scripts/*.sh
chmod +x /path/to/model-dispatch/scripts/openrouter-api/*.py
```

### 3.3 Install Python Dependencies

```bash
pip3 install -r /path/to/model-dispatch/scripts/openrouter-api/requirements.txt
```

### 3.4 Run Validation

```bash
bash /path/to/model-dispatch/scripts/validate-setup.sh
```

Expected output (example with openrouter + ollama configured):

```
=== model-dispatch Validation Suite ===

[PASS] provider-dispatch in PATH
[PASS] claude-dispatch in PATH
[PASS] providers.json found at /home/user/.config/claude-code-router/providers.json
[PASS] providers.json is valid JSON
[PASS] Provider openrouter: token file exists (chmod 600)
[PASS] Provider ollama: token file exists (chmod 600)
[PASS] provider-dispatch unsets CLAUDECODE (nesting protection)
[PASS] tmux installed
[PASS] python3 installed
[PASS] jq installed
[WARN] inotify-tools not found — sudo apt install inotify-tools (optional)

=== Summary ===
Passed: 10
Failed: 0
Warnings: 1

All critical checks passed!
```

> Token check lines (`Provider X: token file exists`) appear once per configured provider in your `~/.config/claude-code-router/providers.json`. The exact count depends on your setup.

---

## 4. Claude Setup

### 4.1 Configure Claude Settings

Add skill to your `.claude/settings.local.json`:

```json
{
  "skills": [
    "/path/to/model-dispatch"
  ]
}
```

### 4.2 Optional: Hook for Auto-Approve

Add to settings for auto-approval of dispatched agents:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/absolute/path/to/model-dispatch/scripts/auto-approve-hook.sh"
          }
        ]
      }
    ]
  }
}
```

---

## 5. OpenRouter Setup

### 5.1 Get API Key

1. Visit [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys)
2. Create a new API key
3. Store in `~/.openrouter-token` (see Section 2.2)

### 5.2 Test OpenRouter Connection

```bash
python3 -c "
import os
from openai import OpenAI
key = open(os.path.expanduser('~/.openrouter-token')).read().strip()
client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=key)
result = client.chat.completions.create(
    model='openai/gpt-4o-mini',
    messages=[{'role': 'user', 'content': 'Say hello'}]
)
print(result.choices[0].message.content)
"
```

---

## 6. Ollama Setup

### 6.1 Get API Token

1. Visit your Ollama provider (e.g., `https://ollama.com`)
2. Create an API token
3. Store in `~/.ollama-token` (see Section 2.2)

### 6.2 Change Ollama Endpoint

Edit `~/.config/claude-code-router/providers.json` to change the Ollama baseUrl, or re-run `bash install.sh` to reconfigure. Alternatively, set the env var directly:

```bash
ANTHROPIC_BASE_URL="http://localhost:11434" provider-dispatch ollama  # Local Ollama
```

---

## 7. API Mode Setup

OpenRouter API scripts enable direct model access without tmux:

### 7.1 Available Scripts

| Script | Purpose | Lines |
|---|---|---|
| `scripts/openrouter-api/text-generate.py` | Text generation via chat completions | ~80 |
| `scripts/openrouter-api/image-analyze.py` | Vision model, base64 or URL | ~100 |
| `scripts/openrouter-api/image-generate.py` | DALL-E 3 image creation | ~90 |
| `scripts/openrouter-api/audio-process.py` | Whisper transcription | ~100 |
| `scripts/openrouter-api/audio-generate.py` | Text-to-speech and music generation via TTS providers (OpenAI TTS, ElevenLabs, Suno) | ~90 |
| `scripts/openrouter-api/video-generate.py` | Video generation via video model providers (Runway, Kling, Pika, Minimax, Luma) | ~90 |
| `scripts/openrouter-api/requirements.txt` | Python dependencies | ~10 |

### 7.2 Install Dependencies

```bash
pip3 install -r scripts/openrouter-api/requirements.txt
```

### 7.3 Test Scripts

```bash
# Help
python3 scripts/openrouter-api/text-generate.py --help

# Text generation
python3 scripts/openrouter-api/text-generate.py \
  --model openai/gpt-4o-mini \
  --input "Hello, world!" \
  --output -
```

---

## 8. Permissions

Choose one option for tool permissions:

### Option A: CLI Flags (Recommended)

```bash
provider-dispatch openrouter --model <model-name> \
  --allowedTools "Edit" "Write" "Read" "Glob" "Grep" "Bash(*)"
```

### Option B: PermissionRequest Hook

See Section 4.2 for hook configuration.

### Option C: Project Permissions

```json
{
  "permissions": {
    "allow": [
      "Bash(tmux list-panes:*)",
      "Bash(tmux send-keys:*)",
      "Bash(tmux kill-pane:*)",
      "Bash(tmux capture-pane:*)",
      "Bash(python3:*)"
    ]
  }
}
```

---

## 9. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `command not found` | Wrapper not installed or not in PATH | Check `~/.local/bin/` and PATH |
| `401 unauthorized` | Token missing or wrong | Check `~/*.token` contents and chmod 600 |
| `model does not exist` | Wrong ANTHROPIC_BASE_URL | Verify wrapper sets correct URL |
| Nesting error | CLAUDECODE env var inherited | Verify wrapper has `unset CLAUDECODE` |
| Prompt not submitted | Enter hit too fast | Wait 2 seconds after prompt, then Enter once |
| Blank pane after launch | Init wait too short | Increase sleep to 8-10 seconds |
| Permission dialogs blocking | Tools not pre-approved | Use `--allowedTools` flags |

---

## 10. File Locations

| File | Purpose |
|---|---|
| `~/.local/bin/claude-dispatch` | Native Claude wrapper |
| `~/.local/bin/provider-dispatch` | Unified provider dispatch wrapper (all providers) |
| `~/.anthropic-token` | Anthropic API token, chmod 600 |
| `~/.openrouter-token` | OpenRouter API token, chmod 600 |
| `~/.ollama-token` | Ollama API token, chmod 600 |
| `~/.gemini-token` | Google Gemini API token, chmod 600 |
| `~/.deepseek-token` | DeepSeek API token, chmod 600 |
| `~/.groq-token` | Groq API token, chmod 600 |
| `~/.cerebras-token` | Cerebras API token, chmod 600 |
| `~/.mistral-token` | Mistral API token, chmod 600 |
| `~/.openai-token` | OpenAI API token, chmod 600 |
| `~/.vertex-token` | Google Vertex AI token, chmod 600 |
| `~/.siliconflow-token` | SiliconFlow API token, chmod 600 |
| `.claude/skills/model-dispatch/` | Skill directory |
| `.claude/skills/model-dispatch/scripts/` | Support scripts |
| `.claude/skills/model-dispatch/references/` | Documentation |
| `/tmp/model-dispatch-result-*.txt` | Captured agent outputs |

---

## Next Steps

- Read `references/user-guide.md` for usage examples
- Read `references/model-selection-guide.md` for model selection
- Run `dispatch to model-dispatch: [task]` to try dispatching
