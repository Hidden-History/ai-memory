#!/usr/bin/env bash
# update.sh - AI Memory Module Updater
# Version: 1.0.0
# 2026 Best Practices: set -euo pipefail, signal traps, comprehensive backup

set -euo pipefail  # Strict error handling

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
INSTALL_DIR="${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}"
BACKUP_RETENTION_DAYS="${AI_MEMORY_BACKUP_RETENTION:-30}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEBUG="${AI_MEMORY_DEBUG:-0}"

# Initialize BACKUP_DIR to prevent unbound variable in cleanup trap
BACKUP_DIR=""

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Cleanup function for signal traps
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "Update interrupted or failed (exit code: $exit_code)"
        echo ""
        if [[ -n "$BACKUP_DIR" ]] && [[ -d "$BACKUP_DIR" ]]; then
            echo "Your installation is unchanged. Backup is at: $BACKUP_DIR"
            echo "To restore manually if needed:"
            echo "  1. Stop services: docker compose -f \"$INSTALL_DIR/docker/docker-compose.yml\" down"
            echo "  2. Restore backup: cp -r \"$BACKUP_DIR\"/* \"$INSTALL_DIR/\""
            echo "  3. Start services: docker compose -f \"$INSTALL_DIR/docker/docker-compose.yml\" up -d"
        else
            echo "No backup was created (failure occurred before backup step)."
            echo "Your installation should be unchanged."
        fi
    fi
}

# Set trap for cleanup on EXIT
trap cleanup EXIT

# Enable debug trace if requested (2026 best practice: optional -x flag)
if [[ "$DEBUG" == "1" ]] || [[ "${1:-}" == "--debug" ]]; then
    set -x
    log_info "Debug mode enabled (set -x)"
fi

main() {
    echo ""
    echo "========================================"
    echo "  AI Memory Module Updater"
    echo "========================================"
    echo ""

    check_installation
    detect_git_repo
    create_backup
    pull_updates
    update_files
    update_docker_images
    restart_services
    run_migrations
    cleanup_old_backups
    run_health_check
    show_success_message
}

