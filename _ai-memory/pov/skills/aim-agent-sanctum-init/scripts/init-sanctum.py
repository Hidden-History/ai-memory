#!/usr/bin/env python3
"""
First Breath — Deterministic sanctum scaffolding.

This script runs BEFORE the conversational awakening. It creates the sanctum
folder structure, copies template files with config values substituted,
and copies all capability files and their supporting references into the sanctum.

After this script runs, the sanctum is fully self-contained — the agent does
not depend on the skill bundle location for normal operation.

Usage:
    python3 init-sanctum.py <project-root> <skill-path>

    project-root: The root of the project (where _ai-memory/ lives)
    skill-path:   Path to the skill directory (where SKILL.md, references/, assets/ live)
"""

import shutil
import sys
from datetime import date
from pathlib import Path

# --- Agent-specific configuration (set by builder) ---

SKILL_NAME = "parzival"
SANCTUM_DIR = SKILL_NAME

# Files that stay in the skill bundle (only used during First Breath)
SKILL_ONLY_FILES = set()  # Parzival doesn't have a conversational first-breath.md

TEMPLATE_FILES = [
    "CREED-template.md",
    "PERSONA-template.md",
    "INDEX-template.md",
    "BOND-template.md",
    "LORE-template.md",
    "MEMORY-template.md",
    "CAPABILITIES-template.md",
    "PULSE-template.md",
]
# All sanctum files are template-driven. File-level idempotency (per template) ensures
# existing files are never overwritten — owner customizations survive across reruns.

# --- End agent-specific configuration ---


def parse_yaml_config(config_path: Path) -> dict:
    """Simple YAML key-value parser. Handles top-level scalar values only."""
    config = {}
    if not config_path.exists():
        return config
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                value = value.strip().strip("'\"")
                if value:
                    config[key.strip()] = value
    return config


def copy_references(source_dir: Path, dest_dir: Path) -> list[str]:
    """Copy all reference files (except skill-only files) into the sanctum."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []

    if not source_dir.exists():
        return copied

    for source_file in sorted(source_dir.iterdir()):
        if source_file.name in SKILL_ONLY_FILES:
            continue
        if source_file.is_file():
            dest = dest_dir / source_file.name
            if dest.exists():
                print(f"  Preserved {source_file.name} (already exists)")
                continue
            shutil.copy2(source_file, dest)
            copied.append(source_file.name)

    return copied


def copy_scripts(source_dir: Path, dest_dir: Path) -> list[str]:
    """Copy any scripts the capabilities might use into the sanctum."""
    if not source_dir.exists():
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = []

    for source_file in sorted(source_dir.iterdir()):
        if source_file.is_file() and source_file.name != "init-sanctum.py":
            dest = dest_dir / source_file.name
            if dest.exists():
                print(f"  Preserved {source_file.name} (already exists)")
                continue
            shutil.copy2(source_file, dest)
            copied.append(source_file.name)

    return copied


def substitute_vars(content: str, variables: dict) -> str:
    """Replace {var_name} placeholders with values from the variables dict."""
    for key, value in variables.items():
        content = content.replace(f"{{{key}}}", value)
    return content


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 init-sanctum.py <project-root> <skill-path>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    skill_path = Path(sys.argv[2]).resolve()

    # Paths (ai-memory layout)
    ai_memory_dir = project_root / "_ai-memory"
    sanctum_path = ai_memory_dir / "sanctum" / SANCTUM_DIR
    assets_dir = skill_path / "assets"
    references_dir = skill_path / "references"
    scripts_dir = skill_path / "scripts"

    # Sanctum subdirectories
    sanctum_refs = sanctum_path / "references"
    sanctum_scripts = sanctum_path / "scripts"

    print(
        f"Scaffolding sanctum at {sanctum_path} (file-level idempotency: existing files preserved)"
    )

    # Load config
    config = {}
    for config_file in ["core/config.yaml", "pov/config.yaml"]:
        config.update(parse_yaml_config(ai_memory_dir / config_file))

    # Build variable substitution map
    today = date.today().isoformat()
    variables = {
        "agent_id": SKILL_NAME,
        "user_name": config.get(
            "user_name", "Developer"
        ),  # installer-default matches install.sh
        "communication_language": config.get("communication_language", "English"),
        "birth_date": today,
        "project_root": str(project_root),
        "sanctum_path": str(sanctum_path),
    }

    # Create sanctum structure
    sanctum_path.mkdir(parents=True, exist_ok=True)
    (sanctum_path / "capabilities").mkdir(exist_ok=True)
    (sanctum_path / "sessions").mkdir(exist_ok=True)
    print(f"Created sanctum at {sanctum_path}")

    # Copy reference files (capabilities + techniques + guidance) into sanctum
    copied_refs = copy_references(references_dir, sanctum_refs)
    print(f"  Copied {len(copied_refs)} reference files to sanctum/references/")
    for name in copied_refs:
        print(f"    - {name}")

    # Copy any supporting scripts into sanctum
    copied_scripts = copy_scripts(scripts_dir, sanctum_scripts)
    if copied_scripts:
        print(f"  Copied {len(copied_scripts)} scripts to sanctum/scripts/")
        for name in copied_scripts:
            print(f"    - {name}")

    # Copy and substitute template files (file-level idempotency — preserve existing)
    for template_name in TEMPLATE_FILES:
        template_path = assets_dir / template_name
        if not template_path.exists():
            print(f"  Warning: template {template_name} not found, skipping")
            continue

        # Remove "-template" from the output filename and uppercase it
        output_name = template_name.replace("-template", "").upper()
        # Fix extension casing: .MD -> .md
        output_name = output_name[:-3] + ".md"

        output_path = sanctum_path / output_name

        # File-level idempotency — never overwrite existing sanctum files
        if output_path.exists():
            print(f"  Preserved {output_name} (already exists)")
            continue

        content = template_path.read_text()
        content = substitute_vars(content, variables)
        output_path.write_text(content)
        print(f"  Created {output_name}")

    print()
    print("First Breath scaffolding complete.")
    print("The conversational awakening can now begin.")
    print(f"Sanctum: {sanctum_path}")


if __name__ == "__main__":
    main()
