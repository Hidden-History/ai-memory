"""Basic AsyncSDKWrapper usage example.

Demonstrates:
- Basic async/await usage
- Context manager pattern for automatic cleanup
- Session ID logging and conversation capture
- Rate limiting with token bucket algorithm
- Graceful degradation on storage failures

Requirements:
- Python 3.11+
- ANTHROPIC_API_KEY environment variable set
- Docker services running (Qdrant, Embedding Service)

Run:
    python3 examples/async_sdk_basic.py
"""

import asyncio
import logging
import os
from pathlib import Path

from src.memory import AsyncSDKWrapper

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def basic_conversation():
    """Basic conversation example with context manager."""

    # Get project directory
    cwd = str(Path(__file__).parent.parent)

    # Verify API key is set
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set in environment")
        return

    logger.info("Starting basic conversation example")

    # Context manager handles cleanup automatically
    async with AsyncSDKWrapper(
        cwd=cwd,
        requests_per_minute=50,  # Tier 1 default
        tokens_per_minute=30000,  # Tier 1 default
    ) as wrapper:

        # Log session information
        logger.info(f"Session ID: {wrapper.capture.session_id}")
        logger.info(f"Working directory: {cwd}")

        # Send first message
        logger.info("Sending first message...")
        result1 = await wrapper.send_message(
            prompt="What is the capital of France?",
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
        )

        print(f"\n[Turn {result1['turn_number']}]")
        print(f"Response: {result1['content']}\n")

        # Send second message (demonstrates conversation flow)
        logger.info("Sending second message...")
        result2 = await wrapper.send_message(
            prompt="What is its population?",
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
        )

        print(f"[Turn {result2['turn_number']}]")
        print(f"Response: {result2['content']}\n")

        logger.info(f"Conversation complete. Session: {result2['session_id']}")

        # Context manager automatically:
        # - Waits for background storage tasks to complete
        # - Closes Anthropic API client
        # - Cleans up resources


async def rate_limiting_example():
    """Example showing rate limiting in action."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Starting rate limiting example")

    async with AsyncSDKWrapper(
        cwd=cwd,
        requests_per_minute=5,  # Low limit for demo
        tokens_per_minute=5000,  # Low limit for demo
    ) as wrapper:

        logger.info("Sending 3 rapid requests...")

        # These requests will be queued if they exceed rate limits
        tasks = []
        for i in range(3):
            task = wrapper.send_message(
                prompt=f"Count to {i+1}",
                model="claude-3-5-sonnet-20241022",
                max_tokens=50,
            )
            tasks.append(task)

        # Wait for all to complete (with rate limiting)
        results = await asyncio.gather(*tasks)

        for i, result in enumerate(results):
            print(f"\n[Request {i+1}] {result['content'][:100]}...")

        logger.info("All requests completed successfully")


async def error_handling_example():
    """Example showing error handling with graceful degradation."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Starting error handling example")

    try:
        async with AsyncSDKWrapper(cwd=cwd) as wrapper:

            # This will succeed even if storage fails (graceful degradation)
            result = await wrapper.send_message(
                prompt="Hello!", model="claude-3-5-sonnet-20241022", max_tokens=50
            )

            print(f"\nResponse: {result['content']}")
            logger.info("Request completed (storage may have failed gracefully)")

    except Exception as e:
        logger.error(f"Request failed: {type(e).__name__}: {e}")


async def main():
    """Run all examples."""

    print("=" * 60)
    print("AsyncSDKWrapper Basic Examples")
    print("=" * 60)

    # Example 1: Basic conversation
    print("\n1. Basic Conversation")
    print("-" * 60)
    await basic_conversation()

    # Example 2: Rate limiting
    print("\n2. Rate Limiting")
    print("-" * 60)
    await rate_limiting_example()

    # Example 3: Error handling
    print("\n3. Error Handling")
    print("-" * 60)
    await error_handling_example()

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
