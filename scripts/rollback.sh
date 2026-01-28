#!/usr/bin/env bash
# scripts/rollback.sh - Rollback AI Memory Module Update
# 2026 Best Practice: Pre-written, tested rollback script

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

INSTALL_DIR="${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}"

# Track rollback state for cleanup
ROLLBACK_STARTED=false
SERVICES_STOPPED=false
SELECTED_BACKUP=""

# Cleanup function for signal traps (consistent with update.sh)
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]] && [[ "$ROLLBACK_STARTED" == "true" ]]; then
        log_error "Rollback interrupted or failed (exit code: $exit_code)"
        echo ""
        if [[ "$SERVICES_STOPPED" == "true" ]]; then
            echo "Services were stopped but may not have been restarted."
            echo "To restart manually:"
            echo "  docker compose -f \"$INSTALL_DIR/docker/docker-compose.yml\" up -d"
        fi
    fi
}

# Set trap for cleanup on EXIT
trap cleanup EXIT

main() {
    echo ""
    echo "========================================"
    echo "  AI Memory Module Rollback"
    echo "========================================"
    echo ""

    check_backups
    select_backup
    confirm_rollback
    stop_services
    restore_backup
    restart_services
    run_health_check
    show_success_message
}

check_backups() {
    log_info "Checking available backups..."

    if [[ ! -d "$INSTALL_DIR/backups" ]]; then
        log_error "No backups directory found at $INSTALL_DIR/backups"
        echo "Cannot rollback without backups"
        exit 1
    fi

    # Find all backup directories
    mapfile -t BACKUPS < <(find "$INSTALL_DIR/backups" -maxdepth 1 -type d -name "????????_??????" | sort -r)

    if [[ ${#BACKUPS[@]} -eq 0 ]]; then
        log_error "No backups found"
        echo "Run update.sh at least once to create backups"
        exit 1
    fi

    log_success "Found ${#BACKUPS[@]} backup(s)"
}

select_backup() {
    echo ""
    echo "Available backups:"
    echo ""

    local index=1
    for backup in "${BACKUPS[@]}"; do
        local timestamp=$(basename "$backup")
        local date_part="${timestamp:0:8}"
        local time_part="${timestamp:9:6}"
        local formatted="${date_part:0:4}-${date_part:4:2}-${date_part:6:2} ${time_part:0:2}:${time_part:2:2}:${time_part:4:2}"

        # Count files in backup
        local file_count=$(find "$backup" -type f | wc -l)

        echo "  [$index] $formatted ($file_count files)"
        ((index++))
    done

    echo ""
    read -p "Select backup to restore [1-${#BACKUPS[@]}]: " -r selection

    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [[ $selection -lt 1 ]] || [[ $selection -gt ${#BACKUPS[@]} ]]; then
        log_error "Invalid selection"
        exit 1
    fi

    SELECTED_BACKUP="${BACKUPS[$((selection-1))]}"
    log_info "Selected: $(basename "$SELECTED_BACKUP")"
}

confirm_rollback() {
    echo ""
    log_warning "This will restore files from backup, potentially losing recent changes"
    echo ""
    echo "Backup to restore: $(basename "$SELECTED_BACKUP")"
    echo ""
    read -p "Continue with rollback? (yes/no): " -r confirmation

    if [[ "$confirmation" != "yes" ]]; then
        log_info "Rollback cancelled"
        exit 0
    fi

    # Mark rollback as started after user confirmation
    ROLLBACK_STARTED=true
}

stop_services() {
    log_info "Stopping services..."

    cd "$INSTALL_DIR/docker"
    docker compose down || log_warning "Services already stopped"

    # Track that services were stopped for cleanup trap
    SERVICES_STOPPED=true
}

restore_backup() {
    log_info "Restoring backup..."

    # Restore .env if present in backup
    if [[ -f "$SELECTED_BACKUP/.env" ]]; then
        cp "$SELECTED_BACKUP/.env" "$INSTALL_DIR/"
        log_info "Restored .env"
    fi

    # Restore settings.json if present
    if [[ -f "$SELECTED_BACKUP/settings.json" ]]; then
        cp "$SELECTED_BACKUP/settings.json" "$HOME/.claude/settings.json"
        log_info "Restored settings.json"
    fi

    # Restore docker-compose.override.yml if present
    if [[ -f "$SELECTED_BACKUP/docker-compose.override.yml" ]]; then
        cp "$SELECTED_BACKUP/docker-compose.override.yml" "$INSTALL_DIR/docker/"
        log_info "Restored docker-compose.override.yml"
    fi

    # Restore custom directory if present
    if [[ -d "$SELECTED_BACKUP/custom" ]]; then
        cp -r "$SELECTED_BACKUP/custom" "$INSTALL_DIR/"
        log_info "Restored custom directory"
    fi

    log_success "Backup restored"
}

restart_services() {
    log_info "Restarting services..."

    cd "$INSTALL_DIR/docker"
    docker compose up -d

    log_info "Waiting for services..."
    sleep 10
}

run_health_check() {
    log_info "Running health check..."

    if python3 "$INSTALL_DIR/scripts/health-check.py"; then
        log_success "Health check passed"
    else
        log_error "Health check failed after rollback"
        echo "Services may need manual intervention"
        exit 1
    fi
}

show_success_message() {
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│                                                             │"
    echo "│   ${GREEN}✓ Rollback completed successfully!${NC}                       │"
    echo "│                                                             │"
    echo "│   Restored from: $(basename "$SELECTED_BACKUP")"
    echo "│                                                             │"
    echo "│   Services restarted and health check passed                │"
    echo "│                                                             │"
    echo "└─────────────────────────────────────────────────────────────┘"
    echo ""
}

main "$@"
