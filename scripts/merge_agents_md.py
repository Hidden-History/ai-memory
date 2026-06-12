#!/usr/bin/env python3
"""Splice the AI-Memory agent-guidance managed block into a project's AGENTS.md.

Codex (unlike Claude/Gemini/Cursor) has no always-on AI-Memory-owned guidance
file: ``AGENTS.override.md`` shadows the user's ``AGENTS.md`` and fallback
filenames apply only when ``AGENTS.md`` is absent. So Codex guidance is delivered
as a managed marker-block inside the project-root ``AGENTS.md`` (BP-172 / BP-171
OQ-3), the one unavoidable managed-block across the 4 supported CLIs.

Behaviour:
  - Insert-if-absent: append the block to an existing or new AGENTS.md.
  - Replace-in-place: if the markers already exist, replace only the region
    between them (the block is owned; everything outside stays byte-for-byte).
  - Backup-copy-first: a timestamped copy of any existing AGENTS.md is made
    before writing (mirrors merge_settings.py — copy, not rename).
  - Atomic write: tempfile + os.replace, so a crash mid-write can't corrupt
    the user's AGENTS.md.

Exit codes:
  0 = Success
  1 = Error (missing arguments, content file not found)
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BEGIN_MARKER = "<!-- BEGIN AI-MEMORY -->"
END_MARKER = "<!-- END AI-MEMORY -->"


def build_block(content: str) -> str:
    """Wrap guidance content in the stable managed-block markers."""
    return f"{BEGIN_MARKER}\n{content.strip()}\n{END_MARKER}"


def splice_block(existing: str, content: str) -> str:
    """Return AGENTS.md text with the AI-Memory block inserted or replaced.

    Everything outside the markers is preserved byte-for-byte. The result is
    idempotent: splicing an already-spliced document reproduces it exactly.
    """
    block = build_block(content)

    begin_idx = existing.find(BEGIN_MARKER)
    end_idx = existing.find(END_MARKER)
    if begin_idx != -1 and end_idx != -1 and end_idx > begin_idx:
        # Replace-in-place: keep bytes before BEGIN and after END untouched.
        pre = existing[:begin_idx]
        post = existing[end_idx + len(END_MARKER) :]
        return pre + block + post

    # Insert-if-absent: append the block, preserving existing content verbatim.
    if not existing:
        return block + "\n"
    separator = "" if existing.endswith("\n") else "\n"
    return existing + separator + "\n" + block + "\n"


def backup_file(path: Path) -> Path:
    """Create a timestamped copy of an existing file (copy, not rename)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.backup.{timestamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def merge_agents_md(agents_path: str, content_path: str) -> None:
    """Splice the guidance block from ``content_path`` into ``agents_path``.

    Side effects:
      - Backs up an existing AGENTS.md (timestamped copy) before writing.
      - Writes the spliced AGENTS.md atomically.
    """
    path = Path(agents_path)
    content = Path(content_path).read_text(encoding="utf-8")

    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    merged = splice_block(existing, content)

    if merged == existing:
        print(f"AGENTS.md already up to date: {agents_path}")
        return

    if path.exists():
        backup_path = backup_file(path)
        print(f"Backed up existing AGENTS.md to {backup_path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=".AGENTS_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(merged)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise

    print(f"Updated {agents_path}")


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: merge_agents_md.py <agents_md_path> <content_path>")
        sys.exit(1)
    agents_path = sys.argv[1]
    content_path = sys.argv[2]
    if not Path(content_path).is_file():
        print(f"ERROR: content file not found: {content_path}")
        sys.exit(1)
    merge_agents_md(agents_path, content_path)


if __name__ == "__main__":
    main()
