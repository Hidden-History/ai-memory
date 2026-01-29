#!/usr/bin/env bash
# install.sh - AI Memory Module Installer
# Version: 1.0.1
# Description: Single-command installer for complete memory system
# Usage: ./install.sh [PROJECT_PATH] [PROJECT_NAME]
#        ./install.sh ~/projects/my-app           # Uses directory name as project ID
#        ./install.sh ~/projects/my-app my-custom-id  # Custom project ID
#
# Exit codes:
#   0 = Success
#   1 = Failure (prerequisite check, configuration error, or service failure)
#
# 2026 Best Practices Applied:
#   - set -euo pipefail for strict error handling
#   - lsof for precise port conflict detection
#   - Docker Compose V2 with service_healthy conditions
#   - Localhost-only bindings for security
#   - NO FALLBACKS - explicit error messages with actionable steps
#
# Based on research:
#   - Docker Compose Health Checks: https://docs.docker.com/compose/how-tos/startup-order/
#   - Bash set -euo pipefail: https://vaneyckt.io/posts/safer_bash_scripts_with_set_euxo_pipefail/
#   - Port conflict detection: https://www.cyberciti.biz/faq/unix-linux-check-if-port-is-in-use-command/

set -euo pipefail

# Script directory for relative path resolution
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Project path handling - accept target project as argument
# Usage: ./install.sh [PROJECT_PATH] [PROJECT_NAME]
PROJECT_PATH="${1:-.}"
PROJECT_PATH=$(cd "$PROJECT_PATH" 2>/dev/null && pwd || pwd)
PROJECT_NAME="${2:-$(basename "$PROJECT_PATH")}"  # Optional second arg or derived from path

# Cleanup handler for interrupts (SIGINT/SIGTERM)
# Per https://vaneyckt.io/posts/safer_bash_scripts_with_set_euxo_pipefail/
INSTALL_STARTED=false
cleanup() {
    local exit_code=$?
    if [[ "$INSTALL_STARTED" = true && $exit_code -ne 0 ]]; then
        echo ""
        log_warning "Installation interrupted (exit code: $exit_code)"

        # Stop Docker services ONLY in full install mode
        # In add-project mode, services are shared/pre-existing - don't touch them!
        if [[ "${INSTALL_MODE:-full}" == "full" && -f "$INSTALL_DIR/docker/docker-compose.yml" ]]; then
            echo ""
            echo "[INFO] Stopping Docker services..."
            cd "$INSTALL_DIR/docker" && docker compose down --timeout 5 2>/dev/null || true
            echo "[INFO] Docker services stopped"
        fi

        echo ""
        if [[ "${INSTALL_MODE:-full}" == "add-project" ]]; then
            echo "Project setup failed. Shared installation at $INSTALL_DIR is intact."
            echo "To retry: ./install.sh \"$PROJECT_PATH\" \"$PROJECT_NAME\""
        else
            echo "Partial installation exists at: $INSTALL_DIR"
            echo "To clean up and retry:"
            echo "  rm -rf $INSTALL_DIR"
            echo "  ./install.sh"
        fi
    fi
}
trap cleanup EXIT

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration with environment variable overrides
INSTALL_DIR="${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}"
QDRANT_PORT="${AI_MEMORY_QDRANT_PORT:-26350}"
EMBEDDING_PORT="${AI_MEMORY_EMBEDDING_PORT:-28080}"
MONITORING_PORT="${AI_MEMORY_MONITORING_PORT:-28000}"
STREAMLIT_PORT="${AI_MEMORY_STREAMLIT_PORT:-28501}"
CONTAINER_PREFIX="${AI_MEMORY_CONTAINER_PREFIX:-ai-memory}"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration flags (set by interactive prompts or environment)
INSTALL_MONITORING="${INSTALL_MONITORING:-}"
SEED_BEST_PRACTICES="${SEED_BEST_PRACTICES:-}"
NON_INTERACTIVE="${NON_INTERACTIVE:-false}"
INSTALL_MODE="${INSTALL_MODE:-full}"  # full or add-project (set by check_existing_installation)

# Prompt for project name (group_id for Qdrant isolation)
configure_project_name() {
    # Skip if non-interactive or already set via command line arg
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        log_info "Using project name: $PROJECT_NAME"
        return 0
    fi

    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  Project Configuration                                      │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
    echo "📁 Project directory: $PROJECT_PATH"
    echo ""
    echo "   The project name is used to isolate memories in Qdrant."
    echo "   Each project gets its own memory space (group_id)."
    echo ""
    read -p "   Project name [$PROJECT_NAME]: " custom_name
    if [[ -n "$custom_name" ]]; then
        PROJECT_NAME="$custom_name"
    fi
    echo ""
    log_info "Project name set to: $PROJECT_NAME"
}

# Interactive configuration prompts
configure_options() {
    # Skip prompts if running non-interactively or if all options pre-set
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        log_info "Non-interactive mode - using defaults/environment variables"
        INSTALL_MONITORING="${INSTALL_MONITORING:-false}"
        SEED_BEST_PRACTICES="${SEED_BEST_PRACTICES:-true}"
        return 0
    fi

    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  Optional Components                                        │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""

    # Monitoring Dashboard
    if [[ -z "$INSTALL_MONITORING" ]]; then
        echo "📊 Monitoring Dashboard"
        echo "   Includes: Streamlit browser, Grafana dashboards, Prometheus metrics"
        echo "   Ports: 28501 (Streamlit), 23000 (Grafana), 29090 (Prometheus)"
        echo "   Adds ~500MB disk usage, ~200MB RAM when running"
        echo ""
        read -p "   Install monitoring dashboard? [y/N]: " monitoring_choice
        if [[ "$monitoring_choice" =~ ^[Yy]$ ]]; then
            INSTALL_MONITORING="true"
        else
            INSTALL_MONITORING="false"
        fi
        echo ""
    fi

    # Best Practices Seeding
    if [[ -z "$SEED_BEST_PRACTICES" ]]; then
        echo "📚 Best Practices Seeding"
        echo "   Pre-populates database with coding patterns (Python, Docker, Git)"
        echo "   Claude will retrieve these during sessions to give better advice"
        echo "   Adds ~50 pattern entries to the best_practices collection"
        echo ""
        read -p "   Seed best practices? [Y/n]: " seed_choice
        if [[ "$seed_choice" =~ ^[Nn]$ ]]; then
            SEED_BEST_PRACTICES="false"
        else
            SEED_BEST_PRACTICES="true"
        fi
        echo ""
    fi

    # Summary
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  Installation Summary                                       │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│  Core Services (always installed):                          │"
    echo "│    ✓ Qdrant vector database (port $QDRANT_PORT)                   │"
    echo "│    ✓ Embedding service (port $EMBEDDING_PORT)                     │"
    echo "│    ✓ Claude Code hooks (session_start, post_tool, stop)     │"
    echo "│                                                             │"
    if [[ "$INSTALL_MONITORING" == "true" ]]; then
        echo "│  Optional Components:                                       │"
        echo "│    ✓ Monitoring dashboard (Streamlit, Grafana, Prometheus)  │"
    fi
    if [[ "$SEED_BEST_PRACTICES" == "true" ]]; then
        echo "│    ✓ Best practices patterns (Python, Docker, Git)          │"
    fi
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""

    read -p "Proceed with installation? [Y/n]: " proceed_choice
    if [[ "$proceed_choice" =~ ^[Nn]$ ]]; then
        echo ""
        log_info "Installation cancelled by user"
        exit 0
    fi
    echo ""
}

