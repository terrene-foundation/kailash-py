"""Rate limiting configuration.

Provides RateLimitConfig dataclass for configuring rate limiting behavior,
backends, per-route overrides, and response headers.
"""

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        requests_per_minute: Default requests allowed per minute (default: 100)
        burst_size: Additional burst allowance above base rate (default: 20)
        backend: Backend type - "memory" or "redis" (default: "memory")
        redis_url: Redis connection URL (required if backend="redis")
        redis_key_prefix: Prefix for Redis keys (default: "nexus:rl:")
        redis_connection_pool_size: Redis connection pool size (default: 50)
        redis_timeout_seconds: Redis operation timeout (default: 5.0)
        route_limits: Per-route limit overrides, path pattern -> config dict
        include_headers: Whether to add X-RateLimit-* headers (default: True)
        fail_open: Allow requests when backend unavailable (default: True)

    Example:
        >>> config = RateLimitConfig(
        ...     requests_per_minute=100,
        ...     burst_size=20,
        ...     backend="redis",
        ...     redis_url="redis://localhost:6379/0",
        ...     route_limits={
        ...         "/api/chat/*": {"requests_per_minute": 30},
        ...         "/api/auth/login": {"requests_per_minute": 10, "burst_size": 5},
        ...         "/health": None,  # No rate limit
        ...     },
        ...     include_headers=True,
        ... )
    """

    # Base limits
    requests_per_minute: int = 100
    burst_size: int = 20

    # Backend configuration
    backend: Literal["memory", "redis"] = "memory"
    redis_url: Optional[str] = None
    redis_key_prefix: str = "nexus:rl:"
    redis_connection_pool_size: int = 50
    redis_timeout_seconds: float = 5.0

    # Per-route overrides (path pattern -> config or None to disable)
    route_limits: Dict[str, Optional[Dict[str, int]]] = field(default_factory=dict)

    # Response behavior
    include_headers: bool = True

    # Failure behavior
    fail_open: bool = True  # Allow requests when backend fails

    def __post_init__(self):
        """Validate configuration."""
        if self.requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        if self.burst_size < 0:
            raise ValueError("burst_size cannot be negative")
        if self.backend == "redis" and not self.redis_url:
            raise ValueError("redis_url required when backend='redis'")
