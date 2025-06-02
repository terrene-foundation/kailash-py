"""Rate limiting and throttling utilities for API requests in the Kailash SDK.

This module provides rate limiting capabilities to prevent API abuse and respect
service limits. It supports various rate limiting strategies including token bucket,
sliding window, and fixed window approaches.

Key Components:
- RateLimiter: Base rate limiter interface
- TokenBucketRateLimiter: Token bucket algorithm implementation
- SlidingWindowRateLimiter: Sliding window algorithm implementation
- RateLimitedAPINode: Wrapper node that adds rate limiting to any API node
"""

import asyncio
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Optional

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting behavior.

    This class defines the parameters for various rate limiting strategies.
    """

    max_requests: int = 100  # Maximum requests allowed
    time_window: float = 60.0  # Time window in seconds
    strategy: str = "token_bucket"  # Rate limiting strategy
    burst_limit: Optional[int] = None  # Maximum burst requests (for token bucket)
    backoff_factor: float = 1.0  # Backoff factor when rate limited
    max_backoff: float = 300.0  # Maximum backoff time in seconds


class RateLimiter(ABC):
    """Abstract base class for rate limiters.

    This class defines the interface that all rate limiters must implement.
    """

    def __init__(self, config: RateLimitConfig):
        """Initialize the rate limiter.

        Args:
            config: Rate limiting configuration
        """
        self.config = config
        self._lock = threading.Lock()

    @abstractmethod
    def can_proceed(self) -> bool:
        """Check if a request can proceed without hitting rate limits.

        Returns:
            True if request can proceed, False if rate limited
        """
        pass

    @abstractmethod
    def wait_time(self) -> float:
        """Get the time to wait before the next request can proceed.

        Returns:
            Wait time in seconds (0 if can proceed immediately)
        """
        pass

    @abstractmethod
    def consume(self) -> bool:
        """Consume a rate limit token for a request.

        Returns:
            True if token was consumed, False if rate limited
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the rate limiter state."""
        pass


class TokenBucketRateLimiter(RateLimiter):
    """Token bucket rate limiter implementation.

    This rate limiter uses the token bucket algorithm, which allows for burst
    requests up to the bucket capacity while maintaining a steady refill rate.

    Design Purpose:
    - Allow burst requests when quota is available
    - Smooth out request rate over time
    - Simple and efficient implementation
    """

    def __init__(self, config: RateLimitConfig):
        """Initialize the token bucket rate limiter.

        Args:
            config: Rate limiting configuration
        """
        super().__init__(config)
        self.bucket_size = config.burst_limit or config.max_requests
        self.tokens = float(self.bucket_size)
        self.refill_rate = config.max_requests / config.time_window
        self.last_refill = time.time()

    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        # Add tokens based on elapsed time and refill rate
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.bucket_size, self.tokens + tokens_to_add)
        self.last_refill = now

    def can_proceed(self) -> bool:
        """Check if a request can proceed without hitting rate limits.

        Returns:
            True if request can proceed, False if rate limited
        """
        with self._lock:
            self._refill_tokens()
            return self.tokens >= 1.0

    def wait_time(self) -> float:
        """Get the time to wait before the next request can proceed.

        Returns:
            Wait time in seconds (0 if can proceed immediately)
        """
        with self._lock:
            self._refill_tokens()
            if self.tokens >= 1.0:
                return 0.0

            # Calculate time needed to get one token
            tokens_needed = 1.0 - self.tokens
            return tokens_needed / self.refill_rate

    def consume(self) -> bool:
        """Consume a rate limit token for a request.

        Returns:
            True if token was consumed, False if rate limited
        """
        with self._lock:
            self._refill_tokens()
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False

    def reset(self) -> None:
        """Reset the rate limiter state."""
        with self._lock:
            self.tokens = float(self.bucket_size)
            self.last_refill = time.time()


class SlidingWindowRateLimiter(RateLimiter):
    """Sliding window rate limiter implementation.

    This rate limiter tracks request timestamps in a sliding window and
    enforces the rate limit based on the number of requests in the current window.

    Design Purpose:
    - More accurate rate limiting than fixed windows
    - Prevents sudden bursts at window boundaries
    - Memory usage grows with request rate
    """

    def __init__(self, config: RateLimitConfig):
        """Initialize the sliding window rate limiter.

        Args:
            config: Rate limiting configuration
        """
        super().__init__(config)
        self.requests: deque = deque()

    def _cleanup_old_requests(self) -> None:
        """Remove requests outside the current time window."""
        now = time.time()
        cutoff = now - self.config.time_window

        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

    def can_proceed(self) -> bool:
        """Check if a request can proceed without hitting rate limits.

        Returns:
            True if request can proceed, False if rate limited
        """
        with self._lock:
            self._cleanup_old_requests()
            return len(self.requests) < self.config.max_requests

    def wait_time(self) -> float:
        """Get the time to wait before the next request can proceed.

        Returns:
            Wait time in seconds (0 if can proceed immediately)
        """
        with self._lock:
            self._cleanup_old_requests()
            if len(self.requests) < self.config.max_requests:
                return 0.0

            # Wait until the oldest request falls outside the window
            oldest_request = self.requests[0]
            return oldest_request + self.config.time_window - time.time()

    def consume(self) -> bool:
        """Consume a rate limit token for a request.

        Returns:
            True if token was consumed, False if rate limited
        """
        with self._lock:
            self._cleanup_old_requests()
            if len(self.requests) < self.config.max_requests:
                self.requests.append(time.time())
                return True
            return False

    def reset(self) -> None:
        """Reset the rate limiter state."""
        with self._lock:
            self.requests.clear()


def create_rate_limiter(config: RateLimitConfig) -> RateLimiter:
    """Factory function to create rate limiters.

    Args:
        config: Rate limiting configuration

    Returns:
        Configured rate limiter instance

    Raises:
        ValueError: If strategy is not supported
    """
    if config.strategy == "token_bucket":
        return TokenBucketRateLimiter(config)
    elif config.strategy == "sliding_window":
        return SlidingWindowRateLimiter(config)
    else:
        raise ValueError(f"Unsupported rate limiting strategy: {config.strategy}")


@register_node()
class RateLimitedAPINode(Node):
    """Wrapper node that adds rate limiting to any API node.

    This node wraps any other API node and applies rate limiting to its execution.
    It can be used to ensure API calls respect service limits and prevent abuse.

    Design Purpose:
    - Add rate limiting to existing API nodes without modification
    - Support multiple rate limiting strategies
    - Provide automatic backoff and retry with rate limiting
    - Enable configuration-driven rate limiting policies

    Upstream Usage:
    - Workflow: Creates and configures with rate limiting policies
    - API integration workflows: Wraps other API nodes

    Downstream Consumers:
    - Same as the wrapped node
    """

    def __init__(
        self, wrapped_node: Node, rate_limit_config: RateLimitConfig, **kwargs
    ):
        """Initialize the rate limited API node.

        Args:
            wrapped_node: The node to wrap with rate limiting
            rate_limit_config: Rate limiting configuration
            **kwargs: Additional parameters passed to base Node
        """
        super().__init__(**kwargs)
        self.wrapped_node = wrapped_node
        self.rate_limiter = create_rate_limiter(rate_limit_config)
        self.config = rate_limit_config

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions (same as wrapped node)
        """
        # Return the same parameters as the wrapped node
        params = self.wrapped_node.get_parameters().copy()

        # Add rate limiting specific parameters
        params.update(
            {
                "respect_rate_limits": NodeParameter(
                    name="respect_rate_limits",
                    type=bool,
                    required=False,
                    default=True,
                    description="Whether to respect rate limits (if False, acts as passthrough)",
                ),
                "wait_on_rate_limit": NodeParameter(
                    name="wait_on_rate_limit",
                    type=bool,
                    required=False,
                    default=True,
                    description="Whether to wait when rate limited (if False, raises exception)",
                ),
            }
        )

        return params

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions (same as wrapped node)
        """
        # Return the same output schema as the wrapped node
        schema = self.wrapped_node.get_output_schema().copy()

        # Add rate limiting metadata
        schema["rate_limit_metadata"] = NodeParameter(
            name="rate_limit_metadata",
            type=dict,
            required=False,
            description="Rate limiting metadata and statistics",
        )

        return schema

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the wrapped node with rate limiting.

        Args:
            respect_rate_limits (bool, optional): Whether to respect rate limits
            wait_on_rate_limit (bool, optional): Whether to wait when rate limited
            **kwargs: Parameters passed to the wrapped node

        Returns:
            Dictionary containing the wrapped node's output plus rate limiting metadata

        Raises:
            NodeExecutionError: If rate limited and wait_on_rate_limit is False
        """
        respect_rate_limits = kwargs.pop("respect_rate_limits", True)
        wait_on_rate_limit = kwargs.pop("wait_on_rate_limit", True)

        # If rate limiting is disabled, just pass through
        if not respect_rate_limits:
            result = self.wrapped_node.run(**kwargs)
            result["rate_limit_metadata"] = {"rate_limiting_active": False}
            return result

        # Check rate limits
        attempts = 0
        max_attempts = 5
        total_wait_time = 0.0

        while attempts < max_attempts:
            if self.rate_limiter.can_proceed():
                # Consume rate limit token and execute
                if self.rate_limiter.consume():
                    start_time = time.time()
                    try:
                        result = self.wrapped_node.run(**kwargs)
                        execution_time = time.time() - start_time

                        # Add rate limiting metadata
                        result["rate_limit_metadata"] = {
                            "rate_limiting_active": True,
                            "attempts": attempts + 1,
                            "total_wait_time": total_wait_time,
                            "execution_time": execution_time,
                            "rate_limit_strategy": self.config.strategy,
                        }

                        return result

                    except Exception:
                        # If the wrapped node fails, we still consumed a token
                        # but we don't want to count this against rate limits
                        raise

            # Rate limited - decide what to do
            if not wait_on_rate_limit:
                raise NodeExecutionError(
                    f"Rate limited: too many requests. "
                    f"Max {self.config.max_requests} requests per {self.config.time_window}s"
                )

            # Calculate wait time with backoff
            wait_time = self.rate_limiter.wait_time()
            if attempts > 0:
                wait_time *= self.config.backoff_factor**attempts

            wait_time = min(wait_time, self.config.max_backoff)

            self.logger.info(
                f"Rate limited, waiting {wait_time:.2f}s before retry (attempt {attempts + 1})"
            )

            time.sleep(wait_time)
            total_wait_time += wait_time
            attempts += 1

        # If we've exhausted all attempts, raise an error
        raise NodeExecutionError(
            f"Rate limited after {max_attempts} attempts. "
            f"Total wait time: {total_wait_time:.2f}s"
        )