# Main orchestration function
main() {
    INSTALL_STARTED=true  # Enable cleanup handler

    echo ""
    echo "========================================"
    echo "  AI Memory Module Installer"
    echo "========================================"
    echo ""
    echo "Target project: $PROJECT_PATH"
    echo "Project name: $PROJECT_NAME"
    echo "Shared installation: $INSTALL_DIR"
    echo "Qdrant port: $QDRANT_PORT"
    echo "Embedding port: $EMBEDDING_PORT"
    echo ""

    # NFR-I5: Idempotent installation - safe to run multiple times
    # Now supports add-project mode for multi-project installations
    # IMPORTANT: Must run BEFORE check_prerequisites to skip port checks in add-project mode
    check_existing_installation

    # Prompt for project name (allows custom group_id for Qdrant isolation)
    configure_project_name

    check_prerequisites
    detect_platform

    # Full install steps - create shared infrastructure
    if [[ "$INSTALL_MODE" == "full" ]]; then
        # Interactive configuration (unless non-interactive mode)
        configure_options

        create_directories
        copy_files
        configure_environment
        start_services
        wait_for_services
        setup_collections
        copy_env_template
        run_health_check
        seed_best_practices
    else
        log_info "Skipping shared infrastructure setup (add-project mode)"
        # BUG-028: Update shared scripts to ensure compatibility with this installer version
        update_shared_scripts
        # Verify services are running in add-project mode
        verify_services_running
    fi

    # Project-level setup - runs for both modes
    create_project_symlinks
    configure_project_hooks
    verify_project_hooks

    show_success_message
}

# Idempotency check - detect existing installation (NFR-I5)
# Now supports both full install and add-project mode (TECH-DEBT-013)
check_existing_installation() {
    local existing=false
    local services_running=false

    # Check if shared installation directory exists with key files
    if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/docker/docker-compose.yml" ]]; then
        existing=true
        log_info "Existing AI Memory installation detected at $INSTALL_DIR"
    fi

    # Check if Docker services are already running
    if command -v docker &> /dev/null && docker info &> /dev/null; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "ai-memory\|qdrant"; then
            services_running=true
            log_info "AI Memory services are currently running"
        fi
    fi

    # Handle existing installation - offer add-project mode
    if [[ "$existing" = true ]]; then
        echo ""
        log_info "Found existing AI Memory installation"
        echo ""
        echo "Options:"
        echo "  1. Add project to existing installation (recommended)"
        echo "     - Reuses shared Docker services"
        echo "     - Creates project-level hooks via symlinks"
        echo "  2. Reinstall shared infrastructure (stop services, update files, restart)"
        echo "  3. Abort installation"
        echo ""

        # Check for non-interactive mode
        if [[ "${AI_MEMORY_ADD_PROJECT_MODE:-}" = "true" ]]; then
            log_info "AI_MEMORY_ADD_PROJECT_MODE=true - using add-project mode"
            INSTALL_MODE="add-project"
            return 0
        elif [[ "${AI_MEMORY_FORCE_REINSTALL:-}" = "true" ]]; then
            log_info "AI_MEMORY_FORCE_REINSTALL=true - proceeding with full reinstall"
            INSTALL_MODE="full"
            handle_reinstall "$services_running"
            return 0
        fi

        # Interactive prompt
        read -r -p "Choose [1/2/3]: " choice
        case "$choice" in
            1)
                log_info "Adding project to existing installation..."
                INSTALL_MODE="add-project"
                ;;
            2)
                log_info "Reinstalling shared infrastructure..."
                INSTALL_MODE="full"
                handle_reinstall "$services_running"
                ;;
            3|*)
                log_info "Installation aborted by user"
                exit 0
                ;;
        esac
    else
        # No existing installation - do full install
        INSTALL_MODE="full"
        log_info "No existing installation found - will perform full install"
    fi
}

# Handle reinstallation - stop services, clean up if needed
handle_reinstall() {
    local services_running=$1

    if [[ "$services_running" = true ]]; then
        log_info "Stopping existing services..."
        if [[ -f "$INSTALL_DIR/docker/docker-compose.yml" ]]; then
            (cd "$INSTALL_DIR/docker" && docker compose down 2>/dev/null) || true
        fi
        log_success "Services stopped"
    fi

    log_info "Proceeding with reinstallation..."
}

