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
shopt -s nullglob

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

        # BUG-097: Do NOT auto-destroy containers on failure.
        # Running containers with their logs are the most valuable diagnostic tool.
        # Previous behavior ran `docker compose down` without profile flags, which
        # killed only qdrant + embedding (default-scope) while leaving 7 profile
        # services orphaned — the root cause of "mysterious container disappearance"
        # across Tests 1-5.
        if [[ "${INSTALL_MODE:-full}" == "full" && -f "$INSTALL_DIR/docker/docker-compose.yml" ]]; then
            echo ""
            log_info "Docker services left running for inspection."
            log_info "  View logs:  cd $INSTALL_DIR/docker && docker compose logs"
            log_info "  Stop all:   cd $INSTALL_DIR/docker && docker compose --profile monitoring --profile github down"
        fi

        echo ""
        if [[ "${INSTALL_MODE:-full}" == "add-project" ]]; then
            echo "Project setup failed. Shared installation at $INSTALL_DIR is intact."
            echo "To retry: ./install.sh \"$PROJECT_PATH\" \"$PROJECT_NAME\""
        else
            echo "Partial installation exists at: $INSTALL_DIR"
            echo "To clean up and retry:"
            echo "  rm -rf \"$INSTALL_DIR\""
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

# Convert comma-separated Jira project keys to JSON array for .env file
# Required because Pydantic Settings v2.12 calls json.loads() on list[str]
# fields from DotEnvSettingsSource BEFORE @field_validator runs (BUG-069)
format_jira_projects_json() {
    local input="${1:-}"
    if [[ -z "$input" ]]; then
        echo "[]"
        return
    fi
    local result
    result=$(echo "$input" | python3 -c "
import json, sys
keys = [k.strip() for k in sys.stdin.read().strip().split(',') if k.strip()]
print(json.dumps(keys))
" 2>/dev/null) || {
        log_warning "Failed to convert JIRA_PROJECTS '$input' to JSON (python3 error), using empty list"
        result="[]"
    }
    echo "$result"
}

# Configuration flags (set by interactive prompts or environment)
INSTALL_MONITORING="${INSTALL_MONITORING:-}"
SEED_BEST_PRACTICES="${SEED_BEST_PRACTICES:-}"
NON_INTERACTIVE="${NON_INTERACTIVE:-false}"
INSTALL_MODE="${INSTALL_MODE:-full}"  # full or add-project (set by check_existing_installation)

# Jira sync configuration (PLAN-004 Phase 2)
JIRA_SYNC_ENABLED="${JIRA_SYNC_ENABLED:-}"
JIRA_INSTANCE_URL="${JIRA_INSTANCE_URL:-}"
JIRA_EMAIL="${JIRA_EMAIL:-}"
JIRA_API_TOKEN="${JIRA_API_TOKEN:-}"
JIRA_PROJECTS="${JIRA_PROJECTS:-}"
JIRA_INITIAL_SYNC="${JIRA_INITIAL_SYNC:-}"

