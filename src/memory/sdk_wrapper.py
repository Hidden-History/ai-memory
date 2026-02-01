"""Minimal Anthropic SDK wrapper for conversation capture (TECH-DEBT-035 Phase 1).

Provides basic integration with Anthropic Messages API to capture user messages
and agent responses in real-time, storing them to the discussions collection.

This is a PROTOTYPE to prove the concept works before full integration.

Architecture:
- Uses anthropic.Anthropic() client with messages.stream()
- Captures messages during streaming (not after file write)
- Stores to discussions collection with USER_MESSAGE and AGENT_RESPONSE types
- Graceful degradation on storage failures

References:
- Research: oversight/specs/tech-debt-035/phase-0-research/agent-sdk-overview.md
- Storage: src/memory/storage.py (MemoryStorage.store_memory)
- Models: src/memory/models.py (MemoryType.USER_MESSAGE, AGENT_RESPONSE)
"""

import logging
import os
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

from anthropic import Anthropic
from anthropic.types import Message, TextBlock

from .config import COLLECTION_DISCUSSIONS
from .models import MemoryType
from .storage import MemoryStorage

__all__ = ["ConversationCapture", "SDKWrapper"]

logger = logging.getLogger("ai_memory.sdk_wrapper")


class ConversationCapture:
    """Captures and stores a single conversation turn.

    Stores both user message and agent response to discussions collection.
    """

    def __init__(
        self,
        storage: MemoryStorage,
        cwd: str,
        session_id: str | None = None,
    ):
        """Initialize conversation capture.

        Args:
            storage: MemoryStorage instance for persistence
            cwd: Current working directory for project detection
            session_id: Optional session identifier (generates UUID if not provided)
        """
        self.storage = storage
        self.cwd = cwd
        self.session_id = session_id or f"sdk_sess_{uuid.uuid4().hex[:8]}"
        self.turn_number = 0

    def capture_user_message(self, content: str) -> dict:
        """Capture and store user message.

        Args:
            content: User message content

        Returns:
            Storage result dict with status and memory_id
        """
        self.turn_number += 1

        try:
            result = self.storage.store_memory(
                content=content,
                cwd=self.cwd,
                memory_type=MemoryType.USER_MESSAGE,
                source_hook="SDKWrapper",
                session_id=self.session_id,
                collection=COLLECTION_DISCUSSIONS,
                turn_number=self.turn_number,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            logger.info(
                "user_message_captured",
                extra={
                    "session_id": self.session_id,
                    "turn_number": self.turn_number,
                    "status": result.get("status"),
                },
            )
            return result
        except Exception as e:
            logger.warning(
                "user_message_capture_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            return {"status": "failed", "error": str(e)}

    def capture_agent_response(self, content: str) -> dict:
        """Capture and store agent response.

        Args:
            content: Agent response content

        Returns:
            Storage result dict with status and memory_id
        """
        try:
            result = self.storage.store_memory(
                content=content,
                cwd=self.cwd,
                memory_type=MemoryType.AGENT_RESPONSE,
                source_hook="SDKWrapper",
                session_id=self.session_id,
                collection=COLLECTION_DISCUSSIONS,
                turn_number=self.turn_number,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            logger.info(
                "agent_response_captured",
                extra={
                    "session_id": self.session_id,
                    "turn_number": self.turn_number,
                    "status": result.get("status"),
                },
            )
            return result
        except Exception as e:
            logger.warning(
                "agent_response_capture_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            return {"status": "failed", "error": str(e)}


class SDKWrapper:
    """Minimal Anthropic SDK wrapper for message capture.

    Provides basic send/receive functionality with automatic conversation capture.

    Example:
        >>> wrapper = SDKWrapper(cwd="/path/to/project")
        >>> response = wrapper.send_message(
        ...     prompt="What is the capital of France?",
        ...     model="claude-3-5-sonnet-20241022"
        ... )
        >>> print(response["content"])
        'The capital of France is Paris.'
        >>> print(response["capture_status"])
        {'user': 'stored', 'agent': 'stored'}
    """

    def __init__(
        self,
        cwd: str,
        api_key: str | None = None,
        storage: MemoryStorage | None = None,
        session_id: str | None = None,
    ):
        """Initialize SDK wrapper.

        Args:
            cwd: Current working directory for project detection
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            storage: Optional MemoryStorage instance (creates new if not provided)
            session_id: Optional session identifier (generates UUID if not provided)
        """
        self.cwd = cwd
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Provide api_key parameter or set environment variable."
            )

        self.client = Anthropic(api_key=self.api_key)
        self.storage = storage or MemoryStorage()
        self.capture = ConversationCapture(
            storage=self.storage,
            cwd=cwd,
            session_id=session_id,
        )

        logger.info(
            "sdk_wrapper_initialized",
            extra={
                "session_id": self.capture.session_id,
                "cwd": cwd,
            },
        )

    def send_message(
        self,
        prompt: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 1024,
        **kwargs,
    ) -> dict:
        """Send a message and capture the conversation.

        Args:
            prompt: User message/prompt
            model: Claude model to use
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters for messages.create()

        Returns:
            Dict with:
                - content: Agent response text
                - message: Full Message object from API
                - capture_status: Dict with user/agent storage status
                - session_id: Session identifier
                - turn_number: Turn number in conversation
        """
        # Capture user message
        user_capture = self.capture.capture_user_message(prompt)

        # Send to API (non-streaming for simplicity in Phase 1)
        try:
            message = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )

            # Extract text content from response
            response_text = self._extract_text_content(message)

            # Capture agent response
            agent_capture = self.capture.capture_agent_response(response_text)

            return {
                "content": response_text,
                "message": message,
                "capture_status": {
                    "user": user_capture.get("status"),
                    "agent": agent_capture.get("status"),
                },
                "session_id": self.capture.session_id,
                "turn_number": self.capture.turn_number,
            }

        except Exception as e:
            logger.error(
                "send_message_failed",
                extra={
                    "session_id": self.capture.session_id,
                    "error": str(e),
                },
            )
            raise

    def send_message_streaming(
        self,
        prompt: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 1024,
        **kwargs,
    ) -> Iterator[str]:
        """Send a message and stream the response with capture.

        Yields response text chunks as they arrive, then captures the full response.

        Args:
            prompt: User message/prompt
            model: Claude model to use
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters for messages.stream()

        Yields:
            Text chunks from the response

        Note:
            Full response is captured after streaming completes.
            Check wrapper.last_capture_status for capture results.
        """
        # Capture user message
        user_capture = self.capture.capture_user_message(prompt)

        # Stream response
        full_response = []

        try:
            with self.client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            ) as stream:
                for text in stream.text_stream:
                    full_response.append(text)
                    yield text

            # Capture complete response
            response_text = "".join(full_response)
            agent_capture = self.capture.capture_agent_response(response_text)

            # Store capture status for retrieval
            self.last_capture_status = {
                "user": user_capture.get("status"),
                "agent": agent_capture.get("status"),
            }

        except Exception as e:
            logger.error(
                "streaming_failed",
                extra={
                    "session_id": self.capture.session_id,
                    "error": str(e),
                },
            )
            raise

    def _extract_text_content(self, message: Message) -> str:
        """Extract text content from API Message object.

        Args:
            message: Message object from API

        Returns:
            Concatenated text from all TextBlock content blocks
        """
        text_parts = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
        return "".join(text_parts)
