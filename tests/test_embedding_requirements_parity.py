"""Verify pydantic-settings version parity between main requirements.txt and docker/embedding/requirements.txt.

Source of truth: requirements.txt (main). Embedding image must pin the same version.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MAIN_REQS = REPO_ROOT / "requirements.txt"
EMBEDDING_REQS = REPO_ROOT / "docker" / "embedding" / "requirements.txt"
GITHUB_SYNC_REQS = REPO_ROOT / "docker" / "github-sync" / "requirements.txt"
MONITORING_REQS = REPO_ROOT / "monitoring" / "requirements.txt"
STREAMLIT_REQS = REPO_ROOT / "docker" / "streamlit" / "requirements.txt"

# Fleet of requirement files that must pin pydantic-settings identically.
PYDANTIC_SETTINGS_FLEET = {
    "main": MAIN_REQS,
    "embedding": EMBEDDING_REQS,
    "github-sync": GITHUB_SYNC_REQS,
    "monitoring": MONITORING_REQS,
    "streamlit": STREAMLIT_REQS,
}


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


def test_pydantic_settings_fleet_parity():
    """pydantic-settings must pin identically across the main, embedding, github-sync,
    monitoring, and streamlit requirement files (F-RT-3 regression guard)."""
    main_version = _parse_pinned_version(MAIN_REQS, "pydantic-settings")
    versions = {
        name: _parse_pinned_version(path, "pydantic-settings")
        for name, path in PYDANTIC_SETTINGS_FLEET.items()
    }
    mismatched = {n: v for n, v in versions.items() if v != main_version}
    assert (
        not mismatched
    ), f"pydantic-settings fleet mismatch against main={main_version}: {mismatched}"


def test_main_requirements_pins_click():
    """Main requirements.txt must pin click so the classifier-worker image can
    `import spacy` (spaCy imports click at package load) and load L3 NER —
    regression guard for F-RT-8."""
    pattern = re.compile(r"^click[<>=!~]", re.MULTILINE)
    text = MAIN_REQS.read_text()
    assert pattern.search(
        text
    ), "click pin not found in requirements.txt (F-RT-8 regression)"
