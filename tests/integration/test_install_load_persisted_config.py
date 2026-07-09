"""Regression tests for install.sh's load_persisted_config() (BUG-520 / BP-182 §2).

Before this fix, the full/reinstall install path (INSTALL_MODE=full over an existing
~/.ai-memory) re-prompted the operator for EVERY previously-configured setting
(GitHub owner/repo/token, Jira URL/email/token/projects, Langfuse, monitoring) because
nothing reloaded the persisted docker/.env + docker/.env.secrets before configure_options
ran — `import_user_env` was a deprecated no-op. Skipping a prompt (the intuitive
"leave as-is" action) silently wrote the enable-flag to "false", disabling a live sync.

load_persisted_config() hydrates the prompt-gated shell vars from persisted state before
configure_options runs, so its existing `[[ -z "$VAR" ]]` prompt guards short-circuit —
the shell analogue of debconf's "seen" flag. Reuses the secrets-first _read_env_key
idiom already proven in configure_project_sources / derive_and_persist_compose_profiles.

Non-negotiable constraints under test:
  1. Only fill UNSET vars — shell-env override still wins (fill-unset-only).
  2. All-or-nothing per feature — an enable-flag hydrates only WITH its dependents.
  3. Secrets-first — GITHUB_TOKEN / JIRA_API_TOKEN read from .env.secrets first.
  4. Gate on existing install — no-op on fresh install (no docker/.env yet).

No external services required — shells out to bash only.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"


def _minimal_env():
    """Isolated environment with only PATH + HOME — prevents ambient shell vars (e.g.
    this dev environment's own LANGFUSE_ENABLED=true from AI-Memory's Langfuse tracing)
    from leaking into the shell-env-override-precedence assertions under test. HOME
    must be present because install.sh's top-level INSTALL_DIR default (`$HOME/.ai-memory`)
    is evaluated under `set -u` even though we override INSTALL_DIR immediately after.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
    }


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """Copy install.sh minus final 'main "$@"' line into tmp_path for safe sourcing."""
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


@pytest.fixture
def install_dir(tmp_path) -> Path:
    """INSTALL_DIR with a fully-configured prior install (GitHub + Jira + Langfuse + monitoring)."""
    docker_dir = tmp_path / "install_dir" / "docker"
    docker_dir.mkdir(parents=True)
    (docker_dir / ".env").write_text(
        "GITHUB_SYNC_ENABLED=true\n"
        "GITHUB_REPO=owner/repo\n"
        "GITHUB_TOKEN=\n"
        "JIRA_SYNC_ENABLED=true\n"
        "JIRA_INSTANCE_URL=https://company.atlassian.net\n"
        "JIRA_EMAIL=user@example.com\n"
        "JIRA_API_TOKEN=\n"
        'JIRA_PROJECTS="[\\"PROJ\\"]"\n'
        "LANGFUSE_ENABLED=false\n"
        "MONITORING_ENABLED=true\n"
    )
    (docker_dir / ".env.secrets").write_text(
        "GITHUB_TOKEN=ghp_persisted_token\n" "JIRA_API_TOKEN=ATATpersisted_token\n"
    )
    return tmp_path / "install_dir"


