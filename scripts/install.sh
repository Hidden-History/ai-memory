#!/usr/bin/env bash
# install.sh - BMAD Memory Module Installer
# Version: 1.0.0
# Description: Single-command installer for complete memory system
# Usage: ./install.sh or curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
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

# Cleanup handler for interrupts (SIGINT/SIGTERM)
# Per https://vaneyckt.io/posts/safer_bash_scripts_with_set_euxo_pipefail/
INSTALL_STARTED=false
cleanup() {
    local exit_code=$?
    if [[ "$INSTALL_STARTED" = true && $exit_code -ne 0 ]]; then
        echo ""
        log_warning "Installation interrupted (exit code: $exit_code)"
        echo ""
        echo "Partial installation may exist at: $INSTALL_DIR"
        echo "To clean up and retry:"
        echo "  rm -rf $INSTALL_DIR"
        echo "  ./install.sh"
        echo ""
        echo "If services were started, stop them with:"
        echo "  cd $INSTALL_DIR/docker && docker compose down"
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
INSTALL_DIR="${BMAD_INSTALL_DIR:-$HOME/.bmad-memory}"
QDRANT_PORT="${BMAD_QDRANT_PORT:-26350}"
EMBEDDING_PORT="${BMAD_EMBEDDING_PORT:-28080}"
MONITORING_PORT="${BMAD_MONITORING_PORT:-28000}"
STREAMLIT_PORT="${BMAD_STREAMLIT_PORT:-28501}"

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

# Main orchestration function
main() {
    INSTALL_STARTED=true  # Enable cleanup handler

    echo ""
    echo "========================================"
    echo "  BMAD Memory Module Installer"
    echo "========================================"
    echo ""
    echo "Installation directory: $INSTALL_DIR"
    echo "Qdrant port: $QDRANT_PORT"
    echo "Embedding port: $EMBEDDING_PORT"
    echo ""

    # NFR-I5: Idempotent installation - safe to run multiple times
    check_existing_installation

    check_prerequisites
    detect_platform
    create_directories
    copy_files
    configure_environment
    start_services
    wait_for_services
    configure_hooks
    copy_env_template
    verify_hooks
    run_health_check
    seed_best_practices
    show_success_message
}

# Idempotency check - detect existing installation (NFR-I5)
check_existing_installation() {
    local existing=false
    local services_running=false

    # Check if installation directory exists with key files
    if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/docker/docker-compose.yml" ]]; then
        existing=true
        log_info "Existing installation detected at $INSTALL_DIR"
    fi

    # Check if Docker services are already running
    if command -v docker &> /dev/null && docker info &> /dev/null; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "bmad-memory\|qdrant"; then
            services_running=true
            log_info "BMAD Memory services are currently running"
        fi
    fi

    # Handle existing installation
    if [[ "$existing" = true || "$services_running" = true ]]; then
        echo ""
        log_warning "Previous installation detected."
        echo ""
        echo "Options:"
        echo "  1. Reinstall (stop services, update files, restart)"
        echo "  2. Abort installation"
        echo ""

        # Check for BMAD_FORCE_REINSTALL env var for non-interactive mode
        if [[ "${BMAD_FORCE_REINSTALL:-}" = "true" ]]; then
            log_info "BMAD_FORCE_REINSTALL=true - proceeding with reinstall"
            handle_reinstall "$services_running"
            return 0
        fi

        # Interactive prompt
        read -r -p "Choose [1/2]: " choice
        case "$choice" in
            1)
                handle_reinstall "$services_running"
                ;;
            2|*)
                log_info "Installation aborted by user"
                exit 0
                ;;
        esac
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
    check_port_available "$QDRANT_PORT" "Qdrant"
    check_port_available "$EMBEDDING_PORT" "Embedding Service"
    check_port_available "$MONITORING_PORT" "Monitoring API"
    check_port_available "$STREAMLIT_PORT" "Streamlit Dashboard"

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

    # Create main installation directory and subdirectories
    mkdir -p "$INSTALL_DIR"/{docker,src/memory,scripts,.claude/hooks/scripts,logs}

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

    log_info "Copying Python memory modules..."
    cp -r "$SOURCE_DIR/src/memory/"* "$INSTALL_DIR/src/memory/"

    log_info "Copying scripts..."
    cp -r "$SOURCE_DIR/scripts/"* "$INSTALL_DIR/scripts/"

    log_info "Copying Claude Code hooks..."
    cp -r "$SOURCE_DIR/.claude/hooks/"* "$INSTALL_DIR/.claude/hooks/"

    # Make scripts executable (both .py and .sh files)
    log_info "Making scripts executable..."
    chmod +x "$INSTALL_DIR/scripts/"*.{py,sh} 2>/dev/null || true
    chmod +x "$INSTALL_DIR/.claude/hooks/scripts/"*.py 2>/dev/null || true

    log_success "Files copied to $INSTALL_DIR"
}

