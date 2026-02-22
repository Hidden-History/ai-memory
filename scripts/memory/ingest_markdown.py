#!/usr/bin/env python3
"""Ingest markdown files into BMAD memory conventions collection.

Parses markdown files from a directory, extracts frontmatter metadata,
chunks content using ProseChunker, and stores in the conventions collection.

Usage:
    python scripts/memory/ingest_markdown.py --dir ./docs
    python scripts/memory/ingest_markdown.py --dir ./docs --dry-run
    python scripts/memory/ingest_markdown.py --file ./docs/guide.md

Reference: TECH-DEBT-054, Chunking-Strategy-V1.md
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from memory.chunking import ProseChunker, ProseChunkerConfig
from memory.config import COLLECTION_CONVENTIONS, get_config
from memory.storage import MemoryStorage

logger = logging.getLogger("ai_memory.ingest")

# Frontmatter pattern (YAML between --- markers)
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown content.

    Args:
        content: Full markdown file content

    Returns:
        Tuple of (frontmatter dict, remaining content)
    """
    match = FRONTMATTER_PATTERN.match(content)

    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1))
            remaining = content[match.end() :]
            return frontmatter or {}, remaining
        except yaml.YAMLError as e:
            logger.warning(
                "frontmatter_parse_failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return {}, content

    return {}, content


def extract_title(content: str, frontmatter: dict) -> str:
    """Extract title from frontmatter or first heading.

    Args:
        content: Markdown content (without frontmatter)
        frontmatter: Parsed frontmatter dict

    Returns:
        Document title
    """
    # Try frontmatter first
    if "title" in frontmatter:
        return frontmatter["title"]

    # Look for first H1 heading
    h1_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    return "Untitled"


def ingest_file(
    file_path: Path,
    storage: MemoryStorage,
    chunker: ProseChunker,
    group_id: str,
    dry_run: bool = False,
) -> int:
    """Ingest a single markdown file.

    Args:
        file_path: Path to markdown file
        storage: MemoryStorage instance
        chunker: ProseChunker instance
        group_id: Project group ID
        dry_run: If True, don't actually store

    Returns:
        Number of chunks stored
    """
    logger.info("processing_file", extra={"file_path": str(file_path)})

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        # MED-3: Handle binary files gracefully
        logger.warning(
            "binary_file_skipped",
            extra={
                "file_path": str(file_path),
                "error": str(e),
            },
        )
        return 0
    except Exception as e:
        logger.error(
            "file_read_failed",
            extra={
                "file_path": str(file_path),
                "error": str(e),
            },
        )
        return 0

    # Parse frontmatter
    frontmatter, body = parse_frontmatter(content)
    title = extract_title(body, frontmatter)

    # Extract metadata with type validation (MED-4)
    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    elif isinstance(tags, dict):
        # Convert dict keys to tags
        tags = list(tags.keys())
    elif not isinstance(tags, list):
        logger.warning(
            "invalid_tags_type",
            extra={
                "type": type(tags).__name__,
                "file_path": str(file_path),
            },
        )
        tags = []

    memory_type = frontmatter.get("type", "guideline")
    source = f"file:{file_path}"

    # Chunk content
    chunks = chunker.chunk(
        text=body,
        source=str(file_path),
        metadata={
            "title": title,
            "file_path": str(file_path),
        },
    )

    if not chunks:
        logger.warning("no_chunks_generated", extra={"file_path": str(file_path)})
        return 0

    logger.info(
        "file_parsed",
        extra={
            "title": title,
            "chunk_count": len(chunks),
            "memory_type": memory_type,
            "tags": tags,
            "file_path": str(file_path),
        },
    )

    if dry_run:
        for i, chunk in enumerate(chunks):
            logger.info(
                "dry_run_chunk",
                extra={"chunk_index": i, "size_chars": len(chunk.content)},
            )
        return len(chunks)

    # Store each chunk
    stored = 0
    for i, chunk in enumerate(chunks):
        try:
            # Build chunk-specific content with title context
            chunk_content = f"# {title}\n\n{chunk.content}" if i == 0 else chunk.content

            memory_id = storage.store(
                content=chunk_content,
                group_id=group_id,
                memory_type=memory_type,
                source=f"{source}#chunk-{i}",
                tags=tags,
                collection=COLLECTION_CONVENTIONS,
                metadata={
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "title": title,
                    "file_path": str(file_path),
                },
            )

            logger.debug(
                "chunk_stored", extra={"chunk_index": i, "memory_id": memory_id}
            )
            stored += 1

        except Exception as e:
            logger.error(
                "chunk_store_failed", extra={"chunk_index": i, "error": str(e)}
            )

    return stored


def ingest_directory(
    directory: Path,
    storage: MemoryStorage,
    chunker: ProseChunker,
    group_id: str,
    dry_run: bool = False,
    recursive: bool = True,
) -> tuple[int, int]:
    """Ingest all markdown files from a directory.

    Args:
        directory: Directory to scan
        storage: MemoryStorage instance
        chunker: ProseChunker instance
        group_id: Project group ID
        dry_run: If True, don't actually store
        recursive: If True, scan subdirectories

    Returns:
        Tuple of (files processed, chunks stored)
    """
    pattern = "**/*.md" if recursive else "*.md"
    files = list(directory.glob(pattern))

    logger.info(
        "files_discovered", extra={"count": len(files), "directory": str(directory)}
    )

    total_files = 0
    total_chunks = 0

    for file_path in sorted(files):
        chunks = ingest_file(file_path, storage, chunker, group_id, dry_run)
        if chunks > 0:
            total_files += 1
            total_chunks += chunks

    return total_files, total_chunks


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest markdown files into BMAD memory"
    )
    parser.add_argument("--dir", type=Path, help="Directory containing markdown files")
    parser.add_argument("--file", type=Path, help="Single markdown file to ingest")
    parser.add_argument(
        "--group-id", default="shared", help="Project group ID (default: shared)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without storing"
    )
    parser.add_argument(
        "--no-recursive", action="store_true", help="Don't scan subdirectories"
    )
    parser.add_argument(
        "--max-chunk-size",
        type=int,
        default=500,
        help="Maximum chunk size in characters (default: 500)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    if not args.dir and not args.file:
        logger.error(
            "missing_input", extra={"error": "Either --dir or --file is required"}
        )
        sys.exit(1)

    # Initialize components
    config = get_config()
    storage = MemoryStorage(config)
    chunker = ProseChunker(ProseChunkerConfig(max_chunk_size=args.max_chunk_size))

    logger.info(
        "ingestion_started",
        extra={
            "dry_run": args.dry_run,
            "qdrant_host": config.qdrant_host,
            "qdrant_port": config.qdrant_port,
            "collection": COLLECTION_CONVENTIONS,
            "group_id": args.group_id,
        },
    )

    if args.file:
        if not args.file.exists():
            logger.error("file_not_found", extra={"file_path": str(args.file)})
            sys.exit(1)

        chunks = ingest_file(args.file, storage, chunker, args.group_id, args.dry_run)
        logger.info(
            "ingestion_complete",
            extra={
                "files": 1,
                "chunks": chunks,
                "dry_run": args.dry_run,
            },
        )

    elif args.dir:
        if not args.dir.exists():
            logger.error("directory_not_found", extra={"directory": str(args.dir)})
            sys.exit(1)

        files, chunks = ingest_directory(
            args.dir,
            storage,
            chunker,
            args.group_id,
            args.dry_run,
            recursive=not args.no_recursive,
        )
        logger.info(
            "ingestion_complete",
            extra={
                "files": files,
                "chunks": chunks,
                "dry_run": args.dry_run,
            },
        )

    if args.dry_run:
        logger.info(
            "dry_run_notice",
            extra={"message": "No data was stored. Remove --dry-run to store."},
        )


if __name__ == "__main__":
    main()
