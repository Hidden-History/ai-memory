"""BP-162 §7.1 Layer 3 — prometheus-init runtime init flow regression guard.

Exercises the actual container init flow that broke in PM #311 Phase 1:
prometheus-init started with the prometheus_runtime named volume mounted at
/etc/prometheus/runtime must complete exit 0, not fail with PermissionError
from os.makedirs() stat checks against a non-traversable parent directory.

This is the load-bearing test for the BP-162 regression class. Static image
inspection (Layer 2) passes even when this test would fail, because
`ls -la /etc/prometheus` only needs read permission (mode 644 has it), while
`os.makedirs('/etc/prometheus/runtime', exist_ok=True)` requires execute on
the parent (mode 644 lacks it). Requires Docker daemon; marked integration.
"""

import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.integration
def test_prometheus_init_runs_to_completion_with_named_volume(tmp_path):
    """BP-162 §7.1 Layer 3 + TD-583 regression guard.

    Exercises the actual init flow that broke in PM #311 Phase 1:
    prometheus-init container started with the prometheus_runtime named
    volume mounted at /etc/prometheus/runtime must complete successfully
    (exit 0), not fail with PermissionError from os.makedirs() stat checks
    against a non-traversable parent dir.
    """
    vol_name = f"test-prom-runtime-{uuid.uuid4().hex[:8]}"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PROMETHEUS_ADMIN_PASSWORD=test-pw-bp162\n"
        "QDRANT_API_KEY=test-key-bp162\n"
    )
    subprocess.run(["docker", "volume", "create", vol_name], check=True, capture_output=True)
    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--env-file", str(env_file),
                "-v", f"{vol_name}:/etc/prometheus/runtime",
                "ai-memory-prometheus-init:3.12-alpine",
                "sh", "-c",
                "pip install --no-cache-dir --quiet bcrypt==4.2.1 && "
                "python3 /scripts/gen-prometheus-config.py",
            ],
            capture_output=True, text=True, timeout=180,
        )
        assert result.returncode == 0, (
            f"prometheus-init must exit 0 (BP-162 regression guard).\n"
            f"returncode: {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    finally:
        subprocess.run(["docker", "volume", "rm", "-f", vol_name], capture_output=True)
