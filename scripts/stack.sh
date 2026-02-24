#!/usr/bin/env bash
# =============================================================================
# stack.sh — AI Memory Unified Stack Manager
# Version: 1.1.0
# Fixes: BUG-148 (network conflict when stopping two compose stacks)
# =============================================================================
#
# Usage: stack.sh <command> [options]
#
# Commands:
#   start              Start all enabled services in correct order
#   stop               Gracefully stop all containers
#   restart            Stop then start (full cycle)
#   status             Show container status, health, and ports
#   nuke [--yes|-y]    Stop + remove volumes + clean up (clean slate)
#   help               Show this help
#
# Architecture:
#   Core compose:    docker-compose.yml        (qdrant, embedding + profiles)
#   Langfuse compose: docker-compose.langfuse.yml (7 containers, external network)
#
#   Both files share the ai-memory_default network.
#   CORRECT ORDER — Start:  core first (creates network), then langfuse (joins it)
#   CORRECT ORDER — Stop:   langfuse first (leaves network), then core (removes it)
#
# 2026 Best Practices Applied:
#   - set -euo pipefail + IFS for strict error handling
#   - Docker Compose V2 (docker compose, not docker-compose)
#   - Project name from compose file's name: field (no -p CLI flag)
#   - --wait for health verification on startup
#   - --timeout 120 for graceful shutdown
#   - down -v (not docker volume prune -f) for volume cleanup
#   - --remove-orphans to catch any leftover containers
#   - Environment read from .env (LANGFUSE_ENABLED, GITHUB_TOKEN, etc.)
#   - Secrets never printed to stdout (token values masked)
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# =============================================================================
# COLORS & LOGGING  (matching install.sh / langfuse_setup.sh style)
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*" >&2; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

step() {
    echo ""
    echo -e "${BLUE}━━━${NC} ${BOLD}$*${NC}"
}

# =============================================================================
# PATH DETECTION
# Auto-detects docker directory from:
#   1. AI_MEMORY_INSTALL_DIR env var (explicit override)
#   2. ~/.ai-memory/docker  (default installed location)
#   3. <script-dir>/../docker  (source repo layout)
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_docker_dir() {
    # 1. Explicit env var override
    if [[ -n "${AI_MEMORY_INSTALL_DIR:-}" ]] && \
       [[ -d "${AI_MEMORY_INSTALL_DIR}/docker" ]] && \
       [[ -f "${AI_MEMORY_INSTALL_DIR}/docker/docker-compose.yml" ]]; then
        echo "${AI_MEMORY_INSTALL_DIR}/docker"
        return 0
    fi

    # 2. Default installed location (~/.ai-memory)
    if [[ -d "${HOME}/.ai-memory/docker" ]] && \
       [[ -f "${HOME}/.ai-memory/docker/docker-compose.yml" ]]; then
        echo "${HOME}/.ai-memory/docker"
        return 0
    fi

    # 3. Source repo: scripts/ is sibling to docker/
    local candidate
    candidate="$(cd "${SCRIPT_DIR}/../docker" 2>/dev/null && pwd)" || true
    if [[ -n "${candidate:-}" ]] && \
       [[ -d "${candidate}" ]] && \
       [[ -f "${candidate}/docker-compose.yml" ]]; then
        echo "${candidate}"
        return 0
    fi

    return 1
}

if ! DOCKER_DIR="$(find_docker_dir)"; then
    log_error "Cannot locate the AI Memory docker directory."
    log_error ""
    log_error "Searched:"
    log_error "  1. \${AI_MEMORY_INSTALL_DIR}/docker  (AI_MEMORY_INSTALL_DIR=${AI_MEMORY_INSTALL_DIR:-<not set>})"
    log_error "  2. ${HOME}/.ai-memory/docker"
    log_error "  3. ${SCRIPT_DIR}/../docker"
    log_error ""
    log_error "Fix: Run from the source repo, or set AI_MEMORY_INSTALL_DIR to your install path."
    exit 1
