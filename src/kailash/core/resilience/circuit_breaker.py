"""Circuit Breaker pattern implementation for connection management.

This module implements the Circuit Breaker pattern to prevent cascading failures
in connection pools and database operations. It provides automatic failure detection,
recovery testing, and graceful degradation.

The circuit breaker has three states:
- CLOSED: Normal operation, requests pass through
- OPEN: Failures detected, requests fail fast
- HALF_OPEN: Testing recovery, limited requests allowed

Example:
    >>> breaker = ConnectionCircuitBreaker(
    ...     failure_threshold=5,
    ...     recovery_timeout=60,
    ...     half_open_requests=3
    ... )
    >>>
    >>> # Wrap connection operations
    >>> async with breaker.call() as protected:
    ...     result = await connection.execute(query)
"""

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes to close from half-open
    recovery_timeout: int = 60  # Seconds before trying half-open
    half_open_requests: int = 3  # Requests allowed in half-open
    error_rate_threshold: float = 0.5  # Error rate to trigger open
    window_size: int = 100  # Rolling window for error rate
    excluded_exceptions: List[type] = field(default_factory=list)  # Don't count these

    # Enhanced configurable thresholds
    min_calls_before_evaluation: int = 10  # Min calls before evaluating error rate
    slow_call_threshold: float = 5.0  # Seconds to consider a call slow
    slow_call_rate_threshold: float = 0.8  # Rate of slow calls to trigger open
    max_wait_duration_in_half_open: int = 60  # Max wait in half-open state
    exponential_backoff_multiplier: float = 2.0  # Backoff multiplier for recovery
    jitter_enabled: bool = True  # Add jitter to recovery timeout
    max_jitter_percentage: float = 0.1  # Maximum jitter as percentage of timeout


