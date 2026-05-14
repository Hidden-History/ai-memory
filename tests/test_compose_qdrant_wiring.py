"""Unit-layer regression test for BUG-287: QDRANT__SERVICE__READ_ONLY_API_KEY compose wiring.

Test 1 (test_compose_wires_read_only_api_key): pure YAML-parse — no Docker dependency,
runs in unit CI tier (no --run-integration required). Asserts the BUG-287 fix is present
and the primary auth key wiring (QDRANT__SERVICE__API_KEY) is not accidentally removed
(regression guard for get_qdrant_client default callers).

Relocated from tests/integration/ in BUG-287 fix-r2 (cycle-1 finding H-1): placing a
pure YAML-parse test in the integration directory caused it to be auto-marked integration
and excluded from the fast unit CI job, defeating its cheap-regression-guard purpose.
Live container probes remain in tests/integration/test_qdrant_read_only_wiring.py.

References: BUG-287 (server-side wiring gap), TD-333 (get_qdrant_client read_only
parameter implementation and MemoryConfig field).
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


_COMPOSE_PATH = _find_repo_root() / "docker" / "docker-compose.yml"


def test_compose_wires_read_only_api_key() -> None:
    """Verify docker-compose.yml qdrant environment block contains read-only key wiring.

    Unit-layer test (no Docker dependency, runs in standard unit CI without
    --run-integration). Relocated from tests/integration/ to fix H-1: the integration
    directory auto-marks all tests as @pytest.mark.integration and is excluded from
    the unit CI job via --ignore=tests/integration.

    Asserts:
    - QDRANT__SERVICE__READ_ONLY_API_KEY is wired (BUG-287 fix present)
    - QDRANT__SERVICE__API_KEY is still wired (regression guard for default callers)

    Uses prefix-matching (.startswith) rather than exact-string equality so that
    future defensive interpolation forms (e.g., :?missing, :-default) do not break
    the assertion while the property (key is wired) is preserved — L-6 fix.

    References: BUG-287 (server-side wiring gap), TD-333 (get_qdrant_client
    read_only parameter and MemoryConfig.qdrant_read_only_api_key field).
    """
    assert _COMPOSE_PATH.exists(), f"compose file not found at {_COMPOSE_PATH}"

    with _COMPOSE_PATH.open() as fh:
        compose = yaml.safe_load(fh)

    env_block = compose["services"]["qdrant"]["environment"]
    assert isinstance(env_block, list), "qdrant environment block must be a list"

    # BUG-287 fix: read-only key must be wired to container
    assert any(
        s.startswith("QDRANT__SERVICE__READ_ONLY_API_KEY=") for s in env_block
    ), (
        "BUG-287 regression: QDRANT__SERVICE__READ_ONLY_API_KEY not found in qdrant "
        "service environment block. The read-only key must be wired so that "
        "get_qdrant_client(read_only=True) callers work end-to-end."
    )

    # Regression guard: primary auth key must still be present (BUG-184 regression guard)
    assert any(s.startswith("QDRANT__SERVICE__API_KEY=") for s in env_block), (
        "Regression: QDRANT__SERVICE__API_KEY was accidentally removed from qdrant "
        "service environment block. Default get_qdrant_client callers would break."
    )
