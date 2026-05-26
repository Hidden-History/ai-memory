"""Unit-layer regression test for BUG-287: QDRANT__SERVICE__READ_ONLY_API_KEY compose wiring.

Test 1 (test_compose_wires_read_only_api_key): pure YAML-parse — no Docker dependency,
runs in unit CI tier (no --run-integration required). Asserts the BUG-287 fix is present
and the primary auth key wiring (QDRANT__SERVICE__API_KEY) is not accidentally removed
(regression guard for get_qdrant_client default callers).

TD-582 architecture update: The QDRANT__SERVICE__* keys are no longer set directly in
the qdrant service environment: block via ${VAR} compose interpolation. Instead, an
entrypoint shim (docker/qdrant/entrypoint.sh) translates the canonical QDRANT_API_KEY
and QDRANT_READ_ONLY_API_KEY env vars (delivered via env_file: from .env.secrets) into
Qdrant's QDRANT__SERVICE__* config namespace before exec'ing the upstream CMD. This
test now asserts the shim-based wiring is present.

Relocated from tests/integration/ in BUG-287 fix-r2 (cycle-1 finding H-1): placing a
pure YAML-parse test in the integration directory caused it to be auto-marked integration
and excluded from the fast unit CI job, defeating its cheap-regression-guard purpose.
Live container probes remain in tests/integration/test_qdrant_read_only_wiring.py.

References: BUG-287 (server-side wiring gap), TD-333 (get_qdrant_client read_only
parameter implementation and MemoryConfig field), TD-582 (shim architecture).
"""

from pathlib import Path

import yaml


def _find_repo_root() -> Path:
    """Walk upward from this file to find the repository root.

    Identifies repo root by the presence of pyproject.toml. Survives test
    file relocations — does not assume a fixed directory depth.

    Returns:
        Path to the repository root directory.

    Raises:
        RuntimeError: if no ancestor directory contains pyproject.toml.
    """
    p = Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("repo root not found — no ancestor contains pyproject.toml")


_REPO_ROOT = _find_repo_root()
_COMPOSE_PATH = _REPO_ROOT / "docker" / "docker-compose.yml"
_SHIM_PATH = _REPO_ROOT / "docker" / "qdrant" / "entrypoint.sh"


def test_compose_wires_read_only_api_key() -> None:
    """Verify qdrant API key wiring is present via the TD-582 entrypoint shim.

    Unit-layer test (no Docker dependency, runs in standard unit CI without
    --run-integration).

    TD-582 architecture: QDRANT__SERVICE__* keys are no longer set in the
    environment: block via ${VAR} interpolation. The entrypoint shim
    (docker/qdrant/entrypoint.sh) translates QDRANT_API_KEY and
    QDRANT_READ_ONLY_API_KEY (delivered by env_file: from .env.secrets) into
    Qdrant's QDRANT__SERVICE__* namespace before exec'ing the upstream CMD.

    Asserts:
    - The shim file exists and exports QDRANT__SERVICE__READ_ONLY_API_KEY
      (BUG-287 wiring via shim — get_qdrant_client(read_only=True) callers)
    - The shim file exports QDRANT__SERVICE__API_KEY
      (regression guard for default get_qdrant_client callers)
    - The qdrant service entrypoint references the shim (shim is actually invoked)
    - The qdrant service env_file: delivers .env.secrets (canonical keys available)
    - The qdrant service environment: block does NOT contain the old ${VAR} forms
      (TD-582 regression guard — no re-introduction of compose-side interpolation)

    References: BUG-287 (server-side wiring gap), TD-333 (get_qdrant_client
    read_only parameter), TD-582 (entrypoint shim replaces ${VAR} interpolation).
    """
    assert _COMPOSE_PATH.exists(), f"compose file not found at {_COMPOSE_PATH}"
    assert _SHIM_PATH.exists(), (
        f"qdrant entrypoint shim not found at {_SHIM_PATH}. "
        "TD-582 shim must be present for key translation to work."
    )

    # --- Verify shim content wires both keys ---
    shim_content = _SHIM_PATH.read_text()
    assert "QDRANT__SERVICE__READ_ONLY_API_KEY" in shim_content, (
        "BUG-287 regression: QDRANT__SERVICE__READ_ONLY_API_KEY not found in "
        f"entrypoint shim {_SHIM_PATH}. The read-only key must be translated by "
        "the shim so that get_qdrant_client(read_only=True) callers work end-to-end."
    )
    assert "QDRANT__SERVICE__API_KEY" in shim_content, (
        f"Regression: QDRANT__SERVICE__API_KEY not found in entrypoint shim {_SHIM_PATH}. "
        "Default get_qdrant_client callers would break."
    )

    # --- Verify compose wiring ---
    with _COMPOSE_PATH.open() as fh:
        compose = yaml.safe_load(fh)

    qdrant_service = compose["services"]["qdrant"]

    # Shim must be referenced in entrypoint: (it must actually be invoked)
    entrypoint = qdrant_service.get("entrypoint", [])
    entrypoint_str = (
        " ".join(str(p) for p in entrypoint)
        if isinstance(entrypoint, list)
        else str(entrypoint)
    )
    assert "td582-entrypoint.sh" in entrypoint_str, (
        f"qdrant entrypoint must reference the td582 shim; got: {entrypoint}. "
        "Without the entrypoint override, the shim is never invoked."
    )

    # env_file: must include .env.secrets so canonical keys are delivered to the shim
    env_file_entries = qdrant_service.get("env_file") or []
    env_file_paths = [
        e["path"] if isinstance(e, dict) else str(e) for e in env_file_entries
    ]
    assert any(".env.secrets" in p for p in env_file_paths), (
        f"qdrant env_file: must include .env.secrets; got: {env_file_paths}. "
        "Without .env.secrets, QDRANT_API_KEY and QDRANT_READ_ONLY_API_KEY are "
        "empty strings and the shim produces empty QDRANT__SERVICE__* keys."
    )

    # TD-582 regression guard: old ${VAR} interpolation must NOT be reintroduced
    env_block = qdrant_service.get("environment") or []
    if isinstance(env_block, list):
        env_items = env_block
    else:
        env_items = [f"{k}={v}" for k, v in env_block.items()]
    old_forms = [
        s
        for s in env_items
        if "QDRANT__SERVICE__API_KEY=${" in s
        or "QDRANT__SERVICE__READ_ONLY_API_KEY=${" in s
    ]
    assert not old_forms, (
        "TD-582 regression: old ${VAR} compose interpolation reintroduced for "
        f"QDRANT__SERVICE__* keys: {old_forms}. These must be set by the shim only."
    )
