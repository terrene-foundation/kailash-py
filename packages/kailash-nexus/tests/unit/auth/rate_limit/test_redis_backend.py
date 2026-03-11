"""Unit tests for RedisBackend (TODO-310D).

Tier 1 tests - tests basic initialization and error handling.
Does NOT test actual Redis connectivity (that's Tier 2).
"""

import pytest
from nexus.auth.rate_limit.backends.base import RateLimitBackend

# =============================================================================
# Tests: Redis Backend Import
# =============================================================================


class TestRedisBackendImport:
    """Test RedisBackend import and initialization."""

    def test_redis_backend_importable(self):
        """RedisBackend is importable."""
        from nexus.auth.rate_limit.backends.redis import RedisBackend

        assert RedisBackend is not None

    def test_redis_backend_is_rate_limit_backend(self):
        """RedisBackend is a RateLimitBackend subclass."""
        from nexus.auth.rate_limit.backends.redis import RedisBackend

        assert issubclass(RedisBackend, RateLimitBackend)

    def test_redis_backend_has_lua_script(self):
        """RedisBackend has Lua rate limit script."""
        from nexus.auth.rate_limit.backends.redis import RedisBackend

        assert hasattr(RedisBackend, "_RATE_LIMIT_SCRIPT")
        assert "ZREMRANGEBYSCORE" in RedisBackend._RATE_LIMIT_SCRIPT
        assert "ZCARD" in RedisBackend._RATE_LIMIT_SCRIPT
        assert "ZADD" in RedisBackend._RATE_LIMIT_SCRIPT

    def test_redis_availability_flag(self):
        """REDIS_AVAILABLE flag reflects redis package availability."""
        from nexus.auth.rate_limit.backends.redis import REDIS_AVAILABLE

        # redis package may or may not be installed
        assert isinstance(REDIS_AVAILABLE, bool)


# =============================================================================
# Tests: Redis Backend Initialization
# =============================================================================


class TestRedisBackendInit:
    """Test RedisBackend initialization."""

    def test_init_stores_config(self):
        """Init stores configuration parameters."""
        from nexus.auth.rate_limit.backends.redis import REDIS_AVAILABLE

        if not REDIS_AVAILABLE:
            pytest.skip("redis package not installed")

        from nexus.auth.rate_limit.backends.redis import RedisBackend

        backend = RedisBackend(
            redis_url="redis://localhost:6379/0",
            key_prefix="test:rl:",
            pool_size=25,
            timeout_seconds=3.0,
            fail_open=False,
        )
        assert backend._redis_url == "redis://localhost:6379/0"
        assert backend._key_prefix == "test:rl:"
        assert backend._pool_size == 25
        assert backend._timeout == 3.0
        assert backend._fail_open is False
        assert backend._initialized is False

    def test_init_default_values(self):
        """Init uses correct defaults."""
        from nexus.auth.rate_limit.backends.redis import REDIS_AVAILABLE

        if not REDIS_AVAILABLE:
            pytest.skip("redis package not installed")

        from nexus.auth.rate_limit.backends.redis import RedisBackend

        backend = RedisBackend(redis_url="redis://localhost:6379/0")
        assert backend._key_prefix == "nexus:rl:"
        assert backend._pool_size == 50
        assert backend._timeout == 5.0
        assert backend._fail_open is True

    def test_init_raises_without_redis_package(self):
        """Init raises ImportError if redis not installed."""
        from nexus.auth.rate_limit.backends.redis import REDIS_AVAILABLE

        if REDIS_AVAILABLE:
            pytest.skip("redis package is installed - can't test ImportError")

        from nexus.auth.rate_limit.backends.redis import RedisBackend

        with pytest.raises(ImportError, match="redis package required"):
            RedisBackend(redis_url="redis://localhost:6379/0")

    @pytest.mark.asyncio
    async def test_check_fail_open_when_not_initialized(self):
        """check_and_record fails open when not initialized."""
        from nexus.auth.rate_limit.backends.redis import REDIS_AVAILABLE

        if not REDIS_AVAILABLE:
            pytest.skip("redis package not installed")

        from nexus.auth.rate_limit.backends.redis import RedisBackend

        backend = RedisBackend(
            redis_url="redis://localhost:6379/0",
            fail_open=True,
        )
        # Not initialized but fail_open=True
        allowed, remaining, reset_at = await backend.check_and_record(
            "user-1", limit=10
        )
        assert allowed is True
        assert remaining == 10

    @pytest.mark.asyncio
    async def test_check_fail_closed_when_not_initialized(self):
        """check_and_record raises when not initialized and fail_open=False."""
        from nexus.auth.rate_limit.backends.redis import REDIS_AVAILABLE

        if not REDIS_AVAILABLE:
            pytest.skip("redis package not installed")

        from nexus.auth.rate_limit.backends.redis import RedisBackend

        backend = RedisBackend(
            redis_url="redis://localhost:6379/0",
            fail_open=False,
        )
        with pytest.raises(RuntimeError, match="not initialized"):
            await backend.check_and_record("user-1", limit=10)
