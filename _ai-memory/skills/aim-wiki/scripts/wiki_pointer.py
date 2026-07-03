#!/usr/bin/env python3
"""aim-wiki — CLAUDE.md / AGENTS.md pointer injection.

Deterministic string templating: upsert an AI-memory-branded `## Project Wiki`
reference section into the project's top-level agent-instruction file(s), so any
coding agent is told to consult the wiki. Adapted from OpenWiki prompt.ts:57-78
(concept reuse, MIT — paraphrased, not lifted) with an AI-memory trust-but-verify
line added.

Placement rule (mirrors prompt.ts:57-64):
- Upsert into top-level CLAUDE.md and/or AGENTS.md wherever they already exist.
- If NEITHER exists, create AGENTS.md containing only the section.
- Only ever the top-level files — never nested CLAUDE.md/AGENTS.md.

Ownership / idempotency (BP-171 OQ-3): the pointer is delivered as a managed
marker block delimited by `<!-- BEGIN AI-MEMORY (managed aim-wiki) -->` …
`<!-- END AI-MEMORY (managed aim-wiki) -->`. Idempotency keys on the MARKER
pair, never on the human-readable `## Project Wiki` heading, so a user's own
same-named section is never clobbered. Content outside the markers is preserved
verbatim, except that the UTF-8 text-mode read/write round-trip normalizes line
endings: the universal-newlines read collapses CRLF/lone-CR to `\n`, and the
text-mode write emits `os.linesep`. On this project's POSIX/Linux/WSL deployment
(`os.linesep == "\n"`) that rewrites a CRLF (or lone-CR) source with LF endings on
any real change; on a platform whose `os.linesep` differs, the written ending
follows that platform, not necessarily LF. Writes are backup-copy-first + atomic
(mirrors scripts/merge_settings.py and scripts/merge_agents_md.py).
"""

import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

POINTER_HEADING = "## Project Wiki"

POINTER_SECTION = """\
## Project Wiki

This repository has an AI-maintained wiki in the `wiki/` directory.

Start here:
- [Wiki quickstart](wiki/quickstart.md)

The wiki covers the repository overview, architecture, key workflows, domain
concepts, operations, and testing guidance. Read the quickstart first, then
follow its links to the area you are changing.

Treat the wiki as a starting map, not ground truth: confirm any specific file,
function, or flag against current source before relying on it. It is maintained
with `aim-wiki` — run an update when your changes make a page stale.
"""

# Managed-block markers (BP-171 OQ-3 canonical form). aim-wiki-specific so this
# block never collides with the Codex `<!-- BEGIN AI-MEMORY -->` guidance block
# managed by scripts/merge_agents_md.py in the same AGENTS.md.
BEGIN_MARKER = "<!-- BEGIN AI-MEMORY (managed aim-wiki) -->"
END_MARKER = "<!-- END AI-MEMORY (managed aim-wiki) -->"

# Matches a markerless `## Project Wiki` block: the heading through to (but not
# including) the next heading of level <=2 (`# ` H1 or `## ` H2), or end-of-file.
# `#{1,2}[ \t]` stops at H1/H2 while leaving deeper `###` subsections as part of
# the section. Used ONLY to detect a legacy aim-wiki markerless section eligible
# for one-time migration to the marked form — never to key idempotency.
_SECTION_RE = re.compile(
    r"^##[ \t]+Project Wiki[ \t]*$.*?(?=^#{1,2}[ \t]|\Z)",
    re.MULTILINE | re.DOTALL,
)


class MalformedMarkersError(Exception):
    """Raised by splice_block when the managed markers are in an unsafe state.

    Safe states: (0 BEGIN + 0 END) or (exactly 1 BEGIN strictly before 1 END).
    Any other combination — stray BEGIN or END, END before BEGIN, duplicate
    blocks — is malformed; the caller must warn and leave the file unchanged.
    Mirrors scripts/merge_agents_md.py's MalformedMarkersError contract.
    """


class PointerResult(NamedTuple):
    """Outcome of an upsert_pointer run, split by disposition.

    `changed`: repo-relative paths written (created or updated). `refused`:
    repo-relative paths left untouched because their markers were malformed —
    an actionable failure distinct from a true no-op (both leave `changed`
    empty), so the CLI can signal it separately.
    """

    changed: list[str]
    refused: list[str]


def build_block() -> str:
    """Wrap the pointer section in the stable managed-block markers."""
    return f"{BEGIN_MARKER}\n{POINTER_SECTION.strip()}\n{END_MARKER}"


def _is_legacy_managed_section(section_text: str) -> bool:
    """True if a markerless `## Project Wiki` section is aim-wiki's own output.

    Migration is conservative: only a section whose body matches the current
    POINTER_SECTION template is treated as a legacy aim-wiki block eligible for
    one-time migration to the marked form. A section whose body differs is user
    content and must be preserved.
    """
    return section_text.strip() == POINTER_SECTION.strip()


