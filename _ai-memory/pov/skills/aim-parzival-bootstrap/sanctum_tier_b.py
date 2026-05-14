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
