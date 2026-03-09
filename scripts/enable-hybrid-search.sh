#!/usr/bin/env bash
# =============================================================================
# enable-hybrid-search.sh — Turnkey hybrid search enablement for AI Memory
# Version: 1.0.0
# Part of: AI Memory Module v2.2.1 (PLAN-013)
#
# Enables BM25 sparse vector hybrid search on an existing installation.
# Handles the complete sequence:
#   1. Pre-flight checks (Docker, Qdrant, embedding service)
#   2. Embedding container rebuild (adds /embed/sparse endpoint + BM25 model)
#   3. Configuration update (HYBRID_SEARCH_ENABLED=true in .env)
#   4. Data migration (add sparse vectors to existing Qdrant points)
#   5. Verification (confirm hybrid search is operational)
#
# Usage:
#   enable-hybrid-search.sh                    # Full enablement
#   enable-hybrid-search.sh --dry-run          # Preview without changes
#   enable-hybrid-search.sh --skip-rebuild     # Skip container rebuild
#   enable-hybrid-search.sh --skip-migration   # Enable config only
#   enable-hybrid-search.sh --collection NAME  # Migrate single collection
#
# Architecture:
#   This script orchestrates existing components:
#     - docker compose build (embedding Dockerfile with BM25 pre-download)
#     - .env configuration (HYBRID_SEARCH_ENABLED toggle)
#     - migrate_v221_hybrid_vectors.py (Qdrant sparse vector migration)
#
#   It does NOT modify application code, search logic, or hook scripts.
#   Those are updated via the installer (install.sh Option 1).
#
# Ports:
#   Qdrant:    ${QDRANT_PORT:-26350}
#   Embedding: ${EMBEDDING_PORT:-28080}
#
# See also:
#   - PLAN-013: oversight/plans/PLAN-013-hybrid-search-quality-sprint.md
#   - Migration: scripts/migrate_v221_hybrid_vectors.py
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# =============================================================================
# COLORS & LOGGING  (matching stack.sh / install.sh style)
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
# CLI ARGUMENT PARSING
# =============================================================================
DRY_RUN=false
SKIP_REBUILD=false
SKIP_MIGRATION=false
COLLECTION_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-rebuild)
            SKIP_REBUILD=true
            shift
            ;;
        --skip-migration)
            SKIP_MIGRATION=true
            shift
            ;;
        --collection)
            if [[ -z "${2:-}" ]]; then
                log_error "--collection requires a NAME argument."
                exit 1
            fi
            COLLECTION_ARG="$2"
            shift 2
            ;;
        --help|-h|help)
            cat <<EOF
${BOLD}AI Memory — Enable Hybrid Search${NC}  (PLAN-013, v2.2.1)

${BOLD}USAGE${NC}
  $(basename "${BASH_SOURCE[0]}") [options]

${BOLD}OPTIONS${NC}
  ${GREEN}--dry-run${NC}            Preview without making changes
  ${GREEN}--skip-rebuild${NC}       Skip embedding container rebuild
  ${GREEN}--skip-migration${NC}     Skip data migration (config update only)
  ${GREEN}--collection NAME${NC}    Migrate only a specific collection
  ${GREEN}--help${NC}               Show this help

${BOLD}EXAMPLES${NC}
  $(basename "${BASH_SOURCE[0]}")                              # Full enablement
  $(basename "${BASH_SOURCE[0]}") --dry-run                    # Preview changes
  $(basename "${BASH_SOURCE[0]}") --skip-rebuild               # Skip container rebuild
  $(basename "${BASH_SOURCE[0]}") --collection discussions     # Migrate one collection
  $(basename "${BASH_SOURCE[0]}") --skip-migration             # Config only, no data migration

${BOLD}SEQUENCE${NC}
  1. Pre-flight checks   — Docker, Qdrant, embedding health
  2. Embedding rebuild   — Add BM25 sparse model to container
  3. Configuration       — Set HYBRID_SEARCH_ENABLED=true in .env
  4. Data migration      — Add sparse vectors to existing Qdrant points
  5. Verification        — Confirm hybrid search is operational

${BOLD}ENVIRONMENT${NC}
  AI_MEMORY_INSTALL_DIR   Override install directory (default: ~/.ai-memory)
  QDRANT_PORT             Qdrant port (default: 26350)
  EMBEDDING_PORT          Embedding service port (default: 28080)
