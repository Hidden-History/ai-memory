#!/usr/bin/env bash
set -euo pipefail

# setup-secrets.sh - SOPS+age Encryption Setup Wizard
# SPEC-011: SOPS+age Secrets Encryption
# Purpose: Generate age key, create .sops.yaml config, and encrypt secrets interactively

# 1. Check prerequisites
for cmd in sops age-keygen; do
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "ERROR: $cmd not found. Install: brew install sops age  OR  apt install sops age"
        exit 1
    }
done

# 2. Find or generate age key
AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt}"
if [ ! -f "$AGE_KEY_FILE" ]; then
    echo "No age key found. Generating..."
    mkdir -p "$(dirname "$AGE_KEY_FILE")"
    age-keygen -o "$AGE_KEY_FILE"
    chmod 600 "$AGE_KEY_FILE"
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║  Age key generated at: $AGE_KEY_FILE"
    echo "║"
    echo "║  ⚠️  CRITICAL: Back up this file immediately!                        ║"
    echo "║"
    echo "║  Without this key, you CANNOT decrypt your secrets. Recommended:     ║"
    echo "║    1. Copy to secure password manager (1Password, Bitwarden, etc.)   ║"
    echo "║    2. Store encrypted backup on separate device/cloud storage        ║"
    echo "║    3. Print physical copy and store in secure location               ║"
    echo "║"
    echo "║  NEVER commit this key to Git. NEVER share via unencrypted channels. ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""
fi

AGE_PUBLIC_KEY=$(grep "public key:" "$AGE_KEY_FILE" | awk '{print $NF}')

# 3. Create .sops.yaml if not present
# Find repo root, fallback to parent of script directory if not in git repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "${SCRIPT_DIR}/..")"
SOPS_CONFIG="$REPO_ROOT/.sops.yaml"
if [ ! -f "$SOPS_CONFIG" ]; then
    cat > "$SOPS_CONFIG" <<EOF
creation_rules:
  - path_regex: secrets\\.enc\\.yaml\$
    age: >-
      $AGE_PUBLIC_KEY
EOF
    echo "Created $SOPS_CONFIG"
fi

# 4. Collect secrets interactively
SECRETS_FILE="docker/secrets.enc.yaml"
TEMPLATE="docker/secrets.template.yaml"

if [ -f "$SECRETS_FILE" ]; then
    echo "Encrypted secrets file already exists: $SECRETS_FILE"
    echo "To edit: sops $SECRETS_FILE"
    exit 0
fi

TEMP_FILE=$(mktemp)
trap 'rm -f "$TEMP_FILE"' EXIT

cp "$TEMPLATE" "$TEMP_FILE"

echo ""
echo "Enter your Qdrant API key:"
read -s -r QDRANT_KEY

# Use Python to safely substitute secrets (avoids sed portability and delimiter issues)
QDRANT_KEY_VALUE="$QDRANT_KEY" python3 - "$TEMP_FILE" <<'PYEOF'
import sys, os, yaml
temp_file = sys.argv[1]
with open(temp_file, 'r') as f:
    data = yaml.safe_load(f)
data['QDRANT_API_KEY'] = os.environ['QDRANT_KEY_VALUE']
with open(temp_file, 'w') as f:
    yaml.dump(data, f, default_flow_style=False)
PYEOF

# Optional: GitHub token (if enabled)
read -r -p "Configure GitHub token? [y/N]: " GITHUB_YN
if [[ "$GITHUB_YN" =~ ^[Yy]$ ]]; then
    echo "Enter GitHub PAT (fine-grained):"
    read -s -r GH_TOKEN
    GH_TOKEN_VALUE="$GH_TOKEN" python3 - "$TEMP_FILE" <<'PYEOF'
import sys, os, yaml
temp_file = sys.argv[1]
with open(temp_file, 'r') as f:
    data = yaml.safe_load(f)
data['GITHUB_TOKEN'] = os.environ['GH_TOKEN_VALUE']
with open(temp_file, 'w') as f:
    yaml.dump(data, f, default_flow_style=False)
PYEOF
fi

# 5. Encrypt and save
sops -e "$TEMP_FILE" > "$SECRETS_FILE"
echo "Secrets encrypted and saved to $SECRETS_FILE"
echo "To edit later: sops $SECRETS_FILE"
