"""
Integration tests for install.sh installer script

Tests cover:
- Platform detection (Linux, macOS, WSL2)
- Prerequisite checks (Docker, Python, ports)
- Port conflict scenarios
- Python version validation
- Error message clarity

Story: 7.1 - Single-Command Installer Script
AC: 7.1.3 (Prerequisites), 7.1.4 (Platform), 7.1.8 (Error Messages)
"""

import json
import os
import subprocess
import pytest
from pathlib import Path


# Fixtures
@pytest.fixture
def installer_script():
    """Path to install.sh"""
    script_path = Path(__file__).parent.parent.parent / "scripts" / "install.sh"
    assert script_path.exists(), f"Installer script not found at {script_path}"
    assert os.access(script_path, os.X_OK), "Installer script is not executable"
    return str(script_path)


@pytest.fixture
def temp_install_dir(tmp_path):
    """Temporary installation directory"""
    install_dir = tmp_path / "bmad-memory-test"
    return str(install_dir)


# Test 1: Script structure and executability
def test_installer_script_exists_and_executable(installer_script):
    """
    AC 7.1.2: Verify installer script structure

    GIVEN the repository is cloned
    WHEN I check for install.sh
    THEN it exists and is executable
    """
    script_path = Path(installer_script)

    # Verify file exists
    assert script_path.exists(), "install.sh does not exist"

    # Verify executable permission
    assert os.access(script_path, os.X_OK), "install.sh is not executable"

    # Verify shebang
    with open(script_path, 'r') as f:
        first_line = f.readline().strip()
        assert first_line == "#!/usr/bin/env bash", f"Invalid shebang: {first_line}"


def test_installer_has_set_flags(installer_script):
    """
    AC 7.1.2: Verify strict error handling with set -euo pipefail

    GIVEN the installer script
    WHEN I read the script content
    THEN it contains 'set -euo pipefail' for 2026 best practices
    """
    with open(installer_script, 'r') as f:
        content = f.read()
        assert 'set -euo pipefail' in content, "Missing strict error handling flags"


# Test 2: Prerequisite checks
def test_docker_check(installer_script, monkeypatch, capsys):
    """
    AC 7.1.3: Verify Docker prerequisite checking

    GIVEN Docker is not installed
    WHEN I run install.sh
    THEN it exits with error and clear message
    """
    # This test verifies the check logic exists
    # Full integration would require Docker to be stopped
    with open(installer_script, 'r') as f:
        content = f.read()
        assert 'command -v docker' in content, "Missing Docker check"
        assert 'docker info' in content, "Missing Docker daemon check"
        assert 'docker compose version' in content, "Missing Docker Compose V2 check"


def test_python_version_check(installer_script):
    """
    AC 7.1.3: Verify Python 3.10+ requirement check

    GIVEN the installer script
    WHEN I examine the Python version check
    THEN it requires Python 3.10+
    """
    with open(installer_script, 'r') as f:
        content = f.read()
        assert 'python3' in content, "Missing Python check"
        assert '(3, 10)' in content, "Missing Python 3.10 version requirement"


def test_port_availability_check_using_lsof(installer_script):
    """
    AC 7.1.3: Verify port conflict detection using lsof (2026 best practice)

    GIVEN the installer script
    WHEN I examine the port checking logic
    THEN it uses lsof for precise port detection
    """
    with open(installer_script, 'r') as f:
        content = f.read()
        assert 'lsof -i' in content, "Missing lsof port check"
        assert 'check_port_available' in content, "Missing port check function"

        # Verify all critical ports are checked
        assert '26350' in content or 'QDRANT_PORT' in content, "Missing Qdrant port check"
        assert '28080' in content or 'EMBEDDING_PORT' in content, "Missing Embedding port check"