# Environment configuration (AC 7.1.6)
configure_environment() {
    log_info "Configuring environment..."

    # Create .env file with port configuration
    cat > "$INSTALL_DIR/.env" <<EOF
# BMAD Memory Module Configuration
# Generated by install.sh on $(date)

# Port Configuration
QDRANT_PORT=$QDRANT_PORT
EMBEDDING_PORT=$EMBEDDING_PORT
MONITORING_PORT=$MONITORING_PORT
STREAMLIT_PORT=$STREAMLIT_PORT

# Installation Paths
INSTALL_DIR=$INSTALL_DIR
QUEUE_DIR=$HOME/.claude-memory

# Platform Information
PLATFORM=$PLATFORM
ARCH=$ARCH
EOF

    log_success "Environment configured at $INSTALL_DIR/.env"
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
    docker compose pull

    # Start core services with 2026 security best practices:
    # - Localhost-only bindings (127.0.0.1)
    # - Health checks enabled (condition: service_healthy)
    # - Security opts: no-new-privileges:true
    # - Non-root user execution where possible
    log_info "Starting services with security hardening..."
    docker compose up -d

    log_success "Docker services started"
}

# Wait for services to be healthy (AC 7.1.7)
wait_for_services() {
    log_info "Waiting for services to be ready..."
    log_info "Note: First start may take 1-2 minutes to download embedding model (~500MB)"

    local max_attempts=${WAIT_TIMEOUT:-180}
    local attempt=0

    # Wait for Qdrant using localhost health check (2026 best practice)
    echo -n "  Qdrant ($QDRANT_PORT): "
    while [[ $attempt -lt $max_attempts ]]; do
        if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$QDRANT_PORT/" &> /dev/null; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 1
        ((attempt++))
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

    # Wait for Embedding Service
    attempt=0
    echo -n "  Embedding ($EMBEDDING_PORT): "
    while [[ $attempt -lt $max_attempts ]]; do
        if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:$EMBEDDING_PORT/health" &> /dev/null; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        # Show progress every 30 seconds
        if [[ $((attempt % 30)) -eq 0 && $attempt -gt 0 ]]; then
            echo -n " [${attempt}s/${max_attempts}s] "
        fi
        echo -n "."
        sleep 1
        ((attempt++))
    done

    if [[ $attempt -eq $max_attempts ]]; then
        echo -e "${RED}timeout${NC}"
        log_error "Embedding service failed to start within ${max_attempts} seconds."
        echo ""
        echo "Check logs for details:"
        echo "  cd $INSTALL_DIR/docker && docker compose logs embedding"
        echo ""
        echo "NOTE: First start downloads ~500MB model from HuggingFace (may take 1-2 min)."
        echo "      Subsequent starts load from cache (~5 seconds)."
        echo "      If this persists, check network connection and available disk space."
        echo ""
        echo "NO FALLBACK: Service health is required for installation."
        exit 1
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
        ((attempt++))
    done

    if [[ $attempt -eq 30 ]]; then
        echo -e "${YELLOW}timeout (non-critical)${NC}"
        log_warning "Monitoring API did not start (this is optional)"
    fi

    log_success "All critical services ready"
}

