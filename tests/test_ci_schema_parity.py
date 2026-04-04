"""CI schema parity test -- V4-NEW-1.

Asserts that the collections list in .github/workflows/test.yml matches
the authoritative source of truth in memory.config. Prevents BUG-259-class
drift where the CI E2E init block diverges from COLLECTION_NAMES.
"""

import ast
import re
from pathlib import Path

from memory.config import COLLECTION_JIRA_DATA, COLLECTION_NAMES


def test_ci_yml_collections_match_config() -> None:
    """CI E2E init collections must equal COLLECTION_NAMES union {COLLECTION_JIRA_DATA}.

    Regression guard for BUG-259: the `collections = [...]` literal inside
    the inline Python block of .github/workflows/test.yml must stay in sync
    with config.py whenever collections are added or removed.
    """
    yml_path = (
        Path(__file__).resolve().parent.parent / ".github" / "workflows" / "test.yml"
    )

    if not yml_path.exists():
        raise AssertionError(f"test.yml not found at expected path: {yml_path}")

    content = yml_path.read_text(encoding="utf-8")

    # Anchor search to the E2E init heredoc block to avoid matching
    # unrelated `collections = [...]` assignments elsewhere in the workflow.
    heredoc_match = re.search(
        r"<<[-]?\s*['\"]?INIT_COLLECTIONS['\"]?\n(.*?)^\s*INIT_COLLECTIONS\s*$",
        content,
        re.DOTALL | re.MULTILINE,
    )
    if heredoc_match is None:
        raise AssertionError(
            f"Could not locate INIT_COLLECTIONS heredoc in {yml_path}. "
            "The E2E init step may have been restructured."
        )

    heredoc_body = heredoc_match.group(1)

    # Find ALL `collections = [...]` literals in the heredoc -- must be exactly one.
    # Use a character-class pattern that tolerates multiline lists: anything
    # except brackets inside the outer brackets.
    list_matches = re.findall(
        r"(?<!\w)collections\s*=\s*(\[[^\[\]]*\])",
        heredoc_body,
    )
    if len(list_matches) != 1:
        raise AssertionError(
            f"Expected exactly 1 `collections = [...]` assignment in the "
            f"INIT_COLLECTIONS heredoc of {yml_path}, found {len(list_matches)}."
        )

    parsed_yml = ast.literal_eval(list_matches[0])
    if len(parsed_yml) != len(set(parsed_yml)):
        raise AssertionError(
            f"Duplicate entries in yml collections list: {parsed_yml}. "
            "Each collection name must appear exactly once in "
            f"{yml_path} (collections = [...] in the INIT_COLLECTIONS heredoc)."
        )
    yml_collections = set(parsed_yml)
    expected = set(COLLECTION_NAMES) | {COLLECTION_JIRA_DATA}

    assert yml_collections == expected, (
        f"CI/config drift detected between two files:\n"
        f"  source of truth: src/memory/config.py "
        f"(COLLECTION_NAMES + COLLECTION_JIRA_DATA)\n"
        f"  CI init block:   {yml_path}\n"
        f"  extra in yml:    {yml_collections - expected}\n"
        f"  missing in yml:  {expected - yml_collections}\n"
        f"Update both files to match, then re-run this test."
    )