# Test 3: Platform detection
def test_platform_detection_logic(installer_script):
    """
    AC 7.1.4: Verify platform detection for Linux, macOS, WSL2

    GIVEN the installer script
    WHEN I examine platform detection logic
    THEN it detects Linux, macOS (Intel/Apple Silicon), and WSL2
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Check for platform detection patterns
        assert 'uname -s' in content, "Missing OS detection"
        assert 'uname -m' in content, "Missing architecture detection"
        assert 'Linux*' in content, "Missing Linux detection"
        assert 'Darwin*' in content, "Missing macOS detection"
        assert 'microsoft' in content or 'WSL' in content, "Missing WSL2 detection"
        assert 'arm64' in content, "Missing Apple Silicon detection"


# Test 4: Error message templates
def test_error_message_templates_exist(installer_script):
    """
    AC 7.1.8: Verify error message templates with NO FALLBACK warnings

    GIVEN the installer script
    WHEN I examine error handling
    THEN clear error message templates exist
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Verify error message functions exist
        assert 'show_docker_not_running_error' in content, "Missing Docker error message"
        assert 'show_port_conflict_error' in content, "Missing port conflict error message"
        assert 'show_disk_space_error' in content, "Missing disk space error message"
        assert 'show_python_version_error' in content, "Missing Python version error message"

        # Verify NO FALLBACK warnings (strict fail-fast principle)
        assert content.count('NO FALLBACK') >= 4, "Missing NO FALLBACK warnings in error messages"


def test_error_messages_are_clear_and_actionable(installer_script):
    """
    FR22: Verify error messages provide clear resolution steps

    GIVEN the installer script error templates
    WHEN I examine error message content
    THEN each provides actionable guidance
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Docker error provides start commands
        assert 'sudo systemctl start docker' in content, "Missing Docker start command"
        assert 'Open Docker Desktop' in content, "Missing Docker Desktop instruction"

        # Port error provides lsof diagnostic
        assert 'lsof -i :' in content, "Missing port diagnostic command"

        # Python error explains why 3.10+ is needed
        assert 'Async support' in content or 'async' in content, "Missing Python async justification"


# Test 5: Configuration and environment
def test_environment_variable_configuration(installer_script):
    """
    AC 7.1.6: Verify environment variable overrides

    GIVEN the installer script
    WHEN I examine configuration handling
    THEN it supports BMAD_* environment variables
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Verify environment variable support
        assert 'BMAD_INSTALL_DIR' in content, "Missing INSTALL_DIR env var"
        assert 'BMAD_QDRANT_PORT' in content, "Missing QDRANT_PORT env var"
        assert 'BMAD_EMBEDDING_PORT' in content, "Missing EMBEDDING_PORT env var"

        # Verify defaults
        assert '26350' in content, "Missing Qdrant default port"
        assert '28080' in content, "Missing Embedding default port"


# Test 6: Security best practices (2026)
def test_security_best_practices_applied(installer_script):
    """
    AC 7.1.7: Verify 2026 security best practices in service startup

    GIVEN the installer script
    WHEN I examine service startup logic
    THEN it references security hardening patterns
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Verify security references
        assert '127.0.0.1' in content, "Missing localhost-only binding reference"
        assert 'service_healthy' in content, "Missing health check reference"
        assert 'security' in content.lower(), "Missing security best practices reference"


# Test 7: Service health checks
def test_service_health_check_logic(installer_script):
    """
    AC 7.1.7: Verify service health check implementation

    GIVEN the installer script
    WHEN I examine wait_for_services logic
    THEN it polls health endpoints with timeout
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Verify health check patterns
        assert 'curl' in content, "Missing curl for health checks"
        assert '/health' in content, "Missing health endpoint"
        assert 'max_attempts' in content or 'timeout' in content, "Missing timeout logic"

        # Verify checks for critical services
        assert 'Qdrant' in content, "Missing Qdrant health check"
        assert 'Embedding' in content, "Missing Embedding health check"


