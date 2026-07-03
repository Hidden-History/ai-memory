"""Tests for scripts/aim_doctor.py (TD-578).

Covers:
- tier1-compose-profiles: derive-vs-persisted PASS / WARNING (BUG-311 shape) / SKIP
- config-delivery: PASS / WARNING (F-D1-1 shape, real subprocess proof) / SKIP
- main() exit codes: default always 0, --strict flips WARNING to 1
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import stat
import sys
from pathlib import Path

import pytest

# Load scripts/aim_doctor.py by file location — it lives outside any
# importable package (mirrors tests/test_check_version_consistency.py).
REPO_ROOT = Path(__file__).parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "aim_doctor.py"
_spec = importlib.util.spec_from_file_location("aim_doctor", _SCRIPT)
doctor = importlib.util.module_from_spec(_spec)
# Register before exec: aim_doctor.py uses @dataclass, whose decorator looks
# up sys.modules[cls.__module__] — exec_module() would AttributeError without
# this (module_from_spec alone does not register in sys.modules).
sys.modules[_spec.name] = doctor
_spec.loader.exec_module(doctor)


def _write_env(path: Path, **kv: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{k}={v}\n" for k, v in kv.items()), encoding="utf-8")


def _install_skeleton(tmp_path: Path) -> Path:
    install_dir = tmp_path / ".ai-memory"
    (install_dir / "docker").mkdir(parents=True)
    return install_dir


def _link_venv_python(install_dir: Path) -> None:
    py_bin = install_dir / ".venv" / "bin" / "python"
    py_bin.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(sys.executable, py_bin)


def _write_stub_forwarder(install_dir: Path, forwarded_keys: list[str]) -> Path:
    """A minimal run-with-env.sh stand-in that forwards only ``forwarded_keys``
    (read from docker/.env), mirroring run-with-env.sh's load_env_var + exec shape.
    """
    script = install_dir / "scripts" / "memory" / "run-with-env.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    # `|| true` neutralizes grep's non-zero "no match" exit under `set -e`
    # (mirrors the real run-with-env.sh's load_env_var pattern).
    export_lines = "\n".join(
        f'v=$(grep "^{k}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true); '
        f'if [ -n "$v" ]; then export {k}="$v"; fi'
        for k in forwarded_keys
    )
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'INSTALL_DIR="${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}"\n'
        'ENV_FILE="$INSTALL_DIR/docker/.env"\n'
        'PY_BIN="$INSTALL_DIR/.venv/bin/python"\n'
        f"{export_lines}\n"
        'SCRIPT="$1"; shift\n'
        'exec "$PY_BIN" "$SCRIPT" "$@"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _forwarded_keys_from_script(script_path: Path) -> set[str]:
    """Parse ``load_env_var "KEY"`` calls out of a run-with-env.sh-shaped script.

    Used to compute the *actual current* forwarded set from a live copy of the
    script, so a test can assert against ground truth instead of a hardcoded
    verdict that would break the moment the script's forwarding list changes.
    """
    text = script_path.read_text(encoding="utf-8")
    return set(re.findall(r'load_env_var\s+"([A-Z0-9_]+)"', text))


# ---------------------------------------------------------------------------
# Check 1: tier1-compose-profiles (BUG-311 shape)
# ---------------------------------------------------------------------------


def test_tier1_pass_when_profiles_match_derived_state(tmp_path):
    install_dir = _install_skeleton(tmp_path)
    _write_env(
        install_dir / "docker" / ".env",
        MONITORING_ENABLED="true",
        GITHUB_SYNC_ENABLED="true",
        COMPOSE_PROFILES="monitoring,github",
    )
    result = doctor.check_tier1_derived_state(install_dir)
    assert result.status == doctor.Status.PASS


def test_tier1_warning_reproduces_bug311_shape(tmp_path):
    """BUG-311: MONITORING_ENABLED=true but COMPOSE_PROFILES persisted blank."""
    install_dir = _install_skeleton(tmp_path)
    _write_env(
        install_dir / "docker" / ".env",
        MONITORING_ENABLED="true",
        GITHUB_SYNC_ENABLED="false",
        COMPOSE_PROFILES="",
    )
    result = doctor.check_tier1_derived_state(install_dir)
    assert result.status == doctor.Status.WARNING
    assert "monitoring" in result.detail


def test_tier1_skip_when_not_installed(tmp_path):
    install_dir = tmp_path / ".ai-memory"  # docker/.env never created
    result = doctor.check_tier1_derived_state(install_dir)
    assert result.status == doctor.Status.SKIP


def test_tier1_skip_when_no_monitoring_choice(tmp_path):
    install_dir = _install_skeleton(tmp_path)
    _write_env(install_dir / "docker" / ".env", COMPOSE_PROFILES="")
    result = doctor.check_tier1_derived_state(install_dir)
    assert result.status == doctor.Status.SKIP


# ---------------------------------------------------------------------------
# Check 2: config-delivery (F-D1-1 class)
# ---------------------------------------------------------------------------


def test_delivery_pass_when_all_manifest_keys_forwarded(tmp_path):
    install_dir = _install_skeleton(tmp_path)
    _write_env(
        install_dir / "docker" / ".env",
        QDRANT_API_KEY="abc123",
        AI_MEMORY_SOT_DIGEST_MAX_SECONDS="18.0",
    )
    _link_venv_python(install_dir)
    _write_stub_forwarder(install_dir, list(doctor.DELIVERY_MANIFEST))

    result = doctor.check_config_delivery(install_dir)
    assert result.status == doctor.Status.PASS


def test_delivery_warning_reproduces_f_d1_1_shape(tmp_path):
    """F-D1-1: AI_MEMORY_SOT_* documented + configured in .env, but the
    forwarder (stubbed here as it existed pre-Lane-A-fix) only forwards
    QDRANT_API_KEY — the whole SOT surface is silently undelivered.
    """
    install_dir = _install_skeleton(tmp_path)
    _write_env(
        install_dir / "docker" / ".env",
        QDRANT_API_KEY="abc123",
        AI_MEMORY_SOT_DIGEST_MAX_SECONDS="18.0",
    )
    _link_venv_python(install_dir)
    _write_stub_forwarder(install_dir, ["QDRANT_API_KEY"])  # pre-fix shape

    result = doctor.check_config_delivery(install_dir)
    assert result.status == doctor.Status.WARNING
    assert "AI_MEMORY_SOT_DIGEST_MAX_SECONDS" in result.detail
    assert "QDRANT_API_KEY" not in result.detail  # that one WAS delivered


def test_delivery_pass_when_nothing_configured(tmp_path):
    install_dir = _install_skeleton(tmp_path)
    _write_env(install_dir / "docker" / ".env", SOME_OTHER_KEY="x")
    _link_venv_python(install_dir)
    _write_stub_forwarder(install_dir, [])

    result = doctor.check_config_delivery(install_dir)
    assert result.status == doctor.Status.PASS
    assert "nothing to verify" in result.detail


def test_delivery_skip_when_not_installed(tmp_path):
    install_dir = tmp_path / ".ai-memory"
    result = doctor.check_config_delivery(install_dir)
    assert result.status == doctor.Status.SKIP


def test_delivery_skip_when_no_venv(tmp_path):
    install_dir = _install_skeleton(tmp_path)
    _write_env(install_dir / "docker" / ".env", QDRANT_API_KEY="abc123")
    _write_stub_forwarder(install_dir, ["QDRANT_API_KEY"])
    # deliberately no _link_venv_python(install_dir)

    result = doctor.check_config_delivery(install_dir)
    assert result.status == doctor.Status.SKIP
    assert "venv" in result.detail


@pytest.mark.skipif(shutil.which("bash") is None, reason="requires bash")
def test_delivery_against_real_run_with_env_script(tmp_path):
    """Runs the actual scripts/memory/run-with-env.sh from this repo (not a
    stub) to prove the delivery check works against the production forwarder,
    not just a test double.

    State-agnostic by design (E-FIX-2): the expected verdict is derived from
    the live script's own ``load_env_var`` calls, not hardcoded. At the time
    this test was written, PR #256 (which adds AI_MEMORY_SOT_* forwarding) had
    not merged, so this reproduced a live WARNING — but the assertion holds
    either way, so the suite does not break the moment #256 lands.
    """
    install_dir = _install_skeleton(tmp_path)
    real_script = REPO_ROOT / "scripts" / "memory" / "run-with-env.sh"
    dest = install_dir / "scripts" / "memory" / "run-with-env.sh"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_script, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)

    forwarded_today = _forwarded_keys_from_script(dest)
    expected_undelivered = sorted(set(doctor.DELIVERY_MANIFEST) - forwarded_today)

    env_kv = {k: f"bench-value-{i}" for i, k in enumerate(doctor.DELIVERY_MANIFEST)}
    _write_env(install_dir / "docker" / ".env", **env_kv)
    _link_venv_python(install_dir)

    result = doctor.check_config_delivery(install_dir)
    if expected_undelivered:
        assert result.status == doctor.Status.WARNING
        for key in expected_undelivered:
            assert key in result.detail
    else:
        assert result.status == doctor.Status.PASS


def test_delivery_no_false_pass_from_caller_env_leakage(tmp_path, monkeypatch):
    """E-FIX-1 regression: a DELIVERY_MANIFEST key already exported in the
    *caller's* shell (this test process) must not leak into the probe
    subprocess and manufacture a false PASS that masks a genuine forwarding
    failure. Sets the leaked value equal to the configured value — the exact
    shape that would previously have produced a false match.
    """
    install_dir = _install_skeleton(tmp_path)
    _write_env(
        install_dir / "docker" / ".env",
        QDRANT_API_KEY="abc123",
        GITHUB_TOKEN="configured-value",
    )
    _link_venv_python(install_dir)
    # Forwards QDRANT_API_KEY but deliberately NOT GITHUB_TOKEN (pre-fix shape).
    _write_stub_forwarder(install_dir, ["QDRANT_API_KEY"])

    # Simulate an operator's shell already having GITHUB_TOKEN exported (e.g.
    # for `gh` CLI use), with a value that happens to match docker/.env.
    monkeypatch.setenv("GITHUB_TOKEN", "configured-value")

    result = doctor.check_config_delivery(install_dir)
    assert result.status == doctor.Status.WARNING
    assert "GITHUB_TOKEN" in result.detail


# ---------------------------------------------------------------------------
# main() exit codes
# ---------------------------------------------------------------------------


def test_main_default_exit_zero_even_with_warning(tmp_path, capsys):
    install_dir = _install_skeleton(tmp_path)
    _write_env(
        install_dir / "docker" / ".env",
        MONITORING_ENABLED="true",
        COMPOSE_PROFILES="",
    )
    _link_venv_python(install_dir)
    _write_stub_forwarder(install_dir, list(doctor.DELIVERY_MANIFEST))

    rc = doctor.main(["--install-dir", str(install_dir)])
    assert rc == 0
    assert "WARNING" in capsys.readouterr().out


def test_main_strict_exit_nonzero_with_warning(tmp_path, capsys):
    install_dir = _install_skeleton(tmp_path)
    _write_env(
        install_dir / "docker" / ".env",
        MONITORING_ENABLED="true",
        COMPOSE_PROFILES="",
    )
    _link_venv_python(install_dir)
    _write_stub_forwarder(install_dir, list(doctor.DELIVERY_MANIFEST))

    rc = doctor.main(["--install-dir", str(install_dir), "--strict"])
    assert rc == 1


def test_main_strict_exit_zero_when_all_pass(tmp_path):
    install_dir = _install_skeleton(tmp_path)
    _write_env(
        install_dir / "docker" / ".env",
        MONITORING_ENABLED="true",
        COMPOSE_PROFILES="monitoring",
    )
    _link_venv_python(install_dir)
    _write_stub_forwarder(install_dir, list(doctor.DELIVERY_MANIFEST))

    rc = doctor.main(["--install-dir", str(install_dir), "--strict"])
    assert rc == 0
