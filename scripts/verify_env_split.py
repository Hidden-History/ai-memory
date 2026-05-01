#!/usr/bin/env python3
"""verify_env_split.py — Doctor command for ENV-MANAGEMENT-V2 secrets split.

CLI: python scripts/verify_env_split.py --install-dir <path> [--strict]
Exit codes: 0 = all invariants pass; 1 = invariant failed; 2 = required files missing.

Asserts 8 invariants per BP-154 §9. Use --strict to additionally require
PP-3 user-supplied keys absent from docker/.env.
"""

import argparse
import glob
import re
import stat
import sys
from pathlib import Path

# PP-1: user-supplied required tokens — already-correct keys (installer moves these)
PP_1_KEYS = [
    "GITHUB_TOKEN",
    "JIRA_API_TOKEN",
]

# PP-2 core: auto-generated secret-class keys — always required (6 keys)
PP_2_CORE_KEYS = [
    "QDRANT_API_KEY",
    "QDRANT_READ_ONLY_API_KEY",
    "GRAFANA_ADMIN_PASSWORD",
    "GRAFANA_SECRET_KEY",
    "PROMETHEUS_ADMIN_PASSWORD",
    "PROMETHEUS_BASIC_AUTH_HEADER",
]

# PP-2 Langfuse: auto-generated Langfuse secret-class keys — required only when LANGFUSE_ENABLED=true (12 keys)
PP_2_LANGFUSE_KEYS = [
    "LANGFUSE_DB_PASSWORD",
    "LANGFUSE_CLICKHOUSE_PASSWORD",
    "LANGFUSE_NEXTAUTH_SECRET",
    "LANGFUSE_SALT",
    "LANGFUSE_ENCRYPTION_KEY",
    "LANGFUSE_S3_ACCESS_KEY",
    "LANGFUSE_S3_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_INIT_PROJECT_PUBLIC_KEY",
    "LANGFUSE_INIT_PROJECT_SECRET_KEY",
    "LANGFUSE_INIT_USER_PASSWORD",
]

# PP-3: user-supplied optional keys — migrate-if-present
PP_3_KEYS = [
    "OLLAMA_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "EVALUATOR_API_KEY",
]

ALL_SECRET_KEYS = (
    PP_1_KEYS + PP_2_CORE_KEYS + PP_2_LANGFUSE_KEYS + PP_3_KEYS
)  # 25 total

# Non-secret LANGFUSE_INIT_* keys — belong in docker/.env, not .env.secrets
LANGFUSE_NON_SECRET_INIT_KEYS = [
    "LANGFUSE_INIT_ORG_ID",
    "LANGFUSE_INIT_ORG_NAME",
    "LANGFUSE_INIT_PROJECT_ID",
    "LANGFUSE_INIT_PROJECT_NAME",
    "LANGFUSE_INIT_USER_EMAIL",
    "LANGFUSE_INIT_USER_NAME",
]


def _read_env_pairs(path: Path) -> dict:
    """Parse KEY=VALUE lines from an env file; strip surrounding quotes from values."""
    result: dict = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip().strip("\"'")
    return result


def _file_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _is_wsl() -> bool:
    """Detect WSL host — chmod 600 may silently no-op on WSL; degrade I2 to _warn only."""
    try:
        return any(
            marker in Path("/proc/sys/kernel/osrelease").read_text().lower()
            for marker in ("microsoft", "wsl")
        )
    except OSError:
        return False


def _ok(msg: str) -> None:
    print(f"[PASS] {msg}")


# Diagnostic function: logs key NAMES only (set membership against PP_*_KEYS /
# LANGFUSE_* constants). Secret VALUES are never passed in — callers embed only
# key names via taint-breaking tuple(sorted(...)) constructors at each call site.
# CodeQL py/clear-text-logging-sensitive-data is suppressed for this whole file
# via .github/codeql/codeql-config.yml (PM #273; inline `# lgtm[...]` markers
# are not honoured by github/codeql-action@v4).
def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _fail(failures: list, msg: str) -> None:
    failures.append(msg)


