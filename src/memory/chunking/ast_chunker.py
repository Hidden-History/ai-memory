"""AST-based code chunking using Tree-sitter.

TECH-DEBT-052: Implements code chunking per Chunking-Strategy-V1.md Section 2.1.
"""

from dataclasses import dataclass
from typing import List, Optional, Set
from pathlib import Path
import logging

try:
    from tree_sitter import Language, Parser, Node
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    # Define dummy types for type hints when tree-sitter unavailable
    Language = None  # type: ignore
    Parser = None  # type: ignore
    Node = None  # type: ignore

# Use existing models from chunking module
from . import ChunkResult, ChunkMetadata, CHARS_PER_TOKEN

logger = logging.getLogger("ai_memory.chunking.ast")


class ASTChunker:
    """AST-based code chunker using Tree-sitter.

    Chunks code at syntactic boundaries (functions, classes, methods).
    Preserves context by including imports and class signatures.
    """

    # Spec constants from Chunking-Strategy-V1.md Section 2.1
    MAX_CHARS = 500  # Non-whitespace characters
    OVERLAP_PCT = 0.20  # 20% for code
    MIN_OVERLAP_CHARS = 50

    # Supported languages (per Chunking-Strategy-V1.md Section 2.1)
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
    }

    # Node types that represent chunk boundaries
    CHUNK_NODE_TYPES = {
        "python": {"function_definition", "class_definition"},
        "javascript": {"function_declaration", "class_declaration", "method_definition", "arrow_function"},
        "typescript": {"function_declaration", "class_declaration", "method_definition", "arrow_function"},
        "go": {"function_declaration", "method_declaration", "type_declaration"},
        "rust": {"function_item", "impl_item", "struct_item", "enum_item", "trait_item"},
    }

    # Node types for context extraction
    IMPORT_NODE_TYPES = {
        "python": {"import_statement", "import_from_statement"},
        "javascript": {"import_statement"},
        "typescript": {"import_statement"},
        "go": {"import_declaration", "import_spec"},
        "rust": {"use_declaration"},
    }

    def __init__(self):
        """Initialize AST chunker.

        Raises:
            ImportError: If tree-sitter is not installed
        """
        if not TREE_SITTER_AVAILABLE:
            raise ImportError(
                "tree-sitter not installed. Run: pip install tree-sitter tree-sitter-python"
            )

        self._parsers = {}
        self._languages = {}
        logger.info("ast_chunker_initialized")

    def _get_parser(self, language: str) -> Optional[Parser]:
        """Get or create parser for language.

        Args:
            language: Language name (python, javascript, typescript, go, rust)

        Returns:
            Parser instance or None if language not supported
        """
        if language in self._parsers:
            return self._parsers[language]

        try:
            # Import language-specific module
            if language == "python":
                from tree_sitter_python import language as py_lang
                lang = Language(py_lang())
            elif language == "javascript":
                from tree_sitter_javascript import language as js_lang
                lang = Language(js_lang())
            elif language == "typescript":
                from tree_sitter_typescript import language_typescript as ts_lang
                lang = Language(ts_lang())
            elif language == "go":
                from tree_sitter_go import language as go_lang
                lang = Language(go_lang())
            elif language == "rust":
                from tree_sitter_rust import language as rust_lang
                lang = Language(rust_lang())
            else:
                logger.warning("unsupported_language", extra={"language": language})
                return None

            # FIX-7: Use correct Parser API (tree-sitter 0.21+ compatible)
            parser = Parser()
            parser.language = lang
            self._parsers[language] = parser
            self._languages[language] = lang

            logger.debug("parser_created", extra={"language": language})
            return parser

        except Exception as e:
            logger.error(
                "parser_creation_failed",
                extra={"language": language, "error": str(e)},
            )
            return None

    def chunk(self, content: str, file_path: str) -> List[ChunkResult]:
        """Chunk code content using AST parsing.

        Args:
            content: Code content to chunk
            file_path: Source file path (for language detection)

        Returns:
            List of ChunkResult objects, or whole-content fallback if parsing fails
        """
        # Detect language from file extension
        ext = Path(file_path).suffix.lower()
        language = self.LANGUAGE_MAP.get(ext)

        if not language:
            logger.debug(
                "unsupported_file_extension",
                extra={"file_path": file_path, "extension": ext},
            )
            return self._fallback_whole_content(content, file_path)

        # Get parser for language
        parser = self._get_parser(language)
        if not parser:
            logger.warning(
                "parser_unavailable",
                extra={"file_path": file_path, "language": language},
            )
            return self._fallback_whole_content(content, file_path)

        # Parse content
        try:
            tree = parser.parse(bytes(content, "utf8"))
            root_node = tree.root_node

            if root_node.has_error:
                logger.warning(
                    "parse_error_in_ast",
                    extra={"file_path": file_path, "language": language},
                )
                return self._fallback_whole_content(content, file_path)

        except Exception as e:
            logger.error(
                "parsing_failed",
                extra={"file_path": file_path, "error": str(e)},
            )
            return self._fallback_whole_content(content, file_path)

        # Extract chunks from AST
        try:
            chunks = self._extract_chunks(
                content=content,
                root_node=root_node,
                language=language,
                file_path=file_path,
            )

            if not chunks:
                logger.debug(
                    "no_chunks_extracted",
                    extra={"file_path": file_path},
                )
                return self._fallback_whole_content(content, file_path)

            logger.info(
                "ast_chunking_complete",
                extra={
                    "file_path": file_path,
                    "language": language,
                    "chunk_count": len(chunks),
                },
            )
            return chunks

        except Exception as e:
            logger.error(
                "chunk_extraction_failed",
                extra={"file_path": file_path, "error": str(e)},
            )
            return self._fallback_whole_content(content, file_path)

    def _extract_chunks(
        self,
        content: str,
        root_node: "Node",
        language: str,
        file_path: str,
    ) -> List[ChunkResult]:
        """Extract chunks from parsed AST.

        Args:
            content: Source code content
            root_node: Root node of AST
            language: Language name
            file_path: Source file path

        Returns:
            List of ChunkResult objects
        """
        # Get chunk boundaries (functions, classes, methods)
        chunk_nodes = self._find_chunk_nodes(root_node, language)

        if not chunk_nodes:
            # File has no functions/classes - return whole content
            return []

        # Extract imports for context
        import_nodes = self._find_import_nodes(root_node, language)
        import_text = self._extract_node_text(content, import_nodes)

        # Build chunks with context and overlap
        chunks = []
        previous_chunk_tail = ""  # Store end of previous chunk for overlap

        for idx, node in enumerate(chunk_nodes):
            # Extract node content
            node_text = self._get_node_text(content, node)

            # Calculate non-whitespace character count (all whitespace types)
            non_ws_chars = sum(1 for c in node_text if not c.isspace())

            # FIX-6: Validate chunk size and split if needed
            if non_ws_chars > self.MAX_CHARS:
                logger.warning(
                    "chunk_exceeds_max_size",
                    extra={
                        "size_chars": non_ws_chars,
                        "max_chars": self.MAX_CHARS,
                        "file_path": file_path,
                        "node_type": node.type,
                    }
                )
                # Split large node into multiple chunks
                sub_chunk_texts = self._split_large_node(node, content, language)

                # Process each sub-chunk
                for sub_idx, sub_chunk_text in enumerate(sub_chunk_texts):
                    # Calculate non-whitespace for this sub-chunk
                    sub_non_ws = sum(1 for c in sub_chunk_text if not c.isspace())

                    # Calculate overlap
                    sub_overlap_chars = max(
                        int(sub_non_ws * self.OVERLAP_PCT),
                        self.MIN_OVERLAP_CHARS
                    )
                    sub_overlap_tokens = sub_overlap_chars // CHARS_PER_TOKEN

                    # Add overlap from previous chunk/sub-chunk
                    if (len(chunks) > 0 or sub_idx > 0) and previous_chunk_tail:
                        sub_chunk_text = previous_chunk_tail + "\n" + sub_chunk_text

                    # Add marker showing this is a split chunk
                    marker = f"# ... split {sub_idx + 1}/{len(sub_chunk_texts)} of large {node.type} ...\n\n"

                    # Add imports to ALL sub-chunks
                    if import_text:
                        sub_chunk_content = f"{import_text}\n\n{marker}{sub_chunk_text}"
                    else:
                        sub_chunk_content = f"{marker}{sub_chunk_text}"

                    # Store tail for next chunk's overlap
                    if len(sub_chunk_text) > sub_overlap_chars:
                        previous_chunk_tail = sub_chunk_text[-sub_overlap_chars:]
                    else:
                        previous_chunk_tail = sub_chunk_text

                    # Estimate tokens
                    sub_token_count = len(sub_chunk_content) // CHARS_PER_TOKEN

                    # Get approximate line numbers (best effort for sub-chunks)
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1

                    # Create metadata for sub-chunk
                    sub_metadata = ChunkMetadata(
                        chunk_type="ast_code_split",
                        chunk_index=len(chunks),
                        total_chunks=-1,  # Will be updated after loop
                        chunk_size_tokens=sub_token_count,
                        overlap_tokens=sub_overlap_tokens,
                        source_file=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        section_header=f"{self._get_node_name(node)}_part{sub_idx + 1}",
                    )

                    chunks.append(ChunkResult(content=sub_chunk_content, metadata=sub_metadata))

                # Skip processing the original oversized node
                continue

            # Get line numbers
            start_line = node.start_point[0] + 1  # Tree-sitter uses 0-indexed
            end_line = node.end_point[0] + 1

            # FIX-1: Calculate 20% overlap per Chunking-Strategy-V1.md Section 2.1
            overlap_chars = max(int(non_ws_chars * self.OVERLAP_PCT), self.MIN_OVERLAP_CHARS)
            overlap_tokens = overlap_chars // CHARS_PER_TOKEN

            # Prepend overlap from previous chunk (if not first chunk)
            if idx > 0 and previous_chunk_tail:
                node_text = previous_chunk_tail + "\n" + node_text

            # FIX-2: Add imports to ALL chunks for context (not just first)
            if import_text:
                chunk_content = f"{import_text}\n\n{node_text}"
            else:
                chunk_content = node_text

            # Store tail for next chunk's overlap (extract from original node_text before imports)
            clean_node_text = self._get_node_text(content, node)
            if len(clean_node_text) > overlap_chars:
                previous_chunk_tail = clean_node_text[-overlap_chars:]
            else:
                previous_chunk_tail = clean_node_text

            # Estimate tokens using shared constant
            token_count = len(chunk_content) // CHARS_PER_TOKEN

            # Create metadata
            metadata = ChunkMetadata(
                chunk_type="ast_code",
                chunk_index=len(chunks),
                total_chunks=-1,  # Will be updated after loop
                chunk_size_tokens=token_count,
                overlap_tokens=overlap_tokens,  # Now set correctly with 20% overlap
                source_file=file_path,
                start_line=start_line,
                end_line=end_line,
                section_header=self._get_node_name(node),
            )

            chunks.append(ChunkResult(content=chunk_content, metadata=metadata))

        # Update total_chunks in all metadata (now that we know final count)
        # Note: ChunkMetadata is frozen, so create new instances
        final_chunks = []
        for chunk in chunks:
            updated_metadata = ChunkMetadata(
                chunk_type=chunk.metadata.chunk_type,
                chunk_index=chunk.metadata.chunk_index,
                total_chunks=len(chunks),  # Now set to actual total
                chunk_size_tokens=chunk.metadata.chunk_size_tokens,
                overlap_tokens=chunk.metadata.overlap_tokens,
                source_file=chunk.metadata.source_file,
                start_line=chunk.metadata.start_line,
                end_line=chunk.metadata.end_line,
                section_header=chunk.metadata.section_header,
            )
            final_chunks.append(ChunkResult(content=chunk.content, metadata=updated_metadata))

        return final_chunks

    def _find_chunk_nodes(self, root_node: "Node", language: str) -> List["Node"]:
        """Find all top-level nodes that represent chunk boundaries.

        Only extracts top-level functions/classes. Methods inside classes
        are kept with their parent class chunk.

        Args:
            root_node: Root AST node
            language: Language name

        Returns:
            List of top-level nodes to chunk at
        """
        chunk_types = self.CHUNK_NODE_TYPES.get(language, set())
        chunk_nodes = []

        # Only visit direct children of root (top-level definitions)
        # Don't recursively visit nested definitions
        def visit_top_level(node: "Node"):
            if node.type in chunk_types:
                chunk_nodes.append(node)
                # Don't visit children - we want the whole class with its methods
                return
            # Keep visiting children to find top-level definitions
            for child in node.children:
                visit_top_level(child)

        for child in root_node.children:
            visit_top_level(child)

        return chunk_nodes

    def _find_import_nodes(self, root_node: "Node", language: str) -> List["Node"]:
        """Find all import nodes for context extraction.

        Only extracts top-level imports (direct children of root).
        Stops after encountering non-import statements.

        Args:
            root_node: Root AST node
            language: Language name

        Returns:
            List of import nodes
        """
        import_types = self.IMPORT_NODE_TYPES.get(language, set())
        import_nodes = []

        # Only look at direct children of root (top-level imports)
        for child in root_node.children:
            if child.type in import_types:
                import_nodes.append(child)
            # Stop after we hit non-import, non-comment nodes
            # (imports are typically at the top of the file)
            elif child.type not in ("comment", "expression_statement", "string"):
                # Reached actual code, stop looking for imports
                if import_nodes:
                    break

        return import_nodes

    def _extract_node_text(self, content: str, nodes: List["Node"]) -> str:
        """Extract text from multiple nodes.

        Args:
            content: Source code
            nodes: List of AST nodes

        Returns:
            Combined text from all nodes
        """
        if not nodes:
            return ""

        return "\n".join(self._get_node_text(content, node) for node in nodes)

    def _get_node_text(self, content: str, node: "Node") -> str:
        """Get text content of a node.

        Args:
            content: Source code
            node: AST node

        Returns:
            Text content of node
        """
        start_byte = node.start_byte
        end_byte = node.end_byte
        return content[start_byte:end_byte]

    def _get_node_name(self, node: "Node") -> Optional[str]:
        """Extract function/class name from node.

        Args:
            node: AST node (function or class definition)

        Returns:
            Name of function/class, or None if not found
        """
        # Look for identifier child node
        # FIX-11: In tree-sitter 0.21+, child.text is always bytes
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf8")

        return None

    def _split_large_node(
        self, node: "Node", content: str, language: str
    ) -> List[str]:
        """Split a large AST node into smaller chunks at statement boundaries.

        FIX-5: Implements recursive splitting per Chunking-Strategy-V1.md.

        Args:
            node: AST node that exceeds MAX_CHARS
            content: Source code content
            language: Language name

        Returns:
            List of chunk strings split at natural boundaries
        """
        node_text = self._get_node_text(content, node)
        non_ws_chars = sum(1 for c in node_text if not c.isspace())

        # If within limit, return as-is
        if non_ws_chars <= self.MAX_CHARS:
            return [node_text]

        logger.debug(
            "splitting_large_node",
            extra={
                "node_type": node.type,
                "size_chars": non_ws_chars,
                "max_chars": self.MAX_CHARS,
            }
        )

        # Split at child statement boundaries
        chunks = []
        current_chunk = ""

        for child in node.children:
            child_text = self._get_node_text(content, child)
            child_non_ws = sum(1 for c in child_text if not c.isspace())

            # Check if adding this child would exceed limit
            combined = current_chunk + "\n" + child_text if current_chunk else child_text
            combined_non_ws = sum(1 for c in combined if not c.isspace())

            if combined_non_ws > self.MAX_CHARS and current_chunk:
                # Save current chunk and start new one
                chunks.append(current_chunk)
                current_chunk = child_text
            else:
                current_chunk = combined

        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk)

        return chunks if chunks else [node_text]

    def _fallback_whole_content(
        self, content: str, file_path: str
    ) -> List[ChunkResult]:
        """Fallback to whole-content chunk when parsing fails.

        Args:
            content: Source code
            file_path: Source file path

        Returns:
            Single-chunk list with whole content
        """
        token_count = len(content) // CHARS_PER_TOKEN

        metadata = ChunkMetadata(
            chunk_type="whole",
            chunk_index=0,
            total_chunks=1,
            chunk_size_tokens=token_count,
            overlap_tokens=0,
            source_file=file_path,
        )

        logger.debug(
            "fallback_to_whole_content",
            extra={"file_path": file_path, "token_count": token_count},
        )

        return [ChunkResult(content=content, metadata=metadata)]


__all__ = ["ASTChunker"]