# GitHub sync configuration (PLAN-006 Phase 1a)
GITHUB_SYNC_ENABLED="${GITHUB_SYNC_ENABLED:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
GITHUB_REPO="${GITHUB_REPO:-}"
GITHUB_INITIAL_SYNC="${GITHUB_INITIAL_SYNC:-}"

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

    # Jira Cloud Integration (PLAN-004 Phase 2)
    if [[ -z "$JIRA_SYNC_ENABLED" ]]; then
        echo "🔗 Jira Cloud Integration (Optional)"
        echo "   Syncs issues and comments to memory for semantic search"
        echo "   Enables Claude to retrieve work context from Jira"
        echo ""
        read -p "   Enable Jira sync? [y/N]: " jira_choice

        if [[ "$jira_choice" =~ ^[Yy]$ ]]; then
            JIRA_SYNC_ENABLED="true"

            # Collect credentials
            echo ""
            read -p "   Jira instance URL (e.g., https://company.atlassian.net): " jira_url
            JIRA_INSTANCE_URL="$jira_url"

            read -p "   Jira email: " jira_email
            JIRA_EMAIL="$jira_email"

            echo "   Generate API token: https://id.atlassian.com/manage-profile/security/api-tokens"
            read -sp "   Jira API token (hidden): " jira_token
            JIRA_API_TOKEN="$jira_token"
            echo ""

            # Strip trailing slash for consistent URL handling (matches JiraClient behavior)
            JIRA_INSTANCE_URL="${JIRA_INSTANCE_URL%/}"

            # Validate credentials via curl smoke test (BP-053: Two-Phase Validation)
            # Full Python validation runs later in validate_external_services()
            echo ""
            log_info "Testing Jira connection..."

            # Jira Cloud REST API v3 Basic Auth: base64(email:api_token)
            local jira_auth
            jira_auth=$(printf '%s:%s' "$JIRA_EMAIL" "$JIRA_API_TOKEN" | base64 | tr -d '\n')

            local http_code
            http_code=$(curl -s -o /dev/null -w "%{http_code}" \
                -H "Authorization: Basic $jira_auth" \
                -H "Content-Type: application/json" \
                "${JIRA_INSTANCE_URL}/rest/api/3/myself" \
                --connect-timeout 10 --max-time 15 2>/dev/null)

            if [[ "$http_code" == "200" ]]; then
                log_success "Jira connection verified (HTTP 200)"

                # Auto-discover Jira projects (BUG-068: replaces manual key entry)
                log_info "Fetching available Jira projects..."
                local projects_json
                projects_json=$(curl -s \
                    -H "Authorization: Basic $jira_auth" \
                    -H "Content-Type: application/json" \
                    "${JIRA_INSTANCE_URL}/rest/api/3/project/search?maxResults=100" \
                    --connect-timeout 10 --max-time 15 2>/dev/null) || projects_json=""

                if [[ -n "$projects_json" ]]; then
                    # Parse project keys and names using system python3
                    local project_list
                    project_list=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    projects = data.get('values', data) if isinstance(data, dict) else data
    if not isinstance(projects, list) or len(projects) == 0:
        print('EMPTY')
        sys.exit(0)
    for i, p in enumerate(projects, 1):
        print(f\"{i}. {p['key']}: {p.get('name', p['key'])}\")
except Exception:
    print('ERROR')
" <<< "$projects_json" 2>/dev/null) || project_list="ERROR"

                    if [[ "$project_list" != "EMPTY" && "$project_list" != "ERROR" && -n "$project_list" ]]; then
                        echo ""
                        echo "   Available projects on ${JIRA_INSTANCE_URL#https://}:"
                        echo "$project_list" | while IFS= read -r line; do
                            echo "     $line"
                        done
                        echo ""
                        read -p "   Which projects to sync? (comma-separated numbers, or 'all'): " project_selection

                        if [[ "$project_selection" == "all" ]]; then
                            JIRA_PROJECTS=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
projects = data.get('values', data) if isinstance(data, dict) else data
print(','.join(p['key'] for p in projects))
" <<< "$projects_json" 2>/dev/null) || JIRA_PROJECTS=""
                        else
                            JIRA_PROJECTS=$(_PROJ_SEL="$project_selection" python3 -c "
import json, sys, os
data = json.loads(sys.stdin.read())
projects = data.get('values', data) if isinstance(data, dict) else data
sel_input = os.environ.get('_PROJ_SEL', '')
selections = [int(s.strip()) for s in sel_input.split(',') if s.strip().isdigit()]
keys = [projects[i-1]['key'] for i in selections if 0 < i <= len(projects)]
print(','.join(keys))
" <<< "$projects_json" 2>/dev/null) || JIRA_PROJECTS=""
                        fi

                        if [[ -n "$JIRA_PROJECTS" ]]; then
                            log_success "Selected projects: $JIRA_PROJECTS"
                        else
                            log_error "No valid projects selected — Jira sync disabled"
                            JIRA_SYNC_ENABLED="false"
                        fi
                    else
                        log_warning "Could not fetch project list — enter keys manually"
                        read -p "   Project keys (comma-separated): " jira_projects
                        JIRA_PROJECTS="$jira_projects"
                        if [[ -z "$JIRA_PROJECTS" ]]; then
                            log_error "No projects entered — Jira sync disabled"
                            JIRA_SYNC_ENABLED="false"
                        fi
                    fi
                else
                    log_warning "Could not fetch project list — enter keys manually"
                    read -p "   Project keys (comma-separated): " jira_projects
                    JIRA_PROJECTS="$jira_projects"
                    if [[ -z "$JIRA_PROJECTS" ]]; then
                        log_error "No projects entered — Jira sync disabled"
                        JIRA_SYNC_ENABLED="false"
                    fi
                fi

                # Prompt for initial sync
                echo ""
                echo "   Initial sync can take 5-10 minutes for large projects"
                read -p "   Run initial sync now? [y/N]: " initial_sync
                if [[ "$initial_sync" =~ ^[Yy]$ ]]; then
                    JIRA_INITIAL_SYNC="true"
                else
                    JIRA_INITIAL_SYNC="false"
                fi
            else
                log_error "Jira connection test failed (HTTP $http_code) - sync will be disabled"
                log_info "Verify: URL, email, and API token at https://id.atlassian.com/manage-profile/security/api-tokens"
                JIRA_SYNC_ENABLED="false"
            fi
        else
            JIRA_SYNC_ENABLED="false"
        fi
        echo ""
    fi

    # GitHub Integration (PLAN-006 Phase 1a)
    if [[ -z "$GITHUB_SYNC_ENABLED" ]]; then
        echo "GitHub Integration (Optional)"
        echo "   Syncs issues, PRs, commits, and code to memory for semantic search"
        echo "   Enables Claude to retrieve development context from GitHub"
        echo ""
        read -p "   Enable GitHub sync? [y/N]: " github_choice

        if [[ "$github_choice" =~ ^[Yy]$ ]]; then
            GITHUB_SYNC_ENABLED="true"

            # PAT guidance
            echo ""
            echo "   GitHub Personal Access Token (PAT) Setup:"
            echo "   - Use FINE-GRAINED tokens (not classic): https://github.com/settings/tokens?type=beta"
            echo "   - Minimum scopes: Contents (read), Issues (read), Pull Requests (read), Actions (read)"
            echo "   - Set expiration (90 days recommended)"
            echo ""
            echo "   IMPORTANT: Enter the FULL token exactly as shown by GitHub."
            echo "   Fine-grained tokens start with: github_pat_..."
            echo "   Classic tokens start with: ghp_..."
            echo "   Include the entire string including the prefix."
            echo ""

            read -sp "   GitHub PAT (hidden): " github_token
            GITHUB_TOKEN="$github_token"
            echo ""

            # Validate PAT format
            if [[ ! "$GITHUB_TOKEN" =~ ^(github_pat_|ghp_|gho_|ghs_|ghr_) ]]; then
                log_warning "Token doesn't match known GitHub PAT formats (github_pat_*, ghp_*, etc.)"
                log_warning "Make sure you entered the FULL token including the prefix"
            fi

            # Auto-detect repo from .git remote
            local detected_repo="" detected_owner="" detected_name=""
            if [[ -d "$PROJECT_PATH/.git" ]]; then
                detected_repo=$(cd "$PROJECT_PATH" && git remote get-url origin 2>/dev/null | sed -E 's|.*github\.com[:/](.+/[^.]+)(\.git)?$|\1|' || true)
                if [[ -n "$detected_repo" ]]; then
                    detected_owner="${detected_repo%%/*}"
                    detected_name="${detected_repo##*/}"
                fi
            fi

            if [[ -n "$detected_repo" ]]; then
                echo "   Detected repository: $detected_repo"
                read -p "   Use this repo? [Y/n]: " use_detected
                if [[ ! "$use_detected" =~ ^[Nn]$ ]]; then
                    GITHUB_REPO="$detected_repo"
                else
                    echo ""
                    read -p "   GitHub username or organization: " github_owner
                    read -p "   Repository name: " github_name
                    GITHUB_REPO="${github_owner}/${github_name}"
                fi
            else
                echo ""
                read -p "   GitHub username or organization: " github_owner
                read -p "   Repository name: " github_name
                GITHUB_REPO="${github_owner}/${github_name}"
            fi

            # Validate PAT via GitHub API
            echo ""
            log_info "Testing GitHub connection..."

            local http_code
            http_code=$(curl -s -o /dev/null -w "%{http_code}" \
                -H "Authorization: Bearer $GITHUB_TOKEN" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/${GITHUB_REPO}" \
                --connect-timeout 10 --max-time 15 2>/dev/null)

            if [[ "$http_code" == "200" ]]; then
                log_success "GitHub connection verified (HTTP 200) — repo: $GITHUB_REPO"

                # Prompt for initial sync
                echo ""
                echo "   Initial sync can take 5-30 minutes depending on repo size"
                read -p "   Run initial sync after install? [y/N]: " initial_sync
                if [[ "$initial_sync" =~ ^[Yy]$ ]]; then
                    GITHUB_INITIAL_SYNC="true"
                else
                    GITHUB_INITIAL_SYNC="false"
                fi
            else
                log_error "GitHub connection test failed (HTTP $http_code)"
                log_info "Verify: PAT scopes and repository access"
                GITHUB_SYNC_ENABLED="false"
            fi
        else
            GITHUB_SYNC_ENABLED="false"
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
    if [[ "$JIRA_SYNC_ENABLED" == "true" ]]; then
        echo "│    ✓ Jira Cloud sync (${JIRA_PROJECTS})                     │"
    fi
    if [[ "$GITHUB_SYNC_ENABLED" == "true" ]]; then
        echo "│    ✓ GitHub sync (${GITHUB_REPO})                     │"
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

# Configure secrets storage backend (SPEC-011)
configure_secrets_backend() {
    # Skip if non-interactive mode
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        SECRETS_BACKEND="${SECRETS_BACKEND:-env-file}"
        log_info "Non-interactive mode - using secrets backend: $SECRETS_BACKEND"
        return 0
    fi

    echo ""
    echo "=== Secrets Storage ==="
    echo ""
    echo "How would you like to store API keys and tokens?"
    echo ""
    echo "  [1] SOPS+age encryption (Recommended)"
    echo "      Secrets encrypted in Git. Requires: sops, age (brew install sops age)"
    echo ""
    echo "  [2] System keyring (OS-level encryption)"
    echo "      Uses macOS Keychain / GNOME Keyring / Windows Credential Locker"
    echo ""
    echo "  [3] .env file (Minimum security)"
    echo "      Plaintext on disk. NOT recommended for shared machines."
    echo ""
    read -r -p "Choose [1/2/3] (default: 3): " SECRETS_CHOICE

    case "${SECRETS_CHOICE:-3}" in
        1)
            SECRETS_BACKEND="sops-age"
            if command -v sops &>/dev/null && command -v age-keygen &>/dev/null; then
                log_info "sops and age found. Running setup..."
                bash "$SCRIPT_DIR/setup-secrets.sh"
            else
                log_warning "sops and/or age not found."
                echo "Install: brew install sops age  OR  apt install sops age"
                echo "Then run: ./scripts/setup-secrets.sh"
                echo "Falling back to .env file for now."
                SECRETS_BACKEND="env-file"
            fi
            ;;
        2)
            SECRETS_BACKEND="keyring"
            if "$INSTALL_DIR/.venv/bin/pip" install keyring 2>/dev/null; then
                log_success "keyring installed successfully"
            else
                log_warning "Failed to install keyring. Falling back to .env file."
                SECRETS_BACKEND="env-file"
            fi
            ;;
        3|*)
            SECRETS_BACKEND="env-file"
            log_warning "Using plaintext .env file. Consider upgrading to SOPS+age."
            ;;
    esac

    # Store backend choice in .env
    local docker_env="$INSTALL_DIR/docker/.env"
    if grep -q "^AI_MEMORY_SECRETS_BACKEND=" "$docker_env" 2>/dev/null; then
        sed -i.bak "s|^AI_MEMORY_SECRETS_BACKEND=.*|AI_MEMORY_SECRETS_BACKEND=$SECRETS_BACKEND|" "$docker_env" && rm -f "$docker_env.bak"
    else
        echo "" >> "$docker_env"
        echo "# Secrets Backend (SPEC-011)" >> "$docker_env"
        echo "AI_MEMORY_SECRETS_BACKEND=$SECRETS_BACKEND" >> "$docker_env"
    fi
    log_success "Secrets backend set to: $SECRETS_BACKEND"
    echo ""
}