def run_checks(install_dir: str, strict: bool) -> int:
    """Run all invariants. Returns exit code: 0 (pass), 1 (failed), 2 (files missing)."""
    docker_dir = Path(install_dir) / "docker"
    env_file = docker_dir / ".env"
    secrets_file = docker_dir / ".env.secrets"
    compose_file = docker_dir / "docker-compose.yml"

    failures: list = []

    if not env_file.exists():
        print(f"[FATAL] docker/.env not found: {env_file}", file=sys.stderr)
        return 2

    env_vals = _read_env_pairs(env_file)
    secrets_vals = _read_env_pairs(secrets_file) if secrets_file.exists() else {}

    # I1: .env.secrets must exist if any secret-class key is non-empty
    if not secrets_file.exists():
        any_present = any(env_vals.get(k) for k in ALL_SECRET_KEYS)
        if any_present:
            _fail(
                failures,
                "I1: docker/.env.secrets absent but secret-class keys non-empty in docker/.env",
            )
        else:
            _ok(
                "I1: docker/.env.secrets absent and no secret-class keys in docker/.env (pre-configure state)"
            )
    else:
        _ok("I1: docker/.env.secrets exists")

    # I2: file permissions (.env = 644, .env.secrets = 600)
    # On WSL, chmod 600 may silently no-op (filesystem limitation); warn only on WSL.
    # On real Linux/macOS, a mode mismatch is a security invariant violation → _fail.
    env_mode = _file_mode(env_file)
    if env_mode != 0o644:
        if _is_wsl():
            _warn(
                f"I2: docker/.env mode {oct(env_mode)} (expected 0o644 — WSL may not enforce)"
            )
        else:
            _fail(failures, f"I2: docker/.env mode {oct(env_mode)} (expected 0o644)")
    else:
        _ok("I2a: docker/.env mode 644")

    if secrets_file.exists():
        sec_mode = _file_mode(secrets_file)
        if sec_mode != 0o600:
            if _is_wsl():
                _warn(
                    f"I2: docker/.env.secrets mode {oct(sec_mode)} (expected 0o600 — WSL may not enforce)"
                )
            else:
                _fail(
                    failures,
                    f"I2: docker/.env.secrets mode {oct(sec_mode)} (expected 0o600)",
                )
        else:
            _ok("I2b: docker/.env.secrets mode 600")

    # I3: PP-2 keys present (non-empty) in .env.secrets
    # Core keys always required; Langfuse subset gated on LANGFUSE_ENABLED=true
    # (mirrors GITHUB_SYNC_ENABLED / JIRA_SYNC_ENABLED gates at I5 below)
    langfuse_enabled = env_vals.get("LANGFUSE_ENABLED", "false").lower() == "true"
    # Key NAMES only — .get() truth-value selects names; values are never included.
    missing_core = tuple(sorted(k for k in PP_2_CORE_KEYS if not secrets_vals.get(k)))
    missing_langfuse = (
        tuple(sorted(k for k in PP_2_LANGFUSE_KEYS if not secrets_vals.get(k)))
        if langfuse_enabled
        else ()
    )
    i3_failed = False
    if missing_core:
        _fail(
            failures,
            f"I3: PP-2 core keys missing/empty in .env.secrets: {missing_core}",
        )
        i3_failed = True
    if missing_langfuse:
        _fail(
            failures,
            f"I3: PP-2 Langfuse keys missing/empty in .env.secrets: {missing_langfuse}",
        )
        i3_failed = True
    if not i3_failed:
        if langfuse_enabled:
            _ok(
                f"I3: all {len(PP_2_CORE_KEYS) + len(PP_2_LANGFUSE_KEYS)} PP-2 keys present"
                " in .env.secrets"
            )
        else:
            _ok(
                f"I3: all {len(PP_2_CORE_KEYS)} PP-2 core keys present in .env.secrets"
                " (Langfuse keys not required)"
            )

    # I4: no secret-class key has a non-empty value in .env
    # Key NAMES only — .get() truth-value selects names; values are never included.
    leaked = tuple(sorted(k for k in ALL_SECRET_KEYS if env_vals.get(k)))
    if leaked:
        _fail(
            failures,
            f"I4: secret-class keys with non-empty values in docker/.env: {leaked}",
        )
    else:
        _ok("I4: no secret-class keys have non-empty values in docker/.env")

    # I5: PP-1 keys in .env.secrets when sync is enabled
    github_enabled = env_vals.get("GITHUB_SYNC_ENABLED", "false").lower() == "true"
    jira_enabled = env_vals.get("JIRA_SYNC_ENABLED", "false").lower() == "true"
    pp1_fail = False
    if github_enabled and not secrets_vals.get("GITHUB_TOKEN"):
        _fail(
            failures,
            "I5: GITHUB_TOKEN missing in .env.secrets but GITHUB_SYNC_ENABLED=true",
        )
        pp1_fail = True
    if jira_enabled and not secrets_vals.get("JIRA_API_TOKEN"):
        _fail(
            failures,
            "I5: JIRA_API_TOKEN missing in .env.secrets but JIRA_SYNC_ENABLED=true",
        )
        pp1_fail = True
    if not pp1_fail:
        _ok("I5: PP-1 keys present in .env.secrets (or sync not enabled)")

    # I6: non-secret LANGFUSE_INIT_* keys absent from .env.secrets AND present in .env
    # Key NAMES only — .get() truth-value selects names; values are never included.
    wrong_in_secrets = tuple(
        sorted(k for k in LANGFUSE_NON_SECRET_INIT_KEYS if secrets_vals.get(k))
    )
    if wrong_in_secrets:
        _fail(
            failures,
            f"I6: non-secret LANGFUSE_INIT_* keys in .env.secrets: {wrong_in_secrets}",
        )
    else:
        _ok("I6: non-secret LANGFUSE_INIT_* keys absent from .env.secrets")
    # _warn (not _fail): these keys are only populated after langfuse_setup.sh runs;
    # absence on a non-Langfuse install is acceptable.
    # Key NAMES only — .get() truth-value selects names; values are never included.
    missing_from_env = tuple(
        sorted(k for k in LANGFUSE_NON_SECRET_INIT_KEYS if not env_vals.get(k))
    )
    if missing_from_env:
        _warn(
            f"I6: non-secret LANGFUSE_INIT_* keys absent from .env (expected after langfuse setup): "
            f"{missing_from_env}"
        )

    # I7: no orphan .env.secrets.XXXXXX tempfiles in docker/
    orphans = [
        Path(p).name
        for p in glob.glob(str(docker_dir / ".env.secrets.*"))
        if not p.endswith(".example")
    ]
    if orphans:
        _fail(failures, f"I7: orphan .env.secrets.* tempfiles in docker/: {orphans}")
    else:
        _ok("I7: no orphan .env.secrets.* tempfiles")

    # I8: docker-compose.yml lists .env.secrets with required: false
    if not compose_file.exists():
        _warn(f"I8: docker-compose.yml not found at {compose_file} — skipping")
    else:
        compose_text = compose_file.read_text(encoding="utf-8")
        if re.search(r"path:\s*\.env\.secrets\s*\n\s*required:\s*false", compose_text):
            _ok("I8: docker-compose.yml lists .env.secrets with required: false")
        elif ".env.secrets" in compose_text:
            _fail(
                failures,
                "I8: .env.secrets present in compose but not paired with required: false — check compose layout",
            )
        else:
            _fail(
                failures,
                "I8: docker-compose.yml missing .env.secrets entry with required: false",
            )

    # --strict: PP-3 user-supplied keys absent from .env
    if strict:
        # Key NAMES only — .get() truth-value selects names; values are never included.
        pp3_in_env = tuple(sorted(k for k in PP_3_KEYS if env_vals.get(k)))
        if pp3_in_env:
            _fail(
                failures,
                f"STRICT: PP-3 keys with non-empty values in docker/.env: {pp3_in_env}",
            )
        else:
            _ok("STRICT: PP-3 keys absent from docker/.env")

    if failures:
        print(f"\n[FAIL] {len(failures)} invariant(s) failed:", file=sys.stderr)
        # Failures list contains diagnostic key NAMES only — see taint-breaking
        # tuple(sorted(...)) constructors at each _fail call site above.
        # Secret VALUES are never embedded. CodeQL suppression for this file lives
        # in .github/codeql/codeql-config.yml (PM #273).
        for msg in failures:
            print(f"  ✗ {msg}", file=sys.stderr)
        return 1

    print("\n[OK] All env-split invariants passed.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify ENV-MANAGEMENT-V2 split-file invariants (BP-154 §9)."
    )
    parser.add_argument(
        "--install-dir", required=True, help="AI Memory installation directory path"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also assert PP-3 user-supplied keys absent from docker/.env",
    )
    args = parser.parse_args()
    sys.exit(run_checks(args.install_dir, args.strict))


if __name__ == "__main__":
    main()