fi

COMPOSE_CORE="${DOCKER_DIR}/docker-compose.yml"
COMPOSE_LANGFUSE="${DOCKER_DIR}/docker-compose.langfuse.yml"
ENV_FILE="${DOCKER_DIR}/.env"

# =============================================================================
# COMPOSE WRAPPER
# Wraps docker compose to conditionally pass --env-file only when .env exists.
# Without this, docker compose crashes if --env-file points to a missing file.
# =============================================================================
_compose() {
    if [[ -f "${ENV_FILE}" ]]; then
        docker compose --env-file "${ENV_FILE}" "$@"
    else
        docker compose "$@"
    fi
}

# =============================================================================
# ENVIRONMENT LOADING
# Sources .env to pick up LANGFUSE_ENABLED, GITHUB_TOKEN, etc.
# Uses a targeted grep to avoid sourcing comments or invalid lines.
# =============================================================================
load_env() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        log_warning ".env not found at ${ENV_FILE} — using defaults."
        return 0
    fi

    # Export all KEY=VALUE lines (skips comments, blank lines, lines starting
    # with digits or other non-identifier characters).
    set -a
    # shellcheck disable=SC1090
    source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "${ENV_FILE}") 2>/dev/null || true
    set +a
}

load_env

# Defaults — set after load_env so .env values take precedence
CONTAINER_PREFIX="${AI_MEMORY_CONTAINER_PREFIX:-ai-memory}"
LANGFUSE_ENABLED="${LANGFUSE_ENABLED:-false}"
GITHUB_SYNC_ENABLED="${GITHUB_SYNC_ENABLED:-false}"
# MONITORING_ENABLED: not in .env.example, defaults to true (always start monitoring)
MONITORING_ENABLED="${MONITORING_ENABLED:-true}"

# =============================================================================
# HELPERS
# =============================================================================

check_docker() {
    if ! docker info &>/dev/null; then
        log_error "Docker daemon is not running. Start Docker first and retry."
        exit 1
    fi
}

check_compose_file() {
    if [[ ! -f "${COMPOSE_CORE}" ]]; then
        log_error "Core compose file not found: ${COMPOSE_CORE}"
        exit 1
    fi
}

# Returns true (exit 0) if any langfuse containers are currently running
langfuse_running() {
    docker ps \
        --filter "name=${CONTAINER_PREFIX}-langfuse" \
        --format "{{.Names}}" \
        2>/dev/null | grep -q .
}