# Update shared scripts for add-project mode compatibility (BUG-028, BUG-034)
# When adding a project to an existing installation, ensure the shared
# scripts AND hook scripts are compatible with the installer version being used.
update_shared_scripts() {
    log_info "Updating shared scripts for compatibility..."

    # Ensure directories exist
    mkdir -p "$INSTALL_DIR/scripts"
    mkdir -p "$INSTALL_DIR/.claude/hooks/scripts"

    # Copy all Python scripts from repo to shared installation
    local updated_count=0
    for script in "$SCRIPT_DIR"/*.py; do
        if [[ -f "$script" ]]; then
            cp "$script" "$INSTALL_DIR/scripts/"
            ((updated_count++)) || true
        fi
    done

    # BUG-034: Also update hook scripts in shared installation
    # This ensures projects get the latest hooks when added
    local hooks_source="$SCRIPT_DIR/../.claude/hooks/scripts"
    local hooks_count=0
    local archived_count=0
    if [[ -d "$hooks_source" ]]; then
        # Build list of source hook names for stale detection
        local source_hooks=()
        for hook in "$hooks_source"/*.py; do
            if [[ -f "$hook" ]]; then
                source_hooks+=("$(basename "$hook")")
                cp "$hook" "$INSTALL_DIR/.claude/hooks/scripts/"
                ((hooks_count++)) || true
            fi
        done

        # Archive stale hooks not in source (BUG-034 cleanup)
        local hooks_dest="$INSTALL_DIR/.claude/hooks/scripts"
        local archive_dir="$INSTALL_DIR/.claude/hooks/scripts/.archived"
        for existing in "$hooks_dest"/*.py; do
            if [[ -f "$existing" ]]; then
                local basename_hook=$(basename "$existing")
                local is_source=false
                for src in "${source_hooks[@]}"; do
                    if [[ "$src" == "$basename_hook" ]]; then
                        is_source=true
                        break
                    fi
                done
                if [[ "$is_source" == false ]]; then
                    mkdir -p "$archive_dir"
                    mv "$existing" "$archive_dir/"
                    ((archived_count++)) || true
                fi
            fi
        done

        # Also sync src/memory modules
        if [[ -d "$SCRIPT_DIR/../src/memory" ]]; then
            cp -r "$SCRIPT_DIR/../src/memory" "$INSTALL_DIR/src/" 2>/dev/null || true
        fi
    fi

    if [[ $updated_count -gt 0 || $hooks_count -gt 0 ]]; then
        log_success "Updated $updated_count shared scripts, $hooks_count hook scripts"
        if [[ $archived_count -gt 0 ]]; then
            log_info "Archived $archived_count stale hook scripts to .archived/"
        fi
    else
        log_warning "No scripts found to update"
    fi
}

# Prerequisite checking (AC 7.1.3)
check_prerequisites() {
    log_info "Checking prerequisites..."

    local failed=false

    # Check Docker installation
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed."
        echo ""
        echo "Please install Docker first:"
        echo "  Ubuntu/Debian: sudo apt install docker.io docker-compose-plugin"
        echo "  macOS: brew install --cask docker"
        echo "  Windows: Install Docker Desktop with WSL2 backend"
        echo ""
        echo "For more information: https://docs.docker.com/engine/install/"
        failed=true
    fi

    # Check Docker daemon is running
    if command -v docker &> /dev/null && ! docker info &> /dev/null; then
        show_docker_not_running_error
    fi

    # Check Docker Compose V2 (REQUIRED for condition: service_healthy)
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose V2 is not available."
        echo ""
        echo "Please install Docker Compose V2:"
        echo "  Ubuntu/Debian: sudo apt install docker-compose-plugin"
        echo "  macOS: Included with Docker Desktop"
        echo ""
        echo "NOTE: V2 is REQUIRED for proper health check support (condition: service_healthy)"
        echo "      V1 (docker-compose) is not supported."
        echo ""
        echo "For more information: https://docs.docker.com/compose/install/"
        failed=true
    fi

    # Check Python 3.10+ (REQUIRED for async support and improved type hints)
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed."
        echo ""
        echo "Please install Python 3.10 or higher:"
        echo "  Ubuntu/Debian: sudo apt install python3"
        echo "  macOS: brew install python@3.10"
        echo ""
        failed=true
    else
        # Extract Python version using python itself (more reliable than bc)
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

        # Compare version (requires Python 3.10+)
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" &> /dev/null; then
            log_info "Python $PYTHON_VERSION detected"
        else
            show_python_version_error "$PYTHON_VERSION"
        fi
    fi

    # Check Claude Code CLI (WARNING not ERROR - hooks won't work until installed)
    if ! command -v claude &> /dev/null; then
        log_warning "Claude Code CLI not found."
        log_warning "Hooks will be configured but won't work until Claude Code is installed."
        log_warning "Install from: https://claude.ai/code"
    fi

    # Check port availability using ss (primary) or lsof (fallback)
    # Per 2025/2026 best practices: ss is faster and more universally available
    # SKIP in add-project mode - ports are expected to be in use by existing services
    if [[ "${INSTALL_MODE:-full}" == "full" ]]; then
        check_port_available "$QDRANT_PORT" "Qdrant"
        check_port_available "$EMBEDDING_PORT" "Embedding Service"
        check_port_available "$MONITORING_PORT" "Monitoring API"
        check_port_available "$STREAMLIT_PORT" "Streamlit Dashboard"
    else
        log_info "Skipping port checks (add-project mode - reusing existing services)"
    fi

    # Check disk space (requires ~10GB: Qdrant 1GB, Nomic model 7GB, Docker images 2GB)
    check_disk_space

    # Fail immediately if any prerequisite missing (NO FALLBACKS as requested)
    if [ "$failed" = true ]; then
        log_error "Prerequisites not met. Aborting installation."
        echo ""
        echo "NO FALLBACK: This installer follows strict fail-fast principles."
        echo "You must resolve all prerequisite issues before proceeding."
        exit 1
    fi

    log_success "All prerequisites satisfied"
}

# Port availability check using ss (primary) or lsof (fallback) - 2026 best practice
# Per https://serveravatar.com/netstat-ss-and-lsof/ - ss is faster and more universally available
check_port_available() {
    local port=$1
    local service=$2
    local port_in_use=false

    # Primary: Use ss (faster, more universally available per 2025/2026 best practices)
    if command -v ss &> /dev/null; then
        if ss -tulpn 2>/dev/null | grep -q ":${port} "; then
            port_in_use=true
        fi
    # Fallback: Use lsof if ss not available
    elif command -v lsof &> /dev/null; then
        if lsof -i :"$port" &> /dev/null; then
            port_in_use=true
        fi
    else
        log_warning "Neither ss nor lsof available - skipping port $port check"
        return 0
    fi

    if [ "$port_in_use" = true ]; then
        show_port_conflict_error "$port" "$service"
    fi
}

# Disk space check - requires at least 5GB free (AC 7.1.8)
# Full installation needs: Qdrant ~1GB, Nomic Embed Code ~7GB, Docker images ~2GB
check_disk_space() {
    local required_gb=5
    local install_path="${INSTALL_DIR:-$HOME}"

    # Use parent directory if INSTALL_DIR doesn't exist yet
    if [[ ! -d "$install_path" ]]; then
        install_path="$(dirname "$install_path")"
    fi

    # Get available space in GB (portable across Linux/macOS)
    local available_kb
    available_kb=$(df -k "$install_path" 2>/dev/null | tail -1 | awk '{print $4}')

    if [[ -z "$available_kb" ]]; then
        log_warning "Could not determine disk space - proceeding anyway"
        return 0
    fi

    # Convert KB to GB (integer division)
    local available_gb=$((available_kb / 1024 / 1024))

    if [[ $available_gb -lt $required_gb ]]; then
        show_disk_space_error
    else
        log_info "Disk space: ${available_gb}GB available (${required_gb}GB required)"
    fi
}

# Platform detection (AC 7.1.4)
detect_platform() {
    log_info "Detecting platform..."

    PLATFORM="unknown"
    ARCH=$(uname -m)

    case "$(uname -s)" in
        Linux*)
            # Check for WSL2 by examining /proc/version
            if grep -qi microsoft /proc/version 2>/dev/null; then
                PLATFORM="wsl"
                log_info "Detected: WSL2 on Windows ($ARCH)"
            else
                PLATFORM="linux"
                log_info "Detected: Linux ($ARCH)"
            fi
            ;;
        Darwin*)
            PLATFORM="macos"
            if [[ "$ARCH" == "arm64" ]]; then
                log_info "Detected: macOS (Apple Silicon)"
            else
                log_info "Detected: macOS (Intel)"
            fi
            ;;
        *)
            log_error "Unsupported platform: $(uname -s)"
            echo ""
            echo "Supported platforms:"
            echo "  - Linux (x86_64, arm64)"
            echo "  - macOS (Intel, Apple Silicon)"
            echo "  - WSL2 on Windows"
            echo ""
            echo "NO FALLBACK: This installer does not support $(uname -s)."
            exit 1
            ;;
    esac

    # Export for use in other functions
    export PLATFORM ARCH
}

# Directory structure creation (AC 7.1.5)
create_directories() {
    log_info "Creating directory structure..."

    # Skip confirmation in non-interactive mode
    if [[ "$NON_INTERACTIVE" != "true" ]]; then
        echo ""
        echo "The installer will create the following directories:"
        echo "  📁 $INSTALL_DIR/"
        echo "     ├── docker/              (Docker Compose configs)"
        echo "     ├── src/memory/          (Python memory modules)"
        echo "     ├── scripts/             (Management scripts)"
        echo "     ├── .claude/hooks/scripts/ (Hook implementations)"
        echo "     └── logs/                (Application logs)"
        echo ""
        echo "  📁 $HOME/.claude-memory/   (Private queue/logs, chmod 700)"
        echo ""
        read -p "Proceed with directory creation? [Y/n]: " confirm
        if [[ "$confirm" =~ ^[Nn]$ ]]; then
            echo ""
            log_info "Installation cancelled by user"
            exit 0
        fi
        echo ""
    fi

    # Create main installation directory and subdirectories
    mkdir -p "$INSTALL_DIR"/{docker,src/memory,scripts,.claude/hooks/scripts,.claude/skills,.claude/agents,logs}

    # Create queue directory with restricted permissions (security best practice 2026)
    mkdir -p "$HOME/.claude-memory"
    chmod 700 "$HOME/.claude-memory"  # Private queue/logs directory

    log_success "Directory structure created at $INSTALL_DIR"
    log_info "Private queue directory: $HOME/.claude-memory (chmod 700)"
}

# File copying (AC 7.1.6)
copy_files() {
    log_info "Copying files..."

    # Determine source directory (script location or current directory)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Try script directory first (for installed scripts)
    if [[ -f "$SCRIPT_DIR/../docker/docker-compose.yml" ]]; then
        SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
        log_info "Using source directory: $SOURCE_DIR"
    # Fall back to current directory (for in-repo execution)
    elif [[ -f "./docker/docker-compose.yml" ]]; then
        SOURCE_DIR="$(pwd)"
        log_info "Using current directory as source: $SOURCE_DIR"
    else
        log_error "Cannot find source files (docker-compose.yml)."
        echo ""
        echo "Expected structure:"
        echo "  ./docker/docker-compose.yml"
        echo "  ./src/memory/*.py"
        echo "  ./scripts/*.sh"
        echo "  ./.claude/hooks/scripts/*.py"
        echo ""
        echo "Run from repository root or ensure install.sh is in scripts/ directory."
        exit 1
    fi

    # Copy core files (preserve directory structure)
    log_info "Copying docker configuration..."
    cp -r "$SOURCE_DIR/docker/"* "$INSTALL_DIR/docker/"
    # BUG-040: Explicitly copy dotfiles (.env, .gitignore, etc.) - bash glob * doesn't match dotfiles
    cp "$SOURCE_DIR/docker/".* "$INSTALL_DIR/docker/" 2>/dev/null || true

    log_info "Copying Python memory modules..."
    cp -r "$SOURCE_DIR/src/memory/"* "$INSTALL_DIR/src/memory/"

    log_info "Copying scripts..."
    cp -r "$SOURCE_DIR/scripts/"* "$INSTALL_DIR/scripts/"

    log_info "Copying Claude Code hooks..."
    cp -r "$SOURCE_DIR/.claude/hooks/"* "$INSTALL_DIR/.claude/hooks/"

    # Copy Claude Code skills (core ai-memory functionality)
    if [[ -d "$SOURCE_DIR/.claude/skills" ]]; then
        log_info "Copying Claude Code skills..."
        cp -r "$SOURCE_DIR/.claude/skills/"* "$INSTALL_DIR/.claude/skills/" 2>/dev/null || true
    fi

    # Copy Claude Code agents (core ai-memory functionality)
    if [[ -d "$SOURCE_DIR/.claude/agents" ]]; then
        log_info "Copying Claude Code agents..."
        cp -r "$SOURCE_DIR/.claude/agents/"* "$INSTALL_DIR/.claude/agents/" 2>/dev/null || true
    fi

    # Copy templates for best practices seeding
    if [[ -d "$SOURCE_DIR/templates" ]]; then
        log_info "Copying templates..."
        mkdir -p "$INSTALL_DIR/templates"
        cp -r "$SOURCE_DIR/templates/"* "$INSTALL_DIR/templates/"
    fi

    # Make scripts executable (both .py and .sh files)
    log_info "Making scripts executable..."
    chmod +x "$INSTALL_DIR/scripts/"*.{py,sh} 2>/dev/null || true
    chmod +x "$INSTALL_DIR/.claude/hooks/scripts/"*.py 2>/dev/null || true

    log_success "Files copied to $INSTALL_DIR"
}

# Environment configuration (AC 7.1.6)
# BUG-040: Docker Compose runs from $INSTALL_DIR/docker/ and needs .env there
configure_environment() {
    log_info "Configuring environment..."

    local docker_env="$INSTALL_DIR/docker/.env"

    # Check if .env was copied from source (has credentials)
    if [[ -f "$docker_env" ]]; then
        log_info "Found existing docker/.env with credentials - updating paths..."

        # Update AI_MEMORY_INSTALL_DIR to actual installation path
        # This handles the case where source .env has dev repo path
        if grep -q "^AI_MEMORY_INSTALL_DIR=" "$docker_env"; then
            sed -i "s|^AI_MEMORY_INSTALL_DIR=.*|AI_MEMORY_INSTALL_DIR=$INSTALL_DIR|" "$docker_env"
            log_info "Updated AI_MEMORY_INSTALL_DIR to $INSTALL_DIR"
        else
            echo "" >> "$docker_env"
            echo "# Installation path (added by installer)" >> "$docker_env"
            echo "AI_MEMORY_INSTALL_DIR=$INSTALL_DIR" >> "$docker_env"
        fi

        log_success "Environment configured at $docker_env"
    else
        # No source .env - create minimal template (user needs to add credentials)
        log_warning "No source .env found - creating template without credentials"
        cat > "$docker_env" <<EOF
# AI Memory Module Configuration
# Generated by install.sh on $(date)
#
# WARNING: This is a minimal template. For full functionality, copy your
# configured .env from the source repository to this location.

# Container Configuration
AI_MEMORY_CONTAINER_PREFIX=$CONTAINER_PREFIX

# Port Configuration
QDRANT_PORT=$QDRANT_PORT
EMBEDDING_PORT=$EMBEDDING_PORT
MONITORING_PORT=$MONITORING_PORT
STREAMLIT_PORT=$STREAMLIT_PORT

# Installation Paths
AI_MEMORY_INSTALL_DIR=$INSTALL_DIR
QUEUE_DIR=$HOME/.claude-memory

# Platform Information
PLATFORM=$PLATFORM
ARCH=$ARCH

# Search Configuration
SIMILARITY_THRESHOLD=0.4

# =============================================================================
# CREDENTIALS (Required - add your values below)
# =============================================================================
# Generate API key: python3 -c "import secrets; print(secrets.token_urlsafe(18))"
QDRANT_API_KEY=
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=
PROMETHEUS_ADMIN_PASSWORD=
EOF
        log_warning "Please configure credentials in $docker_env"
        log_success "Environment template created at $docker_env"
    fi
}

# Service startup with 2026 security best practices (AC 7.1.7)
start_services() {
    log_info "Starting Docker services..."

    # Navigate to docker directory
    cd "$INSTALL_DIR/docker" || {
        log_error "Failed to navigate to $INSTALL_DIR/docker"
        exit 1
    }

    # Pull images first (show progress)
    log_info "Pulling Docker images (this may take a few minutes)..."
    if [[ "$INSTALL_MONITORING" == "true" ]]; then
        docker compose --profile monitoring pull
    else
        docker compose pull
    fi

    # Start core services with 2026 security best practices:
    # - Localhost-only bindings (127.0.0.1)
    # - Health checks enabled (condition: service_healthy)
    # - Security opts: no-new-privileges:true
    # - Non-root user execution where possible
    log_info "Starting services with security hardening..."
    if [[ "$INSTALL_MONITORING" == "true" ]]; then
        log_info "Including monitoring dashboard (Streamlit, Grafana, Prometheus)..."
        docker compose --profile monitoring up -d
    else
        docker compose up -d
    fi

    log_success "Docker services started"
}

# Wait for services to be healthy (AC 7.1.7)
wait_for_services() {
    log_info "Waiting for services to be ready..."
    log_info "Note: First start may take 5-10 minutes to download embedding model (~500MB)"

    # BUG-040: Increased timeout for first-time model download on slow connections
    local max_attempts=${WAIT_TIMEOUT:-600}
    local attempt=0

    # Wait for Qdrant using localhost health check (2026 best practice)
    echo -n "  Qdrant ($QDRANT_PORT): "
    while [[ $attempt -lt $max_attempts ]]; do
        if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$QDRANT_PORT/" &> /dev/null; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        # Show elapsed time every 5 seconds
        if [[ $((attempt % 5)) -eq 0 && $attempt -gt 0 ]]; then
            echo -n "${attempt}s "
        else
            echo -n "."
        fi
        sleep 1
        ((attempt++)) || true
    done

    if [[ $attempt -eq $max_attempts ]]; then
        echo -e "${RED}timeout${NC}"
        log_error "Qdrant failed to start within ${max_attempts} seconds."
        echo ""
        echo "Check logs for details:"
        echo "  cd $INSTALL_DIR/docker && docker compose logs qdrant"
        echo ""
        echo "NO FALLBACK: Service health is required for installation."
        exit 1
    fi

    # Wait for Embedding Service (with live progress)
    attempt=0
    echo -n "  Embedding ($EMBEDDING_PORT): "

    # Check if already ready (cached model)
    if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$EMBEDDING_PORT/health" &> /dev/null; then
        echo -e "${GREEN}ready${NC} (cached)"
    else
        echo "downloading model..."
        echo ""

        # Start background log tail - filter to only show progress bars and key events
        # Run in subshell so we can kill entire process group
        (docker logs -f "${CONTAINER_PREFIX}-embedding" 2>&1 | grep --line-buffered -E "Fetching|Downloading|%\||model_load|ERROR|error" | sed 's/^/    /') &
        LOG_PID=$!

        while [[ $attempt -lt $max_attempts ]]; do
            if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$EMBEDDING_PORT/health" &> /dev/null; then
                # Kill the entire log tail process group
                pkill -P $LOG_PID 2>/dev/null || true
                kill $LOG_PID 2>/dev/null || true
                echo ""
                echo -e "  Embedding ($EMBEDDING_PORT): ${GREEN}ready${NC}"
                break
            fi
            sleep 2
            ((attempt+=2)) || true
        done

        # Cleanup log tail if still running (timeout case)
        pkill -P $LOG_PID 2>/dev/null || true
        kill $LOG_PID 2>/dev/null || true

        if [[ $attempt -ge $max_attempts ]]; then
            echo -e "${RED}timeout${NC}"
            log_error "Embedding service failed to start within ${max_attempts} seconds."
            echo ""
            echo "Check logs for details:"
            echo "  cd $INSTALL_DIR/docker && docker compose logs embedding"
            echo ""
            echo "NOTE: First start downloads ~500MB model from HuggingFace (may take 5-10 min)."
            echo "      Subsequent starts load from cache (~10 seconds)."
            echo "      If this persists, check network connection and available disk space."
            echo "      You can retry with: WAIT_TIMEOUT=900 ./install.sh"
            echo ""
            echo "NO FALLBACK: Service health is required for installation."
            exit 1
        fi
    fi

    # Optional: Wait for Monitoring API (non-critical, just info)
    attempt=0
    echo -n "  Monitoring ($MONITORING_PORT): "
    while [[ $attempt -lt 30 ]]; do
        if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$MONITORING_PORT/health" &> /dev/null; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 1
        ((attempt++)) || true
    done

    if [[ $attempt -eq 30 ]]; then
        echo -e "${YELLOW}timeout (non-critical)${NC}"
        log_warning "Monitoring API did not start (this is optional)"
    fi

    # If monitoring profile was requested, wait for those services too
    if [[ "$INSTALL_MONITORING" == "true" ]]; then
        # Wait for Streamlit
        attempt=0
        echo -n "  Streamlit ($STREAMLIT_PORT): "
        while [[ $attempt -lt 60 ]]; do
            if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$STREAMLIT_PORT/" &> /dev/null; then
                echo -e "${GREEN}ready${NC}"
                break
            fi
            echo -n "."
            sleep 1
            ((attempt++)) || true
        done
        if [[ $attempt -eq 60 ]]; then
            echo -e "${YELLOW}timeout (non-critical)${NC}"
            log_warning "Streamlit dashboard did not start within 60s"
        fi

        # Wait for Grafana
        attempt=0
        echo -n "  Grafana (23000): "
        while [[ $attempt -lt 60 ]]; do
            if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:23000/api/health" &> /dev/null; then
                echo -e "${GREEN}ready${NC}"
                break
            fi
            echo -n "."
            sleep 1
            ((attempt++)) || true
        done
        if [[ $attempt -eq 60 ]]; then
            echo -e "${YELLOW}timeout (non-critical)${NC}"
            log_warning "Grafana dashboard did not start within 60s"
        fi
    fi

    log_success "All critical services ready"
}

# Initialize Qdrant collections
setup_collections() {
    log_info "Setting up Qdrant collections..."

    # Run the setup script
    if python3 "$INSTALL_DIR/scripts/setup-collections.py" 2>/dev/null; then
        log_success "Qdrant collections created (code-patterns, conventions, discussions)"
    else
        log_warning "Collection setup had issues - will be created on first use"
    fi
}

copy_env_template() {
    log_info "Copying environment template..."

    # Copy .env.example to installation directory
    if [ -f "$SCRIPT_DIR/../.env.example" ]; then
        cp "$SCRIPT_DIR/../.env.example" "$INSTALL_DIR/.env.example"
        log_success "Environment template copied to $INSTALL_DIR/.env.example"

        # Check if .env already exists
        if [ ! -f "$INSTALL_DIR/.env" ]; then
            log_info "No .env file found - using defaults"
            log_info "To customize: cp $INSTALL_DIR/.env.example $INSTALL_DIR/.env"
        else
            log_info "Existing .env file detected - keeping current configuration"
        fi
    else
        log_warning "Template .env.example not found - skipping"
    fi
}

# Verify services are running (for add-project mode)
verify_services_running() {
    log_info "Verifying AI Memory services are running..."

    # Check Qdrant
    if ! curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$QDRANT_PORT/" &> /dev/null; then
        log_error "Qdrant is not running at port $QDRANT_PORT"
        echo ""
        echo "Start services from shared installation:"
        echo "  cd $INSTALL_DIR/docker && docker compose up -d"
        exit 1
    fi

    # Check Embedding Service
    if ! curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$EMBEDDING_PORT/health" &> /dev/null; then
        log_error "Embedding service is not running at port $EMBEDDING_PORT"
        echo ""
        echo "Start services from shared installation:"
        echo "  cd $INSTALL_DIR/docker && docker compose up -d"
        exit 1
    fi

    log_success "All services are running"
}

# Create project-level symlinks to shared installation
# BUG-032: On WSL, symlinks are not visible from Windows applications (e.g., VS Code, Windows Explorer).
# We use file copies instead of symlinks on WSL to ensure cross-platform visibility.
# Trade-off: Updates to shared hooks require re-running install.sh for the project.
create_project_symlinks() {
    # Determine link method based on platform
    local link_method="symlink"
    if [[ "$PLATFORM" == "wsl" ]]; then
        link_method="copy"
        log_info "Creating project-level hook copies (WSL mode for Windows visibility)..."
    else
        log_info "Creating project-level symlinks..."
    fi

    # Skip confirmation in non-interactive mode
    if [[ "$NON_INTERACTIVE" != "true" && ! -d "$PROJECT_PATH/.claude" ]]; then
        echo ""
        echo "The installer will create the following in your project:"
        echo "  $PROJECT_PATH/.claude/"
        if [[ "$link_method" == "copy" ]]; then
            echo "     hooks/scripts/       (Copies of shared hooks - WSL mode)"
            echo ""
            echo "NOTE: On WSL, we copy files instead of creating symlinks."
            echo "      This ensures hooks are visible from Windows applications."
            echo "      If you update the shared installation, re-run this installer"
            echo "      to update the project hooks."
        else
            echo "     hooks/scripts/       (Symlinks to shared hooks)"
        fi
        echo ""
        echo "This allows Claude Code to use the memory system in your project."
        echo ""
        read -p "Proceed with project setup? [Y/n]: " confirm
        if [[ "$confirm" =~ ^[Nn]$ ]]; then
            echo ""
            log_info "Project setup cancelled by user"
            exit 0
        fi
        echo ""
    fi

    # Create project .claude directory structure
    mkdir -p "$PROJECT_PATH/.claude/hooks/scripts"

    # Link or copy hook scripts from shared install
    local file_count=0
    for script in "$INSTALL_DIR/.claude/hooks/scripts"/*.py; do
        if [[ -f "$script" ]]; then
            script_name=$(basename "$script")
            target_path="$PROJECT_PATH/.claude/hooks/scripts/$script_name"

            if [[ "$link_method" == "copy" ]]; then
                # BUG-032: Copy files on WSL for Windows visibility
                if ! cp "$script" "$target_path"; then
                    log_error "Failed to copy $script_name - check disk space and permissions"
                    exit 1
                fi
            else
                # Use symlinks on native Linux/macOS
                ln -sf "$script" "$target_path"
            fi
            ((file_count++)) || true
        fi
    done

    # Verify at least one hook file was processed
    if [[ $file_count -eq 0 ]]; then
        log_error "No hook scripts found in $INSTALL_DIR/.claude/hooks/scripts/"
        exit 1
    fi

    # BUG-035: Archive stale hooks in project directory (WSL copy mode)
    if [[ "$link_method" == "copy" ]]; then
        local archived_count=0
        local archive_dir="$PROJECT_PATH/.claude/hooks/scripts/.archived"
        for existing in "$PROJECT_PATH/.claude/hooks/scripts"/*.py; do
            if [[ -f "$existing" ]]; then
                local basename_hook=$(basename "$existing")
                # Check if this file exists in the shared install (source of truth)
                if [[ ! -f "$INSTALL_DIR/.claude/hooks/scripts/$basename_hook" ]]; then
                    mkdir -p "$archive_dir"
                    mv "$existing" "$archive_dir/"
                    ((archived_count++)) || true
                fi
            fi
        done
        if [[ $archived_count -gt 0 ]]; then
            log_info "Archived $archived_count stale project hooks to .archived/"
        fi
    fi

    # Verify files exist and are accessible
    local verification_failed=0
    for script in "$PROJECT_PATH/.claude/hooks/scripts"/*.py; do
        if [[ ! -e "$script" ]]; then
            log_error "Missing or inaccessible: $script"
            verification_failed=1
        elif [[ "$link_method" == "symlink" ]]; then
            # Additional symlink-specific checks
            if [[ ! -L "$script" ]]; then
                log_error "Not a symlink: $script"
                verification_failed=1
            fi
            # Note: -e on symlink checks if TARGET exists (broken symlink test)
        elif [[ "$link_method" == "copy" ]]; then
            # Copy-specific checks: ensure readable
            if [[ ! -r "$script" ]]; then
                log_error "Not readable: $script"
                verification_failed=1
            fi
        fi
    done

    if [[ $verification_failed -eq 1 ]]; then
        log_error "Hook file verification failed"
        exit 1
    fi

    if [[ "$link_method" == "copy" ]]; then
        log_success "Copied $file_count hook files to $PROJECT_PATH/.claude/hooks/scripts/"
        log_info "WSL note: Re-run installer after updating shared hooks to sync changes"
    else
        log_success "Created $file_count symlinks in $PROJECT_PATH/.claude/hooks/scripts/"
    fi
}

# Configure hooks for project (project-level settings.json)
configure_project_hooks() {
    log_info "Configuring project-level hooks..."

    PROJECT_SETTINGS="$PROJECT_PATH/.claude/settings.json"
    HOOKS_DIR="$INSTALL_DIR/.claude/hooks/scripts"

    # Export QDRANT_API_KEY from docker/.env for generate_settings.py (BUG-029 fix)
    # The generator reads this from environment to avoid hardcoding secrets
    # BUG-029+030 fixes:
    #   - cut -d= -f2- captures everything after first = (base64 keys contain =)
    #   - tr -d removes quotes from .env values like QDRANT_API_KEY="value"
    #   - || echo "" prevents grep exit 1 from crashing under set -e
    if [[ -f "$INSTALL_DIR/docker/.env" ]]; then
        QDRANT_API_KEY=$(grep "^QDRANT_API_KEY=" "$INSTALL_DIR/docker/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || echo "")
        export QDRANT_API_KEY
        if [[ -n "$QDRANT_API_KEY" ]]; then
            log_info "Loaded QDRANT_API_KEY from docker/.env (${#QDRANT_API_KEY} chars)"
        else
            log_warning "QDRANT_API_KEY not found or empty in docker/.env"
        fi
    else
        log_warning "docker/.env not found - QDRANT_API_KEY will be empty"
    fi

    # Check if project already has settings.json
    if [[ -f "$PROJECT_SETTINGS" ]]; then
        log_info "Existing project settings found - merging hooks..."
        python3 "$INSTALL_DIR/scripts/merge_settings.py" "$PROJECT_SETTINGS" "$HOOKS_DIR" "$PROJECT_NAME"
    else
        # Generate new project-level settings.json
        log_info "Creating new project settings at $PROJECT_SETTINGS..."
        python3 "$INSTALL_DIR/scripts/generate_settings.py" "$PROJECT_SETTINGS" "$HOOKS_DIR" "$PROJECT_NAME"
    fi

    log_success "Project hooks configured in $PROJECT_SETTINGS"
}

# Verify project hooks configuration
verify_project_hooks() {
    log_info "Verifying project hook configuration..."

    PROJECT_SETTINGS="$PROJECT_PATH/.claude/settings.json"

    # Check settings.json exists and is valid JSON
    if ! python3 -c "import json; json.load(open('$PROJECT_SETTINGS'))" 2>/dev/null; then
        log_error "Invalid JSON in $PROJECT_SETTINGS"
        exit 1
    fi

    # Verify AI_MEMORY_PROJECT_ID is set
    if ! python3 -c "
import json
import sys

settings = json.load(open('$PROJECT_SETTINGS'))
if 'env' not in settings or 'AI_MEMORY_PROJECT_ID' not in settings['env']:
    print('ERROR: AI_MEMORY_PROJECT_ID not found in settings.json')
    sys.exit(1)

project_id = settings['env']['AI_MEMORY_PROJECT_ID']
if project_id != '$PROJECT_NAME':
    print(f'ERROR: AI_MEMORY_PROJECT_ID mismatch: {project_id} != $PROJECT_NAME')
    sys.exit(1)

print(f'✓ AI_MEMORY_PROJECT_ID set to: {project_id}')
" 2>/dev/null; then
        log_error "AI_MEMORY_PROJECT_ID verification failed"
        exit 1
    fi

    log_success "Project hooks verified"
}

run_health_check() {
    log_info "Running health checks..."

    # BUG-041: Export QDRANT_API_KEY from docker/.env for authenticated health check
    if [[ -f "$INSTALL_DIR/docker/.env" ]]; then
        QDRANT_API_KEY=$(grep "^QDRANT_API_KEY=" "$INSTALL_DIR/docker/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || echo "")
        export QDRANT_API_KEY
    fi

    # Call Python health check script
    if python3 "$INSTALL_DIR/scripts/health-check.py"; then
        log_success "All health checks passed"
    else
        log_error "Health checks failed"
        echo ""
        echo "┌─────────────────────────────────────────────────────────────┐"
        echo "│  Health Check Failed - Troubleshooting Steps               │"
        echo "├─────────────────────────────────────────────────────────────┤"
        echo "│                                                             │"
        echo "│  1. Check Docker logs:                                      │"
        echo "│     cd $INSTALL_DIR/docker                                  │"
        echo "│     docker compose logs                                     │"
        echo "│                                                             │"
        echo "│  2. Restart services:                                       │"
        echo "│     docker compose restart                                  │"
        echo "│                                                             │"
        echo "│  3. Retry health check:                                     │"
        echo "│     python3 $INSTALL_DIR/scripts/health-check.py            │"
        echo "│                                                             │"
        echo "│  4. See troubleshooting guide:                              │"
        echo "│     cat $INSTALL_DIR/TROUBLESHOOTING.md                     │"
        echo "│                                                             │"
        echo "└─────────────────────────────────────────────────────────────┘"
        echo ""

        # NO FALLBACK: Exit on health check failure
        exit 1
    fi
}

# Seed best practices collection (AC 7.5.4 - optional)
seed_best_practices() {
    if [[ "${SEED_BEST_PRACTICES:-false}" == "true" ]]; then
        log_info "Seeding best_practices collection..."

        # Check if templates directory exists (V2.0: renamed from best_practices to conventions)
        if [[ ! -d "$INSTALL_DIR/templates/conventions" ]]; then
            log_warning "Templates directory not found - skipping seeding"
            log_info "To seed manually later:"
            log_info "  python3 $INSTALL_DIR/scripts/memory/seed_best_practices.py"
            return 0
        fi

        # Run seeding script
        if python3 "$INSTALL_DIR/scripts/memory/seed_best_practices.py" --templates-dir "$INSTALL_DIR/templates/conventions"; then
            log_success "Best practices seeded successfully"
        else
            log_warning "Failed to seed best practices (non-critical)"
            log_info "You can seed manually later with:"
            log_info "  python3 $INSTALL_DIR/scripts/memory/seed_best_practices.py --templates-dir $INSTALL_DIR/templates/conventions"
        fi
    fi
    # No tip shown if user explicitly declined during interactive prompt
}

show_success_message() {
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                                                             │"
    echo "│   \033[92m✓ AI Memory Module installed successfully!\033[0m              │"
    echo "│                                                             │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│                                                             │"
    echo "│   Installed components:                                     │"
    echo "│     ✓ Qdrant vector database (port $QDRANT_PORT)                   │"
    echo "│     ✓ Embedding service (port $EMBEDDING_PORT)                     │"
    echo "│     ✓ Claude Code hooks (session_start, post_tool, stop)    │"
    if [[ "$INSTALL_MONITORING" == "true" ]]; then
    echo "│     ✓ Monitoring dashboard (Streamlit, Grafana, Prometheus) │"
    fi
    if [[ "$SEED_BEST_PRACTICES" == "true" ]]; then
    echo "│     ✓ Best practices patterns seeded                        │"
    fi
    echo "│                                                             │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│                                                             │"
    echo "│   What happens next:                                        │"
    echo "│                                                             │"
    echo "│   1. Start a new Claude Code session in your project        │"
    echo "│   2. Work on your code as usual (Edit/Write files)          │"
    echo "│   3. Claude will automatically capture implementation       │"
    echo "│      patterns from your edits                               │"
    echo "│   4. On next session, Claude will remember your work!       │"
    echo "│                                                             │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│                                                             │"
    echo "│   Useful commands:                                          │"
    echo "│                                                             │"
    echo "│   Health check:                                             │"
    echo "│     python3 $INSTALL_DIR/scripts/health-check.py            │"
    echo "│                                                             │"
    echo "│   View logs:                                                │"
    echo "│     cd $INSTALL_DIR/docker && docker compose logs -f        │"
    echo "│                                                             │"
    echo "│   Stop services:                                            │"
    echo "│     cd $INSTALL_DIR/docker && docker compose down           │"
    echo "│                                                             │"
    if [[ "$INSTALL_MONITORING" == "true" ]]; then
    echo "│   Monitoring dashboards:                                    │"
    echo "│     Streamlit: http://localhost:28501                       │"
    echo "│     Grafana:   http://localhost:23000                       │"
    echo "│                                                             │"
    else
    echo "│   Add monitoring later:                                     │"
    echo "│     cd $INSTALL_DIR/docker                                  │"
    echo "│     docker compose --profile monitoring up -d               │"
    echo "│                                                             │"
    fi
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
}

# Error message templates for common failures (AC 7.1.8)
# These provide clear, actionable guidance with NO FALLBACK warnings

show_docker_not_running_error() {
    log_error "Docker daemon is not running"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  Docker needs to be running to install AI Memory Module    │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│  Start Docker:                                              │"
    echo "│    Ubuntu/Debian: sudo systemctl start docker               │"
    echo "│    macOS:         Open Docker Desktop                       │"
    echo "│    WSL2:          Start Docker Desktop on Windows           │"
    echo "│                                                             │"
    echo "│  NO FALLBACK: This installer will NOT continue without     │"
    echo "│  a running Docker daemon.                                  │"
    echo "└─────────────────────────────────────────────────────────────┘"
    exit 1
}

show_port_conflict_error() {
    local port=$1
    local service=$2
    log_error "Port $port is already in use"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  Port $port is needed for $service but is already in use   │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│  Options:                                                   │"
    echo "│    1. Stop the conflicting service:                         │"
    echo "│       lsof -i :$port  # Find what's using it               │"
    echo "│       kill <PID>      # Stop it                            │"
    echo "│                                                             │"
    echo "│    2. Use a different port:                                 │"
    echo "│       AI_MEMORY_QDRANT_PORT=26360 ./install.sh                  │"
    echo "│                                                             │"
    echo "│  NO FALLBACK: This installer will NOT automatically find   │"
    echo "│  an available port. You must resolve the conflict.         │"
    echo "└─────────────────────────────────────────────────────────────┘"
    exit 1
}

show_disk_space_error() {
    local available_space
    available_space=$(df -h . | tail -1 | awk '{print $4}')
    log_error "Insufficient disk space"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  AI Memory Module requires at least 5GB of free space      │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│  Current free space: $available_space                       │"
    echo "│                                                             │"
    echo "│  Free up space by:                                          │"
    echo "│    docker system prune -a   # Remove unused Docker data    │"
    echo "│                                                             │"
    echo "│  WARNING: This installer requires space for:               │"
    echo "│    - Qdrant database (~1GB)                                 │"
    echo "│    - Nomic Embed Code model (~7GB)                          │"
    echo "│    - Docker images (~2GB)                                   │"
    echo "└─────────────────────────────────────────────────────────────┘"
    exit 1
}

show_python_version_error() {
    local current=$1
    log_error "Python version too old"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  Python 3.10+ is REQUIRED                                  │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│  Found: Python $current                                     │"
    echo "│  Needed: Python 3.10 or higher                             │"
    echo "│                                                             │"
    echo "│  Why?                                                       │"
    echo "│    - Async support for non-blocking hooks (NFR-P1)         │"
    echo "│    - Improved type hints for better IDE support            │"
    echo "│    - Match statements and modern Python features           │"
    echo "│                                                             │"
    echo "│  NO FALLBACK: This installer will NOT downgrade            │"
    echo "│  functionality. You must upgrade Python.                   │"
    echo "└─────────────────────────────────────────────────────────────┘"
    exit 1
}

# Execute main function with all arguments
main "$@"
