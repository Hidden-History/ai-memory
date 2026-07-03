"""Tests for AI_MEMORY_SOT_* namespace forwarding in
scripts/memory/run-with-env.sh (F-D1-1 fix).

The aim-sot engine reads its walk/discovery budgets (AI_MEMORY_SOT_*) from the
process environment (aim_sot_detect_propose.py / aim_sot_shadow.py) with safe
defaults. Operator/hook scripts run on the HOST and invoke the engine through
run-with-env.sh, which inherits the parent environment but only *exports* the
keys it explicitly forwards. Before F-D1-1 the documented SOT tuning surface in
docker/.env never reached the engine — it was inert (config present but not
delivered).

These tests prove *delivery, not presence*: they run the real script with a stub
interpreter that dumps its environment, and assert that (a) a distinctive
AI_MEMORY_SOT_* value set in docker/.env is exported into the child the engine
runs as, (b) commented example lines are NOT forwarded, and (c) the BUG-314
confused-deputy exclusion holds — AI_MEMORY_PROJECT_ID in docker/.env is never
forwarded.

Hermetic (bash + a stub python, no Qdrant / no external service), so this lives
at the unit level — it must run in the default `pytest tests/` gate (the release
gate ignores tests/integration), else the delivery guard would be absent from
the gates that block a release, which is the exact silent-regression class
F-D1-1 exists to prevent.
"""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "memory" / "run-with-env.sh"


def _run(tmp_path: Path, env_content: str) -> dict:
    """Run run-with-env.sh against a stub install and return the child's environment.

    Builds a fake install dir (docker/.env + an executable .venv/bin/python stub
    that prints ``env``), invokes the real script with AI_MEMORY_INSTALL_DIR
    pointed at it, and parses the dumped child environment into a dict. The child
    env is the exact environment the engine would run under.

    Args:
        tmp_path: pytest tmp_path fixture directory.
        env_content: content written to the fixture docker/.env.

    Returns:
        The child process environment as a {key: value} dict.
    """
    install = tmp_path / "install"
    (install / "docker").mkdir(parents=True)
    (install / ".venv" / "bin").mkdir(parents=True)
    (install / "docker" / ".env").write_text(env_content)

    py_stub = install / ".venv" / "bin" / "python"
    py_stub.write_text("#!/usr/bin/env bash\nenv\n")
    py_stub.chmod(0o755)

    engine = tmp_path / "engine.py"
    engine.write_text("# stub engine\n")

    # Controlled parent env: no AI_MEMORY_PROJECT_ID, so any occurrence in the
    # child must have come from the script forwarding it (it must not).
    result = subprocess.run(
        ["bash", str(SCRIPT), str(engine)],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "AI_MEMORY_INSTALL_DIR": str(install),
        },
    )
    assert (
        result.returncode == 0
    ), f"script exited {result.returncode}; stderr={result.stderr!r}"

    child_env = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            child_env[key] = val
    return child_env


def test_sot_var_is_forwarded(tmp_path):
    """A distinctive AI_MEMORY_SOT_* value in docker/.env reaches the engine's env.

    This is the delivery proof: DISCOVERY_MAX_DIRS=1 is an out-of-band value the
    engine would never default to (default 5000), so its presence in the child
    env proves the value flowed through the gateway rather than a coincidence.
    """
    env = _run(
        tmp_path,
        "QDRANT_API_KEY=k\n"
        "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=1\n"
        "AI_MEMORY_SOT_DIGEST_MAX_FILES=99\n",
    )
    assert env.get("AI_MEMORY_SOT_DISCOVERY_MAX_DIRS") == "1"
    assert env.get("AI_MEMORY_SOT_DIGEST_MAX_FILES") == "99"


def test_commented_sot_line_not_forwarded(tmp_path):
    """A commented-out AI_MEMORY_SOT_* example line is never exported.

    The anchored ^AI_MEMORY_SOT_ prefix must not match a leading '# ' comment, so
    an operator's documented-but-disabled default stays disabled.
    """
    env = _run(
        tmp_path,
        "QDRANT_API_KEY=k\n"
        "# AI_MEMORY_SOT_DISCOVERY_MAX_SECONDS=6.0\n"
        "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=1\n",
    )
    assert "AI_MEMORY_SOT_DISCOVERY_MAX_SECONDS" not in env
    assert env.get("AI_MEMORY_SOT_DISCOVERY_MAX_DIRS") == "1"


def test_project_id_not_forwarded(tmp_path):
    """BUG-314: AI_MEMORY_PROJECT_ID in docker/.env is never forwarded.

    The install-global project id is a *service* default; forwarding it into
    per-workspace operator scripts is the confused-deputy bug. The SOT namespace
    forwarding must not reintroduce it — the prefix does not match it, and the
    dedicated exclusion above stays intact.
    """
    env = _run(
        tmp_path,
        "QDRANT_API_KEY=k\n"
        "AI_MEMORY_PROJECT_ID=should-not-leak\n"
        "AI_MEMORY_SOT_DISCOVERY_MAX_DIRS=1\n",
    )
    assert env.get("AI_MEMORY_PROJECT_ID") != "should-not-leak"
    assert env.get("AI_MEMORY_SOT_DISCOVERY_MAX_DIRS") == "1"