# =============================================================================
# cmd_start — Start all enabled services
# Order: core (creates network) → langfuse (joins network)
# =============================================================================
cmd_start() {
    check_docker
    check_compose_file

    # Build profile list for core compose.
    # - monitoring: always enabled unless explicitly set to false
    # - github:     only when GITHUB_SYNC_ENABLED=true AND GITHUB_TOKEN is set
    local profiles=(--profile monitoring)
    [[ "${MONITORING_ENABLED}" == "false" ]] && profiles=()

    if [[ "${GITHUB_SYNC_ENABLED}" == "true" && -n "${GITHUB_TOKEN:-}" ]]; then
        profiles+=(--profile github)
    fi

    step "Starting AI Memory Stack"
    log_info "Docker dir:         ${DOCKER_DIR}"
    local _profiles_display; IFS=' ' _profiles_display="${profiles[*]}"
    log_info "Core profiles:      ${_profiles_display:-(default — qdrant + embedding only)}"
    log_info "LANGFUSE_ENABLED:   ${LANGFUSE_ENABLED}"
    log_info "MONITORING_ENABLED: ${MONITORING_ENABLED}"
    if [[ "${GITHUB_SYNC_ENABLED}" == "true" ]]; then
        # Use intermediate variable to prevent token value from leaking to stdout.
        # ${GITHUB_TOKEN:+set} expands to "set" when token is non-empty.
        # ${GITHUB_TOKEN:-NOT SET} would expand to the ACTUAL TOKEN when set — security bug.
        local _token_status="${GITHUB_TOKEN:+set}"
        log_info "GITHUB_SYNC:        enabled (token ${_token_status:-NOT SET})"
    fi

    # ── Step 1: Core stack ────────────────────────────────────────────────────
    # Creates the ai-memory_default network that langfuse will join.
    local _profiles_short="${_profiles_display//--profile /}"
    step "Step 1/2 — Core services (qdrant + embedding${_profiles_short:+, ${_profiles_short}})"

    if ! _compose \
            -f "${COMPOSE_CORE}" \
            "${profiles[@]}" \
            up -d --wait; then
        log_error "Core services failed to start or reach healthy state."
        log_error "Inspect logs with:"
        log_error "  docker compose -f ${COMPOSE_CORE} logs"
        exit 1
    fi
    log_success "Core services are healthy."

    # ── Step 2: Langfuse stack ────────────────────────────────────────────────
    # Joins the ai-memory_default network created above.
    if [[ "${LANGFUSE_ENABLED}" == "true" ]]; then
        if [[ ! -f "${COMPOSE_LANGFUSE}" ]]; then
            log_warning "LANGFUSE_ENABLED=true but compose file not found: ${COMPOSE_LANGFUSE}"
            log_warning "Skipping Langfuse startup. Run langfuse_setup.sh first."
        else
            step "Step 2/2 — Langfuse services (LLM observability)"
            log_info "This may take up to 2 minutes (ClickHouse + PostgreSQL startup)..."

            # NOTE: Both compose files are passed intentionally. Docker Compose merges
            # them under one project name ("ai-memory" from docker-compose.yml name: field).
            # This ensures stop/down can find the Langfuse containers later — if we passed
            # only the Langfuse file, it would get a different project name (derived from
            # the directory), and 'docker compose down' wouldn't match the containers.
            # This is exactly the root cause of BUG-148.
            #
            # The --profile langfuse flag limits 'up' to langfuse-profile services only.
            # Already-running core services are NOT restarted — docker compose up -d is
            # idempotent for unchanged, running services.
            if ! _compose \
                    -f "${COMPOSE_CORE}" \
                    -f "${COMPOSE_LANGFUSE}" \
                    --profile langfuse \
                    up -d --wait; then
                log_error "Langfuse services failed to start or reach healthy state."
                log_warning "Core services are still running. Fix the issue and re-run 'stack.sh start',"
                log_warning "or run 'stack.sh stop' to stop all services."
                log_error "Inspect logs with:"
                log_error "  docker compose -f ${COMPOSE_CORE} -f ${COMPOSE_LANGFUSE} --profile langfuse logs"
                exit 1
            fi
            log_success "Langfuse services are healthy."
        fi
    else
        log_info "Step 2/2 — Langfuse disabled (LANGFUSE_ENABLED=${LANGFUSE_ENABLED}). Skipping."
    fi

    echo ""
    log_success "Stack started successfully."
    echo ""
    cmd_status
}

