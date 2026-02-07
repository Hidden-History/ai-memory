"""Smart truncation functions for content that should remain whole.

Implements sentence-boundary and structured truncation strategies per
Chunking-Strategy-V2.md Section 4.

These functions are for content that should remain as single vectors but may
exceed token limits. For content that should be chunked into multiple vectors
(guidelines, long documents), use IntelligentChunker instead.

Key principles:
- Use sentence boundaries, not arbitrary character cuts
- Preserve semantic integrity
- Use tiktoken for accurate token counting
- Append ' [...]' marker (NOT '[TRUNCATED]')
"""

import re
from typing import Dict

import tiktoken


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens in text using tiktoken.

    Args:
        text: Text to count tokens for
        encoding_name: tiktoken encoding (default: cl100k_base for GPT-4)

    Returns:
        Number of tokens in the text

    Example:
        >>> count_tokens("Hello world")
        2
    """
    if not text:
        return 0
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


def smart_end(content: str, max_tokens: int, encoding_name: str = "cl100k_base") -> str:
    """Truncate at sentence boundary, keeping beginning.

    Algorithm per Chunking-Strategy-V2.md Section 4.1:
    1. If content <= max_tokens: return as-is
    2. Find last sentence boundary (. ! ? followed by space/newline) before max_tokens
    3. If no sentence boundary found, find last word boundary
    4. Append ' [...]' marker (NOT "[TRUNCATED]")

    Args:
        content: Content to truncate
        max_tokens: Maximum tokens to keep
        encoding_name: tiktoken encoding (default: cl100k_base for GPT-4)

    Returns:
        Truncated content with [...] marker if truncated, original if under limit

    Example:
        >>> text = "First sentence. Second sentence. Third sentence."
        >>> smart_end(text, max_tokens=10)
        'First sentence. Second sentence. [...]'
    """
    if not content or not content.strip():
        return content

    # Check if content is already within limit
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(content)

    if len(tokens) <= max_tokens:
        return content

    # Estimate character position for max_tokens (rough: 4 chars/token)
    # Use conservative estimate to avoid overshooting
    estimated_char_pos = max_tokens * 3  # Conservative: 3 chars/token

    # Find last sentence boundary before estimated position
    # Sentence boundaries: . ! ? followed by space, newline, or end of string
    truncated = content[:estimated_char_pos]

    # Find all sentence boundaries
    sentence_pattern = r'[.!?](?:\s|$)'
    matches = list(re.finditer(sentence_pattern, truncated))

    if matches:
        # Get position after the last sentence boundary
        last_boundary = matches[-1].end()

        # Verify this keeps us under token limit and >= 50% of budget
        candidate = content[:last_boundary].rstrip()
        candidate_tokens = len(encoding.encode(candidate))

        if candidate_tokens <= max_tokens and candidate_tokens >= max_tokens * 0.5:
            return candidate + " [...]"

    # Fallback: Find last word boundary
    # Decode tokens directly to stay within limit
    truncated_tokens = tokens[:max_tokens]
    truncated_text = encoding.decode(truncated_tokens)

    # Find last space to avoid cutting mid-word
    last_space = truncated_text.rfind(' ')
    if last_space > len(truncated_text) * 0.5:  # At least 50% of content
        return truncated_text[:last_space] + " [...]"

    # Last resort: use token-based truncation
    return truncated_text.rstrip() + " [...]"


def first_last(
    content: str,
    max_tokens: int,
    first_ratio: float = 0.7,
    encoding_name: str = "cl100k_base"
) -> str:
    """Keep beginning + end, truncate middle.

    Algorithm per Chunking-Strategy-V2.md Section 4.2:
    Used for command output, log files where middle is least useful.

    Args:
        content: Content to truncate
        max_tokens: Maximum tokens to keep
        first_ratio: Ratio for beginning (default 0.7 = 70% beginning, 30% end)
        encoding_name: tiktoken encoding

    Returns:
        Content with ' [...] ' marker in middle if truncated

    Example:
        >>> log = "START\\n" + "\\n".join([f"line {i}" for i in range(100)]) + "\\nEND"
        >>> first_last(log, max_tokens=50, first_ratio=0.7)
        'START\\nline 0\\n...\\n\\n[... truncated middle ...]\\n\\n...\\nline 99\\nEND'
    """
    if not content or not content.strip():
        return content

    # Validate first_ratio
    if not (0.0 < first_ratio < 1.0):
        raise ValueError(f"first_ratio must be between 0 and 1, got {first_ratio}")

    # Check if content is already within limit
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(content)

    if len(tokens) <= max_tokens:
        return content

    # Calculate token budgets for first and last sections
    first_tokens = int(max_tokens * first_ratio)
    last_tokens = max_tokens - first_tokens

    # Get first section
    first_section_tokens = tokens[:first_tokens]
    first_section = encoding.decode(first_section_tokens).rstrip()

    # Get last section
    last_section_tokens = tokens[-last_tokens:]
    last_section = encoding.decode(last_section_tokens).lstrip()

    return first_section + "\n\n[... truncated middle ...]\n\n" + last_section


def structured_truncate(
    content: str,
    max_tokens: int,
    sections: Dict[str, str],
    encoding_name: str = "cl100k_base"
) -> str:
    """Truncate preserving structure of command + error + output.

    For error context preservation per Chunking-Strategy-V2.md Section 2.5.
    Ensures command, error message, and relevant output are all preserved proportionally.

    The error message is NEVER truncated. Command and output are truncated if needed
    to stay within budget.

    Args:
        content: Full error context (will be ignored, sections dict is used)
        max_tokens: Maximum tokens to keep (typically 800)
        sections: Dict with keys:
            - 'command': str (full command that failed)
            - 'error': str (error message - NEVER truncated)
            - 'output': str (command output - truncated if needed)
        encoding_name: tiktoken encoding

    Returns:
        Structured truncated content maintaining all 3 sections

    Example:
        >>> sections = {
        ...     'command': 'pytest tests/',
        ...     'error': 'AssertionError: expected 5, got 3',
        ...     'output': '...long stack trace...'
        ... }
        >>> structured_truncate('', max_tokens=800, sections=sections)
        'Command: pytest tests/\\nError: AssertionError: expected 5, got 3\\nOutput: [truncated]...'
    """
    if not sections:
        return content

    # Validate required keys
    required_keys = {'command', 'error', 'output'}
    missing_keys = required_keys - set(sections.keys())
    if missing_keys:
        raise ValueError(f"Missing required sections: {missing_keys}")

    encoding = tiktoken.get_encoding(encoding_name)

    # Count tokens for each section
    command = sections['command']
    error = sections['error']
    output = sections['output']

    # Build header strings
    command_header = "Command: "
    error_header = "\nError: "
    output_header = "\nOutput: "

    # Error is NEVER truncated - this is the most important part
    error_tokens = len(encoding.encode(error_header + error))

    # Reserve tokens for headers and structure
    header_tokens = len(encoding.encode(command_header + output_header))
    reserved_tokens = error_tokens + header_tokens + 10  # +10 for safety margin

    if reserved_tokens >= max_tokens:
        # If error alone exceeds budget, keep error + minimal command/output
        return f"{command_header}{command[:50]}...\n{error_header}{error}\n{output_header}[truncated]"

    # Calculate remaining budget for command and output
    remaining_tokens = max_tokens - reserved_tokens

    # Allocate 20% to command, 80% to output (output is usually more important for debugging)
    command_budget = int(remaining_tokens * 0.2)
    output_budget = remaining_tokens - command_budget

    # Truncate command if needed
    command_tokens = encoding.encode(command)
    if len(command_tokens) > command_budget:
        truncated_command = encoding.decode(command_tokens[:command_budget]).rstrip() + "..."
    else:
        truncated_command = command

    # Truncate output using first_last strategy
    output_tokens = encoding.encode(output)
    if len(output_tokens) > output_budget:
        # Use first_last for output (keep beginning and end of stack trace)
        truncated_output = first_last(
            output,
            max_tokens=output_budget,
            first_ratio=0.6,  # 60% beginning, 40% end for errors
            encoding_name=encoding_name
        )
    else:
        truncated_output = output

    # Assemble final result
    result = (
        f"{command_header}{truncated_command}"
        f"{error_header}{error}"
        f"{output_header}{truncated_output}"
    )

    return result
