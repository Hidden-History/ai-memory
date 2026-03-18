#!/bin/bash
# install.sh — Interactive installer for model-dispatch
# Installs all providers, validates setup, creates wrappers
#
# Usage:
#   install.sh                    — Full install (system + skill copy to current dir)
#   install.sh /path/to/project   — Add skill to another project (skips system setup
#                                   if already configured)
#
# Features:
#   - Detect existing CCR config for import
#   - Interactive provider selection (all CCR-compatible providers)
#   - API token prompts with secure file creation per provider
#   - Default model collection per provider
#   - Write providers.json to ~/.config/claude-code-router/
#   - provider-dispatch wrapper installation to ~/.local/bin
#   - Python dependencies installation
#   - Copy skill into target project's .claude/skills/model-dispatch/
#   - Final validation

set -euo pipefail

SKILL_DIR="${MODEL_DISPATCH_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}"

# ──────────────────────────────────────────────────────────────────────
# Parse optional target project directory argument
# ──────────────────────────────────────────────────────────────────────
TARGET_DIR=""
if [ -n "${1:-}" ]; then
  if [ ! -d "$1" ]; then
    echo "Error: Target directory not found: $1" >&2
    exit 1
  fi
  TARGET_DIR="$(cd "$1" && pwd)"
fi

# Fast-path: if a target project is given AND system is already set up,
# skip all provider/wrapper steps and go straight to skill copy.
PROVIDERS_CONFIG="${HOME}/.config/claude-code-router/providers.json"
SYSTEM_READY=false
if [ -f "$PROVIDERS_CONFIG" ] && \
   [ -x "${HOME}/.local/bin/provider-dispatch" ] && \
   [ -x "${HOME}/.local/bin/claude-dispatch" ]; then
  SYSTEM_READY=true
fi

if [ -n "$TARGET_DIR" ] && [ "$SYSTEM_READY" = "true" ]; then
  echo "=== model-dispatch: Add to Project ==="
  echo ""
  echo "System already configured (providers.json + wrappers found)."
  echo "Installing skill into: ${TARGET_DIR}/.claude/skills/model-dispatch/"
  echo ""
  SKILL_TARGET="${TARGET_DIR}/.claude/skills/model-dispatch"
  if [ -d "$SKILL_TARGET" ]; then
    read -p "Skill already exists at ${SKILL_TARGET}. Overwrite? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "Skipped — skill already installed in that project."
      exit 0
    fi
  fi
  mkdir -p "$SKILL_TARGET"
  cp -r "${SKILL_DIR}/." "$SKILL_TARGET/"
  echo -e "${GREEN:-}[OK]${NC:-} Skill installed to ${SKILL_TARGET}"
  echo ""
  echo "Done. The skill is ready to use in: ${TARGET_DIR}"
  exit 0
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
  local msg="$1"
  local status="$2"  # ok, warn, error
  case "$status" in
    ok) echo -e "${GREEN}[OK]${NC} $msg" ;;
    warn) echo -e "${YELLOW}[WARN]${NC} $msg" ;;
    error) echo -e "${RED}[ERROR]${NC} $msg" ;;
  esac
}

check_command() {
  command -v "$1" &>/dev/null
}

echo "=== model-dispatch Installer ==="
echo ""
echo "This script will install model-dispatch infrastructure."
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 1: Check prerequisites
# ──────────────────────────────────────────────────────────────────────
echo "Step 1: Checking prerequisites..."
echo ""

MISSING=()
for cmd in python3 tmux jq; do
  if ! check_command "$cmd"; then
    MISSING+=("$cmd")
  fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
  echo -e "${YELLOW}WARNING:${NC} Missing commands: ${MISSING[*]}"
  echo "Install with: sudo apt install ${MISSING[*]}"
  echo ""
fi

if ! check_command "inotifywait"; then
  echo -e "${YELLOW}WARNING:${NC} inotify-tools not found"
  echo "Optional: sudo apt install inotify-tools (improves signal detection)"
  echo ""
fi

# ──────────────────────────────────────────────────────────────────────
# Step 2: Detect existing CCR config
# ──────────────────────────────────────────────────────────────────────
echo "Step 2: Checking for existing Claude Code Router config..."
echo ""

CCR_CONFIG="${HOME}/.config/claude-code-router/config.json"
if [ ! -f "$CCR_CONFIG" ]; then
  CCR_CONFIG="${HOME}/.claude-code-router/config.json"
