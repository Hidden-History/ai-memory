"""Contract: WORKFLOW-MAP.md routing table validity.

Every unique {workflows_path}/.../workflow.md entry in WORKFLOW-MAP.md must
resolve to a real file under WORKFLOWS_ROOT.

The routing entries are extracted dynamically — the test count reflects the
actual number of unique entries in the current corpus (21 at time of authoring;
BP-017 §13 cited 16 which predates corpus growth).
"""

import re

import pytest

from .conftest import WORKFLOWS_ROOT

_WORKFLOW_MAP = WORKFLOWS_ROOT / "WORKFLOW-MAP.md"

# Narrow extractor: only lowercase paths (the normal convention).
_ROUTE_RE = re.compile(r"\{workflows_path\}/([a-z][a-z0-9/_\-]*/workflow\.md)")

# Broad extractor: case-insensitive, used only for the cross-check sentinel.
# If a malformed/uppercase entry exists that _ROUTE_RE silently drops,
# the counts will diverge and test_workflow_map_no_dropped_entries will fail.
_ROUTE_RE_BROAD = re.compile(
    r"\{workflows_path\}/([^\s{}/][^\s{}]*/workflow\.md)", re.IGNORECASE
)


def _routing_entries() -> list:
    """Return deduplicated list of relative paths from WORKFLOW-MAP routing entries."""
    text = _WORKFLOW_MAP.read_text(encoding="utf-8")
    seen: set = set()
    entries = []
    for m in _ROUTE_RE.finditer(text):
        rel = m.group(1)
        if rel not in seen:
            seen.add(rel)
            entries.append(rel)
    return entries


def _routing_entries_broad() -> set:
    """Broad (case-insensitive) deduplicated set of workflow.md refs."""
    text = _WORKFLOW_MAP.read_text(encoding="utf-8")
    return {m.group(1).lower() for m in _ROUTE_RE_BROAD.finditer(text)}


@pytest.mark.process
def test_workflow_map_no_dropped_entries():
    """Narrow extractor must not silently drop any workflow.md reference.

    If the narrow _ROUTE_RE misses an entry (e.g. due to uppercase letters or
    an unexpected path format), the broad grep will find a different count and
    this test fails — surfacing the dropped entry rather than hiding it.
    """
    narrow = set(_routing_entries())
    broad = _routing_entries_broad()
    assert narrow == broad, (
        f"_ROUTE_RE dropped {len(broad) - len(narrow)} workflow.md reference(s). "
        f"Entries in WORKFLOW-MAP not captured by narrow regex: {broad - narrow}"
    )


@pytest.mark.process
@pytest.mark.parametrize("rel_path", _routing_entries(), ids=lambda r: r)
def test_workflow_map_entry_resolves(rel_path):
    """WORKFLOW-MAP routing entry must resolve to a real workflow.md."""
    resolved = (WORKFLOWS_ROOT / rel_path).resolve()
    assert resolved.exists(), (
        f"WORKFLOW-MAP entry '{{workflows_path}}/{rel_path}' → "
        f"non-existent: {resolved}"
    )
