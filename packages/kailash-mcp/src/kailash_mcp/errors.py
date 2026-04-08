"""Enhanced error handling for MCP implementations.

This module provides structured error codes, error recovery strategies,
and enhanced error handling capabilities that build on top of the
official MCP SDK error handling.

Features:
- Structured error codes following MCP protocol
- Error recovery and retry strategies
- Circuit breaker patterns
- Error aggregation and reporting
- Graceful degradation mechanisms

Examples:
    Structured error handling:

    >>> try:
    ...     result = await client.call_tool("search", {"query": "test"})
    ... except MCPError as e:
    ...     if e.is_retryable():
    ...         await asyncio.sleep(e.get_retry_delay())
    ...         # retry logic
    ...     else:
    ...         logger.error(f"Non-retryable error: {e}")

    Error recovery with circuit breaker:

    >>> circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)
    >>> async with circuit_breaker:
    ...     result = await risky_operation()
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union

logger = logging.getLogger(__name__)


class MCPErrorCode(Enum):
    """Standardized MCP error codes following JSON-RPC conventions."""

    # Standard JSON-RPC errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP-specific errors (in reserved range -32099 to -32000)
    TRANSPORT_ERROR = -32001
    AUTHENTICATION_FAILED = -32002
    AUTHORIZATION_FAILED = -32003
    RATE_LIMITED = -32004
    TOOL_NOT_FOUND = -32005
    TOOL_EXECUTION_FAILED = -32006
    RESOURCE_NOT_FOUND = -32007
    RESOURCE_ACCESS_FAILED = -32008
    SERVER_UNAVAILABLE = -32009
    PROTOCOL_VERSION_MISMATCH = -32010
    CAPABILITY_NOT_SUPPORTED = -32011
    SESSION_EXPIRED = -32012
    CIRCUIT_BREAKER_OPEN = -32013

    # Application-specific errors (positive codes)
    VALIDATION_ERROR = 1001
    BUSINESS_LOGIC_ERROR = 1002
    EXTERNAL_SERVICE_ERROR = 1003
    DATA_INTEGRITY_ERROR = 1004
    QUOTA_EXCEEDED = 1005
    REQUEST_TIMEOUT = 1006
    REQUEST_CANCELLED = 1007


class MCPError(Exception):
    """Enhanced MCP error with structured information.

    Extends the basic exception with MCP-specific error codes,
    retry information, and recovery hints.

    Args:
        message: Human-readable error message
        error_code: Structured error code
        data: Additional error data
        retryable: Whether the error is retryable
        retry_after: Suggested retry delay in seconds

    Examples:
        Create structured error:

        >>> error = MCPError(
        ...     "Tool execution failed",
        ...     error_code=MCPErrorCode.TOOL_EXECUTION_FAILED,
        ...     data={"tool": "search", "reason": "timeout"},
        ...     retryable=True,
        ...     retry_after=5
        ... )
    """

    def __init__(
        self,
        message: str,
        error_code: Union[MCPErrorCode, int] = MCPErrorCode.INTERNAL_ERROR,
        data: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
        retry_after: Optional[float] = None,
        cause: Optional[Exception] = None,
    ):
        """Initialize MCP error."""
        super().__init__(message)
        self.message = message
        self.error_code = (
            error_code
            if isinstance(error_code, MCPErrorCode)
            else MCPErrorCode(error_code)
        )
        self.data = data or {}
        self.retryable = retryable
        self.retry_after = retry_after
        self.cause = cause
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format for JSON-RPC."""
        error_dict = {"code": self.error_code.value, "message": self.message}

        if self.data:
            error_dict["data"] = self.data

        return error_dict

    def is_retryable(self) -> bool:
        """Check if error is retryable."""
        return self.retryable

    def get_retry_delay(self) -> float:
        """Get suggested retry delay."""
        if self.retry_after is not None:
            return self.retry_after

        # Default retry delays based on error type
        retry_delays = {
            MCPErrorCode.RATE_LIMITED: 60.0,
            MCPErrorCode.SERVER_UNAVAILABLE: 30.0,
            MCPErrorCode.TRANSPORT_ERROR: 5.0,
            MCPErrorCode.TOOL_EXECUTION_FAILED: 2.0,
            MCPErrorCode.EXTERNAL_SERVICE_ERROR: 10.0,
        }

        return retry_delays.get(self.error_code, 1.0)

    def get_severity(self) -> str:
        """Get error severity level."""
        high_severity = {
            MCPErrorCode.AUTHENTICATION_FAILED,
            MCPErrorCode.AUTHORIZATION_FAILED,
            MCPErrorCode.DATA_INTEGRITY_ERROR,
            MCPErrorCode.PROTOCOL_VERSION_MISMATCH,
        }

        medium_severity = {
            MCPErrorCode.TOOL_NOT_FOUND,
            MCPErrorCode.RESOURCE_NOT_FOUND,
            MCPErrorCode.VALIDATION_ERROR,
            MCPErrorCode.BUSINESS_LOGIC_ERROR,
        }

        if self.error_code in high_severity:
            return "high"
        elif self.error_code in medium_severity:
            return "medium"
        else:
            return "low"


