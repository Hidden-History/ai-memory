#!/usr/bin/env bash
# _env_split_helpers.sh — Shared helpers for ENV-MANAGEMENT-V2 secrets split.
# Source this file from install.sh and langfuse_setup.sh; do not execute directly.
# Implements BUG-277 fix: atomic migration + fresh-install write to .env.secrets.
# Algorithm source: BP-154 §3 (POSIX rename atomicity; verify-before-blank; chmod-before-write).

# Compatible with parent script color vars; define fallbacks only if not already set.
_H_RED="${RED:-\033[0;31m}"
_H_GREEN="${GREEN:-\033[0;32m}"
_H_YELLOW="${YELLOW:-\033[1;33m}"
_H_BLUE="${BLUE:-\033[0;34m}"
_H_NC="${NC:-\033[0m}"

# ALL_SECRET_KEYS — canonical 25-key list for split enforcement (BUG-286).
# Single source of truth: adding a new secret-class key requires updating only here.
# Sourced by install.sh; referenced by migrate_secrets_to_split_file and
# any future blanking / import-filter logic.
ALL_SECRET_KEYS=(
    # PP-1: user-input secrets (2)
    GITHUB_TOKEN
    JIRA_API_TOKEN
    # PP-2: auto-generated infrastructure secrets (17)
    QDRANT_API_KEY
    GRAFANA_ADMIN_PASSWORD GRAFANA_SECRET_KEY
    PROMETHEUS_ADMIN_PASSWORD PROMETHEUS_BASIC_AUTH_HEADER
    LANGFUSE_DB_PASSWORD LANGFUSE_CLICKHOUSE_PASSWORD
    LANGFUSE_NEXTAUTH_SECRET LANGFUSE_SALT LANGFUSE_ENCRYPTION_KEY
    LANGFUSE_S3_ACCESS_KEY LANGFUSE_S3_SECRET_KEY
    LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY
    LANGFUSE_INIT_PROJECT_PUBLIC_KEY LANGFUSE_INIT_PROJECT_SECRET_KEY
    LANGFUSE_INIT_USER_PASSWORD
    # PP-3: template-only / user-supplied API keys (6)
    QDRANT_READ_ONLY_API_KEY
    OLLAMA_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY
    OPENAI_API_KEY EVALUATOR_API_KEY
)

_h_log_success() { printf "${_H_GREEN}[SUCCESS]${_H_NC} %s\n" "$1"; }
_h_log_error()   { printf "${_H_RED}[ERROR]${_H_NC} %s\n" "$1" >&2; }
_h_log_info()    { printf "${_H_BLUE}[INFO]${_H_NC} %s\n" "$1"; }
_h_log_warn()    { printf "${_H_YELLOW}[WARNING]${_H_NC} %s\n" "$1"; }

# ensure_secrets_file_exists — create .env.secrets with chmod 600 if absent; enforce 600 if present.
ensure_secrets_file_exists() {
    local secrets_file="$1"
    if [[ ! -f "$secrets_file" ]]; then
        install -m 600 /dev/null "$secrets_file" 2>/dev/null \
            || _h_log_warn "install -m 600 on ${secrets_file} failed — secrets may be world-readable"
        _h_log_info "Created ${secrets_file} (chmod 600)"
    else
        chmod 600 "$secrets_file" 2>/dev/null \
            || _h_log_warn "chmod 600 on ${secrets_file} failed"
    fi
}

# _blank_key_in_env — replace KEY=<value> with KEY= in env_file; idempotent.
_blank_key_in_env() {
    local key="$1"
    local env_file="$2"
    if grep -qE "^${key}=.+" "$env_file" 2>/dev/null; then
        sed -i.bak "s|^${key}=.*|${key}=|" "$env_file" && rm -f "${env_file}.bak"
    fi
}

