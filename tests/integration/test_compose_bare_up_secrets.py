"""Rendered-config integration test for TD-582 bare-up secret resolution.

Stages a tmp project dir (mirrors ~/.ai-memory/docker/ at runtime) and runs
`docker compose config` with NO --env-file flags — exercising the bare-up
production path. Verifies that secret-class values are non-empty in the
rendered config, that no compose-time interpolation warnings remain for the
6 secret-class keys, and that the qdrant shim entrypoint + volume mount are
correctly wired.

No containers are started.

Companion source-topology test (pure YAML parse, no docker daemon needed)
lives in tests/test_compose_bare_up_topology.py — runs in the fast unit CI
job without --run-integration.

Background: TD-582 (BUG-279 sibling, PM #308 bare-up verification gap).
Architecture: Option 4 env_file: for prometheus-init, prometheus, grafana;
              Option 1 entrypoint shim for qdrant (canonical name translation).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
DOCKER_COMPOSE_PATH = REPO_ROOT / "docker" / "docker-compose.yml"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "td582"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The 6 secret-class keys that must NOT appear as ${VAR} interpolation sites
# in any service environment: block after TD-582.
SECRET_CLASS_KEYS = [
    "PROMETHEUS_ADMIN_PASSWORD",
    "PROMETHEUS_BASIC_AUTH_HEADER",
    "GRAFANA_ADMIN_PASSWORD",
    "GRAFANA_SECRET_KEY",
    "QDRANT_API_KEY",
    "QDRANT_READ_ONLY_API_KEY",
]

# Services under the monitoring profile (absent from `compose config` without
# --profile monitoring).
MONITORING_PROFILE_SERVICES = ["prometheus-init", "prometheus", "grafana"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env_list_to_dict(env_block) -> dict[str, str]:
    """Normalise an environment: block (list or dict) to a plain dict."""
    if not env_block:
        return {}
    if isinstance(env_block, dict):
        return {k: str(v) for k, v in env_block.items()}
    result = {}
    for item in env_block:
        if "=" in item:
            k, v = item.split("=", 1)
            result[k] = v
        else:
            result[item] = ""
    return result


def _render_compose_config(
    project_dir: Path, profiles: list[str] | None = None
) -> tuple[dict, str]:
    """Run `docker compose config` with no --env-file flags (bare-up simulation).

    Docker Compose auto-loads an adjacent .env; .env.secrets is loaded via
    service-level env_file: directives — the TD-582 mechanism under test.

    Args:
        project_dir: Directory containing docker-compose.yml + adjacent env files.
        profiles: Optional list of Docker Compose profiles to activate.

    Returns:
        (parsed_config_dict, stderr_str) — stderr is preserved so callers can
        assert on compose-time interpolation warnings (e.g. "variable is not
        set" lines for secret-class keys, which would indicate a bare-up
        delivery defect).
    """
    compose_file = project_dir / "docker-compose.yml"
    cmd = [
        "docker",
        "compose",
        "--project-directory",
        str(project_dir),
        "-f",
        str(compose_file),
    ]
    for profile in profiles or []:
        cmd += ["--profile", profile]
    cmd.append("config")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(project_dir),
    )
    if result.returncode != 0:
        errors = [ln for ln in result.stderr.splitlines() if "level=error" in ln]
        if errors:
            pytest.fail(
                f"docker compose config exited non-zero with errors:\n"
                f"stderr:\n{result.stderr}\n"
                f"stdout:\n{result.stdout[:2000]}"
            )
    assert result.stdout.strip(), "docker compose config produced no output"
    return yaml.safe_load(result.stdout), result.stderr


# ---------------------------------------------------------------------------
# Rendered bare-up config assertions
# ---------------------------------------------------------------------------


class TestComposeRenderedBarUp:
    """Verify the rendered compose config under bare-up conditions.

    Staged project directory (tmp) mirrors ~/.ai-memory/docker/ at runtime:
      tmp/docker-compose.yml      — copied from docker/docker-compose.yml
      tmp/.env                    — fixture non-secret keys (auto-loaded)
      tmp/.env.secrets            — fixture secret keys (loaded via env_file:)

    No --env-file CLI flags are passed — exercising the bare-up production path.
    """

    @pytest.fixture(scope="class")
    def staged_project(self, tmp_path_factory):
        """Stage tmp dir mimicking ~/.ai-memory/docker/ with fixture env files."""
        tmp_dir = tmp_path_factory.mktemp("td582-bare-up")
        shutil.copy(DOCKER_COMPOSE_PATH, tmp_dir / "docker-compose.yml")
        shutil.copy(FIXTURES_DIR / ".env", tmp_dir / ".env")
        shutil.copy(FIXTURES_DIR / ".env.secrets", tmp_dir / ".env.secrets")
        return tmp_dir

    @pytest.fixture(scope="class")
    def _compose_render(self, staged_project):
        """Single per-class invocation of `docker compose config`.

        Returns (config_dict, stderr_str). Both surfaces are needed: stdout for
        rendered-config structural assertions, stderr for compose-time
        interpolation-warning assertions.
        """
        return _render_compose_config(staged_project, profiles=["monitoring"])

    @pytest.fixture(scope="class")
    def compose_config(self, _compose_render):
        """Rendered compose config dict (all profiles; no --env-file flags)."""
        return _compose_render[0]

    @pytest.fixture(scope="class")
    def compose_stderr(self, _compose_render):
        """Captured stderr from the per-class `docker compose config` run."""
        return _compose_render[1]

    def test_no_secret_class_interpolation_in_rendered_config(self, compose_config):
        """No ${SECRET_CLASS_VAR} interpolation strings for the 6 TD-582 keys
        should appear in the fully rendered compose config.

        Core TD-582 acceptance criterion: env_file: delivery eliminates
        compose-side ${VAR} interpolation for all 6 secret-class keys.
        """
        config_str = yaml.dump(compose_config)
        pattern = re.compile(
            r"\$\{(" + "|".join(re.escape(k) for k in SECRET_CLASS_KEYS) + r")\}"
        )
        matches = pattern.findall(config_str)
        assert not matches, (
            f"Remaining ${{VAR}} interpolation sites for secret-class keys in "
            f"rendered config: {matches}. "
            f"All 6 keys must be delivered via env_file:, not compose interpolation."
        )

    def test_no_unset_variable_warnings_for_secret_class_keys(self, compose_stderr):
        """`docker compose config` stderr must contain zero "variable is not
        set" warnings naming any of the 6 secret-class keys under bare-up.

        Compose emits this warning class whenever a compose-time interpolation
        site (either ${VAR} or unbraced $VAR) cannot be resolved from its
        interpolation source (shell env + auto-loaded adjacent .env). Because
        .env.secrets is NOT in that source under bare-up — it is delivered to
        container env via service-level env_file: at container start — any
        such warning naming a secret-class key indicates a compose-time
        interpolation site that should be using env_file: delivery instead.

        Catches both braced ${VAR} (TD-582 original surface) and unbraced $VAR
        (the prometheus healthcheck CMD-SHELL escape defect found in cycle-1
        review, where compose consumed the $VAR at config-time before the
        container shell could interpolate it from env_file:-populated env)
        regressions through one gate.
        """
        offenders = [
            ln
            for ln in compose_stderr.splitlines()
            if "variable is not set" in ln and any(k in ln for k in SECRET_CLASS_KEYS)
        ]
        assert not offenders, (
            "docker compose config emitted 'variable is not set' warnings for "
            "secret-class key(s) under bare-up. Each warning indicates a "
            "compose-time interpolation site that resolves to an empty string "
            "(since .env.secrets is not in the interpolation source) instead "
            "of being delivered to the container via env_file:.\n"
            "Offending warnings:\n  " + "\n  ".join(offenders)
        )

    @pytest.mark.parametrize(
        "key,expected_prefix",
        [
            ("QDRANT_API_KEY", "td582-test-qdrant-api"),
            ("QDRANT_READ_ONLY_API_KEY", "td582-test-qdrant-ro"),
            ("PROMETHEUS_ADMIN_PASSWORD", "td582-test-prom-admin"),
            ("GRAFANA_ADMIN_PASSWORD", "td582-test-grafana-admin"),
            ("GRAFANA_SECRET_KEY", "td582-test-grafana-secret"),
            ("PROMETHEUS_BASIC_AUTH_HEADER", "Basic dGQ1"),
        ],
    )
    def test_secret_key_resolved_to_fixture_value(
        self, compose_config, key, expected_prefix
    ):
        """With adjacent .env.secrets, each of the 6 secret-class keys must
        resolve to the fixture value (proving bare-up auto-load works).

        `docker compose config` expands env_file: into environment:. The
        resolved values in the rendered config prove the adjacent-file chain
        works without --env-file flags.
        """
        all_env: dict[str, str] = {}
        for service_block in compose_config.get("services", {}).values():
            all_env.update(_env_list_to_dict(service_block.get("environment")))
        value = all_env.get(key, "")
        assert value and value.startswith(expected_prefix), (
            f"Secret key '{key}' should resolve to fixture value starting with "
            f"'{expected_prefix}' under bare-up (adjacent .env.secrets); "
            f"got: {value!r}. env_file: auto-load may not be working."
        )

    def test_qdrant_entrypoint_references_td582_shim(self, compose_config):
        """qdrant service entrypoint must reference the td582 shim in rendered config."""
        entrypoint = compose_config["services"]["qdrant"].get("entrypoint", [])
        if isinstance(entrypoint, list):
            entrypoint_str = " ".join(str(p) for p in entrypoint)
        else:
            entrypoint_str = str(entrypoint)
        assert (
            "td582-entrypoint.sh" in entrypoint_str
        ), f"qdrant entrypoint must reference td582 shim; got: {entrypoint}"

    def test_qdrant_shim_volume_in_rendered_config(self, compose_config):
        """qdrant service must include the shim bind-mount in rendered volumes."""
        volumes = compose_config["services"]["qdrant"].get("volumes") or []
        volume_strs = []
        for v in volumes:
            if isinstance(v, dict):
                volume_strs.append(f"{v.get('source', '')}:{v.get('target', '')}")
            else:
                volume_strs.append(str(v))
        assert any("td582-entrypoint.sh" in v for v in volume_strs), (
            f"qdrant rendered volumes must include td582-entrypoint.sh mount; "
            f"got: {volume_strs}"
        )

    def test_qdrant_log_level_non_secret_still_in_environment(self, compose_config):
        """QDRANT__LOG_LEVEL (non-secret, set via environment:) must remain
        present in the rendered qdrant service config.
        """
        qdrant_env = _env_list_to_dict(
            compose_config["services"]["qdrant"].get("environment")
        )
        assert "QDRANT__LOG_LEVEL" in qdrant_env, (
            "QDRANT__LOG_LEVEL should still be present in qdrant environment: "
            f"(non-secret, set via ${{QDRANT_LOG_LEVEL:-INFO}}); got: {list(qdrant_env)}"
        )


# ---------------------------------------------------------------------------
# TODO (deferred): container-startup integration test
# Boot prometheus + grafana + qdrant under bare-up (no --env-file flags) and
# assert healthy state + non-empty `docker exec env | grep <KEY>` for the 6
# secret-class keys. Blocked on: test orchestration pattern for monitoring
# profile services in CI (requires docker-in-docker or equivalent).
# Reference: TD-582 post-merge follow-up.
# ---------------------------------------------------------------------------
