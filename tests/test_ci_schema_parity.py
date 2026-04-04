"""CI schema parity test — V4-NEW-1.

Asserts that the collections list in .github/workflows/test.yml matches
the authoritative source of truth in memory.config. Prevents BUG-259-class
drift where the CI E2E init block diverges from COLLECTION_NAMES.
"""

import ast
import re
from pathlib import Path

from memory.config import COLLECTION_JIRA_DATA, COLLECTION_NAMES


def test_test_yml_collections_match_config() -> None:
    """CI E2E init collections must match COLLECTION_NAMES ∪ {COLLECTION_JIRA_DATA}.

    Regression guard for BUG-259: the `collections = [...]` literal inside
    the inline Python block of .github/workflows/test.yml must stay in sync
    with config.py whenever collections are added or removed.
    """
    # BUG-259 regression guard: config.py must still include "github"
    assert "github" in COLLECTION_NAMES, (
        "COLLECTION_NAMES must contain 'github' (BUG-259 regression guard)"
    )

    yml_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "test.yml"

    if not yml_path.exists():
        raise AssertionError(f"test.yml not found at expected path: {yml_path}")

    content = yml_path.read_text(encoding="utf-8")

    match = re.search(r"collections\s*=\s*(\[.*?\])", content)
    if match is None:
        raise AssertionError(
            f"Could not parse 'collections = [...]' literal from {yml_path}. "
            "The E2E init block may have been reformatted or removed."
        )

    yml_collections = set(ast.literal_eval(match.group(1)))
    expected = set(COLLECTION_NAMES) | {COLLECTION_JIRA_DATA}

    assert yml_collections == expected, (
        f"CI/config drift: "
        f"extra in yml={yml_collections - expected}, "
        f"missing in yml={expected - yml_collections}"
    )
