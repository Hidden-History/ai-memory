import os
import sys

# Add hooks scripts to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "scripts")
)

from agent_response_capture import extract_last_assistant_message


def test_extract_from_message_content_path():
    """Test extraction from correct transcript format (message.content)."""
    entries = [
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Hello, this is my response."}]
            },
        }
    ]

    result = extract_last_assistant_message(entries)
    assert result == "Hello, this is my response."


def test_extract_handles_empty_content():
    """Test graceful handling of empty content."""
    entries = [{"type": "assistant", "message": {"content": []}}]

    result = extract_last_assistant_message(entries, max_retries=0)
    assert result is None


def test_extract_handles_missing_message():
    """Test graceful handling of missing message key."""
    entries = [{"type": "assistant"}]

    result = extract_last_assistant_message(entries, max_retries=0)
    assert result is None