def _run(
    install_sh_copy: Path,
    install_dir: Path,
    extra: str = "",
    functions: str = "load_persisted_config",
    stdin: str | None = None,
) -> subprocess.CompletedProcess:
    """Source install.sh (no-main copy), export INSTALL_DIR + extra shell vars, run `functions`."""
    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
{extra}
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
{functions}
echo "__GITHUB_SYNC_ENABLED=${{GITHUB_SYNC_ENABLED:-}}"
echo "__GITHUB_REPO=${{GITHUB_REPO:-}}"
echo "__GITHUB_TOKEN=${{GITHUB_TOKEN:-}}"
echo "__JIRA_SYNC_ENABLED=${{JIRA_SYNC_ENABLED:-}}"
echo "__JIRA_INSTANCE_URL=${{JIRA_INSTANCE_URL:-}}"
echo "__JIRA_EMAIL=${{JIRA_EMAIL:-}}"
echo "__JIRA_API_TOKEN=${{JIRA_API_TOKEN:-}}"
echo "__LANGFUSE_ENABLED=${{LANGFUSE_ENABLED:-}}"
echo "__INSTALL_MONITORING=${{INSTALL_MONITORING:-}}"
echo "__SEED_BEST_PRACTICES=${{SEED_BEST_PRACTICES:-}}"
"""
    return subprocess.run(
        ["bash", "-c", bash_cmd],
        capture_output=True,
        text=True,
        input=stdin,
        env=_minimal_env(),
    )


def _parse(stdout: str) -> dict:
    out = {}
    for line in stdout.splitlines():
        if line.startswith("__"):
            key, _, val = line[2:].partition("=")
            out[key] = val
    return out


# ---------------------------------------------------------------------------
# Constraint 4 — gate on existing install (no-op on fresh install)
# ---------------------------------------------------------------------------


def test_fresh_install_noop(install_sh_no_main, tmp_path):
    """No docker/.env present (fresh install) — load_persisted_config is a no-op."""
    fresh_install_dir = tmp_path / "fresh_install_dir"
    fresh_install_dir.mkdir()
    result = _run(install_sh_no_main, fresh_install_dir)
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["GITHUB_SYNC_ENABLED"] == ""
    assert v["JIRA_SYNC_ENABLED"] == ""
    assert v["LANGFUSE_ENABLED"] == ""
    assert v["INSTALL_MONITORING"] == ""
    # SEED_BEST_PRACTICES is not defaulted on fresh install — must still prompt later
    assert v["SEED_BEST_PRACTICES"] == ""


# ---------------------------------------------------------------------------
# Full hydration — complete persisted config reused, secrets-first
# ---------------------------------------------------------------------------


def test_hydrates_complete_github_config(install_sh_no_main, install_dir):
    result = _run(install_sh_no_main, install_dir)
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["GITHUB_SYNC_ENABLED"] == "true"
    assert v["GITHUB_REPO"] == "owner/repo"
    # Secrets-first: GITHUB_TOKEN in .env is blank; real value lives in .env.secrets
    assert v["GITHUB_TOKEN"] == "ghp_persisted_token"


def test_hydrates_complete_jira_config(install_sh_no_main, install_dir):
    result = _run(install_sh_no_main, install_dir)
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["JIRA_SYNC_ENABLED"] == "true"
    assert v["JIRA_INSTANCE_URL"] == "https://company.atlassian.net"
    assert v["JIRA_EMAIL"] == "user@example.com"
    assert v["JIRA_API_TOKEN"] == "ATATpersisted_token"


def test_hydrates_langfuse_and_monitoring(install_sh_no_main, install_dir):
    result = _run(install_sh_no_main, install_dir)
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["LANGFUSE_ENABLED"] == "false"
    assert v["INSTALL_MONITORING"] == "true"


def test_seed_best_practices_defaults_false_on_existing_install(
    install_sh_no_main, install_dir
):
    """SEED_BEST_PRACTICES is an action (not persisted state) — defaults to skip
    re-seed on reinstall so the DB isn't re-populated on every reinstall."""
    result = _run(install_sh_no_main, install_dir)
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["SEED_BEST_PRACTICES"] == "false"


# ---------------------------------------------------------------------------
# Constraint 2 — all-or-nothing per feature (a partial prior config is NOT hydrated)
# ---------------------------------------------------------------------------


def test_github_partial_config_not_hydrated(install_sh_no_main, tmp_path):
    """GITHUB_SYNC_ENABLED=true persisted but GITHUB_TOKEN missing → leave unset (prompt)."""
    docker_dir = tmp_path / "partial_install" / "docker"
    docker_dir.mkdir(parents=True)
    (docker_dir / ".env").write_text(
        "GITHUB_SYNC_ENABLED=true\nGITHUB_REPO=owner/repo\nGITHUB_TOKEN=\n"
    )
    (docker_dir / ".env.secrets").write_text("GITHUB_TOKEN=\n")
    result = _run(install_sh_no_main, tmp_path / "partial_install")
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["GITHUB_SYNC_ENABLED"] == "", (
        "Incomplete GitHub config (enabled but no token) must NOT be hydrated — "
        "would pass validate_external_services's -z guard but fail credential validation."
    )
    assert v["GITHUB_REPO"] == ""


def test_jira_partial_config_not_hydrated(install_sh_no_main, tmp_path):
    """JIRA_SYNC_ENABLED=true persisted but JIRA_EMAIL missing → leave unset (prompt)."""
    docker_dir = tmp_path / "partial_install" / "docker"
    docker_dir.mkdir(parents=True)
    (docker_dir / ".env").write_text(
        "JIRA_SYNC_ENABLED=true\n"
        "JIRA_INSTANCE_URL=https://company.atlassian.net\n"
        "JIRA_EMAIL=\n"
        "JIRA_API_TOKEN=\n"
    )
    (docker_dir / ".env.secrets").write_text("JIRA_API_TOKEN=tok\n")
    result = _run(install_sh_no_main, tmp_path / "partial_install")
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert (
        v["JIRA_SYNC_ENABLED"] == ""
    ), "Incomplete Jira config (enabled but no email) must NOT be hydrated."


def test_disabled_feature_persisted_reused(install_sh_no_main, tmp_path):
    """A previously-disabled feature (enable-flag=false) IS hydrated — reuses the 'no' answer."""
    docker_dir = tmp_path / "disabled_install" / "docker"
    docker_dir.mkdir(parents=True)
    (docker_dir / ".env").write_text(
        "GITHUB_SYNC_ENABLED=false\nJIRA_SYNC_ENABLED=false\n"
    )
    (docker_dir / ".env.secrets").write_text("")
    result = _run(install_sh_no_main, tmp_path / "disabled_install")
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["GITHUB_SYNC_ENABLED"] == "false"
    assert v["JIRA_SYNC_ENABLED"] == "false"


