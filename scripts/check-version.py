#!/usr/bin/env python3
# scripts/check-version.py
"""Check for available AI Memory Module updates.

2026 Best Practices Applied:
- httpx with proper timeout handling (Source: HTTPX Timeout Docs)
- Retry logic with exponential backoff (Source: httpx patterns Dec 2025)
- Graceful degradation (no crash on network errors)
- Clear user messaging
- Semantic version comparison with pre-release support
"""

import os
import sys
import time
from pathlib import Path

import httpx

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.__version__ import __version__

# Configuration via environment variables
GITHUB_OWNER = os.environ.get("AI_MEMORY_GITHUB_OWNER", "bmad-sim")
GITHUB_REPO = os.environ.get("AI_MEMORY_GITHUB_REPO", "ai-memory-module")
MAX_RETRIES = int(os.environ.get("AI_MEMORY_VERSION_CHECK_RETRIES", "3"))


def get_latest_version() -> str | None:
    """Fetch latest version from GitHub releases with retry logic.

    2026 Best Practices:
    - Use httpx.Timeout() for granular timeout control
    - Retry with exponential backoff for transient failures
    Source: https://www.python-httpx.org/advanced/timeouts/

    Returns:
        Latest version string (e.g., "1.0.1") or None if unavailable.
    """
    # GitHub API endpoint for latest release (configurable via env vars)
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

    # 2026 Best Practice: Explicit timeout with connect/read separation
    timeout = httpx.Timeout(
        connect=5.0,  # 5 seconds to establish connection
        read=10.0,  # 10 seconds to read response
        write=5.0,  # 5 seconds to send request
        pool=5.0,  # 5 seconds to acquire connection from pool
    )

    # 2026 Best Practice: Retry with exponential backoff
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = httpx.get(
                url,
                timeout=timeout,
                headers={"Accept": "application/vnd.github+json"},
                follow_redirects=True,
            )

            response.raise_for_status()

            # Extract version from tag (strip 'v' prefix if present)
            tag_name = response.json()["tag_name"]
            return tag_name.lstrip("v")

        except httpx.TimeoutException:
            last_error = "Timeout checking for updates (network slow or offline)"
            # Exponential backoff: 1s, 2s, 4s
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
        except httpx.HTTPStatusError as e:
            # Don't retry 4xx errors (client errors)
            if 400 <= e.response.status_code < 500:
                print(
                    f"⚠️  HTTP error checking for updates: {e.response.status_code}",
                    file=sys.stderr,
                )
                return None
            last_error = f"HTTP error: {e.response.status_code}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
        except httpx.RequestError as e:
            last_error = f"Network error: {e}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
        except (KeyError, ValueError) as e:
            print(f"⚠️  Unexpected API response format: {e}", file=sys.stderr)
            return None

    # All retries exhausted
    if last_error:
        print(f"⚠️  {last_error} (after {MAX_RETRIES} attempts)", file=sys.stderr)
    return None


def parse_version(version: str) -> list:
    """Parse version string into comparable parts.

    Handles PEP 440 versions including pre-releases (1.0.0a1, 1.0.0.dev1).

    Args:
        version: Version string (e.g., "1.0.0", "1.0.0a1", "2.0.0-beta")

    Returns:
        List of version parts for comparison.
    """
    # Strip common pre-release separators
    version = version.replace("-", ".").replace("_", ".")

    parts = []
    current_num = ""

    for char in version:
        if char.isdigit():
            current_num += char
        elif char == ".":
            if current_num:
                parts.append(int(current_num))
                current_num = ""
        else:
            # Hit a letter (pre-release indicator)
            if current_num:
                parts.append(int(current_num))
                current_num = ""
            # Pre-release versions sort before release (append -1 marker)
            # e.g., 1.0.0a1 < 1.0.0
            parts.append(-1)
            break

    if current_num:
        parts.append(int(current_num))

    return parts


def compare_versions(current: str, latest: str) -> int:
    """Compare two semantic version strings.

    Supports PEP 440 versions including pre-releases.

    Args:
        current: Current version (e.g., "1.0.0", "1.0.0a1")
        latest: Latest version (e.g., "1.0.1", "2.0.0-beta")

    Returns:
        -1 if current < latest (update available)
         0 if current == latest (up to date)
         1 if current > latest (ahead of release)
    """
    current_parts = parse_version(current)
    latest_parts = parse_version(latest)

    # Pad with zeros if needed (for numeric parts only)
    max_len = max(len(current_parts), len(latest_parts))
    while len(current_parts) < max_len:
        current_parts.append(0)
    while len(latest_parts) < max_len:
        latest_parts.append(0)

    if current_parts < latest_parts:
        return -1
    elif current_parts > latest_parts:
        return 1
    else:
        return 0


def main() -> None:
    """Check for updates and display status."""
    print("\n" + "=" * 50)
    print("  AI Memory Module Version Check")
    print("=" * 50 + "\n")

    print(f"  Current version: {__version__}")

    print("\n  Checking for updates...", end="", flush=True)
    latest = get_latest_version()
    print(" done\n")

    if latest is None:
        print("  ⚠️  Could not check for updates (see above)")
        print("\n" + "=" * 50 + "\n")
        sys.exit(1)

    print(f"  Latest version:  {latest}")

    comparison = compare_versions(__version__, latest)

    if comparison < 0:
        print(f"\n  📦 Update available: {__version__} → {latest}")
        print("\n  To update:")
        print("    cd /path/to/ai-memory-module")
        print("    ./update.sh")
    elif comparison == 0:
        print(f"\n  ✅ You have the latest version ({__version__})")
    else:
        print(f"\n  ℹ️  You're ahead of the latest release ({__version__} > {latest})")
        print("     This usually means you're on a development branch")

    print("\n" + "=" * 50 + "\n")

    sys.exit(0 if comparison >= 0 else 1)


if __name__ == "__main__":
    main()
