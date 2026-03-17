"""Unit tests for the distributed circuit breaker with Redis backend.

Tier 1 tests - Fast isolated testing with mocked Redis, no external dependencies.
All tests must complete in <1 second with no sleep/delays.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.kailash.core.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerMetrics,
    CircuitState,
)
from src.kailash.core.resilience.distributed_circuit_breaker import (
    DistributedCircuitBreaker,
    DistributedCircuitBreakerManager,
    RedisCircuitBreakerBackend,
    _KEY_PREFIX,
)


# ============================================================
# Helpers
# ============================================================


def _mock_redis_client():
    """Create a mock Redis client with common methods."""
    client = MagicMock()
    client.ping.return_value = True
    client.get.return_value = None
    client.set.return_value = True
    client.delete.return_value = True
    client.expire.return_value = True
    # register_script returns a callable script object
    script = MagicMock()
    script.return_value = 1
    client.register_script.return_value = script
    return client


# ============================================================
# RedisCircuitBreakerBackend Tests
# ============================================================


class TestRedisCircuitBreakerBackend:
    """Tests for the Redis-backed circuit breaker state storage."""

    def test_backend_uses_env_var_when_no_url(self):
        """Backend reads CIRCUIT_BREAKER_REDIS_URL from env when url is empty."""
        with patch.dict(
            "os.environ", {"CIRCUIT_BREAKER_REDIS_URL": "redis://env:6379"}
        ):
            backend = RedisCircuitBreakerBackend()
            assert backend.redis_url == "redis://env:6379"

    def test_backend_explicit_url_overrides_env(self):
        """Explicit redis_url takes priority over environment variable."""
        with patch.dict(
            "os.environ", {"CIRCUIT_BREAKER_REDIS_URL": "redis://env:6379"}
        ):
            backend = RedisCircuitBreakerBackend(redis_url="redis://explicit:6379")
            assert backend.redis_url == "redis://explicit:6379"

    def test_get_state_returns_closed_when_key_missing(self):
        """Missing Redis key defaults to CLOSED state."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.get.return_value = None
        backend._client = mock_client
        backend._transition_script = mock_client.register_script.return_value
        backend._failure_script = mock_client.register_script.return_value

        state = backend.get_state("test-breaker")
        assert state.value == "closed"

    def test_get_state_parses_stored_value(self):
        """Backend correctly parses stored CircuitState string from Redis."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.get.return_value = "open"
        backend._client = mock_client

        state = backend.get_state("test-breaker")
        assert state.value == "open"

    def test_get_state_returns_none_on_redis_error(self):
        """Backend returns None (triggering local fallback) when Redis fails."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.get.side_effect = ConnectionError("Connection refused")
        backend._client = mock_client

        state = backend.get_state("test-breaker")
        assert state is None

    def test_get_failure_count_returns_zero_when_missing(self):
        """Missing failure count key defaults to 0."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.get.return_value = None
        backend._client = mock_client

        count = backend.get_failure_count("test-breaker")
        assert count == 0

    def test_get_failure_count_parses_integer(self):
        """Backend parses stored failure count as integer."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.get.return_value = "7"
        backend._client = mock_client

        count = backend.get_failure_count("test-breaker")
        assert count == 7

    def test_get_last_failure_time_returns_zero_when_missing(self):
        """Missing last failure key defaults to 0.0."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.get.return_value = None
        backend._client = mock_client

        ts = backend.get_last_failure_time("test-breaker")
        assert ts == 0.0

    def test_set_state_writes_to_redis(self):
        """set_state writes the state value and sets TTL."""
        backend = RedisCircuitBreakerBackend(
            redis_url="redis://test:6379", key_ttl=3600
        )
        mock_client = _mock_redis_client()
        backend._client = mock_client

        result = backend.set_state("test-breaker", CircuitState.OPEN)
        assert result is True
        mock_client.set.assert_called_once_with(
            f"{_KEY_PREFIX}:test-breaker:state", "open"
        )
        mock_client.expire.assert_called_once_with(
            f"{_KEY_PREFIX}:test-breaker:state", 3600
        )

    def test_set_state_returns_false_on_redis_error(self):
        """set_state returns False when Redis is unavailable."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.set.side_effect = ConnectionError("Connection refused")
        backend._client = mock_client

        result = backend.set_state("test-breaker", CircuitState.OPEN)
        assert result is False

    def test_atomic_transition_uses_lua_script(self):
        """atomic_transition executes the registered Lua script."""
        backend = RedisCircuitBreakerBackend(
            redis_url="redis://test:6379", key_ttl=3600
        )
        mock_client = _mock_redis_client()
        mock_script = MagicMock(return_value=1)
        backend._client = mock_client
        backend._transition_script = mock_script
        backend._failure_script = MagicMock()

        result = backend.atomic_transition(
            "test-breaker", CircuitState.CLOSED, CircuitState.OPEN
        )
        assert result is True
        mock_script.assert_called_once()
        call_kwargs = mock_script.call_args
        assert call_kwargs[1]["args"] == ["closed", "open", "3600"]

    def test_atomic_transition_returns_false_when_state_mismatch(self):
        """atomic_transition returns False when current state does not match."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_script = MagicMock(return_value=0)
        backend._client = mock_client
        backend._transition_script = mock_script
        backend._failure_script = MagicMock()

        result = backend.atomic_transition(
            "test-breaker", CircuitState.CLOSED, CircuitState.OPEN
        )
        assert result is False

    def test_record_failure_returns_new_count(self):
        """record_failure returns the incremented failure count."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_script = MagicMock(return_value=5)
        backend._client = mock_client
        backend._failure_script = mock_script
        backend._transition_script = MagicMock()

        count = backend.record_failure("test-breaker")
        assert count == 5

    def test_record_failure_returns_none_on_redis_error(self):
        """record_failure returns None when Redis is unavailable."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_script = MagicMock(side_effect=ConnectionError("gone"))
        backend._client = mock_client
        backend._failure_script = mock_script

        count = backend.record_failure("test-breaker")
        assert count is None

    def test_reset_failure_count(self):
        """reset_failure_count sets the counter to zero."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        backend._client = mock_client

        result = backend.reset_failure_count("test-breaker")
        assert result is True
        mock_client.set.assert_called_once_with(
            f"{_KEY_PREFIX}:test-breaker:failure_count", "0"
        )

    def test_delete_all_removes_keys(self):
        """delete_all removes all three Redis keys for a breaker."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        backend._client = mock_client

        result = backend.delete_all("test-breaker")
        assert result is True
        mock_client.delete.assert_called_once_with(
            f"{_KEY_PREFIX}:test-breaker:state",
            f"{_KEY_PREFIX}:test-breaker:failure_count",
            f"{_KEY_PREFIX}:test-breaker:last_failure",
        )

    def test_ping_returns_true_when_connected(self):
        """ping returns True when Redis responds."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.ping.return_value = True
        backend._client = mock_client

        assert backend.ping() is True

    def test_ping_returns_false_when_disconnected(self):
        """ping returns False when Redis is unreachable."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        mock_client = _mock_redis_client()
        mock_client.ping.side_effect = ConnectionError("refused")
        backend._client = mock_client

        assert backend.ping() is False

    def test_key_naming_convention(self):
        """Verify Redis key naming follows the cb:{name}:{field} convention."""
        backend = RedisCircuitBreakerBackend(redis_url="redis://test:6379")
        assert backend._state_key("api") == "cb:api:state"
        assert backend._failure_count_key("api") == "cb:api:failure_count"
        assert backend._last_failure_key("api") == "cb:api:last_failure"


# ============================================================
# DistributedCircuitBreaker Tests
# ============================================================


class TestDistributedCircuitBreaker:
    """Tests for the distributed circuit breaker extending ConnectionCircuitBreaker."""

    def _make_breaker(self, state=CircuitState.CLOSED, failure_count=0):
        """Create a DistributedCircuitBreaker with a mocked backend."""
        backend = MagicMock(spec=RedisCircuitBreakerBackend)
        backend.get_state.return_value = state
        backend.get_failure_count.return_value = failure_count
        backend.get_last_failure_time.return_value = 0.0
        backend.ping.return_value = True
        backend.atomic_transition.return_value = True
        backend.set_state.return_value = True
        backend.reset_failure_count.return_value = True
        backend.delete_all.return_value = True
        backend.record_failure.return_value = failure_count + 1

        breaker = DistributedCircuitBreaker(
            name="test-svc",
            backend=backend,
            config=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=10,
                min_calls_before_evaluation=1,
            ),
        )
        return breaker, backend

    def test_init_syncs_state_from_redis(self):
        """Constructor pulls current state from Redis backend."""
        breaker, backend = self._make_breaker(state=CircuitState.OPEN, failure_count=5)
        assert breaker.state.value == "open"
        assert breaker.metrics.consecutive_failures == 5

    def test_init_defaults_to_closed_when_redis_unavailable(self):
        """When Redis returns None, breaker defaults to CLOSED."""
        backend = MagicMock(spec=RedisCircuitBreakerBackend)
        backend.get_state.return_value = None
        backend.get_failure_count.return_value = None
        backend.get_last_failure_time.return_value = None

        breaker = DistributedCircuitBreaker(name="test", backend=backend)
        assert breaker.state.value == "closed"

    @pytest.mark.asyncio
    async def test_force_open_updates_redis(self):
        """force_open writes OPEN state to Redis backend."""
        breaker, backend = self._make_breaker()
        await breaker.force_open("test reason")
        # Verify set_state was called with correct name and OPEN state
        assert backend.set_state.call_count == 1
        call_args = backend.set_state.call_args[0]
        assert call_args[0] == "test-svc"
        assert call_args[1].value == "open"
        assert breaker.state.value == "open"

    @pytest.mark.asyncio
    async def test_force_close_updates_redis(self):
        """force_close writes CLOSED state and resets failures in Redis."""
        breaker, backend = self._make_breaker(state=CircuitState.OPEN, failure_count=5)
        await breaker.force_close("recovery")
        # Verify set_state was called with CLOSED
        assert backend.set_state.call_count == 1
        call_args = backend.set_state.call_args[0]
        assert call_args[0] == "test-svc"
        assert call_args[1].value == "closed"
        backend.reset_failure_count.assert_called_once_with("test-svc")
        assert breaker.state.value == "closed"

    @pytest.mark.asyncio
    async def test_reset_deletes_redis_keys(self):
        """reset clears all Redis keys for the breaker."""
        breaker, backend = self._make_breaker(state=CircuitState.OPEN)
        await breaker.reset()
        backend.delete_all.assert_called_once_with("test-svc")
        assert breaker.state.value == "closed"

    def test_get_status_includes_distributed_fields(self):
        """get_status includes distributed metadata."""
        breaker, _ = self._make_breaker()
        status = breaker.get_status()
        assert status["distributed"] is True
        assert status["name"] == "test-svc"
        assert "redis_available" in status

    @pytest.mark.asyncio
    async def test_record_failure_pushes_to_redis(self):
        """_record_failure increments the Redis failure counter."""
        breaker, backend = self._make_breaker()
        error = RuntimeError("test error")
        await breaker._record_failure(error, duration=0.1)
        backend.record_failure.assert_called_once_with("test-svc")

    @pytest.mark.asyncio
    async def test_record_failure_falls_back_to_local_on_redis_error(self):
        """When Redis record_failure returns None, local recording proceeds."""
        breaker, backend = self._make_breaker()
        backend.record_failure.return_value = None  # Redis unavailable
        error = RuntimeError("test error")
        # Should not raise -- falls back to parent implementation
        await breaker._record_failure(error, duration=0.1)
        assert breaker.metrics.failed_calls >= 1


# ============================================================
# DistributedCircuitBreakerManager Tests
# ============================================================


class TestDistributedCircuitBreakerManager:
    """Tests for the factory that creates distributed circuit breakers."""

    def test_manager_creates_distributed_breakers_with_redis_url(self):
        """Manager creates DistributedCircuitBreaker when redis_url is set."""
        with patch(
            "src.kailash.core.resilience.distributed_circuit_breaker."
            "RedisCircuitBreakerBackend"
        ) as MockBackend:
            mock_instance = MagicMock()
            mock_instance.get_state.return_value = CircuitState.CLOSED
            mock_instance.get_failure_count.return_value = 0
            mock_instance.get_last_failure_time.return_value = 0.0
            MockBackend.return_value = mock_instance

            manager = DistributedCircuitBreakerManager(
                redis_url="redis://localhost:6379"
            )
            assert manager.is_distributed is True

            breaker = manager.get_or_create("test-service")
            assert isinstance(breaker, DistributedCircuitBreaker)

    def test_manager_creates_local_breakers_without_redis_url(self):
        """Manager falls back to local ConnectionCircuitBreaker without Redis."""
        manager = DistributedCircuitBreakerManager(redis_url="")
        assert manager.is_distributed is False

        breaker = manager.get_or_create("test-service")
        assert not isinstance(breaker, DistributedCircuitBreaker)

    def test_manager_reuses_existing_breakers(self):
        """get_or_create returns the same instance for the same name."""
        manager = DistributedCircuitBreakerManager(redis_url="")
        breaker1 = manager.get_or_create("svc-a")
        breaker2 = manager.get_or_create("svc-a")
        assert breaker1 is breaker2

    def test_manager_uses_pattern_config(self):
        """create_circuit_breaker applies pattern-based configuration."""
        manager = DistributedCircuitBreakerManager(redis_url="")
        breaker = manager.create_circuit_breaker("db-pool", pattern="database")
        assert breaker.config.failure_threshold == 5
        assert breaker.config.recovery_timeout == 60

    def test_manager_get_circuit_breaker_returns_none_for_unknown(self):
        """get_circuit_breaker returns None for non-existent breakers."""
        manager = DistributedCircuitBreakerManager(redis_url="")
        assert manager.get_circuit_breaker("nonexistent") is None

    def test_manager_reads_redis_url_from_env(self):
        """Manager reads CIRCUIT_BREAKER_REDIS_URL from environment."""
        with patch.dict(
            "os.environ", {"CIRCUIT_BREAKER_REDIS_URL": "redis://envhost:6379"}
        ):
            with patch(
                "src.kailash.core.resilience.distributed_circuit_breaker."
                "RedisCircuitBreakerBackend"
            ) as MockBackend:
                mock_instance = MagicMock()
                MockBackend.return_value = mock_instance
                manager = DistributedCircuitBreakerManager()
                assert manager.is_distributed is True

    def test_manager_get_all_status(self):
        """get_all_status returns status for all managed breakers."""
        manager = DistributedCircuitBreakerManager(redis_url="")
        manager.get_or_create("svc-a")
        manager.get_or_create("svc-b")

        statuses = manager.get_all_status()
        assert "svc-a" in statuses
        assert "svc-b" in statuses
        assert statuses["svc-a"]["state"] == "closed"

    def test_manager_set_default_config(self):
        """set_default_config changes config for subsequent breakers."""
        manager = DistributedCircuitBreakerManager(redis_url="")
        custom_config = CircuitBreakerConfig(failure_threshold=10, recovery_timeout=120)
        manager.set_default_config(custom_config)

        breaker = manager.get_or_create("custom-svc")
        assert breaker.config.failure_threshold == 10
        assert breaker.config.recovery_timeout == 120