@dataclass
class CircuitBreakerMetrics:
    """Metrics tracking for circuit breaker."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    slow_calls: int = 0  # New: Track slow calls
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)
    last_failure_time: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    avg_call_duration: float = 0.0  # New: Average call duration
    total_call_duration: float = 0.0  # New: Total duration for average calculation

    def record_success(self, duration: float = 0.0):
        """Record successful call."""
        self.total_calls += 1
        self.successful_calls += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self._update_duration(duration)

    def record_failure(self, duration: float = 0.0):
        """Record failed call."""
        self.total_calls += 1
        self.failed_calls += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_failure_time = time.time()
        self._update_duration(duration)

    def record_rejection(self):
        """Record rejected call (circuit open)."""
        self.rejected_calls += 1

    def record_slow_call(self):
        """Record slow call."""
        self.slow_calls += 1

    def _update_duration(self, duration: float):
        """Update duration metrics."""
        if duration > 0:
            self.total_call_duration += duration
            # Update rolling average
            if self.total_calls > 0:
                self.avg_call_duration = self.total_call_duration / self.total_calls

    def get_error_rate(self) -> float:
        """Calculate current error rate."""
        if self.total_calls == 0:
            return 0.0
        return self.failed_calls / self.total_calls

    def get_slow_call_rate(self) -> float:
        """Calculate current slow call rate."""
        if self.total_calls == 0:
            return 0.0
        return self.slow_calls / self.total_calls


class ConnectionCircuitBreaker(Generic[T]):
    """Circuit breaker for database connections and operations.

    Monitors failures and prevents cascading failures by failing fast
    when error threshold is reached. Automatically tests recovery
    after timeout period.
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker with configuration."""
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.metrics = CircuitBreakerMetrics()
        self._lock = asyncio.Lock()
        self._half_open_requests = 0
        self._last_state_change = time.time()
        self._rolling_window = deque(maxlen=self.config.window_size)
        self._listeners: List[Callable] = []

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection.

        Args:
            func: Async function to protect
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: If function fails
        """
        async with self._lock:
            # Check if we should transition states
            await self._check_state_transition()

            if self.state == CircuitState.OPEN:
                self.metrics.record_rejection()
                raise CircuitBreakerError(
                    f"Circuit breaker is OPEN. "
                    f"Rejected after {self.metrics.consecutive_failures} failures. "
                    f"Will retry in {self._time_until_recovery():.1f}s"
                )

            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_requests >= self.config.half_open_requests:
                    self.metrics.record_rejection()
                    raise CircuitBreakerError(
                        "Circuit breaker is HALF_OPEN but request limit reached"
                    )
                self._half_open_requests += 1

        # Execute the function
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time

            # Check if this was a slow call
            is_slow = execution_time > self.config.slow_call_threshold

            await self._record_success(execution_time, is_slow)
            return result
        except Exception as e:
            execution_time = time.time() - start_time

            # Check if this exception should be counted
            if not any(
                isinstance(e, exc_type) for exc_type in self.config.excluded_exceptions
            ):
                await self._record_failure(e, execution_time)
            raise

    async def _check_state_transition(self):
        """Check if state should transition based on metrics."""
        current_time = time.time()

        if self.state == CircuitState.CLOSED:
            # Check if we should open
            if self._should_open():
                await self._transition_to(CircuitState.OPEN)

        elif self.state == CircuitState.OPEN:
            # Check if we should try recovery
            time_since_open = current_time - self._last_state_change
            if time_since_open >= self.config.recovery_timeout:
                await self._transition_to(CircuitState.HALF_OPEN)
                self._half_open_requests = 0

        elif self.state == CircuitState.HALF_OPEN:
            # This is handled after request execution
            pass

    def _should_open(self) -> bool:
        """Determine if circuit should open based on failures."""
        # Only evaluate if we have minimum number of calls
        if self.metrics.total_calls < self.config.min_calls_before_evaluation:
            return False

        # Check consecutive failures
        if self.metrics.consecutive_failures >= self.config.failure_threshold:
            return True

        # Check error rate in rolling window
        if len(self._rolling_window) >= self.config.window_size / 2:
            error_count = sum(1 for success in self._rolling_window if not success)
            error_rate = error_count / len(self._rolling_window)
            if error_rate >= self.config.error_rate_threshold:
                return True

        # Check slow call rate
        slow_call_rate = self.metrics.get_slow_call_rate()
        if slow_call_rate >= self.config.slow_call_rate_threshold:
            return True

        return False

    async def _record_success(self, duration: float = 0.0, is_slow: bool = False):
        """Record successful execution."""
        async with self._lock:
            self.metrics.record_success(duration)
            if is_slow:
                self.metrics.record_slow_call()
            self._rolling_window.append(True)

            if self.state == CircuitState.HALF_OPEN:
                if self.metrics.consecutive_successes >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)

    async def _record_failure(self, error: Exception, duration: float = 0.0):
        """Record failed execution."""
        async with self._lock:
            self.metrics.record_failure(duration)
            # Consider slow failures as additional burden
            if duration > self.config.slow_call_threshold:
                self.metrics.record_slow_call()
            self._rolling_window.append(False)

            if self.state == CircuitState.HALF_OPEN:
                # Single failure in half-open goes back to open
                await self._transition_to(CircuitState.OPEN)
            elif self.state == CircuitState.CLOSED:
                # Check if we should open the circuit
                if self._should_open():
                    await self._transition_to(CircuitState.OPEN)

            logger.warning(
                f"Circuit breaker recorded failure: {type(error).__name__}: {error}"
            )

    async def _transition_to(self, new_state: CircuitState):
        """Transition to new state and notify listeners."""
        old_state = self.state
        self.state = new_state
        self._last_state_change = time.time()

        # Reset counters on state change
        if new_state == CircuitState.CLOSED:
            self.metrics.consecutive_failures = 0
        elif new_state == CircuitState.OPEN:
            self.metrics.consecutive_successes = 0

        # Record transition
        self.metrics.state_transitions.append(
            {
                "from": old_state.value,
                "to": new_state.value,
                "timestamp": datetime.now().isoformat(),
                "reason": self._get_transition_reason(old_state, new_state),
            }
        )

        logger.info(
            f"Circuit breaker transitioned from {old_state.value} to {new_state.value}"
        )

        # Notify listeners
        for listener in self._listeners:
            try:
                await listener(old_state, new_state, self.metrics)
            except Exception as e:
                logger.error(f"Error notifying circuit breaker listener: {e}")

    def _get_transition_reason(
        self, old_state: CircuitState, new_state: CircuitState
    ) -> str:
        """Get human-readable reason for state transition."""
        if old_state == CircuitState.CLOSED and new_state == CircuitState.OPEN:
            return f"Failure threshold reached ({self.metrics.consecutive_failures} failures)"
        elif old_state == CircuitState.OPEN and new_state == CircuitState.HALF_OPEN:
            return f"Recovery timeout elapsed ({self.config.recovery_timeout}s)"
        elif old_state == CircuitState.HALF_OPEN and new_state == CircuitState.CLOSED:
            return f"Success threshold reached ({self.metrics.consecutive_successes} successes)"
        elif old_state == CircuitState.HALF_OPEN and new_state == CircuitState.OPEN:
            return "Failure during recovery test"
        return "Unknown reason"

    def _time_until_recovery(self) -> float:
        """Calculate seconds until recovery attempt with jitter and backoff."""
        if self.state != CircuitState.OPEN:
            return 0.0

        elapsed = time.time() - self._last_state_change

        # Apply exponential backoff based on number of state transitions to OPEN
        open_transitions = sum(
            1
            for t in self.metrics.state_transitions
            if t.get("to") == CircuitState.OPEN.value
        )
        backoff_multiplier = self.config.exponential_backoff_multiplier ** max(
            0, open_transitions - 1
        )

        base_timeout = self.config.recovery_timeout * backoff_multiplier

        # Add jitter if enabled
        if self.config.jitter_enabled:
            jitter_range = base_timeout * self.config.max_jitter_percentage
            jitter = random.uniform(-jitter_range, jitter_range)
            base_timeout += jitter

        remaining = base_timeout - elapsed
        return max(0.0, remaining)

    async def force_open(self, reason: str = "Manual override"):
        """Manually open the circuit breaker."""
        async with self._lock:
            if self.state != CircuitState.OPEN:
                logger.warning(f"Manually opening circuit breaker: {reason}")
                await self._transition_to(CircuitState.OPEN)

    async def force_close(self, reason: str = "Manual override"):
        """Manually close the circuit breaker."""
        async with self._lock:
            if self.state != CircuitState.CLOSED:
                logger.warning(f"Manually closing circuit breaker: {reason}")
                self.metrics.consecutive_failures = 0
                self.metrics.consecutive_successes = 0
                await self._transition_to(CircuitState.CLOSED)

    async def reset(self):
        """Reset circuit breaker to initial state."""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.metrics = CircuitBreakerMetrics()
            self._rolling_window.clear()
            self._half_open_requests = 0
            self._last_state_change = time.time()
            logger.info("Circuit breaker reset to initial state")

    def add_listener(self, listener: Callable):
        """Add state change listener."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable):
        """Remove state change listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    @property
    def success_count(self) -> int:
        """Get number of successful calls."""
        return self.metrics.successful_calls

    @property
    def failure_count(self) -> int:
        """Get number of failed calls."""
        return self.metrics.failed_calls

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "metrics": {
                "total_calls": self.metrics.total_calls,
                "successful_calls": self.metrics.successful_calls,
                "failed_calls": self.metrics.failed_calls,
                "rejected_calls": self.metrics.rejected_calls,
                "slow_calls": self.metrics.slow_calls,
                "error_rate": self.metrics.get_error_rate(),
                "slow_call_rate": self.metrics.get_slow_call_rate(),
                "avg_call_duration": self.metrics.avg_call_duration,
                "consecutive_failures": self.metrics.consecutive_failures,
                "consecutive_successes": self.metrics.consecutive_successes,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "error_rate_threshold": self.config.error_rate_threshold,
                "slow_call_threshold": self.config.slow_call_threshold,
                "slow_call_rate_threshold": self.config.slow_call_rate_threshold,
                "min_calls_before_evaluation": self.config.min_calls_before_evaluation,
                "exponential_backoff_multiplier": self.config.exponential_backoff_multiplier,
                "jitter_enabled": self.config.jitter_enabled,
            },
            "time_until_recovery": (
                self._time_until_recovery() if self.state == CircuitState.OPEN else None
            ),
            "state_transitions": self.metrics.state_transitions[
                -5:
            ],  # Last 5 transitions
        }