# =============================================================================
# cmd_stop — Gracefully stop all containers
# Order: langfuse (network user) → core (network owner)
# Uses 'stop' (not 'down') so containers can be restarted quickly.
# =============================================================================
cmd_stop() {
    check_docker

    step "Stopping AI Memory Stack"
    log_info "Shutdown order: Langfuse (network user) → Core (network owner)"
    log_info "Timeout: 120 seconds per stage"

    # ── Step 1: Langfuse first ────────────────────────────────────────────────
    # Must stop before core removes the ai-memory_default network.
    if [[ "${LANGFUSE_ENABLED}" == "true" ]] || langfuse_running; then
        if [[ -f "${COMPOSE_LANGFUSE}" ]]; then
            step "Step 1/2 — Stopping Langfuse services"
            _compose \
                -f "${COMPOSE_CORE}" \
                -f "${COMPOSE_LANGFUSE}" \
                --profile langfuse \
                stop --timeout 120 \
                && log_success "Langfuse services stopped." \
                || log_warning "Langfuse stop completed with warnings (some services may not have been running)."
        else
            log_info "Step 1/2 — Langfuse compose file not found. Skipping."
        fi
    else
        log_info "Step 1/2 — No Langfuse containers running. Skipping."
    fi

    # ── Step 2: Core stack ────────────────────────────────────────────────────
    # Use ALL core profiles to ensure every profile-gated service is stopped,
    # regardless of which profiles were active at start time.
    # Profiles: monitoring (grafana, prometheus, etc.), github (github-sync),
    # testing (monitoring-api in test mode).
    step "Step 2/2 — Stopping core services"
    _compose \
        -f "${COMPOSE_CORE}" \
        --profile monitoring \
        --profile github \
        --profile testing \
        stop --timeout 120 \
        && log_success "Core services stopped." \
        || log_warning "Core stop completed with warnings."

    echo ""
    log_success "Stack stopped. Containers preserved — run 'stack.sh start' to restart."
}

# =============================================================================
# cmd_restart — Full stop → start cycle
# =============================================================================
cmd_restart() {
    step "Restarting AI Memory Stack"
    cmd_stop
    echo ""
    cmd_start
}

# =============================================================================
# cmd_status — Show all AI Memory container status, health, and ports
# =============================================================================
cmd_status() {
    check_docker

    echo ""
    echo -e "${BOLD}━━━ AI Memory Stack Status ━━━${NC}"
    echo ""

    # Container table (all containers, including stopped ones)
    local ps_output
    ps_output="$(docker ps -a \
        --filter "name=${CONTAINER_PREFIX}" \
        --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" \
        2>/dev/null)" || ps_output=""

    # docker ps --format table always emits at least the header line
    local line_count=0
    [[ -n "${ps_output}" ]] && line_count="$(echo "${ps_output}" | wc -l)"

    if [[ "${line_count}" -le 1 ]]; then
        echo "  (no AI Memory containers found)"
    else
        echo "${ps_output}"
    fi

    echo ""

    # Summary: running vs total
    local running=0 total=0
    running="$(docker ps    --filter "name=${CONTAINER_PREFIX}" --format "{{.Names}}" 2>/dev/null | wc -l)"
    total="$(  docker ps -a --filter "name=${CONTAINER_PREFIX}" --format "{{.Names}}" 2>/dev/null | wc -l)"

    if   [[ "${total}"   -eq 0 ]]; then
        log_info    "Stack: NOT DEPLOYED (run 'stack.sh start' to launch)"
    elif [[ "${running}" -eq 0 ]]; then
        log_warning "Stack: STOPPED (${running}/${total} containers running)"
    elif [[ "${running}" -lt "${total}" ]]; then
        log_warning "Stack: PARTIAL (${running}/${total} containers running — some may be unhealthy)"
    else
        log_success "Stack: RUNNING (${running}/${total} containers)"
    fi

    # Named volumes
    echo ""
    echo -e "${BOLD}Volumes:${NC}"
    local volumes
    volumes="$(docker volume ls \
        --filter "name=${CONTAINER_PREFIX}" \
        --format "  {{.Name}}" \
        2>/dev/null)" || volumes=""
    [[ -n "${volumes}" ]] && echo "${volumes}" || echo "  (none)"

    # Network
    echo ""
    echo -e "${BOLD}Networks:${NC}"
    local networks
    networks="$(docker network ls \
        --filter "name=${CONTAINER_PREFIX}" \
        --format "  {{.Name}}" \
        2>/dev/null)" || networks=""
    [[ -n "${networks}" ]] && echo "${networks}" || echo "  (none)"

    echo ""
}