# ---------------------------------------------------------------------------
# Constraint 1 — fill-unset-only: shell-env override wins over persisted state
# ---------------------------------------------------------------------------


def test_shell_env_override_wins_over_persisted(install_sh_no_main, install_dir):
    """JIRA_SYNC_ENABLED=false exported in shell BEFORE load_persisted_config runs —
    override wins even though a complete, enabled prior config is persisted."""
    result = _run(
        install_sh_no_main, install_dir, extra='export JIRA_SYNC_ENABLED="false"'
    )
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert (
        v["JIRA_SYNC_ENABLED"] == "false"
    ), "Shell-env override must win over persisted state (shell > .env > default)"
    # GitHub was NOT overridden — still hydrates normally from persisted state
    assert v["GITHUB_SYNC_ENABLED"] == "true"


def test_shell_env_override_wins_for_monitoring(install_sh_no_main, install_dir):
    result = _run(
        install_sh_no_main, install_dir, extra='export INSTALL_MONITORING="false"'
    )
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["INSTALL_MONITORING"] == "false"


# ---------------------------------------------------------------------------
# Transparency log line
# ---------------------------------------------------------------------------


def test_transparency_log_line_emitted_on_hydration(install_sh_no_main, install_dir):
    result = _run(install_sh_no_main, install_dir)
    assert result.returncode == 0, result.stderr
    assert "Reusing existing config" in result.stdout


def test_no_transparency_log_line_on_fresh_install(install_sh_no_main, tmp_path):
    fresh_install_dir = tmp_path / "fresh_install_dir"
    fresh_install_dir.mkdir()
    result = _run(install_sh_no_main, fresh_install_dir)
    assert result.returncode == 0, result.stderr
    assert "Reusing existing config" not in result.stdout


# ---------------------------------------------------------------------------
# Production-path integration — reinstall fires ZERO prompts (BP-182 §2.5 assertion #2)
# ---------------------------------------------------------------------------
# Exercises load_persisted_config() -> configure_options() as install.sh's main() calls
# them (immediately adjacent, full-mode branch), with stdin closed (/dev/null) so any
# `read -p` that DID fire would read EOF and take the "no"/default branch — reproducing
# the exact BUG-520 footgun (skipped prompt silently disables a live sync) if hydration
# were broken. Asserts the persisted "true" answers survive untouched.


def test_reinstall_over_existing_install_fires_zero_prompts(
    install_sh_no_main, install_dir
):
    # configure_options ends with an unconditional (ungated) "Proceed with
    # installation?" confirmation — not one of the four feature prompts under
    # test here. Feed it a bare newline (default/empty answer = proceed) so
    # `read` doesn't hit EOF and abort the script under `set -e`; this does
    # NOT feed any of the GitHub/Jira/Langfuse/monitoring prompt reads, which
    # must not fire at all if hydration worked.
    result = _run(
        install_sh_no_main,
        install_dir,
        extra='export NON_INTERACTIVE="false"',
        functions="load_persisted_config\nconfigure_options",
        stdin="\n",
    )
    assert result.returncode == 0, result.stderr
    v = _parse(result.stdout)
    assert v["GITHUB_SYNC_ENABLED"] == "true", (
        "GITHUB_SYNC_ENABLED flipped by a prompt reading EOF from /dev/null — "
        "load_persisted_config did not hydrate before configure_options ran."
    )
    assert v["GITHUB_REPO"] == "owner/repo"
    assert v["GITHUB_TOKEN"] == "ghp_persisted_token"
    assert v["JIRA_SYNC_ENABLED"] == "true"
    assert v["JIRA_API_TOKEN"] == "ATATpersisted_token"
    assert v["INSTALL_MONITORING"] == "true"


# ---------------------------------------------------------------------------
# Structural — call-site reachability (BP-182 §2.4 call site)
# ---------------------------------------------------------------------------
# BUG-311/fix-r4 escape lesson: a function-in-isolation test can pass while the
# production call chain is broken. Assert load_persisted_config is actually wired
# into main()'s full-mode branch, immediately before configure_options.


def test_load_persisted_config_called_immediately_before_configure_options():
    lines = _INSTALL_SH.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if "load_persisted_config" in line and not line.strip().startswith("#"):
            window = "\n".join(lines[i : i + 3])
            if "configure_options" in window:
                found = True
                break
    assert found, (
        "load_persisted_config must be called immediately before configure_options "
        "in scripts/install.sh's full-mode branch (BP-182 §2.4 call site missing)."
    )
