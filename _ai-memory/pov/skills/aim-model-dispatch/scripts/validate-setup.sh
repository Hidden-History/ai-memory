#!/bin/bash
# validate-setup.sh — Pre-flight checks for model-dispatch (all CCR providers)
set -euo pipefail

PASS=0
FAIL=0
WARN=0

check() {
  local label="$1" ok="$2" critical="${3:-true}"
  if [ "$ok" = "true" ]; then
    echo "[PASS] ${label}"
    PASS=$((PASS + 1))
  elif [ "$critical" = "true" ]; then
    echo "[FAIL] ${label}"
    FAIL=$((FAIL + 1))
  else
    echo "[WARN] ${label}"
    WARN=$((WARN + 1))
  fi
}

echo "=== model-dispatch Validation Suite ==="
echo ""

# 1. provider-dispatch wrapper
if command -v provider-dispatch &>/dev/null; then
  check "provider-dispatch in PATH" "true"
elif [ -x "$HOME/.local/bin/provider-dispatch" ]; then
  check "provider-dispatch exists but not in PATH — add ~/.local/bin to PATH" "false"
else
  check "provider-dispatch wrapper not found — run: model-dispatch install" "false"
fi

# 2. claude-dispatch wrapper
if command -v claude-dispatch &>/dev/null; then
  check "claude-dispatch in PATH" "true"
elif [ -x "$HOME/.local/bin/claude-dispatch" ]; then
  check "claude-dispatch exists but not in PATH — add ~/.local/bin to PATH" "false"
else
  check "claude-dispatch wrapper not found — run: model-dispatch install" "false"
fi

# 3. providers.json exists
PROVIDERS_CONFIG="${HOME}/.config/claude-code-router/providers.json"
if [ -f "$PROVIDERS_CONFIG" ]; then
  check "providers.json found at ${PROVIDERS_CONFIG}" "true"

  # 4. providers.json is valid JSON
  if jq . "$PROVIDERS_CONFIG" &>/dev/null; then
    check "providers.json is valid JSON" "true"

    # 5. For each configured provider: token file exists + chmod 600
    mapfile -t CONFIGURED_PROVIDERS < <(jq -r '.providers | keys[]' "$PROVIDERS_CONFIG" 2>/dev/null || true)
    for PROVIDER in "${CONFIGURED_PROVIDERS[@]}"; do
      KEY_FILE=$(jq -r ".providers[\"${PROVIDER}\"].keyFile // empty" "$PROVIDERS_CONFIG" 2>/dev/null)
      if [ -z "$KEY_FILE" ]; then
        check "Provider $PROVIDER: no keyFile configured (skipping token check)" "true" "false"
        continue
      fi

      # Expand ~ in path
      TOKEN_PATH="${KEY_FILE/#\~/$HOME}"

      if [ -f "$TOKEN_PATH" ]; then
        if [ -L "$TOKEN_PATH" ]; then
          check "Provider $PROVIDER: token is a symlink — security risk ($TOKEN_PATH)" "false" "false"
        else
          OWNER=$(stat -c '%U' "$TOKEN_PATH" 2>/dev/null || echo "unknown")
          CURRENT_USER=$(whoami)
          if [ "$OWNER" != "$CURRENT_USER" ]; then
            check "Provider $PROVIDER: token owned by $OWNER (should be $CURRENT_USER)" "false" "false"
          else
            PERMS=$(stat -c '%a' "$TOKEN_PATH" 2>/dev/null || stat -f '%Lp' "$TOKEN_PATH" 2>/dev/null)
            if [ "$PERMS" = "600" ]; then
              check "Provider $PROVIDER: token file exists (chmod 600)" "true"
            else
              check "Provider $PROVIDER: token permissions are ${PERMS} (should be 600)" "false" "false"
            fi
          fi
        fi
      else
        check "Provider $PROVIDER: token file not found — $TOKEN_PATH" "false" "false"
      fi
    done

  else
    check "providers.json is not valid JSON — re-run model-dispatch install" "false"
  fi
else
  check "providers.json not found at ${PROVIDERS_CONFIG} — run: model-dispatch install" "false"
fi

# 5b. Gemini CLI check (native CLI, separate from provider-dispatch)
if command -v gemini &>/dev/null; then
  check "gemini CLI installed (native Gemini CLI)" "true" "false"
else
  check "gemini CLI not found — install with: npm install -g @google/gemini-cli (optional, needed for gemini dispatch)" "false" "false"
fi

# 6. provider-dispatch unsets CLAUDECODE (integrity check)
if [ -f "$HOME/.local/bin/provider-dispatch" ]; then
  if grep -q "unset CLAUDECODE" "$HOME/.local/bin/provider-dispatch"; then
    check "provider-dispatch unsets CLAUDECODE (nesting protection)" "true"
  else
    check "provider-dispatch missing 'unset CLAUDECODE'" "false"
  fi
fi

# 7. tmux
if command -v tmux &>/dev/null; then
  check "tmux installed" "true"
else
  check "tmux not found — sudo apt install tmux" "false"
fi

# 8. python3
if command -v python3 &>/dev/null; then
  check "python3 installed" "true"
else
  check "python3 not found — sudo apt install python3" "false"
fi

# 9. jq
if command -v jq &>/dev/null; then
  check "jq installed" "true"
else
  check "jq not found — sudo apt install jq" "false"
fi

# 10. inotify-tools (optional, recommended)
if command -v inotifywait &>/dev/null; then
  check "inotify-tools installed (recommended for instant signal detection)" "true" "false"
else
  check "inotify-tools not found — sudo apt install inotify-tools (optional)" "false" "false"
fi

echo ""
echo "=== Summary ==="
echo "Passed: ${PASS}"
echo "Failed: ${FAIL}"
echo "Warnings: ${WARN}"
echo ""

if [ $FAIL -eq 0 ]; then
  echo "All critical checks passed!"
  echo ""
  echo "Next steps:"
  echo "  - To configure providers: model-dispatch install"
  echo "  - To test: claude-dispatch --help"
  echo "  - To use a provider: provider-dispatch <provider-name>"
  exit 0
else
  echo "WARNING: ${FAIL} critical check(s) failed. Please fix before dispatching."
  exit 1
fi