# Test 8: Script main flow
def test_main_orchestration_function(installer_script):
    """
    AC 7.1.2: Verify main() orchestration follows correct order

    GIVEN the installer script
    WHEN I examine main() function
    THEN steps execute in proper sequence
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Find main function
        assert 'main() {' in content or 'main () {' in content, "Missing main() function"

        # Verify key steps in order
        main_section = content[content.find('main'):]

        steps = [
            'check_prerequisites',
            'detect_platform',
            'create_directories',
            'copy_files',
            'configure_environment',
            'start_services',
            'wait_for_services'
        ]

        last_pos = 0
        for step in steps:
            pos = main_section.find(step)
            assert pos > 0, f"Missing step: {step}"
            assert pos > last_pos, f"Step {step} is out of order"
            last_pos = pos


# Test 9: Logging and output
def test_colored_logging_functions(installer_script):
    """
    AC 7.1.2: Verify colored logging functions for clear output

    GIVEN the installer script
    WHEN I examine logging functions
    THEN log_info, log_success, log_warning, log_error exist
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Verify logging functions
        assert 'log_info()' in content, "Missing log_info function"
        assert 'log_success()' in content, "Missing log_success function"
        assert 'log_warning()' in content, "Missing log_warning function"
        assert 'log_error()' in content, "Missing log_error function"

        # Verify color codes
        assert 'RED=' in content, "Missing RED color"
        assert 'GREEN=' in content, "Missing GREEN color"
        assert 'YELLOW=' in content, "Missing YELLOW color"
        assert 'BLUE=' in content, "Missing BLUE color"


