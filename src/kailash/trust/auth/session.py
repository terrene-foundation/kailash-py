# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SSO state nonce validation -- framework-agnostic.

Extracted from ``nexus.auth.sso`` (SPEC-06). Provides pluggable session/state
stores for SSO CSRF nonce validation that work independently of any HTTP framework.

For production multi-process deployments, implement the ``SessionStore`` protocol
with a Redis-backed store.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "SessionStore",
    "InMemorySessionStore",
    "InvalidStateError",
]


class InvalidStateError(Exception):
    """Raised when SSO state is invalid or expired."""

    pass


@runtime_checkable
class SessionStore(Protocol):
    """Protocol for SSO CSRF state storage.

    Implementations must provide store, validate, and cleanup methods.
    The default InMemorySessionStore is suitable for single-process
    development only. For production multi-process or multi-server
    deployments, use a Redis-backed implementation.

    Example Redis implementation::

        class RedisSSOStateStore:
            def __init__(self, redis_client, ttl=600):
                self._redis = redis_client
                self._ttl = ttl

            def store(self, state: str) -> None:
                self._redis.setex(f"sso:state:{state}", self._ttl, "1")

            def validate_and_consume(self, state: str) -> bool:
                key = f"sso:state:{state}"
                pipe = self._redis.pipeline()
                pipe.get(key)
                pipe.delete(key)
                result = pipe.execute()
                return result[0] is not None

            def cleanup(self) -> None:
                pass  # Redis TTL handles expiration
    """

    def store(self, state: str) -> None:
        """Store a new CSRF state token."""
        ...

    def validate_and_consume(self, state: str) -> bool:
        """Validate state token and remove it (single use).

        Returns:
            True if state was valid and not expired, False otherwise
        """
        ...

    def cleanup(self) -> None:
        """Remove expired state entries."""
        ...


class InMemorySessionStore:
    """In-memory SSO state store for development.

    WARNING: Not suitable for production multi-process deployments.
    State is not shared between workers/servers and is lost on restart.
    Use a Redis-backed store for production.
    """

    def __init__(self, ttl_seconds: int = 600):
        self._store: Dict[str, float] = {}
        self._ttl = ttl_seconds

    def store(self, state: str) -> None:
        """Store a new state token with current timestamp."""
        self.cleanup()
        self._store[state] = time.time()

    def validate_and_consume(self, state: str) -> bool:
        """Validate and atomically consume state token."""
        stored_time = self._store.pop(state, None)
        if stored_time is None:
            return False
        if time.time() - stored_time > self._ttl:
            return False
        return True

    def cleanup(self) -> None:
        """Remove expired state entries."""
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v > self._ttl]
        for k in expired:
            del self._store[k]
