"""AsyncSDKWrapper streaming response example.

Demonstrates:
- Streaming response handling
- Progressive chunk processing
- Real-time output display
- Retry logic for stream initialization
- Background conversation capture

Note: Current implementation buffers full response for reliability.
For true low-latency streaming, chunks would be yielded during retry.

Requirements:
- Python 3.11+
- ANTHROPIC_API_KEY environment variable set
- Docker services running (Qdrant, Embedding Service)

Run:
    python3 examples/async_sdk_streaming.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from src.memory import AsyncSDKWrapper

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def basic_streaming():
    """Basic streaming example with progressive output."""

    cwd = str(Path(__file__).parent.parent)

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set in environment")
        return

    logger.info("Starting basic streaming example")

    async with AsyncSDKWrapper(cwd=cwd) as wrapper:

        logger.info(f"Session ID: {wrapper.capture.session_id}")

        print("\nStreaming response:")
        print("-" * 60)

        # Stream response chunks
        async for chunk in wrapper.send_message_buffered(
            prompt="Write a haiku about Python programming",
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
        ):
            # Print chunk as it arrives (note: current implementation
            # returns full response after buffering for retry reliability)
            print(chunk, end="", flush=True)

        print("\n" + "-" * 60)
        logger.info("Streaming complete")


async def streaming_with_processing():
    """Stream response with progressive processing."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Starting streaming with processing example")

    async with AsyncSDKWrapper(cwd=cwd) as wrapper:

        prompt = "List 5 benefits of async programming in Python"
        print(f"\nPrompt: {prompt}")
        print("-" * 60)

        # Accumulate response for processing
        full_response = []

        async for chunk in wrapper.send_message_buffered(
            prompt=prompt, model="claude-3-5-sonnet-20241022", max_tokens=500
        ):
            full_response.append(chunk)
            print(chunk, end="", flush=True)

        print("\n" + "-" * 60)

        # Process complete response
        response_text = "".join(full_response)
        word_count = len(response_text.split())
        char_count = len(response_text)

        print(f"\nResponse stats:")
        print(f"  Words: {word_count}")
        print(f"  Characters: {char_count}")


async def streaming_multiple():
    """Stream multiple responses sequentially."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Starting multiple streaming example")

    async with AsyncSDKWrapper(cwd=cwd) as wrapper:

        prompts = [
            "What is async/await?",
            "How does rate limiting work?",
            "What is exponential backoff?",
        ]

        for i, prompt in enumerate(prompts, 1):
            print(f"\n[Question {i}] {prompt}")
            print("-" * 60)

            async for chunk in wrapper.send_message_buffered(
                prompt=prompt, model="claude-3-5-sonnet-20241022", max_tokens=150
            ):
                print(chunk, end="", flush=True)

            print("\n")

        logger.info(f"All streaming complete. Session: {wrapper.capture.session_id}")


async def streaming_with_retry_simulation():
    """Demonstrate retry behavior (if rate limited)."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Starting streaming with retry simulation")

    # Use low rate limits to potentially trigger rate limiting
    async with AsyncSDKWrapper(
        cwd=cwd, requests_per_minute=5, tokens_per_minute=5000
    ) as wrapper:

        print("\nSending rapid streaming requests...")
        print("(May trigger rate limiting and retry)\n")

        # Send multiple streaming requests rapidly
        for i in range(3):
            print(f"\n[Request {i+1}]")
            print("-" * 60)

            try:
                async for chunk in wrapper.send_message_buffered(
                    prompt=f"Count to {i+1}",
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=50,
                ):
                    print(chunk, end="", flush=True)

                print()  # Newline after chunk

            except Exception as e:
                logger.error(f"Request {i+1} failed: {type(e).__name__}: {e}")

        logger.info("Streaming requests complete")


async def streaming_long_response():
    """Stream a longer response to show progressive behavior."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Starting long response streaming example")

    async with AsyncSDKWrapper(cwd=cwd) as wrapper:

        prompt = "Explain the benefits of using async/await in Python for API calls"
        print(f"\nPrompt: {prompt}")
        print("-" * 60)

        # Track progress
        chars_received = 0
        start_time = asyncio.get_event_loop().time()

        async for chunk in wrapper.send_message_buffered(
            prompt=prompt, model="claude-3-5-sonnet-20241022", max_tokens=800
        ):
            chars_received += len(chunk)
            print(chunk, end="", flush=True)

        elapsed = asyncio.get_event_loop().time() - start_time

        print("\n" + "-" * 60)
        print(f"\nReceived {chars_received} characters in {elapsed:.2f}s")
        print(f"Rate: {chars_received/elapsed:.0f} chars/sec")


async def main():
    """Run all streaming examples."""

    print("=" * 60)
    print("AsyncSDKWrapper Streaming Examples")
    print("=" * 60)

    # Example 1: Basic streaming
    print("\n1. Basic Streaming")
    print("=" * 60)
    await basic_streaming()

    # Example 2: Streaming with processing
    print("\n2. Streaming with Processing")
    print("=" * 60)
    await streaming_with_processing()

    # Example 3: Multiple streaming requests
    print("\n3. Multiple Streaming Requests")
    print("=" * 60)
    await streaming_multiple()

    # Example 4: Streaming with retry
    print("\n4. Streaming with Retry Simulation")
    print("=" * 60)
    await streaming_with_retry_simulation()

    # Example 5: Long response streaming
    print("\n5. Long Response Streaming")
    print("=" * 60)
    await streaming_long_response()

    print("\n" + "=" * 60)
    print("Streaming examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
