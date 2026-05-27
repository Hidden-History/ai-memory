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

    def test_grafana_entrypoint_set_in_source(self, source_config):
        """grafana service must declare the TD-582 shim entrypoint + restored command.

        Mirror of test_qdrant_entrypoint_set_in_source: closes F-NEW-1
        (Grafana's GF_SECURITY_* namespace-mismatch). Docker Compose clears
        the image ENTRYPOINT when entrypoint: is overridden; the upstream
        image has Entrypoint=["/run.sh"] + Cmd=null, so command: must
        restore /run.sh as the exec target of the shim's `exec "$@"`.
        """
        grafana = source_config["services"]["grafana"]
        assert grafana.get("entrypoint") == [
            "/bin/sh",
            "/usr/local/bin/td582-entrypoint.sh",
        ], f"grafana entrypoint must invoke the td582 shim; got: {grafana.get('entrypoint')}"
        assert grafana.get("command") == [
            "/run.sh"
        ], f"grafana command must restore upstream /run.sh; got: {grafana.get('command')}"

    def test_grafana_shim_volume_in_source(self, source_config):
        """grafana service must include the shim bind-mount in volumes:.

        Mirror of test_qdrant_shim_volume_in_source.
        """
        volumes = source_config["services"]["grafana"].get("volumes") or []
        volume_strs = [str(v) for v in volumes]
        assert any(
            "./grafana/entrypoint.sh:/usr/local/bin/td582-entrypoint.sh:ro" in v
            for v in volume_strs
        ), (
            "grafana volumes must include the td582 shim bind-mount; "
            f"got: {volume_strs}"
        )


# ---------------------------------------------------------------------------
# Effective-env subset assertion (closes the F-NEW-1 escape gap)
# ---------------------------------------------------------------------------

# Consumer-side env var names each TD-582-affected service relies on at runtime.
# The effective container env (env_file: source files union environment: block
# union shim re-exports) MUST be a superset of this for the service to function.
#
# - qdrant: shim re-exports QDRANT__SERVICE__* from canonical QDRANT_*
# - prometheus-init: reads canonical names directly (renders prometheus.yml)
# - prometheus: healthcheck shell reads canonical PROMETHEUS_BASIC_AUTH_HEADER
# - grafana: shim re-exports GF_SECURITY_* from canonical GRAFANA_*; datasource
#   provisioning reads canonical PROMETHEUS_ADMIN_PASSWORD directly
EXPECTED_CONSUMER_ENV_PER_SERVICE: dict[str, set[str]] = {
    "qdrant": {"QDRANT__SERVICE__API_KEY", "QDRANT__SERVICE__READ_ONLY_API_KEY"},
    "prometheus-init": {"PROMETHEUS_ADMIN_PASSWORD", "QDRANT_API_KEY"},
    "prometheus": {"PROMETHEUS_BASIC_AUTH_HEADER"},
    "grafana": {
        "GF_SECURITY_ADMIN_PASSWORD",
        "GF_SECURITY_SECRET_KEY",
        "PROMETHEUS_ADMIN_PASSWORD",
    },
}

# Path containing docker-compose.yml — env_file: paths are relative to it,
# and the shim bind-mount LHS paths are also relative to it.
DOCKER_DIR = REPO_ROOT / "docker"

# .env contracts: example files committed to source. The tests must NEVER read
# the operator's real .env / .env.secrets (which contain real secrets); the
# *.example files document the contract for what env_file: will deliver.
ENV_FILE_CONTRACT_MAP = {
    ".env": DOCKER_DIR / ".env.example",
    ".env.secrets": DOCKER_DIR / ".env.secrets.example",
}

# Match a POSIX-sh `export NAME="$OTHER"` (with or without quotes / fallback
# expansion) in an entrypoint shim. Used to derive the shim rename mapping
# without executing the shim. Group 1 captures the exported (LHS) name.
SHIM_EXPORT_RE = re.compile(
    r'^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"?\$\{?[A-Za-z_]',
    re.MULTILINE,
)


def _parse_env_keys(path: Path) -> set[str]:
    """Return the set of NAME= keys in a dotenv-style file (commented lines skipped)."""
    keys: set[str] = set()
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        name = stripped.split("=", 1)[0].strip()
        if name and name.replace("_", "").isalnum():
            keys.add(name)
    return keys


