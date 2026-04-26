#!/usr/bin/env python3
"""Merge per-instance CREED.md frontmatter fields from a backup into a freshly-deployed template.

Called by install.sh deploy_parzival_v2() during Option 1 updates to preserve
per-instance sanctum identity state while allowing the CREED body and static
frontmatter fields to update from the new template.

Usage:
    python3 _merge_sanctum_creed_frontmatter.py <backup_creed_path> <target_creed_path>

Modifies target_creed_path in-place. Exits 0 on success, 1 on error.
Requires: Python 3.8+ stdlib only (re, os, sys, pathlib, tempfile).

Per parzival-answers.md DQ-3 (a):
    Fields preserved from backup (per-instance mutating state):
        sessions_completed, last_session, updated, tier_promoted_on
    Fields taken from new template (static identity descriptors):
        type, agent, domain, created-by, load, tier
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

FIELDS_TO_PRESERVE: tuple[str, ...] = (
    "sessions_completed",
    "last_session",
    "updated",
    "tier_promoted_on",
)


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split CREED text into (frontmatter_content, body) or None if no valid frontmatter.

    Returns frontmatter_content as the raw lines between the --- delimiters,
    and body as everything after the closing --- (including the leading newline
    if present).
    """
    if not text.startswith("---\n"):
        return None
    close = text.find("\n---", 4)
    if close == -1:
        return None
    fm = text[4:close]
    body_start = close + 4  # len('\n---') == 4
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    body = text[body_start:]
    return fm, body


def _extract_field(frontmatter: str, field: str) -> str | None:
    """Return the raw value string for a field, or None if not present.

    Value is the verbatim text after 'field: ' — e.g. 'null', '5', '"2026-04-20T10:00:00Z"'.
    """
    m = re.search(rf"^{re.escape(field)}:[ \t]*(.*)$", frontmatter, re.MULTILINE)
    if m:
        return m.group(1)
    return None


def _replace_field(frontmatter: str, field: str, value: str) -> str:
    """Replace the value of field in frontmatter with value, preserving all other content."""
    return re.sub(
        rf"^({re.escape(field)}:[ \t]*).*$",
        lambda m: m.group(1) + value,
        frontmatter,
        flags=re.MULTILINE,
    )


def merge_creed_frontmatter(backup_path: Path, target_path: Path) -> None:
    """Merge preserved fields from backup CREED.md into target CREED.md in-place.

    Preserved fields (FIELDS_TO_PRESERVE) take their values from backup_path.
    All other frontmatter fields and the entire body come from target_path.
    If backup has no frontmatter, or target has no frontmatter, returns without change.
    If a field is missing from backup or from target, that field is skipped.
    Writes atomically via tempfile + os.replace (mirrors merge_settings.py pattern).
    """
    backup_text = backup_path.read_text(encoding="utf-8")
    target_text = target_path.read_text(encoding="utf-8")

    backup_parts = _split_frontmatter(backup_text)
    target_parts = _split_frontmatter(target_text)

    if backup_parts is None or target_parts is None:
        return

    backup_fm, _ = backup_parts
    target_fm, body = target_parts

    merged_fm = target_fm
    for field in FIELDS_TO_PRESERVE:
        value = _extract_field(backup_fm, field)
        if value is None:
            continue
        if _extract_field(target_fm, field) is None:
            continue
        merged_fm = _replace_field(merged_fm, field, value)

    merged_text = "---\n" + merged_fm + "\n---\n" + body

    fd, tmp_path = tempfile.mkstemp(dir=target_path.parent, prefix=".creed_merge_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(merged_text)
        os.replace(tmp_path, target_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <backup_creed_path> <target_creed_path>",
            file=sys.stderr,
        )
        return 1

    backup_path = Path(sys.argv[1])
    target_path = Path(sys.argv[2])

    if not backup_path.is_file():
        print(f"Error: backup path not found: {backup_path}", file=sys.stderr)
        return 1
    if not target_path.is_file():
        print(f"Error: target path not found: {target_path}", file=sys.stderr)
        return 1

    try:
        merge_creed_frontmatter(backup_path, target_path)
    except Exception as e:
        print(f"Error during frontmatter merge: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