# _read_env_key — read KEY=VALUE from a flat env file (secrets_file-first fallthrough).
# Handles dual-file architecture: secrets live in secrets_file post-migration.
# NOTE: tr -d '"'"'" strips ALL quote characters from value. Safe for auto-generated
# PP-2 secrets (openssl rand hex, secrets.token_*) and PP-1 tokens (alphanumeric + _ + -).
# PP-3 user-supplied keys with embedded ' or " characters will be silently corrupted
# — track via BP-153 follow-up env-loader cleanup.
_read_env_key() {
    local key="$1"
    local secrets_file="$2"
    local env_file="$3"
    local val
    val=$(grep "^${key}=" "$secrets_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'" || true)
    if [[ -z "$val" ]]; then
        val=$(grep "^${key}=" "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'" || true)
    fi
    printf '%s' "$val"
}

# migrate_secret_to_secrets_file — BP-154 §3 Option γ atomic single-key migration.
# Moves one key from .env (chmod 644) to .env.secrets (chmod 600).
# Idempotent: safe to re-run; verify-before-blank prevents data loss.
migrate_secret_to_secrets_file() {
    local key="$1"
    local env_file="$2"
    local secrets_file="$3"
    local secrets_dir
    secrets_dir="$(dirname "$secrets_file")"

    # Step 1: Read current value from .env
    local current_val
    current_val=$(grep "^${key}=" "$env_file" 2>/dev/null \
                  | head -1 | cut -d= -f2- | tr -d '"'"'" || true)

    # Step 2: Already in .env.secrets with a value — ensure .env is blanked and return
    local existing_in_secrets
    existing_in_secrets=$(grep "^${key}=" "$secrets_file" 2>/dev/null \
                          | head -1 | cut -d= -f2- | tr -d '"'"'" || true)
    if [[ -n "$existing_in_secrets" ]]; then
        _blank_key_in_env "$key" "$env_file"
        return 0
    fi

    # Step 3: No value in .env — template-only key not configured; skip silently
    if [[ -z "$current_val" ]]; then return 0; fi

    # Step 4: Atomic write to .env.secrets via tempfile in same directory.
    # chmod 600 applied BEFORE writing content — never 644 even transiently.
    # Same-directory tempfile guarantees same filesystem for POSIX rename() atomicity.
    local tmp_secrets _rc
    tmp_secrets=$(mktemp "${secrets_dir}/.env.secrets.XXXXXX") \
        || { _h_log_error "mktemp failed for ${key}"; return 1; }
    chmod 600 "$tmp_secrets" \
        || { _h_log_error "chmod 600 on tempfile failed for ${key}"; rm -f "$tmp_secrets"; return 1; }
    if [[ -f "$secrets_file" ]]; then
        grep -v "^${key}=" "$secrets_file" >> "$tmp_secrets"
        _rc=$?
        if [[ $_rc -ne 0 && $_rc -ne 1 ]]; then
            rm -f "$tmp_secrets"
            _h_log_error "grep -v failed reading ${secrets_file} (exit $_rc); aborting migration of ${key}"
            return 1
        fi
    fi
    printf '%s="%s"\n' "$key" "$current_val" >> "$tmp_secrets"
    mv "$tmp_secrets" "$secrets_file"

    # Step 5: Verify write succeeded before touching .env
    local verify_val
    verify_val=$(grep "^${key}=" "$secrets_file" 2>/dev/null \
                 | head -1 | cut -d= -f2- | tr -d '"'"'" || true)
    if [[ "$verify_val" != "$current_val" ]]; then
        _h_log_error "Migration verify failed for ${key} — .env unchanged; investigate and re-run"
        return 1
    fi

    # Step 6: Blank in .env only after verification passes (data-loss guard)
    _blank_key_in_env "$key" "$env_file"
    _h_log_success "Migrated ${key} → .env.secrets"
}

