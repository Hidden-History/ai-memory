"""
conservation.py — Conservation helpers for aim-tracking-rotate.

Entry-ID mode (oversight classes):
    build_id_manifest() collects entry-ID tokens across a set of files.
    assert_no_id_loss() asserts every ID present before is present after,
    with equal or greater count (multiset/count-based).

Content-union mode (auto-memory-index class):
    build_content_set() collects all non-empty stripped lines across files
    as a Counter (multiset) so duplicate-line losses are detectable.
    assert_no_content_loss() asserts every content line occurrence before
    is present after.

Both sets of functions are importable with no side effects on import.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

# Entry-ID token pattern: 2-4 uppercase letters, a dash, then alphanumeric+dash
# (e.g. DEC-PM001-D1, BLK-042, RISK-003, TASK-076, TD-655).
ENTRY_ID_RE = re.compile(r"\b([A-Z]{2,4}-[A-Za-z0-9][A-Za-z0-9-]*)\b")


def build_id_manifest(
    paths: Iterable[Path],
    pattern: re.Pattern[str] = ENTRY_ID_RE,
    *,
    raise_on_error: bool = False,
) -> Counter[str]:
    """Return a Counter of entry-ID tokens found across all readable paths.

    With ``raise_on_error=False`` (default), paths that do not exist or cannot
    be decoded are silently skipped so callers can safely include not-yet-created
    archive shards.  Use ``raise_on_error=True`` for BEFORE-baseline reads where
    an unreadable source must never produce a silent false-pass.
    """
    counts: Counter[str] = Counter()
    for p in paths:
        try:
            if p.is_file():
                counts.update(pattern.findall(p.read_text(encoding="utf-8")))
        except OSError:
            if raise_on_error:
                raise
    return counts


def assert_no_id_loss(before: Counter[str], after: Counter[str]) -> None:
    """Assert that no ID count decreased from before to after (multiset check).

    An ID is 'lost' when its after-count is less than its before-count.
    Raises AssertionError listing up to ten lost IDs so the caller can
    surface them in the conservation report.
    """
    lost = sorted(eid for eid, cnt in before.items() if after.get(eid, 0) < cnt)
    if lost:
        sample = ", ".join(lost[:10])
        raise AssertionError(
            f"Conservation FAILED — {len(lost)} entry ID(s) lost. " f"Sample: {sample}"
        )


def build_content_set(
    paths: Iterable[Path],
    *,
    raise_on_error: bool = False,
) -> Counter[str]:
    """Return a Counter of all non-empty stripped lines across all readable paths.

    Used for the auto-memory-index class where conservation is proven by hashing
    the union of MEMORY.md and all sibling memory/*.md files.  A relocation moves
    text from MEMORY.md to a sibling without deleting it, so every line present
    before the fix is still present in the union after.

    The Counter (multiset) representation catches duplicate-line losses that a
    frozenset would miss.  With ``raise_on_error=True``, unreadable paths raise
    instead of being silently skipped (use for BEFORE-baseline reads).
    """
    counts: Counter[str] = Counter()
    for p in paths:
        try:
            if p.is_file():
                for line in p.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped:
                        counts[stripped] += 1
        except OSError:
            if raise_on_error:
                raise
    return counts


def assert_no_content_loss(before: Counter[str], after: Counter[str]) -> None:
    """Assert that every content line occurrence present before is still present after.

    Uses Counter subtraction so a line present N times before must appear at
    least N times after; losing one of two identical lines raises.
    Raises AssertionError with a count of lost occurrences and a short sample.
    """
    lost = before - after  # Counter subtraction: items where before[k] > after[k]
    if lost:
        sample = sorted(lost.keys())[:5]
        raise AssertionError(
            f"Content conservation FAILED — {sum(lost.values())} content line(s) lost. "
            f"Sample: {sample!r}"
        )
