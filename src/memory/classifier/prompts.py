"""Classification prompt templates.

Provides structured prompts for LLM-based memory classification.

TECH-DEBT-069: LLM-based memory classification system.
"""

from typing import Optional

__all__ = ["CLASSIFICATION_PROMPT", "build_classification_prompt"]

CLASSIFICATION_PROMPT = """You are a memory classifier for a software development AI assistant.

Classify this memory into EXACTLY ONE type based on its content.

## MEMORY TYPES

### code-patterns collection (HOW things are built):
- **implementation**: How a feature was built, code patterns, architecture
- **error_fix**: An error/exception encountered AND its solution
- **refactor**: Code restructuring, renaming, moving, extracting
- **file_pattern**: File-specific conventions or patterns

### conventions collection (WHAT rules to follow):
- **rule**: Hard rules using MUST/NEVER/ALWAYS/REQUIRED
- **guideline**: Soft recommendations, best practices, suggestions
- **port**: Port number configurations or assignments
- **naming**: Naming conventions for files, functions, variables
- **structure**: Folder structure or file organization conventions

### discussions collection (WHY things were decided):
- **decision**: Architectural choices, technology selections, approach decisions
- **session**: Session summaries (handled separately - don't classify as this)
- **blocker**: Something blocking progress, waiting on external
- **preference**: User preferences, personal choices about workflow

### Default types (only if nothing else fits):
- **user_message**: Raw user input with no special classification
- **agent_response**: Raw agent output with no special classification

## CLASSIFICATION RULES
1. Choose the MOST SPECIFIC type that applies
2. "decision" requires an actual choice was made, not just discussion
3. "error_fix" requires BOTH the error AND its fix
4. "rule" requires strong language (MUST/NEVER), otherwise use "guideline"
5. If unsure between types, prefer the default (user_message/agent_response)

## CONTENT TO CLASSIFY
Collection: {collection}
Current Type: {current_type}{file_path_line}

Content:
---
{content}
---

## RESPONSE FORMAT
Respond with valid JSON only, no markdown:
{{
  "classified_type": "<type from list above>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief 1-sentence explanation>",
  "tags": ["<relevant>", "<tags>"],
  "is_significant": <true if valuable for future sessions, false otherwise>
}}"""


def build_classification_prompt(
    content: str,
    collection: str,
    current_type: str,
    file_path: Optional[str] = None,
) -> str:
    """Build classification prompt with content.

    Args:
        content: The content to classify
        collection: Target collection (code-patterns, conventions, discussions)
        current_type: Current memory type
        file_path: Optional file path context

    Returns:
        Formatted prompt string
    """
    # Truncate content if too long
    from .config import MAX_INPUT_CHARS

    truncated_content = content
    if len(content) > MAX_INPUT_CHARS:
        truncated_content = content[:MAX_INPUT_CHARS] + "\n\n[...truncated]"

    # FIX-3: Build file path line BEFORE formatting (fixes placeholder bug)
    file_path_line = f"\nFile Path: {file_path}" if file_path else ""

    # Format prompt with all placeholders at once
    prompt = CLASSIFICATION_PROMPT.format(
        collection=collection,
        current_type=current_type,
        file_path_line=file_path_line,
        content=truncated_content,
    )

    return prompt
