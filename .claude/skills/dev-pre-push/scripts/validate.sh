#!/bin/bash
# Pre-push validation script
# Run by: /dev:pre-push skill OR PreToolUse hook on git push
# Exit 0 = pass, Exit 1 = fail

set -euo pipefail

echo "=== Pre-Push Validation ==="

# Step 1: Lint
echo "--- Ruff ---"
python3 -m ruff check src/ tests/ || { echo "FAIL: ruff"; exit 1; }

echo "--- Black ---"
python3 -m black --check src/ tests/ || { echo "FAIL: black"; exit 1; }

echo "--- Isort ---"
python3 -m isort --check-only --profile black src/ tests/ || { echo "FAIL: isort"; exit 1; }

# Step 2: Tests
echo "--- Tests ---"
python3 -m pytest tests/ --tb=short -q \
  --ignore=tests/e2e \
  --ignore=tests/integration \
  -m "not quarantine" \
  -p no:randomly \
  --cov=src/memory --cov-report=xml --cov-fail-under=70 || { echo "FAIL: tests"; exit 1; }

# Step 3: Security
echo "--- Security ---"
SECRETS=$(git diff main..HEAD --name-only 2>/dev/null | xargs grep -l 'api_key.*=.*["'"'"']sk-' 2>/dev/null || true)
if [ -n "$SECRETS" ]; then
  echo "WARN: Possible hardcoded secrets in: $SECRETS"
fi

echo "=== All checks passed ==="
exit 0
