"""Unit tests for ADF converter.

Tests Atlassian Document Format (ADF) to plain text conversion with:
- All must-have node types (paragraph, text, heading, lists, code, blockquote)
- Should-have node types (mention, inlineCard)
- Unknown nodes (graceful fallback)
- Edge cases (empty input, nested structures, malformed JSON)
"""

from src.memory.connectors.jira.adf_converter import _walk_node, adf_to_text

# =============================================================================
# Must-Have Node Types
# =============================================================================


class TestParagraphNode:
    """Test paragraph node conversion."""

    def test_empty_paragraph(self):
        """Empty paragraph should produce blank line."""
        adf = {
            "type": "doc",
            "content": [{"type": "paragraph", "content": []}],
        }
        result = adf_to_text(adf)
        assert result == ""

    def test_single_text_node(self):
        """Paragraph with single text node."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "Hello world\n"

    def test_multiple_text_nodes(self):
        """Paragraph with multiple inline text nodes."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "world"},
                        {"type": "text", "text": "!"},
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "Hello world!\n"

    def test_multiple_paragraphs(self):
        """Multiple paragraphs with blank lines between."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
            ],
        }
        result = adf_to_text(adf)
        assert result == "First\n\nSecond\n"


class TestTextNode:
    """Test text node conversion with marks."""

    def test_plain_text(self):
        """Plain text without marks."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Plain text"}],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "Plain text\n"

    def test_bold_text(self):
        """Text with strong (bold) mark."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "bold",
                            "marks": [{"type": "strong"}],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "**bold**\n"

    def test_italic_text(self):
        """Text with em (italic) mark."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "italic",
                            "marks": [{"type": "em"}],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "*italic*\n"

    def test_code_text(self):
        """Text with code mark."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "code",
                            "marks": [{"type": "code"}],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "`code`\n"

    def test_empty_text(self):
        """Empty text node."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": ""}]}
            ],
        }
        result = adf_to_text(adf)
        assert result == ""