@register_node()
class AsyncRateLimitedAPINode(AsyncNode):
    """Asynchronous wrapper node that adds rate limiting to any async API node.

    This node provides the same functionality as RateLimitedAPINode but for
    asynchronous execution. It uses async/await for non-blocking operation.

    Design Purpose:
    - Add rate limiting to async API nodes without blocking the event loop
    - Support high-concurrency scenarios with rate limiting
    - Provide the same interface as RateLimitedAPINode but with async execution

    Upstream Usage:
    - AsyncLocalRuntime: Executes workflow with async support
    - Async API integration workflows: Wraps other async API nodes

    Downstream Consumers:
    - Same as the wrapped async node
    """

    def __init__(
        self, wrapped_node: AsyncNode, rate_limit_config: RateLimitConfig, **kwargs
    ):
        """Initialize the async rate limited API node.

        Args:
            wrapped_node: The async node to wrap with rate limiting
            rate_limit_config: Rate limiting configuration
            **kwargs: Additional parameters passed to base AsyncNode
        """
        super().__init__(**kwargs)
        self.wrapped_node = wrapped_node
        self.rate_limiter = create_rate_limiter(rate_limit_config)
        self.config = rate_limit_config
        self.sync_node = RateLimitedAPINode(wrapped_node, rate_limit_config, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return self.sync_node.get_parameters()

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        return self.sync_node.get_output_schema()

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous version for compatibility.

        Args:
            **kwargs: Parameters for the wrapped node

        Returns:
            Same as RateLimitedAPINode.run()
        """
        return self.sync_node.run(**kwargs)

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute the wrapped async node with rate limiting.

        Args:
            respect_rate_limits (bool, optional): Whether to respect rate limits
            wait_on_rate_limit (bool, optional): Whether to wait when rate limited
            **kwargs: Parameters passed to the wrapped node

        Returns:
            Dictionary containing the wrapped node's output plus rate limiting metadata

        Raises:
            NodeExecutionError: If rate limited and wait_on_rate_limit is False
        """
        respect_rate_limits = kwargs.pop("respect_rate_limits", True)
        wait_on_rate_limit = kwargs.pop("wait_on_rate_limit", True)

        # If rate limiting is disabled, just pass through
        if not respect_rate_limits:
            result = await self.wrapped_node.async_run(**kwargs)
            result["rate_limit_metadata"] = {"rate_limiting_active": False}
            return result

        # Check rate limits
        attempts = 0
        max_attempts = 5
        total_wait_time = 0.0

        while attempts < max_attempts:
            if self.rate_limiter.can_proceed():
                # Consume rate limit token and execute
                if self.rate_limiter.consume():
                    start_time = time.time()
                    try:
                        result = await self.wrapped_node.async_run(**kwargs)
                        execution_time = time.time() - start_time

                        # Add rate limiting metadata
                        result["rate_limit_metadata"] = {
                            "rate_limiting_active": True,
                            "attempts": attempts + 1,
                            "total_wait_time": total_wait_time,
                            "execution_time": execution_time,
                            "rate_limit_strategy": self.config.strategy,
                        }

                        return result

                    except Exception:
                        # If the wrapped node fails, we still consumed a token
                        # but we don't want to count this against rate limits
                        raise

            # Rate limited - decide what to do
            if not wait_on_rate_limit:
                raise NodeExecutionError(
                    f"Rate limited: too many requests. "
                    f"Max {self.config.max_requests} requests per {self.config.time_window}s"
                )

            # Calculate wait time with backoff
            wait_time = self.rate_limiter.wait_time()
            if attempts > 0:
                wait_time *= self.config.backoff_factor**attempts

            wait_time = min(wait_time, self.config.max_backoff)

            self.logger.info(
                f"Rate limited, waiting {wait_time:.2f}s before retry (attempt {attempts + 1})"
            )

            await asyncio.sleep(wait_time)
            total_wait_time += wait_time
            attempts += 1

        # If we've exhausted all attempts, raise an error
        raise NodeExecutionError(
            f"Rate limited after {max_attempts} attempts. "
            f"Total wait time: {total_wait_time:.2f}s"
        )