# Test 10: Success message
def test_success_message_shows_next_steps(installer_script):
    """
    AC 7.1.1: Verify success message provides next steps

    GIVEN the installer completes successfully
    WHEN success message is shown
    THEN it includes service URLs and next steps
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Verify success message function
        assert 'show_success_message' in content, "Missing success message function"

        # Verify next steps references
        assert 'What happens next' in content or 'Next steps' in content or 'next steps' in content, \
            "Missing next steps guidance"
        assert 'health-check' in content, "Missing health check reference"


# Test 11: File structure validation
def test_file_structure_validation(installer_script):
    """
    AC 7.1.6: Verify script validates source file structure

    GIVEN the installer script
    WHEN it copies files
    THEN it validates expected structure exists
    """
    with open(installer_script, 'r') as f:
        content = f.read()

        # Verify structure validation
        assert 'docker-compose.yml' in content, "Missing docker-compose.yml check"
        assert 'Expected structure' in content or 'Cannot find source files' in content, \
            "Missing file structure validation"


# ==============================================================================
# END-TO-END INSTALLATION TESTS (Story 7.8)
# ==============================================================================
# The tests above verify script structure (static analysis).
# The tests below verify actual installation behavior (E2E).

def test_installer_creates_directories(temp_install_dir):
    """
    AC 7.8.1: Verify installer creates required directories

    GIVEN a clean environment
    WHEN I run ./install.sh
    THEN ~/.bmad-memory structure is created
    """
    result = subprocess.run(
        ["./scripts/install.sh"],
        capture_output=True,
        text=True,
        env={**os.environ, "BMAD_INSTALL_DIR": temp_install_dir}
    )

    assert result.returncode == 0, f"Installer failed: {result.stderr}"

    # Verify directory structure
    assert os.path.exists(os.path.join(temp_install_dir, "src/memory"))
    assert os.path.exists(os.path.join(temp_install_dir, "docker"))
    assert os.path.exists(os.path.join(temp_install_dir, ".claude/hooks/scripts"))
    assert os.path.exists(os.path.join(temp_install_dir, "logs"))
    assert os.path.exists(os.path.join(temp_install_dir, "scripts"))

    # Verify private queue directory
    claude_memory = os.path.expanduser("~/.claude-memory")
    assert os.path.exists(claude_memory)


def test_hooks_configured_in_settings():
    """
    AC 7.8.1: Verify hooks are configured in ~/.claude/settings.json

    GIVEN installation is complete
    WHEN I check ~/.claude/settings.json
    THEN hooks are configured for SessionStart, PostToolUse, Stop
    """
    settings_path = os.path.expanduser("~/.claude/settings.json")

    # Skip if settings.json doesn't exist (install may not have configured it)
    if not os.path.exists(settings_path):
        pytest.skip("~/.claude/settings.json not found (hooks not configured)")

    with open(settings_path) as f:
        settings = json.load(f)

    assert "hooks" in settings, "No 'hooks' section in settings.json"

    hooks = settings["hooks"]
    assert "SessionStart" in hooks, "SessionStart hook not configured"
    assert "PostToolUse" in hooks, "PostToolUse hook not configured"
    assert "Stop" in hooks, "Stop hook not configured"

    # Verify hook scripts exist
    install_dir = os.environ.get("BMAD_INSTALL_DIR", os.path.expanduser("~/.bmad-memory"))
    hooks_dir = os.path.join(install_dir, ".claude/hooks/scripts")

    required_scripts = ["session_start.py", "post_tool_capture.py", "session_stop.py"]
    for script in required_scripts:
        script_path = os.path.join(hooks_dir, script)
        assert os.path.exists(script_path), f"Hook script missing: {script}"
        assert os.access(script_path, os.X_OK), f"Hook script not executable: {script}"


def test_health_check_passes():
    """
    AC 7.8.1: Verify health check passes end-to-end

    GIVEN installation is complete
    WHEN I run health-check.py
    THEN all checks pass
    """
    install_dir = os.environ.get("BMAD_INSTALL_DIR", os.path.expanduser("~/.bmad-memory"))
    health_check_script = os.path.join(install_dir, "scripts/health-check.py")

    if not os.path.exists(health_check_script):
        pytest.skip(f"Health check script not found: {health_check_script}")

    result = subprocess.run(
        ["python3", health_check_script],
        capture_output=True,
        text=True,
        timeout=60
    )

    assert result.returncode == 0, f"Health check failed:\n{result.stdout}\n{result.stderr}"
    assert "All checks passed" in result.stdout or "healthy" in result.stdout.lower()


def test_docker_services_running():
    """
    AC 7.8.1: Verify Docker services are running

    GIVEN installation is complete
    WHEN I check Docker services
    THEN qdrant and embedding containers are running
    """
    install_dir = os.environ.get("BMAD_INSTALL_DIR", os.path.expanduser("~/.bmad-memory"))
    compose_file = os.path.join(install_dir, "docker/docker-compose.yml")

    if not os.path.exists(compose_file):
        pytest.skip(f"docker-compose.yml not found: {compose_file}")

    result = subprocess.run(
        ["docker", "compose", "-f", compose_file, "ps", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=30
    )

    assert result.returncode == 0, f"docker compose ps failed: {result.stderr}"

    # Parse service status
    import json as json_lib
    services_raw = result.stdout.strip()

    # Handle both single JSON object and newline-delimited JSON
    if services_raw.startswith('['):
        services = json_lib.loads(services_raw)
    else:
        services = [json_lib.loads(line) for line in services_raw.split('\n') if line.strip()]

    running_services = {s["Service"] for s in services if s.get("State") == "running"}

    assert "qdrant" in running_services, "Qdrant service not running"
    assert "embedding" in running_services, "Embedding service not running"


def test_qdrant_collections_exist():
    """
    AC 7.8.1: Verify Qdrant collections exist

    GIVEN installation is complete
    WHEN I query Qdrant collections API
    THEN implementations and best_practices collections exist
    """
    import httpx

    qdrant_port = int(os.environ.get("BMAD_QDRANT_PORT", "26350"))

    try:
        response = httpx.get(
            f"http://localhost:{qdrant_port}/collections",
            timeout=10
        )
    except httpx.ConnectError:
        pytest.skip(f"Cannot connect to Qdrant on port {qdrant_port}")

    assert response.status_code == 200, f"Qdrant API error: {response.status_code}"

    data = response.json()
    collections = data.get("result", {}).get("collections", [])
    collection_names = [c["name"] for c in collections]

    assert "code-patterns" in collection_names, "implementations collection not found"
    assert "conventions" in collection_names, "best_practices collection not found"


def test_embedding_service_responds():
    """
    AC 7.8.1: Verify embedding service responds with 768d embeddings

    GIVEN installation is complete
    WHEN I POST to /embed endpoint
    THEN I get 768-dimensional embeddings
    """
    import httpx

    embedding_port = int(os.environ.get("BMAD_EMBEDDING_PORT", "28080"))

    try:
        response = httpx.post(
            f"http://localhost:{embedding_port}/embed",
            json={"texts": ["test embedding generation"]},
            timeout=30
        )
    except httpx.ConnectError:
        pytest.skip(f"Cannot connect to embedding service on port {embedding_port}")

    assert response.status_code == 200, f"Embedding API error: {response.status_code}"

    data = response.json()
    embeddings = data.get("embeddings", [])

    assert len(embeddings) == 1, f"Expected 1 embedding, got {len(embeddings)}"
    assert len(embeddings[0]) == 768, f"Expected 768 dimensions, got {len(embeddings[0])}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
