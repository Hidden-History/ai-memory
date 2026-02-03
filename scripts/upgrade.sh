#!/bin/bash
#
# AI Memory Upgrade Script
#
# Performs safe upgrade with automatic backup:
# 1. Backup current Qdrant data
# 2. Pull latest code from git
# 3. Run installer in upgrade mode
# 4. Verify installation
#
# Usage:
#   ./scripts/upgrade.sh                           # Upgrade from current branch
#   ./scripts/upgrade.sh --branch fix/sprint-xxx   # Upgrade from specific branch
#   ./scripts/upgrade.sh --skip-backup             # Skip backup (not recommended)
#
# Exit codes:
#   0 = Success
#   1 = Error (invalid args, backup failed, install failed, etc.)
#   2 = Another upgrade already in progress
#

set -e  # Exit on error
set -u  # Treat unset variables as error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LOCK_FILE="/tmp/ai-memory-upgrade.lock"

# Cleanup function for lock file
cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Check for concurrent upgrade
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "unknown")
    echo -e "${RED}Error: Another upgrade is in progress (PID: $LOCK_PID)${NC}"
    echo "  Lock file: $LOCK_FILE"
    echo "  If no upgrade is running, remove the lock file manually."
    exit 2
fi
echo $$ > "$LOCK_FILE"

# Parse arguments
BRANCH="${BRANCH:-}"  # Initialize to empty string for set -u compatibility
SKIP_BACKUP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --branch|-b)
            BRANCH="${2:-}"
            if [ -z "$BRANCH" ]; then
                echo -e "${RED}Error: --branch requires a branch name${NC}"
                exit 1
            fi
            shift 2
            ;;
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--branch BRANCH] [--skip-backup]"
            echo ""
            echo "Options:"
            echo "  --branch, -b BRANCH   Upgrade from specific git branch"
            echo "  --skip-backup         Skip database backup (not recommended)"
            echo "  --help, -h            Show this help"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo ""
echo "============================================================"
echo "  AI Memory Upgrade"
echo "============================================================"
echo ""

# Check if AI Memory is installed
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${RED}Error: AI Memory not installed at $INSTALL_DIR${NC}"
    echo "Run install.sh first to install AI Memory."
    exit 1
fi

echo "  Install directory: $INSTALL_DIR"
echo "  Repository: $REPO_DIR"
[ -n "${BRANCH:-}" ] && echo "  Target branch: $BRANCH"
echo ""

# Step 1: Backup
if [ "$SKIP_BACKUP" = false ]; then
    echo -e "${YELLOW}Step 1: Creating backup...${NC}"

    if python3 "$SCRIPT_DIR/backup_qdrant.py"; then
        echo -e "${GREEN}  ✓ Backup complete${NC}"
    else
        echo -e "${RED}  ✗ Backup failed${NC}"
        echo "  Use --skip-backup to proceed without backup (not recommended)"
        exit 1
    fi
else
    echo -e "${YELLOW}Step 1: Skipping backup (--skip-backup)${NC}"
fi

echo ""

# Step 2: Pull latest code
echo -e "${YELLOW}Step 2: Pulling latest code...${NC}"

cd "$REPO_DIR"

# Get current version before update
CURRENT_VERSION=$(cat "$INSTALL_DIR/version.txt" 2>/dev/null || echo "0.0.0")

if [ -n "$BRANCH" ]; then
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    git pull
fi

# Get new version after update
NEW_VERSION=$(cat "$REPO_DIR/version.txt" 2>/dev/null || echo "unknown")

echo -e "${GREEN}  ✓ Code updated${NC}"
echo "  Current version: $CURRENT_VERSION"
echo "  New version: $NEW_VERSION"

if [ "$CURRENT_VERSION" = "$NEW_VERSION" ]; then
    echo -e "${YELLOW}  ! Already at version $CURRENT_VERSION (reinstalling anyway)${NC}"
fi
echo ""

# Step 3: Run installer
echo -e "${YELLOW}Step 3: Running installer...${NC}"

if [ -f "$REPO_DIR/install.sh" ]; then
    bash "$REPO_DIR/install.sh" --upgrade
    echo -e "${GREEN}  ✓ Installation complete${NC}"
else
    echo -e "${RED}  ✗ install.sh not found${NC}"
    exit 1
fi

echo ""

# Step 4: Verify
echo -e "${YELLOW}Step 4: Verifying installation...${NC}"

if python3 "$SCRIPT_DIR/health-check.py"; then
    echo -e "${GREEN}  ✓ Health check passed${NC}"
else
    echo -e "${YELLOW}  ! Health check had warnings (see above)${NC}"
fi

echo ""
echo "============================================================"
echo -e "${GREEN}  ✓ Upgrade complete${NC}"
echo ""
echo "  To rollback, use:"
echo "    python3 $SCRIPT_DIR/restore_qdrant.py <backup_dir>"
echo "============================================================"
echo ""