EOF
            exit 0
            ;;
        *)
            log_error "Unknown option: '$1'"
            log_error "Run with --help for usage."
            exit 1
            ;;
    esac
done

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
# Sources .env to pick up QDRANT_API_KEY, QDRANT_PORT, EMBEDDING_PORT, etc.
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

# Read a value from .env, stripping surrounding quotes
read_env_value() {
    local key="$1"
    local raw
    raw="$(grep -E "^${key}=" "${ENV_FILE}" 2>/dev/null | head -1 | cut -d'=' -f2- || true)"
    # Strip surrounding single or double quotes
    raw="${raw#\"}"
    raw="${raw%\"}"
    raw="${raw#\'}"
    raw="${raw%\'}"
    echo "${raw}"
}

# =============================================================================
# INSTALL DIR DETECTION
# Determines where AI Memory is installed for Python venv and migration script.
# =============================================================================
find_install_dir() {
    # 1. Explicit env var override
    if [[ -n "${AI_MEMORY_INSTALL_DIR:-}" ]] && [[ -d "${AI_MEMORY_INSTALL_DIR}" ]]; then
        echo "${AI_MEMORY_INSTALL_DIR}"
        return 0
    fi

    # 2. Default installed location
    if [[ -d "${HOME}/.ai-memory" ]]; then
        echo "${HOME}/.ai-memory"
        return 0
    fi

    return 1
}

# =============================================================================
# BANNER
# =============================================================================
echo ""
echo -e "${BOLD}━━━ AI Memory — Enable Hybrid Search (v2.2.1) ━━━${NC}"

if [[ "${DRY_RUN}" == "true" ]]; then
    echo ""
    log_warning "DRY RUN MODE — no changes will be made."
fi

# =============================================================================
# STEP 1 — Pre-flight checks
# =============================================================================
step "Step 1/5 — Pre-flight checks"

# 1a. Check Docker is running
if ! docker info &>/dev/null; then
    log_error "Docker daemon is not running. Start Docker first and retry."
    exit 1
fi
log_info "Docker: running"

# 1b. Detect docker directory
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
ENV_FILE="${DOCKER_DIR}/.env"
log_info "Docker dir: ${DOCKER_DIR}"

# 1c. Load environment
load_env

# Port defaults (set after load_env so .env values take precedence)
QDRANT_PORT="${QDRANT_PORT:-26350}"
EMBEDDING_PORT="${EMBEDDING_PORT:-28080}"

# 1d. CRITICAL: Check for QDRANT_API_KEY shell env override (BUG-202 pattern)
if [[ -n "${QDRANT_API_KEY:-}" ]] && [[ -f "${ENV_FILE}" ]]; then
    # Read the .env file value directly
    ENV_FILE_KEY="$(read_env_value "QDRANT_API_KEY")"
    if [[ -n "${ENV_FILE_KEY}" ]] && [[ "${QDRANT_API_KEY}" != "${ENV_FILE_KEY}" ]]; then
        log_warning "Shell QDRANT_API_KEY differs from .env file value"
        log_warning "  Shell env OVERRIDES .env — Docker containers read from .env."
        log_warning "  This can cause 401 errors. Recommended: unset QDRANT_API_KEY"
    fi
fi

# Use the key from .env for our curl calls (matches what containers see)
if [[ -f "${ENV_FILE}" ]]; then
    QDRANT_KEY="$(read_env_value "QDRANT_API_KEY")"
else
    QDRANT_KEY="${QDRANT_API_KEY:-}"
fi

# 1e. Check Qdrant is healthy
if ! curl -sf -H "api-key: ${QDRANT_KEY}" "http://localhost:${QDRANT_PORT}/healthz" >/dev/null 2>&1; then
    log_error "Qdrant is not healthy at http://localhost:${QDRANT_PORT}/healthz"
    log_error "Check that Qdrant is running: docker ps | grep qdrant"
    log_error "If using an API key, ensure QDRANT_API_KEY in ${ENV_FILE} is correct."
    exit 1
fi
log_info "Qdrant: healthy (port ${QDRANT_PORT})"

# 1f. Check embedding service is healthy
if ! curl -sf "http://localhost:${EMBEDDING_PORT}/health" >/dev/null 2>&1; then
    log_error "Embedding service is not healthy at http://localhost:${EMBEDDING_PORT}/health"
    log_error "Check that the embedding container is running: docker ps | grep embedding"
    exit 1
