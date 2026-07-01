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
- Replace an existing section in place (idempotent); preserve surrounding content.
"""

import re
from pathlib import Path

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

# Matches an existing `## Project Wiki` block: the heading through to (but not
# including) the next heading of level <=2 (`# ` H1 or `## ` H2), or end-of-file.
# Terminating only at `## ` (as before) swallowed a following `# H1` on replace
# (data-loss); `#{1,2}[ \t]` stops at H1/H2 while leaving deeper `###` subsections
# as part of the regenerated section.
_SECTION_RE = re.compile(
    r"^##[ \t]+Project Wiki[ \t]*$.*?(?=^#{1,2}[ \t]|\Z)",
    re.MULTILINE | re.DOTALL,
)


def upsert_section(text: str) -> str:
    """Return `text` with the Project Wiki section inserted or replaced.

    Existing section → replaced in place (surrounding content preserved).
    No section → appended, separated by a blank line.
    """
    block = POINTER_SECTION.rstrip("\n") + "\n"
    if _SECTION_RE.search(text):
        return _SECTION_RE.sub(lambda _m: block, text, count=1)
    if text and not text.endswith("\n"):
        text += "\n"
    if text.strip():
        text += "\n"
    return text + block


def upsert_pointer(root: Path) -> list[str]:
    """Upsert the pointer into the correct top-level file(s).

    Returns the repo-relative paths that were created or changed (empty when the
    section was already present and identical — the write is a true no-op).
    """
    claude = root / "CLAUDE.md"
    agents = root / "AGENTS.md"
    targets = [p for p in (claude, agents) if p.exists()]
    if not targets:
        targets = [agents]  # neither exists → create AGENTS.md

    changed: list[str] = []
    for path in targets:
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        updated = upsert_section(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(path.relative_to(root).as_posix())
    return changed
