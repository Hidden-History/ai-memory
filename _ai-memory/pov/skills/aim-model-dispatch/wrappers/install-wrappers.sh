#!/bin/bash
# install-wrappers.sh — Install model-dispatch wrappers to ~/.local/bin
# Non-destructive, re-runnable — preserves existing wrappers

set -uo pipefail

SKILL_DIR="${MODEL_DISPATCH_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}"
WRAPPERS_DIR="${SKILL_DIR}/wrappers"
LOCAL_BIN="$HOME/.local/bin"

# Validate skill directory structure
if [ ! -d "$SKILL_DIR" ]; then
  echo "Error: SKILL_DIR not found: $SKILL_DIR" >&2
  exit 1
fi

# Create ~/.local/bin if needed
mkdir -p "$LOCAL_BIN" || {
  echo "Error: Cannot create $LOCAL_BIN" >&2
  exit 1
}

# Check if ~/.local/bin is in PATH
if ! echo ":$PATH:" | grep -q ":${HOME}/.local/bin:"; then
  echo "Warning: ~/.local/bin is not in PATH. Add to your shell profile:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo ""
fi

install_wrapper() {
  local name="$1"
  local src="${WRAPPERS_DIR}/${name}.sh"
  local dst="${LOCAL_BIN}/${name}"

  if [ ! -f "$src" ]; then
    echo "Error: Source file not found: $src" >&2
    return 1
  fi

  # Copy wrapper (overwrite existing)
  cp "$src" "$dst" || {
    echo "Error: Cannot copy $src to $dst" >&2
    return 1
  }

  # Set executable permission
  chmod +x "$dst" || {
    echo "Error: Cannot chmod +x $dst" >&2
    return 1
  }

  echo "Installed: $dst"
  return 0
}

echo "Installing model-dispatch wrappers to $LOCAL_BIN..."

# Install all wrappers
FAILED=0
for wrapper in claude-dispatch openrouter-claude; do
  if ! install_wrapper "$wrapper"; then
    FAILED=$((FAILED + 1))
  fi
done

# ollama-claude — check if already installed (from ollama-dispatch or manual)
if command -v ollama-claude &>/dev/null; then
    echo "[OK] ollama-claude already installed at $(command -v ollama-claude)"
else
    echo "[SKIP] ollama-claude not found — install via ollama-dispatch skill or manually"
fi

echo ""
if [ $FAILED -eq 0 ]; then
  echo "All wrappers installed successfully."
  echo ""
  echo "Verify installation:"
  echo "  which claude-dispatch"
  echo "  which openrouter-claude"
  echo ""
  echo "If wrappers are not found, ensure ~/.local/bin is in your PATH."
  exit 0
else
  echo "WARNING: $FAILED wrapper(s) failed to install." >&2
  exit 1
fi
