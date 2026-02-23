#!/usr/bin/env bash
# langfuse_setup.sh — Initialize Langfuse for AI Memory
# Usage: ./langfuse_setup.sh [--generate-secrets] [--start] [--health-check]
#        No args = run all steps (generate-secrets + start + health-check)
# Part of the AI Memory installation pipeline.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="${SCRIPT_DIR}/../docker"
ENV_FILE="${DOCKER_DIR}/.env"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Logging (matches install.sh style) ────────────────────────────────────────
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_warn()    { log_warning "$1"; }  # alias
log_error()   { echo -e "${RED}[ERROR]${NC} $1" >&2; }

step() {
    echo ""
    echo -e "${BLUE}━━━ $1 ━━━${NC}"
}

# ── Argument parsing ──────────────────────────────────────────────────────────
DO_ALL=false
DO_SECRETS=false
DO_START=false
DO_HEALTH=false

if [[ $# -eq 0 ]]; then
    DO_ALL=true
    DO_SECRETS=true
    DO_START=true
    DO_HEALTH=true
fi

for arg in "$@"; do
    case "$arg" in
        --generate-secrets) DO_SECRETS=true ;;
        --start)            DO_START=true ;;
        --health-check)     DO_HEALTH=true ;;
        --help|-h)
            echo "Usage: $0 [--generate-secrets] [--start] [--health-check]"
            echo "  No args: run all steps"
            echo "  --generate-secrets  Generate Langfuse secrets, project init vars, and MinIO bucket"
            echo "  --start             Start Langfuse Docker services"
            echo "  --health-check      Wait for health, register custom models, print summary"
            exit 0
            ;;
        *)
            log_error "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

# ── Verify .env exists ────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    log_error ".env not found at: $ENV_FILE"
    log_error "Run the main installer first: scripts/install.sh"
    exit 1
fi

# ── .env helpers ──────────────────────────────────────────────────────────────

# Get value of a key from .env (returns empty string if not set)
env_get() {
    local key="$1"
    grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true
}

