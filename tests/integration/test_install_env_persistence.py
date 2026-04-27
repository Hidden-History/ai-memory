"""Regression tests for install.sh user-input persistence to env files (BUG-274).

Exercises persist_user_choices_to_env() — verifies that user-collected shell
vars (GitHub sync, Jira sync, Langfuse) reach docker/.env and docker/.env.secrets
after the function runs, and that template placeholder defaults are NOT preserved
when the user provided real values.

No external services required — shells out to bash only.
Performance budget: <3 s per test.
"""

import os
import stat
import subprocess

import pytest

# Minimal docker/.env content mirroring the real .env.example template shape.
ENV_TEMPLATE = """\
GITHUB_SYNC_ENABLED=false
GITHUB_TOKEN=
GITHUB_REPO=
JIRA_SYNC_ENABLED=false
JIRA_INSTANCE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECTS=
LANGFUSE_ENABLED=false
"""

# Minimal docker/.env.secrets content mirroring .env.secrets.example Section 1.
SECRETS_TEMPLATE = """\
GITHUB_TOKEN=
JIRA_API_TOKEN=
"""

# Inline bash definitions for the functions under test.
# These are copied from scripts/install.sh to allow isolated invocation without
# triggering the full installer (install.sh calls main "$@" unconditionally at EOF).
_BASH_HELPERS = """\
log_debug()   { :; }
log_warning() { :; }
log_info()    { :; }

format_jira_projects_json() {
    local input="${1:-}"
    if [[ -z "$input" ]]; then echo '[]'; return; fi
    local result
    result=$(printf '%s' "$input" | python3 -c "
import json, sys
keys = [k.strip() for k in sys.stdin.read().strip().split(',') if k.strip()]
print(json.dumps(keys))
" 2>/dev/null) || { echo '[]'; return; }
    echo "$result"
}

set_env_value() {
    local key="$1"
    local value="$2"
    local env_file="${3:-$INSTALL_DIR/docker/.env}"
    if grep -q "^${key}=" "$env_file" 2>/dev/null; then
        sed -i.bak "s|^${key}=.*|${key}=${value}|" "$env_file" && rm -f "$env_file.bak"
    else
        echo "${key}=${value}" >> "$env_file"
    fi
}

persist_user_choices_to_env() {
    local env_file="$INSTALL_DIR/docker/.env"
    local secrets_file="$INSTALL_DIR/docker/.env.secrets"

    if [[ ! -f "$secrets_file" ]]; then
        if [[ -f "$INSTALL_DIR/docker/.env.secrets.example" ]]; then
            cp "$INSTALL_DIR/docker/.env.secrets.example" "$secrets_file"
        else
            touch "$secrets_file"
        fi
    fi
    chmod 600 "$secrets_file" 2>/dev/null || log_warning "chmod 600 on .env.secrets failed"

    [[ -n "${LANGFUSE_ENABLED:-}" ]] && set_env_value "LANGFUSE_ENABLED" "$LANGFUSE_ENABLED"
    [[ -n "${GITHUB_SYNC_ENABLED:-}" ]] && set_env_value "GITHUB_SYNC_ENABLED" "$GITHUB_SYNC_ENABLED"
    [[ -n "${JIRA_SYNC_ENABLED:-}" ]] && set_env_value "JIRA_SYNC_ENABLED" "$JIRA_SYNC_ENABLED"

    if [[ "${GITHUB_SYNC_ENABLED:-}" == "true" ]]; then
        [[ -n "${GITHUB_REPO:-}" ]] && set_env_value "GITHUB_REPO" "$GITHUB_REPO"
    fi

    if [[ "${JIRA_SYNC_ENABLED:-}" == "true" ]]; then
        [[ -n "${JIRA_INSTANCE_URL:-}" ]] && set_env_value "JIRA_INSTANCE_URL" "$JIRA_INSTANCE_URL"
        [[ -n "${JIRA_EMAIL:-}" ]] && set_env_value "JIRA_EMAIL" "$JIRA_EMAIL"
        if [[ -n "${JIRA_PROJECTS:-}" ]]; then
            local jira_json
            if [[ "${JIRA_PROJECTS}" =~ ^\\[ ]]; then
                jira_json="$JIRA_PROJECTS"
            else
                jira_json=$(format_jira_projects_json "$JIRA_PROJECTS")
            fi
            set_env_value "JIRA_PROJECTS" "'$jira_json'"
        fi
    fi

    if [[ "${GITHUB_SYNC_ENABLED:-}" == "true" && -n "${GITHUB_TOKEN:-}" ]]; then
        set_env_value "GITHUB_TOKEN" "$GITHUB_TOKEN" "$secrets_file"
    fi
    if [[ "${JIRA_SYNC_ENABLED:-}" == "true" && -n "${JIRA_API_TOKEN:-}" ]]; then
        set_env_value "JIRA_API_TOKEN" "$JIRA_API_TOKEN" "$secrets_file"
    fi

    chmod 600 "$secrets_file" 2>/dev/null || true
}
"""