fi
log_info "Embedding: healthy (port ${EMBEDDING_PORT})"

# 1g. Check if already enabled
ALREADY_ENABLED=false
HAS_BM25_ENDPOINT=false

if curl -sf "http://localhost:${EMBEDDING_PORT}/health" 2>/dev/null | grep -q '"bm25"'; then
    HAS_BM25_ENDPOINT=true
fi

if [[ -f "${ENV_FILE}" ]]; then
    CURRENT_HYBRID="$(read_env_value "HYBRID_SEARCH_ENABLED")"
    if [[ "${CURRENT_HYBRID}" == "true" ]] && [[ "${HAS_BM25_ENDPOINT}" == "true" ]]; then
        ALREADY_ENABLED=true
    fi
fi

if [[ "${ALREADY_ENABLED}" == "true" ]]; then
    log_info "Hybrid search appears to be already enabled."
    log_info "  HYBRID_SEARCH_ENABLED=true in .env"
    log_info "  Embedding service has BM25 support"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would re-run data migration."
        SKIP_REBUILD=true
    elif [[ -t 0 ]]; then
        # In interactive mode, ask the user
        read -r -p "  Re-run data migration? [Y/n] " answer
        if [[ "${answer}" =~ ^[Nn] ]]; then
            log_info "Nothing to do. Exiting."
            exit 0
        fi
        # If user said yes, skip rebuild and config steps
        SKIP_REBUILD=true
    else
        log_info "Non-interactive mode: proceeding with migration re-run."
        SKIP_REBUILD=true
    fi
fi

log_success "All pre-flight checks passed."

# =============================================================================
# STEP 2 — Embedding container rebuild
# =============================================================================
step "Step 2/5 — Embedding container"

if [[ "${SKIP_REBUILD}" == "true" ]]; then
    log_info "Skipping embedding container rebuild (--skip-rebuild or already enabled)."
elif [[ "${HAS_BM25_ENDPOINT}" == "true" ]]; then
    log_info "Embedding service already has BM25 support — skipping rebuild."
else
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY RUN] Would rebuild embedding container with BM25 sparse model support."
        log_info "[DRY RUN] Would run: docker compose build --no-cache embedding"
        log_info "[DRY RUN] Would run: docker compose up -d embedding"
    else
        log_info "Rebuilding embedding container with BM25 sparse model support..."
        log_info "This may take a few minutes (downloading BM25 model)..."

        # Build with no cache to ensure BM25 model is downloaded
        if ! _compose -f "${COMPOSE_CORE}" build --no-cache embedding; then
            log_error "Embedding container build failed."
            log_error "Check build logs: docker compose -f ${COMPOSE_CORE} logs embedding"
            exit 1
        fi
        log_success "Embedding container built successfully."

        # Start the rebuilt container
        if ! _compose -f "${COMPOSE_CORE}" up -d embedding; then
            log_error "Failed to start embedding container."
            log_error "Check logs: docker compose -f ${COMPOSE_CORE} logs embedding"
            exit 1
        fi
        log_info "Waiting for embedding service to become healthy..."

        # Wait for health check with timeout (max 120 seconds, poll every 5 seconds)
        TIMEOUT=120
        ELAPSED=0
        HEALTHY=false
        while [[ ${ELAPSED} -lt ${TIMEOUT} ]]; do
            if curl -sf "http://localhost:${EMBEDDING_PORT}/health" 2>/dev/null | grep -q '"bm25"'; then
                HEALTHY=true
                break
            fi
            sleep 5
            ELAPSED=$((ELAPSED + 5))
            log_info "  Waiting... (${ELAPSED}s / ${TIMEOUT}s)"
        done

        if [[ "${HEALTHY}" != "true" ]]; then
            log_error "Embedding service did not become healthy with BM25 support within ${TIMEOUT}s."
            log_error "Check logs: docker compose -f ${COMPOSE_CORE} logs embedding"
            exit 1
        fi

        log_success "Embedding container rebuilt and healthy with BM25 support."
    fi
fi

# =============================================================================
# STEP 3 — Configuration update
# =============================================================================
step "Step 3/5 — Configuration"

if [[ ! -f "${ENV_FILE}" ]]; then
    log_error ".env file not found at ${ENV_FILE}"
    log_error "Cannot update configuration without a .env file."
    exit 1
