"""Distributed Circuit Breaker pattern with Redis-backed state.

This module extends the local CircuitBreaker pattern to support distributed
deployments where multiple application instances share circuit breaker state
via Redis. When Redis is unavailable, the breaker falls back to local
in-memory state and logs a warning.

Key components:
- RedisCircuitBreakerBackend: Stores CB state in Redis with atomic transitions
- DistributedCircuitBreaker: Extends ConnectionCircuitBreaker with Redis state
- DistributedCircuitBreakerManager: Factory for creating distributed breakers

Configuration:
    Set CIRCUIT_BREAKER_REDIS_URL environment variable or pass redis_url
    directly to the manager/backend constructors.

Example:
    >>> from kailash.core.resilience.distributed_circuit_breaker import (
    ...     DistributedCircuitBreakerManager,
    ... )
    >>> manager = DistributedCircuitBreakerManager(
    ...     redis_url="redis://localhost:6379/0"
    ... )
    >>> breaker = manager.get_or_create("my-service")
    >>> # breaker state is shared across all instances via Redis
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

from kailash.core.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerManager,
    CircuitBreakerMetrics,
    CircuitState,
    ConnectionCircuitBreaker,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Redis key prefix for circuit breaker state
_KEY_PREFIX = "cb"

# Lua script for atomic state transitions.
# KEYS[1] = state key, KEYS[2] = failure_count key, KEYS[3] = last_failure key
# ARGV[1] = expected current state, ARGV[2] = new state, ARGV[3] = ttl seconds
# Returns 1 on success, 0 if current state does not match expected.
_TRANSITION_LUA = """
local current = redis.call('GET', KEYS[1])
if current == false then current = 'closed' end
if current ~= ARGV[1] then
    return 0
end
redis.call('SET', KEYS[1], ARGV[2])
if tonumber(ARGV[3]) > 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[3])
    redis.call('EXPIRE', KEYS[2], ARGV[3])
    redis.call('EXPIRE', KEYS[3], ARGV[3])