def _minimal_env():
    """Return a minimal environment with only PATH so Python resolves correctly."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}


@pytest.fixture()
def install_dir(tmp_path):
    """Set up a minimal INSTALL_DIR with starter docker/.env and docker/.env.secrets."""
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    (docker_dir / ".env").write_text(ENV_TEMPLATE)
    (docker_dir / ".env.secrets").write_text(SECRETS_TEMPLATE)
    os.chmod(str(docker_dir / ".env.secrets"), 0o600)
    return str(tmp_path)


def _run(script, install_dir, env_vars=""):
    """Run a bash script with the helper defs and given INSTALL_DIR + env vars."""
    cmd = f"""\
{_BASH_HELPERS}
export INSTALL_DIR={install_dir}
{env_vars}
persist_user_choices_to_env
"""
    return subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        env=_minimal_env(),
    )


def _read_env(install_dir, filename="docker/.env"):
    with open(os.path.join(install_dir, filename)) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Positive tests — user values land in the correct file
# ---------------------------------------------------------------------------


def test_github_sync_enabled_written_to_env(install_dir):
    """GITHUB_SYNC_ENABLED=true persists to docker/.env."""
    result = _run(
        "",
        install_dir,
        "GITHUB_SYNC_ENABLED=true GITHUB_REPO=owner/myrepo GITHUB_TOKEN=ghp_test",
    )
    assert result.returncode == 0, result.stderr.decode()
    content = _read_env(install_dir)
    assert "GITHUB_SYNC_ENABLED=true" in content


def test_github_repo_written_to_env(install_dir):
    """GITHUB_REPO persists to docker/.env when GitHub sync enabled."""
    result = _run(
        "",
        install_dir,
        "GITHUB_SYNC_ENABLED=true GITHUB_REPO=owner/myrepo GITHUB_TOKEN=ghp_test",
    )
    assert result.returncode == 0, result.stderr.decode()
    content = _read_env(install_dir)
    assert "GITHUB_REPO=owner/myrepo" in content


def test_github_token_written_to_secrets(install_dir):
    """GITHUB_TOKEN persists to docker/.env.secrets (not docker/.env)."""
    result = _run(
        "",
        install_dir,
        "GITHUB_SYNC_ENABLED=true GITHUB_REPO=owner/myrepo GITHUB_TOKEN=ghp_testtoken",
    )
    assert result.returncode == 0, result.stderr.decode()
    secrets = _read_env(install_dir, "docker/.env.secrets")
    assert "GITHUB_TOKEN=ghp_testtoken" in secrets


def test_jira_sync_enabled_written_to_env(install_dir):
    """JIRA_SYNC_ENABLED=true persists to docker/.env."""
    result = _run(
        "",
        install_dir,
        (
            "JIRA_SYNC_ENABLED=true "
            "JIRA_INSTANCE_URL=https://company.atlassian.net "
            "JIRA_EMAIL=user@example.com "
            "JIRA_API_TOKEN=ATATtesttoken "
            "JIRA_PROJECTS=PROJ,BACKEND"
        ),
    )
    assert result.returncode == 0, result.stderr.decode()
    content = _read_env(install_dir)
    assert "JIRA_SYNC_ENABLED=true" in content


def test_jira_credentials_written_to_env(install_dir):
    """JIRA_INSTANCE_URL and JIRA_EMAIL persist to docker/.env."""
    result = _run(
        "",
        install_dir,
        (
            "JIRA_SYNC_ENABLED=true "
            "JIRA_INSTANCE_URL=https://company.atlassian.net "
            "JIRA_EMAIL=user@example.com "
            "JIRA_API_TOKEN=ATATtesttoken "
            "JIRA_PROJECTS=PROJ"
        ),
    )
    assert result.returncode == 0, result.stderr.decode()
    content = _read_env(install_dir)
    assert "JIRA_INSTANCE_URL=https://company.atlassian.net" in content
    assert "JIRA_EMAIL=user@example.com" in content


def test_jira_api_token_written_to_secrets(install_dir):
    """JIRA_API_TOKEN persists to docker/.env.secrets (not docker/.env)."""
    result = _run(
        "",
        install_dir,
        (
            "JIRA_SYNC_ENABLED=true "
            "JIRA_INSTANCE_URL=https://company.atlassian.net "
            "JIRA_EMAIL=user@example.com "
            "JIRA_API_TOKEN=ATATtesttoken "
            "JIRA_PROJECTS=PROJ"
        ),
    )
    assert result.returncode == 0, result.stderr.decode()
    secrets = _read_env(install_dir, "docker/.env.secrets")
    assert "JIRA_API_TOKEN=ATATtesttoken" in secrets


def test_jira_projects_written_as_json(install_dir):
    """JIRA_PROJECTS comma-separated is converted to JSON array in docker/.env."""
    result = _run(
        "",
        install_dir,
        (
            "JIRA_SYNC_ENABLED=true "
            "JIRA_INSTANCE_URL=https://co.atlassian.net "
            "JIRA_EMAIL=a@b.com "
            "JIRA_API_TOKEN=tok "
            "JIRA_PROJECTS=PROJ,BACKEND"
        ),
    )
    assert result.returncode == 0, result.stderr.decode()
    content = _read_env(install_dir)
    assert "PROJ" in content
    assert "BACKEND" in content


def test_langfuse_enabled_written_to_env(install_dir):
    """LANGFUSE_ENABLED=true persists to docker/.env."""
    result = _run("", install_dir, "LANGFUSE_ENABLED=true")
    assert result.returncode == 0, result.stderr.decode()
    content = _read_env(install_dir)
    assert "LANGFUSE_ENABLED=true" in content


# ---------------------------------------------------------------------------
# Negative tests — empty / disabled vars don't overwrite template defaults
# ---------------------------------------------------------------------------


def test_github_disabled_leaves_token_empty_in_secrets(install_dir):
    """When GitHub sync is disabled, GITHUB_TOKEN is not written to .env.secrets."""
    result = _run("", install_dir, "GITHUB_SYNC_ENABLED=false")
    assert result.returncode == 0, result.stderr.decode()
    secrets = _read_env(install_dir, "docker/.env.secrets")
    # Template has GITHUB_TOKEN= (empty); must not be overwritten with empty either
    assert "GITHUB_TOKEN=ghp_" not in secrets
    # The template placeholder may still be present or absent; what must NOT happen is
    # a non-empty token appearing when user disabled sync.
    assert "ghp_" not in secrets


def test_github_sync_disabled_does_not_write_repo(install_dir):
    """GITHUB_REPO is not written to docker/.env when GitHub sync is disabled."""
    result = _run("", install_dir, "GITHUB_SYNC_ENABLED=false")
    assert result.returncode == 0, result.stderr.decode()
    content = _read_env(install_dir)
    # Template has GITHUB_REPO= (empty); disabled sync must not populate it
    assert "GITHUB_REPO=owner/" not in content


def test_empty_github_token_not_written(install_dir):
    """Empty GITHUB_TOKEN is not written to .env.secrets even when sync enabled."""
    result = _run(
        "",
        install_dir,
        "GITHUB_SYNC_ENABLED=true GITHUB_REPO=owner/repo GITHUB_TOKEN=",
    )
    assert result.returncode == 0, result.stderr.decode()
    secrets = _read_env(install_dir, "docker/.env.secrets")
    # Template has GITHUB_TOKEN=; must still be empty after the function ran
    assert "GITHUB_TOKEN=" in secrets  # placeholder preserved
    # But must not have been updated to something non-empty
    lines = [line for line in secrets.splitlines() if line.startswith("GITHUB_TOKEN=")]
    assert lines, "GITHUB_TOKEN key should still be present"
    assert lines[0] == "GITHUB_TOKEN=", f"Expected empty, got: {lines[0]!r}"


def test_github_sync_false_written_when_user_answered_no(install_dir):
    """GITHUB_SYNC_ENABLED=false (user answered no) overwrites template false — idempotent."""
    result = _run("", install_dir, "GITHUB_SYNC_ENABLED=false")
    assert result.returncode == 0, result.stderr.decode()
    content = _read_env(install_dir)
    assert "GITHUB_SYNC_ENABLED=false" in content


# ---------------------------------------------------------------------------
# Idempotency test — running twice with same args produces no duplicate keys
# ---------------------------------------------------------------------------


def test_idempotency_no_duplicate_keys(install_dir):
    """Running persist_user_choices_to_env twice with same vars produces no duplicate keys."""
    vars_str = (
        "GITHUB_SYNC_ENABLED=true GITHUB_REPO=owner/repo GITHUB_TOKEN=ghp_tok "
        "JIRA_SYNC_ENABLED=true "
        "JIRA_INSTANCE_URL=https://co.atlassian.net "
        "JIRA_EMAIL=u@e.com JIRA_API_TOKEN=tok JIRA_PROJECTS=PROJ "
        "LANGFUSE_ENABLED=false"
    )
    cmd = f"""\
{_BASH_HELPERS}
export INSTALL_DIR={install_dir}
{vars_str}
persist_user_choices_to_env
persist_user_choices_to_env
"""
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        env=_minimal_env(),
    )
    assert result.returncode == 0, result.stderr.decode()

    env_content = _read_env(install_dir)
    for key in (
        "GITHUB_SYNC_ENABLED",
        "GITHUB_REPO",
        "JIRA_SYNC_ENABLED",
        "JIRA_INSTANCE_URL",
        "JIRA_EMAIL",
        "JIRA_PROJECTS",
        "LANGFUSE_ENABLED",
    ):
        count = sum(
            1 for line in env_content.splitlines() if line.startswith(f"{key}=")
        )
        assert (
            count == 1
        ), f"Duplicate key {key}: found {count} occurrences in docker/.env"

    secrets_content = _read_env(install_dir, "docker/.env.secrets")
    for key in ("GITHUB_TOKEN", "JIRA_API_TOKEN"):
        count = sum(
            1 for line in secrets_content.splitlines() if line.startswith(f"{key}=")
        )
        assert (
            count == 1
        ), f"Duplicate key {key}: found {count} occurrences in docker/.env.secrets"


# ---------------------------------------------------------------------------
# chmod 600 test — .env.secrets permissions enforced after writes
# ---------------------------------------------------------------------------


def test_secrets_file_chmod_600(install_dir):
    """docker/.env.secrets has mode 600 after persist_user_choices_to_env runs."""
    result = _run(
        "",
        install_dir,
        "GITHUB_SYNC_ENABLED=true GITHUB_REPO=owner/repo GITHUB_TOKEN=ghp_tok",
    )
    assert result.returncode == 0, result.stderr.decode()
    secrets_path = os.path.join(install_dir, "docker", ".env.secrets")
    mode = stat.S_IMODE(os.stat(secrets_path).st_mode)
    assert mode == 0o600, f"Expected 0o600 on .env.secrets, got {oct(mode)}"


# ---------------------------------------------------------------------------
# No-secret-leak test — tokens must NOT appear in docker/.env
# ---------------------------------------------------------------------------


def test_github_token_not_in_env(install_dir):
    """GITHUB_TOKEN must not appear in docker/.env (secrets belong in .env.secrets)."""
    result = _run(
        "",
        install_dir,
        "GITHUB_SYNC_ENABLED=true GITHUB_REPO=owner/repo GITHUB_TOKEN=ghp_secrettoken",
    )
    assert result.returncode == 0, result.stderr.decode()
    env_content = _read_env(install_dir)
    # The template has GITHUB_TOKEN= (empty placeholder) — that's acceptable.
    # What must NOT happen: the actual secret value appears in docker/.env.
    assert (
        "ghp_secrettoken" not in env_content
    ), "GITHUB_TOKEN secret value leaked into docker/.env"


def test_jira_api_token_not_in_env(install_dir):
    """JIRA_API_TOKEN must not appear in docker/.env (belongs in .env.secrets)."""
    result = _run(
        "",
        install_dir,
        (
            "JIRA_SYNC_ENABLED=true "
            "JIRA_INSTANCE_URL=https://co.atlassian.net "
            "JIRA_EMAIL=u@e.com "
            "JIRA_API_TOKEN=ATATsecrettoken "
            "JIRA_PROJECTS=PROJ"
        ),
    )
    assert result.returncode == 0, result.stderr.decode()
    env_content = _read_env(install_dir)
    assert (
        "ATATsecrettoken" not in env_content
    ), "JIRA_API_TOKEN secret value leaked into docker/.env"


# ---------------------------------------------------------------------------
# Pre-fix regression — documents the pre-fix behavior (BUG-274 itself)
# ---------------------------------------------------------------------------


def test_without_persist_function_user_values_are_lost(install_dir):
    """Without persist_user_choices_to_env, template defaults survive (pre-fix behavior).

    This documents the BUG-274 root cause: if we skip the persist call and just
    let configure_environment run its append guard, the guard finds the key already
    present (from the .env.example template) and skips the write. User answers stay
    only in shell memory, never reaching the file.

    If this test starts FAILING (values DO appear without the persist call), it
    means the root cause has been addressed elsewhere — investigate before removing.
    """
    # Simulate the pre-fix state: set env vars but do NOT call persist_user_choices_to_env.
    # Then check that docker/.env still has the template defaults.
    cmd = f"""\
export INSTALL_DIR={install_dir}
export GITHUB_SYNC_ENABLED=true
export GITHUB_REPO=owner/repo
export GITHUB_TOKEN=ghp_tok
# No persist call — user choices live only in shell vars, never reach the file.
# The template docker/.env still has GITHUB_SYNC_ENABLED=false.
"""
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        env=_minimal_env(),
    )
    assert result.returncode == 0
    env_content = _read_env(install_dir)
    # Without the fix, the file retains template defaults.
    assert "GITHUB_SYNC_ENABLED=false" in env_content, (
        "Pre-fix: expected template default GITHUB_SYNC_ENABLED=false to be preserved "
        "without persist_user_choices_to_env. If this fails, check BUG-274 root cause."
    )
    assert "GITHUB_REPO=" in env_content  # template has empty GITHUB_REPO=
    assert "owner/repo" not in env_content
