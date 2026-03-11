"""
DataFlow Platform Resilience: Retry & Circuit Breaking.

This module provides production-ready retry logic with exponential backoff
and circuit breaker pattern for failing dependencies.

Key Features:
- Automatic retry with exponential backoff and jitter
- Circuit breaker with three states (CLOSED/OPEN/HALF_OPEN)
- Thread-safe state management
- Metrics tracking for monitoring
- Configurable thresholds and timeouts

Design Philosophy:
- EXPLICIT IS BETTER THAN IMPLICIT
- Raise clear errors instead of silent fallbacks
- Log all state transitions with context
- Make debugging easier with informative messages

Circuit Breaker States:
- CLOSED: Normal operation, all requests pass through
- OPEN: Too many failures, reject requests immediately (fail fast)
- HALF_OPEN: Testing if dependency recovered, allow limited requests

Usage:
    # Retry with exponential backoff
    retry_config = RetryConfig(max_attempts=3, base_delay=0.1, max_delay=5.0)
    retry_handler = RetryHandler(retry_config)
    result = await retry_handler.execute_with_retry(database_operation, arg1, arg2)

    # Circuit breaker for failing services
    circuit_config = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)
    circuit_breaker = CircuitBreaker(circuit_config)
    result = await circuit_breaker.execute(external_api_call, arg1, arg2)

    # Combined retry + circuit breaker
    async def protected_call():
        return await circuit_breaker.execute(database_operation)
    result = await retry_handler.execute_with_retry(protected_call)
"""

import asyncio
import logging
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Retry Strategy and Configuration
# ============================================================================


class RetryStrategy(Enum):
    """Retry backoff strategies."""

    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    CONSTANT_DELAY = "constant_delay"


@dataclass
class RetryConfig:
    """
    Retry configuration.

    Attributes:
        max_attempts: Maximum number of retry attempts (default: 3)
        strategy: Backoff strategy (default: EXPONENTIAL_BACKOFF)
        base_delay: Base delay in seconds (default: 0.1 = 100ms)
        max_delay: Maximum delay in seconds (default: 5.0)
        multiplier: Backoff multiplier for exponential strategy (default: 2.0)
        jitter: Apply jitter to prevent thundering herd (default: True)
    """

    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 0.1  # 100ms
    max_delay: float = 5.0  # 5 seconds
    multiplier: float = 2.0
    jitter: bool = True

    def __post_init__(self):
        """Validate configuration."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay < 0:
            raise ValueError("base_delay must be >= 0")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if self.multiplier < 1:
            raise ValueError("multiplier must be >= 1")


# ============================================================================
# Retry Exceptions
# ============================================================================


class RetryExhausted(Exception):
    """Raised when max retry attempts are reached."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


# ============================================================================
# Retry Handler
# ============================================================================


class RetryHandler:
    """
    Automatic retry handler with exponential backoff.

    Features:
    - Exponential/linear/constant backoff strategies
    - Jitter to prevent thundering herd (50-100% of calculated delay)
    - Configurable max attempts and delays
    - Retry metrics tracking

    Thread Safety:
    - Metrics tracking is thread-safe with lock protection
    """

    def __init__(self, config: RetryConfig):
        """
        Initialize retry handler.

        Args:
            config: Retry configuration
        """
        self.config = config
        self._metrics_lock = threading.Lock()
        self._metrics = {
            "total_attempts": 0,
            "total_failures": 0,
            "total_successes": 0,
        }
        logger.info(
            f"RetryHandler initialized: max_attempts={config.max_attempts}, "
            f"strategy={config.strategy.value}, base_delay={config.base_delay}s"
        )

    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from successful function execution

        Raises:
            RetryExhausted: When max attempts reached without success
        """
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                logger.debug(f"Retry attempt {attempt}/{self.config.max_attempts}")
                result = await func(*args, **kwargs)

                # Success!
                self._record_success(attempt)
                if attempt > 1:
                    logger.info(f"Operation succeeded after {attempt} attempts")
                return result

            except Exception as e:
                last_exception = e

                if attempt < self.config.max_attempts:
                    # Calculate and apply backoff delay
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt} failed: {type(e).__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    # Max attempts reached - record all failures
                    self._record_all_failures(attempt)
                    logger.error(
                        f"Max retry attempts ({self.config.max_attempts}) reached. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    raise RetryExhausted(
                        f"Max retry attempts ({self.config.max_attempts}) reached",
                        original_error=e,
                    )

        # Should not reach here, but for safety
        raise last_exception  # pragma: no cover

    def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate backoff delay for the given attempt.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        if self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            # Exponential: base * (multiplier ^ (attempt - 1))
            delay = self.config.base_delay * (self.config.multiplier ** (attempt - 1))
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            # Linear: base * attempt
            delay = self.config.base_delay * attempt
        else:  # CONSTANT_DELAY
            # Constant: always base_delay
            delay = self.config.base_delay

        # Apply max_delay cap
        delay = min(delay, self.config.max_delay)

        # Apply jitter (50-100% of calculated delay)
        if self.config.jitter:
            jitter_factor = 0.5 + random.random() * 0.5  # 0.5 to 1.0
            delay *= jitter_factor

        return delay

    def _record_success(self, attempt: int):
        """Record successful execution."""
        with self._metrics_lock:
            self._metrics["total_attempts"] += attempt
            self._metrics["total_successes"] += 1
            if attempt > 1:
                self._metrics["total_failures"] += attempt - 1

    def _record_all_failures(self, total_attempts: int):
        """Record all failures when max attempts exhausted."""
        with self._metrics_lock:
            self._metrics["total_attempts"] += total_attempts
            self._metrics["total_failures"] += total_attempts

    def get_metrics(self) -> Dict[str, int]:
        """
        Get retry metrics.

        Returns:
            Dictionary with retry statistics
        """
        with self._metrics_lock:
            return self._metrics.copy()


# ============================================================================
# Circuit Breaker State and Configuration
# ============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """
    Circuit breaker configuration.

    Attributes:
        failure_threshold: Number of failures before opening circuit (default: 5)
        success_threshold: Number of successes in HALF_OPEN to close (default: 2)
        timeout: Seconds to wait before attempting reset (default: 60.0)
        half_open_timeout: Timeout for HALF_OPEN state (default: 30.0)
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 60.0  # seconds
    half_open_timeout: float = 30.0

    def __post_init__(self):
        """Validate configuration."""
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if self.timeout < 0:
            raise ValueError("timeout must be >= 0")
        if self.half_open_timeout < 0:
            raise ValueError("half_open_timeout must be >= 0")