configure_hooks() {
    log_info "Configuring Claude Code hooks..."

    CLAUDE_SETTINGS="$HOME/.claude/settings.json"
    HOOKS_DIR="$INSTALL_DIR/.claude/hooks/scripts"

    # Create .claude directory if needed
    mkdir -p "$HOME/.claude"

    # Use Python merge script for reliable deep merge
    if [[ -f "$CLAUDE_SETTINGS" ]]; then
        # Merge with existing settings
        log_info "Merging with existing settings.json..."
        python3 "$INSTALL_DIR/scripts/merge_settings.py" "$CLAUDE_SETTINGS" "$HOOKS_DIR"
    else
        # Create new settings file
        log_info "Creating new settings.json..."
        python3 "$INSTALL_DIR/scripts/generate_settings.py" "$CLAUDE_SETTINGS" "$HOOKS_DIR"
    fi

    log_success "Hooks configured in $CLAUDE_SETTINGS"
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

verify_hooks() {
    log_info "Verifying hook configuration..."

    CLAUDE_SETTINGS="$HOME/.claude/settings.json"
    HOOKS_DIR="$INSTALL_DIR/.claude/hooks/scripts"

    # Check settings.json exists and is valid JSON
    if ! python3 -c "import json; json.load(open('$CLAUDE_SETTINGS'))" 2>/dev/null; then
        log_error "Invalid JSON in $CLAUDE_SETTINGS"
        echo ""
        echo "Backup available: $CLAUDE_SETTINGS.backup.*"
        exit 1
    fi

    # Check hook scripts exist and are executable
    local hooks_missing=0
    for hook in session_start.py post_tool_capture.py session_stop.py; do
        if [[ ! -x "$HOOKS_DIR/$hook" ]]; then
            log_error "Hook script missing or not executable: $hook"
            hooks_missing=1
        fi
    done

    if [[ $hooks_missing -eq 1 ]]; then
        exit 1
    fi

    # Verify hooks are in settings using Python
    if ! python3 -c "
import json
import sys

settings = json.load(open('$CLAUDE_SETTINGS'))
if 'hooks' not in settings:
    print('ERROR: No hooks section in settings.json')
    sys.exit(1)

required_hooks = ['SessionStart', 'PostToolUse', 'Stop']
missing = [h for h in required_hooks if h not in settings['hooks']]

if missing:
    print(f'ERROR: Missing hooks: {missing}')
    sys.exit(1)

print('✓ All hooks configured correctly')
" 2>/dev/null; then
        log_error "Hooks not properly configured in settings.json"
        exit 1
    fi

    log_success "Hooks verified"
}

run_health_check() {
    log_info "Running health checks..."

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

        # Check if templates directory exists
        if [[ ! -d "$INSTALL_DIR/templates/best_practices" ]]; then
            log_warning "Templates directory not found - skipping seeding"
            log_info "To seed manually later:"
            log_info "  python3 $INSTALL_DIR/scripts/memory/seed_best_practices.py"
            return 0
        fi

        # Run seeding script
        if python3 "$INSTALL_DIR/scripts/memory/seed_best_practices.py" --templates-dir "$INSTALL_DIR/templates/best_practices"; then
            log_success "Best practices seeded successfully"
        else
            log_warning "Failed to seed best practices (non-critical)"
            log_info "You can seed manually later with:"
            log_info "  python3 $INSTALL_DIR/scripts/memory/seed_best_practices.py --templates-dir $INSTALL_DIR/templates/best_practices"
        fi
    else
        echo ""
        echo "💡 Tip: To seed best practices collection with example templates:"
        echo "   python3 $INSTALL_DIR/scripts/memory/seed_best_practices.py --templates-dir $INSTALL_DIR/templates/best_practices"
        echo ""
        echo "   Or reinstall with seeding enabled:"
        echo "   SEED_BEST_PRACTICES=true ./install.sh"
    fi
}

show_success_message() {
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                                                             │"
    echo "│   \033[92m✓ BMAD Memory Module installed successfully!\033[0m            │"
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
    echo "│   Health check (run anytime):                               │"
    echo "│     python3 $INSTALL_DIR/scripts/health-check.py            │"
    echo "│                                                             │"
    echo "│   View Docker logs:                                         │"
    echo "│     docker compose -f $INSTALL_DIR/docker/docker-compose.yml logs -f"
    echo "│                                                             │"
    echo "│   Stop services:                                            │"
    echo "│     docker compose -f $INSTALL_DIR/docker/docker-compose.yml down"
    echo "│                                                             │"
    echo "│   Start monitoring dashboard (optional):                    │"
    echo "│     docker compose -f $INSTALL_DIR/docker/docker-compose.yml \\"
    echo "│       --profile monitoring up -d                            │"
    echo "│     Then visit: http://localhost:28501 (Streamlit)          │"
    echo "│                 http://localhost:23000 (Grafana)            │"
    echo "│                                                             │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
}

# Error message templates for common failures (AC 7.1.8)
# These provide clear, actionable guidance with NO FALLBACK warnings

show_docker_not_running_error() {
    log_error "Docker daemon is not running"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  Docker needs to be running to install BMAD Memory Module  │"
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
    echo "│       BMAD_QDRANT_PORT=26360 ./install.sh                  │"
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
    echo "│  BMAD Memory Module requires at least 5GB of free space    │"
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
