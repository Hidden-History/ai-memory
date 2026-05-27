from pathlib import Path


def load_sanctum_tier_b(sanctum_path: Path) -> str:
    """Read LORE.md + BOND.md from {sanctum_path}/parzival/ and return a prepend string.

    Returns empty string if neither file exists (graceful degradation — sanctum
    may not have run First Breath yet; filesystem absence is valid state).
    Returns partial output if only one of the two exists.

    Per DEC-253-14 (Q3 resolution): filesystem-only source. No Qdrant reads here.
    Per `feedback_sanctum_files_base_templates_only`: file contents are authoritative
    per-instance state; read verbatim.
    """
    output_parts: list[str] = []
    sanctum_dir = sanctum_path / "parzival"
    for label, filename in (("LORE", "LORE.md"), ("BOND", "BOND.md")):
        file_path = sanctum_dir / filename
        try:
            if file_path.exists():
                body = file_path.read_text(encoding="utf-8").strip()
                if body:
                    output_parts.append(f"## Sanctum — {label}\n\n{body}\n")
        except OSError:
            # Filesystem read failure is not a hard error — skip this section silently
            # and let the bootstrap continue with Qdrant retrieval.
            pass
    return "\n".join(output_parts)


def warn_if_workspace_stale(workspace: Path, source_repo: Path) -> None:
    """Warn at session start if workspace is behind source HEAD.

    BP-161 / TD-522: detects workspace-source-of-truth drift. Reads
    {workspace}/.sync-stamp (written by scripts/sync-workspace.sh) and
    compares against the current HEAD of {source_repo}/.git/refs/heads/main.

    Graceful: returns without raising on any missing file or unreadable path.
    Drift surfaces only as a structured logger.warning record — NEVER blocks
    session start.
    """
    import logging

    logger = logging.getLogger(__name__)

    stamp = workspace / ".sync-stamp"
    if not stamp.exists():
        logger.warning(
            "workspace_sync_stamp_missing", extra={"workspace": str(workspace)}
        )
        return

    head_file = source_repo / ".git" / "refs" / "heads" / "main"
    if not head_file.exists():
        # Cannot determine source HEAD (worktree HEAD-detached or unusual layout); skip.
        return

    try:
        current_head = head_file.read_text().strip()
        stamped = stamp.read_text().strip()
    except OSError:
        return

    if stamped != current_head:
        logger.warning(
            "workspace_sync_stale",
            extra={
                "workspace": str(workspace),
                "stamped_head": stamped[:12],
                "source_head": current_head[:12],
            },
        )