# Set or update a key=value in .env (idempotent; appends if absent)
env_set() {
    local key="$1"
    local value="$2"
    if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
        # Update in place — sed with | delimiter to handle hex values safely
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

# Return true if key has a non-empty value
env_has() {
    local val
    val=$(env_get "$1")
    [[ -n "$val" ]]
}

# ── Step 1: Generate secrets ──────────────────────────────────────────────────
generate_secrets() {
    step "Generate Langfuse Secrets"
    local generated=0

    # Helper: generate and store secret if not already set
    gen_secret() {
        local key="$1"
        local cmd="$2"
        if env_has "$key"; then
            log_info "  ${key} — already set, skipping."
        else
            local val
            val=$(eval "$cmd")
            env_set "$key" "$val"
            log_success "  ${key} — generated."
            generated=$((generated + 1))
        fi
    }

    gen_secret "LANGFUSE_DB_PASSWORD"          "openssl rand -hex 32"
    gen_secret "LANGFUSE_CLICKHOUSE_PASSWORD"   "openssl rand -hex 32"
    gen_secret "LANGFUSE_NEXTAUTH_SECRET"       "openssl rand -hex 32"
    gen_secret "LANGFUSE_SALT"                  "openssl rand -hex 32"
    gen_secret "LANGFUSE_ENCRYPTION_KEY"        "openssl rand -hex 32"  # 64 hex chars
    gen_secret "LANGFUSE_S3_ACCESS_KEY"         "openssl rand -hex 16"
    gen_secret "LANGFUSE_S3_SECRET_KEY"         "openssl rand -hex 32"

    if [[ $generated -gt 0 ]]; then
        log_success "Generated ${generated} new secret(s) → ${ENV_FILE}"
    else
        log_info "All secrets already set — no changes."
    fi
}

# ── Step 2: Generate project init vars + API keys (before first start) ────────
setup_project_keys() {
    step "Langfuse Project Init Vars + API Keys"

    if env_has "LANGFUSE_PUBLIC_KEY" && env_has "LANGFUSE_SECRET_KEY"; then
        log_info "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY already set — skipping."
        return 0
    fi

    local public_key="pk-lf-$(openssl rand -hex 20)"
    local secret_key="sk-lf-$(openssl rand -hex 20)"
    # Password must meet Langfuse complexity: 8+ chars, uppercase, special char
    local admin_password
    admin_password="Lf$(openssl rand -hex 6)!$(openssl rand -hex 4)"

    # Write Langfuse v3 bootstrap env vars — picked up by langfuse-web on first start
    env_set "LANGFUSE_INIT_ORG_ID"                "ai-memory-org"
    env_set "LANGFUSE_INIT_ORG_NAME"              "AI Memory"
    env_set "LANGFUSE_INIT_PROJECT_ID"            "ai-memory-project"
    env_set "LANGFUSE_INIT_PROJECT_NAME"          "ai-memory"
    env_set "LANGFUSE_INIT_PROJECT_PUBLIC_KEY"    "$public_key"
    env_set "LANGFUSE_INIT_PROJECT_SECRET_KEY"    "$secret_key"
    env_set "LANGFUSE_INIT_USER_EMAIL"            "admin@example.com"
    env_set "LANGFUSE_INIT_USER_NAME"             "admin"
    env_set "LANGFUSE_INIT_USER_PASSWORD"         "$admin_password"

    # Runtime API keys used by Python SDK and model registration
    env_set "LANGFUSE_PUBLIC_KEY" "$public_key"
    env_set "LANGFUSE_SECRET_KEY" "$secret_key"
    env_set "LANGFUSE_ENABLED"    "true"

    log_success "API keys generated and written to .env"
    log_info "  Admin email:    admin@example.com"
    log_info "  Admin password: ${admin_password} (stored as LANGFUSE_INIT_USER_PASSWORD)"
    log_info "  Public key:     ${public_key}"
    log_warning "Protect ${ENV_FILE} — it contains secrets."
}

# ── Step 3: Create MinIO bucket ───────────────────────────────────────────────
create_minio_bucket() {
    step "Create MinIO Bucket"

    local access_key secret_key minio_port
    access_key=$(env_get "LANGFUSE_S3_ACCESS_KEY")
    secret_key=$(env_get "LANGFUSE_S3_SECRET_KEY")
    minio_port=$(env_get "LANGFUSE_MINIO_PORT")
    minio_port="${minio_port:-29000}"

    if [[ -z "$access_key" || -z "$secret_key" ]]; then
        log_error "LANGFUSE_S3_ACCESS_KEY / LANGFUSE_S3_SECRET_KEY not set — run --generate-secrets first."
        exit 1
    fi

    # Start only the MinIO service temporarily
    log_info "Starting MinIO service..."
    (
        cd "$DOCKER_DIR"
        docker compose -f docker-compose.yml -f docker-compose.langfuse.yml \
            --profile langfuse up -d langfuse-minio
    )

    # Wait up to 30s for MinIO liveness endpoint
    log_info "Waiting for MinIO to be ready..."
    local elapsed=0
    while ! curl -sf "http://localhost:${minio_port}/minio/health/live" >/dev/null 2>&1; do
        if [[ $elapsed -ge 30 ]]; then
            log_error "MinIO did not become ready within 30s."
            exit 1
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    log_success "MinIO is ready."

    # Create langfuse bucket using the minio/mc docker image
    # Uses --network host so localhost resolves to the host's MinIO port.
    # Chainguard MinIO (our service image) is distroless and has no mc CLI,
    # so we spin up the standard minio/mc image for this one operation.
    log_info "Creating 'langfuse' bucket..."
    docker run --rm \
        --network host \
        "minio/mc" \
        sh -c "mc alias set myminio http://localhost:${minio_port} ${access_key} ${secret_key} --quiet \
               && mc mb myminio/langfuse --ignore-existing --quiet" \
        2>&1 | grep -v '^$' || {
            log_warning "mc bucket creation returned non-zero — bucket may already exist."
        }

    log_success "MinIO bucket 'langfuse' is ready."
}

# ── Step 4: Start services ────────────────────────────────────────────────────
start_services() {
    step "Start Langfuse Services"

    # Warn if bucket may not exist (user ran --start without --generate-secrets)
    if ! env_has "LANGFUSE_S3_ACCESS_KEY"; then
        log_warning "LANGFUSE_S3_ACCESS_KEY not set — MinIO bucket may not exist."
        log_warning "Run with --generate-secrets first, or run all steps (no args)."
    fi

    log_info "Running: docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile langfuse up -d"
    (
        cd "$DOCKER_DIR"
        docker compose \
            -f docker-compose.yml \
            -f docker-compose.langfuse.yml \
            --profile langfuse \
            up -d
    )
    log_success "Langfuse services started."
}

# ── Step 5: Health check ──────────────────────────────────────────────────────
run_health_check() {
    step "Health Check"

    local web_port
    web_port=$(env_get "LANGFUSE_WEB_PORT")
    web_port="${web_port:-23100}"

    local health_url="http://localhost:${web_port}/api/public/health"

    log_info "Waiting for Langfuse web at ${health_url} (max 120s)..."
    local elapsed=0
    while true; do
        local response
        response=$(curl -sf "$health_url" 2>/dev/null || echo "")
        if echo "$response" | grep -qi '"status"'; then
            if echo "$response" | grep -qi '"OK"\|"ok"'; then
                log_success "Langfuse web is healthy (${elapsed}s elapsed)."
                break
            fi
        fi
        if [[ $elapsed -ge 120 ]]; then
            log_error "Langfuse web did not become healthy within 120s."
            log_error "  Response: ${response:-<no response>}"
            log_error "  Logs: cd ${DOCKER_DIR} && docker compose -f docker-compose.yml -f docker-compose.langfuse.yml logs langfuse-web"
            exit 1
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    # Check worker containers
    local prefix
    prefix=$(env_get "AI_MEMORY_CONTAINER_PREFIX")
    prefix="${prefix:-ai-memory}"

    local worker_running=false
    if docker ps --filter "name=${prefix}-langfuse-worker" --filter "status=running" -q 2>/dev/null | grep -q .; then
        log_success "langfuse-worker is running."
        worker_running=true
    else
        log_warning "langfuse-worker is not running — check: docker ps | grep langfuse-worker"
    fi

    if docker ps --filter "name=${prefix}-trace-flush-worker" --filter "status=running" -q 2>/dev/null | grep -q .; then
        log_success "trace-flush-worker is running."
    else
        log_warning "trace-flush-worker is not running — it may start after API keys are applied."
    fi
}

# ── Step 5b: Verify bootstrap (org/project/user were created) ────────────────
verify_bootstrap() {
    step "Verify Langfuse Bootstrap"

    local public_key secret_key web_port
    public_key=$(env_get "LANGFUSE_PUBLIC_KEY")
    secret_key=$(env_get "LANGFUSE_SECRET_KEY")
    web_port=$(env_get "LANGFUSE_WEB_PORT")
    web_port="${web_port:-23100}"

    if [[ -z "$public_key" || -z "$secret_key" ]]; then
        log_warning "LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set — skipping bootstrap verification."
        return 0
    fi

    local base_url="http://localhost:${web_port}"

    # Returns "yes" if auth succeeds and at least one project exists, else "no"
    _bootstrap_ok() {
        local resp
        resp=$(curl -sf \
            -u "${public_key}:${secret_key}" \
            "${base_url}/api/public/projects" 2>/dev/null || echo "")
        [[ -z "$resp" ]] && { echo "no"; return; }
        echo "$resp" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    items = d if isinstance(d, list) else d.get('data', [])
    print('yes' if items else 'no')
except Exception:
    print('no')
" 2>/dev/null || echo "no"
    }

    log_info "Checking Langfuse bootstrap (org, project, user)..."

    if [[ "$(_bootstrap_ok)" == "yes" ]]; then
        log_success "Langfuse bootstrap verified — org and project exist."
        return 0
    fi

    # Bootstrap did not take effect — wipe volumes and retry once
    log_warning "Langfuse bootstrap did not take effect — cleaning volumes and restarting..."

    (
        cd "$DOCKER_DIR"
        docker compose -f docker-compose.yml -f docker-compose.langfuse.yml \
            --profile langfuse stop \
            langfuse-web langfuse-worker langfuse-postgres langfuse-clickhouse langfuse-redis langfuse-minio
        docker compose -f docker-compose.yml -f docker-compose.langfuse.yml \
            --profile langfuse rm -f \
            langfuse-web langfuse-worker langfuse-postgres langfuse-clickhouse langfuse-redis langfuse-minio
    )

    docker volume rm \
        ai-memory-langfuse-postgres-data \
        ai-memory-langfuse-clickhouse-data \
        ai-memory-langfuse-redis-data \
        ai-memory-langfuse-minio-data 2>/dev/null || true

    start_services
    run_health_check

    if [[ "$(_bootstrap_ok)" == "yes" ]]; then
        log_success "Langfuse bootstrap verified after restart — org and project exist."
        return 0
    fi

    log_error "Langfuse bootstrap failed even after volume reset and restart."
    log_error "Manual recovery steps:"
    log_error "  1. cd ${DOCKER_DIR}"
    log_error "  2. docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile langfuse down -v"
    log_error "  3. Re-run the installer: scripts/install.sh"
    exit 1
}

# ── Step 6: Register custom models ───────────────────────────────────────────
register_custom_models() {
    step "Register Custom Model Patterns"

    local secret_key web_port public_key
    secret_key=$(env_get "LANGFUSE_SECRET_KEY")
    public_key=$(env_get "LANGFUSE_PUBLIC_KEY")
    web_port=$(env_get "LANGFUSE_WEB_PORT")
    web_port="${web_port:-23100}"

    if [[ -z "$secret_key" || -z "$public_key" ]]; then
        log_error "LANGFUSE_SECRET_KEY or LANGFUSE_PUBLIC_KEY not set — cannot register models."
        return 1
    fi

    local base_url="http://localhost:${web_port}"

    # Fetch existing model names (idempotency check)
    log_info "Checking existing model registrations..."
    local existing=""
    existing=$(curl -sf \
        -u "${public_key}:${secret_key}" \
        "${base_url}/api/public/models" 2>/dev/null \
        | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data if isinstance(data, list) else data.get('data', data.get('models', []))
    for m in items:
        name = m.get('modelName', '')
        if name:
            print(name)
except Exception:
    pass
" 2>/dev/null || echo "")

    # Registration helper
    register_model() {
        local name="$1"
        local match_pattern="$2"
        local payload
        payload="$(printf '{"modelName":"%s","matchPattern":"%s","inputPrice":0,"outputPrice":0,"unit":"TOKENS"}' \
            "$name" "$match_pattern")"

        local result
        result=$(curl -sf -X POST "${base_url}/api/public/models" \
            -u "${public_key}:${secret_key}" \
            -H "Content-Type: application/json" \
            -d "$payload" 2>&1 || echo "CURL_ERROR")

        if echo "$result" | grep -qi "CURL_ERROR\|\"error\"\|\"message\""; then
            log_warning "  Registration response for '${name}': ${result}"
        else
            log_success "  Registered: ${name}"
        fi
    }

    # Process each model pattern
    local registered=0 skipped=0

    # Pattern 1: ollama/* — all local Ollama models (free)
    if echo "$existing" | grep -qxF "ollama/*"; then
        log_info "  'ollama/*' already registered — skipping."
        skipped=$((skipped + 1))
    else
        register_model "ollama/*" "ollama/.*"
        registered=$((registered + 1))
    fi

    # Pattern 2: openrouter/*:free — OpenRouter free tier (free)
    if echo "$existing" | grep -qxF "openrouter/*:free"; then
        log_info "  'openrouter/*:free' already registered — skipping."
        skipped=$((skipped + 1))
    else
        register_model "openrouter/*:free" "openrouter/.*:free"
        registered=$((registered + 1))
    fi

    # Pattern 3: openrouter/* — OpenRouter paid tier (user-configurable pricing)
    if echo "$existing" | grep -qxF "openrouter/*"; then
        log_info "  'openrouter/*' already registered — skipping."
        skipped=$((skipped + 1))
    else
        register_model "openrouter/*" "openrouter/.*"
        registered=$((registered + 1))
    fi

    log_info "Model registration: ${registered} new, ${skipped} already present (total 3 patterns)."
}

# ── Step 7: Print summary ─────────────────────────────────────────────────────
print_summary() {
    local web_port public_key secret_key enabled
    web_port=$(env_get "LANGFUSE_WEB_PORT")
    web_port="${web_port:-23100}"
    public_key=$(env_get "LANGFUSE_PUBLIC_KEY")
    secret_key=$(env_get "LANGFUSE_SECRET_KEY")
    enabled=$(env_get "LANGFUSE_ENABLED")

    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Langfuse Setup Complete  ${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${BLUE}Langfuse UI:${NC}      http://localhost:${web_port}"
    echo -e "  ${BLUE}Health API:${NC}       http://localhost:${web_port}/api/public/health"
    echo ""
    if [[ -n "$public_key" ]]; then
        echo -e "  ${BLUE}Public Key:${NC}       ${public_key}"
        echo -e "  ${BLUE}Secret Key:${NC}       ${secret_key:0:16}... (see .env)"
        echo -e "  ${BLUE}Enabled:${NC}          ${enabled:-false}"
    else
        echo -e "  ${YELLOW}API Keys:${NC}         Not configured (run with --generate-secrets)"
    fi
    echo ""
    echo -e "  ${BLUE}Custom Models:${NC}    ollama/*, openrouter/*:free, openrouter/*"
    echo -e "  ${BLUE}Config file:${NC}      ${ENV_FILE}"
    echo ""
    echo -e "  To view logs:  cd ${DOCKER_DIR} && docker compose -f docker-compose.yml -f docker-compose.langfuse.yml logs"
    echo -e "  To stop:       cd ${DOCKER_DIR} && docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile langfuse stop"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    log_info "Langfuse Setup Script"
    log_info "ENV file: ${ENV_FILE}"

    # --generate-secrets: steps 1–3 (secrets, project init vars, MinIO bucket)
    if [[ "$DO_SECRETS" == true ]]; then
        generate_secrets
        setup_project_keys
        create_minio_bucket
    fi

    # --start: step 4 (full stack up)
    if [[ "$DO_START" == true ]]; then
        start_services
    fi

    # --health-check: steps 5–7 (health, model registration, summary)
    if [[ "$DO_HEALTH" == true ]]; then
        run_health_check
        verify_bootstrap
        register_custom_models
        print_summary
    elif [[ "$DO_SECRETS" == true || "$DO_START" == true ]]; then
        # Print brief summary even when health check not requested
        echo ""
        log_info "Run with --health-check to verify services and register models."
        log_info "Langfuse UI: http://localhost:$(env_get "LANGFUSE_WEB_PORT" || echo "23100")"
    fi
}

main "$@"