def _env_block_keys(service_block: dict) -> set[str]:
    """Return the set of NAME= keys defined directly in environment:.

    Strips out ${VAR}-only references (since those resolve from upstream env
    rather than introducing a new name into the effective container env).
    """
    env = service_block.get("environment") or []
    if isinstance(env, dict):
        items = [f"{k}={v}" for k, v in env.items()]
    else:
        items = [str(item) for item in env]
    keys: set[str] = set()
    for item in items:
        # `- NAME` form (no `=`) is a passthrough from upstream; the whole item
        # is the name. Otherwise split on the first `=` and take the LHS.
        name = item.strip() if "=" not in item else item.split("=", 1)[0].strip()
        if name:
            keys.add(name)
    return keys


def _shim_exports(volumes: list, docker_dir: Path) -> set[str]:
    """Return the set of variable names a TD-582 entrypoint shim re-exports.

    Looks for a `td582-entrypoint.sh` bind-mount; if present, reads the source
    file (LHS of the bind-mount, resolved relative to docker_dir) and parses
    `export NAME=$OTHER` lines. The LHS names are added to the effective
    container env when the shim runs.
    """
    exports: set[str] = set()
    for vol in volumes or []:
        vol_str = str(vol)
        if "td582-entrypoint.sh" not in vol_str:
            continue
        # Bind-mount form is "<host_path>:<container_path>[:mode]"; host_path
        # is the LHS. Resolve relative to docker_dir.
        host_path_rel = vol_str.split(":", 1)[0]
        shim_path = (docker_dir / host_path_rel).resolve()
        if not shim_path.exists():
            continue
        shim_text = shim_path.read_text(encoding="utf-8")
        for match in SHIM_EXPORT_RE.finditer(shim_text):
            exports.add(match.group(1))
    return exports


def _effective_env(service_block: dict) -> set[str]:
    """Compute the effective container env name set the same way the runtime sees it.

    Combines:
      (a) every NAME= key in each env_file: path's *.example contract,
      (b) every NAME (or NAME=...) key in the environment: block,
      (c) every NAME re-exported by the td582 entrypoint shim (if mounted).

    This is the static analog of `docker exec <ctr> env | cut -d= -f1` for the
    bare-up code path (no --env-file flags, no shell-source of secrets).
    """
    keys: set[str] = set()
    # (a) env_file: contracts
    for entry in service_block.get("env_file") or []:
        path = entry["path"] if isinstance(entry, dict) else str(entry)
        contract = ENV_FILE_CONTRACT_MAP.get(path)
        if contract is not None:
            keys |= _parse_env_keys(contract)
    # (b) environment: block
    keys |= _env_block_keys(service_block)
    # (c) shim re-exports
    keys |= _shim_exports(service_block.get("volumes") or [], DOCKER_DIR)
    return keys


class TestEffectiveContainerEnvCoverage:
    """Assert each TD-582 service's expected consumer env-var names are a
    subset of the effective container env at bare-up time.

    Closes the structural-test gap that let F-NEW-1 (Grafana
    `GF_SECURITY_ADMIN_PASSWORD` / `GF_SECURITY_SECRET_KEY` namespace
    mismatch) escape both cycle-1 and cycle-2 review: prior tests asserted
    `env_file:` was declared but did not verify that the consumer-side
    namespaced keys were actually reachable from env_file: + environment: +
    shim composition.
    """

    @pytest.fixture(scope="class")
    def source_config(self):
        with open(DOCKER_COMPOSE_PATH) as fh:
            return yaml.safe_load(fh)

    @pytest.mark.parametrize("service", sorted(EXPECTED_CONSUMER_ENV_PER_SERVICE))
    def test_effective_env_satisfies_consumer_expectations(
        self, source_config, service
    ):
        block = source_config["services"][service]
        effective = _effective_env(block)
        expected = EXPECTED_CONSUMER_ENV_PER_SERVICE[service]
        missing = expected - effective
        assert not missing, (
            f"Service '{service}': consumer env vars {sorted(missing)} are not "
            f"reachable via env_file: contracts + environment: block + shim "
            f"re-exports. Effective env names (sample): "
            f"{sorted(effective)[:15]}{'...' if len(effective) > 15 else ''}"
        )
