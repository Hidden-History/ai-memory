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
tests/test_compose_qdrant_wiring.py precedent (BUG-287 H-1): placing a
pure YAML-parse test under integration/ caused it to be auto-marked integration
and excluded from the fast unit CI job, defeating the cheap-regression-guard
purpose.

Background: TD-582 (BUG-279 sibling, PM #308 bare-up verification gap).
Architecture: Option 4 env_file: for prometheus-init, prometheus, grafana;
              Option 1 entrypoint shims for qdrant + grafana (canonical name
              translation); TD-583 image-bake for prometheus-init +
              langfuse-clickhouse config delivery.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
DOCKER_COMPOSE_PATH = REPO_ROOT / "docker" / "docker-compose.yml"
DOCKER_COMPOSE_LANGFUSE_PATH = REPO_ROOT / "docker" / "docker-compose.langfuse.yml"

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

    def test_qdrant_shim_baked_via_dockerfile(self, source_config):
        """qdrant service must bake the shim via Dockerfile, NOT a bind-mount.

        Replaces the prior test_qdrant_shim_volume_in_source assertion. On
        Docker Desktop / WSL2 the single-file bind-mount delivery became
        fragile across host reboots (tmpfs cache corruption -> runc 'not a
        directory' mount errors). The fix bakes the shim into a local image
        via docker/qdrant/Dockerfile; this test pins that delivery shape.
        """
        qdrant = source_config["services"]["qdrant"]

        # (a) build: block points at the local Dockerfile
        build = qdrant.get("build")
        assert isinstance(
            build, dict
        ), f"qdrant must declare a build: block; got: {build!r}"
        assert (
            build.get("context") == "./qdrant"
        ), f"qdrant build.context must be './qdrant'; got: {build.get('context')!r}"
        assert build.get("dockerfile") == "Dockerfile", (
            f"qdrant build.dockerfile must be 'Dockerfile'; got: "
            f"{build.get('dockerfile')!r}"
        )

        # (b) Dockerfile exists and COPYs the shim to the expected target path
        dockerfile_path = DOCKER_DIR / "qdrant" / "Dockerfile"
        assert (
            dockerfile_path.exists()
        ), f"docker/qdrant/Dockerfile must exist; not found at {dockerfile_path}"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
        assert re.search(
            r"COPY\s+(?:--chmod=\d+\s+)?entrypoint\.sh\s+"
            r"/usr/local/bin/td582-entrypoint\.sh",
            dockerfile_text,
        ), (
            "qdrant Dockerfile must COPY entrypoint.sh to "
            "/usr/local/bin/td582-entrypoint.sh"
        )

        # (c) the regression class: no shim bind-mount in volumes:
        volumes = qdrant.get("volumes") or []
        volume_strs = [str(v) for v in volumes]
        assert not any("td582-entrypoint.sh" in v for v in volume_strs), (
            "qdrant volumes must NOT bind-mount the shim (image-bake delivery "
            f"only); got: {volume_strs}"
        )

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

    def test_grafana_shim_baked_via_dockerfile(self, source_config):
        """grafana service must bake the shim via Dockerfile, NOT a bind-mount.

        Mirror of test_qdrant_shim_baked_via_dockerfile.
        """
        grafana = source_config["services"]["grafana"]

        # (a) build: block points at the local Dockerfile
        build = grafana.get("build")
        assert isinstance(
            build, dict
        ), f"grafana must declare a build: block; got: {build!r}"
        assert (
            build.get("context") == "./grafana"
        ), f"grafana build.context must be './grafana'; got: {build.get('context')!r}"
        assert build.get("dockerfile") == "Dockerfile", (
            f"grafana build.dockerfile must be 'Dockerfile'; got: "
            f"{build.get('dockerfile')!r}"
        )

        # (b) Dockerfile exists and COPYs the shim to the expected target path
        dockerfile_path = DOCKER_DIR / "grafana" / "Dockerfile"
        assert (
            dockerfile_path.exists()
        ), f"docker/grafana/Dockerfile must exist; not found at {dockerfile_path}"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
        assert re.search(
            r"COPY\s+(?:--chmod=\d+\s+)?entrypoint\.sh\s+"
            r"/usr/local/bin/td582-entrypoint\.sh",
            dockerfile_text,
        ), (
            "grafana Dockerfile must COPY entrypoint.sh to "
            "/usr/local/bin/td582-entrypoint.sh"
        )

        # (c) the regression class: no shim bind-mount in volumes:
        volumes = grafana.get("volumes") or []
        volume_strs = [str(v) for v in volumes]
        assert not any("td582-entrypoint.sh" in v for v in volume_strs), (
            "grafana volumes must NOT bind-mount the shim (image-bake "
            f"delivery only); got: {volume_strs}"
        )

    @pytest.fixture(scope="class")
    def langfuse_config(self):
        """Parsed docker/docker-compose.langfuse.yml source."""
        with open(DOCKER_COMPOSE_LANGFUSE_PATH) as fh:
            return yaml.safe_load(fh)

    def test_prometheus_init_baked_via_dockerfile(self, source_config):
        """prometheus-init must bake config templates via Dockerfile, NOT bind-mounts.

        TD-583: the 3 single-file bind-mounts for web.yml, prometheus.yml, and
        gen-prometheus-config.py were fragile on Docker Desktop / WSL2 (tmpfs
        cache corruption on host reboot). Fix bakes them into a local image via
        docker/prometheus/Dockerfile.
        """
        svc = source_config["services"]["prometheus-init"]

        # (a) build: block points at the local Dockerfile
        build = svc.get("build")
        assert isinstance(
            build, dict
        ), f"prometheus-init must declare a build: block; got: {build!r}"
        assert (
            build.get("context") == "./prometheus"
        ), f"prometheus-init build.context must be './prometheus'; got: {build.get('context')!r}"
        assert (
            build.get("dockerfile") == "Dockerfile"
        ), f"prometheus-init build.dockerfile must be 'Dockerfile'; got: {build.get('dockerfile')!r}"

        # (b) Dockerfile exists and COPYs all 3 config files to expected target paths
        dockerfile_path = DOCKER_DIR / "prometheus" / "Dockerfile"
        assert (
            dockerfile_path.exists()
        ), f"docker/prometheus/Dockerfile must exist; not found at {dockerfile_path}"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
        for src, dst in [
            ("web.yml", "/etc/prometheus/web.yml.template"),
            ("prometheus.yml", "/etc/prometheus/prometheus.yml.template"),
            ("gen-prometheus-config.py", "/scripts/gen-prometheus-config.py"),
        ]:
            assert re.search(
                r"COPY\s+(?:--\S+\s+)?" + re.escape(src) + r"\s+" + re.escape(dst),
                dockerfile_text,
            ), f"prometheus Dockerfile must COPY {src} to {dst}"

        # (c) no single-file bind-mounts remain for the 3 TD-583 prometheus sites
        volumes = svc.get("volumes") or []
        volume_strs = [str(v) for v in volumes]
        td583_prometheus_mounts = [
            "web.yml.template",
            "prometheus.yml.template",
            "gen-prometheus-config.py",
        ]
        for mount_fragment in td583_prometheus_mounts:
            assert not any(mount_fragment in v for v in volume_strs), (
                f"prometheus-init volumes must NOT bind-mount {mount_fragment} "
                f"(image-bake delivery only); got: {volume_strs}"
            )

    def test_langfuse_clickhouse_baked_via_dockerfile(self, langfuse_config):
        """langfuse-clickhouse must bake retention config via Dockerfile, NOT bind-mount.

        TD-583: the clickhouse-config.xml single-file bind-mount was fragile on
        Docker Desktop / WSL2 (empirically Exited 127 after host reboot). Fix
        bakes it into a local image via docker/langfuse/Dockerfile.
        """
        svc = langfuse_config["services"]["langfuse-clickhouse"]

        # (a) build: block points at the local Dockerfile
        build = svc.get("build")
        assert isinstance(
            build, dict
        ), f"langfuse-clickhouse must declare a build: block; got: {build!r}"
        assert (
            build.get("context") == "./langfuse"
        ), f"langfuse-clickhouse build.context must be './langfuse'; got: {build.get('context')!r}"
        assert (
            build.get("dockerfile") == "Dockerfile"
        ), f"langfuse-clickhouse build.dockerfile must be 'Dockerfile'; got: {build.get('dockerfile')!r}"

        # (b) Dockerfile exists and COPYs retention.xml to expected target path
        dockerfile_path = DOCKER_DIR / "langfuse" / "Dockerfile"
        assert (
            dockerfile_path.exists()
        ), f"docker/langfuse/Dockerfile must exist; not found at {dockerfile_path}"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")
        assert re.search(
            r"COPY\s+(?:--\S+\s+)?clickhouse-config\.xml\s+"
            r"/etc/clickhouse-server/config\.d/retention\.xml",
            dockerfile_text,
        ), (
            "langfuse Dockerfile must COPY clickhouse-config.xml to "
            "/etc/clickhouse-server/config.d/retention.xml"
        )

        # (c) no single-file bind-mount remains for the TD-583 langfuse site
        volumes = svc.get("volumes") or []
        volume_strs = [str(v) for v in volumes]
        assert not any("clickhouse-config.xml" in v for v in volume_strs), (
            "langfuse-clickhouse volumes must NOT bind-mount clickhouse-config.xml "
            f"(image-bake delivery only); got: {volume_strs}"
        )

    def test_no_td583_single_file_bind_mounts(self, source_config, langfuse_config):
        """No TD-583 single-file bind-mounts must remain in either compose file.

        Structural regression guard: if any of the 4 TD-583 sites reappears as
        a host bind-mount in either compose file, this test catches it.
        """
        # Pairs of (compose_service_name, config, fragment_that_must_not_appear)
        checks = [
            (
                "prometheus-init (web.yml)",
                source_config["services"]["prometheus-init"],
                "web.yml.template",
            ),
            (
                "prometheus-init (prometheus.yml)",
                source_config["services"]["prometheus-init"],
                "prometheus.yml.template",
            ),
            (
                "prometheus-init (gen-prometheus-config.py)",
                source_config["services"]["prometheus-init"],
                "gen-prometheus-config.py",
            ),
            (
                "langfuse-clickhouse",
                langfuse_config["services"]["langfuse-clickhouse"],
                "clickhouse-config.xml",
            ),
        ]
        for label, svc, fragment in checks:
            volumes = svc.get("volumes") or []
            volume_strs = [str(v) for v in volumes]
            assert not any(fragment in v for v in volume_strs), (
                f"{label}: TD-583 single-file bind-mount must be removed "
                f"(image-bake delivery); got: {volume_strs}"
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


def _shim_exports(service_block: dict, docker_dir: Path) -> set[str]:
    """Return the set of variable names a TD-582 entrypoint shim re-exports.

    Post-fix-r3 the shim is baked into the service image at build time (no
    longer host-bind-mounted), so discovery now follows the build: context:
    if `<docker_dir>/<build.context>/entrypoint.sh` exists, parse it for
    `export NAME=$OTHER` lines. The LHS names are added to the effective
    container env when the image-baked shim runs as entrypoint.

    For services without a build: block (or without an adjacent entrypoint.sh)
    this returns the empty set — matching the prior helper's pre-shim behavior.
    """
    exports: set[str] = set()
    build = service_block.get("build")
    if not isinstance(build, dict):
        return exports
    context = build.get("context")
    if not context:
        return exports
    shim_path = (docker_dir / context / "entrypoint.sh").resolve()
    if not shim_path.exists():
        return exports
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
    # (c) shim re-exports — discovered via build: context (post-fix-r3 the
    #     shim is image-baked, no longer bind-mounted)
    keys |= _shim_exports(service_block, DOCKER_DIR)
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


# ---------------------------------------------------------------------------
# TD-587 — stack.sh cmd_start image-bake rebuild assertions
# ---------------------------------------------------------------------------


STACK_SH_PATH = REPO_ROOT / "scripts" / "stack.sh"


class TestStackShImageBakeRebuild:
    """Verify stack.sh cmd_start contains an explicit compose build call for
    all image-bake services.

    TD-587: compose up -d does NOT rebuild on source change to Dockerfile or
    COPY'd files when a cached image already exists. The fix adds an explicit
    `compose build --no-cache` before `up -d` so operator edits take effect.
    Regression guard: if the build call is removed or a service is dropped
    from the list, these tests catch it before CI.
    """

    @pytest.fixture(scope="class")
    def stack_sh_text(self):
        return STACK_SH_PATH.read_text(encoding="utf-8")

    def test_stack_sh_has_compose_build_no_cache(self, stack_sh_text):
        """stack.sh must contain a `compose build --no-cache` invocation."""
        assert re.search(
            r"build\s+--no-cache",
            stack_sh_text,
        ), "stack.sh must contain 'build --no-cache' for image-bake services (TD-587)"

    @pytest.mark.parametrize(
        "service",
        ["qdrant", "grafana", "prometheus-init", "langfuse-clickhouse"],
    )
    def test_image_bake_service_in_rebuild_list(self, stack_sh_text, service):
        """Each image-bake service must appear near a compose build call in stack.sh."""
        assert service in stack_sh_text, (
            f"Image-bake service '{service}' must be referenced in stack.sh "
            f"rebuild list (TD-587); missing from script."
        )


# ---------------------------------------------------------------------------
# TD-723 — stack.sh cmd_start python-source CACHED rebuild assertions
# ---------------------------------------------------------------------------

# Python-source baked services rebuilt by stack.sh cmd_start (TD-723).
#
# Two source-delivery classes both require the CACHED rebuild:
#   • baked-src — COPY python source into the image with NO src volume mount, so
#     a source change deploys ONLY via a rebuild: embedding, monitoring-api,
#     github-sync (core); trace-flush-worker (langfuse).
#   • baked-deps, src volume-mounted — COPY requirements.txt + pip-install but
#     volume-mount ../src:/app/src:ro, so src changes deploy via the mount but a
#     requirements.txt change (the PM #353 'No module named openai' class) still
#     needs a rebuild: classifier-worker (core); evaluator-scheduler (langfuse).
#
# Unconditional core members (always built). monitoring-api is gated on
# MONITORING_ENABLED and github-sync on GITHUB_SYNC_ENABLED+GITHUB_TOKEN;
# both are asserted separately by their respective gating tests.
TD723_CORE_SOURCE_SERVICES = ["embedding", "classifier-worker"]
TD723_LANGFUSE_SOURCE_SERVICES = ["evaluator-scheduler", "trace-flush-worker"]


def _source_bake_build_block(text, build_array):
    """Return the `if ! _compose ... build "${build_array[@]}"` invocation text.

    Spans from the nearest `if ! _compose` preceding the build call down to and
    including the `build "${build_array[@]}"` line. Lets tests assert that a
    --profile flag and its build call co-occur in the SAME invocation without
    requiring them on adjacent lines (LOW-5: decoupled from the brittle
    exact-adjacency regex that broke if any flag was inserted between them).
    """
    m = re.search(r'build\s+"\$\{' + re.escape(build_array) + r'\[@\]\}"', text)
    if not m:
        return None
    starts = list(re.finditer(r"if ! _compose", text[: m.start()]))
    if not starts:
        return None
    return text[starts[-1].start() : m.end()]


class TestStackShSourceBakeRebuild:
    """Verify stack.sh cmd_start contains a CACHED compose build for the
    python-source baked services.

    TD-723: embedding, classifier-worker, monitoring-api (conditional on
    MONITORING_ENABLED), and github-sync (conditional on GITHUB_SYNC_ENABLED +
    GITHUB_TOKEN) in core; evaluator-scheduler and trace-flush-worker in langfuse.
    compose caches each service's built image; `compose up -d` reuses the cached
    image even when a baked change shipped, so a release deploys stale silently.
    The fix adds a CACHED `build` (NOT --no-cache, so only changed layers are
    invalidated) before each `up -d --wait`. The rebuild redeploys baked changes
    — baked src for the baked-src services, and baked pip dependencies
    (requirements.txt) for all of them.

    These must be CACHED builds — adding them to the --no-cache IMAGE_BAKE
    arrays would re-bake embedding ONNX models / re-run github-sync's spacy
    download on every restart.
    """

    @pytest.fixture(scope="class")
    def stack_sh_text(self):
        return STACK_SH_PATH.read_text(encoding="utf-8")

    def test_core_source_bake_cached_build_present(self, stack_sh_text):
        """Core python-source services must be built via a CACHED build
        (the build call must NOT carry --no-cache)."""
        assert re.search(
            r'build\s+"\$\{SOURCE_BAKE_SERVICES\[@\]\}"',
            stack_sh_text,
        ), "stack.sh must build SOURCE_BAKE_SERVICES (cached) before core up (TD-723)"
        assert not re.search(
            r'--no-cache\s+"\$\{SOURCE_BAKE_SERVICES\[@\]\}"',
            stack_sh_text,
        ), "core python-source build must be CACHED, not --no-cache (TD-723)"

    def test_langfuse_source_bake_cached_build_present(self, stack_sh_text):
        """Langfuse python-source services must be built via a CACHED build."""
        assert re.search(
            r'build\s+"\$\{SOURCE_BAKE_SERVICES_LANGFUSE\[@\]\}"',
            stack_sh_text,
        ), "stack.sh must build SOURCE_BAKE_SERVICES_LANGFUSE (cached) before langfuse up (TD-723)"
        assert not re.search(
            r'--no-cache\s+"\$\{SOURCE_BAKE_SERVICES_LANGFUSE\[@\]\}"',
            stack_sh_text,
        ), "langfuse python-source build must be CACHED, not --no-cache (TD-723)"

    @pytest.mark.parametrize("service", TD723_CORE_SOURCE_SERVICES)
    def test_core_service_in_source_bake_array(self, stack_sh_text, service):
        """Each unconditional core python-source service must appear in the core
        array initializer (github-sync is gated — see the gating test)."""
        assert re.search(
            r"SOURCE_BAKE_SERVICES=\([^)]*\b" + re.escape(service) + r"\b[^)]*\)",
            stack_sh_text,
        ), f"'{service}' must be in the core SOURCE_BAKE_SERVICES array (TD-723)"

    @pytest.mark.parametrize("service", TD723_LANGFUSE_SOURCE_SERVICES)
    def test_langfuse_service_in_source_bake_array(self, stack_sh_text, service):
        """Each langfuse python-source service must appear in the langfuse array."""
        assert re.search(
            r"SOURCE_BAKE_SERVICES_LANGFUSE=\([^)]*\b"
            + re.escape(service)
            + r"\b[^)]*\)",
            stack_sh_text,
        ), f"'{service}' must be in the SOURCE_BAKE_SERVICES_LANGFUSE array (TD-723)"

    def test_core_build_is_profile_monitoring_aware(self, stack_sh_text):
        """monitoring-api is behind --profile monitoring; the core source build
        must expand _monitoring_source_profile so the flag reaches the build
        when monitoring is enabled. Asserts co-occurrence within the same
        `if ! _compose` block, NOT line-adjacency (LOW-5)."""
        block = _source_bake_build_block(stack_sh_text, "SOURCE_BAKE_SERVICES")
        assert block is not None, "core source-bake build invocation not found (TD-723)"
        assert '"${_monitoring_source_profile[@]}"' in block, (
            'core source build must expand "${_monitoring_source_profile[@]}" so '
            "--profile monitoring reaches the build invocation when monitoring is "
            "enabled (TD-723)"
        )

    def test_monitoring_api_build_conditionally_gated(self, stack_sh_text):
        """monitoring-api is behind --profile monitoring and only started when
        MONITORING_ENABLED != 'false' (default ON, mirrors the `up` gating),
        so the core source build must append monitoring-api (and set
        _monitoring_source_profile) under that SAME condition — not build it
        unconditionally (TD-723)."""
        gates = [
            m.group(1)
            for m in re.finditer(
                r'if \[\[ "\$\{MONITORING_ENABLED\}" != "false" \]\]; then(.*?)\n    fi',
                stack_sh_text,
                re.DOTALL,
            )
            if "SOURCE_BAKE_SERVICES+=" in m.group(1)
        ]
        assert gates, (
            "monitoring-api must be appended to SOURCE_BAKE_SERVICES inside the "
            "MONITORING_ENABLED gate (TD-723)"
        )
        gate = gates[0]
        assert "SOURCE_BAKE_SERVICES+=(monitoring-api)" in gate, (
            "monitoring-api must be appended to the core source-bake set inside "
            "the monitoring gate (TD-723)"
        )
        assert "_monitoring_source_profile=(--profile monitoring)" in gate, (
            "the monitoring gate must set _monitoring_source_profile to "
            "--profile monitoring so monitoring-api is visible to the build (TD-723)"
        )
        # Assert the profile variable is wired into the build invocation
        build_block = _source_bake_build_block(stack_sh_text, "SOURCE_BAKE_SERVICES")
        assert (
            build_block is not None
        ), "core source-bake build invocation not found (TD-723)"
        assert '"${_monitoring_source_profile[@]}"' in build_block, (
            '"${_monitoring_source_profile[@]}" must appear in the core source '
            "build invocation so --profile monitoring is wired in (TD-723)"
        )

    def test_github_sync_build_conditionally_gated(self, stack_sh_text):
        """github-sync is behind --profile github and is only started when
        GITHUB_SYNC_ENABLED=true AND GITHUB_TOKEN is set, so the core source
        build must append github-sync (and --profile github) under that SAME
        condition — not build it unconditionally (TD-723)."""
        gates = [
            m.group(1)
            for m in re.finditer(
                r'if \[\[ "\$\{GITHUB_SYNC_ENABLED\}" == "true" '
                r'&& -n "\$\{GITHUB_TOKEN:-\}" \]\]; then(.*?)\n    fi',
                stack_sh_text,
                re.DOTALL,
            )
            if "SOURCE_BAKE_SERVICES+=" in m.group(1)
        ]
        assert gates, (
            "github-sync must be appended to SOURCE_BAKE_SERVICES inside the "
            "GITHUB_SYNC_ENABLED + GITHUB_TOKEN gate (TD-723)"
        )
        gate = gates[0]
        assert "SOURCE_BAKE_SERVICES+=(github-sync)" in gate, (
            "github-sync must be appended to the core source-bake set inside the "
            "github gate (TD-723)"
        )
        assert "--profile github" in gate, (
            "the github gate must also enable --profile github for the source "
            "build so github-sync is visible (TD-723)"
        )
        # Assert the profile variable expansion is wired into the build invocation
        build_block = _source_bake_build_block(stack_sh_text, "SOURCE_BAKE_SERVICES")
        assert (
            build_block is not None
        ), "core source-bake build invocation not found (TD-723)"
        assert '"${_github_source_profile[@]}"' in build_block, (
            '"${_github_source_profile[@]}" must appear in the core source build '
            "invocation so --profile github is wired in, not just set (TD-723)"
        )

    def test_langfuse_build_is_profile_langfuse_aware(self, stack_sh_text):
        """langfuse services are behind --profile langfuse; the build invocation
        must carry --profile langfuse. Asserts co-occurrence within the same
        `if ! _compose` block, NOT line-adjacency (LOW-5)."""
        block = _source_bake_build_block(stack_sh_text, "SOURCE_BAKE_SERVICES_LANGFUSE")
        assert (
            block is not None
        ), "langfuse source-bake build invocation not found (TD-723)"
        assert (
            "--profile langfuse" in block
        ), "langfuse source build must pass --profile langfuse (TD-723)"


# ---------------------------------------------------------------------------
# BP-162 Layer 2 — built-image parent-dir mode assertions
# ---------------------------------------------------------------------------


class TestTd583DirModes:
    """BP-162: parent dirs of TD-583 COPY --chmod=644 files must be traversable (mode 755).

    Layer 2 of the three-layer test pattern from BP-162 §7.1 — static
    per-image assertions that the built images have correct directory modes.
    Requires Docker daemon; marked integration so they're excluded from the
    fast unit CI job.

    These catch the BuildKit moby/buildkit#5943 propagation defect class:
    COPY --chmod=644 to a new parent dir propagates 644 to the parent, making
    it non-traversable (drw-r--r--) without the BP-162 Pattern A pre-mkdir fix.
    """

    @pytest.mark.integration
    def test_prometheus_init_image_dir_modes(self):
        """Parent dirs created via COPY --chmod=644 must have execute bit."""
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "stat",
                "ai-memory-prometheus-init:3.12-alpine",
                "-c",
                "%a %n",
                "/etc/prometheus",
                "/scripts",
                "/etc/prometheus/web.yml.template",
                "/scripts/gen-prometheus-config.py",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        out = result.stdout
        assert "755 /etc/prometheus" in out, f"BP-162 regression: {out}"
        assert "755 /scripts" in out, f"BP-162 regression: {out}"
        assert "644 /etc/prometheus/web.yml.template" in out
        assert "755 /scripts/gen-prometheus-config.py" in out

    @pytest.mark.integration
    def test_langfuse_clickhouse_image_dir_modes(self):
        """Defensive: parent dir of retention.xml must remain traversable."""
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "stat",
                "ai-memory-langfuse-clickhouse:24",
                "-c",
                "%a %n",
                "/etc/clickhouse-server/config.d",
                "/etc/clickhouse-server/config.d/retention.xml",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        out = result.stdout
        # Accept any mode >= 755 (clickhouse base provides 0777).
        config_d_line = next(
            ln
            for ln in out.splitlines()
            if ln.endswith("/etc/clickhouse-server/config.d")
        )
        config_d_mode = int(config_d_line.split()[0])
        assert config_d_mode >= 755, f"BP-162 regression: {out}"
        assert "644 /etc/clickhouse-server/config.d/retention.xml" in out


# ---------------------------------------------------------------------------
# F-ADV-1 — evaluator-scheduler must carry LANGFUSE_ENABLED
# ---------------------------------------------------------------------------


class TestEvaluatorSchedulerLangfuseEnv:
    """Regression guard: evaluator-scheduler env block must include LANGFUSE_ENABLED.

    F-ADV-1 (PM #361): LANGFUSE_ENABLED was absent from the evaluator-scheduler
    explicit environment: allow-list. Inside the container
    ``os.environ.get("LANGFUSE_ENABLED", "false")`` therefore returned "false",
    so ``is_langfuse_enabled()`` was False and ``_register_langfuse_shutdown()``
    early-returned without registering the bounded TD-698 atexit drain.
    Mirrors the trace-flush-worker pattern (``LANGFUSE_ENABLED=true`` hardcoded
    — both services run exclusively inside the langfuse profile).
    """

    @pytest.fixture(scope="class")
    def langfuse_cfg(self):
        """Parsed docker/docker-compose.langfuse.yml source."""
        with open(DOCKER_COMPOSE_LANGFUSE_PATH) as fh:
            return yaml.safe_load(fh)

    def test_evaluator_scheduler_env_includes_langfuse_enabled(self, langfuse_cfg):
        """evaluator-scheduler environment: block must carry LANGFUSE_ENABLED=true."""
        svc = langfuse_cfg["services"]["evaluator-scheduler"]
        env_keys = _env_block_keys(svc)
        assert "LANGFUSE_ENABLED" in env_keys, (
            "evaluator-scheduler: LANGFUSE_ENABLED missing from environment: allow-list; "
            "os.environ.get('LANGFUSE_ENABLED','false') returns 'false' inside the "
            "container and the bounded atexit drain is never registered (F-ADV-1)"
        )
        # R1: assert value is "true"; LANGFUSE_ENABLED=false would silently
        # re-break the TD-698 bounded atexit drain (F-ADV-1).
        env = svc.get("environment") or []
        if isinstance(env, dict):
            langfuse_val = str(env.get("LANGFUSE_ENABLED", ""))
        else:
            langfuse_val = next(
                (
                    str(item).split("=", 1)[1]
                    for item in env
                    if str(item).startswith("LANGFUSE_ENABLED=")
                ),
                "",
            )
        assert langfuse_val == "true", (
            f"evaluator-scheduler: LANGFUSE_ENABLED={langfuse_val!r}; expected 'true' — "
            "a false value disables the bounded atexit drain registered by "
            "_register_langfuse_shutdown() (TD-698, F-ADV-1)"
        )