class CircuitBreakerManager:
    """Manages multiple circuit breakers for different resources."""

    def __init__(self, performance_monitor=None):
        """Initialize circuit breaker manager."""
        self._breakers: Dict[str, ConnectionCircuitBreaker] = {}
        self._default_config = CircuitBreakerConfig()
        self._performance_monitor = performance_monitor
        self._patterns = {
            "database": CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60),
            "api": CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30),
            "cache": CircuitBreakerConfig(failure_threshold=2, recovery_timeout=15),
        }

    def get_or_create(
        self, name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> ConnectionCircuitBreaker:
        """Get existing or create new circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = ConnectionCircuitBreaker(
                config or self._default_config
            )
        return self._breakers[name]

    def create_circuit_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        pattern: Optional[str] = None,
    ) -> ConnectionCircuitBreaker:
        """Create a new circuit breaker with optional pattern-based configuration."""
        if pattern and pattern in self._patterns:
            config = config or self._patterns[pattern]
        return self.get_or_create(name, config)

    async def execute_with_circuit_breaker(
        self, name: str, func: Callable, fallback: Optional[Callable] = None
    ):
        """Execute a function with circuit breaker protection."""
        cb = self.get_or_create(name)
        try:
            result = await cb.call(func)
            return result
        except CircuitBreakerError:
            if fallback:
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                else:
                    return fallback()
            raise

    def get_circuit_breaker(self, name: str) -> Optional[ConnectionCircuitBreaker]:
        """Get an existing circuit breaker by name."""
        return self._breakers.get(name)

    def get_all_circuit_states(self) -> Dict[str, Dict[str, Any]]:
        """Get the state of all circuit breakers."""
        return {name: cb.get_status() for name, cb in self._breakers.items()}

    def force_open_circuit_breaker(self, name: str) -> bool:
        """Manually open a circuit breaker."""
        cb = self._breakers.get(name)
        if cb:
            asyncio.create_task(cb.force_open("Manual override"))
            return True
        return False

    def reset_circuit_breaker(self, name: str) -> bool:
        """Reset a circuit breaker to closed state."""
        cb = self._breakers.get(name)
        if cb:
            asyncio.create_task(cb.reset())
            return True
        return False

    def add_global_callback(self, callback: Callable):
        """Add a global callback for circuit breaker state changes."""
        # For now, add to all existing breakers
        for cb in self._breakers.values():
            cb.add_listener(callback)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    async def reset_all(self):
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            await breaker.reset()

    def set_default_config(self, config: CircuitBreakerConfig):
        """Set default configuration for new breakers."""
        self._default_config = config