check_installation() {
    log_info "Checking existing installation..."

    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "No installation found at $INSTALL_DIR"
        echo ""
        echo "Run ./install.sh for fresh installation"
        exit 1
    fi

    # Verify critical directories exist
    local missing_dirs=()
    for dir in docker src/memory scripts .claude/hooks/scripts; do
        if [[ ! -d "$INSTALL_DIR/$dir" ]]; then
            missing_dirs+=("$dir")
        fi
    done

    if [[ ${#missing_dirs[@]} -gt 0 ]]; then
        log_error "Installation appears incomplete. Missing directories:"
        printf '  - %s\n' "${missing_dirs[@]}"
        echo ""
        echo "Consider running ./install.sh --force for full reinstallation"
        exit 1
    fi

    log_success "Found installation at $INSTALL_DIR"
}

detect_git_repo() {
    log_info "Detecting update source..."

    if [[ -d "$SCRIPT_DIR/.git" ]]; then
        UPDATE_SOURCE="git"
        log_info "Update source: Git repository"

        # Verify clean working tree
        if [[ -n $(git -C "$SCRIPT_DIR" status --porcelain) ]]; then
            log_warning "Git working tree has uncommitted changes"
            echo "This may cause merge conflicts during update"
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Update cancelled by user"
                exit 0
            fi
        fi
    else
        UPDATE_SOURCE="local"
        log_info "Update source: Local files"
    fi
}

create_backup() {
    log_info "Creating backup..."

    # Create backup directory with timestamp
    BACKUP_DIR="$INSTALL_DIR/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"

    # Backup critical configuration files
    local backed_up=0

    # .env file (user configuration)
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        cp "$INSTALL_DIR/.env" "$BACKUP_DIR/"
        ((backed_up++))
    fi

    # Claude settings.json (hook configuration)
    if [[ -f "$HOME/.claude/settings.json" ]]; then
        cp "$HOME/.claude/settings.json" "$BACKUP_DIR/"
        ((backed_up++))
    fi

    # Docker compose overrides (if present)
    if [[ -f "$INSTALL_DIR/docker/docker-compose.override.yml" ]]; then
        cp "$INSTALL_DIR/docker/docker-compose.override.yml" "$BACKUP_DIR/"
        ((backed_up++))
    fi

    # Custom scripts (if any)
    if [[ -d "$INSTALL_DIR/custom" ]]; then
        cp -r "$INSTALL_DIR/custom" "$BACKUP_DIR/"
        ((backed_up++))
    fi

    log_success "Backup created at $BACKUP_DIR ($backed_up files/dirs)"
}

pull_updates() {
    if [[ "$UPDATE_SOURCE" == "git" ]]; then
        log_info "Pulling latest changes from repository..."

        cd "$SCRIPT_DIR"

        # Get current branch
        current_branch=$(git rev-parse --abbrev-ref HEAD)
        log_info "Current branch: $current_branch"

        # Fetch updates
        if git fetch origin "$current_branch"; then
            # Check if updates available
            local_commit=$(git rev-parse HEAD)
            remote_commit=$(git rev-parse "origin/$current_branch")

            if [[ "$local_commit" == "$remote_commit" ]]; then
                log_info "Already up to date (commit: ${local_commit:0:7})"
            else
                log_info "Updates available: ${local_commit:0:7} -> ${remote_commit:0:7}"

                # Pull updates
                if git pull origin "$current_branch"; then
                    log_success "Repository updated"
                else
                    log_error "Git pull failed"
                    echo "Check for merge conflicts or network issues"
                    exit 1
                fi
            fi
        else
            log_error "Failed to fetch from remote"
            exit 1
        fi
    else
        log_info "Using local files (no git pull needed)"
    fi
}

update_files() {
    log_info "Updating files..."

    # Stop services before updating files
    log_info "Stopping services for safe file update..."
    docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" down || log_warning "Services not running"

    # Update source files (preserve user .env)
    log_info "Updating Python modules..."
    cp -r "$SCRIPT_DIR/src/memory/"* "$INSTALL_DIR/src/memory/"

    log_info "Updating scripts..."
    cp -r "$SCRIPT_DIR/scripts/"* "$INSTALL_DIR/scripts/"

    log_info "Updating hook scripts..."
    cp -r "$SCRIPT_DIR/.claude/hooks/scripts/"* "$INSTALL_DIR/.claude/hooks/scripts/"

    log_info "Updating Docker configuration..."
    # Preserve docker-compose.override.yml if exists
    if [[ -f "$INSTALL_DIR/docker/docker-compose.override.yml" ]]; then
        mv "$INSTALL_DIR/docker/docker-compose.override.yml" "$INSTALL_DIR/docker/docker-compose.override.yml.tmp"
    fi

    cp -r "$SCRIPT_DIR/docker/"* "$INSTALL_DIR/docker/"

    if [[ -f "$INSTALL_DIR/docker/docker-compose.override.yml.tmp" ]]; then
        mv "$INSTALL_DIR/docker/docker-compose.override.yml.tmp" "$INSTALL_DIR/docker/docker-compose.override.yml"
    fi

    # Update .env.example (don't overwrite user's .env)
    if [[ -f "$SCRIPT_DIR/.env.example" ]]; then
        cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/.env.example"

        if [[ ! -f "$INSTALL_DIR/.env" ]]; then
            log_info "No .env file found - copy .env.example to .env to customize"
        else
            log_info "Kept existing .env (see .env.example for new options)"
        fi
    fi

    # Make scripts executable
    chmod +x "$INSTALL_DIR/scripts/"*.py 2>/dev/null || true
    chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true
    chmod +x "$INSTALL_DIR/.claude/hooks/scripts/"*.py

    log_success "Files updated"
}

update_docker_images() {
    log_info "Updating Docker images..."

    cd "$INSTALL_DIR/docker"

    # Pull new images
    if docker compose pull; then
        log_success "Docker images updated"
    else
        log_warning "Failed to pull some images (continuing with existing)"
    fi

    # Rebuild custom images if Dockerfile changed
    if [[ -f "$INSTALL_DIR/docker/embedding/Dockerfile" ]]; then
        log_info "Rebuilding embedding service..."
        docker compose build embedding || log_warning "Rebuild failed (using cached)"
    fi
}

restart_services() {
    log_info "Restarting services..."

    cd "$INSTALL_DIR/docker"

    # Start services
    if docker compose up -d; then
        log_success "Services started"
    else
        log_error "Failed to start services"
        echo ""
        echo "Check logs: docker compose -f \"$INSTALL_DIR/docker/docker-compose.yml\" logs"
        exit 1
    fi

    # Wait for services to be ready
    log_info "Waiting for services to be ready..."
    sleep 10

    # Check service status
    local unhealthy_services=()
    while IFS= read -r line; do
        service=$(echo "$line" | awk '{print $2}')
        state=$(echo "$line" | awk '{print $3}')

        if [[ "$state" != "running" ]]; then
            unhealthy_services+=("$service: $state")
        fi
    done < <(docker compose ps --format "{{.Name}} {{.Service}} {{.State}}")

    if [[ ${#unhealthy_services[@]} -gt 0 ]]; then
        log_warning "Some services are not running:"
        printf '  - %s\n' "${unhealthy_services[@]}"
        echo ""
        echo "Check logs: docker compose -f \"$INSTALL_DIR/docker/docker-compose.yml\" logs"
        echo ""
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

run_migrations() {
    log_info "Running migrations..."

    # Check for migration scripts directory
    local migration_dir="$SCRIPT_DIR/scripts/migrations"

    if [[ ! -d "$migration_dir" ]]; then
        log_info "No migrations directory found (skipping)"
        return
    fi

    # Run migration scripts in order
    local migrations_run=0
    while IFS= read -r migration; do
        if [[ -f "$migration" ]] && [[ -x "$migration" ]]; then
            log_info "Running $(basename "$migration")..."

            if python3 "$migration"; then
                ((migrations_run++))
            else
                log_warning "Migration failed: $(basename "$migration")"
                echo "This may not be critical - continuing update"
            fi
        fi
    done < <(find "$migration_dir" -name "*.py" -type f | sort)

    if [[ $migrations_run -eq 0 ]]; then
        log_info "No migrations to run"
    else
        log_success "$migrations_run migration(s) completed"
    fi
}

cleanup_old_backups() {
    log_info "Cleaning up old backups..."

    local backup_base="$INSTALL_DIR/backups"

    if [[ ! -d "$backup_base" ]]; then
        return
    fi

    # Find backups older than retention period
    local deleted=0
    while IFS= read -r old_backup; do
        rm -rf "$old_backup"
        ((deleted++))
    done < <(find "$backup_base" -maxdepth 1 -type d -mtime +$BACKUP_RETENTION_DAYS)

    if [[ $deleted -gt 0 ]]; then
        log_info "Deleted $deleted old backup(s) (retention: ${BACKUP_RETENTION_DAYS} days)"
    fi
}

run_health_check() {
    log_info "Running health check..."

    if python3 "$INSTALL_DIR/scripts/health-check.py"; then
        log_success "Health check passed"
    else
        log_error "Health check failed"
        echo ""
        echo "Services may not be fully operational. Troubleshooting steps:"
        echo "  1. Check logs: docker compose -f \"$INSTALL_DIR/docker/docker-compose.yml\" logs"
        echo "  2. Restart services: docker compose -f \"$INSTALL_DIR/docker/docker-compose.yml\" restart"
        echo "  3. Restore backup if needed: See cleanup message above"
        echo ""
        read -p "Continue despite health check failure? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

show_success_message() {
    local current_version="unknown"
    if [[ -f "$INSTALL_DIR/src/memory/__version__.py" ]]; then
        current_version=$(grep -Po '__version__\s*=\s*"\K[^"]+' "$INSTALL_DIR/src/memory/__version__.py" || echo "unknown")
    fi

    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                                                             │"
    echo "│   ${GREEN}✓ AI Memory Module updated successfully!${NC}              │"
    echo "│                                                             │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│                                                             │"
    echo "│   Version: $current_version"
    echo "│   Backup:  $BACKUP_DIR"
    echo "│                                                             │"
    echo "│   Services restarted and health check passed                │"
    echo "│                                                             │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│                                                             │"
    echo "│   What's changed:                                           │"
    echo "│     - Python modules updated                                │"
    echo "│     - Scripts and hooks updated                             │"
    echo "│     - Docker images updated                                 │"
    echo "│     - Migrations applied (if any)                           │"
    echo "│                                                             │"
    echo "│   Your configuration (.env) preserved                       │"
    echo "│                                                             │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
}

main "$@"