# =============================================================================
# cmd_nuke — Full teardown: stop + remove containers, volumes, network
# Intended for CI/testing or when a clean slate is needed.
# =============================================================================
cmd_nuke() {
    check_docker

    # ── Confirmation ─────────────────────────────────────────────────────────
    local confirmed=false
    for arg in "$@"; do
        [[ "${arg}" == "--yes" || "${arg}" == "-y" ]] && confirmed=true
    done

    if [[ "${confirmed}" != "true" ]]; then
        # Non-interactive safety: abort if stdin is not a terminal.
        # Prevents hanging on read in CI, pipes, cron, or backgrounded processes.
        if [[ ! -t 0 ]]; then
            log_error "Cannot prompt for confirmation: stdin is not a terminal."
            log_error "Use 'stack.sh nuke --yes' to skip confirmation in non-interactive contexts."
            exit 1
        fi

        echo ""
        echo -e "${RED}${BOLD}WARNING: DESTRUCTIVE OPERATION${NC}"
        echo ""
        echo "  This will permanently destroy:"
        echo "    - All AI Memory containers"
        echo "    - All named volumes:"
        echo "        qdrant_storage, embedding_cache, prometheus_data,"
        echo "        grafana_data, pushgateway_data, classifier_queue"
        if [[ -f "${COMPOSE_LANGFUSE}" ]]; then
            echo "        langfuse-postgres-data, langfuse-clickhouse-data, langfuse-minio-data"
        fi
        echo "    - The ai-memory_default Docker network"
        echo "    - Any orphaned resources matching 'ai-memory_*'"
        echo ""
        echo "  Use --yes to skip this prompt (for CI/scripts)."
        echo ""
        read -r -p "  Type 'yes' to confirm: " answer
        if [[ "${answer}" != "yes" ]]; then
            log_info "Nuke cancelled."
            exit 0
        fi
    fi

    step "Nuking AI Memory Stack"

    # ── Tear down everything at once ─────────────────────────────────────────
    # Passing both compose files lets Docker Compose resolve shutdown order
    # correctly: langfuse services (external network user) are stopped before
    # the core network is removed. All volumes are removed with -v.
    # ALL profiles are listed to ensure every profile-gated service is caught.
    if [[ -f "${COMPOSE_LANGFUSE}" ]]; then
        step "Removing all containers + volumes (core + Langfuse)"
        _compose \
            -f "${COMPOSE_CORE}" \
            -f "${COMPOSE_LANGFUSE}" \
            --profile monitoring \
            --profile github \
            --profile testing \
            --profile langfuse \
            down -v --remove-orphans --timeout 120 \
            && log_success "All containers and volumes removed." \
            || {
                log_warning "Combined teardown had warnings. Attempting core-only cleanup..."
                _compose \
                    -f "${COMPOSE_CORE}" \
                    --profile monitoring \
                    --profile github \
                    --profile testing \
                    down -v --remove-orphans --timeout 120 \
                    && log_success "Core cleanup complete." \
                    || log_warning "Core cleanup also had warnings. Manual cleanup may be needed."
            }
    else
        step "Removing core containers + volumes"
        _compose \
            -f "${COMPOSE_CORE}" \
            --profile monitoring \
            --profile github \
            --profile testing \
            down -v --remove-orphans --timeout 120 \
            && log_success "Core containers and volumes removed." \
            || log_warning "Core teardown had warnings."
    fi

    # ── Clean up any orphaned ai-memory_ volumes ──────────────────────────────
    # Catches volumes that compose down may have missed (e.g., from manual starts).
    step "Checking for orphaned volumes"
    local orphaned
    orphaned="$(docker volume ls \
        --filter "name=ai-memory_" \
        --format "{{.Name}}" \
        2>/dev/null)" || orphaned=""

    if [[ -n "${orphaned}" ]]; then
        while IFS= read -r vol; do
            [[ -z "${vol}" ]] && continue
            log_info "  Removing orphaned volume: ${vol}"
            docker volume rm "${vol}" 2>/dev/null \
                && log_success "  Removed: ${vol}" \
                || log_warning "  Could not remove: ${vol} (may be in use by another container)"
        done <<< "${orphaned}"
    else
        log_info "No orphaned volumes found."
    fi

    echo ""
    log_success "Nuke complete. Stack is fully cleaned."
    cmd_status
}

