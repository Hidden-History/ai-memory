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
  - Refuse-and-warn: if the markers are in any other state (stray BEGIN or END,
    END before BEGIN, duplicate blocks), the file is left byte-for-byte unchanged
    and a WARNING is printed to stderr. The install is not aborted.
  - Backup-copy-first: a timestamped copy of any existing AGENTS.md is made
    before writing (mirrors merge_settings.py — copy, not rename).
  - Atomic write: tempfile + os.replace, so a crash mid-write can't corrupt
    the user's AGENTS.md.

Exit codes:
  0 = Success (wrote or already up-to-date)
  1 = Error (missing arguments, content file not found)
  2 = Malformed markers (refused — WARNING printed to stderr; install continues)
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BEGIN_MARKER = "<!-- BEGIN AI-MEMORY -->"
END_MARKER = "<!-- END AI-MEMORY -->"


class MalformedMarkersError(Exception):
    """Raised by splice_block when markers are in an unrecognised state.

    Safe states: (0 BEGIN + 0 END) or (exactly 1 BEGIN strictly before 1 END).
    Any other combination is malformed; the caller must warn and leave the file
    unchanged.
    """


def build_block(content: str) -> str:
    """Wrap guidance content in the stable managed-block markers."""
    return f"{BEGIN_MARKER}\n{content.strip()}\n{END_MARKER}"


def splice_block(existing: str, content: str) -> str:
    """Return AGENTS.md text with the AI-Memory block inserted or replaced.

    Routing (count-based, no naive find assumptions):
    - 0 BEGIN + 0 END  →  insert-if-absent (append).
    - 1 BEGIN + 1 END, BEGIN strictly before END  →  replace-in-place.
    - Any other marker state  →  raise MalformedMarkersError (pure; no IO).

    Everything outside the markers is preserved byte-for-byte. The result is
    idempotent: splicing an already-spliced document reproduces it exactly.

    Raises:
        MalformedMarkersError: markers are present but not in a safe state
            (stray BEGIN or END, END before BEGIN, duplicate blocks, etc.).
            The caller is responsible for warning and leaving the file unchanged.
    """
    block = build_block(content)

    n_begin = existing.count(BEGIN_MARKER)
    n_end = existing.count(END_MARKER)

    if n_begin == 0 and n_end == 0:
        # Insert-if-absent: append the block, preserving existing content verbatim.
        if not existing:
            return block + "\n"
        separator = "" if existing.endswith("\n") else "\n"
        return existing + separator + "\n" + block + "\n"

    if n_begin == 1 and n_end == 1:
        begin_idx = existing.find(BEGIN_MARKER)
        end_idx = existing.find(END_MARKER)
        if end_idx > begin_idx:
            # Replace-in-place: keep bytes before BEGIN and after END untouched.
            # Accepted residual: a file whose ONLY markers are a single balanced
            # BEGIN…END pair (even wrapping purely user-authored text) is
            # indistinguishable from a stale managed block, so replace-in-place
            # applies. Refusing would break idempotent re-install. The original
            # content is backup-recoverable if a real unintended replacement occurs.
            # Do not change this branch to refuse — that would be a regression.
            pre = existing[:begin_idx]
            post = existing[end_idx + len(END_MARKER) :]
            return pre + block + post

    # Any other marker state: stray BEGIN or END, END before BEGIN, duplicates.
    raise MalformedMarkersError(
        f"{n_begin} BEGIN marker(s) and {n_end} END marker(s) found "
        f"(expected 0+0 or 1 BEGIN before 1 END)"
    )


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

    Raises:
        MalformedMarkersError: if markers are in an unrecognised state.
            A WARNING is printed to stderr; the file is left unchanged; the
            caller (main) exits 2 so the install continues without aborting.
    """
    path = Path(agents_path)
    content = Path(content_path).read_text(encoding="utf-8")

    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        merged = splice_block(existing, content)
    except MalformedMarkersError as exc:
        print(
            f"WARNING: {agents_path}: {exc}. "
            f"Resolve the AI-Memory markers manually, then re-run the installer. "
            f"File left unchanged.",
            file=sys.stderr,
        )
        raise

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
    try:
        merge_agents_md(agents_path, content_path)
    except MalformedMarkersError:
        sys.exit(2)


if __name__ == "__main__":
    main()