def splice_block(text: str) -> str:
    """Return `text` with the aim-wiki managed block inserted or replaced.

    Idempotency keys on the marker pair (never on the `## Project Wiki` heading):
    - 1 BEGIN before 1 END → replace-in-place between the markers; bytes outside
      the markers are preserved exactly.
    - 0 BEGIN + 0 END → migrate a legacy markerless aim-wiki section once (only
      when its body matches the template), else append the managed block. A
      user-authored `## Project Wiki` section is left untouched.
    - Any other marker state (stray, duplicate, or out-of-order) → raise
      MalformedMarkersError; the caller warns and leaves the file unchanged.

    The result is idempotent: splicing an already-spliced document reproduces it.

    Raises:
        MalformedMarkersError: markers are present but not in a safe state.
            The caller is responsible for warning and writing nothing.
    """
    block = build_block()
    n_begin = text.count(BEGIN_MARKER)
    n_end = text.count(END_MARKER)

    if n_begin == 1 and n_end == 1:
        begin_idx = text.find(BEGIN_MARKER)
        end_idx = text.find(END_MARKER)
        if end_idx > begin_idx:
            # Replace-in-place: keep bytes before BEGIN and after END untouched.
            # Accepted residual: a document whose ONLY markers are a single
            # balanced BEGIN…END pair (even one wrapping purely user-authored
            # text) is indistinguishable from a stale managed block, so
            # replace-in-place applies. Refusing would break idempotent re-run;
            # the prior content stays backup-recoverable. Do not change this
            # branch to refuse — that would be a regression (mirrors
            # scripts/merge_agents_md.py's replace-in-place caveat).
            pre = text[:begin_idx]
            post = text[end_idx + len(END_MARKER) :]
            return pre + block + post

    if n_begin == 0 and n_end == 0:
        match = _SECTION_RE.search(text)
        if match and _is_legacy_managed_section(match.group(0)):
            # Migrate the legacy markerless section once, in place (no duplicate).
            return _SECTION_RE.sub(lambda _m: block + "\n", text, count=1)
        # Insert-if-absent: append the block, preserving existing content (incl.
        # any user-authored `## Project Wiki` section) verbatim.
        if not text:
            return block + "\n"
        separator = "" if text.endswith("\n") else "\n"
        return text + separator + "\n" + block + "\n"

    # Malformed markers: stray BEGIN or END, END before BEGIN, or duplicates.
    # Refuse (pure; no IO) so the caller can warn, leave the file unchanged, and
    # signal the refusal distinctly. Never risk clobbering user content on an
    # ambiguous marker state.
    raise MalformedMarkersError(
        f"{n_begin} BEGIN marker(s) and {n_end} END marker(s) found "
        f"(expected 0+0 or 1 BEGIN before 1 END)"
    )


def _backup_file(path: Path) -> Path:
    """Create a timestamped copy of an existing file (copy, not rename).

    Mirrors merge_settings.py / merge_agents_md.py: copy first so the original
    survives a crash between backup and write.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.backup.{timestamp}")
    shutil.copy2(path, backup_path)  # copy2 preserves metadata
    return backup_path


def upsert_pointer(root: Path) -> PointerResult:
    """Upsert the pointer into the correct top-level file(s).

    Returns a PointerResult splitting the outcome per file:
    - `changed`: paths created or updated (empty when the managed block is
      already present and identical — a true no-op: no write, no backup).
    - `refused`: paths left untouched because their markers were malformed
      (a WARNING is printed to stderr; no write, no backup) — an actionable
      failure the caller surfaces separately from a no-op.

    On change, writes are backup-copy-first then atomic (tempfile + os.replace)
    so a crash mid-write cannot truncate the user's file.
    """
    claude = root / "CLAUDE.md"
    agents = root / "AGENTS.md"
    targets = [p for p in (claude, agents) if p.exists()]
    if not targets:
        targets = [agents]  # neither exists → create AGENTS.md

    changed: list[str] = []
    refused: list[str] = []
    for path in targets:
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        try:
            updated = splice_block(original)
        except MalformedMarkersError as exc:
            # Refuse: leave the file byte-for-byte unchanged (no write, no
            # backup) and record it as refused so the caller can distinguish it
            # from a true no-op. Keep the stderr WARNING for tty/log visibility.
            print(
                f"WARNING: {path.name}: aim-wiki managed markers are malformed "
                f"({exc}). Pointer left unchanged — resolve the markers "
                f"manually, then re-run.",
                file=sys.stderr,
            )
            refused.append(path.relative_to(root).as_posix())
            continue
        if updated == original:
            continue  # true no-op: no write, no backup
        if path.exists():
            _backup_file(path)  # copy-first; only when content actually changes
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(updated)
            os.replace(temp_path, path)  # atomic
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
        changed.append(path.relative_to(root).as_posix())
    return PointerResult(changed=changed, refused=refused)
