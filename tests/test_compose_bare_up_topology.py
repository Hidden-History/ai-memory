"""Unit-tier topology test for TD-582 bare-up secret resolution.

Pure YAML-parse — no Docker daemon dependency. Runs in the fast unit CI job
without the --run-integration flag.

`docker compose config` expands env_file: entries into the environment: block
in rendered output (the env_file: key is not preserved). Source-file assertions
are therefore the authoritative check for the TD-582 topology change: secret-class
env vars are routed through env_file: directives rather than compose-side ${VAR}
interpolation, so that bare `docker compose up -d` resolves secrets without
requiring --env-file flags.

Companion rendered-config test (needs `docker compose config` CLI) lives in
tests/integration/test_compose_bare_up_secrets.py.

Relocated from tests/integration/ to mirror the
tests/test_compose_qdrant_wiring.py precedent (BUG-287 fix-r2 H-1): placing a
pure YAML-parse test under integration/ caused it to be auto-marked integration
and excluded from the fast unit CI job, defeating the cheap-regression-guard
purpose.

Background: TD-582 (BUG-279 sibling, PM #308 bare-up verification gap).
Architecture: Option 4 env_file: for prometheus-init, prometheus, grafana;
              Option 1 entrypoint shim for qdrant (canonical name translation).
"""

import re
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
DOCKER_COMPOSE_PATH = REPO_ROOT / "docker" / "docker-compose.yml"

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

# Services that must declare env_file: with .env.secrets after TD-582.
ENV_FILE_SERVICES = ["prometheus-init", "prometheus", "grafana", "qdrant"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env_file_paths(service_block: dict) -> list[str]:
    """Extract path strings from a service's env_file: list (handles dict or str entries)."""
    entries = service_block.get("env_file") or []
    return [
        entry["path"] if isinstance(entry, dict) else str(entry) for entry in entries
    ]


# ---------------------------------------------------------------------------
# Source topology assertions (parse docker-compose.yml directly)
# ---------------------------------------------------------------------------


class TestComposeSourceTopology:
    """Verify the env_file: topology in the compose source file.

    `docker compose config` expands env_file: entries into the environment:
    block in rendered output; the env_file: key is not preserved. Source-file
    assertions are the authoritative check for the TD-582 topology change.
    """

    @pytest.fixture(scope="class")
    def source_config(self):
        """Parsed docker/docker-compose.yml source (not rendered output)."""
        with open(DOCKER_COMPOSE_PATH) as fh:
            return yaml.safe_load(fh)

    @pytest.mark.parametrize("service", ENV_FILE_SERVICES)
    def test_service_has_env_file_with_dot_env_secrets(self, source_config, service):
        """Each TD-582 service must declare env_file: with a .env.secrets path."""
        paths = _env_file_paths(source_config["services"][service])
        assert any(
            ".env.secrets" in p for p in paths
        ), f"{service}: env_file: must include .env.secrets; got paths: {paths}"

    @pytest.mark.parametrize("service", ENV_FILE_SERVICES)
    def test_service_has_env_file_with_dot_env(self, source_config, service):
        """Each TD-582 service must also declare env_file: with a .env path."""
        paths = _env_file_paths(source_config["services"][service])
        assert any(
            p.endswith(".env") and ".secrets" not in p for p in paths
        ), f"{service}: env_file: must include .env (required); got paths: {paths}"

    @pytest.mark.parametrize("key", SECRET_CLASS_KEYS)
    def test_no_secret_class_key_in_source_environment_blocks(self, source_config, key):
        """No service environment: block should set a secret-class key via
        ${VAR} interpolation after TD-582.

        This is the direct structural proof that the 6 secret-class env vars
        are no longer resolved via compose interpolation.
        """
        pattern = re.compile(r"\$\{" + re.escape(key) + r"[}:]")
        for service_name, service_block in source_config.get("services", {}).items():
            env_block = service_block.get("environment") or []
            if isinstance(env_block, list):
                env_items = env_block
            else:
                env_items = [f"{k}={v}" for k, v in env_block.items()]
            for item in env_items:
                assert not pattern.search(str(item)), (
                    f"Service '{service_name}': secret-class key '{key}' still "
                    f"appears as ${{VAR}} interpolation in environment: block: {item!r}"
                )

    def test_qdrant_entrypoint_set_in_source(self, source_config):
        """qdrant service must declare entrypoint: referencing the td582 shim."""
        entrypoint = source_config["services"]["qdrant"].get("entrypoint", [])
        if isinstance(entrypoint, list):
            entrypoint_str = " ".join(str(p) for p in entrypoint)
        else:
            entrypoint_str = str(entrypoint)
        assert (
            "td582-entrypoint.sh" in entrypoint_str
        ), f"qdrant entrypoint must reference td582 shim; got: {entrypoint}"

    def test_qdrant_shim_volume_in_source(self, source_config):
        """qdrant service must include the shim bind-mount in volumes:."""
        volumes = source_config["services"]["qdrant"].get("volumes") or []
        volume_strs = [str(v) for v in volumes]
        assert any(
            "td582-entrypoint.sh" in v for v in volume_strs
        ), f"qdrant volumes must include td582-entrypoint.sh mount; got: {volume_strs}"
