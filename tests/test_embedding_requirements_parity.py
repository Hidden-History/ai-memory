"""Verify pydantic-settings version parity between main requirements.txt and docker/embedding/requirements.txt.

Source of truth: requirements.txt (main). Embedding image must pin the same version.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MAIN_REQS = REPO_ROOT / "requirements.txt"
EMBEDDING_REQS = REPO_ROOT / "docker" / "embedding" / "requirements.txt"


def _parse_pinned_version(req_file: Path, package: str) -> str:
    """Return the pinned version string for `package` in `req_file`, or raise."""
    pattern = re.compile(rf"^{re.escape(package)}==(.+)$", re.MULTILINE)
    text = req_file.read_text()
    match = pattern.search(text)
    if not match:
        raise AssertionError(f"{package} not found in {req_file}")
    return match.group(1).strip()


def test_pydantic_settings_version_parity():
    """pydantic-settings in docker/embedding/requirements.txt must match main requirements.txt."""
    main_version = _parse_pinned_version(MAIN_REQS, "pydantic-settings")
    embedding_version = _parse_pinned_version(EMBEDDING_REQS, "pydantic-settings")
    assert embedding_version == main_version, (
        f"pydantic-settings version mismatch: "
        f"main={main_version}, embedding={embedding_version}"
    )
