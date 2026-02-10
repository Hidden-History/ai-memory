"""Atlassian Document Format (ADF) to plain text converter.

Converts Jira's ADF JSON format to plain text for embedding.
Implements recursive tree walker with graceful fallback for unknown node types.

Reference: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/
"""

import logging
from typing import Any

logger = logging.getLogger("ai_memory.jira.adf")


def adf_to_text(adf_content: dict[str, Any] | None) -> str:
    """Convert Atlassian Document Format (ADF) JSON to plain text.

    Recursively walks the ADF tree and extracts text content.

    Supported node types:
    - Must-have: paragraph, text, heading, bulletList, orderedList, listItem,
                 codeBlock, blockquote, hardBreak
    - Should-have: mention (@displayName), inlineCard (URL)
    - Unknown: logs warning, extracts nested text gracefully

    Args:
        adf_content: ADF JSON dict (can be None or empty)

    Returns:
        Plain text representation. Returns empty string for None/empty input.

    Example:
        >>> adf = {
        ...     "type": "doc",
        ...     "content": [
        ...         {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}
        ...     ]
        ... }
        >>> adf_to_text(adf)
        'Hello\\n'
    """
    if not adf_content:
        return ""

    output: list[str] = []
    _walk_node(adf_content, output, indent_level=0, list_counter=None)
    return "\n".join(output)


def _walk_node(
    node: dict[str, Any],
    output: list[str],
    indent_level: int = 0,
    list_counter: int | None = None,
) -> None:
    """Recursively walk ADF node tree and build text output.

    Args:
        node: ADF node dict with type and optional content/attrs
        output: List to accumulate text lines
        indent_level: Current indentation level for nested lists
        list_counter: Counter for ordered list items (1, 2, 3...)
    """
    # Guard against non-dict content items (malformed ADF)
    if not isinstance(node, dict):
        if isinstance(node, str):
            output.append(node)
        return

    node_type = node.get("type")

    if not node_type:
        logger.debug("adf_node_missing_type", extra={"node": str(node)[:100]})
        return

    # Handle text nodes (leaf nodes with actual text content)
    if node_type == "text":
        text = node.get("text", "")
        # Apply text marks (bold, italic, etc.)
        marks = node.get("marks", [])
        for mark in marks:
            mark_type = mark.get("type")
            if mark_type == "strong":
                text = f"**{text}**"
            elif mark_type == "em":
                text = f"*{text}*"
            elif mark_type == "code":
                text = f"`{text}`"
        output.append(text)
        return

    # Handle hardBreak (newline)
    if node_type == "hardBreak":
        output.append("\n")
        return

    # Handle mention nodes (@username)
    if node_type == "mention":
        display_name = node.get("attrs", {}).get("displayName", "Unknown")
        output.append(f"@{display_name}")
        return

    # Handle inlineCard (links)
    if node_type == "inlineCard":
        url = node.get("attrs", {}).get("url", "")
        if url:
            output.append(url)
        return

    # Get child nodes
    content = node.get("content", [])

    # Handle document root
    if node_type == "doc":
        for child in content:
            _walk_node(child, output, indent_level, list_counter)
        return

    # Handle paragraph
    if node_type == "paragraph":
        paragraph_text = []
        temp_output: list[str] = []
        for child in content:
            _walk_node(child, temp_output, indent_level, list_counter)
        paragraph_text = temp_output
        if paragraph_text:
            joined = "".join(paragraph_text)
            if joined:  # Skip empty text paragraphs
                output.append(joined)
                output.append("")  # Blank line
        return

    # Handle heading
    if node_type == "heading":
        level = node.get("attrs", {}).get("level", 1)
        heading_text = []
        temp_output: list[str] = []
        for child in content:
            _walk_node(child, temp_output, indent_level, list_counter)
        heading_text = temp_output
        if heading_text:
            prefix = "#" * level
            output.append(f"{prefix} {''.join(heading_text)}")
            output.append("")  # Blank line
        return

    # Handle bulletList
    if node_type == "bulletList":
        for child in content:
            _walk_node(child, output, indent_level, list_counter=None)
        output.append("")  # Blank line after list
        return

    # Handle orderedList
    if node_type == "orderedList":
        counter = 1
        for child in content:
            _walk_node(child, output, indent_level, list_counter=counter)
            counter += 1
        output.append("")  # Blank line after list
        return

    # Handle listItem
    if node_type == "listItem":
        indent = "  " * indent_level
        if list_counter is not None:
            # Ordered list item
            prefix = f"{indent}{list_counter}. "
        else:
            # Bullet list item
            prefix = f"{indent}- "

        item_text = []
        temp_output: list[str] = []
        for child in content:
            if child.get("type") in ("bulletList", "orderedList"):
                # Nested list - process separately with increased indent
                if temp_output:
                    output.append(prefix + "".join(temp_output))
                    temp_output = []
                _walk_node(child, output, indent_level + 1, None)
            else:
                _walk_node(child, temp_output, indent_level, list_counter)

        if temp_output:
            item_text = temp_output
            output.append(prefix + "".join(item_text))
        return

    # Handle codeBlock
    if node_type == "codeBlock":
        language = node.get("attrs", {}).get("language", "")
        code_lines = []
        temp_output: list[str] = []
        for child in content:
            _walk_node(child, temp_output, indent_level, list_counter)
        code_lines = temp_output
        if code_lines:
            output.append(f"```{language}")
            output.append("".join(code_lines))
            output.append("```")
            output.append("")  # Blank line
        return

    # Handle blockquote
    if node_type == "blockquote":
        quote_lines = []
        temp_output: list[str] = []
        for child in content:
            _walk_node(child, temp_output, indent_level, list_counter)
        quote_lines = temp_output
        if quote_lines:
            # Prefix each line with "> "
            text = "\n".join(quote_lines)
            for line in text.split("\n"):
                if line.strip():
                    output.append(f"> {line}")
            output.append("")  # Blank line
        return

    # Unknown node type - log warning and try to extract nested content
    logger.warning(
        "adf_unknown_node_type",
        extra={"node_type": node_type, "has_content": bool(content)},
    )

    # Graceful fallback: recurse into children
    for child in content:
        _walk_node(child, output, indent_level, list_counter)