fi

# Read current values
CURRENT_HYBRID="$(read_env_value "HYBRID_SEARCH_ENABLED")"
CURRENT_COLBERT="$(read_env_value "COLBERT_RERANKING_ENABLED")"
CURRENT_COLBERT_MAIN="$(read_env_value "COLBERT_ENABLED")"

if [[ "${CURRENT_HYBRID}" == "true" ]]; then
    log_info "HYBRID_SEARCH_ENABLED=true already set — skipping."
elif [[ "${DRY_RUN}" == "true" ]]; then
    if [[ -n "${CURRENT_HYBRID}" ]]; then
        log_info "[DRY RUN] Would update HYBRID_SEARCH_ENABLED from '${CURRENT_HYBRID}' to 'true'."
    else
        log_info "[DRY RUN] Would append HYBRID_SEARCH_ENABLED=true to ${ENV_FILE}."
    fi
    if [[ -z "${CURRENT_COLBERT}" ]]; then
        log_info "[DRY RUN] Would append COLBERT_RERANKING_ENABLED=false to ${ENV_FILE}."
    fi
    if [[ -z "${CURRENT_COLBERT_MAIN}" ]]; then
        log_info "[DRY RUN] Would append COLBERT_ENABLED=false to ${ENV_FILE}."
    fi
else
    CONFIG_CHANGED=false

    if [[ -n "${CURRENT_HYBRID}" ]]; then
        # Exists but not 'true' — update in place
        sed -i.bak "s/^HYBRID_SEARCH_ENABLED=.*/HYBRID_SEARCH_ENABLED=true/" "${ENV_FILE}" && rm -f "${ENV_FILE}.bak"
        log_info "Updated HYBRID_SEARCH_ENABLED from '${CURRENT_HYBRID}' to 'true'."
        CONFIG_CHANGED=true
    else
        # Not present — append with comment header
        {
            echo ""
            echo "# Hybrid Search (v2.2.1)"
            echo "HYBRID_SEARCH_ENABLED=true"
        } >> "${ENV_FILE}"
        log_info "Added HYBRID_SEARCH_ENABLED=true to ${ENV_FILE}."
        CONFIG_CHANGED=true
    fi

    # Ensure COLBERT_RERANKING_ENABLED exists (default false)
    if [[ -z "${CURRENT_COLBERT}" ]]; then
        echo "COLBERT_RERANKING_ENABLED=false" >> "${ENV_FILE}"
        log_info "Added COLBERT_RERANKING_ENABLED=false (disabled by default)."
    fi

    # Ensure COLBERT_ENABLED exists (default false)
    if [[ -z "${CURRENT_COLBERT_MAIN}" ]]; then
        echo "COLBERT_ENABLED=false" >> "${ENV_FILE}"
        log_info "Added COLBERT_ENABLED=false (disabled by default)."
    fi

    if [[ "${CONFIG_CHANGED}" == "true" ]]; then
        log_success "Configuration updated."
    fi
fi

# =============================================================================
# STEP 4 — Data migration
# =============================================================================
step "Step 4/5 — Data migration"

if [[ "${SKIP_MIGRATION}" == "true" ]]; then
    log_info "Skipping data migration (--skip-migration)."