fi
IMPORTED_PROVIDERS=()

if [ -f "$CCR_CONFIG" ] && check_command "jq"; then
  echo "Found existing CCR config at $CCR_CONFIG"
  read -p "Import provider records from it? [Y/n] " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    # Extract provider names that have a baseUrl
    mapfile -t IMPORTED_PROVIDERS < <(jq -r '
      .providers // {} | to_entries[] |
      select(.value.baseUrl != null) | .key
    ' "$CCR_CONFIG" 2>/dev/null || true)

    if [ ${#IMPORTED_PROVIDERS[@]} -gt 0 ]; then
      print_status "Found providers in CCR config: ${IMPORTED_PROVIDERS[*]}" "ok"
    else
      echo "No compatible providers found in CCR config — proceeding with fresh setup."
    fi
  fi
  echo ""
fi

# ──────────────────────────────────────────────────────────────────────
# Provider tables (base URLs, key files, suggested defaults)
# ──────────────────────────────────────────────────────────────────────

declare -A PROVIDER_BASE_URLS=(
  ["openrouter"]="https://openrouter.ai/api"
  ["ollama"]="https://ollama.com"
  ["gemini"]="https://generativelanguage.googleapis.com/v1beta/openai"
  ["deepseek"]="https://api.deepseek.com"
  ["groq"]="https://api.groq.com/openai"
  ["cerebras"]="https://api.cerebras.ai/v1"
  ["mistral"]="https://api.mistral.ai/v1"
  ["openai"]="https://api.openai.com/v1"
  ["vertex-ai"]="https://aiplatform.googleapis.com/v1/publishers/google/models"
  ["siliconflow"]="https://api.siliconflow.cn/v1"
)

declare -A PROVIDER_KEY_FILES=(
  ["openrouter"]="~/.openrouter-token"
  ["ollama"]="~/.ollama-token"
  ["gemini"]="~/.gemini-token"
  ["deepseek"]="~/.deepseek-token"
  ["groq"]="~/.groq-token"
  ["cerebras"]="~/.cerebras-token"
  ["mistral"]="~/.mistral-token"
  ["openai"]="~/.openai-token"
  ["vertex-ai"]="~/.vertex-token"
  ["siliconflow"]="~/.siliconflow-token"
)

declare -A PROVIDER_DEFAULT_MODELS=(
  ["openrouter"]="anthropic/claude-sonnet-4-6"
  ["ollama"]="glm-5:cloud"
  ["gemini"]="gemini-2.0-flash"
  ["deepseek"]="deepseek-chat"
  ["groq"]="llama-4-scout-17b-16e-instruct"
  ["cerebras"]="llama3.1-70b"
  ["mistral"]="mistral-large-2411"
  ["openai"]="gpt-4o"
  ["vertex-ai"]="claude-sonnet-4-5@anthropic"
  ["siliconflow"]="Qwen/Qwen2.5-72B-Instruct"
)

declare -A PROVIDER_EMPTY_API_KEY=(
  ["openrouter"]="true"
  ["ollama"]="false"
  ["gemini"]="false"
  ["deepseek"]="false"
  ["groq"]="false"
  ["cerebras"]="false"
  ["mistral"]="false"
  ["openai"]="false"
  ["vertex-ai"]="false"
  ["siliconflow"]="false"
)

PROVIDER_LIST=("openrouter" "ollama" "gemini" "deepseek" "groq" "cerebras" "mistral" "openai" "vertex-ai" "siliconflow")

# Pre-select providers found in CCR config
SELECTED_PROVIDERS=()
if [ ${#IMPORTED_PROVIDERS[@]} -gt 0 ]; then
  echo "Pre-selecting providers from CCR config: ${IMPORTED_PROVIDERS[*]}"
  for imp_prov in "${IMPORTED_PROVIDERS[@]}"; do
    # Only pre-select if we support this provider
    if [[ " ${PROVIDER_LIST[*]} " =~ " ${imp_prov} " ]]; then
      if [[ ! " ${SELECTED_PROVIDERS[*]} " =~ " ${imp_prov} " ]]; then
        SELECTED_PROVIDERS+=("$imp_prov")
      fi
    fi
  done
  echo "Pre-selected: ${SELECTED_PROVIDERS[*]:-none}"
  read -p "Proceed with these pre-selected providers? Add/remove in Step 3. [Y/n] " -n 1 -r
  echo ""
fi

# ──────────────────────────────────────────────────────────────────────
# Step 3: Select providers to configure
# ──────────────────────────────────────────────────────────────────────
echo "Step 3: Select providers to configure"
echo ""
echo "Claude native (Anthropic) is always required and cannot be deselected."
echo ""

# Save pre-selections from CCR import so they survive the user's input
PRE_SELECTIONS=("${SELECTED_PROVIDERS[@]}")

if [ ${#PRE_SELECTIONS[@]} -gt 0 ]; then
  echo "Pre-selected from CCR import: ${PRE_SELECTIONS[*]}"
  echo ""
fi

echo "Available providers:"
echo ""
for i in "${!PROVIDER_LIST[@]}"; do
  PNAME="${PROVIDER_LIST[$i]}"
  NUM=$((i + 1))
  PRE_MARK=""
  if [[ " ${PRE_SELECTIONS[*]} " =~ " ${PNAME} " ]]; then
    PRE_MARK=" [pre-selected]"
  fi
  echo "  $NUM) $PNAME${PRE_MARK}  (${PROVIDER_BASE_URLS[$PNAME]})"
done
echo ""

if [ ${#PRE_SELECTIONS[@]} -gt 0 ]; then
  echo "Enter numbers to override pre-selections, 'all' for all providers, or 'skip' to keep pre-selected:"
else
  echo "Enter comma-separated numbers (e.g. 1,3,5), 'all' for all providers, or 'skip' to skip:"
fi
read -r PROVIDER_SELECTION
echo ""

# Restore pre-selections as the base — explicit user input overrides them
SELECTED_PROVIDERS=("${PRE_SELECTIONS[@]}")

if [[ "$PROVIDER_SELECTION" == "skip" ]]; then
  if [ ${#SELECTED_PROVIDERS[@]} -gt 0 ]; then
    echo "Keeping pre-selected providers: ${SELECTED_PROVIDERS[*]}"
  else
    echo "No additional providers selected. Only Claude native will be configured."
  fi
elif [[ "$PROVIDER_SELECTION" == "all" ]]; then
  SELECTED_PROVIDERS=("${PROVIDER_LIST[@]}")
else
  # Explicit number selection replaces pre-selections entirely
  SELECTED_PROVIDERS=()
  IFS=',' read -ra SELECTIONS <<< "$PROVIDER_SELECTION"
  for SEL in "${SELECTIONS[@]}"; do
    SEL="${SEL// /}"
    if [[ "$SEL" =~ ^[0-9]+$ ]] && [ "$SEL" -ge 1 ] && [ "$SEL" -le "${#PROVIDER_LIST[@]}" ]; then
      IDX=$((SEL - 1))
      SELECTED_PROVIDERS+=("${PROVIDER_LIST[$IDX]}")
    else
      echo -e "${YELLOW}[WARN]${NC} Invalid selection: $SEL (ignored)"
    fi
  done
fi

if [ ${#SELECTED_PROVIDERS[@]} -gt 0 ]; then
  echo "Selected providers: ${SELECTED_PROVIDERS[*]}"
else
  echo "No additional providers selected."
fi
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 4: For each selected provider, collect config
# ──────────────────────────────────────────────────────────────────────
echo "Step 4: Collecting provider configuration..."
echo ""

# Track collected configs for JSON assembly
declare -A COLLECTED_BASE_URLS
declare -A COLLECTED_KEY_FILES
declare -A COLLECTED_DEFAULT_MODELS

for PROVIDER in "${SELECTED_PROVIDERS[@]}"; do
  PROVIDER_TOKEN=""
  BASE_URL="${PROVIDER_BASE_URLS[$PROVIDER]}"
  KEY_FILE="${PROVIDER_KEY_FILES[$PROVIDER]}"
  DEFAULT_MODEL="${PROVIDER_DEFAULT_MODELS[$PROVIDER]}"
  TOKEN_PATH="${HOME}/${KEY_FILE#\~\/}"

  echo "--- Provider: $PROVIDER ---"
  echo "  Base URL: $BASE_URL"
  echo "  Token file: $KEY_FILE"
  echo ""

  # Token collection
  if [ -f "$TOKEN_PATH" ]; then
    print_status "Existing token found at $KEY_FILE" "ok"
    read -p "  Overwrite existing token? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      read -sp "  Enter $PROVIDER API token: " PROVIDER_TOKEN
      echo ""
      echo "$PROVIDER_TOKEN" > "$TOKEN_PATH"
      chmod 600 "$TOKEN_PATH"
      print_status "Token saved to $KEY_FILE" "ok"
    else
      echo "  Keeping existing token."
    fi
  else
    if [ "$PROVIDER" = "ollama" ]; then
      echo "  Ollama local mode typically needs no API token."
      read -p "  Set a token? [y/N] " -n 1 -r
      echo ""
      if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -sp "  Enter ollama API token: " PROVIDER_TOKEN
        echo ""
        echo "$PROVIDER_TOKEN" > "$TOKEN_PATH"
        chmod 600 "$TOKEN_PATH"
        print_status "Token saved to $KEY_FILE" "ok"
      else
        touch "$TOKEN_PATH"
        chmod 600 "$TOKEN_PATH"
        print_status "Empty token file created (no auth)" "ok"
      fi
    else
      read -sp "  Enter $PROVIDER API token: " PROVIDER_TOKEN
      echo ""
      if [ -z "$PROVIDER_TOKEN" ]; then
        print_status "No token entered — you'll need to set it later in $KEY_FILE" "warn"
        touch "$TOKEN_PATH"
        chmod 600 "$TOKEN_PATH"
      else
        echo "$PROVIDER_TOKEN" > "$TOKEN_PATH"
        chmod 600 "$TOKEN_PATH"
        print_status "Token saved to $KEY_FILE" "ok"
      fi
    fi
  fi

  # Default model collection
  echo ""
  read -p "  Default model for $PROVIDER [$DEFAULT_MODEL]: " USER_MODEL
  if [ -n "$USER_MODEL" ]; then
    DEFAULT_MODEL="$USER_MODEL"
  fi
  print_status "Default model: $DEFAULT_MODEL" "ok"
  echo ""

  COLLECTED_BASE_URLS[$PROVIDER]="$BASE_URL"
  COLLECTED_KEY_FILES[$PROVIDER]="${KEY_FILE}"
  COLLECTED_DEFAULT_MODELS[$PROVIDER]="$DEFAULT_MODEL"
done

# ──────────────────────────────────────────────────────────────────────
# Step 5: Write providers.json
# ──────────────────────────────────────────────────────────────────────
echo "Step 5: Writing providers.json..."
echo ""

PROVIDERS_CONFIG="${HOME}/.config/claude-code-router/providers.json"
mkdir -p "$(dirname "$PROVIDERS_CONFIG")"

# Build JSON incrementally using jq
PROVIDERS_JSON='{"providers":{}}'
for PROVIDER in "${SELECTED_PROVIDERS[@]}"; do
  BASE_URL="${COLLECTED_BASE_URLS[$PROVIDER]}"
  KEY_FILE="${COLLECTED_KEY_FILES[$PROVIDER]}"
  DEFAULT_MODEL="${COLLECTED_DEFAULT_MODELS[$PROVIDER]}"
  EMPTY_API_KEY="${PROVIDER_EMPTY_API_KEY[$PROVIDER]:-false}"

  PROVIDERS_JSON=$(echo "$PROVIDERS_JSON" | jq \
    --arg p "$PROVIDER" \
    --arg u "$BASE_URL" \
    --arg k "$KEY_FILE" \
    --arg m "$DEFAULT_MODEL" \
    --argjson e "$EMPTY_API_KEY" \
    '.providers[$p] = {baseUrl: $u, keyFile: $k, defaultModel: $m, emptyApiKey: $e}')
done

if [ ${#SELECTED_PROVIDERS[@]} -eq 0 ]; then
  echo -e "${YELLOW}[WARN]${NC} No providers configured. providers.json will contain only claude-native."
  echo "You can re-run install.sh later to add providers."
fi
echo "$PROVIDERS_JSON" > "$PROVIDERS_CONFIG"
chmod 600 "$PROVIDERS_CONFIG"
print_status "providers.json written to $PROVIDERS_CONFIG" "ok"
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 6: Install provider-dispatch wrapper to ~/.local/bin
# ──────────────────────────────────────────────────────────────────────
echo "Step 6: Installing wrappers to ~/.local/bin..."
echo ""

mkdir -p "$HOME/.local/bin"

if [ -f "${SKILL_DIR}/wrappers/provider-dispatch.sh" ]; then
  cp "${SKILL_DIR}/wrappers/provider-dispatch.sh" "$HOME/.local/bin/provider-dispatch"
  chmod +x "$HOME/.local/bin/provider-dispatch"
  print_status "provider-dispatch installed to ~/.local/bin/provider-dispatch" "ok"
else
  print_status "wrappers/provider-dispatch.sh not found in skill dir" "error"
fi

if [ -f "${SKILL_DIR}/wrappers/claude-dispatch.sh" ]; then
  cp "${SKILL_DIR}/wrappers/claude-dispatch.sh" "$HOME/.local/bin/claude-dispatch"
  chmod +x "$HOME/.local/bin/claude-dispatch"
  print_status "claude-dispatch installed to ~/.local/bin/claude-dispatch" "ok"
else
  print_status "wrappers/claude-dispatch.sh not found in skill dir" "error"
fi

echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 7: Install Python dependencies
# ──────────────────────────────────────────────────────────────────────
echo "Step 7: Installing Python dependencies..."
echo ""

# Check if openai library is available
python3 -c "import openai" &>/dev/null || {
  echo "Installing openai library..."
  pip3 install --user openai 2>/dev/null || {
    print_status "Failed to install openai library" "error"
  }
}

python3 -c "import requests" &>/dev/null || {
  echo "Installing requests library..."
  pip3 install --user requests 2>/dev/null || {
    print_status "Failed to install requests library" "error"
  }
}

print_status "Python dependencies ready" "ok"
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 8: Copy skill into target project
# ──────────────────────────────────────────────────────────────────────
echo "Step 8: Installing skill into project..."
echo ""

# Determine target: use argument if given, otherwise ask
if [ -z "$TARGET_DIR" ]; then
  echo "Which project should the skill be installed into?"
  echo "Press Enter to skip, or enter a project directory path:"
  read -r TARGET_DIR_INPUT
  echo ""
  if [ -n "$TARGET_DIR_INPUT" ]; then
    if [ -d "$TARGET_DIR_INPUT" ]; then
      TARGET_DIR="$(cd "$TARGET_DIR_INPUT" && pwd)"
    else
      print_status "Directory not found: $TARGET_DIR_INPUT — skipping skill copy" "warn"
      TARGET_DIR=""
    fi
  fi
fi

if [ -n "$TARGET_DIR" ]; then
  SKILL_TARGET="${TARGET_DIR}/.claude/skills/model-dispatch"
  if [ -d "$SKILL_TARGET" ]; then
    read -p "Skill already exists at ${SKILL_TARGET}. Overwrite? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      cp -r "${SKILL_DIR}/." "$SKILL_TARGET/"
      print_status "Skill updated at ${SKILL_TARGET}" "ok"
    else
      print_status "Kept existing skill at ${SKILL_TARGET}" "ok"
    fi
  else
    mkdir -p "$SKILL_TARGET"
    cp -r "${SKILL_DIR}/." "$SKILL_TARGET/"
    print_status "Skill installed to ${SKILL_TARGET}" "ok"
  fi
else
  print_status "Skill copy skipped — run: install.sh /path/to/project  to add later" "warn"
fi
echo ""

# ──────────────────────────────────────────────────────────────────────
# Step 9: Final validation
# ──────────────────────────────────────────────────────────────────────
echo "Step 9: Running final validation..."
echo ""

if [ -f "${SKILL_DIR}/scripts/validate-setup.sh" ]; then
  bash "${SKILL_DIR}/scripts/validate-setup.sh"
  VALIDATION_RESULT=$?
  echo ""
  if [ $VALIDATION_RESULT -eq 0 ]; then
    print_status "All checks passed!" "ok"
  else
    print_status "Some checks failed - review output above" "warn"
  fi
else
  print_status "validate-setup.sh not found" "error"
fi

# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────
echo ""
echo "=== Installation Complete ==="
echo ""
if [ ${#SELECTED_PROVIDERS[@]} -gt 0 ]; then
  echo "Configured providers: ${SELECTED_PROVIDERS[*]}"
else
  echo "Configured providers: (none — Claude native only)"
fi
if [ -n "$TARGET_DIR" ]; then
  echo "Skill installed in:    ${TARGET_DIR}/.claude/skills/model-dispatch/"
fi
echo ""
echo "Quick start:"
echo "  claude-dispatch --help"
echo "  provider-dispatch --help"
echo ""
echo "Add skill to another project:"
echo "  bash ${SKILL_DIR}/scripts/install.sh /path/to/project"
echo ""
echo "If wrappers are not found, add to PATH:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
echo ""
echo "For usage instructions, see: ${SKILL_DIR}/references/user-guide.md"
echo "For provider details, see: ${SKILL_DIR}/references/providers.md"
