"""Rate limiting configuration example for AsyncSDKWrapper.

Demonstrates:
- Custom rate limit configuration for different API tiers
- Queue depth and timeout customization
- Handling QueueTimeoutError and QueueDepthExceededError
- Monitoring rate limiter state

Requirements:
- Python 3.11+
- ANTHROPIC_API_KEY environment variable set
- Docker services running (Qdrant, Embedding Service)

Run:
    python3 examples/async_sdk_rate_limiting.py
"""

import asyncio
import logging
import os
from pathlib import Path

from src.memory import AsyncSDKWrapper, QueueTimeoutError, QueueDepthExceededError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def tier1_configuration():
    """Example: Tier 1 rate limits (50 RPM, 30K TPM) - Default."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Example 1: Tier 1 Configuration (Default)")

    async with AsyncSDKWrapper(
        cwd=cwd,
        requests_per_minute=50,    # Tier 1 default
        tokens_per_minute=30000    # Tier 1 default
    ) as wrapper:

        logger.info(f"Rate limiter configured:")
        logger.info(f"  Requests/min: {wrapper.rate_limiter.requests_per_minute}")
        logger.info(f"  Tokens/min: {wrapper.rate_limiter.tokens_per_minute}")
        logger.info(f"  Max queue depth: {wrapper.rate_limiter.max_queue_depth}")
        logger.info(f"  Queue timeout: {wrapper.rate_limiter.queue_timeout}s")


async def tier2_configuration():
    """Example: Tier 2 rate limits (100 RPM, 100K TPM)."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Example 2: Tier 2 Configuration")

    async with AsyncSDKWrapper(
        cwd=cwd,
        requests_per_minute=100,   # Tier 2
        tokens_per_minute=100000   # Tier 2
    ) as wrapper:

        logger.info(f"Rate limiter configured for Tier 2:")
        logger.info(f"  Requests/min: {wrapper.rate_limiter.requests_per_minute}")
        logger.info(f"  Tokens/min: {wrapper.rate_limiter.tokens_per_minute}")


async def custom_queue_limits():
    """Example: Custom queue depth and timeout limits."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Example 3: Custom Queue Limits")

    async with AsyncSDKWrapper(
        cwd=cwd,
        requests_per_minute=50,
        tokens_per_minute=30000,
        max_queue_depth=25,      # Lower queue depth (default: 100)
        queue_timeout=30.0       # Shorter timeout (default: 60s)
    ) as wrapper:

        logger.info(f"Custom queue configuration:")
        logger.info(f"  Max queue depth: {wrapper.rate_limiter.max_queue_depth}")
        logger.info(f"  Queue timeout: {wrapper.rate_limiter.queue_timeout}s")


async def handling_queue_errors():
    """Example: Handling QueueTimeoutError and QueueDepthExceededError."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Example 4: Handling Queue Errors")

    # Configure very low limits to trigger errors
    async with AsyncSDKWrapper(
        cwd=cwd,
        requests_per_minute=2,     # Very low for demo
        tokens_per_minute=1000,
        max_queue_depth=3,         # Small queue
        queue_timeout=5.0          # Short timeout
    ) as wrapper:

        try:
            # Simulate burst of requests
            tasks = []
            for i in range(5):
                task = wrapper.send_message(
                    prompt=f"Request {i+1}",
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=50
                )
                tasks.append(task)

            # This should trigger queue errors
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for errors
            for i, result in enumerate(results):
                if isinstance(result, QueueDepthExceededError):
                    logger.warning(f"Request {i+1}: Queue depth exceeded")
                elif isinstance(result, QueueTimeoutError):
                    logger.warning(f"Request {i+1}: Queue timeout")
                elif isinstance(result, Exception):
                    logger.error(f"Request {i+1}: {type(result).__name__}: {result}")
                else:
                    logger.info(f"Request {i+1}: Success")

        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")


async def monitoring_rate_limiter_state():
    """Example: Monitor rate limiter state during execution."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Example 5: Monitoring Rate Limiter State")

    async with AsyncSDKWrapper(
        cwd=cwd,
        requests_per_minute=10,
        tokens_per_minute=5000
    ) as wrapper:

        limiter = wrapper.rate_limiter

        # Check initial state
        logger.info(f"Initial state:")
        logger.info(f"  Available requests: {limiter.available_requests:.2f}")
        logger.info(f"  Available tokens: {limiter.available_tokens:.2f}")

        # Make a request
        if os.getenv("ANTHROPIC_API_KEY"):
            logger.info("Sending request...")
            result = await wrapper.send_message(
                prompt="Hello",
                model="claude-3-5-sonnet-20241022",
                max_tokens=50
            )

            # Check state after request
            logger.info(f"After request:")
            logger.info(f"  Available requests: {limiter.available_requests:.2f}")
            logger.info(f"  Available tokens: {limiter.available_tokens:.2f}")
        else:
            logger.warning("ANTHROPIC_API_KEY not set - skipping actual request")


async def tier3_high_volume():
    """Example: Tier 3+ configuration for high volume (1000+ RPM)."""

    cwd = str(Path(__file__).parent.parent)

    logger.info("Example 6: Tier 3+ High Volume Configuration")

    async with AsyncSDKWrapper(
        cwd=cwd,
        requests_per_minute=1000,   # Tier 3+
        tokens_per_minute=400000,   # Tier 3+
        max_queue_depth=500,        # Larger queue for bursts
        queue_timeout=120.0         # Longer timeout
    ) as wrapper:

        logger.info(f"High volume configuration:")
        logger.info(f"  Requests/min: {wrapper.rate_limiter.requests_per_minute}")
        logger.info(f"  Tokens/min: {wrapper.rate_limiter.tokens_per_minute}")
        logger.info(f"  Max queue depth: {wrapper.rate_limiter.max_queue_depth}")
        logger.info(f"  Queue timeout: {wrapper.rate_limiter.queue_timeout}s")


async def main():
    """Run all rate limiting configuration examples."""

    print("=" * 60)
    print("AsyncSDKWrapper Rate Limiting Examples")
    print("=" * 60)

    # Example 1: Tier 1 (Default)
    print("\n1. Tier 1 Configuration (Default)")
    print("-" * 60)
    await tier1_configuration()

    # Example 2: Tier 2
    print("\n2. Tier 2 Configuration")
    print("-" * 60)
    await tier2_configuration()

    # Example 3: Custom Queue Limits
    print("\n3. Custom Queue Limits")
    print("-" * 60)
    await custom_queue_limits()

    # Example 4: Handling Queue Errors
    print("\n4. Handling Queue Errors")
    print("-" * 60)
    await handling_queue_errors()

    # Example 5: Monitoring State
    print("\n5. Monitoring Rate Limiter State")
    print("-" * 60)
    await monitoring_rate_limiter_state()

    # Example 6: Tier 3+ High Volume
    print("\n6. Tier 3+ High Volume Configuration")
    print("-" * 60)
    await tier3_high_volume()

    print("\n" + "=" * 60)
    print("Rate limiting examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