end
return 1
"""

# Lua script for atomic failure recording.
# KEYS[1] = failure_count key, KEYS[2] = last_failure key
# ARGV[1] = timestamp, ARGV[2] = ttl seconds
# Returns the new failure count.
_RECORD_FAILURE_LUA = """
local count = redis.call('INCR', KEYS[1])
redis.call('SET', KEYS[2], ARGV[1])
if tonumber(ARGV[2]) > 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    redis.call('EXPIRE', KEYS[2], ARGV[2])
end
return count
"""


@dataclass
class RedisCircuitBreakerBackend:
    """Redis-backed storage for circuit breaker state.

    Stores state using the following Redis key layout:
        cb:{name}:state         -- current CircuitState value (string)
        cb:{name}:failure_count -- integer failure counter
        cb:{name}:last_failure  -- Unix timestamp of last failure (float string)

    All state transitions use Lua scripts executed atomically on the Redis
    server to prevent race conditions between distributed instances.

    Args:
        redis_url: Redis connection URL (e.g. "redis://localhost:6379/0").
            Defaults to ``CIRCUIT_BREAKER_REDIS_URL`` environment variable.
        key_ttl: TTL in seconds for Redis keys. Prevents stale keys from
            accumulating if a circuit breaker name is retired. 0 means no expiry.
            Defaults to 86400 (24 hours).
    """

    redis_url: str = ""
    key_ttl: int = 86400  # 24 hours default TTL

    def __post_init__(self):
        if not self.redis_url:
            self.redis_url = os.environ.get("CIRCUIT_BREAKER_REDIS_URL", "")
        self._client = None
        self._transition_script = None
        self._failure_script = None

    # -- Connection management --

    def _get_client(self):
        """Lazily create and return a Redis client.

        Returns:
            A ``redis.Redis`` instance.

        Raises:
            ConnectionError: If Redis is unreachable.
        """
        if self._client is None:
            import redis as redis_lib

            if not self.redis_url.startswith(("redis://", "rediss://")):
                raise ValueError(
                    f"Invalid Redis URL '{self.redis_url}': must start with redis:// or rediss://"
                )
            self._client = redis_lib.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True,
            )
            # Register Lua scripts for atomic operations
            self._transition_script = self._client.register_script(_TRANSITION_LUA)
            self._failure_script = self._client.register_script(_RECORD_FAILURE_LUA)
        return self._client

    def _state_key(self, name: str) -> str:
        return f"{_KEY_PREFIX}:{name}:state"

    def _failure_count_key(self, name: str) -> str:
        return f"{_KEY_PREFIX}:{name}:failure_count"

    def _last_failure_key(self, name: str) -> str:
        return f"{_KEY_PREFIX}:{name}:last_failure"

    # -- Read operations --

    def get_state(self, name: str) -> Optional[CircuitState]:
        """Read the current circuit state from Redis.

        Args:
            name: Circuit breaker name.

        Returns:
            The current ``CircuitState``, or ``None`` if Redis is unavailable.
        """
        try:
            client = self._get_client()
            raw = client.get(self._state_key(name))
            if raw is None:
                return CircuitState.CLOSED
            return CircuitState(raw)
        except Exception as exc:
            logger.warning(
                "Redis unavailable for circuit breaker '%s' state read: %s",
                name,
                exc,
            )
            return None

    def get_failure_count(self, name: str) -> Optional[int]:
        """Read the failure count from Redis.

        Args:
            name: Circuit breaker name.

        Returns:
            The failure count, or ``None`` if Redis is unavailable.
        """
        try:
            client = self._get_client()
            raw = client.get(self._failure_count_key(name))
            if raw is None:
                return 0
            return int(raw)
        except Exception as exc:
            logger.warning(
                "Redis unavailable for circuit breaker '%s' failure count read: %s",
                name,
                exc,
            )
            return None

    def get_last_failure_time(self, name: str) -> Optional[float]:
        """Read the last failure timestamp from Redis.

        Args:
            name: Circuit breaker name.

        Returns:
            Unix timestamp of the last failure, 0.0 if no failure recorded,
            or ``None`` if Redis is unavailable.
        """
        try:
            client = self._get_client()
            raw = client.get(self._last_failure_key(name))
            if raw is None:
                return 0.0
            return float(raw)
        except Exception as exc:
            logger.warning(
                "Redis unavailable for circuit breaker '%s' last failure read: %s",
                name,
                exc,
            )
            return None

    # -- Write operations (atomic via Lua) --

    def set_state(self, name: str, state: CircuitState) -> bool:
        """Write circuit state to Redis.

        Args:
            name: Circuit breaker name.
            state: The new circuit state.

        Returns:
            True if the write succeeded, False if Redis is unavailable.
        """
        try:
            client = self._get_client()
            client.set(self._state_key(name), state.value)
            if self.key_ttl > 0:
                client.expire(self._state_key(name), self.key_ttl)
            return True
        except Exception as exc:
            logger.warning(
                "Redis unavailable for circuit breaker '%s' state write: %s",
                name,
                exc,
            )
            return False

    def atomic_transition(
        self, name: str, expected_state: CircuitState, new_state: CircuitState
    ) -> bool:
        """Atomically transition state if the current state matches expected.

        Uses a Lua script on the Redis server so the read-compare-write is a
        single atomic operation. This prevents two instances from both seeing
        OPEN and both transitioning to HALF_OPEN simultaneously.

        Args:
            name: Circuit breaker name.
            expected_state: The state we expect the breaker to be in.
            new_state: The state to transition to.

        Returns:
            True if the transition succeeded, False if the current state did
            not match ``expected_state`` or if Redis is unavailable.
        """
        try:
            client = self._get_client()
            result = self._transition_script(
                keys=[
                    self._state_key(name),
                    self._failure_count_key(name),
                    self._last_failure_key(name),
                ],
                args=[expected_state.value, new_state.value, str(self.key_ttl)],
            )
            return bool(result)
        except Exception as exc:
            logger.warning(
                "Redis unavailable for circuit breaker '%s' atomic transition: %s",
                name,
                exc,
            )
            return False

    def record_failure(self, name: str) -> Optional[int]:
        """Atomically increment failure count and update last failure time.

        Args:
            name: Circuit breaker name.

        Returns:
            The new failure count, or ``None`` if Redis is unavailable.
        """
        try:
            client = self._get_client()
            count = self._failure_script(
                keys=[self._failure_count_key(name), self._last_failure_key(name)],
                args=[str(time.time()), str(self.key_ttl)],
            )
            return int(count)
        except Exception as exc:
            logger.warning(
                "Redis unavailable for circuit breaker '%s' failure recording: %s",
                name,
                exc,
            )
            return None

    def reset_failure_count(self, name: str) -> bool:
        """Reset the failure count to zero.

        Args:
            name: Circuit breaker name.

        Returns:
            True if the reset succeeded, False if Redis is unavailable.
        """
        try:
            client = self._get_client()
            client.set(self._failure_count_key(name), "0")
            if self.key_ttl > 0:
                client.expire(self._failure_count_key(name), self.key_ttl)
            return True
        except Exception as exc:
            logger.warning(
                "Redis unavailable for circuit breaker '%s' failure count reset: %s",
                name,
                exc,
            )
            return False

    def delete_all(self, name: str) -> bool:
        """Delete all Redis keys for a circuit breaker. Used for full reset.

        Args:
            name: Circuit breaker name.

        Returns:
            True if deletion succeeded, False if Redis is unavailable.
        """
        try:
            client = self._get_client()
            client.delete(
                self._state_key(name),
                self._failure_count_key(name),
                self._last_failure_key(name),
            )
            return True
        except Exception as exc:
            logger.warning(
                "Redis unavailable for circuit breaker '%s' key deletion: %s",
                name,
                exc,
            )
            return False

    def ping(self) -> bool:
        """Check Redis connectivity.

        Returns:
            True if Redis responds to PING, False otherwise.
        """
        try:
            client = self._get_client()
            return client.ping()
        except Exception:
            return False


class DistributedCircuitBreaker(ConnectionCircuitBreaker):
    """Circuit breaker with Redis-backed distributed state.

    Extends :class:`ConnectionCircuitBreaker` to persist state in Redis so
    that multiple application instances share the same circuit breaker state.
    When Redis is unavailable, the breaker gracefully falls back to local
    in-memory state inherited from the parent class.

    Args:
        name: Unique name for this circuit breaker (used as Redis key prefix).
        backend: A :class:`RedisCircuitBreakerBackend` instance.
        config: Optional circuit breaker configuration.

    Example:
        >>> backend = RedisCircuitBreakerBackend(redis_url="redis://localhost:6379/0")
        >>> breaker = DistributedCircuitBreaker("payment-api", backend)
        >>> result = await breaker.call(my_async_func)
    """

    def __init__(
        self,
        name: str,
        backend: RedisCircuitBreakerBackend,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        super().__init__(config=config)
        self.name = name
        self._backend = backend
        # Synchronize local state from Redis on init
        self._sync_from_redis()

    def _sync_from_redis(self):
        """Pull current state from Redis into local fields.

        If Redis is unavailable, local defaults (CLOSED, 0 failures) are kept.
        """
        remote_state = self._backend.get_state(self.name)
        if remote_state is not None:
            self.state = remote_state

        remote_failures = self._backend.get_failure_count(self.name)
        if remote_failures is not None:
            self.metrics.consecutive_failures = remote_failures

        remote_last_failure = self._backend.get_last_failure_time(self.name)
        if remote_last_failure is not None:
            self.metrics.last_failure_time = (
                remote_last_failure if remote_last_failure > 0 else None
            )

    async def _record_failure(self, error: Exception, duration: float = 0.0):
        """Record failure in both local metrics and Redis.

        Overrides the parent to also push failure state to Redis. If Redis
        is unavailable, local-only recording proceeds normally.
        """
        # Record in Redis atomically
        new_count = self._backend.record_failure(self.name)
        if new_count is not None:
            # Keep local metrics in sync
            async with self._lock:
                self.metrics.record_failure(duration)
                if duration > self.config.slow_call_threshold:
                    self.metrics.record_slow_call()
                self._rolling_window.append(False)
                # Override consecutive failures with Redis authoritative count
                self.metrics.consecutive_failures = new_count

                if self.state == CircuitState.HALF_OPEN:
                    await self._distributed_transition(
                        CircuitState.HALF_OPEN, CircuitState.OPEN
                    )
                elif self.state == CircuitState.CLOSED:
                    if self._should_open():
                        await self._distributed_transition(
                            CircuitState.CLOSED, CircuitState.OPEN
                        )

                logger.warning(
                    "Circuit breaker '%s' recorded failure: %s: %s",
                    self.name,
                    type(error).__name__,
                    error,
                )
        else:
            # Redis unavailable -- fall back to parent behavior
            await super()._record_failure(error, duration)

    async def _record_success(self, duration: float = 0.0, is_slow: bool = False):
        """Record success in both local metrics and Redis.

        Overrides the parent to push success state transitions to Redis.
        """
        async with self._lock:
            self.metrics.record_success(duration)
            if is_slow:
                self.metrics.record_slow_call()
            self._rolling_window.append(True)

            if self.state == CircuitState.HALF_OPEN:
                if self.metrics.consecutive_successes >= self.config.success_threshold:
                    await self._distributed_transition(
                        CircuitState.HALF_OPEN, CircuitState.CLOSED
                    )

    async def _check_state_transition(self):
        """Check and perform state transitions using Redis as source of truth.

        Reads current state from Redis before evaluating transitions.
        """
        # Refresh state from Redis
        remote_state = self._backend.get_state(self.name)
        if remote_state is not None:
            self.state = remote_state

        current_time = time.time()

        if self.state == CircuitState.CLOSED:
            if self._should_open():
                await self._distributed_transition(
                    CircuitState.CLOSED, CircuitState.OPEN
                )
        elif self.state == CircuitState.OPEN:
            time_since_change = current_time - self._last_state_change
            # Also check last failure from Redis for distributed accuracy
            remote_last_failure = self._backend.get_last_failure_time(self.name)
            if remote_last_failure is not None and remote_last_failure > 0:
                time_since_change = current_time - remote_last_failure
            if time_since_change >= self.config.recovery_timeout:
                await self._distributed_transition(
                    CircuitState.OPEN, CircuitState.HALF_OPEN
                )
                self._half_open_requests = 0

    async def _distributed_transition(
        self, expected: CircuitState, new_state: CircuitState
    ):
        """Attempt an atomic state transition via Redis.

        If Redis performs the transition, local state is updated to match.
        If Redis is unavailable, falls back to local transition.

        Args:
            expected: The state we expect the breaker to be in.
            new_state: The target state.
        """
        success = self._backend.atomic_transition(self.name, expected, new_state)
        if success:
            await self._transition_to(new_state)
            # Reset failure count in Redis on close
            if new_state == CircuitState.CLOSED:
                self._backend.reset_failure_count(self.name)
        elif success is False:
            # Transition failed because state changed (another instance won the race).
            # Re-sync from Redis.
            self._sync_from_redis()
        # If success is None (Redis unavailable), fall back to local transition
        # which already happened via _transition_to above only if success was True.

    async def force_open(self, reason: str = "Manual override"):
        """Manually open the circuit breaker in both local and Redis state."""
        async with self._lock:
            if self.state != CircuitState.OPEN:
                logger.warning(
                    "Manually opening distributed circuit breaker '%s': %s",
                    self.name,
                    reason,
                )
                self._backend.set_state(self.name, CircuitState.OPEN)
                await self._transition_to(CircuitState.OPEN)

    async def force_close(self, reason: str = "Manual override"):
        """Manually close the circuit breaker in both local and Redis state."""
        async with self._lock:
            if self.state != CircuitState.CLOSED:
                logger.warning(
                    "Manually closing distributed circuit breaker '%s': %s",
                    self.name,
                    reason,
                )
                self._backend.set_state(self.name, CircuitState.CLOSED)
                self._backend.reset_failure_count(self.name)
                self.metrics.consecutive_failures = 0
                self.metrics.consecutive_successes = 0
                await self._transition_to(CircuitState.CLOSED)

    async def reset(self):
        """Reset the circuit breaker to initial state, clearing Redis keys."""
        async with self._lock:
            self._backend.delete_all(self.name)
            self.state = CircuitState.CLOSED
            self.metrics = CircuitBreakerMetrics()
            self._rolling_window.clear()
            self._half_open_requests = 0
            self._last_state_change = time.time()
            logger.info(
                "Distributed circuit breaker '%s' reset to initial state", self.name
            )

    def get_status(self) -> Dict[str, Any]:
        """Get status including Redis connectivity information."""
        status = super().get_status()
        status["distributed"] = True
        status["name"] = self.name
        status["redis_available"] = self._backend.ping()
        return status


class DistributedCircuitBreakerManager:
    """Factory for creating and managing distributed circuit breakers.

    Creates :class:`DistributedCircuitBreaker` instances when a Redis URL is
    provided, or falls back to standard local
    :class:`ConnectionCircuitBreaker` instances otherwise.

    Args:
        redis_url: Redis connection URL. Defaults to
            ``CIRCUIT_BREAKER_REDIS_URL`` environment variable.
        key_ttl: TTL for Redis keys in seconds. Defaults to 86400 (24h).
        default_config: Default circuit breaker config for new breakers.

    Example:
        >>> manager = DistributedCircuitBreakerManager(
        ...     redis_url="redis://localhost:6379/0"
        ... )
        >>> breaker = manager.get_or_create("payment-service")
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_ttl: int = 86400,
        default_config: Optional[CircuitBreakerConfig] = None,
    ):
        self._redis_url = redis_url or os.environ.get("CIRCUIT_BREAKER_REDIS_URL", "")
        self._key_ttl = key_ttl
        self._default_config = default_config or CircuitBreakerConfig()
        self._breakers: Dict[str, ConnectionCircuitBreaker] = {}
        self._backend: Optional[RedisCircuitBreakerBackend] = None
        self._patterns = {
            "database": CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60),
            "api": CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30),
            "cache": CircuitBreakerConfig(failure_threshold=2, recovery_timeout=15),
        }

        # Initialize backend if Redis URL is available
        if self._redis_url:
            self._backend = RedisCircuitBreakerBackend(
                redis_url=self._redis_url,
                key_ttl=self._key_ttl,
            )
            logger.info(
                "DistributedCircuitBreakerManager initialized with Redis backend"
            )
        else:
            logger.info(
                "DistributedCircuitBreakerManager initialized without Redis "
                "(falling back to local circuit breakers)"
            )

    @property
    def is_distributed(self) -> bool:
        """Whether this manager creates distributed (Redis-backed) breakers."""
        return self._backend is not None

    def get_or_create(
        self, name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> ConnectionCircuitBreaker:
        """Get an existing circuit breaker or create a new one.

        If Redis is configured, creates a :class:`DistributedCircuitBreaker`.
        Otherwise creates a standard :class:`ConnectionCircuitBreaker`.

        Args:
            name: Unique name for the circuit breaker.
            config: Optional configuration override.

        Returns:
            A circuit breaker instance (distributed or local).
        """
        if name not in self._breakers:
            effective_config = config or self._default_config
            if self._backend is not None:
                self._breakers[name] = DistributedCircuitBreaker(
                    name=name,
                    backend=self._backend,
                    config=effective_config,
                )
            else:
                self._breakers[name] = ConnectionCircuitBreaker(
                    config=effective_config,
                )
        return self._breakers[name]

    def create_circuit_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        pattern: Optional[str] = None,
    ) -> ConnectionCircuitBreaker:
        """Create a circuit breaker with optional pattern-based configuration.

        Args:
            name: Unique name for the circuit breaker.
            config: Optional configuration override.
            pattern: Optional pattern name ("database", "api", "cache") for
                preset configurations.

        Returns:
            A circuit breaker instance (distributed or local).
        """
        if pattern and pattern in self._patterns:
            config = config or self._patterns[pattern]
        return self.get_or_create(name, config)

    def get_circuit_breaker(self, name: str) -> Optional[ConnectionCircuitBreaker]:
        """Get an existing circuit breaker by name.

        Args:
            name: Circuit breaker name.

        Returns:
            The circuit breaker, or ``None`` if not found.
        """
        return self._breakers.get(name)

    async def execute_with_circuit_breaker(
        self, name: str, func: Callable, fallback: Optional[Callable] = None
    ):
        """Execute a function protected by a named circuit breaker.

        Args:
            name: Circuit breaker name.
            func: Async callable to execute.
            fallback: Optional fallback callable invoked when the circuit is open.

        Returns:
            The result of ``func`` or ``fallback``.

        Raises:
            CircuitBreakerError: If the circuit is open and no fallback is given.
        """
        cb = self.get_or_create(name)
        try:
            return await cb.call(func)
        except CircuitBreakerError:
            if fallback:
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback()
                else:
                    return fallback()
            raise

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all managed circuit breakers.

        Returns:
            Dictionary mapping breaker names to their status dicts.
        """
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    async def reset_all(self):
        """Reset all managed circuit breakers to initial state."""
        for breaker in self._breakers.values():
            await breaker.reset()

    def set_default_config(self, config: CircuitBreakerConfig):
        """Set default configuration for new breakers.

        Args:
            config: The new default configuration.
        """
        self._default_config = config
