"""Resilience patterns for connection management."""

from .circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerManager,
    CircuitState,
    ConnectionCircuitBreaker,
)
from .distributed_circuit_breaker import (
    DistributedCircuitBreaker,
    DistributedCircuitBreakerManager,
    RedisCircuitBreakerBackend,
)

__all__ = [
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitBreakerManager",
    "CircuitState",
    "ConnectionCircuitBreaker",
    "DistributedCircuitBreaker",
    "DistributedCircuitBreakerManager",
    "RedisCircuitBreakerBackend",
]