# Main orchestration function
main() {
    INSTALL_STARTED=true  # Enable cleanup handler

    # Persistent install logging — captures ALL output to a log file
    # Essential for diagnosing issues like P1 (container disappearance)
    mkdir -p "$INSTALL_DIR/logs" 2>/dev/null || true
    INSTALL_LOG="$INSTALL_DIR/logs/install-$(date +%Y%m%d-%H%M%S).log"
    exec > >(tee -a "$INSTALL_LOG") 2>&1
    log_info "Install log: $INSTALL_LOG"

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
        install_python_dependencies
        configure_environment
        validate_external_services
        configure_secrets_backend

        # Skip Docker-related steps if SKIP_DOCKER_CHECKS is set (for CI without Docker)
        if [[ "${SKIP_DOCKER_CHECKS:-}" == "true" ]]; then
            log_info "Skipping Docker services (SKIP_DOCKER_CHECKS=true)"
            copy_env_template
        else
            start_services
            wait_for_services
            setup_collections
            copy_env_template
            run_health_check
            seed_best_practices
            run_initial_jira_sync
            setup_jira_cron
            setup_github_indexes
            run_initial_github_sync
        fi
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
    setup_audit_directory

    # Parzival session agent (optional, SPEC-015)
    setup_parzival

    # Record project in manifest for cross-filesystem recovery discovery
    record_installed_project

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

        # Non-interactive fallback: default to add-project mode
        if [[ "$NON_INTERACTIVE" == "true" ]]; then
            log_info "Non-interactive mode - defaulting to add-project mode"
            INSTALL_MODE="add-project"
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
            updated_count=$((updated_count + 1))
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
                hooks_count=$((hooks_count + 1))
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
                    archived_count=$((archived_count + 1))
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

    # SKIP_DOCKER_CHECKS: For CI environments without Docker (e.g., macOS GitHub Actions)
    if [[ "${SKIP_DOCKER_CHECKS:-}" == "true" ]]; then
        log_info "Skipping Docker checks (SKIP_DOCKER_CHECKS=true)"
    else
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
    fi

    # Check curl (REQUIRED for health checks and API validation)
    if ! command -v curl &> /dev/null; then
        log_error "curl is not installed (required for health checks and API validation)"
        echo ""
        echo "Please install curl:"
        echo "  Ubuntu/Debian: sudo apt install curl"
        echo "  macOS: brew install curl"
        echo ""
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
    # SKIP when SKIP_DOCKER_CHECKS is set (no services to bind ports)
    if [[ "${SKIP_DOCKER_CHECKS:-}" == "true" ]]; then
        log_info "Skipping port checks (SKIP_DOCKER_CHECKS=true)"
    elif [[ "${INSTALL_MODE:-full}" == "full" ]]; then
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
        echo "     ├── .locks/              (Process lock files)"
        echo "     └── logs/                (Application logs)"
        echo ""
        echo "  📁 \$INSTALL_DIR/queue/    (Private queue, chmod 700)"
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
    mkdir -p "$INSTALL_DIR"/{docker,src/memory,scripts,.claude/hooks/scripts,.claude/skills,.claude/agents,logs,queue,.locks}

    # Create queue directory with restricted permissions (security best practice 2026)
    # Queue is shared across all projects - single classifier worker processes all
    chmod 700 "$INSTALL_DIR/queue"  # Private queue directory (already created above)

    log_success "Directory structure created at $INSTALL_DIR"
    log_info "Private queue directory: $INSTALL_DIR/queue (chmod 700)"
}