# write_secret_to_secrets_file — fresh-install direct write to .env.secrets (steps 4-5 only).
# No source-file read or blank — used when generating a new value for the first time.
# Idempotent: if key already has a non-empty value in secrets_file, returns 0 without change.
write_secret_to_secrets_file() {
    local key="$1"
    local value="$2"
    local secrets_file="$3"
    local secrets_dir
    secrets_dir="$(dirname "$secrets_file")"

    # Idempotence: already set with a non-empty value — skip generation
    local existing
    existing=$(grep "^${key}=" "$secrets_file" 2>/dev/null \
               | head -1 | cut -d= -f2- | tr -d '"'"'" || true)
    if [[ -n "$existing" ]]; then
        _h_log_info "${key} already present in $(basename "$secrets_file") — skipped"
        return 0
    fi

    # Atomic write via tempfile in same directory (POSIX rename() atomicity)
    local tmp_secrets _rc
    tmp_secrets=$(mktemp "${secrets_dir}/.env.secrets.XXXXXX") \
        || { _h_log_error "mktemp failed for ${key}"; return 1; }
    chmod 600 "$tmp_secrets" \
        || { _h_log_error "chmod 600 on tempfile failed for ${key}"; rm -f "$tmp_secrets"; return 1; }
    if [[ -f "$secrets_file" ]]; then
        grep -v "^${key}=" "$secrets_file" >> "$tmp_secrets"
        _rc=$?
        if [[ $_rc -ne 0 && $_rc -ne 1 ]]; then
            rm -f "$tmp_secrets"
            _h_log_error "grep -v failed reading ${secrets_file} (exit $_rc); aborting write of ${key}"
            return 1
        fi
    fi
    printf '%s="%s"\n' "$key" "$value" >> "$tmp_secrets"
    mv "$tmp_secrets" "$secrets_file"

    # Verify write
    local verify_val
    verify_val=$(grep "^${key}=" "$secrets_file" 2>/dev/null \
                 | head -1 | cut -d= -f2- | tr -d '"'"'" || true)
    if [[ "$verify_val" != "$value" ]]; then
        _h_log_error "Write verify failed for ${key} in .env.secrets"
        return 1
    fi
    _h_log_success "Wrote ${key} → $(basename "$secrets_file")"
}

# migrate_secrets_to_split_file — wrapper: migrate all 25 secret-class keys (PP-1 + PP-2 + PP-3).
# PP-1 keys (GITHUB_TOKEN, JIRA_API_TOKEN) are now included as defense-in-depth (BUG-286):
# migrate_secret_to_secrets_file step 2 handles the case where .env.secrets already has the
# value (idempotent blank-in-.env), so including PP-1 is always safe.
# Called ONLY on Option 1 in-place upgrade (existing docker/.env with non-blank secret keys).
# Halts on first failure so partial-migration state is visible to the user.
migrate_secrets_to_split_file() {
    local env_file="$1"
    local secrets_file="$2"

    local pp1_keys=(
        GITHUB_TOKEN
        JIRA_API_TOKEN
    )
    local pp2_keys=(
        QDRANT_API_KEY
        GRAFANA_ADMIN_PASSWORD GRAFANA_SECRET_KEY
        PROMETHEUS_ADMIN_PASSWORD PROMETHEUS_BASIC_AUTH_HEADER
        LANGFUSE_DB_PASSWORD LANGFUSE_CLICKHOUSE_PASSWORD
        LANGFUSE_NEXTAUTH_SECRET LANGFUSE_SALT LANGFUSE_ENCRYPTION_KEY
        LANGFUSE_S3_ACCESS_KEY LANGFUSE_S3_SECRET_KEY
        LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY
        LANGFUSE_INIT_PROJECT_PUBLIC_KEY LANGFUSE_INIT_PROJECT_SECRET_KEY
        LANGFUSE_INIT_USER_PASSWORD
    )
    local pp3_keys=(
        QDRANT_READ_ONLY_API_KEY
        OLLAMA_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY
        OPENAI_API_KEY EVALUATOR_API_KEY
    )

    _h_log_info "Migrating secret-class keys from .env to .env.secrets..."
    for key in "${pp1_keys[@]}" "${pp2_keys[@]}" "${pp3_keys[@]}"; do
        migrate_secret_to_secrets_file "$key" "$env_file" "$secrets_file" || {
            _h_log_error "Migration halted on ${key} — re-run installer after investigating"
            return 1
        }
    done
    _h_log_success "Migration complete (25 keys checked across PP-1/PP-2/PP-3 — all secret-class keys enforced)"
}