# =============================================================================
# cmd_help — Usage information
# =============================================================================
cmd_help() {
    cat <<EOF
${BOLD}AI Memory Stack Manager${NC}  (BUG-148: unified two-compose-file management)

${BOLD}USAGE${NC}
  $(basename "${BASH_SOURCE[0]}") <command> [options]

${BOLD}COMMANDS${NC}
  ${GREEN}start${NC}              Start all enabled services in correct order
  ${GREEN}stop${NC}               Gracefully stop all containers (Langfuse first, then core)
  ${GREEN}restart${NC}            Stop then start (full cycle)
  ${GREEN}status${NC}             Show container status, health, and ports
  ${GREEN}nuke${NC} [--yes|-y]    Stop + remove volumes + remove network (clean slate)
  ${GREEN}help${NC}               Show this help

${BOLD}CONFIGURATION${NC}
  Reads from: ${ENV_FILE}

  Variables that control startup:
    LANGFUSE_ENABLED      Start Langfuse observability stack (default: false)
    MONITORING_ENABLED    Start monitoring profile (default: true)
    GITHUB_SYNC_ENABLED   Enable GitHub sync profile (default: false)
    GITHUB_TOKEN          Required for GitHub sync profile

${BOLD}COMPOSE FILES${NC}
  Core:     ${COMPOSE_CORE}
  Langfuse: ${COMPOSE_LANGFUSE}

${BOLD}STARTUP ORDER${NC}
  1. Core    → qdrant + embedding (+ monitoring + github if enabled)
             → creates ai-memory_default Docker network
  2. Langfuse → all 7 Langfuse containers (web, worker, postgres, redis,
               clickhouse, minio, trace-flush-worker)
             → joins existing network via external: true

${BOLD}SHUTDOWN ORDER${NC}
  1. Langfuse first  → leaves the network cleanly (prevents BUG-148)
  2. Core last       → removes the network it owns

${BOLD}EXAMPLES${NC}
  $(basename "${BASH_SOURCE[0]}") start              # Start based on .env settings
  $(basename "${BASH_SOURCE[0]}") stop               # Graceful stop (containers preserved)
  $(basename "${BASH_SOURCE[0]}") status             # Quick health check
  $(basename "${BASH_SOURCE[0]}") restart            # Full stop + start cycle
  $(basename "${BASH_SOURCE[0]}") nuke               # Interactive clean slate
  $(basename "${BASH_SOURCE[0]}") nuke --yes         # Non-interactive (CI / testing)

${BOLD}PATH AUTO-DETECTION${NC}
  Docker dir is resolved in this order:
    1. \${AI_MEMORY_INSTALL_DIR}/docker   (explicit override)
    2. ~/.ai-memory/docker                (default install location)
    3. <script-dir>/../docker             (source repo layout)

  Resolved to: ${DOCKER_DIR}
EOF
}

# =============================================================================
# MAIN
# =============================================================================
COMMAND="${1:-help}"
shift 2>/dev/null || true  # shift command away; remaining args passed to subcommands

case "${COMMAND}" in
    start)           cmd_start ;;
    stop)            cmd_stop ;;
    restart)         cmd_restart ;;
    status)          cmd_status ;;
    nuke)            cmd_nuke "$@" ;;
    help|--help|-h)  cmd_help ;;
    *)
        log_error "Unknown command: '${COMMAND}'"
        echo ""
        cmd_help
        exit 1
        ;;
esac