else
    # Detect install directory
    if ! INSTALL_DIR="$(find_install_dir)"; then
        log_error "Cannot locate AI Memory installation directory."
        log_error "Searched:"
        log_error "  1. \${AI_MEMORY_INSTALL_DIR}  (AI_MEMORY_INSTALL_DIR=${AI_MEMORY_INSTALL_DIR:-<not set>})"
        log_error "  2. ${HOME}/.ai-memory"
        log_error "Fix: Set AI_MEMORY_INSTALL_DIR to your install path."
        exit 1
    fi

    VENV="${INSTALL_DIR}/.venv/bin/python"
    MIGRATE_SCRIPT="${INSTALL_DIR}/scripts/migrate_v221_hybrid_vectors.py"

    # Check Python venv exists
    if [[ ! -x "${VENV}" ]]; then
        log_error "Python venv not found at: ${VENV}"
        log_error "Ensure AI Memory is installed: run install.sh first."
        exit 1
    fi

    # Check migration script exists
    if [[ ! -f "${MIGRATE_SCRIPT}" ]]; then
        log_error "Migration script not found at: ${MIGRATE_SCRIPT}"
        log_error "Ensure AI Memory v2.2.1 is installed: run install.sh Option 1 to update."
        exit 1
    fi

    # Build migration command args
    MIGRATE_ARGS=()
    if [[ "${DRY_RUN}" == "true" ]]; then
        MIGRATE_ARGS+=(--dry-run)
    fi
    if [[ -n "${COLLECTION_ARG}" ]]; then
        MIGRATE_ARGS+=(--collection "${COLLECTION_ARG}")
    fi

    log_info "Running migrate_v221_hybrid_vectors.py..."
    log_info "  Python:  ${VENV}"
    log_info "  Script:  ${MIGRATE_SCRIPT}"
    if [[ ${#MIGRATE_ARGS[@]} -gt 0 ]]; then
        log_info "  Args:    ${MIGRATE_ARGS[*]}"
    fi

    echo ""
    set +e
    "${VENV}" "${MIGRATE_SCRIPT}" "${MIGRATE_ARGS[@]+"${MIGRATE_ARGS[@]}"}"
    migrate_rc=$?
    set -e
    if [[ ${migrate_rc} -ne 0 ]]; then
        echo ""
        log_error "Migration script failed (exit code ${migrate_rc})."
        log_error "Try running with --dry-run first to preview changes:"
        log_error "  $(basename "${BASH_SOURCE[0]}") --dry-run"
        exit 1
    fi
    echo ""
    log_success "Migration complete."
fi

# =============================================================================
# STEP 5 — Verification
# =============================================================================
step "Step 5/5 — Verification"

if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "[DRY RUN] Would verify embedding health and collection sparse config."
    log_info "[DRY RUN] No changes were made."
else
    VERIFY_OK=true

    # 5a. Check embedding health for BM25 support
    HEALTH_RESPONSE="$(curl -sf "http://localhost:${EMBEDDING_PORT}/health" 2>/dev/null || true)"
    if echo "${HEALTH_RESPONSE}" | grep -q '"bm25"'; then
        log_success "Embedding health: sparse_models includes \"bm25\""
    else
        log_warning "Embedding health: BM25 not detected in sparse_models."
        log_warning "  Response: ${HEALTH_RESPONSE}"
        log_warning "  Embedding may need a rebuild: $(basename "${BASH_SOURCE[0]}") (without --skip-rebuild)"
        VERIFY_OK=false
    fi

    # 5b. Check one collection for sparse config
    VERIFY_COLLECTION="${COLLECTION_ARG:-discussions}"
    COLLECTION_RESPONSE="$(curl -sf -H "api-key: ${QDRANT_KEY}" \
        "http://localhost:${QDRANT_PORT}/collections/${VERIFY_COLLECTION}" 2>/dev/null || true)"

    if echo "${COLLECTION_RESPONSE}" | grep -q "bm25"; then
        log_success "Collection '${VERIFY_COLLECTION}': BM25 sparse config present"
    else
        log_warning "Collection '${VERIFY_COLLECTION}': BM25 sparse config not detected."
        if [[ "${SKIP_MIGRATION}" == "true" ]]; then
            log_warning "  Data migration was skipped. Run without --skip-migration to add sparse vectors."
        else
            log_warning "  Migration may not have processed this collection."
            log_warning "  Try: $(basename "${BASH_SOURCE[0]}") --collection ${VERIFY_COLLECTION}"
        fi
        VERIFY_OK=false
    fi

    # 5c. Verify .env has the correct value
    FINAL_HYBRID="$(read_env_value "HYBRID_SEARCH_ENABLED")"
    if [[ "${FINAL_HYBRID}" == "true" ]]; then
        log_success "Configuration: HYBRID_SEARCH_ENABLED=true"
    else
        log_warning "Configuration: HYBRID_SEARCH_ENABLED is '${FINAL_HYBRID:-<not set>}' (expected 'true')"
        VERIFY_OK=false
    fi

    if [[ "${VERIFY_OK}" == "true" ]]; then
        log_success "Hybrid search is now enabled and operational."
    else
        log_warning "Hybrid search configuration updated, but verification had warnings (see above)."
    fi
fi

# =============================================================================
# DONE
# =============================================================================
echo ""
echo -e "${BOLD}━━━ Done ━━━${NC}"
echo ""