class TestHeadingNode:
    """Test heading node conversion."""

    def test_heading_level_1(self):
        """H1 heading."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Heading 1"}],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "# Heading 1\n"

    def test_heading_level_6(self):
        """H6 heading."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 6},
                    "content": [{"type": "text", "text": "Heading 6"}],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "###### Heading 6\n"

    def test_empty_heading(self):
        """Empty heading."""
        adf = {
            "type": "doc",
            "content": [{"type": "heading", "attrs": {"level": 2}, "content": []}],
        }
        result = adf_to_text(adf)
        assert result == ""

    def test_heading_with_marks(self):
        """Heading with text marks."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [
                        {
                            "type": "text",
                            "text": "Bold Heading",
                            "marks": [{"type": "strong"}],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "## **Bold Heading**\n"


class TestBulletList:
    """Test bullet list conversion."""

    def test_single_item(self):
        """Bullet list with single item."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Item 1"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "- Item 1\n"

    def test_multiple_items(self):
        """Bullet list with multiple items."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Item 1"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Item 2"}],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "- Item 1\n- Item 2\n"

    def test_nested_bullet_list(self):
        """Nested bullet lists with proper indentation."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Parent"}],
                                },
                                {
                                    "type": "bulletList",
                                    "content": [
                                        {
                                            "type": "listItem",
                                            "content": [
                                                {
                                                    "type": "paragraph",
                                                    "content": [
                                                        {
                                                            "type": "text",
                                                            "text": "Child",
                                                        }
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "- Parent" in result
        assert "  - Child" in result


class TestOrderedList:
    """Test ordered list conversion."""

    def test_sequential_numbering(self):
        """Ordered list with sequential numbering."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "First"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Second"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Third"}],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "1. First" in result
        assert "2. Second" in result
        assert "3. Third" in result

    def test_nested_ordered_list(self):
        """Nested ordered lists with proper indentation."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Parent"}],
                                },
                                {
                                    "type": "orderedList",
                                    "content": [
                                        {
                                            "type": "listItem",
                                            "content": [
                                                {
                                                    "type": "paragraph",
                                                    "content": [
                                                        {
                                                            "type": "text",
                                                            "text": "Child",
                                                        }
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "1. Parent" in result
        assert "  1. Child" in result

    def test_empty_ordered_list(self):
        """Empty ordered list."""
        adf = {
            "type": "doc",
            "content": [{"type": "orderedList", "content": []}],
        }
        result = adf_to_text(adf)
        assert result == ""


class TestListItem:
    """Test list item conversion."""

    def test_simple_content(self):
        """List item with simple text content."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Simple"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "- Simple\n"

    def test_paragraph_content(self):
        """List item with paragraph content."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Paragraph in list"}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "- Paragraph in list" in result

    def test_nested_list_in_item(self):
        """List item containing nested list."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Parent"}],
                                },
                                {
                                    "type": "bulletList",
                                    "content": [
                                        {
                                            "type": "listItem",
                                            "content": [
                                                {
                                                    "type": "paragraph",
                                                    "content": [
                                                        {
                                                            "type": "text",
                                                            "text": "Nested",
                                                        }
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "- Parent" in result
        assert "  - Nested" in result


class TestCodeBlock:
    """Test code block conversion."""

    def test_with_language(self):
        """Code block with language specified."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "attrs": {"language": "python"},
                    "content": [{"type": "text", "text": "print('hello')"}],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "```python\nprint('hello')\n```\n"

    def test_without_language(self):
        """Code block without language."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "attrs": {},
                    "content": [{"type": "text", "text": "code here"}],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "```\ncode here\n```\n"

    def test_multiline_code(self):
        """Code block with multiline content."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "attrs": {"language": "javascript"},
                    "content": [
                        {"type": "text", "text": "function test() {\n  return true;\n}"}
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "```javascript" in result
        assert "function test()" in result
        assert "return true;" in result

    def test_empty_code_block(self):
        """Empty code block."""
        adf = {
            "type": "doc",
            "content": [{"type": "codeBlock", "attrs": {}, "content": []}],
        }
        result = adf_to_text(adf)
        assert result == ""


class TestBlockquote:
    """Test blockquote conversion."""

    def test_single_paragraph(self):
        """Blockquote with single paragraph."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Quoted text"}],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "> Quoted text" in result

    def test_multiple_paragraphs(self):
        """Blockquote with multiple paragraphs."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "First line"}],
                        },
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Second line"}],
                        },
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "> First line" in result
        assert "> Second line" in result

    def test_empty_blockquote(self):
        """Empty blockquote."""
        adf = {
            "type": "doc",
            "content": [{"type": "blockquote", "content": []}],
        }
        result = adf_to_text(adf)
        assert result == ""


class TestHardBreak:
    """Test hard break conversion."""

    def test_single_break(self):
        """Single hard break."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Line 1"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "Line 2"},
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "Line 1\nLine 2" in result

    def test_multiple_breaks(self):
        """Multiple hard breaks."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "A"},
                        {"type": "hardBreak"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "B"},
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "A\n\nB" in result

    def test_break_at_end(self):
        """Hard break at end of paragraph."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Text"},
                        {"type": "hardBreak"},
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "Text\n" in result


# =============================================================================
# Should-Have Node Types
# =============================================================================


class TestMention:
    """Test mention node conversion."""

    def test_with_display_name(self):
        """Mention with displayName."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "mention", "attrs": {"displayName": "John Doe"}}
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "@John Doe\n"

    def test_without_display_name(self):
        """Mention without displayName (defaults to Unknown)."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "mention", "attrs": {}}]}
            ],
        }
        result = adf_to_text(adf)
        assert result == "@Unknown\n"

    def test_mention_in_sentence(self):
        """Mention embedded in sentence."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hey "},
                        {"type": "mention", "attrs": {"displayName": "Alice"}},
                        {"type": "text", "text": " can you review?"},
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "Hey @Alice can you review?\n"


class TestInlineCard:
    """Test inline card (link) conversion."""

    def test_with_url(self):
        """Inline card with URL."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "inlineCard",
                            "attrs": {"url": "https://example.com"},
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert result == "https://example.com\n"

    def test_without_url(self):
        """Inline card without URL (empty)."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "inlineCard", "attrs": {}}]}
            ],
        }
        result = adf_to_text(adf)
        assert result == ""

    def test_card_in_sentence(self):
        """Inline card embedded in text."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "See "},
                        {
                            "type": "inlineCard",
                            "attrs": {"url": "https://jira.com/PROJ-123"},
                        },
                        {"type": "text", "text": " for details"},
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "https://jira.com/PROJ-123" in result
        assert "for details" in result


# =============================================================================
# Edge Cases
# =============================================================================


class TestUnknownNodes:
    """Test graceful fallback for unknown node types."""

    def test_unknown_node_type(self, caplog):
        """Unknown node type should log warning and extract nested content."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "unknownNode",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Nested text"}],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        # Should extract nested text despite unknown parent
        assert "Nested text" in result
        # Should log warning
        assert any("unknown" in record.message.lower() for record in caplog.records)

    def test_unknown_nested_in_paragraph(self, caplog):
        """Unknown node nested in paragraph should be skipped with warning."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Before "},
                        {"type": "unknownInline", "content": []},
                        {"type": "text", "text": " After"},
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "Before" in result
        assert "After" in result

    def test_deeply_nested_unknown(self):
        """Unknown node deeply nested should still extract text."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "unknownOuter",
                    "content": [
                        {
                            "type": "unknownInner",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Deep text"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "Deep text" in result


class TestEmptyAndNullInput:
    """Test empty and null input handling."""

    def test_none_input(self):
        """None input should return empty string."""
        result = adf_to_text(None)
        assert result == ""

    def test_empty_dict(self):
        """Empty dict should return empty string."""
        result = adf_to_text({})
        assert result == ""

    def test_empty_content_array(self):
        """Empty content array should return empty string."""
        adf = {"type": "doc", "content": []}
        result = adf_to_text(adf)
        assert result == ""

    def test_missing_content_key(self):
        """Missing content key should return empty string."""
        adf = {"type": "doc"}
        result = adf_to_text(adf)
        assert result == ""


class TestNestedStructures:
    """Test deeply nested structures."""

    def test_three_level_list_nesting(self):
        """3-level nested list."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "L1"}],
                                },
                                {
                                    "type": "bulletList",
                                    "content": [
                                        {
                                            "type": "listItem",
                                            "content": [
                                                {
                                                    "type": "paragraph",
                                                    "content": [
                                                        {"type": "text", "text": "L2"}
                                                    ],
                                                },
                                                {
                                                    "type": "bulletList",
                                                    "content": [
                                                        {
                                                            "type": "listItem",
                                                            "content": [
                                                                {
                                                                    "type": "paragraph",
                                                                    "content": [
                                                                        {
                                                                            "type": "text",
                                                                            "text": "L3",
                                                                        }
                                                                    ],
                                                                }
                                                            ],
                                                        }
                                                    ],
                                                },
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_text(adf)
        assert "- L1" in result
        assert "  - L2" in result
        assert "    - L3" in result

    def test_mixed_content_nesting(self):
        """Mixed content: list containing code block and blockquote."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Item"}],
                                },
                            ],
                        }
                    ],
                },
                {
                    "type": "codeBlock",
                    "attrs": {"language": "python"},
                    "content": [{"type": "text", "text": "code"}],
                },
                {
                    "type": "blockquote",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "quote"}],
                        }
                    ],
                },
            ],
        }
        result = adf_to_text(adf)
        assert "- Item" in result
        assert "```python" in result
        assert "> quote" in result

    def test_complex_document(self):
        """Complex document with multiple node types."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Title"}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Intro with "},
                        {"type": "mention", "attrs": {"displayName": "Bob"}},
                    ],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Point 1"}],
                                }
                            ],
                        }
                    ],
                },
                {
                    "type": "codeBlock",
                    "attrs": {"language": "bash"},
                    "content": [{"type": "text", "text": "ls -la"}],
                },
            ],
        }
        result = adf_to_text(adf)
        assert "# Title" in result
        assert "@Bob" in result
        assert "- Point 1" in result
        assert "```bash" in result


class TestMalformedJSON:
    """Test malformed JSON handling."""

    def test_missing_type(self, caplog):
        """Node missing type field should log debug and skip."""
        adf = {
            "type": "doc",
            "content": [
                {"content": [{"type": "text", "text": "orphan"}]},  # Missing type
            ],
        }
        result = adf_to_text(adf)
        # Should not crash, may or may not extract content
        assert isinstance(result, str)

    def test_invalid_node_structure(self):
        """Node with invalid structure should not crash."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": "string instead of list"}  # Invalid
            ],
        }
        result = adf_to_text(adf)
        # Should handle gracefully
        assert isinstance(result, str)

    def test_missing_attrs(self):
        """Node missing attrs should use defaults."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    # Missing attrs
                    "content": [{"type": "text", "text": "No level"}],
                }
            ],
        }
        result = adf_to_text(adf)
        # Should default to level 1
        assert "# No level" in result


# =============================================================================
# Internal Function Tests
# =============================================================================


class TestWalkNode:
    """Test _walk_node internal function."""

    def test_walk_with_indent(self):
        """Walk node with indentation level."""
        node = {
            "type": "listItem",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Indented"}]}
            ],
        }
        output = []
        _walk_node(node, output, indent_level=2, list_counter=None)
        # Should have 4-space indent (2 levels * 2 spaces)
        assert any("    - Indented" in line for line in output)

    def test_walk_with_counter(self):
        """Walk node with list counter."""
        node = {
            "type": "listItem",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Numbered"}]}
            ],
        }
        output = []
        _walk_node(node, output, indent_level=0, list_counter=5)
        # Should have number 5
        assert any("5. Numbered" in line for line in output)

    def test_walk_empty_content(self):
        """Walk node with no content."""
        node = {"type": "paragraph", "content": []}
        output = []
        _walk_node(node, output)
        # Should not add anything to output
        assert output == []