# ============================================================================
# Circuit Breaker Exceptions
# ============================================================================


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open and request is rejected."""

    pass


# ============================================================================
# Circuit Breaker
# ============================================================================


class CircuitBreaker:
    """
    Circuit breaker for failing dependencies.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Too many failures, reject requests immediately
    - HALF_OPEN: Testing if dependency recovered, allow limited requests

    State Transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After timeout elapsed
    - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
    - HALF_OPEN -> OPEN: On any failure during testing

    Thread Safety:
    - All state mutations are protected by lock
    """

    def __init__(self, config: CircuitBreakerConfig):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self._lock = threading.Lock()
        self._metrics = {"state_changes": 0, "rejected_requests": 0}

        logger.info(
            f"CircuitBreaker initialized: failure_threshold={config.failure_threshold}, "
            f"timeout={config.timeout}s"
        )

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from successful function execution

        Raises:
            CircuitBreakerOpen: When circuit is open and request is rejected
        """
        # Check circuit state before execution
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    self._metrics["rejected_requests"] += 1
                    logger.warning(
                        f"Circuit breaker OPEN: rejecting request "
                        f"(failures: {self.failure_count})"
                    )
                    raise CircuitBreakerOpen(
                        "Circuit breaker is open, rejecting request"
                    )

        # Execute function
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result

        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful execution."""
        with self._lock:
            self.failure_count = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.debug(
                    f"Circuit breaker HALF_OPEN: success {self.success_count}/"
                    f"{self.config.success_threshold}"
                )

                if self.success_count >= self.config.success_threshold:
                    # Recovered! Close circuit
                    self._transition_to_closed()

    def _on_failure(self):
        """Handle failed execution."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == CircuitState.HALF_OPEN:
                # Failed during testing, reopen circuit
                logger.warning(
                    "Circuit breaker HALF_OPEN: test failed, reopening circuit"
                )
                self._transition_to_open()

            elif self.failure_count >= self.config.failure_threshold:
                # Too many failures, open circuit
                logger.error(
                    f"Circuit breaker opening: {self.failure_count} failures "
                    f">= threshold {self.config.failure_threshold}"
                )
                self._transition_to_open()

    def _should_attempt_reset(self) -> bool:
        """
        Check if should attempt reset (transition to HALF_OPEN).

        Returns:
            True if timeout elapsed and should test recovery
        """
        if self.last_failure_time is None:
            return False

        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.config.timeout

    def _transition_to_open(self):
        """Transition to OPEN state (must hold lock)."""
        old_state = self.state
        self.state = CircuitState.OPEN
        self.success_count = 0
        self._metrics["state_changes"] += 1
        logger.error(f"Circuit breaker: {old_state.value} -> OPEN")

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state (must hold lock)."""
        old_state = self.state
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self._metrics["state_changes"] += 1
        logger.info(
            f"Circuit breaker: {old_state.value} -> HALF_OPEN (testing recovery)"
        )

    def _transition_to_closed(self):
        """Transition to CLOSED state (must hold lock)."""
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self._metrics["state_changes"] += 1
        logger.info(f"Circuit breaker: {old_state.value} -> CLOSED (recovered)")

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get circuit breaker metrics.

        Returns:
            Dictionary with circuit breaker statistics
        """
        with self._lock:
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "state_changes": self._metrics["state_changes"],
                "rejected_requests": self._metrics["rejected_requests"],
            }


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    "RetryStrategy",
    "RetryConfig",
    "RetryHandler",
    "RetryExhausted",
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitBreakerOpen",
]
