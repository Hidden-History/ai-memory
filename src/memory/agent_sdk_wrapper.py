"""Claude Agent SDK wrapper with memory integration (TECH-DEBT-035 Phase 3).

Integrates claude-agent-sdk with the AI Memory system to enable:
- Automatic memory capture via SDK hooks
- Session continuity with conversation context
- Tool execution pattern capture
- Agent response archival to discussions collection

Architecture:
- AgentSDKWrapper: Main wrapper managing ClaudeSDKClient with hooks
- Hook callbacks: Capture tool use (PostToolUse) and responses (Stop)
- Fire-and-forget storage: Background tasks via asyncio.create_task()
- Memory type mapping: SDK events → V2.0 collections

Memory Type Mapping:
- PostToolUse (Write/Edit) → IMPLEMENTATION → code-patterns
- PostToolUse (Bash error) → ERROR_FIX → code-patterns
- Stop (agent response) → AGENT_RESPONSE → discussions
- Message stream → AGENT_RESPONSE → discussions (real-time)

References:
- BP-003: oversight/knowledge/best-practices/BP-003-agent-sdk-memory-integration.md
- Design: TECH-DEBT-035 Phase 3 spec
- Existing pattern: src/memory/async_sdk_wrapper.py (AsyncConversationCapture)
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import uuid4

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    HookMatcher,
    PostToolUseHookInput,
    StopHookInput,
    HookContext,
    ClaudeSDKError,
    CLINotFoundError,
    ProcessError,
)
from prometheus_client import Counter, Gauge

from .config import COLLECTION_DISCUSSIONS, COLLECTION_CODE_PATTERNS, get_config
from .deduplication import compute_content_hash, is_duplicate
from .models import MemoryType
from .project import detect_project
from .storage import MemoryStorage

# Prometheus Metrics
agent_sdk_hook_fires = Counter('ai_memory_agent_sdk_hook_fires_total', 'SDK hook invocations', ['hook_type'])
agent_sdk_storage_tasks = Counter('ai_memory_agent_sdk_storage_tasks_total', 'Storage tasks', ['status'])
agent_sdk_sessions = Gauge('ai_memory_agent_sdk_active_sessions', 'Active SDK sessions')
agent_sdk_dedup_checks = Counter(
    'ai_memory_agent_sdk_dedup_checks_total',
    'Deduplication checks',
    ['result']  # 'duplicate', 'unique', 'error'
)

__all__ = [
    "AgentSDKWrapper",
    "PendingMemory",
    "create_memory_enhanced_client",
]

logger = logging.getLogger("ai_memory.agent_sdk_wrapper")


@dataclass
class PendingMemory:
    """Memory waiting in batch queue.

    Attributes:
        content: Memory content
        memory_type: Memory type (IMPLEMENTATION, ERROR_FIX, AGENT_RESPONSE)
        collection: Target collection name
        source: Source hook name
        session_id: Session identifier
        turn_number: Turn number in session
        timestamp: Creation timestamp
        content_hash: SHA-256 hash of content
    """

    content: str
    memory_type: "MemoryType"
    collection: str
    source: str
    session_id: str
    turn_number: int
    timestamp: datetime
    content_hash: str


class AgentSDKWrapper:
    """Agent SDK wrapper with automatic memory capture via hooks.

    Wraps ClaudeSDKClient to provide:
    - PostToolUse hook → captures code patterns (implementation, error_fix)
    - Stop hook → captures agent responses (agent_response)
    - Background storage with fire-and-forget pattern
    - Session continuity and conversation context
    - Graceful degradation on storage failures

    Example:
        >>> async def main():
        ...     async with AgentSDKWrapper(cwd="/path") as wrapper:
        ...         await wrapper.query("Write a hello world function")
        ...         async for message in wrapper.receive_response():
        ...             print(message.content)
        >>>
        >>> asyncio.run(main())
    """

    def __init__(
        self,
        cwd: str,
        api_key: Optional[str] = None,
        storage: Optional[MemoryStorage] = None,
        session_id: Optional[str] = None,
        options: Optional[ClaudeAgentOptions] = None,
    ):
        """Initialize Agent SDK wrapper with memory hooks.

        Args:
            cwd: Current working directory for project detection
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            storage: Optional MemoryStorage instance (creates new if not provided)
            session_id: Optional session identifier (generates UUID if not provided)
            options: Optional ClaudeAgentOptions (creates with hooks if not provided)

        Raises:
            ValueError: If ANTHROPIC_API_KEY not found
            CLINotFoundError: If Claude Code CLI not installed
        """
        self.cwd = cwd
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Provide api_key parameter or set environment variable."
            )

        self.storage = storage or MemoryStorage()
        self.session_id = session_id or f"agent_sdk_{uuid4().hex[:8]}"
        self.turn_number = 0
        self._turn_lock = asyncio.Lock()  # MEDIUM-9: Prevent race condition
        self._storage_tasks: List[asyncio.Task] = []

        # Batching configuration (TECH-DEBT-042, TECH-DEBT-043)
        self._batch_queue: List[PendingMemory] = []
        self._batch_lock = asyncio.Lock()
        self._batch_size = 10  # Flush when queue reaches this size
        self._batch_flush_interval = 5.0  # Seconds between auto-flushes
        self._flush_task: Optional[asyncio.Task] = None

        # Set ANTHROPIC_API_KEY for SDK
        os.environ["ANTHROPIC_API_KEY"] = self.api_key

        # Register hooks for memory capture
        if options is None:
            options = self._create_default_options()

        # Initialize SDK client
        try:
            self.client = ClaudeSDKClient(options=options)
            agent_sdk_sessions.inc()
        except CLINotFoundError as e:
            logger.error(
                "claude_cli_not_found",
                extra={
                    "error": str(e),
                    "install_instructions": "npm install -g @anthropic-ai/claude-code",
                },
            )
            raise

        logger.info(
            "agent_sdk_wrapper_initialized",
            extra={
                "session_id": self.session_id,
                "cwd": cwd,
            },
        )

    def _create_default_options(self) -> ClaudeAgentOptions:
        """Create default ClaudeAgentOptions with memory hooks."""
        return ClaudeAgentOptions(
            cwd=self.cwd,
            hooks={
                "PostToolUse": [
                    HookMatcher(
                        matcher="Write|Edit|NotebookEdit",
                        hooks=[self._post_tool_use_hook],
                        timeout=0.5,  # <500ms requirement
                    )
                ],
                "Stop": [
                    HookMatcher(
                        hooks=[self._stop_hook],
                        timeout=0.5,
                    )
                ],
            },
        )

    def _get_group_id(self) -> str:
        """Get project group_id from working directory.

        Uses detect_project() to normalize cwd into a project identifier
        suitable for Qdrant group_id filtering.

        Returns:
            Normalized project name (e.g., "ai-memory-module")
        """
        return detect_project(self.cwd)

    async def _start_batch_flusher(self):
        """Start background task that flushes batches periodically.

        Creates an async task that runs _periodic_flush() in the background,
        flushing the batch queue every _batch_flush_interval seconds.
        """
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.debug(
            "batch_flusher_started",
            extra={
                "session_id": self.session_id,
                "flush_interval": self._batch_flush_interval,
            },
        )

    async def _periodic_flush(self):
        """Flush batches every N seconds.

        Runs indefinitely until cancelled, flushing the batch queue
        at regular intervals defined by _batch_flush_interval.
        """
        try:
            while True:
                await asyncio.sleep(self._batch_flush_interval)
                await self._flush_batch()
        except asyncio.CancelledError:
            logger.debug(
                "periodic_flush_cancelled",
                extra={"session_id": self.session_id},
            )
            raise

    async def _flush_batch(self):
        """Flush all pending memories to storage.

        Atomically extracts all pending memories from the queue and
        stores them one by one. Handles errors gracefully per-item.
        """
        async with self._batch_lock:
            if not self._batch_queue:
                return

            batch = self._batch_queue.copy()
            self._batch_queue.clear()

        logger.info(
            "flushing_batch",
            extra={
                "session_id": self.session_id,
                "batch_size": len(batch),
            },
        )

        for memory in batch:
            try:
                # Store each memory using the existing storage logic
                # MEDIUM-9: Turn number already set in PendingMemory
                loop = asyncio.get_running_loop()

                from functools import partial
                store_func = partial(
                    self.storage.store_memory,
                    memory.content,
                    self.cwd,
                    memory.memory_type,
                    memory.source,
                    memory.session_id,
                    memory.collection,
                    # Note: turn_number not supported by MemoryPayload
                    # Note: Don't pass timestamp - storage creates its own
                )

                await loop.run_in_executor(None, store_func)

                logger.debug(
                    "batch_item_stored",
                    extra={
                        "session_id": self.session_id,
                        "type": memory.memory_type.value,
                        "collection": memory.collection,
                    },
                )

            except Exception as e:
                logger.error(
                    "batch_item_storage_failed",
                    extra={
                        "session_id": self.session_id,
                        "error": str(e),
                    },
                )
                agent_sdk_storage_tasks.labels(status='batch_error').inc()

    async def _queue_memory(
        self,
        content: str,
        memory_type: MemoryType,
        collection: str,
        source: str,
    ) -> None:
        """Add memory to batch queue with deduplication check.

        Checks for duplicates in both the pending queue (fast) and Qdrant (thorough),
        then adds to the batch queue if unique. Triggers flush if batch size reached.

        Args:
            content: Memory content
            memory_type: Memory type (IMPLEMENTATION, ERROR_FIX, AGENT_RESPONSE)
            collection: Target collection (code-patterns or discussions)
            source: Source hook name
        """
        # Stage 1: Compute hash
        content_hash = compute_content_hash(content)

        # MEDIUM-9: Thread-safe turn_number increment
        async with self._turn_lock:
            self.turn_number += 1
            current_turn = self.turn_number

        async with self._batch_lock:
            # Stage 2a: Check pending queue first (fast, in-memory)
            for pending in self._batch_queue:
                if pending.content_hash == content_hash:
                    logger.debug(
                        "duplicate_in_pending_queue",
                        extra={
                            "content_hash": content_hash[:16],
                            "collection": collection,
                        },
                    )
                    agent_sdk_dedup_checks.labels(result='duplicate').inc()
                    agent_sdk_storage_tasks.labels(status='skipped_duplicate').inc()
                    return

            # Stage 2b: Check Qdrant (slower but necessary)
            try:
                result = await is_duplicate(
                    collection=collection,
                    content_hash=content_hash,
                    embedding=None,  # Skip semantic check for speed
                    group_id=self._get_group_id(),
                )
                if result.is_duplicate:
                    logger.debug(
                        "duplicate_in_qdrant",
                        extra={
                            "content_hash": content_hash[:16],
                            "existing_id": result.existing_id,
                            "collection": collection,
                        },
                    )
                    agent_sdk_dedup_checks.labels(result='duplicate').inc()
                    agent_sdk_storage_tasks.labels(status='skipped_duplicate').inc()
                    return

                agent_sdk_dedup_checks.labels(result='unique').inc()

            except Exception as e:
                # Graceful degradation: queue anyway if dedup check fails
                logger.warning(
                    "dedup_check_failed_queueing_anyway",
                    extra={"error": str(e)},
                )
                agent_sdk_dedup_checks.labels(result='error').inc()

            # Stage 3: Add to queue
            self._batch_queue.append(
                PendingMemory(
                    content=content,
                    memory_type=memory_type,
                    collection=collection,
                    source=source,
                    session_id=self.session_id,
                    turn_number=current_turn,
                    timestamp=datetime.now(timezone.utc),
                    content_hash=content_hash,
                )
            )

            logger.debug(
                "memory_queued",
                extra={
                    "session_id": self.session_id,
                    "queue_size": len(self._batch_queue),
                    "type": memory_type.value,
                },
            )

            # Stage 4: Flush if batch size reached
            if len(self._batch_queue) >= self._batch_size:
                # Release lock before flushing to avoid deadlock
                # Create task outside the lock
                should_flush = True
            else:
                should_flush = False

        # Flush outside the lock to avoid blocking
        if should_flush:
            asyncio.create_task(self._flush_batch())

    async def _post_tool_use_hook(
        self,
        input_data: PostToolUseHookInput,
        tool_use_id: Optional[str],
        context: HookContext,
    ) -> Dict[str, Any]:
        """Capture tool use patterns in background (PostToolUse hook).

        Maps tool executions to memory types:
        - Write/Edit/NotebookEdit → IMPLEMENTATION (code-patterns)
        - Bash with error → ERROR_FIX (code-patterns)

        Args:
            input_data: Hook input with tool name, input, response
            tool_use_id: Tool use identifier
            context: Hook context

        Returns:
            Empty dict (hook doesn't modify flow)
        """
        agent_sdk_hook_fires.labels(hook_type='PostToolUse').inc()

        try:
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input", {})
            tool_response = input_data.get("tool_response", "")

            # Determine memory type based on tool and result
            if tool_name == "Bash":
                # HIGH-7: Improved error detection - check exit_code properly
                exit_code = None
                if isinstance(tool_response, dict):
                    exit_code = tool_response.get("exit_code")
                    # Coerce string exit codes to int
                    if isinstance(exit_code, str):
                        try:
                            exit_code = int(exit_code)
                        except (ValueError, TypeError):
                            exit_code = None

                # Detect error: non-zero exit code OR explicit error in structured response
                is_error = (exit_code is not None and exit_code != 0) or \
                           (isinstance(tool_response, dict) and tool_response.get("error"))

                if is_error:
                    memory_type = MemoryType.ERROR_FIX
                    content = f"Error fix pattern (Bash): {tool_input.get('command', '')}\nResult: {tool_response}"
                else:
                    # Don't capture successful Bash commands
                    return {}
            elif tool_name in ("Write", "Edit", "NotebookEdit"):
                memory_type = MemoryType.IMPLEMENTATION
                file_path = tool_input.get("file_path", "unknown")
                content = f"Code pattern ({tool_name}): {file_path}\n{tool_response}"
            else:
                # Unknown tool, skip
                return {}

            # Queue to batch (with deduplication)
            task = asyncio.create_task(
                self._queue_memory(
                    content=content,
                    memory_type=memory_type,
                    collection=COLLECTION_CODE_PATTERNS,
                    source="PostToolUse",
                )
            )
            self._storage_tasks.append(task)
            agent_sdk_storage_tasks.labels(status='created').inc()

        except Exception as e:
            # Graceful degradation - log and continue
            logger.warning(
                "post_tool_hook_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )

        return {}  # Return immediately (<500ms)

    async def _stop_hook(
        self,
        input_data: StopHookInput,
        tool_use_id: Optional[str],
        context: HookContext,
    ) -> Dict[str, Any]:
        """Capture final agent response at session end (Stop hook).

        Args:
            input_data: Hook input with session data
            tool_use_id: Tool use identifier
            context: Hook context

        Returns:
            Empty dict (hook doesn't modify flow)
        """
        agent_sdk_hook_fires.labels(hook_type='Stop').inc()

        try:
            # Extract transcript path to read final response
            transcript_path = input_data.get("transcript_path", "")

            if transcript_path and os.path.exists(transcript_path):
                # Read last agent message from transcript
                # Fork to background
                task = asyncio.create_task(
                    self._extract_and_store_response(transcript_path)
                )
                self._storage_tasks.append(task)
                agent_sdk_storage_tasks.labels(status='created').inc()

        except Exception as e:
            logger.warning(
                "stop_hook_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )

        return {}

    async def _extract_and_store_response(self, transcript_path: str):
        """Extract and store agent response from transcript."""
        try:
            # MEDIUM-11: Wrap file read with proper error handling
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    transcript = f.read()
            except (FileNotFoundError, PermissionError, OSError) as file_err:
                logger.warning(
                    "transcript_file_read_failed",
                    extra={
                        "session_id": self.session_id,
                        "transcript_path": transcript_path,
                        "error": str(file_err),
                    },
                )
                return  # Graceful degradation

            # Queue as agent response
            await self._queue_memory(
                content=transcript,
                memory_type=MemoryType.AGENT_RESPONSE,
                collection=COLLECTION_DISCUSSIONS,
                source="Stop",
            )

        except Exception as e:
            agent_sdk_storage_tasks.labels(status='failed').inc()
            logger.warning(
                "response_extraction_failed",
                extra={
                    "session_id": self.session_id,
                    "transcript_path": transcript_path,
                    "error": str(e),
                },
            )

    async def _store_memory_background(
        self,
        content: str,
        memory_type: MemoryType,
        collection: str,
        source: str,
    ):
        """Store memory in background (fire-and-forget) with deduplication check.

        Args:
            content: Memory content
            memory_type: Memory type (IMPLEMENTATION, ERROR_FIX, AGENT_RESPONSE)
            collection: Target collection (code-patterns or discussions)
            source: Source hook name
        """
        try:
            # Stage 1: Compute hash
            content_hash = compute_content_hash(content)

            # Stage 2: Check for duplicate (hash-based, fast)
            try:
                result = await is_duplicate(
                    collection=collection,
                    content_hash=content_hash,
                    embedding=None,  # Skip semantic check for speed
                    group_id=self._get_group_id(),
                )
                if result.is_duplicate:
                    logger.debug(
                        "skipping_duplicate_memory",
                        extra={
                            "content_hash": content_hash[:16],
                            "existing_id": result.existing_id,
                            "collection": collection,
                        },
                    )
                    agent_sdk_dedup_checks.labels(result='duplicate').inc()
                    agent_sdk_storage_tasks.labels(status='skipped_duplicate').inc()
                    return None

                agent_sdk_dedup_checks.labels(result='unique').inc()

            except Exception as e:
                # Graceful degradation: store anyway if dedup check fails
                logger.warning(
                    "dedup_check_failed_storing_anyway",
                    extra={"error": str(e)},
                )
                agent_sdk_dedup_checks.labels(result='error').inc()

            # Stage 3: Store if not duplicate
            # MEDIUM-9: Thread-safe turn_number increment
            async with self._turn_lock:
                self.turn_number += 1
                current_turn = self.turn_number

            # CRITICAL-1: Fixed store_memory() call - use kwargs for extra fields
            # Run sync storage in executor (storage.store_memory is sync)
            loop = asyncio.get_running_loop()

            # Partial function to pass kwargs correctly through executor
            from functools import partial
            store_func = partial(
                self.storage.store_memory,
                content,
                self.cwd,
                memory_type,
                source,
                self.session_id,
                collection,
                turn_number=current_turn,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            await loop.run_in_executor(None, store_func)

            logger.info(
                "memory_stored_background",
                extra={
                    "session_id": self.session_id,
                    "type": memory_type.value,
                    "collection": collection,
                    "source": source,
                },
            )

        except Exception as e:
            agent_sdk_storage_tasks.labels(status='failed').inc()
            logger.warning(
                "background_storage_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        await self.close()

    async def connect(self):
        """Connect to Claude Code CLI and start batch flusher."""
        try:
            await self.client.connect()

            # Start periodic batch flusher
            await self._start_batch_flusher()

            logger.info(
                "agent_sdk_connected",
                extra={"session_id": self.session_id},
            )
        except (CLINotFoundError, ProcessError) as e:
            logger.error(
                "agent_sdk_connection_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            raise

    async def disconnect(self):
        """Disconnect from Claude Code CLI."""
        try:
            await self.client.disconnect()
            logger.info(
                "agent_sdk_disconnected",
                extra={"session_id": self.session_id},
            )
        except Exception as e:
            logger.warning(
                "disconnect_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )

    async def close(self):
        """Cleanup resources, flush batch, and wait for background tasks."""
        # Cancel periodic flusher
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                logger.debug(
                    "flush_task_cancelled",
                    extra={"session_id": self.session_id},
                )

        # Final flush of any remaining memories in batch queue
        try:
            await self._flush_batch()
        except Exception as e:
            logger.warning(
                "final_batch_flush_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )

        # Wait for storage tasks to complete
        if self._storage_tasks:
            try:
                done, pending = await asyncio.wait(
                    self._storage_tasks,
                    timeout=10.0,
                    return_when=asyncio.ALL_COMPLETED,
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()

                successes = sum(1 for task in done if not task.exception())
                logger.info(
                    "storage_cleanup_complete",
                    extra={
                        "session_id": self.session_id,
                        "completed": successes,
                        "pending": len(pending),
                    },
                )

            except asyncio.TimeoutError:
                logger.warning(
                    "storage_cleanup_timeout",
                    extra={
                        "session_id": self.session_id,
                        "pending_tasks": len(self._storage_tasks),
                    },
                )

        # Disconnect client
        await self.disconnect()
        agent_sdk_sessions.dec()

    async def query(self, prompt: str, **kwargs) -> None:
        """Send a query to Claude via the SDK.

        Args:
            prompt: User message/prompt
            **kwargs: Additional parameters for query
        """
        try:
            await self.client.query(prompt, **kwargs)
        except ClaudeSDKError as e:
            logger.error(
                "query_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            raise

    async def receive_response(self):
        """Receive response messages from Claude.

        Yields:
            Message objects from the SDK
        """
        try:
            async for message in self.client.receive_response():
                yield message
        except ClaudeSDKError as e:
            logger.error(
                "receive_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                },
            )
            raise


async def create_memory_enhanced_client(
    project_id: str,
    cwd: str,
    api_key: Optional[str] = None,
    storage: Optional[MemoryStorage] = None,
) -> AgentSDKWrapper:
    """Factory for memory-enhanced Agent SDK client (BP-003 recommended pattern).

    Creates an AgentSDKWrapper with:
    - PostToolUse hooks for code pattern capture
    - Stop hooks for agent response capture
    - Background storage (fire-and-forget)
    - Session continuity

    Args:
        project_id: Project identifier for group_id filtering
        cwd: Current working directory
        api_key: Optional Anthropic API key
        storage: Optional MemoryStorage instance

    Returns:
        Connected AgentSDKWrapper instance

    Example:
        >>> client = await create_memory_enhanced_client(
        ...     project_id="my-project",
        ...     cwd="/path/to/project"
        ... )
        >>> await client.query("Write a test function")
        >>> async for message in client.receive_response():
        ...     print(message.content)
        >>> await client.close()
    """
    wrapper = AgentSDKWrapper(
        cwd=cwd,
        api_key=api_key,
        storage=storage,
        session_id=f"agent_{project_id}_{uuid4().hex[:8]}",
    )

    await wrapper.connect()

    logger.info(
        "memory_enhanced_client_created",
        extra={
            "project_id": project_id,
            "session_id": wrapper.session_id,
        },
    )

    return wrapper