# Python dependency installation (BUG-054)
# Installs Python dependencies using pip, handling venv detection and PEP 668 compliance
install_python_dependencies() {
    log_info "Installing Python dependencies..."

    # Determine source directory for pyproject.toml
    local source_dir
    if [[ -f "$SCRIPT_DIR/../pyproject.toml" ]]; then
        source_dir="$(cd "$SCRIPT_DIR/.." && pwd)"
    elif [[ -f "./pyproject.toml" ]]; then
        source_dir="$(pwd)"
    else
        log_warning "pyproject.toml not found - skipping Python dependencies"
        log_info "You can install manually later: pip install -e \".[dev]\""
        return 0
    fi

    # Copy pyproject.toml and requirements.txt to install directory if not already there
    if [[ ! -f "$INSTALL_DIR/pyproject.toml" ]]; then
        cp "$source_dir/pyproject.toml" "$INSTALL_DIR/"
        log_info "Copied pyproject.toml to $INSTALL_DIR"
    fi
    if [[ -f "$source_dir/requirements.txt" && ! -f "$INSTALL_DIR/requirements.txt" ]]; then
        cp "$source_dir/requirements.txt" "$INSTALL_DIR/"
        log_info "Copied requirements.txt to $INSTALL_DIR"
    fi

    # ============================================
    # Always create venv at INSTALL_DIR/.venv
    # (TECH-DEBT-135: hooks require this path)
    # ============================================
    local venv_dir="$INSTALL_DIR/.venv"
    local pip_exit_code=0

    # Check for existing user venv (informational only)
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        log_info "User venv detected at $VIRTUAL_ENV (will create isolated venv for hooks)"
    fi

    # Create or reuse installation venv
    if [[ -d "$venv_dir" ]]; then
        log_info "Using existing venv at $venv_dir"
    else
        log_info "Creating virtual environment at $venv_dir..."
        if ! python3 -m venv "$venv_dir"; then
            log_warning "Failed to create virtual environment"
            log_warning "Python dependencies NOT installed"
            log_info "To install manually:"
            log_info "  python3 -m venv $venv_dir"
            log_info "  source $venv_dir/bin/activate"
            log_info "  pip install -e \"$INSTALL_DIR[dev]\""
            return 0  # Don't fail install
        fi
        log_success "Virtual environment created"
    fi

    # Install in the installation venv (not user's venv)
    log_info "Installing with pip install -e \".[dev]\"..."
    if "$venv_dir/bin/pip" install -e "$INSTALL_DIR[dev]" 2>&1 | tail -5; then
        log_success "Python dependencies installed successfully"
        log_info "Hooks will use: $venv_dir/bin/python"
    else
        pip_exit_code=$?
    fi

    # ============================================
    # Venv Verification (TECH-DEBT-136)
    # ============================================
    if [[ $pip_exit_code -eq 0 ]]; then
        echo ""
        log_info "Verifying venv installation..."

        VENV_PYTHON="$venv_dir/bin/python"

        # Check venv Python exists
        if [ ! -f "$VENV_PYTHON" ]; then
            log_error "Venv Python not found at $VENV_PYTHON"
            log_error "Venv creation failed. Please check permissions and disk space."
            exit 1
        fi

        # Verify critical packages are importable
        log_info "Checking critical dependencies..."

        CRITICAL_PACKAGES=(
            "qdrant_client:Qdrant client for memory storage"
            "prometheus_client:Prometheus metrics"
            "httpx:HTTP client for embedding service"
            "pydantic:Configuration validation"
            "structlog:Logging"
        )

        FAILED_PACKAGES=()

        for pkg_info in "${CRITICAL_PACKAGES[@]}"; do
            pkg_name="${pkg_info%%:*}"
            pkg_desc="${pkg_info##*:}"

            if ! "$VENV_PYTHON" -c "import $pkg_name" 2>/dev/null; then
                echo "  ✗ $pkg_name ($pkg_desc) - FAILED"
                FAILED_PACKAGES+=("$pkg_name")
            else
                echo "  ✓ $pkg_name"
            fi
        done

        if [ ${#FAILED_PACKAGES[@]} -gt 0 ]; then
            echo ""
            log_error "Critical packages failed to import: ${FAILED_PACKAGES[*]}"
            log_error "Installation cannot continue. Please check:"
            echo "  1. Network connectivity (packages may not have downloaded)"
            echo "  2. Disk space"
            echo "  3. Python version compatibility"
            exit 1
        fi

        # Check optional packages (warn but don't fail)
        log_info "Checking optional dependencies..."

        OPTIONAL_PACKAGES=(
            "tree_sitter:AST-based code chunking"
            "tree_sitter_python:Python code parsing"
        )

        for pkg_info in "${OPTIONAL_PACKAGES[@]}"; do
            pkg_name="${pkg_info%%:*}"
            pkg_desc="${pkg_info##*:}"

            if ! "$VENV_PYTHON" -c "import $pkg_name" 2>/dev/null; then
                echo "  ⚠ $pkg_name ($pkg_desc) - Not available (optional feature disabled)"
            else
                echo "  ✓ $pkg_name"
            fi
        done

        log_success "Venv verification passed. All critical packages available."
    fi

    # Handle pip failure gracefully - warn but don't abort install
    if [[ $pip_exit_code -ne 0 ]]; then
        log_warning "pip install failed (exit code: $pip_exit_code)"
        log_warning "Python dependencies NOT installed - hooks may not work correctly"
        echo ""
        echo "To install manually:"
        echo "  source $INSTALL_DIR/.venv/bin/activate"
        echo "  pip install -e \"$INSTALL_DIR[dev]\""
        echo ""
    fi

    return 0  # Always return success - don't fail entire install
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
    cp -r "$SOURCE_DIR/docker/"* "$INSTALL_DIR/docker/" || { log_error "Failed to copy docker files"; exit 1; }
    # BUG-040: Explicitly copy dotfiles - glob .* matches . and .. causing failures
    # Copy .env if it exists in source (contains credentials)
    if [[ -f "$SOURCE_DIR/docker/.env" ]]; then
        cp "$SOURCE_DIR/docker/.env" "$INSTALL_DIR/docker/"
        log_info "Copied docker/.env with credentials from source"
    fi
    # Copy .env.example if it exists
    if [[ -f "$SOURCE_DIR/docker/.env.example" ]]; then
        cp "$SOURCE_DIR/docker/.env.example" "$INSTALL_DIR/docker/"
    fi

    log_info "Copying Python memory modules..."
    cp -r "$SOURCE_DIR/src/memory/"* "$INSTALL_DIR/src/memory/" || { log_error "Failed to copy Python memory modules"; exit 1; }

    log_info "Copying scripts..."
    cp -r "$SOURCE_DIR/scripts/"* "$INSTALL_DIR/scripts/" || { log_error "Failed to copy scripts"; exit 1; }

    log_info "Copying monitoring module..."
    if [[ -d "$SOURCE_DIR/monitoring" ]]; then
        mkdir -p "$INSTALL_DIR/monitoring"
        cp -r "$SOURCE_DIR/monitoring/"* "$INSTALL_DIR/monitoring/"
    fi

    log_info "Copying Claude Code hooks..."
    cp -r "$SOURCE_DIR/.claude/hooks/"* "$INSTALL_DIR/.claude/hooks/" || { log_error "Failed to copy Claude Code hooks"; exit 1; }

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

    # BUG-107: Copy Claude Code commands (Parzival session commands)
    if [[ -d "$SOURCE_DIR/.claude/commands" ]]; then
        log_info "Copying Claude Code commands..."
        mkdir -p "$INSTALL_DIR/.claude/commands"
        cp -r "$SOURCE_DIR/.claude/commands/"* "$INSTALL_DIR/.claude/commands/" 2>/dev/null || true
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

        # BUG-069: Migrate existing JIRA_PROJECTS from comma-separated to JSON array
        # On reinstall, the Jira config block is skipped (already present), so the
        # old format persists. This in-place migration fixes it.
        if grep -q "^JIRA_PROJECTS=" "$docker_env"; then
            local existing_jp
            existing_jp=$(grep "^JIRA_PROJECTS=" "$docker_env" | cut -d= -f2-)
            # BUG-101: Strip surrounding quotes (single or double) added by installer
            existing_jp="${existing_jp#\'}" && existing_jp="${existing_jp%\'}"
            existing_jp="${existing_jp#\"}" && existing_jp="${existing_jp%\"}"
            if [[ -n "$existing_jp" && ! "$existing_jp" =~ ^\[ ]]; then
                local migrated_jp
                migrated_jp=$(format_jira_projects_json "$existing_jp")
                sed -i.bak "s|^JIRA_PROJECTS=.*|JIRA_PROJECTS='$migrated_jp'|" "$docker_env" && rm -f "$docker_env.bak"
                log_info "Migrated JIRA_PROJECTS to JSON format (BUG-069)"
            fi
        fi

        # Update AI_MEMORY_INSTALL_DIR to actual installation path
        # This handles the case where source .env has dev repo path
        if grep -q "^AI_MEMORY_INSTALL_DIR=" "$docker_env"; then
            sed -i.bak "s|^AI_MEMORY_INSTALL_DIR=.*|AI_MEMORY_INSTALL_DIR=$INSTALL_DIR|" "$docker_env" && rm -f "$docker_env.bak"
            log_info "Updated AI_MEMORY_INSTALL_DIR to $INSTALL_DIR"
        else
            echo "" >> "$docker_env"
            echo "# Installation path (added by installer)" >> "$docker_env"
            echo "AI_MEMORY_INSTALL_DIR=$INSTALL_DIR" >> "$docker_env"
        fi

        # Add Jira config if not present and Jira is enabled
        if [[ "$JIRA_SYNC_ENABLED" == "true" ]] && ! grep -q "^JIRA_SYNC_ENABLED=" "$docker_env"; then
            echo "" >> "$docker_env"
            echo "# Jira Cloud Integration (added by installer)" >> "$docker_env"
            echo "JIRA_SYNC_ENABLED=$JIRA_SYNC_ENABLED" >> "$docker_env"
            echo "JIRA_INSTANCE_URL=$JIRA_INSTANCE_URL" >> "$docker_env"
            echo "JIRA_EMAIL=$JIRA_EMAIL" >> "$docker_env"
            echo "JIRA_API_TOKEN=$JIRA_API_TOKEN" >> "$docker_env"
            echo "JIRA_PROJECTS='$(format_jira_projects_json "${JIRA_PROJECTS:-}")'" >> "$docker_env"
            echo "JIRA_SYNC_DELAY_MS=100" >> "$docker_env"
            log_info "Added Jira configuration to .env"
        fi

        # Add GitHub config if not present and GitHub is enabled
        if [[ "$GITHUB_SYNC_ENABLED" == "true" ]] && ! grep -q "^GITHUB_SYNC_ENABLED=" "$docker_env"; then
            echo "" >> "$docker_env"
            echo "# GitHub Integration (added by installer)" >> "$docker_env"
            echo "GITHUB_SYNC_ENABLED=$GITHUB_SYNC_ENABLED" >> "$docker_env"
            echo "GITHUB_TOKEN=$GITHUB_TOKEN" >> "$docker_env"
            echo "GITHUB_REPO=$GITHUB_REPO" >> "$docker_env"
            echo "GITHUB_SYNC_INTERVAL=${GITHUB_SYNC_INTERVAL:-1800}" >> "$docker_env"
            echo "GITHUB_BRANCH=${GITHUB_BRANCH:-main}" >> "$docker_env"
            echo "GITHUB_CODE_BLOB_ENABLED=${GITHUB_CODE_BLOB_ENABLED:-true}" >> "$docker_env"
            echo "GITHUB_CODE_BLOB_MAX_SIZE=${GITHUB_CODE_BLOB_MAX_SIZE:-102400}" >> "$docker_env"
            echo "GITHUB_CODE_BLOB_EXCLUDE=${GITHUB_CODE_BLOB_EXCLUDE:-node_modules,*.min.js,.git,__pycache__,*.pyc,build,dist,*.egg-info}" >> "$docker_env"
            echo "GITHUB_SYNC_ON_START=${GITHUB_SYNC_ON_START:-true}" >> "$docker_env"
            log_info "Added GitHub configuration to .env"
        fi

        # BUG-092: Ensure AI_MEMORY_PROJECT_ID is set
        if ! grep -q "^AI_MEMORY_PROJECT_ID=" "$docker_env" 2>/dev/null; then
            echo "" >> "$docker_env"
            echo "# Project Identification (used by github-sync for multi-tenancy)" >> "$docker_env"
            echo "AI_MEMORY_PROJECT_ID=$PROJECT_NAME" >> "$docker_env"
            log_info "Added AI_MEMORY_PROJECT_ID=$PROJECT_NAME to .env"
        fi

        log_success "Environment configured at $docker_env"
    else
        # No source .env - create minimal template (user needs to add credentials)
        log_warning "No source .env found - creating template without credentials"
        local jira_projects_json
        jira_projects_json=$(format_jira_projects_json "${JIRA_PROJECTS:-}")
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
QUEUE_DIR=$INSTALL_DIR/queue

# Platform Information
PLATFORM=$PLATFORM
ARCH=$ARCH

# Search Configuration
SIMILARITY_THRESHOLD=0.4

# Project Identification (used by github-sync for multi-tenancy)
AI_MEMORY_PROJECT_ID=$PROJECT_NAME

# =============================================================================
# CREDENTIALS (Required - add your values below)
# =============================================================================
# Generate API key: python3 -c "import secrets; print(secrets.token_urlsafe(18))"
QDRANT_API_KEY=${QDRANT_API_KEY:-}
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=
PROMETHEUS_ADMIN_PASSWORD=

# =============================================================================
# JIRA CLOUD INTEGRATION (Optional - PLAN-004 Phase 2)
# =============================================================================
JIRA_SYNC_ENABLED=${JIRA_SYNC_ENABLED:-false}
JIRA_INSTANCE_URL=${JIRA_INSTANCE_URL:-}
JIRA_EMAIL=${JIRA_EMAIL:-}
JIRA_API_TOKEN=${JIRA_API_TOKEN:-}
JIRA_PROJECTS='$jira_projects_json'
JIRA_SYNC_DELAY_MS=100

# =============================================================================
# GITHUB INTEGRATION (Optional — PLAN-006 Phase 1a)
# =============================================================================
GITHUB_SYNC_ENABLED=${GITHUB_SYNC_ENABLED:-false}
GITHUB_TOKEN=${GITHUB_TOKEN:-}
GITHUB_REPO=${GITHUB_REPO:-}
GITHUB_SYNC_INTERVAL=${GITHUB_SYNC_INTERVAL:-1800}
GITHUB_BRANCH=${GITHUB_BRANCH:-main}
GITHUB_CODE_BLOB_ENABLED=${GITHUB_CODE_BLOB_ENABLED:-true}
GITHUB_CODE_BLOB_MAX_SIZE=${GITHUB_CODE_BLOB_MAX_SIZE:-102400}
GITHUB_CODE_BLOB_EXCLUDE=${GITHUB_CODE_BLOB_EXCLUDE:-node_modules,*.min.js,.git,__pycache__,*.pyc,build,dist,*.egg-info}
GITHUB_SYNC_ON_START=${GITHUB_SYNC_ON_START:-true}
EOF
        # If QDRANT_API_KEY was provided via environment, note it in the log
        if [[ -n "${QDRANT_API_KEY:-}" ]]; then
            log_info "Using QDRANT_API_KEY from environment"
        else
            log_warning "Please configure credentials in $docker_env"
        fi
        log_success "Environment template created at $docker_env"
    fi

    # BUG-087: Auto-generate missing credentials so fresh installs work out-of-the-box
    # Uses Python secrets module for cryptographically secure random values
    local _gen_secret="import secrets; print(secrets.token_urlsafe(18))"

    if ! grep -q "^QDRANT_API_KEY=.\+" "$docker_env" 2>/dev/null; then
        local gen_key
        gen_key=$("$INSTALL_DIR/.venv/bin/python" -c "$_gen_secret")
        if [[ -n "$gen_key" ]]; then
            if grep -q "^QDRANT_API_KEY=" "$docker_env" 2>/dev/null; then
                sed -i.bak "s|^QDRANT_API_KEY=.*|QDRANT_API_KEY=$gen_key|" "$docker_env" && rm -f "$docker_env.bak"
            else
                echo "QDRANT_API_KEY=$gen_key" >> "$docker_env"
            fi
            log_success "Auto-generated QDRANT_API_KEY"
        fi
    fi

    if ! grep -q "^GRAFANA_ADMIN_PASSWORD=.\+" "$docker_env" 2>/dev/null; then
        local gen_gf
        gen_gf=$("$INSTALL_DIR/.venv/bin/python" -c "$_gen_secret")
        if [[ -n "$gen_gf" ]]; then
            if grep -q "^GRAFANA_ADMIN_PASSWORD=" "$docker_env" 2>/dev/null; then
                sed -i.bak "s|^GRAFANA_ADMIN_PASSWORD=.*|GRAFANA_ADMIN_PASSWORD=$gen_gf|" "$docker_env" && rm -f "$docker_env.bak"
            else
                echo "GRAFANA_ADMIN_PASSWORD=$gen_gf" >> "$docker_env"
            fi
            log_success "Auto-generated GRAFANA_ADMIN_PASSWORD"
        fi
    fi

    if ! grep -q "^PROMETHEUS_ADMIN_PASSWORD=.\+" "$docker_env" 2>/dev/null; then
        local gen_prom
        gen_prom=$("$INSTALL_DIR/.venv/bin/python" -c "$_gen_secret")
        if [[ -n "$gen_prom" ]]; then
            if grep -q "^PROMETHEUS_ADMIN_PASSWORD=" "$docker_env" 2>/dev/null; then
                sed -i.bak "s|^PROMETHEUS_ADMIN_PASSWORD=.*|PROMETHEUS_ADMIN_PASSWORD=$gen_prom|" "$docker_env" && rm -f "$docker_env.bak"
            else
                echo "PROMETHEUS_ADMIN_PASSWORD=$gen_prom" >> "$docker_env"
            fi
            log_success "Auto-generated PROMETHEUS_ADMIN_PASSWORD"
        fi
    fi

    if ! grep -q "^GRAFANA_SECRET_KEY=.\+" "$docker_env" 2>/dev/null; then
        local gen_gsk
        gen_gsk=$("$INSTALL_DIR/.venv/bin/python" -c "import secrets; print(secrets.token_hex(32))")
        if [[ -n "$gen_gsk" ]]; then
            if grep -q "^GRAFANA_SECRET_KEY=" "$docker_env" 2>/dev/null; then
                sed -i.bak "s|^GRAFANA_SECRET_KEY=.*|GRAFANA_SECRET_KEY=$gen_gsk|" "$docker_env" && rm -f "$docker_env.bak"
            else
                echo "GRAFANA_SECRET_KEY=$gen_gsk" >> "$docker_env"
            fi
            log_success "Auto-generated GRAFANA_SECRET_KEY"
        fi
    fi

    # Generate Prometheus web.yml with bcrypt hash from password
    generate_prometheus_auth
}

# Post-dependency validation for external services (BP-053: Two-Phase Validation)
# Runs after copy_files + install_python_dependencies + configure_environment
validate_external_services() {
    if [[ "$JIRA_SYNC_ENABLED" != "true" ]]; then
        return 0
    fi

    log_info "Validating Jira integration (full Python test)..."

    # Run from docker/ dir so get_config() finds .env via pydantic env_file=".env"
    local validation_result=""
    local validation_exit=0
    validation_result=$(cd "$INSTALL_DIR/docker" && "$INSTALL_DIR/.venv/bin/python" -c "
import asyncio
import sys
sys.path.insert(0, '$INSTALL_DIR/src')

async def validate():
    try:
        from memory.connectors.jira.client import JiraClient
        from memory.config import get_config
        config = get_config()
        if not config.jira_sync_enabled:
            print('SKIP: Jira sync not enabled in config')
            return 0
        client = JiraClient(
            str(config.jira_instance_url),
            config.jira_email,
            config.jira_api_token.get_secret_value(),
        )
        try:
            result = await client.test_connection()
            if result['success']:
                print(f\"✓ Connected as {result['user_email']}\")
                return 0
            else:
                print(f\"✗ FAIL: {result.get('error', 'Unknown error')}\")
                return 1
        finally:
            await client.close()
    except Exception as e:
        print(f\"✗ FAIL: {e}\")
        return 1

sys.exit(asyncio.run(validate()))
" 2>&1) || validation_exit=$?

    if [[ $validation_exit -eq 0 ]]; then
        log_success "Jira validation passed: $validation_result"
    else
        log_warning "Jira validation failed: $validation_result"
        log_warning "Disabling Jira sync — check JIRA_PROJECTS format and credentials in $INSTALL_DIR/docker/.env and re-run installer"
        JIRA_SYNC_ENABLED="false"
    fi
}

# Generate Prometheus basic auth configuration from PROMETHEUS_ADMIN_PASSWORD
generate_prometheus_auth() {
    local docker_env="$INSTALL_DIR/docker/.env"
    local web_yml="$INSTALL_DIR/docker/prometheus/web.yml"

    # Read password from .env
    local prometheus_password
    prometheus_password=$(grep "^PROMETHEUS_ADMIN_PASSWORD=" "$docker_env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || echo "")

    if [[ -z "$prometheus_password" ]]; then
        log_warning "PROMETHEUS_ADMIN_PASSWORD not set - Prometheus auth may not work"
        return 0
    fi

    # Generate bcrypt hash using Python
    local bcrypt_hash bcrypt_stderr=""
    bcrypt_hash=$(PROM_PASS="$prometheus_password" "$INSTALL_DIR/.venv/bin/python" -c "
import bcrypt, os
password = os.environ['PROM_PASS'].encode('utf-8')
hash_val = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))
print(hash_val.decode('utf-8'))
" 2>/tmp/bcrypt_err.log) || true
    bcrypt_stderr=$(cat /tmp/bcrypt_err.log 2>/dev/null || echo "")
    rm -f /tmp/bcrypt_err.log

    if [[ -n "$bcrypt_stderr" && -z "$bcrypt_hash" ]]; then
        log_warning "bcrypt generation failed: $bcrypt_stderr"
        log_warning "Ensure bcrypt is installed: $INSTALL_DIR/.venv/bin/pip install bcrypt"
    fi

    if [[ -z "$bcrypt_hash" ]]; then
        log_warning "Failed to generate bcrypt hash - check Python/bcrypt installation"
        return 0
    fi

    # Write web.yml with generated hash
    # Note: printf %s prevents $ expansion issues in bcrypt hash ($2b$12$...)
    {
        echo "# Prometheus Web Configuration - Basic Authentication"
        echo "# Auto-generated by install.sh from PROMETHEUS_ADMIN_PASSWORD"
        echo "# DO NOT manually edit - regenerate by re-running installer"
        echo ""
        echo "basic_auth_users:"
        printf "  admin: %s\n" "$bcrypt_hash"
    } > "$web_yml"

    log_success "Generated Prometheus auth config (bcrypt hash from password)"

    # BUG-089: Generate Base64 auth header for Prometheus healthcheck
    local auth_header
    auth_header="Basic $(echo -n "admin:$prometheus_password" | base64)"
    # Append or update in .env
    if grep -q "^PROMETHEUS_BASIC_AUTH_HEADER=" "$docker_env" 2>/dev/null; then
        sed -i.bak "s|^PROMETHEUS_BASIC_AUTH_HEADER=.*|PROMETHEUS_BASIC_AUTH_HEADER='$auth_header'|" "$docker_env" && rm -f "$docker_env.bak"
    else
        echo "" >> "$docker_env"
        echo "# Prometheus healthcheck auth (auto-generated by install.sh)" >> "$docker_env"
        echo "PROMETHEUS_BASIC_AUTH_HEADER='$auth_header'" >> "$docker_env"
    fi
    log_info "Generated Prometheus healthcheck auth header"
}

# Log Docker container state for debugging (P1: container disappearance diagnosis)
_log_docker_state() {
    local label="${1:-}"
    log_info "Docker state snapshot [$label]:"
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1 | while IFS= read -r line; do
        log_info "  $line"
    done
}

# Service startup with 2026 security best practices (AC 7.1.7)
# Uses PHASED startup: core services first (qdrant, embedding), then profile
# services. This prevents --build of profile services from interfering with
# core service startup (P1: Qdrant/Embedding container disappearance).
start_services() {
    log_info "Starting Docker services..."

    # Navigate to docker directory
    cd "$INSTALL_DIR/docker" || {
        log_error "Failed to navigate to $INSTALL_DIR/docker"
        exit 1
    }

    # Check Docker daemon is reachable (BUG-094: works with Docker Engine, Desktop, Colima, etc.)
    if ! docker info &>/dev/null; then
        log_warning "Docker daemon is not reachable — attempting systemd start..."
        sudo systemctl start docker 2>/dev/null || true
        sleep 3
        if ! docker info &>/dev/null; then
            log_error "Docker daemon is not reachable."
            log_error "  Docker Engine:  sudo systemctl start docker"
            log_error "  Docker Desktop: Start from applications menu"
            log_error "  Verify:         docker info"
            exit 1
        fi
        log_success "Docker daemon started"
    fi

    # BUG-095: Check Docker has enough memory for all services
    local docker_mem_bytes
    docker_mem_bytes=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo "0")
    local docker_mem_gb=$((docker_mem_bytes / 1073741824))
    log_info "Docker memory available: ${docker_mem_gb}GB ($((docker_mem_bytes / 1048576))MB)"
    if [[ $docker_mem_gb -lt 3 ]]; then
        log_warning "Docker has only ${docker_mem_gb}GB RAM (minimum 3GB, recommended 4GB+)"
        log_warning "  Docker Desktop: Settings → Resources → Memory → set to 4GB+"
        log_warning "  Low memory causes containers to disappear silently (OOM inside VM)"
        echo ""
        read -p "  Continue anyway? [y/N]: " low_mem_choice
        if [[ ! "$low_mem_choice" =~ ^[Yy]$ ]]; then
            log_info "Increase Docker memory and re-run the installer."
            exit 0
        fi
    fi

    # Build profile flags for later use
    local profile_flags=""
    if [[ "$INSTALL_MONITORING" == "true" ]]; then
        profile_flags="$profile_flags --profile monitoring"
    fi
    if [[ "$GITHUB_SYNC_ENABLED" == "true" ]]; then
        profile_flags="$profile_flags --profile github"
        mkdir -p "${AI_MEMORY_INSTALL_DIR:-${HOME}/.ai-memory}/github-state"
    fi

    # ── Phase 1: Pull ALL images first ──
    log_info "Pulling Docker images (this may take a few minutes)..."
    docker compose $profile_flags pull

    # ── Phase 2: Start CORE services first (no --build, no profiles) ──
    # Qdrant uses a pre-built image (no build context). Embedding has a build
    # context but we build it separately to avoid memory pressure from building
    # multiple images simultaneously on low-RAM systems.
    log_info "Phase 1/2: Starting core services (qdrant + embedding)..."
    docker compose up -d qdrant
    docker compose up -d --build embedding

    _log_docker_state "after core startup"

    # Wait for core services to be healthy before starting profile services
    log_info "Waiting for core services to become healthy..."
    local core_timeout=120
    local core_attempt=0
    echo -n "  Qdrant: "
    while [[ $core_attempt -lt $core_timeout ]]; do
        if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:${QDRANT_PORT:-26350}/" &> /dev/null; then
            echo -e "${GREEN}ready${NC}"
            break
        fi
        echo -n "."
        sleep 1
        core_attempt=$((core_attempt + 1))
    done
    if [[ $core_attempt -ge $core_timeout ]]; then
        log_error "Qdrant failed to become healthy within ${core_timeout}s"
        _log_docker_state "qdrant timeout"
        docker compose logs qdrant 2>&1 | tail -20 | while IFS= read -r line; do log_error "  $line"; done
        exit 1
    fi

    # Verify Qdrant is still running (P1 diagnosis)
    local qdrant_status
    qdrant_status=$(docker ps --filter "name=${CONTAINER_PREFIX}-qdrant" --format "{{.Status}}" 2>/dev/null)
    if [[ -z "$qdrant_status" ]]; then
        log_error "Qdrant container disappeared immediately after healthcheck!"
        _log_docker_state "qdrant disappeared"
        exit 1
    fi
    log_info "Qdrant verified running: $qdrant_status"

    # ── Phase 3: Start profile services ──
    if [[ -n "$profile_flags" ]]; then
        log_info "Phase 2/2: Starting profile services ($profile_flags)..."
        # BUG-079: --build forces rebuild of source-built containers
        docker compose $profile_flags up -d --build
        _log_docker_state "after profile startup"

        # Verify core services survived profile startup
        qdrant_status=$(docker ps --filter "name=${CONTAINER_PREFIX}-qdrant" --format "{{.Status}}" 2>/dev/null)
        local embedding_status
        embedding_status=$(docker ps --filter "name=${CONTAINER_PREFIX}-embedding" --format "{{.Status}}" 2>/dev/null)
        if [[ -z "$qdrant_status" ]]; then
            log_error "CRITICAL: Qdrant container disappeared after profile services started!"
            log_error "This indicates Docker Compose V2 service reconciliation issue."
            _log_docker_state "qdrant gone after profiles"
            exit 1
        fi
        if [[ -z "$embedding_status" ]]; then
            log_error "CRITICAL: Embedding container disappeared after profile services started!"
            _log_docker_state "embedding gone after profiles"
            exit 1
        fi
        log_info "Core services survived profile startup: qdrant=$qdrant_status, embedding=$embedding_status"
    else
        log_info "No profile services to start"
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
        attempt=$((attempt + 1))
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
        attempt=$((attempt + 1))
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
            attempt=$((attempt + 1))
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
            attempt=$((attempt + 1))
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
    if "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/setup-collections.py" 2>&1; then
        log_success "Qdrant collections created (code-patterns, conventions, discussions)"
    else
        log_error "Collection setup FAILED - re-run: $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/setup-collections.py"
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
            echo "     skills/              (Best practices researcher, etc.)"
            echo "     agents/              (Skill creator agent)"
            echo ""
            echo "NOTE: On WSL, we copy files instead of creating symlinks."
            echo "      This ensures hooks are visible from Windows applications."
            echo "      If you update the shared installation, re-run this installer"
            echo "      to update the project files."
        else
            echo "     hooks/scripts/       (Symlinks to shared hooks)"
            echo "     skills/              (Best practices researcher, etc.)"
            echo "     agents/              (Skill creator agent)"
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

    # BUG-106: Remove stale/broken symlinks before creating fresh ones
    # Prior installs may leave symlinks pointing to deleted targets (e.g. archived hooks)
    for existing in "$PROJECT_PATH/.claude/hooks/scripts"/*.py; do
        if [[ -L "$existing" && ! -e "$existing" ]]; then
            rm -f "$existing"  # broken symlink
        elif [[ -f "$existing" && ! -L "$existing" ]]; then
            local bn=$(basename "$existing")
            if [[ ! -f "$INSTALL_DIR/.claude/hooks/scripts/$bn" ]]; then
                rm -f "$existing"  # stale regular file from prior copy-mode install
            fi
        fi
    done

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
            file_count=$((file_count + 1))
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
                    archived_count=$((archived_count + 1))
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

    # Copy skills to project (core ai-memory functionality)
    if [[ -d "$INSTALL_DIR/.claude/skills" ]]; then
        local skills_count=0
        for skill_dir in "$INSTALL_DIR/.claude/skills"/*/; do
            if [[ -d "$skill_dir" ]]; then
                skill_name=$(basename "$skill_dir")
                target_skill="$PROJECT_PATH/.claude/skills/$skill_name"
                mkdir -p "$target_skill"

                if [[ "$link_method" == "copy" ]]; then
                    cp -r "$skill_dir"* "$target_skill/" 2>/dev/null || true
                else
                    # Symlink entire skill directory
                    rm -rf "$target_skill"
                    ln -sf "${skill_dir%/}" "$PROJECT_PATH/.claude/skills/$skill_name"
                fi
                skills_count=$((skills_count + 1))
            fi
        done
        if [[ $skills_count -gt 0 ]]; then
            log_success "Installed $skills_count skill(s) to $PROJECT_PATH/.claude/skills/"
        fi
    fi

    # Copy agents to project (core ai-memory functionality)
    if [[ -d "$INSTALL_DIR/.claude/agents" ]]; then
        mkdir -p "$PROJECT_PATH/.claude/agents"
        local agents_count=0
        for agent_file in "$INSTALL_DIR/.claude/agents"/*.md; do
            if [[ -f "$agent_file" ]]; then
                agent_name=$(basename "$agent_file")
                target_agent="$PROJECT_PATH/.claude/agents/$agent_name"

                if [[ "$link_method" == "copy" ]]; then
                    cp "$agent_file" "$target_agent"
                else
                    ln -sf "$agent_file" "$target_agent"
                fi
                agents_count=$((agents_count + 1))
            fi
        done
        if [[ $agents_count -gt 0 ]]; then
            log_success "Installed $agents_count agent(s) to $PROJECT_PATH/.claude/agents/"
        fi
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

    # BUG-096: Must use venv Python (has httpx), not system python3 (doesn't)
    if "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/health-check.py"; then
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
        echo "│     $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/health-check.py │"
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
            log_info "  $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/memory/seed_best_practices.py"
            return 0
        fi

        # Run seeding script
        if "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/memory/seed_best_practices.py" --templates-dir "$INSTALL_DIR/templates/conventions"; then
            log_success "Best practices seeded successfully"
        else
            log_warning "Failed to seed best practices (non-critical)"
            log_info "You can seed manually later with:"
            log_info "  $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/memory/seed_best_practices.py --templates-dir $INSTALL_DIR/templates/conventions"
        fi
    fi
    # No tip shown if user explicitly declined during interactive prompt
}

# Run initial Jira sync (PLAN-004 Phase 2)
run_initial_jira_sync() {
    if [[ "$JIRA_SYNC_ENABLED" == "true" && "$JIRA_INITIAL_SYNC" == "true" ]]; then
        log_info "Running initial Jira sync (may take 5-10 minutes for large projects)..."

        # Ensure logs directory exists
        mkdir -p "$INSTALL_DIR/logs"

        # Run from docker/ dir so get_config() finds .env (pydantic env_file=".env")
        # Use direct venv Python path — no source activate (BP-053)
        # Subshell (parentheses) prevents cd from changing installer's CWD
        if (cd "$INSTALL_DIR/docker" && "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/jira_sync.py" --full) 2>&1 | tee "$INSTALL_DIR/logs/jira_initial_sync.log"; then
            log_success "Initial Jira sync completed"
        else
            log_warning "Initial sync had errors - check $INSTALL_DIR/logs/jira_initial_sync.log"
            log_info "Re-run manually: cd $INSTALL_DIR/docker && $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/jira_sync.py --full"
        fi
    fi
}

# Set up cron job for automated Jira sync (PLAN-004 Phase 2)
setup_jira_cron() {
    if [[ "$JIRA_SYNC_ENABLED" == "true" ]]; then
        log_info "Configuring automated Jira sync (6am/6pm daily)..."

        # Ensure locks directory exists for flock
        mkdir -p "$INSTALL_DIR/.locks"

        # Build cron command (BP-053: direct interpreter + flock + tagged entry)
        # cd to docker/ so get_config() finds .env (pydantic env_file=".env")
        local cron_tag="# ai-memory-jira-sync"
        local cron_cmd
        if [[ "$PLATFORM" == "macos" ]]; then
            # macOS: no flock available by default
            cron_cmd="cd $INSTALL_DIR/docker && $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/jira_sync.py --incremental"
        else
            # Linux/WSL: use flock for overlap prevention
            cron_cmd="cd $INSTALL_DIR/docker && flock -n $INSTALL_DIR/.locks/jira_sync.lock $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/jira_sync.py --incremental"
        fi
        local cron_entry="0 6,18 * * * $cron_cmd >> $INSTALL_DIR/logs/jira_sync.log 2>&1 $cron_tag"

        # Idempotent: remove any existing ai-memory-jira-sync entry, then add fresh
        local existing_crontab
        existing_crontab=$(crontab -l 2>/dev/null || true)

        # Filter out old entries (by tag OR by legacy jira_sync.py match)
        local filtered_crontab
        filtered_crontab=$(echo "$existing_crontab" | grep -v "ai-memory-jira-sync" | grep -v "jira_sync.py" || true)

        # Add new entry
        if printf '%s\n%s\n' "$filtered_crontab" "$cron_entry" | crontab - 2>/dev/null; then
            log_success "Cron job configured (6am/6pm daily incremental sync)"
            log_info "To view: crontab -l | grep ai-memory-jira-sync"
        else
            log_warning "Failed to configure cron job - set up manually if needed"
            log_info "Add to crontab: $cron_entry"
        fi
    fi
}

# Set up GitHub payload indexes (PLAN-006 Phase 1a)
setup_github_indexes() {
    if [[ "$GITHUB_SYNC_ENABLED" != "true" ]]; then
        return
    fi

    log_info "Creating GitHub payload indexes on discussions collection..."

    local result
    # BUG-098: Source .env so pydantic MemoryConfig reads env vars even when
    # env_file=".env" doesn't resolve (CWD is docker/ but pydantic may not find it)
    result=$(cd "$INSTALL_DIR/docker" && [[ -f .env ]] || { echo "FAILED: docker/.env not found"; exit 1; } && set -a && source .env && set +a && "$INSTALL_DIR/.venv/bin/python" -c "
import sys
sys.path.insert(0, '$INSTALL_DIR/src')
from memory.qdrant_client import get_qdrant_client
from memory.connectors.github.schema import create_github_indexes
client = get_qdrant_client()
counts = create_github_indexes(client)
created = counts.get('created', 0)
existing = counts.get('existing', 0)
print(f'OK: {created} created, {existing} already existed')
" 2>&1) || result="FAILED"

    if [[ "$result" == FAILED* ]]; then
        log_warning "GitHub index creation failed: $result"
        log_info "Indexes will be created automatically on first sync"
    else
        log_success "GitHub indexes: $result"
    fi
}

# Run initial GitHub sync (PLAN-006 Phase 1a)
run_initial_github_sync() {
    if [[ "$GITHUB_SYNC_ENABLED" == "true" && "$GITHUB_INITIAL_SYNC" == "true" ]]; then
        log_info "Running initial GitHub sync (may take 5-30 minutes)..."
        log_info "Repo: $GITHUB_REPO"

        # CWD must be $INSTALL_DIR (not docker/) so engine's Path.cwd()/.audit/state/
        # writes to the correct location that the container volume also maps to
        # BUG-098: Source docker/.env so pydantic MemoryConfig reads GITHUB_SYNC_ENABLED
        # and other env vars — .env is at docker/.env but CWD is $INSTALL_DIR
        if (cd "$INSTALL_DIR" && [[ -f docker/.env ]] || { echo "[ERROR] docker/.env not found"; exit 1; } && set -a && source docker/.env && set +a && ".venv/bin/python" "scripts/github_sync.py" --full) 2>&1 | tee "$INSTALL_DIR/logs/github_initial_sync.log"; then
            log_success "Initial GitHub sync completed"
        else
            log_warning "Initial sync had errors — check $INSTALL_DIR/logs/github_initial_sync.log"
            log_info "Re-run manually: cd $INSTALL_DIR && set -a && source docker/.env && set +a && .venv/bin/python scripts/github_sync.py --full"
        fi
    fi
}

# === .audit/ Directory Setup (v2.0.6 — AD-2 two-tier audit trail) ===
# Creates project-local .audit/ directory for ephemeral/sensitive audit data.
# This is Tier 1 of the two-tier hybrid audit trail (AD-2):
#   Tier 1: .audit/ (gitignored) — ephemeral logs, sync state, session transcripts
#   Tier 2: oversight/ (committed) — decisions, plans, session handoffs, specs
# See: SPEC-003-audit-directory.md
setup_audit_directory() {
    log_info "Setting up .audit/ directory structure..."

    # Track whether .audit/ already exists (for idempotent migration logging)
    local audit_existed=false
    [[ -d "$PROJECT_PATH/.audit" ]] && audit_existed=true

    # Create directory structure (idempotent via mkdir -p)
    mkdir -p "$PROJECT_PATH/.audit"/{logs,sessions,state,snapshots,temp}

    # Set restricted permissions on .audit/ root (owner-only access)
    # Note: On WSL with NTFS-mounted drives, chmod is silently ignored by the
    # filesystem. Permissions are effective in native Linux and Docker contexts.
    chmod 700 "$PROJECT_PATH/.audit" 2>/dev/null || log_warning "Could not set .audit/ permissions to 700 (filesystem limitation)"
    log_info "Private audit directory: $PROJECT_PATH/.audit (chmod 700)"

    # Add .audit/ to project .gitignore (idempotent — check before adding)
    if [[ -f "$PROJECT_PATH/.gitignore" ]]; then
        if ! grep -q "^\.audit/" "$PROJECT_PATH/.gitignore" 2>/dev/null; then
            echo "" >> "$PROJECT_PATH/.gitignore"
            echo "# AI Memory audit trail (ephemeral/sensitive data)" >> "$PROJECT_PATH/.gitignore"
            echo ".audit/" >> "$PROJECT_PATH/.gitignore"
            log_info "Added .audit/ to .gitignore"
        fi
    else
        # Create .gitignore if it doesn't exist
        echo "# AI Memory audit trail (ephemeral/sensitive data)" > "$PROJECT_PATH/.gitignore"
        echo ".audit/" >> "$PROJECT_PATH/.gitignore"
        log_info "Created .gitignore with .audit/ entry"
    fi

    # Generate README (overwritten on re-install to pick up latest content)
    cat > "$PROJECT_PATH/.audit/README.md" << 'AUDIT_README'
# .audit/ — AI Memory Audit Trail

This directory contains ephemeral and sensitive audit data for the AI Memory system.
It is gitignored and should NOT be committed.

## Directory Structure

- `logs/` — JSONL event logs (injection, sync, updates, sanitization)
- `sessions/` — Raw session transcripts
- `state/` — Sync cursors, pending reviews, migration state
- `snapshots/` — Qdrant collection backup references
- `temp/` — Debug/verbose data (auto-cleaned)

## Retention

- Logs: 30 days rolling
- Sessions: Permanent
- State: Latest only
- Snapshots: Last 4 weekly
- Temp: Auto-cleaned after 24 hours

## Related

- Committed audit trail: `oversight/` directory
- Configuration: `AUDIT_DIR` environment variable (default: .audit)
- Architecture: AD-2 in PLAN-006 Architectural Decisions

Generated by ai-memory install script.
AUDIT_README
    log_info "Created .audit/README.md"

    # Upgrade path: detect v2.0.5 → v2.0.6 migration
    # v2.0.5 has ~/.ai-memory/ but no .audit/ directory. If we just created it
    # for an existing installation, log the migration event.
    if [[ "$audit_existed" == "false" && -d "$INSTALL_DIR" && -f "$INSTALL_DIR/docker/docker-compose.yml" && "$INSTALL_MODE" == "add-project" ]]; then
        # Existing installation detected — this is an upgrade scenario
        local migration_log="$PROJECT_PATH/.audit/state/migration-log.jsonl"
        local timestamp
        timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        local safe_project_name="${PROJECT_NAME//\\/\\\\}"
        safe_project_name="${safe_project_name//\"/\\\"}"
        echo "{\"event\": \"audit_dir_created\", \"version\": \"2.0.6\", \"timestamp\": \"$timestamp\", \"project\": \"$safe_project_name\"}" >> "$migration_log"
        log_info "Logged migration event to .audit/state/migration-log.jsonl"
    fi

    log_success ".audit/ directory structure ready"
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
    if [[ "$JIRA_SYNC_ENABLED" == "true" ]]; then
    echo "│     ✓ Jira Cloud sync (${JIRA_PROJECTS})                     │"
    fi
    if [[ "$GITHUB_SYNC_ENABLED" == "true" ]]; then
    echo "│     ✓ GitHub sync (${GITHUB_REPO})                     │"
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
    echo "│     $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/health-check.py │"
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
    log_error "Docker daemon is not reachable"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  Docker needs to be running to install AI Memory Module    │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│  Start Docker:                                              │"
    echo "│    Docker Engine:  sudo systemctl start docker              │"
    echo "│    Docker Desktop: Start from applications menu             │"
    echo "│    macOS:          Open Docker Desktop                      │"
    echo "│    WSL2:           Start Docker Desktop on Windows          │"
    echo "│                                                             │"
    echo "│  Verify: docker info                                        │"
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

# =================================================================
# Parzival Session Agent (optional, SPEC-015)
# =================================================================
setup_parzival() {
    # Skip in non-interactive mode (CI)
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        log_info "Non-interactive mode - skipping Parzival setup"
        append_env_if_missing "PARZIVAL_ENABLED" "false"
        return 0
    fi

    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "  Parzival Session Agent (Optional)"
    echo "═══════════════════════════════════════════════════════"
    echo ""
    echo "Parzival is a Technical PM & Quality Gatekeeper that provides:"
    echo "  - Cross-session memory (remembers previous sessions)"
    echo "  - Project oversight (tracks bugs, specs, decisions)"
    echo "  - Quality gatekeeping (verification checklists)"
    echo ""
    read -p "Enable Parzival session agent? [y/N] " parzival_choice

    if [[ "${parzival_choice,,}" =~ ^(y|yes)$ ]]; then
        log_info "Setting up Parzival..."

        # Deploy commands to project
        deploy_parzival_commands

        # Deploy oversight templates
        deploy_oversight_templates

        # Add Parzival config to .env
        configure_parzival_env

        # Create agent_id payload index
        create_agent_id_index

        log_success "Parzival enabled"
    else
        log_info "Skipping Parzival setup (PARZIVAL_ENABLED=false)"
        # Ensure disabled in .env
        append_env_if_missing "PARZIVAL_ENABLED" "false"
    fi
}

deploy_parzival_commands() {
    local cmd_source="$INSTALL_DIR/.claude/commands/parzival"
    local cmd_dest="$PROJECT_PATH/.claude/commands/parzival"

    mkdir -p "$cmd_dest"

    if [[ -d "$cmd_source" ]]; then
        # Backup existing commands before overwrite
        for src_file in "$cmd_source"/*.md; do
            local bn=$(basename "$src_file")
            local dest_file="$cmd_dest/$bn"
            if [[ -f "$dest_file" ]]; then
                cp "$dest_file" "$dest_file.bak.$(date +%Y%m%d%H%M%S)"
            fi
        done
        cp -r "$cmd_source/"* "$cmd_dest/" 2>/dev/null || true
        log_info "Parzival commands deployed to $cmd_dest"
    else
        log_warning "Parzival command source not found at $cmd_source"
    fi

    # TODO(v2.0.7): De-duplicate agent deployment — create_project_symlinks() already covers
    # agents in $PROJECT_PATH/.claude/agents/. This section deploys the same files.
    # After v2.0.6, consolidate into a single deployment path.

    # Deploy subagent files so exec= directives in parzival.md resolve correctly
    local agent_dest="$PROJECT_PATH/.claude/agents"
    mkdir -p "$agent_dest"

    for agent_file in code-reviewer.md verify-implementation.md; do
        if [[ -f "$INSTALL_DIR/.claude/agents/$agent_file" ]]; then
            cp "$INSTALL_DIR/.claude/agents/$agent_file" "$agent_dest/$agent_file"
        fi
    done

    if [[ -d "$INSTALL_DIR/.claude/agents/parzival" ]]; then
        cp -r "$INSTALL_DIR/.claude/agents/parzival" "$agent_dest/"
    fi

    log_info "Parzival agent files deployed to $agent_dest"
}

deploy_oversight_templates() {
    local tmpl_source="$INSTALL_DIR/templates/oversight"
    local oversight_dest="$PROJECT_PATH/oversight"

    if [[ ! -d "$tmpl_source" ]]; then
        log_warning "Oversight templates not found at $tmpl_source"
        return
    fi

    # Create oversight directory structure (skip existing files)
    mkdir -p "$oversight_dest"

    # Copy templates, preserving directory structure, skip existing
    while read -r tmpl_file; do
        local rel_path="${tmpl_file#$tmpl_source/}"
        local dest_file="$oversight_dest/$rel_path"
        local dest_dir="$(dirname "$dest_file")"

        mkdir -p "$dest_dir"

        if [[ ! -f "$dest_file" ]]; then
            cp "$tmpl_file" "$dest_file"
        fi
    done < <(find "$tmpl_source" -type f)

    log_info "Oversight templates deployed to $oversight_dest (existing files preserved)"
}

configure_parzival_env() {
    local env_file="$INSTALL_DIR/docker/.env"

    append_env_if_missing "PARZIVAL_ENABLED" "true"
    append_env_if_missing "PARZIVAL_USER_NAME" "Developer"
    append_env_if_missing "PARZIVAL_LANGUAGE" "English"
    append_env_if_missing "PARZIVAL_DOC_LANGUAGE" "English"
    append_env_if_missing "PARZIVAL_OVERSIGHT_FOLDER" "oversight"
    append_env_if_missing "PARZIVAL_HANDOFF_RETENTION" "10"

    # Prompt for user name (skip in non-interactive mode)
    if [[ "$NON_INTERACTIVE" != "true" ]]; then
        read -p "Your name for Parzival greetings [Developer]: " user_name
        if [[ -n "$user_name" ]]; then
            escaped_name=$(printf '%s\n' "$user_name" | sed 's/[&/\$`"!]/\\&/g')
            sed -i.bak "s/^PARZIVAL_USER_NAME=.*/PARZIVAL_USER_NAME=$escaped_name/" "$env_file" && rm -f "$env_file.bak"
        fi
    fi
}

# Helper: append key=value to .env if key not already present
append_env_if_missing() {
    local key="$1"
    local value="$2"
    local env_file="$INSTALL_DIR/docker/.env"
    if ! grep -q "^${key}=" "$env_file" 2>/dev/null; then
        echo "${key}=${value}" >> "$env_file"
    fi
}

create_agent_id_index() {
    local qdrant_url="http://localhost:${QDRANT_PORT:-26350}"
    local api_key=""
    if [[ -f "$INSTALL_DIR/docker/.env" ]]; then
        api_key=$(grep "^QDRANT_API_KEY=" "$INSTALL_DIR/docker/.env" 2>/dev/null | cut -d= -f2-) || true
    fi

    log_info "Creating agent_id payload index on discussions collection..."

    curl -s -X PUT \
        -H "Api-Key: $api_key" \
        -H "Content-Type: application/json" \
        -d '{"field_name": "agent_id", "field_schema": {"type": "keyword", "is_tenant": true}}' \
        "$qdrant_url/collections/discussions/index" > /dev/null 2>&1 || {
        log_warning "Could not create agent_id index (may already exist or Qdrant not running)"
    }
}

# Record installed project path in manifest for recovery script discovery
record_installed_project() {
    local manifest="$INSTALL_DIR/installed_projects.json"
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local entry="{\"path\": \"$PROJECT_PATH\", \"name\": \"$PROJECT_NAME\", \"installed\": \"$timestamp\"}"

    if [[ -f "$manifest" ]]; then
        # Read existing, deduplicate by path, append new entry
        # Use python for safe JSON manipulation
        "$INSTALL_DIR/.venv/bin/python" -c "
import json, sys
manifest_path = sys.argv[1]
new_entry = json.loads(sys.argv[2])
try:
    with open(manifest_path) as f:
        data = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    data = []
# Deduplicate by path - update existing entry or append
data = [e for e in data if e.get('path') != new_entry['path']]
data.append(new_entry)
with open(manifest_path, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
" "$manifest" "$entry"
    else
        echo "[$entry]" | "$INSTALL_DIR/.venv/bin/python" -c "
import json, sys
data = json.load(sys.stdin)
with open(sys.argv[1], 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
" "$manifest"
    fi
    log_info "Recorded project in manifest: $PROJECT_PATH"
}

# Execute main function with all arguments
main "$@"