class TransportError(MCPError):
    """Transport-related error."""

    def __init__(self, message: str, transport_type: str = "unknown", **kwargs):
        kwargs.setdefault("error_code", MCPErrorCode.TRANSPORT_ERROR)
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("data", {})["transport_type"] = transport_type
        super().__init__(message, **kwargs)


class AuthenticationError(MCPError):
    """Authentication-related error."""

    def __init__(self, message: str, auth_type: str = "unknown", **kwargs):
        kwargs.setdefault("error_code", MCPErrorCode.AUTHENTICATION_FAILED)
        kwargs.setdefault("retryable", False)
        kwargs.setdefault("data", {})["auth_type"] = auth_type
        super().__init__(message, **kwargs)


class AuthorizationError(MCPError):
    """Authorization-related error."""

    def __init__(self, message: str, required_permission: str = "", **kwargs):
        kwargs.setdefault("error_code", MCPErrorCode.AUTHORIZATION_FAILED)
        kwargs.setdefault("retryable", False)
        kwargs.setdefault("data", {})["required_permission"] = required_permission
        super().__init__(message, **kwargs)


class RateLimitError(MCPError):
    """Rate limiting error."""

    def __init__(self, message: str, retry_after: float = 60.0, **kwargs):
        kwargs.setdefault("error_code", MCPErrorCode.RATE_LIMITED)
        kwargs.setdefault("retryable", True)
        kwargs["retry_after"] = retry_after
        super().__init__(message, **kwargs)


class ToolError(MCPError):
    """Tool-related error."""

    def __init__(self, message: str, tool_name: str = "", **kwargs):
        kwargs.setdefault("error_code", MCPErrorCode.TOOL_EXECUTION_FAILED)
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("data", {})["tool_name"] = tool_name
        super().__init__(message, **kwargs)


class ResourceError(MCPError):
    """Resource-related error."""

    def __init__(self, message: str, resource_uri: str = "", **kwargs):
        kwargs.setdefault("error_code", MCPErrorCode.RESOURCE_ACCESS_FAILED)
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("data", {})["resource_uri"] = resource_uri
        super().__init__(message, **kwargs)


class ServiceDiscoveryError(MCPError):
    """Service discovery related error."""

    def __init__(self, message: str, discovery_type: str = "unknown", **kwargs):
        kwargs.setdefault("error_code", MCPErrorCode.SERVER_UNAVAILABLE)
        kwargs.setdefault("retryable", True)
        kwargs.setdefault("data", {})["discovery_type"] = discovery_type
        super().__init__(message, **kwargs)


