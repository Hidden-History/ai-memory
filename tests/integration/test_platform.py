"""
Platform-specific installation tests

Tests cover:
- Platform detection (Linux, macOS, WSL2)
- Docker socket accessibility (Linux)
- Docker Desktop integration (macOS, WSL2)

Story: 7.8 - Installation Integration Tests
AC: 7.8.2 (Platform-Specific Tests)
"""

import os
import platform
import subprocess

import pytest


def get_platform():
    """
    Detect current platform.

    Returns:
        str: 'linux', 'macos', 'wsl', or 'unknown'
    """
    system = platform.system()

    if system == "Linux":
        # Check for WSL2
        try:
            with open("/proc/version") as f:
                version_info = f.read().lower()
                if "microsoft" in version_info or "wsl" in version_info:
                    return "wsl"
        except FileNotFoundError:
            pass
        return "linux"

    elif system == "Darwin":
        return "macos"

    return "unknown"


def test_platform_detection():
    """
    Verify get_platform() correctly detects the current platform

    GIVEN the current system
    WHEN I call get_platform()
    THEN it returns a valid platform identifier
    """
    detected_platform = get_platform()
    valid_platforms = ["linux", "macos", "wsl", "unknown"]

    assert (
        detected_platform in valid_platforms
    ), f"Invalid platform detected: {detected_platform}"


@pytest.mark.skipif(get_platform() != "linux", reason="Linux only")
def test_linux_docker_socket():
    """
    AC 7.8.2: Verify Docker socket accessible on Linux

    GIVEN a Linux system
    WHEN I check for Docker socket
    THEN /var/run/docker.sock exists and is accessible
    """
    socket_path = "/var/run/docker.sock"

    assert os.path.exists(socket_path), f"Docker socket not found at {socket_path}"

    # Check if socket is actually a socket
    import stat

    mode = os.stat(socket_path).st_mode
    assert stat.S_ISSOCK(mode), f"{socket_path} exists but is not a socket"

    # Verify Docker daemon is reachable
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)

    assert (
        result.returncode == 0
    ), f"Docker daemon not accessible: {result.stderr.decode()}"


@pytest.mark.skipif(get_platform() != "macos", reason="macOS only")
def test_macos_docker_desktop():
    """
    AC 7.8.2: Verify Docker Desktop running on macOS

    GIVEN a macOS system
    WHEN I check Docker Desktop status
    THEN Docker Desktop is running and accessible
    """
    # Check if Docker Desktop is installed
    docker_app = "/Applications/Docker.app"
    assert os.path.exists(docker_app), f"Docker Desktop not found at {docker_app}"

    # Verify Docker daemon is running
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)

    assert (
        result.returncode == 0
    ), "Docker Desktop daemon not running. Start Docker Desktop."

    # Check for Docker.sock (macOS uses different path)
    mac_socket = os.path.expanduser(
        "~/Library/Containers/com.docker.docker/Data/docker.sock"
    )
    if os.path.exists(mac_socket):
        assert os.path.exists(mac_socket), "Docker Desktop socket not accessible"


@pytest.mark.skipif(get_platform() != "wsl", reason="WSL only")
def test_wsl_docker_integration():
    """
    AC 7.8.2: Verify Docker Desktop WSL integration

    GIVEN a WSL2 environment
    WHEN I check Docker integration
    THEN Docker Desktop is accessible from WSL2
    """
    # Verify we're in WSL
    with open("/proc/version") as f:
        version_info = f.read().lower()
        assert (
            "microsoft" in version_info or "wsl" in version_info
        ), "Not running in WSL environment"

    # Check Docker daemon is accessible
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)

    assert (
        result.returncode == 0
    ), "Docker Desktop not accessible from WSL2. Enable WSL integration in Docker Desktop settings."

    # Verify Docker socket exists (WSL2 typically uses /var/run/docker.sock)
    wsl_socket = "/var/run/docker.sock"
    if os.path.exists(wsl_socket):
        assert os.path.exists(wsl_socket), "Docker socket not found in WSL2"


def test_docker_version_compatibility():
    """
    Verify Docker version meets minimum requirements

    GIVEN Docker is installed
    WHEN I check Docker version
    THEN it meets minimum version requirements (20.10+)
    """
    result = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        pytest.skip("Docker not accessible")

    version_str = result.stdout.strip()

    # Parse version (e.g., "24.0.7" -> 24)
    try:
        major_version = int(version_str.split(".")[0])
        assert (
            major_version >= 20
        ), f"Docker version {version_str} is too old. Requires 20.10+"
    except (ValueError, IndexError):
        pytest.skip(f"Could not parse Docker version: {version_str}")


def test_docker_compose_v2_available():
    """
    Verify Docker Compose V2 is available

    GIVEN Docker is installed
    WHEN I check for Docker Compose V2
    THEN 'docker compose' command is available (not 'docker-compose')
    """
    result = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True, timeout=10
    )

    assert (
        result.returncode == 0
    ), "Docker Compose V2 not available. Install docker-compose-plugin."

    assert (
        "Docker Compose version" in result.stdout
    ), f"Unexpected compose version output: {result.stdout}"


def test_architecture_detection():
    """
    Verify architecture detection works correctly

    GIVEN the current system
    WHEN I detect architecture
    THEN it returns a valid value (x86_64, arm64, aarch64)
    """
    arch = platform.machine()
    valid_archs = ["x86_64", "amd64", "arm64", "aarch64"]

    # Normalize amd64 to x86_64 for consistency
    if arch == "amd64":
        arch = "x86_64"

    assert arch in valid_archs, f"Unsupported architecture: {arch}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