class ValidationError(MCPError):
    """Validation error."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("error_code", MCPErrorCode.VALIDATION_ERROR)
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class RetryStrategy(ABC):
    """Abstract base class for retry strategies."""

    @abstractmethod
    def should_retry(self, error: MCPError, attempt: int) -> bool:
        """Determine if operation should be retried."""
        pass

    @abstractmethod
    def get_delay(self, error: MCPError, attempt: int) -> float:
        """Get delay before next retry attempt."""
        pass


class ExponentialBackoffRetry(RetryStrategy):
    """Exponential backoff retry strategy.

    Args:
        max_attempts: Maximum retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Exponential backoff factor
        jitter: Add random jitter to prevent thundering herd

    Examples:
        Create retry strategy:

        >>> retry = ExponentialBackoffRetry(
        ...     max_attempts=5,
        ...     base_delay=1.0,
        ...     max_delay=60.0,
        ...     backoff_factor=2.0,
        ...     jitter=True
        ... )
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
    ):
        """Initialize exponential backoff retry."""
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

    def should_retry(self, error: MCPError, attempt: int) -> bool:
        """Check if operation should be retried."""
        return (
            attempt < self.max_attempts
            and error.is_retryable()
            and error.get_severity() != "high"
        )

    def get_delay(self, error: MCPError, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        # Use error's suggested delay if available
        if error.retry_after is not None:
            delay = error.retry_after
        else:
            delay = self.base_delay * (self.backoff_factor ** (attempt - 1))

        # Apply maximum delay limit
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd
        if self.jitter:
            import random

            delay *= 0.5 + random.random() * 0.5

        return delay


class CircuitBreakerRetry(RetryStrategy):
    """Circuit breaker retry strategy.

    Implements the circuit breaker pattern to prevent cascading failures.

    Args:
        failure_threshold: Number of failures before opening circuit
        timeout: Time to wait before trying to close circuit
        success_threshold: Number of successes needed to close circuit

    Examples:
        Create circuit breaker:

        >>> circuit_breaker = CircuitBreakerRetry(
        ...     failure_threshold=5,
        ...     timeout=60.0,
        ...     success_threshold=3
        ... )
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        success_threshold: int = 3,
    ):
        """Initialize circuit breaker."""
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold

        # Circuit breaker state
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open

    def should_retry(self, error: MCPError, attempt: int) -> bool:
        """Check if operation should be retried based on circuit state."""
        now = time.time()

        if self.state == "open":
            # Check if timeout has passed
            if now - self.last_failure_time > self.timeout:
                self.state = "half-open"
                self.success_count = 0
                return True
            else:
                return False

        elif self.state == "half-open":
            # Allow limited retries to test if service recovered
            return self.success_count < self.success_threshold

        else:  # closed
            return error.is_retryable()

    def get_delay(self, error: MCPError, attempt: int) -> float:
        """Get delay based on circuit state."""
        if self.state == "open":
            return self.timeout - (time.time() - self.last_failure_time)
        else:
            return error.get_retry_delay()

    def on_success(self):
        """Record successful operation."""
        if self.state == "half-open":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = "closed"
                self.failure_count = 0

    def on_failure(self, error: MCPError):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "half-open":
            self.state = "open"
        elif self.failure_count >= self.failure_threshold:
            self.state = "open"


class RetryableOperation:
    """Wrapper for operations with retry logic.

    Args:
        retry_strategy: Retry strategy to use
        logger: Optional logger for retry events

    Examples:
        Execute operation with retries:

        >>> retry_op = RetryableOperation(
        ...     ExponentialBackoffRetry(max_attempts=5)
        ... )
        >>> result = await retry_op.execute(risky_function, arg1, arg2)
    """

    def __init__(
        self, retry_strategy: RetryStrategy, logger: Optional[logging.Logger] = None
    ):
        """Initialize retryable operation."""
        self.retry_strategy = retry_strategy
        self.logger = logger or logging.getLogger(__name__)

    async def execute(self, func, *args, **kwargs):
        """Execute function with retry logic.

        Args:
            func: Function to execute (can be sync or async)
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            MCPError: If all retry attempts failed
        """
        attempt = 0
        last_error = None

        while True:
            attempt += 1

            try:
                # Execute function (handle both sync and async)
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Record success for circuit breaker
                if isinstance(self.retry_strategy, CircuitBreakerRetry):
                    self.retry_strategy.on_success()

                return result

            except MCPError as error:
                last_error = error

                # Record failure for circuit breaker
                if isinstance(self.retry_strategy, CircuitBreakerRetry):
                    self.retry_strategy.on_failure(error)

                # Check if we should retry
                if not self.retry_strategy.should_retry(error, attempt):
                    self.logger.error(
                        f"Operation failed after {attempt} attempts: {error}"
                    )
                    raise error

                # Calculate retry delay
                delay = self.retry_strategy.get_delay(error, attempt)
                self.logger.warning(
                    f"Operation failed (attempt {attempt}), retrying in {delay:.2f}s: {error}"
                )

                # Wait before retry
                await asyncio.sleep(delay)

            except Exception as error:
                # Convert unexpected errors to MCPError
                mcp_error = MCPError(
                    f"Unexpected error: {error}",
                    error_code=MCPErrorCode.INTERNAL_ERROR,
                    cause=error,
                    retryable=False,
                )
                self.logger.error(f"Unexpected error in retryable operation: {error}")
                raise mcp_error


class ErrorAggregator:
    """Aggregates and reports errors for monitoring.

    Collects error statistics and provides insights into
    error patterns and trends.

    Examples:
        Track errors:

        >>> aggregator = ErrorAggregator()
        >>> aggregator.record_error(error)
        >>> stats = aggregator.get_error_stats()
    """

    def __init__(self, max_errors: int = 1000):
        """Initialize error aggregator."""
        self.max_errors = max_errors
        self.errors: List[MCPError] = []
        self.error_counts: Dict[MCPErrorCode, int] = {}

    def record_error(self, error: MCPError):
        """Record an error occurrence."""
        self.errors.append(error)

        # Keep only recent errors
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors :]

        # Update counts
        self.error_counts[error.error_code] = (
            self.error_counts.get(error.error_code, 0) + 1
        )

    def get_error_stats(self, time_window: Optional[float] = None) -> Dict[str, Any]:
        """Get error statistics.

        Args:
            time_window: Time window in seconds (None for all errors)

        Returns:
            Error statistics dictionary
        """
        now = time.time()

        # Filter errors by time window
        if time_window:
            recent_errors = [e for e in self.errors if now - e.timestamp <= time_window]
        else:
            recent_errors = self.errors

        if not recent_errors:
            return {"total_errors": 0}

        # Calculate statistics
        error_codes = [e.error_code for e in recent_errors]
        severity_levels = [e.get_severity() for e in recent_errors]

        from collections import Counter

        return {
            "total_errors": len(recent_errors),
            "error_rate": len(recent_errors)
            / max(time_window or 3600, 1),  # per second
            "error_codes": dict(Counter(error_codes)),
            "severity_levels": dict(Counter(severity_levels)),
            "most_common_error": (
                Counter(error_codes).most_common(1)[0] if error_codes else None
            ),
            "retryable_errors": len([e for e in recent_errors if e.is_retryable()]),
            "time_window": time_window,
        }

    def get_error_trends(self, bucket_size: float = 300) -> List[Dict[str, Any]]:
        """Get error trends over time.

        Args:
            bucket_size: Time bucket size in seconds

        Returns:
            List of time buckets with error counts
        """
        if not self.errors:
            return []

        now = time.time()
        oldest_error = min(e.timestamp for e in self.errors)

        # Create time buckets
        buckets = []
        bucket_start = oldest_error

        while bucket_start < now:
            bucket_end = bucket_start + bucket_size
            bucket_errors = [
                e for e in self.errors if bucket_start <= e.timestamp < bucket_end
            ]

            buckets.append(
                {
                    "start_time": bucket_start,
                    "end_time": bucket_end,
                    "error_count": len(bucket_errors),
                    "error_codes": list(set(e.error_code for e in bucket_errors)),
                }
            )

            bucket_start = bucket_end

        return buckets


# Convenience functions
def create_retry_operation(
    strategy: str = "exponential", **strategy_kwargs
) -> RetryableOperation:
    """Create a retryable operation with the specified strategy.

    Args:
        strategy: Strategy type ("exponential" or "circuit_breaker")
        **strategy_kwargs: Strategy-specific arguments

    Returns:
        RetryableOperation instance
    """
    if strategy == "exponential":
        retry_strategy = ExponentialBackoffRetry(**strategy_kwargs)
    elif strategy == "circuit_breaker":
        retry_strategy = CircuitBreakerRetry(**strategy_kwargs)
    else:
        raise ValueError(f"Unknown retry strategy: {strategy}")

    return RetryableOperation(retry_strategy)


def wrap_with_error_handling(func):
    """Decorator to wrap functions with MCP error handling.

    Examples:
        >>> @wrap_with_error_handling
        ... async def risky_operation():
        ...     # This might fail
        ...     return "success"
    """

    async def wrapper(*args, **kwargs):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except MCPError:
            raise  # Re-raise MCP errors as-is
        except Exception as e:
            # Convert to MCP error
            raise MCPError(
                f"Operation failed: {e}",
                error_code=MCPErrorCode.INTERNAL_ERROR,
                cause=e,
                retryable=True,
            )

    return wrapper
